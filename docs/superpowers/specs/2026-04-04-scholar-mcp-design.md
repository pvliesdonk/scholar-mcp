# Scholar MCP Server — Design Spec

## Overview

An MCP server providing structured access to academic literature via the
Semantic Scholar API, with OpenAlex as an enrichment/fallback layer and
optional PDF-to-Markdown conversion via a self-hosted docling-serve instance.

Built by instantiating `fastmcp-server-template` into a new repo `scholar-mcp`.
Deployed as a Docker container in an existing homelab stack (Traefik + Authelia).

## Naming

| Item | Value |
|------|-------|
| Repo | `pvliesdonk/scholar-mcp` |
| Python module | `scholar_mcp` |
| Env prefix | `SCHOLAR_MCP` |
| Human name | Scholar MCP Server |
| CLI command | `scholar-mcp` |

---

## Architecture

```
LLM Client
    │
    ▼
Scholar MCP Server (FastMCP)
    ├── httpx.AsyncClient  →  Semantic Scholar API (primary)
    ├── httpx.AsyncClient  →  OpenAlex API (enrichment / fallback resolution)
    ├── httpx.AsyncClient  →  docling-serve (optional, PDF → Markdown)
    └── aiosqlite          →  SQLite cache ($SCHOLAR_MCP_CACHE_DIR/cache.db)
```

The server is stateful (SQLite cache, PDF download directory) but otherwise a
thin API proxy. No local ML dependencies — PDF conversion delegates entirely to
a separately hosted docling-serve instance.

### API tiers

- **Semantic Scholar** — primary backend for search, retrieval, citation graph,
  and recommendations. Has dedicated endpoints for each workflow; supports
  semantic relevance ranking, TL;DR summaries, and multi-identifier resolution.
- **OpenAlex** — secondary backend, used in two specific situations:
  1. Fallback resolution: `batch_resolve` tries OpenAlex by DOI when S2 returns
     no match (covers older/niche publications with gaps in S2 coverage).
  2. Metadata enrichment: `enrich_paper` pulls institutional affiliations, funder
     data, and OA licensing details that S2 does not provide.
- **docling-serve** — optional HTTP service for PDF-to-Markdown conversion.
  All three PDF tools are always registered but guard-checked at invocation time:
  if `SCHOLAR_MCP_DOCLING_URL` is unset, they return `{"error": "docling_not_configured"}`
  immediately. This ensures the LLM knows the tools exist and can report the
  configuration gap clearly.

---

## Configuration

| Env var | Required | Default | Description |
|---------|----------|---------|-------------|
| `SCHOLAR_MCP_S2_API_KEY` | No | — | Semantic Scholar API key; enables higher rate limits |
| `SCHOLAR_MCP_DOCLING_URL` | No | — | docling-serve base URL; PDF tools return `docling_not_configured` if unset |
| `SCHOLAR_MCP_VLM_API_URL` | No | — | OpenAI-compatible endpoint for VLM enrichment (formulas, figures) |
| `SCHOLAR_MCP_VLM_API_KEY` | No | — | API key for the VLM endpoint |
| `SCHOLAR_MCP_VLM_MODEL` | No | `gpt-4o` | Model name to pass to the VLM endpoint |
| `SCHOLAR_MCP_CACHE_DIR` | No | `/data/scholar-mcp` | Directory for SQLite DB and downloaded PDFs |
| `SCHOLAR_MCP_READ_ONLY` | No | `true` | Hides write-tagged tools (`fetch_paper_pdf`) |

Validated at startup: `SCHOLAR_MCP_CACHE_DIR` must be writable. If
`SCHOLAR_MCP_DOCLING_URL` is set, the server performs a health check against it
at startup and logs a warning (not a fatal error) if it is unreachable.
`use_vlm=True` on conversion tools is silently downgraded to standard mode if
`SCHOLAR_MCP_VLM_API_URL` or `SCHOLAR_MCP_VLM_API_KEY` are unset, with a
note in the tool response.

---

## Service Object & Lifespan

**`_server_deps.py`**:

```
ServiceBundle:
    s2_client: httpx.AsyncClient       # base_url=https://api.semanticscholar.org/graph/v1
    openalex_client: httpx.AsyncClient # base_url=https://api.openalex.org
    docling_client: httpx.AsyncClient | None  # None if SCHOLAR_MCP_DOCLING_URL unset
    cache: ScholarCache                # wraps aiosqlite connection
    config: ServerConfig               # includes vlm_api_url, vlm_api_key, vlm_model
```

Lifespan creates all clients, opens the DB connection, runs schema migrations,
then yields the bundle. `finally` closes all clients and the DB.

---

## Tools

### Category 1 — Core Search & Retrieval

#### `search_papers`

Search the Semantic Scholar corpus.

- **Inputs**: `query: str`, `year_start: int | None`, `year_end: int | None`,
  `fields_of_study: list[str] | None`, `venue: str | None`,
  `min_citations: int | None`, `sort: Literal["relevance", "citations", "year"]`,
  `fields: Literal["compact", "standard", "full"] = "compact"`,
  `limit: int = 10`, `offset: int = 0`
- **Output**: list of paper records at the requested field-set level
- **Notes**: uses S2's `/paper/search` endpoint; supports both keyword and
  relevance-ranked results depending on `sort`.

#### `get_paper`

Full metadata for a single paper.

- **Inputs**: `identifier: str` — DOI, S2 paper ID, arXiv ID, ACM ID, or
  PubMed ID (S2 accepts all via its `/paper/{identifier}` endpoint)
- **Output**: full paper record (`full` field set) — title, authors with IDs,
  abstract, TL;DR, venue, year, external IDs, OA PDF URL, fields of study,
  citation count, reference count
- **Notes**: result is cached; subsequent calls for the same paper (by any
  identifier alias) are served from cache.

#### `get_author`

Author profile and publication list.

- **Inputs**: `identifier: str` — S2 author ID or free-text name;
  `limit: int = 20`, `offset: int = 0`
- **Output**: on ID lookup — author record with publications list; on name
  search — top 5 candidates with name, affiliation, h-index, paper count for
  disambiguation; paginated
- **Notes**: name-based search is inherently ambiguous; multiple candidates are
  returned with enough context for the LLM to pick the right one.

---

### Category 2 — Citation Graph

#### `get_citations`

Papers that cite a given paper (forward citations).

- **Inputs**: `identifier: str`, `limit: int = 20`, `offset: int = 0`,
  `year_start: int | None`, `year_end: int | None`,
  `min_citations: int | None`,
  `fields_of_study: list[str] | None`,
  `fields: Literal["compact", "standard", "full"] = "compact"`
- **Output**: list of citing paper records
- **Notes**: filtering and pagination are essential — well-cited papers can have
  thousands of citations.

#### `get_references`

Papers cited by a given paper (backward references).

- **Inputs**: `identifier: str`, `limit: int = 50`, `offset: int = 0`,
  `fields: Literal["compact", "standard", "full"] = "compact"`
- **Output**: list of referenced paper records

#### `get_citation_graph`

Multi-hop citation graph traversal from one or more seed papers.

- **Inputs**: `seed_ids: list[str]` (1–10 paper identifiers),
  `direction: Literal["citations", "references", "both"]`,
  `depth: int` (1–3),
  `max_nodes: int = 100`,
  `year_start: int | None`, `year_end: int | None`,
  `min_citations: int | None`,
  `fields_of_study: list[str] | None`
- **Output**:
  ```json
  {
    "nodes": [{ "id": "...", "title": "...", "year": ..., "citation_count": ... }],
    "edges": [{ "source": "...", "target": "...", "direction": "cites" }],
    "stats": { "total_nodes": N, "total_edges": N, "depth_reached": N, "truncated": bool }
  }
  ```
- **Notes**: BFS internally; deduplicates across hops; respects rate limits with
  configurable crawl delay; reads from and writes to cache. If `max_nodes` is
  hit before traversal completes, returns partial result with `truncated: true`.

#### `find_bridge_papers`

Shortest citation path between two papers.

- **Inputs**: `source_id: str`, `target_id: str`,
  `max_depth: int = 4`,
  `direction: Literal["citations", "references", "both"]`
- **Output**: ordered list of paper records forming the shortest path, or
  `{"found": false}` if no path exists within `max_depth`
- **Notes**: BFS over the citation graph; leverages cached citation/reference
  lists to avoid redundant API calls. Useful for connecting disparate literatures.

---

### Category 3 — Recommendations

#### `recommend_papers`

Paper recommendations based on example papers.

- **Inputs**: `positive_ids: list[str]` (1–5),
  `negative_ids: list[str] | None`,
  `limit: int = 10`,
  `fields: Literal["compact", "standard", "full"] = "standard"`
- **Output**: list of recommended paper records
- **Notes**: delegates to S2's `/recommendations/v1/papers` endpoint directly.

---

### Category 4 — Paper Retrieval & Conversion

#### `fetch_paper_pdf`

Download the open-access PDF of a paper.

- **Tags**: `{"write"}` — hidden in read-only mode
- **Inputs**: `identifier: str`
- **Output**: `{"path": "/data/scholar-mcp/pdfs/<paper_id>.pdf"}` on success;
  structured error if no OA PDF is available
- **Notes**: uses `openAccessPdf.url` from S2 metadata. No institutional proxy
  or paywall circumvention. Skips download if file already exists at path.

#### `convert_pdf_to_markdown`

Convert a local PDF to Markdown via docling-serve.

- **Inputs**: `file_path: str`,
  `use_vlm: bool = False`,
  `include_references: bool = True`,
  `include_figures: bool = False`,
  `table_format: Literal["markdown", "html"] = "markdown"`
- **Output**: `{"markdown": "...", "path": "/data/scholar-mcp/md/<stem>.md", "vlm_used": bool}`
- **Notes**: returns `{"error": "docling_not_configured"}` if `SCHOLAR_MCP_DOCLING_URL` is
  unset. Works on any local PDF, including manually placed paywalled papers.
  When `use_vlm=True`, uses the VLM-enhanced docling-serve path
  (`POST /v1/convert/source/async` with base64 payload) which passes formulas and
  figures to the configured VLM model (GPT-4o or compatible) for richer extraction.
  Falls back to standard path with a note in the response if VLM is not configured.
  Standard path uses `POST /v1/convert/file/async` (multipart).
  Both paths are async: submit → poll `/v1/status/poll/{task_id}` → fetch `/v1/result/{task_id}`.

#### `fetch_and_convert`

Convenience tool: resolve → download OA PDF → convert to Markdown.

- **Inputs**: `identifier: str`, `use_vlm: bool = False`
- **Output**: `{"metadata": {...}, "markdown": "..."}` on full success;
  `{"metadata": {...}, "error": "no_oa_pdf"}` if PDF unavailable;
  `{"metadata": {...}, "pdf_path": "...", "error": "docling_not_configured"}` if
  conversion is disabled
- **Notes**: each stage fails gracefully; metadata is always returned if the
  paper resolves.

---

### Category 5 — Utility

#### `batch_resolve`

Resolve a list of identifiers to full paper records.

- **Inputs**: `identifiers: list[str]` (DOIs, S2 IDs, titles, or mixed),
  `fields: Literal["compact", "standard", "full"] = "standard"`
- **Output**: list of `{"identifier": "...", "paper": {...}}` for resolved items,
  `{"identifier": "...", "error": "not_found"}` for unresolved,
  `{"identifier": "...", "paper": {...}, "confidence": 0.87, "ambiguous": true}`
  for fuzzy title matches
- **Notes**: uses S2 batch endpoint (`POST /paper/batch`) for IDs/DOIs; falls
  back to OpenAlex by DOI for papers S2 cannot resolve; title matching is fuzzy
  with a confidence score.

#### `enrich_paper`

Fetch OpenAlex metadata to supplement S2 data.

- **Inputs**: `identifier: str` (DOI preferred; S2 ID accepted if DOI is known),
  `fields: list[Literal["affiliations", "funders", "oa_status", "concepts"]]`
- **Output**: requested OpenAlex fields merged into a dict alongside the S2
  paper ID and DOI
- **Notes**: explicit tool so the LLM can request enrichment when it needs
  institutional/funder data. Result cached in `openalex` table (30-day TTL).

---

## Caching

SQLite database at `$SCHOLAR_MCP_CACHE_DIR/cache.db`, accessed via `aiosqlite`.
Schema managed with lightweight inline migrations (version table, `IF NOT EXISTS`
DDL on startup).

| Table | Key | TTL | Contents |
|-------|-----|-----|----------|
| `papers` | S2 paper ID | 30 days | Full S2 metadata (JSON blob) |
| `citation_counts` | S2 paper ID | 7 days | Citation and reference counts |
| `citations` | S2 paper ID | 7 days | List of citing paper IDs (JSON) |
| `references` | S2 paper ID | 7 days | List of referenced paper IDs (JSON) |
| `authors` | S2 author ID | 30 days | Author metadata + paper list |
| `openalex` | DOI | 30 days | OpenAlex enrichment data |
| `id_aliases` | raw identifier | no TTL | Maps DOI/arXiv ID/etc → S2 paper ID |

TTL checked on read; stale rows are re-fetched transparently. `id_aliases` has
no TTL because S2 paper IDs are stable.

### CLI cache management

```
scholar-mcp cache stats          # row counts, DB size, oldest/newest entries per table
scholar-mcp cache clear          # full wipe
scholar-mcp cache clear --older-than 30  # evict entries older than N days
```

Not exposed as MCP tools.

---

## Rate Limiting

| Mode | Delay | Max req/s |
|------|-------|-----------|
| No API key | 1.1 s inter-request | ~0.9/s |
| With `SCHOLAR_MCP_S2_API_KEY` | 0.1 s inter-request | ~10/s |

- HTTP 429 → exponential backoff, max 3 retries, then structured error
- `get_citation_graph` / `find_bridge_papers`: same delay applied per hop;
  `max_nodes` is the hard cap against runaway expansion

---

## Error Handling

All tools return structured JSON errors, never raw exception text.

| Scenario | Response |
|----------|----------|
| Paper not found | `{"error": "not_found", "identifier": "..."}` |
| Rate limited (after retries) | `{"error": "rate_limited", "retry_after_s": N}` |
| S2 upstream error | `{"error": "upstream_error", "status": N, "detail": "..."}` |
| No OA PDF available | `{"error": "no_oa_pdf", "paper_id": "...", "title": "..."}` |
| docling-serve unreachable | `{"error": "docling_unavailable", "url": "..."}` |
| PDF tools, no `DOCLING_URL` set | `{"error": "docling_not_configured"}` |
| Graph traversal cap hit | partial result + `"truncated": true` in stats |

---

## Output Format

- Structured JSON throughout — no pre-formatted prose
- Field-set presets:
  - `compact` — title, year, venue, citation count (default for list results)
  - `standard` — + authors, DOI, abstract, S2 paper ID
  - `full` — everything: TL;DR, external IDs, OA PDF URL, fields of study,
    reference count
- Citation graph uses a standard node/edge format, convertible to Mermaid,
  GraphML, or other visualisation formats downstream

---

## Testing

- `respx` to mock `httpx` calls (S2, OpenAlex, docling-serve)
- FastMCP's `mcp.test_client()` for integration-style tests
- `aiosqlite` in-memory DB (`:memory:`) for cache tests
- Test files: `test_tools_search.py`, `test_tools_graph.py`,
  `test_tools_pdf.py`, `test_tools_utility.py`, `test_cache.py`

---

## GitHub Issues Structure

### Labels

| Label | Scope |
|-------|-------|
| `area: scaffold` | Template rename, CI verification, remove template artefacts |
| `area: core-search` | `search_papers`, `get_paper`, `get_author` |
| `area: cache` | SQLite schema, TTL logic, `id_aliases`, CLI cache commands |
| `area: citation-graph` | `get_citations`, `get_references`, `get_citation_graph`, `find_bridge_papers` |
| `area: recommendations` | `recommend_papers` |
| `area: pdf` | `fetch_paper_pdf`, `convert_pdf_to_markdown`, `fetch_and_convert` |
| `area: utility` | `batch_resolve`, `enrich_paper` |
| `area: ops` | Docker compose, Traefik/Authelia config notes, env var docs |

### Milestones

| Milestone | Scope |
|-----------|-------|
| `v0.1.0` | scaffold + core-search + cache (foundation) |
| `v0.2.0` | citation graph |
| `v0.3.0` | recommendations + utility |
| `v0.4.0` | PDF tools + ops docs |

---

## Dependencies

Added to `pyproject.toml` beyond the template baseline:

| Package | Extra | Purpose |
|---------|-------|---------|
| `httpx` | core | S2, OpenAlex, docling-serve HTTP clients |
| `aiosqlite` | core | Async SQLite cache |
| `respx` | dev | Mock httpx in tests |

No ML dependencies. docling-serve and the VLM endpoint are external services.
The existing `paperless-docling-md` integration (`/mnt/docker-volumes/compose.git/40-documents/paperless-docling-md/convert.py`)
is the reference implementation for the docling-serve async API and VLM payload structure.

---

## Out of Scope

- Institutional proxy / paywall access
- OpenAlex as a co-equal primary backend
- Bulk dataset downloads
- Full-text search within converted papers (future: local vector index)
- BibTeX export (future issue)
- Trend analysis / monitoring / alerting
- Author search by name as primary workflow (find authors through their papers)

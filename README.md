# scholar-mcp

<!-- mcp-name: io.github.pvliesdonk/scholar-mcp -->

[![CI](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/pvliesdonk/scholar-mcp/graph/badge.svg)](https://codecov.io/gh/pvliesdonk/scholar-mcp) [![PyPI](https://img.shields.io/pypi/v/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/) [![Python](https://img.shields.io/pypi/pyversions/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/) [![License](https://img.shields.io/github/license/pvliesdonk/scholar-mcp)](LICENSE) [![Docker](https://img.shields.io/github/v/release/pvliesdonk/scholar-mcp?label=ghcr.io&logo=docker)](https://github.com/pvliesdonk/scholar-mcp/pkgs/container/scholar-mcp) [![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/scholar-mcp/) [![llms.txt](https://img.shields.io/badge/llms.txt-available-brightgreen)](https://pvliesdonk.github.io/scholar-mcp/llms.txt)

A [FastMCP](https://github.com/jlowin/fastmcp) server for the scholarly citation landscape — **papers**, **patents**, **books**, and **standards** — giving LLMs a unified way to search, cross-reference, and retrieve prior art across all four source types via [Semantic Scholar](https://www.semanticscholar.org/), [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops), [Open Library](https://openlibrary.org/), and standards bodies (NIST, IETF, W3C, ETSI), with [OpenAlex](https://openalex.org/) enrichment and optional [docling-serve](https://github.com/DS4SD/docling-serve) PDF/full-text conversion.

**[Documentation](https://pvliesdonk.github.io/scholar-mcp/)** | **[PyPI](https://pypi.org/project/pvliesdonk-scholar-mcp/)** | **[Docker](https://github.com/pvliesdonk/scholar-mcp/pkgs/container/scholar-mcp)**

## Features

<!-- DOMAIN-START -->

### Source domains

- **Papers** — full-text search with year/venue/field/citation filters; single-paper lookup by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID; author profile and name search; forward citations, backward references, BFS graph traversal, shortest-path bridge discovery; recommendations from positive/negative examples; BibTeX/CSL-JSON/RIS citation generation with OpenAlex venue enrichment.
- **Patents** — search across 100+ patent offices via EPO OPS with CPC/applicant/inventor/jurisdiction filters; bibliographic, claims, description, family, legal, and citations sections; NPL-to-paper resolution via Semantic Scholar and paper-to-patent citation discovery. EPO credentials are optional — other domains work without them.
- **Books** — search by title/author/keywords via Open Library (no API key required); lookup by ISBN-10/13, Open Library work ID, or edition ID; subject-based recommendations sorted by popularity; Google Books excerpts and preview links; WorldCat permalinks for library discovery; cover image caching. Papers with an ISBN in `externalIds` are automatically enriched with publisher, edition, cover URL, and subject data from Open Library.
- **Standards** — identifier resolution, search, and metadata retrieval for NIST, IETF, W3C, and ETSI standards, with optional full-text fetch and Markdown conversion via docling. Tier 2 ISO, IEC, IEEE, Common Criteria (CC), and CEN/CENELEC metadata (including ISO/IEC/IEEE joint standards and the CC ↔ ISO/IEC 15408 cross-link) is synced locally via `sync-standards`. ISO, IEC, IEEE have a live-fetch fallback for unsynced identifiers; CC and CEN have no live API and require a sync first. Citations matching standards patterns (RFC, ISO, NIST SP, IEEE, EN, CC) are automatically enriched with structured `standard_metadata` including identifier, title, body, status, and full-text URL when available (see [docs/guides/standards.md](docs/guides/standards.md)).

### Cross-cutting

- **Enrichment pipeline** — phased enrichment from multiple sources: OpenAlex (OA status, affiliations, funders, concepts), CrossRef (publisher, page ranges, container titles), Google Books (preview links, excerpts), and Open Library (book metadata). Runs automatically on paper and book results.
- **PDF conversion** — download open-access PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures; automatic fallback to ArXiv, PubMed Central, and Unpaywall when Semantic Scholar has no OA link; direct URL download for PDFs found elsewhere.
- **Intelligent caching** — SQLite-backed cache with per-table TTLs (30 days for papers/authors, 7 days for citations/references) and identifier aliasing.
- **Authentication** — bearer token, OIDC (OAuth 2.1), or both simultaneously (multi-auth).
- **Multi-transport** — stdio (Claude Desktop), HTTP (streamable-http), and SSE transports.
- **Linux packages** — `.deb` and `.rpm` packages with systemd service and security hardening.

### Coverage by domain

Per-domain depth is uneven. Papers currently have the richest tool surface (citation graph, recommendations, cross-referencing to all three other domains); standards are the leanest. That reflects public data availability, not a value hierarchy — writing a paper typically needs all four source types for citations and prior art. Parity work is tracked in [GitHub issues](https://github.com/pvliesdonk/scholar-mcp/issues) and [milestones](https://github.com/pvliesdonk/scholar-mcp/milestones); the roadmap shows intent, not a completeness commitment.
<!-- DOMAIN-END -->

## What you can do with it

<!-- DOMAIN-START -->

With this server mounted in an MCP client (Claude, etc.), you can:

- **Survey a field** — "Find the 20 most-cited papers on graph neural networks from 2020–2024 and draft a literature review outline." Composes `search_papers` + `get_citations` + `enrich_paper`.
- **Trace a citation path** — "What's the shortest citation path from 'Attention is All You Need' to 'RLHF for dialogue agents'?" Uses `find_bridge_papers` + `get_citation_graph`.
- **Cross-reference prior art** — "For this patent family, list academic papers it cites and any books or standards that show up in the description." Composes `get_patent` + `batch_resolve` + standards/book enrichment.
- **Generate a bibliography** — "Emit BibTeX for these 30 DOIs with OpenAlex venue data." Uses `generate_citations`.
- **Look up a standard** — "What's the latest status of RFC 9000, and fetch the Markdown full text." Uses `resolve_standard_identifier` + `get_standard`.
<!-- DOMAIN-END -->

<!-- ===== TEMPLATE-OWNED SECTIONS BELOW — DO NOT EDIT; CHANGES WILL BE OVERWRITTEN ON COPIER UPDATE ===== -->

## Installation

### From PyPI

```bash
pip install pvliesdonk-scholar-mcp
```

If you add optional extras via the `PROJECT-EXTRAS-START` / `PROJECT-EXTRAS-END` sentinels in `pyproject.toml`, document them below:

<!-- DOMAIN-START -->

Scholar-mcp ships two optional-dependency groups:

- **`[mcp]`** — installs FastMCP; required to run `scholar-mcp serve` and expose tools over stdio/HTTP.
- **`[all]`** — currently identical to `[mcp]`; reserved for future optional backends.

For MCP-server usage:

```bash
pip install 'pvliesdonk-scholar-mcp[mcp]'
# or, without installing into the environment:
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

Installing the bare `pvliesdonk-scholar-mcp` package is enough for library use (`from scholar_mcp import ...`) but the `scholar-mcp serve` CLI requires `[mcp]`.
<!-- DOMAIN-END -->

### From source

```bash
git clone https://github.com/pvliesdonk/scholar-mcp.git
cd scholar-mcp
uv sync --all-extras --dev
```

### Docker

```bash
docker pull ghcr.io/pvliesdonk/scholar-mcp:latest
```

A `compose.yml` ships at the repo root as a starting point — copy `.env.example` to `.env`, edit, and `docker compose up -d`.

### Linux packages (.deb / .rpm)

Download `.deb` or `.rpm` packages from the [GitHub Releases](https://github.com/pvliesdonk/scholar-mcp/releases) page. Both install a hardened systemd unit; env configuration is sourced from `/etc/scholar-mcp/env` (copy from the shipped `/etc/scholar-mcp/env.example`).

### Claude Desktop (.mcpb bundle)

Download the `.mcpb` bundle from the [GitHub Releases](https://github.com/pvliesdonk/scholar-mcp/releases) page and double-click to install, or run:

```bash
mcpb install scholar-mcp-<version>.mcpb
```

Claude Desktop prompts for required env vars via a GUI wizard — no manual JSON editing needed.

## Quick start

```bash
scholar-mcp serve                                # stdio transport
scholar-mcp serve --transport http --port 8000   # streamable HTTP
```

For library usage (embedding the domain logic without the MCP transport), import from the `scholar_mcp` package directly — backend clients live under `src/scholar_mcp/_s2_client.py`, `_epo_client.py`, `_openlibrary_client.py`, and `_standards_client.py`.

## Configuration

Core environment variables shared across all `fastmcp-pvl-core`-based services:

| Variable | Default | Description |
|---|---|---|
| `FASTMCP_LOG_LEVEL` | `INFO` | Log level for FastMCP internals and app loggers (`DEBUG` / `INFO` / `WARNING` / `ERROR`). The `-v` CLI flag overrides to `DEBUG`. |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set to `false` for plain / structured JSON log output. |
| `SCHOLAR_MCP_EVENT_STORE_URL` | `memory://` | Event store backend for HTTP session persistence — `memory://` (dev), `file:///path` (survives restarts). |

Domain-specific variables go below under [Domain configuration](#domain-configuration).

## GitHub secrets

CI workflows reference three repository secrets. Configure them via **Settings → Secrets and variables → Actions** or with `gh secret set`:

| Secret | Used by | How to generate |
|---|---|---|
| `RELEASE_TOKEN` | `release.yml`, `copier-update.yml` | Fine-grained PAT at <https://github.com/settings/personal-access-tokens/new> with `contents: write` and `pull_requests: write` (the `copier-update` cron opens PRs). Scoped to this repo. |
| `CODECOV_TOKEN` | `ci.yml` | <https://codecov.io> — sign in with GitHub, add the repo, copy the upload token from the repo settings page. |
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude.yml`, `claude-code-review.yml` | Run `claude setup-token` locally and paste the result. |

```bash
gh secret set RELEASE_TOKEN
gh secret set CODECOV_TOKEN
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

`GITHUB_TOKEN` is auto-provided — no action needed.

## Local development

The PR gate (matches CI):

```bash
uv run pytest -x -q                                  # tests
uv run ruff check --fix . && uv run ruff format .    # lint + format
uv run mypy src/ tests/                              # type-check
```

Pre-commit runs a subset of the gate on each commit; see `.pre-commit-config.yaml` for details, or [`CLAUDE.md`](CLAUDE.md) for the full Hard PR Acceptance Gates.

## Troubleshooting

### Moving a scaffolded project

`uv sync` creates `.venv/bin/*` scripts with absolute shebangs pointing at the venv Python. If you move the repo after scaffolding (`mv /old/path /new/path`), `uv run pytest` fails with `ModuleNotFoundError: No module named 'fastmcp'` because the stale shebang resolves to a different interpreter than the venv's site-packages.

**Fix:**

```bash
rm -rf .venv
uv sync --all-extras --dev
```

`uv run python -m pytest` also works as a one-shot workaround (bypasses the stale entry-script shim).

### `uv.lock` refresh after `copier update`

When `copier update` introduces new dependencies (e.g. a new extra added to `pyproject.toml.jinja`), CI runs `uv sync --frozen` which fails against a stale lockfile. Run `uv lock` locally and commit the refreshed `uv.lock` alongside accepting the copier-update PR.

## License

MIT — see [LICENSE](LICENSE).

<!-- ===== TEMPLATE-OWNED SECTIONS END ===== -->

## Domain configuration

<!-- DOMAIN-START -->

All settings are controlled via environment variables with the `SCHOLAR_MCP_` prefix.

### Core

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | — | Semantic Scholar API key ([request one](https://www.semanticscholar.org/product/api#api-key-form)); optional but recommended for higher rate limits |
| `SCHOLAR_MCP_READ_ONLY` | `true` | If `true`, write-tagged tools (`fetch_paper_pdf`, `convert_pdf_to_markdown`, `fetch_and_convert`, `fetch_pdf_by_url`, `fetch_patent_pdf`) are hidden |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Directory for the SQLite cache database and downloaded PDFs |
| `SCHOLAR_MCP_CONTACT_EMAIL` | — | Included in the OpenAlex User-Agent for [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication#the-polite-pool) access (faster rate limits); also enables Unpaywall PDF lookups |

### PDF Conversion (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_DOCLING_URL` | — | Base URL of a running [docling-serve](https://github.com/DS4SD/docling-serve) instance (e.g. `http://localhost:5001`) |
| `SCHOLAR_MCP_VLM_API_URL` | — | OpenAI-compatible VLM endpoint for formula/figure-enriched PDF conversion |
| `SCHOLAR_MCP_VLM_API_KEY` | — | API key for the VLM endpoint |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name for VLM-enriched conversion |

### Patent Search (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | — | EPO OPS consumer key ([register at developers.epo.org](https://developers.epo.org/user/register)); both key and secret must be set for patent tools to appear |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | — | EPO OPS consumer secret |

### Google Books (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` | — | Google Books API key for higher rate limits (1000 req/day without key) |

### Tier 2 standards sync (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_GITHUB_TOKEN` | — | GitHub personal access token for Relaton sync; lifts unauthenticated GitHub rate limit from 60/hr to 5,000/hr (no scopes required for public-repo reads). Useful for repeated `--force` testing; daily cron is fine unauthenticated. |

### Authentication (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_BEARER_TOKEN` | — | Static bearer token for HTTP transport authentication |
| `SCHOLAR_MCP_BASE_URL` | — | Public base URL, required for OIDC (e.g. `https://mcp.example.com`) |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | — | OIDC discovery endpoint URL |
| `SCHOLAR_MCP_OIDC_CLIENT_ID` | — | OIDC client ID |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | — | OIDC client secret |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` | — | JWT signing key; required on Linux/Docker to survive restarts (`openssl rand -hex 32`) |
<!-- DOMAIN-END -->

## Key design decisions

<!-- DOMAIN-START -->

- **Library-first, MCP-optional.** The core domain logic (S2/EPO/Open Library/standards clients, enrichment pipeline, cache) is importable without FastMCP; the MCP server is a thin async wrapper. Enables reuse in scripts, notebooks, and other servers.
- **Sync domain code, async MCP layer.** Backend clients are synchronous; MCP tools call them via `asyncio.to_thread()`. Simpler client code, explicit offloading at the transport boundary.
- **SQLite cache with per-table TTLs and identifier aliases.** Papers / authors last 30 days, citations / references 7 days. DOI ↔ S2 ID ↔ arXiv ID aliasing survives across cache clears so repeated enrichment hits the same row.
- **Read-only by default.** Write-tagged tools (PDF download/convert, patent PDF) are hidden unless `SCHOLAR_MCP_READ_ONLY=false`. Safer default for first-run.
- **Rate-limited try-once with background queueing.** S2/OpenAlex calls try once; on 429 they queue a retry-enabled background task and return `{"queued": true, "task_id": ...}`. PDF tools always queue unless the cache already has the conversion.
- **Tier 2 standards sync out-of-band.** ISO/IEC/IEEE/CC/CEN catalogues come from community Relaton dumps via `scholar-mcp sync-standards`, not live at runtime — avoids paywalled-HTML scraping and keeps tool calls fast.
<!-- DOMAIN-END -->

## Quick Start details

### stdio transport (Claude Desktop / MCP clients)

```bash
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

> **API key optional but recommended:** The server works without a Semantic Scholar API key, but unauthenticated requests are limited to ~1 req/s and will hit 429 throttles quickly during multi-step operations like citation graph traversal. [Request a free key](https://www.semanticscholar.org/product/api#api-key-form) to get ~10 req/s.

Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {
        "SCHOLAR_MCP_S2_API_KEY": "your-key"
      }
    }
  }
}
```

### HTTP transport

```bash
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve --transport http --port 8000
```

### Claude Code plugin

```bash
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

### Syncing Tier 2 standards catalogues

Tier 2 bodies (ISO, IEC, IEEE, CC, CEN) are populated from community-curated bulk dumps rather than live-scraped at MCP-server runtime. Run the sync on first install and periodically thereafter:

```bash
scholar-mcp sync-standards            # all registered bodies
scholar-mcp sync-standards --body ISO # only ISO
scholar-mcp sync-standards --body IEEE # only IEEE
scholar-mcp sync-standards --body CC   # only Common Criteria
scholar-mcp sync-standards --body CEN # only CEN/CENELEC
scholar-mcp sync-standards --force    # re-sync even if upstream SHA is unchanged
```

Schedule via cron / launchd / systemd timer — weekly is sufficient; standards change slowly. First sync can take several minutes; subsequent runs that find no upstream changes exit within seconds.

## MCP Tools

28 tools, organised by scholarly source type.

### Papers

#### Search & retrieval

| Tool | Description |
|---|---|
| `search_papers` | Full-text search with year, venue, field-of-study, and citation-count filters. Returns up to 100 results with pagination. |
| `get_paper` | Fetch full metadata for a single paper by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID. |
| `get_author` | Fetch author profile with publications, or search by name. |

#### Citation graph

| Tool | Description |
|---|---|
| `get_citations` | Forward citations (papers that cite a given paper) with optional filters. |
| `get_references` | Backward references (papers cited by a given paper). |
| `get_citation_graph` | BFS traversal from seed papers, returning nodes + edges up to configurable depth. |
| `find_bridge_papers` | Shortest citation path between two papers. |

#### Recommendations & citation generation

| Tool | Description |
|---|---|
| `recommend_papers` | Paper recommendations from 1–5 positive examples and optional negative examples. |
| `generate_citations` | Generate BibTeX, CSL-JSON, or RIS citations for up to 100 papers, with automatic entry type inference and optional OpenAlex venue enrichment. |
| `enrich_paper` | Augment Semantic Scholar metadata with OpenAlex fields (affiliations, funders, OA status, concepts). |

### Patents

| Tool | Description |
|---|---|
| `search_patents` | Search patents across 100+ patent offices via EPO OPS with CPC / applicant / inventor / jurisdiction / date filters. |
| `get_patent` | Fetch bibliographic / claims / description / family / legal / citations sections for a single patent by publication number. Citations include NPL-to-paper resolution via Semantic Scholar. |
| `get_citing_patents` | Find patents that cite a given academic paper (best-effort; EPO OPS citation search coverage is incomplete). |
| `fetch_patent_pdf` | Download a patent PDF via authenticated EPO OPS and optionally convert to Markdown. |

> Patent tools are hidden when `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET` are not set. `fetch_patent_pdf` is also write-tagged and hidden when `SCHOLAR_MCP_READ_ONLY=true`.

### Books

| Tool | Description |
|---|---|
| `search_books` | Search for books by title, author, ISBN, or keywords via Open Library. Returns up to 50 results. |
| `get_book` | Fetch book metadata by ISBN-10, ISBN-13, Open Library work ID, or edition ID. Optionally download and cache the cover image locally. |
| `get_book_excerpt` | Fetch a book excerpt and description from Google Books by ISBN. Shows preview availability and link. |
| `recommend_books` | Recommend books for a subject via Open Library, sorted by popularity. |

> Papers with an ISBN in their `externalIds` are automatically enriched with `book_metadata` (publisher, edition, cover URL, subjects, and more) from Open Library when fetched via `get_paper`, `get_citations`, `get_references`, or `get_citation_graph`. Book records also include `worldcat_url` (when ISBN-13 is present), `google_books_url`, and `snippet` from Google Books enrichment. Cover images can be downloaded and cached locally via `get_book`.

### Standards

| Tool | Description |
|---|---|
| `resolve_standard_identifier` | Normalise a messy citation string (e.g. `"rfc9000"`, `"nist 800-53"`) to canonical form and body. |
| `search_standards` | Search standards by identifier, title, or free text, optionally filtered to one body (`NIST`, `IETF`, `W3C`, `ETSI`). |
| `get_standard` | Retrieve a standard by canonical or fuzzy identifier, optionally fetching and converting the full text via docling. |

> Tier-1 bodies (NIST, IETF, W3C, ETSI) are supported with full metadata and optional full-text conversion. Tier-2 bodies (ISO, IEC, IEEE, CC, CEN/CENELEC) are populated locally via `scholar-mcp sync-standards`.

### Cross-source Utility

| Tool | Description |
|---|---|
| `batch_resolve` | Resolve up to 100 mixed identifiers (paper DOIs, patent numbers, ISBNs) to full metadata in one call, routing each to the right backend with OpenAlex fallback. |

### PDF Conversion (requires docling-serve)

| Tool | Description |
|---|---|
| `fetch_paper_pdf` | Download PDF for a paper (S2 open-access, then ArXiv/PMC/Unpaywall fallback). |
| `convert_pdf_to_markdown` | Convert a local PDF to Markdown via docling-serve. |
| `fetch_and_convert` | Full pipeline: fetch PDF (with fallback), convert to Markdown, return both. |
| `fetch_pdf_by_url` | Download a PDF from any URL and optionally convert to Markdown. |

> PDF tools are write-tagged and hidden when `SCHOLAR_MCP_READ_ONLY=true` (the default). `fetch_patent_pdf` (above) and the `get_standard` full-text mode cover the patent and standards equivalents.

### Task Polling

| Tool | Description |
|---|---|
| `get_task_result` | Poll for the result of a background task by ID. |
| `list_tasks` | List all active background tasks. |

> Long-running operations (PDF download/conversion) and rate-limited backend requests return `{"queued": true, "task_id": "..."}` immediately. Use `get_task_result` to poll for the result.

## Docker Compose

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"
      SCHOLAR_MCP_VLM_API_URL: "${VLM_API_URL:-}"
      SCHOLAR_MCP_VLM_API_KEY: "${VLM_API_KEY:-}"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
      SCHOLAR_MCP_READ_ONLY: "false"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.scholar-mcp.rule=Host(`scholar-mcp.yourdomain.com`)"

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped

volumes:
  scholar-mcp-data:
```

## Cache Management

```bash
# Show cache statistics (row counts, database size)
scholar-mcp cache stats

# Clear all cached data (preserves identifier aliases)
scholar-mcp cache clear

# Remove entries older than 30 days
scholar-mcp cache clear --older-than 30

# Override cache directory
scholar-mcp cache stats --cache-dir /path/to/cache
```

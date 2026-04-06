# Patent Extension Design Spec

**Date**: 2026-04-05
**Status**: Approved
**Scope**: Extend scholar-mcp with patent search via EPO Open Patent Services

## Overview

Add patent search capabilities to the existing Scholar MCP server using the
European Patent Office (EPO) Open Patent Services (OPS) v3.2 as the backend.
The server becomes a unified literature research tool covering both academic
papers and patents, enabling cross-referencing between the two document types.

### Design Decisions

- **Approach 1 (Flat Module Addition)**: New modules follow existing patterns
  (`_epo_client.py`, `_tools_patent.py`) rather than introducing a backend
  abstraction layer. Migration to a protocol-based abstraction (Approach 2) is
  straightforward if a third backend (e.g., PatentsView) is added later.
- **Minimal tool surface**: 3 new tools + 1 extended, not the 10 from the
  original wish list. Reduces LLM context overhead.
- **Graceful degradation**: Patent tools are hidden (not registered) when EPO
  credentials are absent. An LLM never sees tools it cannot use.
- **EPO client library**: Use `python-epo-ops-client` for auth/transport only,
  without its caching or throttling middleware (Option C). Fall back to using
  the library as-is (Option A) if disabling middleware proves problematic.

## Tool Specifications

### `search_patents`

Search for patents by keyword, classification, applicant, inventor, or date
range. The query is natural language — the tool translates it to EPO CQL
internally.

**Inputs**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | yes | — | Natural language search query, translated to CQL |
| `cpc_classification` | string | no | — | CPC classification code filter |
| `applicant` | string | no | — | Applicant name filter |
| `inventor` | string | no | — | Inventor name filter |
| `date_from` | string | no | — | Start date (ISO format YYYY-MM-DD) |
| `date_to` | string | no | — | End date (ISO format YYYY-MM-DD) |
| `date_type` | string | no | `publication` | Date field to filter: `priority`, `publication`, or `filing` |
| `jurisdiction` | string | no | — | Country code filter (e.g., EP, US, WO) |
| `limit` | int | no | 10 | Max results (max 100) |
| `offset` | int | no | 0 | Pagination offset |

**Output**: List of patent biblio records (title, abstract, applicant,
publication number, date, CPC codes, priority date).

**MCP Annotations**: `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

**Description** (shown to LLM):
> Search for patents in the European Patent Office database. Covers European
> patents and global patents via INPADOC (100+ patent offices). Accepts natural
> language queries. Use CPC classification codes, applicant names, or date
> ranges to narrow results. For academic paper search, use search_papers instead.

---

### `get_patent`

Full metadata for a single patent with configurable detail level. Combines data
from multiple EPO OPS endpoints into one response.

**Inputs**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `patent_number` | string | yes | — | Patent number in any format (EP1234567, WO2024/123456, US11234567B2, etc.) |
| `sections` | list[string] | no | `["biblio"]` | Sections to include: `biblio`, `claims`, `description`, `family`, `legal`, `citations` |

**Output**: Patent record with requested sections. Section contents:

- **biblio**: title, abstract, applicant(s), inventor(s), publication number,
  publication date, filing date, priority date, CPC/IPC classifications, URL
- **claims**: numbered claims text (English preferred)
- **description**: full patent description text
- **family**: list of family members (publication number, jurisdiction, dates,
  kind code) — same invention filed in multiple countries
- **legal**: chronological list of legal events (filing, publication, grant,
  opposition, lapse) with dates and descriptions
- **citations**: patent references and non-patent literature (NPL) references.
  NPL references are resolved to Semantic Scholar paper records where possible
  (confidence: `high` for DOI match, `medium` for title match, `null` for
  unresolved). Raw citation string always preserved as fallback.

**MCP Annotations**: `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

**Description** (shown to LLM):
> Get detailed information about a single patent. Accepts patent numbers in any
> format (EP, WO, US, etc.). By default returns bibliographic data only — use
> the sections parameter to request additional detail (claims, description,
> family members, legal status, cited references). When sections includes
> 'citations', non-patent literature references are resolved to Semantic Scholar
> papers on a best-effort basis; unresolved references are returned as raw
> citation strings.

---

### `get_citing_patents`

Find patents that cite a given academic paper. This is the reverse
cross-reference: paper → patents.

**Inputs**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `paper_id` | string | yes | — | Paper identifier (DOI preferred, also accepts S2 ID, arXiv ID) |
| `limit` | int | no | 10 | Max results |

**Output**: List of patent biblio records with `match_source` field
(`epo_search` or `openalex`).

**Strategy**:
1. Search EPO OPS cited references for the DOI or distinctive title terms
2. Query OpenAlex for patent citations of the work
3. Combine and deduplicate by patent number

**MCP Annotations**: `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

**Description** (shown to LLM):
> Find patents that cite a given academic paper. Coverage is incomplete — relies
> on EPO OPS citation search and OpenAlex, which do not capture all
> patent-to-paper citations. Best results with well-known, highly-cited papers.
> Returns confirmed matches only, not an exhaustive list. Provide a DOI for best
> matching accuracy.

---

### `batch_resolve` (Extended)

Existing tool gains patent number support.

**New optional field per item**: `type` (`"paper"` | `"patent"`, optional).
When omitted, auto-detected by heuristic: identifiers starting with a 2-letter
country code followed by digits are treated as patent numbers.

Patent items are resolved via EPO OPS, paper items via Semantic Scholar as
before. Each resolved item gains a `source_type` field (`"paper"` or
`"patent"`).

Auto-detection with optional explicit override for edge cases.

## Architecture

### New Modules

```
src/scholar_mcp/
  _epo_client.py          -- EPO OPS client (wraps python-epo-ops-client)
  _epo_xml.py             -- XML parsers for EPO OPS responses
  _patent_numbers.py      -- Patent number normalization + detection
  _tools_patent.py        -- Patent MCP tools (search, get, citing)
```

### EPO OPS Client (`_epo_client.py`)

Wraps `python-epo-ops-client` for OAuth2 auth and HTTP transport. Does not use
the library's caching or throttling middleware.

**Class: `EpoClient`**

Constructor: `consumer_key`, `consumer_secret`.

The underlying `epo_ops.Client` is synchronous — all calls go through
`asyncio.to_thread()`, consistent with the existing pattern for blocking calls.

**Methods** (all return parsed Python dicts/strings, no XML):

- `search(cql_query, range_begin, range_end)` → list of patent biblio dicts
- `get_biblio(doc_number)` → parsed biblio dict
- `get_claims(doc_number)` → claims text
- `get_description(doc_number)` → description text
- `get_family(doc_number)` → list of family member dicts
- `get_legal(doc_number)` → list of legal event dicts
- `get_images_info(doc_number)` → image metadata (future use)
- `get_image_page(url)` → bytes (future use)

All methods accept `DocdbNumber` objects (from `_patent_numbers.py`).

### XML Parsing (`_epo_xml.py`)

Focused parsers per endpoint — no generic XML→dict conversion:

- `parse_biblio_xml(xml_bytes)` → dict (title, abstract, applicants, inventors,
  pub number, dates, classifications, cited refs split into patent/NPL)
- `parse_claims_xml(xml_bytes)` → str (plain text, English preferred)
- `parse_description_xml(xml_bytes)` → str
- `parse_family_xml(xml_bytes)` → list[dict]
- `parse_legal_xml(xml_bytes)` → list[dict]
- `parse_search_xml(xml_bytes)` → list of biblio references

Uses `lxml` for XPath queries against namespaced XML (`ops:`, `reg:`, `exch:`).

### Patent Number Handling (`_patent_numbers.py`)

**`DocdbNumber`**: dataclass with `country`, `number`, `kind` fields and a
`.docdb` property returning `CC.number.kind` format.

- `normalize(raw: str) -> DocdbNumber` — parse any accepted format
- `is_patent_number(raw: str) -> bool` — heuristic for `batch_resolve`
  auto-detection

Accepted input formats: `EP1234567`, `EP 1234567 A1`, `EP1234567A1`,
`WO2024/123456`, `WO2024123456`, `US11,234,567`, `US11234567B2`, etc.

Normalization happens at the tool layer boundary — tools normalize inputs before
passing to `EpoClient`.

## Configuration

### New Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | no | — | EPO OPS consumer key |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | no | — | EPO OPS consumer secret |

Both must be set for patent tools to be enabled.

### ServiceBundle

```python
@dataclass
class ServiceBundle:
    s2: S2Client
    openalex: OpenAlexClient
    docling: DoclingClient | None
    epo: EpoClient | None          # NEW
    cache: ScholarCache
    config: ServerConfig
    tasks: TaskQueue
```

### Startup Logging

```
Backends available: Semantic Scholar (authenticated), OpenAlex, EPO OPS
```
or:
```
Backends available: Semantic Scholar (anonymous), OpenAlex — EPO OPS not configured (patent tools disabled)
```

### Conditional Tool Registration

Patent tool registration functions check `bundle.epo is not None` and return
early if not. This follows the existing pattern where `DoclingClient` is
optional.

## Caching

Same SQLite database, new tables:

| Table | TTL | Purpose |
|-------|-----|---------|
| `patents` | 90 days | Patent biblio by DOCDB number |
| `patent_claims` | 180 days | Claims text (essentially static) |
| `patent_descriptions` | 180 days | Description text (essentially static) |
| `patent_families` | 90 days | Family member lists |
| `patent_legal` | 7 days | Legal status (changes over time) |
| `patent_search` | 7 days | Search results by CQL query hash |

Cache key: normalized DOCDB format (`CC.number.kind`), so `EP1234567A1` and
`EP 1234567 A1` hit the same entry.

New methods on `ScholarCache` following the existing `get_*/set_*` pattern.
`stats()` and `clear()` automatically cover new tables.

## Rate Limiting & Task Queue

### EPO Traffic Light System

`python-epo-ops-client` exposes quota status via `X-Throttling-Control`
response header. The `EpoClient` inspects this after each response:

- **Green**: proceed normally
- **Yellow/Red**: raise `RateLimitedError` → triggers task queue background retry
- **Black**: raise hard error (daily quota exhausted)

No separate `RateLimiter` instance needed — the traffic light is server-side
quota feedback, not a client-side delay.

### Task Queue Integration

Same try-once/queue-on-429 pattern as existing tools:

```python
async def _execute(*, retry: bool = True) -> str:
    # ... tool logic ...

try:
    return await _execute(retry=False)
except RateLimitedError:
    task_id = bundle.tasks.submit(_execute(retry=True), tool="search_patents")
    return json.dumps({"queued": True, "task_id": task_id})
```

No changes to `TaskQueue` itself.

### Concurrent Section Fetching

`get_patent` with multiple sections fires parallel requests to EPO OPS, bounded
by a semaphore (consistent with existing OpenAlex enrichment pattern) to avoid
overwhelming the backend.

## Cross-Referencing Detail

### Patent → Papers (NPL Resolution)

When `get_patent` includes `sections=["citations"]`, the biblio response
contains cited references split into patent refs and NPL refs. For NPL:

1. Extract DOI from citation string (regex)
2. If DOI found: resolve via `batch_resolve` → confidence `high`
3. If unresolved: return raw citation string (and DOI if extracted but
   resolution failed) with confidence `null`

> **Deferred:** Title-based S2 fallback (confidence `medium`) is not
> implemented in Phase 3. Most NPL citations with DOIs resolve at high
> confidence; title-based fuzzy matching adds complexity and false-positive
> risk. Tracked as a future enhancement.

### Papers → Patents (`get_citing_patents`)

Best-effort discovery via EPO OPS search: search for DOI or title terms
in cited references (`ct=` CQL field). Each result includes a
`match_source` field. Tool description explicitly states coverage
limitations.

> **Deferred:** OpenAlex patent citation integration (combining EPO + OA
> results with deduplication by patent number) is not implemented in
> Phase 3. EPO-only provides the primary discovery path; OpenAlex
> integration would improve recall but adds API complexity. Tracked as
> a future enhancement.

## Dependencies

### New Python Dependencies

- `python-epo-ops-client` (>=4.2.1) — EPO OPS auth, transport
- `lxml` — XML parsing

### New Dev Dependencies

None beyond existing (`pytest`, `respx`, `mypy`, `ruff`).

## Error Handling

Patent-specific error cases:

| Error | Handling |
|-------|----------|
| Invalid patent number format | `ValueError` at normalization, tool returns clear error message |
| Patent not found | Return structured error with suggestion to check number format |
| Full text not available | Return biblio with empty claims/description and a note |
| Family not available | Return empty family list with a note |
| NPL resolution failed | Return raw citation string with `confidence: null` |
| EPO quota black | Hard error: "EPO daily quota exhausted, try again tomorrow" |
| EPO quota yellow/red | `RateLimitedError` → background queue with retry |

## Implementation Phases

### Phase 1 — Foundation

- `_patent_numbers.py` (normalization + detection)
- `_epo_xml.py` (XML parsers for biblio + search)
- `_epo_client.py` (client with search + get_biblio)
- `config.py`: EPO env vars
- `_server_deps.py`: optional `EpoClient` in `ServiceBundle`
- `_cache.py`: patent + patent_search tables
- `_tools_patent.py`: `search_patents` + `get_patent` (biblio section only)
- Conditional tool registration in `_server_tools.py`
- Tests + docs

### Phase 2 — Full Detail

- `_epo_xml.py`: parsers for claims, description, family, legal
- `_epo_client.py`: remaining endpoint methods
- `_cache.py`: claims, descriptions, families, legal tables
- `_tools_patent.py`: `get_patent` remaining sections
- Concurrent section fetching with semaphore
- Tests + docs

### Phase 3 — Cross-Referencing

- `_epo_xml.py`: cited references parsing (patent refs + NPL split)
- `_tools_patent.py`: `get_patent` citations section with NPL→S2 resolution
- `_tools_patent.py`: `get_citing_patents` (EPO search + OpenAlex)
- `_tools_utility.py`: extended `batch_resolve` with patent support
- Tests + docs

### Phase 4 — Future (Out of Scope)

Tracked as GitHub issues:

- Patent PDF retrieval (`fetch_patent_pdf`) — #43
- Patent-to-Markdown conversion (`convert_patent_to_markdown`) — #44
- USPTO PatentsView / Open Data Portal integration — #45
- Backend abstraction layer (Approach 2) — #46
- Patent-paper co-citation analysis — #47
- CPC classification browser — #48
- Obsidian Vault patent note integration — #49
- BibTeX/RIS export for patent citation formats — #50
- WIPO PATENTSCOPE integration — #51
- Patent monitoring / alerts — #52

# Standards Support Design Spec

**Date**: 2026-04-07
**Status**: Draft
**Scope**: Tier 1 standards support — NIST, IETF, W3C, ETSI — with catalogue index caching, three new tools, and optional full-text via docling

## Overview

Academic papers in security, systems engineering, and regulatory-adjacent fields frequently cite standards (ISO/IEC, NIST SP, IEEE, IETF RFCs, ETSI, W3C, etc.). Semantic Scholar does not index standards meaningfully, and citation strings for standards are notoriously inconsistent. This feature adds standards-aware lookup, metadata resolution, and full-text access for Tier 1 sources (freely published standards with clean APIs or scrapeable catalogues).

### Milestone

v0.8.0 — Standards support (Tier 1)

### Out of scope for this milestone

- Tier 2 paywalled bodies (ISO, IEC, IEEE, CEN/CENELEC) → separate issues
- Tier 3 / Common Criteria portal → separate issue
- Enrichment integration (auto-detection in `get_paper` / `get_references` / `get_citations`) → separate issue
- Citation formatting for `StandardRecord` (BibLaTeX `@techreport`/`@manual`) → separate issue (F4)
- F1–F9 follow-ups from the wishlist → filed as GitHub issues

### Design Decisions

- **Unified `StandardsClient`**: All four source fetchers and the identifier resolver live in `_standards_client.py` behind a single `StandardsClient`. `ServiceBundle` gains one field, and the tools layer stays thin. Avoids proliferating four separate client files and keeps multi-source routing logic in one place.
- **Catalogue index for scraped sources**: ETSI has no search API. On first use, `StandardsClient` scrapes the ETSI catalogue inline (catalogue is compact — a few seconds) and caches the index for 7 days. Subsequent searches query the local index. This pattern is reserved for scraped sources; API-backed sources (NIST, IETF, W3C) query their APIs directly.
- **Full text via docling**: `get_standard` with `fetch_full_text=True` uses the same docling pipeline as `fetch_paper_pdf`. Queued via `TaskQueue` when docling is configured and `full_text_available=True`.
- **Lazy alias cache**: Resolved identifier mappings are persisted in the cache so that repeated fuzzy inputs (e.g. `"nist 800-53"`) are returned instantly from cache without re-running regex or network calls.

## Data Model

### `StandardRecord` (added to `_record_types.py`)

```python
class StandardRecord(TypedDict, total=False):
    identifier: str           # canonical: "NIST SP 800-53 Rev. 5", "RFC 9000"
    aliases: list[str]        # alt forms seen in citations
    title: str
    body: str                 # "NIST" | "IETF" | "W3C" | "ETSI"
    number: str               # "800-53", "9000", "2.1"
    revision: str | None      # "Rev. 5", "2022", "3rd edition"
    status: str               # "published" | "withdrawn" | "superseded" | "draft"
    published_date: str | None
    withdrawn_date: str | None
    superseded_by: str | None
    supersedes: list[str]
    scope: str | None         # abstract / scope statement
    committee: str | None
    url: str                  # canonical catalogue URL
    full_text_url: str | None # direct PDF/HTML link if freely available
    full_text_available: bool # True for all Tier 1 sources
    price: str | None         # None for Tier 1; populated for Tier 2
    related: list[str]        # related standard identifiers
```

`total=False` is consistent with `BookRecord`. The `body` field is constrained to known values but typed as `str` to allow forward-compatible extension.

## Identifier Resolution

Resolution is a two-stage process implemented as a module-level function in `_standards_client.py`:

```python
def resolve_identifier(raw: str) -> tuple[str, str] | None:
    """Return (canonical_identifier, body) or None."""
```

### Stage 1 — Local regex (no network)

A table of compiled patterns matched in priority order:

| Body | Example inputs | Canonical form |
|------|---------------|----------------|
| NIST | `"nist 800-53"`, `"SP800-53r5"`, `"FIPS140-3"`, `"NISTIR 8259A"` | `"NIST SP 800-53 Rev. 5"` |
| IETF | `"rfc9000"`, `"RFC 9000"`, `"rfc-9000"` | `"RFC 9000"` |
| W3C | `"WCAG2.1"`, `"wcag 2.1"`, `"W3C WCAG 2.1"` | `"WCAG 2.1"` |
| ETSI | `"etsi en 303645"`, `"ETSI EN 303 645"` | `"ETSI EN 303 645"` |

Body-specific normalization rules:
- **NIST**: strip `"NIST"` / `"SP"` prefix, normalize revision suffixes (`"r5"` → `"Rev. 5"`, `"Rev5"` → `"Rev. 5"`), expand FIPS/NISTIR forms
- **IETF**: strip `"RFC"` prefix, strip leading zeros, reassemble as `"RFC {n}"`
- **W3C**: normalize version separators, strip `"W3C"` prefix
- **ETSI**: normalize spacing, uppercase type designator

### Stage 2 — API fallback

Called only when Stage 1 returns `None`. The resolver identifies the most likely body from any recognizable fragment in the raw string and calls that body's `search(query, limit=3)`. The top result is accepted if the normalized raw string is a case-insensitive substring of the result title, or the result identifier matches the raw string after stripping non-alphanumeric characters. If unresolved, returns `None`.

### Ambiguity

When a raw string resolves to multiple candidates (e.g. `"62443"` → IEC 62443-1-1, 62443-2-1, 62443-3-3, etc.), the resolver returns all candidates. The `resolve_standard_identifier` tool surfaces these with `"ambiguous": true`.

### Alias cache integration

`StandardsClient.resolve()` checks `cache.get_standard_alias(raw)` before running Stage 1 or Stage 2. On successful resolution, the mapping is written back to the alias cache. This means repeated messy strings are resolved from SQLite without any regex or network overhead.

## Source Clients

All four fetchers are implemented inside `_standards_client.py` as private async functions/classes. They share a single `httpx.AsyncClient` passed in at `StandardsClient.__init__`. Each fetcher exposes:

```python
async def search(query: str, *, limit: int = 10) -> list[StandardRecord]: ...
async def get(identifier: str) -> StandardRecord | None: ...
```

### NIST (`csrc.nist.gov`)

- **Metadata API**: individual publication at `https://csrc.nist.gov/publications/{type}/{number}/json`; search via `https://csrc.nist.gov/CSRC/media/Publications/search-results-json-file/json`
- **Coverage**: SP 800 series, SP 1800 series, FIPS, NISTIR, CSWP
- **Full text**: PDF freely downloadable, URL extracted from publication record
- **Rate limit**: 1 req/s delay
- `full_text_available: True`

### IETF (`datatracker.ietf.org` + `rfc-editor.org`)

- **Metadata**: `https://www.rfc-editor.org/rfc/rfc{n}.json`
- **Full text**: `https://www.rfc-editor.org/rfc/rfc{n}.html` (HTML), `.txt` (plain), `.pdf` (PDF) — all free
- **Search**: `https://datatracker.ietf.org/doc/search/?rfcs=on&q={query}`
- **Rate limit**: 0.5 req/s
- `full_text_available: True`

### W3C (`w3.org`)

- **Catalogue API**: `https://api.w3.org/specifications` (JSON, paginated)
- **Individual spec**: `https://api.w3.org/specifications/{shortname}`
- **Full text**: `https://www.w3.org/TR/{shortname}/` (versioned HTML)
- **Rate limit**: 0.5 req/s
- `full_text_available: True`

### ETSI (`etsi.org`)

- **No official API** — catalogue scraped from `https://www.etsi.org/standards-search/`
- **Index strategy**: on first call, scrape the catalogue inline to populate `standards_index["ETSI"]` (compact catalogue, ~seconds). Subsequent searches query the local index only. Index TTL: 7 days.
- **Full text PDF**: `https://www.etsi.org/deliver/etsi_{type}/{range}/{number}/{version}/...` (pattern-constructed from catalogue metadata)
- **Rate limit**: 2 req/s delay; aggressive caching
- `full_text_available: True`

## Cache Layer

New tables added to `_cache.py` following existing TTL patterns.

### Tables

| Table | Key | TTL | Content |
|-------|-----|-----|---------|
| `standards` | canonical identifier | 90 days | `StandardRecord` as JSON |
| `standards_aliases` | raw alias string | 90 days | canonical identifier (plain string) |
| `standards_search` | query hash (SHA-256) | 7 days | `list[StandardRecord]` as JSON |
| `standards_index` | body name (`"ETSI"`) | 7 days | catalogue stub list as JSON |

TTL constants:
```python
_STANDARD_TTL = 90 * 86400        # 90 days — standards rarely change
_STANDARD_ALIAS_TTL = 90 * 86400  # 90 days
_STANDARD_SEARCH_TTL = 7 * 86400  # 7 days
_STANDARD_INDEX_TTL = 7 * 86400   # 7 days — re-scrape weekly
```

### Cache methods added to `ScholarCache`

```python
async def get_standard(identifier: str) -> StandardRecord | None: ...
async def set_standard(identifier: str, data: StandardRecord) -> None: ...
async def get_standard_alias(raw: str) -> str | None: ...
async def set_standard_alias(raw: str, canonical: str) -> None: ...
async def get_standards_search(query: str) -> list[StandardRecord] | None: ...
async def set_standards_search(query: str, data: list[StandardRecord]) -> None: ...
async def get_standards_index(body: str) -> list[dict] | None: ...
async def set_standards_index(body: str, data: list[dict]) -> None: ...
```

## `StandardsClient` Interface

```python
class StandardsClient:
    def __init__(self, http: httpx.AsyncClient) -> None: ...

    async def search(
        self,
        query: str,
        *,
        body: str | None = None,
        limit: int = 10,
    ) -> list[StandardRecord]: ...
    # body=None searches all four sources; body="NIST" restricts to NIST

    async def get(self, identifier: str) -> StandardRecord | None: ...
    # resolves fuzzy identifiers before fetching

    async def resolve(self, raw: str) -> list[StandardRecord]: ...
    # single-item list when unambiguous; multi-item when ambiguous

    async def aclose(self) -> None: ...
```

### `ServiceBundle` integration

```python
@dataclass
class ServiceBundle:
    ...
    standards: StandardsClient   # always available, no credentials needed
```

Created in `make_service_lifespan`, closed on shutdown. `standards` is not optional — Tier 1 sources require no API keys.

## Tools (`_tools_standards.py`)

Registered via `register_standards_tools(mcp)`, called from `_server_tools.py`.

### `search_standards`

Search standards by identifier, title, or free text.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | — | Identifier, title, or free text |
| `body` | str \| None | None | Filter: `"NIST"`, `"IETF"`, `"W3C"`, `"ETSI"` |
| `limit` | int | 10 | Max results (max 50) |

Flow:
1. Check `standards_search` cache
2. On miss, route to `bundle.standards.search(query, body=body, limit=limit)`
3. Cache results
4. Return JSON list of `StandardRecord`

MCP annotations: `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

### `get_standard`

Resolve and retrieve a single standard by identifier (canonical or fuzzy).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `identifier` | str | — | Canonical or fuzzy identifier |
| `fetch_full_text` | bool | False | Fetch + convert via docling if available |

Flow:
1. Resolve identifier (alias cache → regex → API fallback)
2. Check `standards` cache
3. On miss, fetch from source via `bundle.standards.get(identifier)`
4. Cache result
5. If `fetch_full_text=True` and docling configured and `full_text_available=True`: download PDF/HTML, submit to docling. Returns task ID if queued (same pattern as `fetch_paper_pdf`).
6. Return `StandardRecord`

MCP annotations: `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

### `resolve_standard_identifier`

Normalize a messy citation string to canonical form.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `raw` | str | — | Messy citation string (e.g. `"iso27001"`, `"nist 800-53"`) |

Returns when unambiguous:
```json
{
  "canonical": "NIST SP 800-53 Rev. 5",
  "body": "NIST",
  "record": { ... }
}
```

Returns when ambiguous:
```json
{
  "ambiguous": true,
  "candidates": [ { ... }, { ... } ]
}
```

Returns when unresolvable:
```json
{
  "canonical": null,
  "body": null,
  "record": null
}
```

MCP annotations: `readOnlyHint=True, destructiveHint=False, openWorldHint=False`

## Testing

### `tests/test_standards_client.py`

- Identifier resolver — all fuzzy inputs from wishlist test cases
- Per-fetcher: mock HTTP responses → assert correct `StandardRecord` shape and field mapping
- ETSI index: cold index triggers inline scrape; warm index skips network; stale index (>7 days) re-scrapes
- Alias cache round-trip: resolve once → assert alias written; resolve again → assert no HTTP call made

### `tests/test_tools_standards.py`

- `search_standards`: cache hit; cache miss calls fetcher; `body` filter routes correctly
- `get_standard`: fuzzy resolution → fetch → cache; `fetch_full_text=True` with docling → task queued; `fetch_full_text=True` without docling → record returned with `full_text_available` flag only
- `resolve_standard_identifier`: unambiguous → canonical + record; ambiguous → candidates list; unknown input → graceful `None` response

### Test identifiers

```
NIST  : "NIST SP 800-53 Rev. 5", "FIPS 140-3", "NISTIR 8259A"
IETF  : "RFC 9000", "RFC 8446"
W3C   : "WCAG 2.1", "WebAuthn Level 2"
ETSI  : "ETSI EN 303 645"
Fuzzy : "nist 800-53" → "NIST SP 800-53 Rev. 5"
        "rfc9000"     → "RFC 9000"
        "62443"       → ambiguous (Tier 2, returns empty from Tier 1 sources)
```

## Deferred Issues

Each item below is out of scope for this milestone and becomes a separate GitHub issue.

### Tier 2: ISO metadata lookup
Scrapeable catalogue at `iso.org`. Returns metadata only (`full_text_available: False`, `price` populated). No paywall bypass.

### Tier 2: IEC metadata lookup
`webstore.iec.ch`. Overlaps with ISO/IEC joint standards. Deduplicate by identifier.

### Tier 2: IEEE Standards metadata
`standards.ieee.org`. Metadata browseable; full text paywalled unless Xplore institutional access.

### Tier 2: CEN/CENELEC metadata
European Norms not covered by ETSI. Paywalled via national mirrors. Low priority unless needed for harmonised standards cross-referencing.

### Tier 3: Common Criteria portal
`commoncriteriaportal.org`. Free PDFs. Cross-link CC and ISO/IEC 15408 identifiers.

### Enrichment integration
Auto-detect standard-like citation strings in `get_paper` / `get_references` / `get_citations`. Attach `standard_metadata` field when S2 returns sparse results.

### Citation formatting for standards (F4)
BibLaTeX `@techreport` / `@manual` output for `StandardRecord`. Per-body templates where bodies have distinct citation conventions.

### F1: National standards mirrors (NEN, DIN, BSI, AFNOR)
Extend alias resolution for national identifier forms (e.g. `"NEN-EN-ISO/IEC 27001"`).

### F2: Public.Resource.Org
Standards incorporated by reference into US law. Coverage spotty but legally open.

### F3: OASIS, OMG, 3GPP, ITU-T
All Tier 1 candidates (freely published). Deferred to avoid scope creep.

### F5: Regulatory framework cross-linking
Map standards to referencing regulations (CRA, NIS2, etc.).

### F6: Standards lifecycle tracking
Alert when a cited standard is withdrawn or superseded.

### F7: IEEE Xplore integration
Promote IEEE to Tier 1 if institutional access is available.

### F8: Perinorm integration
Commercial metadata aggregator. Only if TNO has access.

### F9: Standards recommendation
Given a paper or topic, suggest relevant standards.

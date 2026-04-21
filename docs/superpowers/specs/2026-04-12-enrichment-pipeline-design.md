# v0.6.0 Enrichment Pipeline & Data Sources Design

**Date**: 2026-04-12
**Milestone**: [v0.6.0](https://github.com/pvliesdonk/scholar-mcp/milestone/6)
**Issues**: #62, #61, #64, #66, #67, #68

## Overview

This spec covers the v0.6.0 milestone: a foundational enrichment pipeline refactor
followed by four new data source integrations and two record-level enhancements.
The pipeline is built first so all new enrichers plug into a clean, extensible
architecture from day one.

## Decisions

| Issue | Decision |
|-------|----------|
| #62 Pipeline | Foundation-first — build before features |
| #66 WorldCat | Permalink only (always populate `worldcat_url` on BookRecord). No API client — OCLC APIs require institutional subscription with no free tier. |
| #67 CrossRef | Pipeline-controlled enricher, start DOI-only predicate |
| #68 Covers | Inline `download_cover` param on `get_book`, no separate tool |
| #64 Chapters | Integrated into `batch_resolve` + patent NPL citations, no new tool |
| #61 Google Books | Enricher + optional API key + `get_book_excerpt` tool |

## 1. Enrichment Pipeline Architecture (#62)

### Enricher Protocol

```python
@runtime_checkable
class Enricher(Protocol):
    name: str              # e.g. "openalex", "crossref", "google_books"
    phase: int             # execution order group (0 = primary, 1 = secondary)
    tags: frozenset[str]   # e.g. {"papers"}, {"books"}, {"papers", "books"}

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Fast predicate — no I/O. Checks if this enricher applies."""
        ...

    async def enrich(self, record: dict[str, Any], bundle: ServiceBundle) -> None:
        """Mutate record in-place with enriched data. Best-effort, never raises."""
        ...
```

### EnrichmentPipeline

```python
class EnrichmentPipeline:
    def __init__(self, enrichers: list[Enricher]) -> None:
        # Sort into phase groups at construction time
        self._phases: dict[int, list[Enricher]] = ...

    async def enrich(
        self,
        records: list[dict[str, Any]],
        bundle: ServiceBundle,
        *,
        tags: frozenset[str] | None = None,
        concurrency: int = 5,
    ) -> None:
        """Run matching enrichers on all records, phase by phase."""
```

**Execution flow:**

1. Filter enrichers by `tags` (if provided) — e.g. `tags={"books"}` skips
   OpenAlex paper enricher.
2. For each phase (ascending order):
   - For each enricher in the phase, for each record: check `can_enrich(record)`.
   - Run all matching `(enricher, record)` pairs concurrently, bounded by
     `concurrency` semaphore.
   - Wait for all phase work to complete before moving to next phase.
3. Errors in individual `enrich()` calls are caught and logged at DEBUG — never
   propagate.

### File location

New file: `src/scholar_mcp/_enrichment.py` — contains `Enricher` protocol and
`EnrichmentPipeline` class. Each enricher is a small class in its respective
client/enrichment module (not a separate file per enricher).

`EnrichmentPipeline` instance is created in lifespan and stored on
`ServiceBundle.enrichment`.

### Migration of existing enrichers

- **OpenAlexEnricher** (phase 0, tags=`{"papers"}`): wraps current
  `_enrich_paper()` logic from `_tools_citation.py`. Predicate: record has DOI
  and is missing venue metadata.
- **OpenLibraryEnricher** (phase 1, tags=`{"papers"}`): wraps current
  `_book_enrichment.py` logic. Phase 1 because it benefits from OpenAlex having
  already populated `externalIds`. Predicate: record has ISBN in `externalIds`.

After migration, `enrich_books()` and the inline OpenAlex enrichment in
`_tools_citation.py` call `bundle.enrichment.enrich(papers, tags={"papers"})`
instead of their current ad-hoc wiring.

## 2. CrossRef Enrichment (#67)

### CrossRefClient

New file: `src/scholar_mcp/_crossref_client.py`

- Base URL: `https://api.crossref.org/works`
- Rate limiting: uses `contact_email` from config for polite pool (~50 req/s
  vs ~1 req/s). Same `SCHOLAR_MCP_CONTACT_EMAIL` already used for OpenAlex.
- No API key required.

Methods:

- `get_by_doi(doi: str) -> dict | None` — fetch `/works/{doi}`
- `search_chapters(title: str) -> list[dict]` — query with
  `filter=type:book-chapter&query.bibliographic={title}` (future use)

### CrossRefEnricher

Phase 0, tags=`{"papers"}`.

**`can_enrich()` predicate** (DOI-only to start):
- Returns `True` when record has a DOI in `externalIds` AND metadata is sparse
  (missing publisher, page range, or container-title).

**`enrich()` behavior:**
- Query `https://api.crossref.org/works/{doi}`.
- Extract: `container-title`, `publisher`, `page`, `editor`, `type`, `ISBN`.
- Store under `record["crossref_metadata"]` dict.
- If CrossRef returns `type: "book-chapter"`, also extract `page` (start/end)
  for chapter resolution (#64).

### Cache

New table `crossref`, keyed by DOI, 30-day TTL.

Protocol additions:
- `get_crossref(doi: str) -> dict | None`
- `set_crossref(doi: str, data: dict) -> None`

## 3. Google Books Integration (#61)

### GoogleBooksClient

New file: `src/scholar_mcp/_google_books_client.py`

- Base URL: `https://www.googleapis.com/books/v1/volumes`
- Optional API key: `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` (unauthenticated =
  1000 req/day).
- Rate limiter: 0.5s delay (conservative for unauthenticated use).

Methods:

- `search_by_isbn(isbn: str) -> dict | None` — query `?q=isbn:{isbn}`
- `get_volume(volume_id: str) -> dict | None` — fetch volume details
  including preview pages

### GoogleBooksEnricher

Phase 1, tags=`{"books"}`.

**`can_enrich()` predicate:**
- Returns `True` when record has `isbn_13` or `isbn_10`.

**`enrich()` behavior:**
- Query by ISBN.
- Populate `record["google_books_url"]` with `volumeInfo.previewLink`.
- Populate `record["snippet"]` from `searchInfo.textSnippet` if present.
- Phase 1 because it needs ISBN, which might come from CrossRef (phase 0).

### `get_book_excerpt` tool

Added to `_tools_books.py`:

- Input: `isbn` (required).
- Queries Google Books API for volume, checks `accessInfo.viewability`.
- If preview is available (`PARTIAL` or `ALL_PAGES`), returns the
  `searchInfo.textSnippet` and `volumeInfo.description` as the excerpt. Google
  Books does not expose full chapter text via API — the excerpt is a
  publisher-provided summary and/or search snippet, not paginated content.
- Returns: `{"excerpt": "...", "description": "...", "source": "google_books",
  "preview_available": true/false, "preview_link": "..."}`.
- Tags: `{"write"}` (downloads content). Hidden in read-only mode.
- Rate-limit-aware: queues on 429.

### Cache

New table `google_books`, keyed by ISBN, 30-day TTL.

### Config

New field: `google_books_api_key: str | None`, loaded from
`SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY`.

## 4. WorldCat Permalink (#66)

Simplified scope — OCLC APIs require institutional subscription with no free
tier available. The full holdings tool is deferred.

### Implementation

In `_openlibrary_client.py:normalize_book()`: whenever `isbn_13` is present,
set `worldcat_url = f"https://www.worldcat.org/isbn/{isbn_13}"`.

### BookRecord field addition

Add `worldcat_url: str` to `BookRecord` in `_record_types.py`.

No new client, no config, no API calls.

## 5. Cover Image Caching (#68)

Inline on `get_book` — no separate tool.

### Parameter additions to `get_book`

- `download_cover: bool = False` — when true, download and cache the cover
  image locally.
- `cover_size: str = "M"` — accepts `"S"`, `"M"`, `"L"`. Controls Open Library
  cover size variant.

### Behavior

When `download_cover=True`:

1. Check if `cover_url` is present on the resolved record.
2. Check local cache: `{cache_dir}/covers/{isbn13}_{size}.jpg`.
3. If not cached, download from
   `https://covers.openlibrary.org/b/isbn/{isbn13}-{size}.jpg`.
4. Store to `{cache_dir}/covers/{isbn13}_{size}.jpg`.
5. Add `cover_path` field to the returned record with the absolute local path.

When `download_cover=False` (default): no change to current behavior.

### Read-only mode

In read-only mode, `download_cover=True` returns
`{"error": "read_only_mode", "cover_url": "https://..."}` with the remote URL
instead of downloading. The tool itself stays visible.

### Error handling

Cover download is best-effort. If the download fails (404, timeout), log at
DEBUG, return the record without `cover_path`. The `cover_url` field still
points to the remote URL.

## 6. Chapter-Level Resolution (#64)

Integrated into `batch_resolve` and patent citation resolution — no new tool.

### BookChapterRecord

New TypedDict in `_record_types.py`:

```python
class BookChapterRecord(TypedDict, total=False):
    chapter_title: str
    chapter_number: int
    page_start: int
    page_end: int
    parent_book: BookRecord
    citation_source: str  # "crossref" | "parsed"
```

### Citation string parser

New file: `src/scholar_mcp/_chapter_parser.py`

Recognizes patterns in citation strings:
- `Chapter N` / `Ch. N` / `Chap. N`
- `pp. X-Y` / `p. X` / `pages X–Y`
- `In: {book title}` (incollection references)
- ISBN patterns (reuse from `_book_enrichment.py`)

Returns a `ChapterHint` dataclass: `chapter_number | None`,
`page_start | None`, `page_end | None`, `parent_title | None`, `isbn | None`.

### Integration points

**`batch_resolve`** (in `_tools_utility.py`):
- After S2 resolution, if a citation string matched chapter patterns and the
  resolved paper has `book_metadata`, attach `chapter_info: BookChapterRecord`
  to the result.
- If CrossRef enrichment (phase 0) returned `type: "book-chapter"` with page
  data, use that as the authoritative source over parsed hints.

**Patent NPL citations** (in `_tools_patent.py`):
- In `_fetch_citations()`, when processing NPL references, run the chapter
  parser on the raw citation string.
- If chapter/page info found and the citation resolves to a book, include
  `chapter_info` in the citation result alongside `book_ref`.

### CrossRef as primary source

When CrossRef enrichment has already run (pipeline phase 0) and returned
`type: "book-chapter"`, its structured data (`page`, `container-title`) takes
precedence over regex-parsed hints. The parser is the fallback for records
CrossRef didn't cover.

## New Files Summary

| File | Purpose |
|------|---------|
| `_enrichment.py` | `Enricher` protocol, `EnrichmentPipeline` class |
| `_crossref_client.py` | CrossRef API client |
| `_google_books_client.py` | Google Books API client |
| `_chapter_parser.py` | Citation string chapter/page pattern extraction |

## Modified Files Summary

| File | Changes |
|------|---------|
| `_record_types.py` | Add `BookChapterRecord`; add `worldcat_url`, `snippet`, `cover_path` to `BookRecord` |
| `_server_deps.py` | Add `CrossRefClient`, `GoogleBooksClient` to `ServiceBundle`; create `EnrichmentPipeline` with all enrichers; store as `bundle.enrichment` |
| `config.py` | Add `google_books_api_key: str \| None` |
| `_cache.py` / `_protocols.py` | Add `crossref` and `google_books` cache tables + protocol methods |
| `_openlibrary_client.py` | Populate `worldcat_url` in `normalize_book()` |
| `_book_enrichment.py` | Refactor into `OpenLibraryEnricher` class implementing `Enricher` protocol |
| `_tools_citation.py` | Refactor inline OpenAlex enrichment into `OpenAlexEnricher`; replace ad-hoc calls with `bundle.enrichment.enrich()` |
| `_tools_books.py` | Add `download_cover`/`cover_size` params to `get_book`; add `get_book_excerpt` tool; run enrichment pipeline on book results |
| `_tools_utility.py` | Chapter-aware `batch_resolve` — attach `chapter_info` when patterns match |
| `_tools_patent.py` | Chapter-aware NPL citation resolution |

## Enricher Registry at Startup

```
Phase 0: OpenAlexEnricher(tags={"papers"}), CrossRefEnricher(tags={"papers"})
Phase 1: OpenLibraryEnricher(tags={"papers"}), GoogleBooksEnricher(tags={"books"})
```

## New Config Env Vars

| Env var | Required | Purpose |
|---------|----------|---------|
| `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` | No | Higher Google Books rate limits |

No new required configuration. Everything degrades gracefully.

## Implementation Order

1. **#62** Enrichment pipeline — protocol, pipeline class, migrate OpenAlex + OpenLibrary enrichers
2. **#67** CrossRef — client, enricher, cache
3. **#61** Google Books — client, enricher, cache, `get_book_excerpt` tool
4. **#66** WorldCat — `worldcat_url` field in `normalize_book()`
5. **#68** Covers — `download_cover`/`cover_size` on `get_book`
6. **#64** Chapters — parser, integrate into `batch_resolve` + patent citations

Steps 4–6 are independent of each other and could be parallelized.

## What's NOT Changing

- No public MCP tool renames — existing tool names stay the same.
- No new required configuration — all new features are zero-config or optional.
- No breaking changes to existing tool output shapes — new fields are additive.

# Book Support Design Spec

**Date**: 2026-04-06
**Status**: Draft
**Scope**: Add book-aware enrichment and lookup to scholar-mcp via Open Library

## Overview

Semantic Scholar indexes some books and book chapters, but coverage is patchy —
often missing abstracts, DOIs, ISBNs, or publisher info. Books surface
frequently as citation graph nodes that cannot be meaningfully resolved. This
feature adds book-aware enrichment and standalone book lookup using Open Library
as the data source.

### Design Decisions

- **Approach 1 (Flat Module Addition)**: New modules follow established
  patterns (`_openlibrary_client.py`, `_tools_books.py`, `_book_enrichment.py`)
  rather than introducing an enrichment plugin architecture. A future issue
  covers refactoring all enrichers (OpenAlex, Open Library, etc.) into a
  registry/pipeline pattern.
- **Open Library only**: Google Books is deferred to a separate issue. The
  `google_books_url` field is reserved in the book record shape (always `None`).
- **Dict-based records**: Book metadata uses plain `dict[str, Any]`, consistent
  with papers and patents. A separate issue covers migrating all record types to
  dataclasses.
- **Server-side enrichment on strong signals only**: Auto-enrichment triggers on
  S2 `publicationTypes` containing "Book"/"BookChapter" or `externalIds.ISBN`
  being present. No fuzzy title heuristics — the LLM client can call
  `search_books` / `get_book` directly when it has its own context suggesting
  something is a book.
- **Always available**: Open Library requires no API key, so book tools are
  always registered (no tag-based hiding like patents).

## Open Library Client (`_openlibrary_client.py`)

Thin async wrapper around Open Library's REST API using httpx.

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search.json?q={query}&limit={n}` | GET | Text search |
| `/search.json?isbn={isbn}` | GET | ISBN search |
| `/isbn/{isbn}.json` | GET | Edition by ISBN (redirects) |
| `/works/{id}.json` | GET | Work-level metadata |
| `/authors/{id}.json` | GET | Author name resolution |

### Rate Limiting

Open Library asks for ~100 req/min politeness. A dedicated `RateLimiter`
instance with ~0.6s delay enforces this, following the existing rate limiter
pattern in `_rate_limiter.py`.

### Client Interface

```python
class OpenLibraryClient:
    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None: ...
    async def search(self, query: str, *, limit: int = 10) -> list[dict]: ...
    async def get_by_isbn(self, isbn: str) -> dict | None: ...
    async def get_work(self, work_id: str) -> dict | None: ...
    async def close(self) -> None: ...
```

Return values are raw Open Library JSON dicts. Normalization to the book record
shape is handled by callers (tools, enrichment function).

### ServiceBundle Integration

Add `openlibrary: OpenLibraryClient` to `ServiceBundle`. Created in the
lifespan factory, closed on shutdown. Unlike `docling` and `epo`, this field is
not optional — Open Library is always available.

## Cache Layer

New tables in `_cache.py` following existing patterns (SQLite, TTL-based expiry).

### Tables

| Table | Key | TTL | Content |
|-------|-----|-----|---------|
| `books_isbn` | ISBN-13 (normalized) | 30 days | Book metadata dict as JSON |
| `books_openlibrary` | OL work ID (e.g. `OL123W`) | 30 days | Book metadata dict as JSON |
| `books_search` | Query string hash | 7 days | Search result list as JSON |

### Cache Methods

Added to `ScholarCache`:

- `get_book_by_isbn(isbn: str) -> dict | None`
- `set_book_by_isbn(isbn: str, data: dict) -> None`
- `get_book_by_work(work_id: str) -> dict | None`
- `set_book_by_work(work_id: str, data: dict) -> None`
- `get_book_search(query: str) -> list[dict] | None`
- `set_book_search(query: str, data: list[dict]) -> None`

### ISBN Normalization

All ISBNs are stored as ISBN-13. If a 10-digit ISBN is provided, it is converted
to ISBN-13 before cache lookup or storage. Conversion uses the standard
check-digit algorithm — no external library required.

## Book Record Shape

Plain dict with the following keys:

```python
{
    "title": str,
    "authors": list[str],
    "publisher": str | None,
    "year": int | None,
    "edition": str | None,              # e.g. "3rd edition"
    "isbn_10": str | None,
    "isbn_13": str | None,
    "openlibrary_work_id": str | None,
    "openlibrary_edition_id": str | None,
    "cover_url": str | None,            # Open Library cover image URL
    "google_books_url": None,            # reserved, always None for now
    "subjects": list[str],
    "page_count": int | None,
    "description": str | None,           # short blurb if available
}
```

### Normalization

A `_normalize_book(ol_response: dict) -> dict` function maps Open Library's JSON
shape into this standardized dict. Lives in `_openlibrary_client.py` alongside
the client class.

### Cover URL Construction

Open Library covers follow a predictable URL pattern:
`https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg`. Constructed from the ISBN
without an extra API call.

## Tool Specifications (`_tools_books.py`)

Registered via `register_book_tools(mcp)`, called from `_server_tools.py`.

### `search_books`

Search for books by title, author, ISBN, or free text.

**Inputs:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | yes | — | Title, author, ISBN, or free text |
| `limit` | int | no | 10 | Max results (max 50) |

**Behavior:**

1. Check `books_search` cache for query
2. On miss, call `openlibrary.search(query, limit=limit)`
3. Normalize results to book record dicts
4. Cache search results
5. Return JSON list of book records

**Rate limit handling:** Try-once pattern. On `RateLimitedError`, queue for
background execution and return `{"queued": true, "task_id": "...", "tool": "search_books"}`.

**MCP Annotations:** `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

### `get_book`

Resolve a single book by ISBN or Open Library ID.

**Inputs:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `identifier` | string | yes | — | ISBN-10, ISBN-13, or OL work/edition ID |
| `include_editions` | bool | no | false | List all available editions |

**Behavior:**

1. Detect identifier type (ISBN vs OL ID by format)
2. Check cache by ISBN or work ID
3. On miss, call appropriate client method
4. If `include_editions` is true, fetch the work and list editions
5. Cache result
6. Return JSON book record (with `editions` list if requested)

**Rate limit handling:** Try-once pattern, same as `search_books`.

**MCP Annotations:** `readOnlyHint=True, destructiveHint=False, openWorldHint=True`

## Book Enrichment (`_book_enrichment.py`)

Centralized function that enriches paper dicts with book metadata in-place.

### Main Function

```python
async def enrich_books(
    papers: list[dict[str, Any]],
    bundle: ServiceBundle,
    *,
    concurrency: int = 5,
) -> None:
```

### Trigger Conditions

Per paper, enrichment is attempted when either:

1. `publicationTypes` contains `"Book"` or `"BookChapter"`
2. `externalIds` contains an `ISBN` key

If neither condition is met, the paper is skipped. There are no fuzzy heuristics
— the LLM client can use `search_books` / `get_book` when it has its own signal.

### Lookup Strategy

- If ISBN present: cache lookup (`get_book_by_isbn`), then
  `openlibrary.get_by_isbn(isbn)` on miss
- If no ISBN but condition 1 matched (publicationTypes only): skip enrichment.
  This is intentional — title-based search is too unreliable for automatic
  enrichment. The LLM can call `search_books` directly when it has context.

### Mutation

Adds a `book_metadata` key to the paper dict:

```python
paper["book_metadata"] = {
    "publisher": str | None,
    "edition": str | None,
    "isbn_13": str | None,
    "cover_url": str | None,
    "openlibrary_work_id": str | None,
    "description": str | None,
    "subjects": list[str],
    "page_count": int | None,
}
```

### Error Handling

Per-paper `try`/`except`: failures are logged at `DEBUG` level, paper is
returned unchanged. Enrichment failures never break the containing tool.

### Throttling

`asyncio.Semaphore(concurrency)` limits parallel Open Library calls. Default of
5 is conservative for their ~100 req/min guideline. In `get_citation_graph`,
which already has its own batch throttling, the semaphore provides an additional
bound.

### Integration Points

Called before `return` in:

- `get_paper` — single paper (list of one)
- `get_references` — list of referenced papers
- `get_citations` — list of citing papers
- `get_citation_graph` — full graph result list

## Testing

### Test ISBNs

- `9781119643012` — Anderson, *Security Engineering* 3rd ed.
- `9780735611313` — Howard & LeBlanc, *Writing Secure Code* 2nd ed.
- `9780201633610` — Gamma et al., *Design Patterns*

### Test Strategy

- Mock Open Library API responses with `respx`
- Test `_openlibrary_client.py` methods with mocked HTTP
- Test `search_books` and `get_book` tools via `Client(mcp)` pattern
- Test enrichment: paper with ISBN triggers lookup; paper without ISBN/type is
  skipped; API failure leaves paper unchanged
- Test cache: second call for same ISBN returns cached result
- Test ISBN-10 to ISBN-13 conversion
- Test try-once-then-queue on rate limit (429 response)
- Test enrichment integration in `get_paper` and `get_references` with a paper
  that has `publicationTypes: ["Book"]`

## Deferred Issues

Each of the following is out of scope for this implementation and becomes a
separate GitHub issue.

### 1. Google Books Integration

Add Google Books as a secondary data source for preview links, snippet text, and
book excerpt retrieval. The `google_books_url` field is already reserved in the
book record shape.

### 2. Enrichment Plugin Architecture

Refactor OpenAlex and Open Library enrichment into a registry/pipeline pattern.
Register enrichers that run as a configurable pipeline on paper results. Cleaner
extension point for future enrichment sources.

### 3. Dataclass Migration

Migrate papers, patents, and books from `dict[str, Any]` to typed dataclasses
(or TypedDicts) across the codebase. Unified refactor rather than piecemeal
adoption.

### 4. Chapter-Level Resolution (F1)

Parse citation strings for "Chapter N" or "pp. X-Y" patterns, match against
table of contents data. Would need a `BookChapterRecord` linking back to the
parent book.

### 5. BibLaTeX `@book` / `@incollection` Output (F2)

Ensure `generate_citations` produces correct `@book` entries (not `@article`)
when book metadata is present. Add `@incollection` for chapter-level citations.
Fields: `publisher`, `edition`, `isbn`, `address`, `editor`.

### 6. WorldCat Library Availability (F3)

Given an ISBN, check WorldCat for library holdings. Requires an OCLC API key
(free for non-commercial use). Return nearest libraries with holdings and
WorldCat permalink.

### 7. CrossRef Enrichment for Book Chapters (F4)

Use CrossRef to fill gaps where S2 has a sparse book-chapter record. Query
`api.crossref.org/works` filtered by `type:book-chapter`. Free, no key.

### 8. Cover Image Caching (F5)

Cache Open Library cover images locally via the file exchange mechanism for batch
operations or offline use.

### 9. Book Recommendation via Subjects (F6)

`recommend_books` tool using Open Library subject API
(`/subjects/{subject}.json`). Analogous to `recommend_papers`.

### 10. Patent-to-Book Cross-Referencing (F7)

Parse patent citation strings to extract book references, resolve via Open
Library. Connects patent and book enrichment features.

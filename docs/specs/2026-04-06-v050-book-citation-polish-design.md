# v0.5.0 Design: Book & Citation Polish

**Milestone**: [v0.5.0](https://github.com/pvliesdonk/scholar-mcp/milestone/5)
**Date**: 2026-04-06
**Issues**: #63, #55, #65, #69, #74

## Overview

Five issues focused on type safety and book/citation feature polish.
Implementation order: typing foundations first (#63, #55), then features
(#74, #69, #65).

## Decision Log

| Question | Decision | Rationale |
|----------|----------|-----------|
| TypedDict scope | BookRecord only; follow-up issue for Paper/Patent | BookRecord is newest and self-contained; Paper shape is upstream-controlled |
| CacheProtocol scope | Single CacheProtocol covering all methods | One class, one protocol; simpler to maintain |
| @incollection support | Deferred to milestone containing #64 | Depends on chapter-level resolution not in this milestone |
| ISBN author enrichment | Always-on, not opt-in | Empty authors is a bug; one extra request per uncached ISBN is acceptable |
| Implementation order | Typing first → features | Typed foundation makes feature code cleaner from the start |

---

## 1. BookRecord TypedDict (#63)

**New file**: `src/scholar_mcp/_record_types.py`

```python
from typing import TypedDict

class BookRecord(TypedDict, total=False):
    title: str
    authors: list[str]
    publisher: str | None
    year: int | None
    edition: str | None
    isbn_10: str | None
    isbn_13: str | None
    openlibrary_work_id: str | None
    openlibrary_edition_id: str | None
    cover_url: str | None
    google_books_url: str | None
    subjects: list[str]
    page_count: int | None
    description: str | None
```

Uses `total=False` because records are JSON-serialized and all fields may
be absent in edge cases (cache deserialization, partial API responses).

### Files changed

- **New**: `_record_types.py` — BookRecord definition
- `_openlibrary_client.py` — `normalize_book()` return type → `BookRecord`
- `_tools_books.py` — internal functions use `BookRecord`
- `_book_enrichment.py` — `_to_enrichment_dict()` returns BookRecord-shaped dict
- `_cache.py` — book cache methods use `BookRecord` in signatures

### Follow-up

Create issue for PaperRecord + PatentRecord TypedDicts in a future milestone.

---

## 2. CacheProtocol (#55)

**New file**: `src/scholar_mcp/_protocols.py`

A single `CacheProtocol` covering all cache methods (papers, patents, books).
Book methods use `BookRecord`; paper/patent methods remain `dict[str, Any]`
until PaperRecord/PatentRecord are defined.

### Files changed

- **New**: `_protocols.py` — CacheProtocol definition
- `_server_deps.py` — `ServiceBundle.cache` type: `ScholarCache` → `CacheProtocol`
- `_tools_patent.py` — `_fetch_patent_sections` cache param: `Any` → `CacheProtocol`
- Import `ScholarCache` only in `_server_deps.py` where the concrete instance
  is created

### Protocol surface

| Group | Methods |
|-------|---------|
| Paper | `get_paper`, `set_paper`, `get_citations`, `set_citations`, `get_references`, `set_references`, `get_author`, `set_author`, `get_openalex`, `set_openalex`, `get_alias`, `set_alias` |
| Patent | `get_patent`, `set_patent`, `get_patent_claims`, `set_patent_claims`, `get_patent_description`, `set_patent_description`, `get_patent_family`, `set_patent_family`, `get_patent_legal`, `set_patent_legal`, `get_patent_citations`, `set_patent_citations`, `get_patent_search`, `set_patent_search` |
| Book | `get_book_by_isbn`, `set_book_by_isbn`, `get_book_by_work`, `set_book_by_work`, `get_book_search`, `set_book_search` |

Note: `get_book_subject` / `set_book_subject` are added to both
`ScholarCache` and `CacheProtocol` when implementing #69 (section 4).
| Utility | `open`, `close`, `stats`, `clear` |

---

## 3. ISBN Author Enrichment (#74)

Edition records from Open Library lack author names. When resolving by ISBN
or edition ID, fetch the work record and resolve author references.

### New: `OpenLibraryClient.get_author()`

```python
async def get_author(self, author_key: str) -> dict[str, Any] | None:
    """Fetch author by key (e.g. /authors/OL123A)."""
```

### New helper: `_enrich_authors_from_work()`

In `_tools_books.py`:

```python
async def _enrich_authors_from_work(
    book: BookRecord, bundle: ServiceBundle
) -> None:
```

1. Skip if `book["authors"]` is non-empty
2. Get `openlibrary_work_id` from book; skip if absent
3. Fetch work record → extract author keys from `work["authors"]`
4. For each author key, fetch `/authors/{key}.json` → extract `name`
5. Set `book["authors"]` to the resolved name list

### Call sites

- `_resolve_isbn()` — after `normalize_book()`, before caching
- `_resolve_edition()` — after `normalize_book()`, before caching
- `_resolve_work()` — already has the work dict in hand, so resolve author
  keys directly (extract author keys from the work, fetch each via
  `get_author()`, set names on the book dict) rather than calling
  `_enrich_authors_from_work()` which would re-fetch the work. Factor out
  a shared `_resolve_author_keys(author_keys, bundle) -> list[str]` helper
  used by both paths.

### Caching

Author names are persisted in the cached BookRecord, so the extra HTTP
requests only happen on the first lookup per ISBN/work.

---

## 4. recommend_books Tool (#69)

### New: `OpenLibraryClient.get_subject()`

```python
async def get_subject(
    self, subject: str, *, limit: int = 10
) -> dict[str, Any] | None:
    """Fetch books for a subject from /subjects/{subject}.json."""
```

### New cache methods

```python
async def get_book_subject(self, subject: str) -> list[BookRecord] | None: ...
async def set_book_subject(self, subject: str, data: list[BookRecord]) -> None: ...
```

TTL: 7 days. Key: SHA-256 hash of normalized subject slug.

### New tool in `_tools_books.py`

```python
@mcp.tool(...)
async def recommend_books(
    subject: str,
    limit: int = 10,
    bundle: ServiceBundle = Depends(get_bundle),
) -> str:
```

### Subject normalization

`"Machine Learning"` → `"machine_learning"` (lowercase, spaces to underscores).
Open Library is case-insensitive but we normalize for consistent cache keys.

### Subject API response → BookRecord normalization

Subject works have `title`, `authors` (list of `{"name": "..."}` dicts),
`cover_id`, `key` (work key), `edition_count`. Normalized to BookRecord shape.
ISBN and edition-level fields are `None` (not available from subject results).
Sorted by `edition_count` descending (popularity proxy).

### CacheProtocol update

Add `get_book_subject` / `set_book_subject` to the protocol.

---

## 5. BibLaTeX @book Output (#65)

### Entry type inference

In `infer_entry_type()`, add book detection before existing logic:

```python
book_meta = paper.get("book_metadata")
if book_meta and (book_meta.get("isbn_13") or book_meta.get("publisher")):
    return "book"
```

### BibTeX @book fields

When `entry_type == "book"`, emit from `book_metadata`:

| book_metadata field | BibTeX field |
|---------------------|-------------|
| `publisher` | `publisher` |
| `edition` | `edition` |
| `isbn_13` | `isbn` |

Skip `journal` for book entries (no venue expected).

### Author fallback

When paper's S2 `authors` list is empty but `book_metadata.authors` is
non-empty (plain strings, not `{"name": ...}` dicts), synthesize
`{"name": author_str}` entries for the formatter to consume. This is done
at format time, not by mutating the paper record.

### CSL-JSON

- Type mapping: `"book"` → `"book"`
- Emit `publisher` and `ISBN` fields from book_metadata

### RIS

- Type mapping: `"book"` → `"BOOK"`
- Emit `PB  -` (publisher) and `SN  -` (ISBN) tags

### @incollection

Deferred to the milestone containing #64 (chapter-level resolution).

---

## Testing Strategy

Each issue gets tests alongside its implementation:

| Issue | Test focus |
|-------|-----------|
| #63 BookRecord | Type checking via mypy; normalize_book return type assertions |
| #55 CacheProtocol | Verify ScholarCache satisfies protocol; mypy structural check |
| #74 Author enrichment | Mock OL work + author endpoints; verify authors populated; verify caching skips re-fetch |
| #69 recommend_books | Mock subject API; verify normalization, caching, sorting by edition_count |
| #65 @book output | `infer_entry_type` returns "book" for book_metadata papers; verify BibTeX/CSL-JSON/RIS output fields |

---

## Files Created / Modified Summary

### New files
- `src/scholar_mcp/_record_types.py`
- `src/scholar_mcp/_protocols.py`

### Modified files
- `src/scholar_mcp/_openlibrary_client.py` — BookRecord return type, get_author(), get_subject()
- `src/scholar_mcp/_tools_books.py` — BookRecord types, _enrich_authors_from_work(), recommend_books tool
- `src/scholar_mcp/_cache.py` — BookRecord in signatures, get/set_book_subject methods
- `src/scholar_mcp/_server_deps.py` — ServiceBundle.cache type → CacheProtocol
- `src/scholar_mcp/_tools_patent.py` — cache param type → CacheProtocol
- `src/scholar_mcp/_citation_formatter.py` — @book entry type, book-specific fields in all three formatters
- `src/scholar_mcp/_book_enrichment.py` — BookRecord type usage
- `src/scholar_mcp/_server_tools.py` — no changes needed (book tools already registered)
- Test files for each feature

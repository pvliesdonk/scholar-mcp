# v0.5.0 Book & Citation Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Type-safe book records, cache protocol, author enrichment for ISBN lookups, a recommend_books tool, and @book BibTeX/CSL-JSON/RIS output.

**Architecture:** Four stacked PRs, each building on the last. PR 1 adds BookRecord TypedDict + CacheProtocol typing (#63, #55). PR 2 adds ISBN author enrichment (#74). PR 3 adds recommend_books tool (#69). PR 4 adds @book citation output (#65). Each PR is independently reviewable and merge-ready when its ancestors are merged.

**Tech Stack:** Python 3.11+, TypedDict, typing.Protocol, FastMCP, httpx, aiosqlite, pytest + respx

**Spec:** `docs/specs/2026-04-06-v050-book-citation-polish-design.md`

---

## PR Structure (Stacked)

```
main
 └── feat/book-record-typeddict  (PR 1: #63 + #55)
      └── feat/isbn-author-enrichment  (PR 2: #74)
           └── feat/recommend-books  (PR 3: #69)
                └── feat/book-citation-output  (PR 4: #65)
```

---

## PR 1: BookRecord TypedDict + CacheProtocol (#63, #55)

**Branch:** `feat/book-record-typeddict` from `main`

### Task 1.1: Define BookRecord TypedDict

**Files:**
- Create: `src/scholar_mcp/_record_types.py`
- Test: `tests/test_record_types.py`

- [ ] **Step 1: Create the BookRecord TypedDict**

```python
# src/scholar_mcp/_record_types.py
"""Typed record definitions for Scholar MCP."""

from __future__ import annotations

from typing import TypedDict


class BookRecord(TypedDict, total=False):
    """Typed representation of a normalized book record.

    All fields use ``total=False`` because records are JSON-serialized
    and may have absent fields from cache deserialization or partial
    API responses.
    """

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

- [ ] **Step 2: Write a type-checking test**

```python
# tests/test_record_types.py
"""Tests for typed record definitions."""

from __future__ import annotations

from scholar_mcp._record_types import BookRecord


def test_book_record_accepts_valid_data() -> None:
    book: BookRecord = {
        "title": "Design Patterns",
        "authors": ["Erich Gamma"],
        "publisher": "Addison-Wesley",
        "year": 1994,
        "edition": None,
        "isbn_10": "0201633612",
        "isbn_13": "9780201633610",
        "openlibrary_work_id": "OL1168083W",
        "openlibrary_edition_id": "OL1429049M",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9780201633610-M.jpg",
        "google_books_url": None,
        "subjects": ["Software patterns"],
        "page_count": 395,
        "description": None,
    }
    assert book["title"] == "Design Patterns"
    assert book["authors"] == ["Erich Gamma"]


def test_book_record_allows_partial() -> None:
    book: BookRecord = {"title": "Minimal Book"}
    assert book["title"] == "Minimal Book"
```

- [ ] **Step 3: Run test**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_record_types.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/scholar_mcp/_record_types.py tests/test_record_types.py
git commit -m "feat(types): add BookRecord TypedDict (#63)"
```

### Task 1.2: Update normalize_book to return BookRecord

**Files:**
- Modify: `src/scholar_mcp/_openlibrary_client.py:120-197`

- [ ] **Step 1: Update normalize_book return type**

In `_openlibrary_client.py`, add import and change the return type:

```python
# Add import at top (after existing imports)
from ._record_types import BookRecord
```

Change the function signature on line 120:

```python
def normalize_book(
    data: dict[str, Any], *, source: Literal["search", "edition"] = "search"
) -> BookRecord:
```

No other code changes needed — the return dicts already match the BookRecord shape.

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py tests/test_tools_books.py -v`
Expected: PASS

- [ ] **Step 3: Run mypy on the changed file**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m mypy src/scholar_mcp/_openlibrary_client.py --ignore-missing-imports`
Expected: PASS (or only pre-existing issues)

- [ ] **Step 4: Commit**

```bash
git add src/scholar_mcp/_openlibrary_client.py
git commit -m "refactor(types): normalize_book returns BookRecord (#63)"
```

### Task 1.3: Update _tools_books.py to use BookRecord

**Files:**
- Modify: `src/scholar_mcp/_tools_books.py:119-204`

- [ ] **Step 1: Update internal function signatures**

Add import at top of `_tools_books.py`:

```python
from ._record_types import BookRecord
```

Update `_resolve_isbn` (line 119):

```python
async def _resolve_isbn(isbn: str, bundle: ServiceBundle) -> str:
    cached = await bundle.cache.get_book_by_isbn(isbn)
    if cached is not None:
        return json.dumps(cached)

    edition = await bundle.openlibrary.get_by_isbn(isbn)
    if edition is None:
        return json.dumps({"error": "not_found", "identifier": isbn})

    book: BookRecord = normalize_book(edition, source="edition")
    await bundle.cache.set_book_by_isbn(isbn, book)
    if book.get("openlibrary_work_id"):
        await bundle.cache.set_book_by_work(book["openlibrary_work_id"], book)
    return json.dumps(book)
```

Update `_resolve_work` (line 144) — add `BookRecord` annotation to the `book` variable:

```python
    book: BookRecord = {
        "title": work.get("title", ""),
        "authors": [],
        ...
    }
```

- [ ] **Step 2: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/scholar_mcp/_tools_books.py
git commit -m "refactor(types): use BookRecord in book tools (#63)"
```

### Task 1.4: Update _book_enrichment.py to use BookRecord

**Files:**
- Modify: `src/scholar_mcp/_book_enrichment.py:83-101`

- [ ] **Step 1: Update _to_enrichment_dict signature**

Add import at top of `_book_enrichment.py`:

```python
from ._record_types import BookRecord
```

Update `_to_enrichment_dict` (line 83):

```python
def _to_enrichment_dict(book: BookRecord) -> dict[str, Any]:
```

Update `_enrich_one` (line 67) — annotate the `book` variable:

```python
        book: BookRecord = normalize_book(edition, source="edition")
```

- [ ] **Step 2: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_book_enrichment.py tests/test_book_enrichment_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/scholar_mcp/_book_enrichment.py
git commit -m "refactor(types): use BookRecord in book enrichment (#63)"
```

### Task 1.5: Update cache book methods to use BookRecord

**Files:**
- Modify: `src/scholar_mcp/_cache.py:734-832`

- [ ] **Step 1: Update cache method signatures**

Add import at top of `_cache.py`:

```python
from ._record_types import BookRecord
```

Update these method signatures in `ScholarCache`:

```python
    async def get_book_by_isbn(self, isbn: str) -> BookRecord | None:
    async def set_book_by_isbn(self, isbn: str, data: BookRecord) -> None:
    async def get_book_by_work(self, work_id: str) -> BookRecord | None:
    async def set_book_by_work(self, work_id: str, data: BookRecord) -> None:
    async def get_book_search(self, query: str) -> list[BookRecord] | None:
    async def set_book_search(self, query: str, data: list[BookRecord]) -> None:
```

The method bodies remain unchanged — `json.loads()` returns `Any` and the type annotation on the return guides consumers.

- [ ] **Step 2: Run full test suite to verify no breakage**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_cache_books.py tests/test_cache.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/scholar_mcp/_cache.py
git commit -m "refactor(types): BookRecord in cache method signatures (#63)"
```

### Task 1.6: Define CacheProtocol

**Files:**
- Create: `src/scholar_mcp/_protocols.py`
- Test: `tests/test_protocols.py`

- [ ] **Step 1: Write failing test — verify ScholarCache satisfies the protocol**

```python
# tests/test_protocols.py
"""Tests for protocol conformance."""

from __future__ import annotations

from scholar_mcp._cache import ScholarCache
from scholar_mcp._protocols import CacheProtocol


def test_scholar_cache_satisfies_cache_protocol() -> None:
    """ScholarCache must structurally satisfy CacheProtocol."""
    cache_instance: CacheProtocol = ScholarCache.__new__(ScholarCache)
    assert isinstance(cache_instance, object)  # structural check
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_protocols.py -v`
Expected: FAIL (ImportError: _protocols does not exist yet)

- [ ] **Step 3: Create CacheProtocol**

```python
# src/scholar_mcp/_protocols.py
"""Typing protocols for Scholar MCP services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ._record_types import BookRecord


@runtime_checkable
class CacheProtocol(Protocol):
    """Structural type for the scholar cache.

    Covers paper, patent, and book cache methods. Using a protocol
    allows ``mypy`` to catch missing or misnamed methods at type-check
    time rather than at runtime.
    """

    # Paper methods
    async def get_paper(self, paper_id: str) -> dict[str, Any] | None: ...
    async def set_paper(self, paper_id: str, data: dict[str, Any]) -> None: ...
    async def get_citations(self, paper_id: str) -> list[str] | None: ...
    async def set_citations(self, paper_id: str, ids: list[str]) -> None: ...
    async def get_references(self, paper_id: str) -> list[str] | None: ...
    async def set_references(self, paper_id: str, ids: list[str]) -> None: ...
    async def get_author(self, author_id: str) -> dict[str, Any] | None: ...
    async def set_author(self, author_id: str, data: dict[str, Any]) -> None: ...
    async def get_openalex(self, doi: str) -> dict[str, Any] | None: ...
    async def set_openalex(self, doi: str, data: dict[str, Any]) -> None: ...
    async def get_alias(self, raw_id: str) -> str | None: ...
    async def set_alias(self, raw_id: str, s2_paper_id: str) -> None: ...

    # Patent methods
    async def get_patent(self, patent_id: str) -> dict[str, Any] | None: ...
    async def set_patent(self, patent_id: str, data: dict[str, Any]) -> None: ...
    async def get_patent_claims(self, patent_id: str) -> str | None: ...
    async def set_patent_claims(self, patent_id: str, text: str) -> None: ...
    async def get_patent_description(self, patent_id: str) -> str | None: ...
    async def set_patent_description(self, patent_id: str, text: str) -> None: ...
    async def get_patent_family(
        self, patent_id: str
    ) -> list[dict[str, Any]] | None: ...
    async def set_patent_family(
        self, patent_id: str, data: list[dict[str, Any]]
    ) -> None: ...
    async def get_patent_legal(
        self, patent_id: str
    ) -> list[dict[str, Any]] | None: ...
    async def set_patent_legal(
        self, patent_id: str, data: list[dict[str, Any]]
    ) -> None: ...
    async def get_patent_citations(
        self, patent_id: str
    ) -> dict[str, Any] | None: ...
    async def set_patent_citations(
        self, patent_id: str, data: dict[str, Any]
    ) -> None: ...
    async def get_patent_search(self, query: str) -> dict[str, Any] | None: ...
    async def set_patent_search(
        self, query: str, data: dict[str, Any]
    ) -> None: ...

    # Book methods
    async def get_book_by_isbn(self, isbn: str) -> BookRecord | None: ...
    async def set_book_by_isbn(self, isbn: str, data: BookRecord) -> None: ...
    async def get_book_by_work(self, work_id: str) -> BookRecord | None: ...
    async def set_book_by_work(
        self, work_id: str, data: BookRecord
    ) -> None: ...
    async def get_book_search(
        self, query: str
    ) -> list[BookRecord] | None: ...
    async def set_book_search(
        self, query: str, data: list[BookRecord]
    ) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_protocols.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_protocols.py tests/test_protocols.py
git commit -m "feat(types): add CacheProtocol (#55)"
```

### Task 1.7: Wire CacheProtocol into ServiceBundle and patent tools

**Files:**
- Modify: `src/scholar_mcp/_server_deps.py:51`
- Modify: `src/scholar_mcp/_tools_patent.py:376-382`

- [ ] **Step 1: Update ServiceBundle.cache type**

In `_server_deps.py`, add import:

```python
from ._protocols import CacheProtocol
```

Change the `cache` field on `ServiceBundle` (line 51):

```python
    cache: CacheProtocol
```

Keep the `ScholarCache` import — it's still needed in `make_service_lifespan` to construct the instance (line 118).

- [ ] **Step 2: Update _fetch_patent_sections cache parameter**

In `_tools_patent.py`, add import:

```python
from ._protocols import CacheProtocol
```

Change the `cache` parameter on `_fetch_patent_sections` (line 381):

```python
    cache: CacheProtocol,
```

Also update the `s2` parameter type from `Any` to `S2Client | None` while here (it's already imported):

```python
    s2: S2Client | None = None,
```

- [ ] **Step 3: Run full test suite**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 4: Run ruff**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m ruff check src/scholar_mcp/ && python -m ruff format --check src/scholar_mcp/`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_server_deps.py src/scholar_mcp/_tools_patent.py
git commit -m "refactor(types): wire CacheProtocol into ServiceBundle and patent tools (#55)"
```

### Task 1.8: Create follow-up issue for PaperRecord + PatentRecord

- [ ] **Step 1: Create GitHub issue**

```bash
gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "refactor: add PaperRecord and PatentRecord TypedDicts" \
  --body "## Context

Follow-up from #63 which introduced BookRecord TypedDict.

## Proposed work

- Define \`PaperRecord\` TypedDict for S2 paper dicts. Use \`total=False\` since the shape is partially controlled by the upstream S2 API and many fields are optional.
- Define \`PatentRecord\` TypedDict for EPO patent dicts.
- Update \`CacheProtocol\` paper/patent methods to use the typed records instead of \`dict[str, Any]\`.
- Update tool functions and client code to use the typed records.

## Notes

- PaperRecord should align with \`FIELD_SETS\` in \`_s2_client.py\`
- PatentRecord should align with the dict returned by \`parse_biblio_xml()\` in \`_epo_xml.py\`
- Consider keeping \`total=False\` for both since API responses may have missing fields"
```

- [ ] **Step 2: Note the issue number for the milestone assignment**

### Task 1.9: Open PR 1

- [ ] **Step 1: Push branch and create PR**

```bash
git push -u origin feat/book-record-typeddict
gh pr create \
  --title "refactor: BookRecord TypedDict + CacheProtocol typing (#63, #55)" \
  --body "## Summary
- Adds \`BookRecord\` TypedDict for type-safe book record handling
- Adds \`CacheProtocol\` typing protocol covering all cache methods
- Updates \`ServiceBundle.cache\` type from \`ScholarCache\` to \`CacheProtocol\`
- Updates \`_fetch_patent_sections\` cache param from \`Any\` to \`CacheProtocol\`
- Creates follow-up issue for PaperRecord + PatentRecord

Closes #63, closes #55

## Test plan
- [ ] \`pytest\` passes
- [ ] \`mypy\` type checks pass on changed files
- [ ] \`ruff\` lint + format pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)" \
  --milestone "v0.5.0"
```

---

## PR 2: ISBN Author Enrichment (#74)

**Branch:** `feat/isbn-author-enrichment` from `feat/book-record-typeddict`

### Task 2.1: Add get_author() to OpenLibraryClient

**Files:**
- Modify: `src/scholar_mcp/_openlibrary_client.py`
- Test: `tests/test_openlibrary_client.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_openlibrary_client.py`:

```python
@pytest.mark.respx(base_url=OL_BASE)
async def test_get_author(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/authors/OL34184A.json").mock(
        return_value=httpx.Response(
            200,
            json={"name": "Erich Gamma", "key": "/authors/OL34184A"},
        )
    )
    client = OpenLibraryClient(
        httpx.AsyncClient(base_url=OL_BASE),
        RateLimiter(delay=0.0),
    )
    try:
        result = await client.get_author("/authors/OL34184A")
        assert result is not None
        assert result["name"] == "Erich Gamma"
    finally:
        await client.aclose()


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_author_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/authors/OL0000000A.json").mock(
        return_value=httpx.Response(404)
    )
    client = OpenLibraryClient(
        httpx.AsyncClient(base_url=OL_BASE),
        RateLimiter(delay=0.0),
    )
    try:
        result = await client.get_author("/authors/OL0000000A")
        assert result is None
    finally:
        await client.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py::test_get_author -v`
Expected: FAIL (AttributeError: get_author not defined)

- [ ] **Step 3: Implement get_author**

Add to `OpenLibraryClient` in `_openlibrary_client.py` (after `get_edition`):

```python
    async def get_author(self, author_key: str) -> dict[str, Any] | None:
        """Fetch author metadata by key.

        Args:
            author_key: Open Library author key (e.g. ``/authors/OL34184A``).

        Returns:
            Author dict with ``name`` field, or None if not found.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(f"{author_key}.json")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_author_error key=%s", author_key)
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py::test_get_author tests/test_openlibrary_client.py::test_get_author_not_found -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_openlibrary_client.py tests/test_openlibrary_client.py
git commit -m "feat: add OpenLibraryClient.get_author() (#74)"
```

### Task 2.2: Add _resolve_author_keys helper and update _resolve_isbn

**Files:**
- Modify: `src/scholar_mcp/_tools_books.py`
- Test: `tests/test_tools_books.py`

- [ ] **Step 1: Write failing test for author enrichment via ISBN**

Add to `tests/test_tools_books.py`:

```python
SAMPLE_WORK_WITH_AUTHORS = {
    "title": "Design Patterns",
    "key": "/works/OL1168083W",
    "authors": [
        {"author": {"key": "/authors/OL34184A"}, "type": {"key": "/type/author_role"}},
        {"author": {"key": "/authors/OL236174A"}, "type": {"key": "/type/author_role"}},
    ],
}

SAMPLE_AUTHOR_GAMMA = {"name": "Erich Gamma", "key": "/authors/OL34184A"}
SAMPLE_AUTHOR_HELM = {"name": "Richard Helm", "key": "/authors/OL236174A"}


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_isbn_enriches_authors(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book by ISBN should resolve authors from the work record."""
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_WITH_AUTHORS)
    )
    respx_mock.get("/authors/OL34184A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL236174A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py::test_get_book_isbn_enriches_authors -v`
Expected: FAIL (authors is `[]`)

- [ ] **Step 3: Implement _resolve_author_keys and update _resolve_isbn**

In `_tools_books.py`, add the helper after imports:

```python
async def _resolve_author_keys(
    author_keys: list[str], bundle: ServiceBundle
) -> list[str]:
    """Resolve Open Library author keys to author names.

    Args:
        author_keys: List of OL author keys (e.g. ``/authors/OL34184A``).
        bundle: Service bundle with openlibrary client.

    Returns:
        List of author name strings.
    """
    names: list[str] = []
    for key in author_keys:
        author_data = await bundle.openlibrary.get_author(key)
        if author_data and author_data.get("name"):
            names.append(author_data["name"])
    return names


def _extract_author_keys(work: dict[str, Any]) -> list[str]:
    """Extract author keys from a work record.

    Args:
        work: Open Library work dict.

    Returns:
        List of author key strings (e.g. ``/authors/OL34184A``).
    """
    keys: list[str] = []
    for entry in work.get("authors") or []:
        if isinstance(entry, dict):
            author = entry.get("author")
            if isinstance(author, dict) and author.get("key"):
                keys.append(author["key"])
    return keys


async def _enrich_authors_from_work(
    book: BookRecord, bundle: ServiceBundle
) -> None:
    """Enrich book in-place with authors from its work record.

    Best-effort: failures are logged and silently skipped (matching
    the ``_enrich_one`` pattern in ``_book_enrichment.py``).

    Args:
        book: Book record (mutated in-place).
        bundle: Service bundle with openlibrary client.
    """
    if book.get("authors"):
        return
    work_id = book.get("openlibrary_work_id")
    if not work_id:
        return
    try:
        work = await bundle.openlibrary.get_work(work_id)
        if work is None:
            return
        author_keys = _extract_author_keys(work)
        if author_keys:
            names = await _resolve_author_keys(author_keys, bundle)
            if names:
                book["authors"] = names
    except Exception:
        logger.debug(
            "author_enrichment_failed work_id=%s", work_id, exc_info=True
        )
```

Add `from typing import Any` import if not already present.

Update `_resolve_isbn` to call the enrichment:

```python
async def _resolve_isbn(isbn: str, bundle: ServiceBundle) -> str:
    cached = await bundle.cache.get_book_by_isbn(isbn)
    if cached is not None:
        return json.dumps(cached)

    edition = await bundle.openlibrary.get_by_isbn(isbn)
    if edition is None:
        return json.dumps({"error": "not_found", "identifier": isbn})

    book: BookRecord = normalize_book(edition, source="edition")
    await _enrich_authors_from_work(book, bundle)
    await bundle.cache.set_book_by_isbn(isbn, book)
    if book.get("openlibrary_work_id"):
        await bundle.cache.set_book_by_work(book["openlibrary_work_id"], book)
    return json.dumps(book)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py::test_get_book_isbn_enriches_authors -v`
Expected: PASS

- [ ] **Step 5: Update existing ISBN tests to mock work+author endpoints**

Existing tests like `test_get_book_isbn_cache_hit` and `test_get_book_by_isbn` only mock the `/isbn/` endpoint. After this change, `_resolve_isbn` also calls `_enrich_authors_from_work` which fetches the work. Since `_enrich_authors_from_work` catches all exceptions, existing tests won't break — but they should be updated to also mock the work+author endpoints for proper coverage. Add the work and author mocks to each existing ISBN test that uses `SAMPLE_EDITION_RESPONSE`:

```python
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_WITH_AUTHORS)
    )
    respx_mock.get("/authors/OL34184A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL236174A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
```

- [ ] **Step 6: Run all book tests to verify nothing is broken**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/scholar_mcp/_tools_books.py tests/test_tools_books.py
git commit -m "feat: enrich ISBN book results with authors from work (#74)"
```

### Task 2.3: Update _resolve_edition and _resolve_work for author enrichment

**Files:**
- Modify: `src/scholar_mcp/_tools_books.py`
- Test: `tests/test_tools_books.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tools_books.py`:

```python
@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_edition_enriches_authors(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book by edition ID should resolve authors from the work record."""
    respx_mock.get("/books/OL1429049M.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_WITH_AUTHORS)
    )
    respx_mock.get("/authors/OL34184A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL236174A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1429049M"})
    data = json.loads(result.content[0].text)
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_work_resolves_authors(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book by work ID should resolve author keys to names."""
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_WITH_AUTHORS)
    )
    respx_mock.get("/authors/OL34184A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL236174A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1168083W"})
    data = json.loads(result.content[0].text)
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py::test_get_book_edition_enriches_authors tests/test_tools_books.py::test_get_book_work_resolves_authors -v`
Expected: FAIL (authors is `[]`)

- [ ] **Step 3: Update _resolve_edition**

```python
async def _resolve_edition(edition_id: str, bundle: ServiceBundle) -> str:
    edition = await bundle.openlibrary.get_edition(edition_id)
    if edition is None:
        return json.dumps({"error": "not_found", "identifier": edition_id})

    book: BookRecord = normalize_book(edition, source="edition")
    await _enrich_authors_from_work(book, bundle)
    if book.get("isbn_13"):
        await bundle.cache.set_book_by_isbn(book["isbn_13"], book)
    if book.get("openlibrary_work_id"):
        await bundle.cache.set_book_by_work(book["openlibrary_work_id"], book)
    return json.dumps(book)
```

- [ ] **Step 4: Update _resolve_work**

```python
async def _resolve_work(work_id: str, bundle: ServiceBundle) -> str:
    cached = await bundle.cache.get_book_by_work(work_id)
    if cached is not None:
        return json.dumps(cached)

    work = await bundle.openlibrary.get_work(work_id)
    if work is None:
        return json.dumps({"error": "not_found", "identifier": work_id})

    description = work.get("description")
    if isinstance(description, dict):
        description = description.get("value")

    # Resolve authors directly from the work (no re-fetch needed)
    author_keys = _extract_author_keys(work)
    authors = await _resolve_author_keys(author_keys, bundle) if author_keys else []

    book: BookRecord = {
        "title": work.get("title", ""),
        "authors": authors,
        "publisher": None,
        "year": None,
        "edition": None,
        "isbn_10": None,
        "isbn_13": None,
        "openlibrary_work_id": work_id,
        "openlibrary_edition_id": None,
        "cover_url": None,
        "google_books_url": None,
        "subjects": work.get("subjects") or [],
        "page_count": None,
        "description": description if isinstance(description, str) else None,
    }
    await bundle.cache.set_book_by_work(work_id, book)
    return json.dumps(book)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run ruff + full suite**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m ruff check src/scholar_mcp/_tools_books.py && python -m pytest -x -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/scholar_mcp/_tools_books.py tests/test_tools_books.py
git commit -m "feat: enrich edition and work lookups with author names (#74)"
```

### Task 2.4: Update book enrichment to include authors

**Files:**
- Modify: `src/scholar_mcp/_book_enrichment.py:83-101`
- Test: `tests/test_book_enrichment.py`

- [ ] **Step 1: Add authors to _to_enrichment_dict**

The `_to_enrichment_dict` function currently omits `authors`. Add it so that `paper["book_metadata"]["authors"]` is populated (needed by PR 4 for author fallback in citations):

```python
def _to_enrichment_dict(book: BookRecord) -> dict[str, Any]:
    return {
        "publisher": book.get("publisher"),
        "edition": book.get("edition"),
        "isbn_13": book.get("isbn_13"),
        "cover_url": book.get("cover_url"),
        "openlibrary_work_id": book.get("openlibrary_work_id"),
        "description": book.get("description"),
        "subjects": book.get("subjects") or [],
        "page_count": book.get("page_count"),
        "authors": book.get("authors") or [],
    }
```

- [ ] **Step 2: Write test**

Add to `tests/test_book_enrichment.py`:

```python
def test_to_enrichment_dict_includes_authors() -> None:
    from scholar_mcp._book_enrichment import _to_enrichment_dict

    book: dict = {
        "title": "Test",
        "authors": ["Alice", "Bob"],
        "publisher": "Publisher",
        "edition": None,
        "isbn_13": "9781234567890",
        "cover_url": None,
        "openlibrary_work_id": "OL123W",
        "description": None,
        "subjects": [],
        "page_count": None,
    }
    result = _to_enrichment_dict(book)
    assert result["authors"] == ["Alice", "Bob"]


def test_to_enrichment_dict_empty_authors_defaults_to_list() -> None:
    from scholar_mcp._book_enrichment import _to_enrichment_dict

    book: dict = {"title": "Test"}
    result = _to_enrichment_dict(book)
    assert result["authors"] == []
```

- [ ] **Step 3: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_book_enrichment.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/scholar_mcp/_book_enrichment.py tests/test_book_enrichment.py
git commit -m "feat: include authors in book enrichment metadata (#74)"
```

### Task 2.5: Update docs and open PR 2

**Files:**
- Modify: `docs/tools/books.md` (if it exists, update to document author resolution behavior)

- [ ] **Step 1: Update docs**

If `docs/tools/books.md` exists, add a note that `get_book` automatically resolves authors from Open Library work records when looking up by ISBN or edition ID.

- [ ] **Step 2: Push branch and create PR**

```bash
git push -u origin feat/isbn-author-enrichment
gh pr create \
  --base feat/book-record-typeddict \
  --title "feat: enrich ISBN book results with authors from work metadata (#74)" \
  --body "## Summary
- Adds \`OpenLibraryClient.get_author()\` for resolving author keys
- Adds \`_resolve_author_keys()\` and \`_enrich_authors_from_work()\` helpers
- \`get_book\` by ISBN, edition ID, or work ID now resolves author names
- Authors are cached in the BookRecord, so extra HTTP only on first lookup
- Includes authors in \`book_metadata\` enrichment dict

Stacked on: #PR1_NUMBER (BookRecord + CacheProtocol)
Closes #74

## Test plan
- [ ] \`test_get_book_isbn_enriches_authors\` — ISBN lookup resolves authors
- [ ] \`test_get_book_edition_enriches_authors\` — edition ID lookup resolves authors
- [ ] \`test_get_book_work_resolves_authors\` — work ID lookup resolves authors
- [ ] \`test_to_enrichment_dict_includes_authors\` — enrichment dict has authors
- [ ] All existing book tests still pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)" \
  --milestone "v0.5.0"
```

---

## PR 3: recommend_books Tool (#69)

**Branch:** `feat/recommend-books` from `feat/isbn-author-enrichment`

### Task 3.1: Add get_subject() to OpenLibraryClient

**Files:**
- Modify: `src/scholar_mcp/_openlibrary_client.py`
- Test: `tests/test_openlibrary_client.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_openlibrary_client.py`:

```python
SAMPLE_SUBJECT_RESPONSE = {
    "name": "Machine learning",
    "work_count": 1234,
    "works": [
        {
            "title": "Pattern Recognition and Machine Learning",
            "key": "/works/OL8173450W",
            "authors": [{"name": "Christopher M. Bishop", "key": "/authors/OL123A"}],
            "edition_count": 15,
            "cover_id": 12345,
        },
        {
            "title": "Deep Learning",
            "key": "/works/OL17930368W",
            "authors": [{"name": "Ian Goodfellow", "key": "/authors/OL456A"}],
            "edition_count": 8,
            "cover_id": 67890,
        },
    ],
}


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_subject(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/subjects/machine_learning.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
    )
    client = OpenLibraryClient(
        httpx.AsyncClient(base_url=OL_BASE),
        RateLimiter(delay=0.0),
    )
    try:
        result = await client.get_subject("machine_learning", limit=10)
        assert result is not None
        assert result["name"] == "Machine learning"
        assert len(result["works"]) == 2
    finally:
        await client.aclose()


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_subject_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/subjects/nonexistent_topic_xyz.json").mock(
        return_value=httpx.Response(200, json={"name": "nonexistent_topic_xyz", "work_count": 0, "works": []})
    )
    client = OpenLibraryClient(
        httpx.AsyncClient(base_url=OL_BASE),
        RateLimiter(delay=0.0),
    )
    try:
        result = await client.get_subject("nonexistent_topic_xyz")
        assert result is not None
        assert result["works"] == []
    finally:
        await client.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py::test_get_subject -v`
Expected: FAIL (AttributeError)

- [ ] **Step 3: Implement get_subject**

Add to `OpenLibraryClient` in `_openlibrary_client.py`:

```python
    async def get_subject(
        self, subject: str, *, limit: int = 10
    ) -> dict[str, Any] | None:
        """Fetch books for a subject.

        Args:
            subject: Subject slug (e.g. ``machine_learning``).
            limit: Maximum number of works to return.

        Returns:
            Subject dict with ``name``, ``work_count``, and ``works`` list,
            or None on HTTP error.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(
                f"/subjects/{subject}.json", params={"limit": limit}
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_subject_error subject=%s", subject)
            return None
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py::test_get_subject tests/test_openlibrary_client.py::test_get_subject_not_found -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_openlibrary_client.py tests/test_openlibrary_client.py
git commit -m "feat: add OpenLibraryClient.get_subject() (#69)"
```

### Task 3.2: Add subject normalization and BookRecord conversion

**Files:**
- Modify: `src/scholar_mcp/_openlibrary_client.py`
- Test: `tests/test_openlibrary_client.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_openlibrary_client.py`:

```python
from scholar_mcp._openlibrary_client import normalize_subject, normalize_subject_work


def test_normalize_subject() -> None:
    assert normalize_subject("Machine Learning") == "machine_learning"
    assert normalize_subject("  deep learning  ") == "deep_learning"
    assert normalize_subject("algorithms") == "algorithms"
    assert normalize_subject("Natural Language Processing") == "natural_language_processing"


def test_normalize_subject_work() -> None:
    work = {
        "title": "Deep Learning",
        "key": "/works/OL17930368W",
        "authors": [{"name": "Ian Goodfellow"}],
        "edition_count": 8,
        "cover_id": 67890,
    }
    book = normalize_subject_work(work)
    assert book["title"] == "Deep Learning"
    assert book["authors"] == ["Ian Goodfellow"]
    assert book["openlibrary_work_id"] == "OL17930368W"
    assert book["cover_url"] == "https://covers.openlibrary.org/b/id/67890-M.jpg"
    assert book["isbn_13"] is None
    assert book["publisher"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py::test_normalize_subject -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement normalize_subject and normalize_subject_work**

Add to `_openlibrary_client.py`:

```python
def normalize_subject(subject: str) -> str:
    """Normalize a subject string for the Open Library subject API.

    Args:
        subject: Free-text subject (e.g. ``"Machine Learning"``).

    Returns:
        Lowercase slug with spaces replaced by underscores.
    """
    return subject.strip().lower().replace(" ", "_")


def normalize_subject_work(work: dict[str, Any]) -> BookRecord:
    """Convert an Open Library subject API work entry to a BookRecord.

    Args:
        work: Work dict from the ``/subjects/{subject}.json`` response.

    Returns:
        Normalized BookRecord (ISBN and edition fields are None).
    """
    work_key = work.get("key") or ""
    work_match = _OL_WORK_RE.search(work_key)
    cover_id = work.get("cover_id")
    authors = [
        a["name"] for a in (work.get("authors") or [])
        if isinstance(a, dict) and a.get("name")
    ]
    return BookRecord(
        title=work.get("title", ""),
        authors=authors,
        publisher=None,
        year=None,
        edition=None,
        isbn_10=None,
        isbn_13=None,
        openlibrary_work_id=work_match.group(0) if work_match else None,
        openlibrary_edition_id=None,
        cover_url=(
            f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
            if cover_id
            else None
        ),
        google_books_url=None,
        subjects=[],
        page_count=None,
        description=None,
    )
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_openlibrary_client.py::test_normalize_subject tests/test_openlibrary_client.py::test_normalize_subject_work -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_openlibrary_client.py tests/test_openlibrary_client.py
git commit -m "feat: add subject normalization and subject work → BookRecord (#69)"
```

### Task 3.3: Add book_subject cache methods

**Files:**
- Modify: `src/scholar_mcp/_cache.py`
- Modify: `src/scholar_mcp/_protocols.py`
- Test: `tests/test_cache_books.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_cache_books.py`:

```python
async def test_book_subject_roundtrip(cache: ScholarCache) -> None:
    books = [
        {"title": "Book A", "authors": ["Author A"]},
        {"title": "Book B", "authors": ["Author B"]},
    ]
    await cache.set_book_subject("machine_learning", books)
    result = await cache.get_book_subject("machine_learning")
    assert result is not None
    assert len(result) == 2
    assert result[0]["title"] == "Book A"


async def test_book_subject_returns_none_when_missing(cache: ScholarCache) -> None:
    result = await cache.get_book_subject("nonexistent")
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_cache_books.py::test_book_subject_roundtrip -v`
Expected: FAIL (AttributeError)

- [ ] **Step 3: Add cache methods and schema**

In `_cache.py`, add TTL constant after `_BOOK_SEARCH_TTL`:

```python
_BOOK_SUBJECT_TTL = 7 * 86400  # 7 days
```

Add to `_SCHEMA` string (after the `books_search` table):

```sql
CREATE TABLE IF NOT EXISTS books_subject (
    query_hash TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_subject_cached ON books_subject(cached_at);
```

Add `"books_subject"` to `_TTL_TABLES` tuple.

Add methods to `ScholarCache` (after `set_book_search`):

```python
    async def get_book_subject(self, subject: str) -> list[BookRecord] | None:
        """Return cached book subject results or None if missing/stale.

        Args:
            subject: Normalized subject slug; SHA-256 hash used as cache key.

        Returns:
            List of BookRecord dicts or None.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(subject.encode()).hexdigest()
        async with db.execute(
            "SELECT data, cached_at FROM books_subject WHERE query_hash = ?",
            (query_hash,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _BOOK_SUBJECT_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_book_subject(self, subject: str, data: list[BookRecord]) -> None:
        """Cache book subject results.

        Args:
            subject: Normalized subject slug; SHA-256 hash used as cache key.
            data: List of BookRecord dicts.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(subject.encode()).hexdigest()
        await db.execute(
            "INSERT OR REPLACE INTO books_subject (query_hash, data, cached_at) VALUES (?, ?, ?)",
            (query_hash, json.dumps(data), time.time()),
        )
        await db.commit()
```

- [ ] **Step 4: Update CacheProtocol**

Add to `CacheProtocol` in `_protocols.py` (after `set_book_search`):

```python
    async def get_book_subject(
        self, subject: str
    ) -> list[BookRecord] | None: ...
    async def set_book_subject(
        self, subject: str, data: list[BookRecord]
    ) -> None: ...
```

- [ ] **Step 5: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_cache_books.py tests/test_protocols.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_cache.py src/scholar_mcp/_protocols.py tests/test_cache_books.py
git commit -m "feat: add book subject cache methods (#69)"
```

### Task 3.4: Add recommend_books tool

**Files:**
- Modify: `src/scholar_mcp/_tools_books.py`
- Test: `tests/test_tools_books.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_tools_books.py`:

```python
SAMPLE_SUBJECT_RESPONSE = {
    "name": "Machine learning",
    "work_count": 100,
    "works": [
        {
            "title": "Pattern Recognition",
            "key": "/works/OL8173450W",
            "authors": [{"name": "Christopher Bishop"}],
            "edition_count": 15,
            "cover_id": 12345,
        },
        {
            "title": "Deep Learning",
            "key": "/works/OL17930368W",
            "authors": [{"name": "Ian Goodfellow"}],
            "edition_count": 8,
            "cover_id": None,
        },
    ],
}


@pytest.mark.respx(base_url=OL_BASE)
async def test_recommend_books_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/subjects/machine_learning.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "recommend_books", {"subject": "machine learning"}
        )
    data = json.loads(result.content[0].text)
    assert len(data) == 2
    assert data[0]["title"] == "Pattern Recognition"
    assert data[0]["authors"] == ["Christopher Bishop"]
    assert data[0]["openlibrary_work_id"] == "OL8173450W"


@pytest.mark.respx(base_url=OL_BASE)
async def test_recommend_books_caches_results(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/subjects/algorithms.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
    )
    async with Client(mcp) as client:
        await client.call_tool("recommend_books", {"subject": "algorithms"})
    cached = await bundle.cache.get_book_subject("algorithms")
    assert cached is not None
    assert len(cached) == 2


@pytest.mark.respx(base_url=OL_BASE)
async def test_recommend_books_empty_subject(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/subjects/nonexistent.json").mock(
        return_value=httpx.Response(
            200, json={"name": "nonexistent", "work_count": 0, "works": []}
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "recommend_books", {"subject": "nonexistent"}
        )
    data = json.loads(result.content[0].text)
    assert data == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py::test_recommend_books_returns_results -v`
Expected: FAIL

- [ ] **Step 3: Implement recommend_books tool**

In `_tools_books.py`, add import at top:

```python
from ._openlibrary_client import normalize_book, normalize_subject, normalize_subject_work
```

Inside `register_book_tools(mcp)`, add after the `get_book` tool:

```python
    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def recommend_books(
        subject: str,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Recommend books for a subject via Open Library.

        Uses the Open Library subject API to find popular books on a
        topic, sorted by edition count (a proxy for popularity).

        Args:
            subject: Subject or topic (e.g. "machine learning",
                "algorithms", "computer vision").
            limit: Maximum results to return (max 50).

        Returns:
            JSON list of book records sorted by popularity.
        """
        limit = max(1, min(limit, 50))
        slug = normalize_subject(subject)

        cached = await bundle.cache.get_book_subject(slug)
        if cached is not None:
            logger.debug("book_subject_cache_hit subject=%s", slug)
            return json.dumps(cached[:limit])

        async def _execute(*, retry: bool = True) -> str:
            subject_data = await bundle.openlibrary.get_subject(slug, limit=limit)
            if subject_data is None:
                return json.dumps([])
            works = subject_data.get("works") or []
            books = [normalize_subject_work(w) for w in works]
            await bundle.cache.set_book_subject(slug, books)
            return json.dumps(books)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="recommend_books"
            )
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "recommend_books"}
            )
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_tools_books.py -v -k recommend`
Expected: PASS

- [ ] **Step 5: Run full test suite + ruff**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m ruff check src/scholar_mcp/ && python -m ruff format --check src/scholar_mcp/ && python -m pytest -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_tools_books.py tests/test_tools_books.py
git commit -m "feat: add recommend_books tool via Open Library subject API (#69)"
```

### Task 3.5: Update docs and open PR 3

**Files:**
- Modify: `docs/tools/books.md` (add recommend_books documentation)

- [ ] **Step 1: Update docs**

Add `recommend_books` to the books tool documentation with usage examples and parameter descriptions.

- [ ] **Step 2: Push branch and create PR**

```bash
git push -u origin feat/recommend-books
gh pr create \
  --base feat/isbn-author-enrichment \
  --title "feat: add recommend_books tool via Open Library subject API (#69)" \
  --body "## Summary
- Adds \`OpenLibraryClient.get_subject()\` for the subject API
- Adds \`normalize_subject()\` and \`normalize_subject_work()\` helpers
- Adds \`get_book_subject\`/\`set_book_subject\` cache methods (7-day TTL)
- New \`recommend_books(subject, limit)\` MCP tool
- Results sorted by edition count (popularity proxy)
- Updates CacheProtocol with new methods

Stacked on: #PR2_NUMBER (ISBN author enrichment)
Closes #69

## Test plan
- [ ] \`test_recommend_books_returns_results\` — results normalized correctly
- [ ] \`test_recommend_books_caches_results\` — cache populated after first call
- [ ] \`test_recommend_books_empty_subject\` — returns empty list for unknown subjects
- [ ] All existing tests still pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)" \
  --milestone "v0.5.0"
```

---

## PR 4: BibLaTeX @book Citation Output (#65)

**Branch:** `feat/book-citation-output` from `feat/recommend-books`

### Task 4.1: Add @book entry type detection

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py:127-142`
- Test: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_citation_formatter.py`:

```python
class TestInferEntryType:
    def test_article_default(self) -> None:
        assert infer_entry_type({"venue": "Nature"}) == "article"

    def test_inproceedings(self) -> None:
        assert infer_entry_type({"venue": "Conference on X"}) == "inproceedings"

    def test_misc_arxiv(self) -> None:
        assert infer_entry_type({"externalIds": {"ArXiv": "2301.00001"}, "venue": ""}) == "misc"

    def test_book_with_isbn(self) -> None:
        paper = {
            "book_metadata": {"isbn_13": "9780201633610", "publisher": "Addison-Wesley"},
        }
        assert infer_entry_type(paper) == "book"

    def test_book_with_publisher_only(self) -> None:
        paper = {
            "book_metadata": {"publisher": "MIT Press"},
        }
        assert infer_entry_type(paper) == "book"

    def test_book_metadata_without_isbn_or_publisher_falls_through(self) -> None:
        paper = {
            "book_metadata": {"description": "A book"},
            "venue": "Nature",
        }
        assert infer_entry_type(paper) == "article"
```

- [ ] **Step 2: Run test to verify the new tests fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestInferEntryType -v`
Expected: `test_book_with_isbn` and `test_book_with_publisher_only` FAIL

- [ ] **Step 3: Update infer_entry_type**

In `_citation_formatter.py`, update `infer_entry_type` (line 127):

```python
def infer_entry_type(paper: dict[str, Any]) -> str:
    """Infer BibTeX entry type from paper metadata.

    Args:
        paper: Paper metadata dict.

    Returns:
        One of ``"book"``, ``"article"``, ``"inproceedings"``, or ``"misc"``.
    """
    book_meta = paper.get("book_metadata")
    if book_meta and (book_meta.get("isbn_13") or book_meta.get("publisher")):
        return "book"
    venue = (paper.get("venue") or "").lower()
    if any(kw in venue for kw in _CONFERENCE_KEYWORDS):
        return "inproceedings"
    external_ids = paper.get("externalIds") or {}
    if external_ids.get("ArXiv") and not venue:
        return "misc"
    return "article"
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestInferEntryType -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: detect @book entry type from book_metadata (#65)"
```

### Task 4.2: Add @book fields to BibTeX formatter

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py:190-261`
- Test: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_citation_formatter.py`:

```python
class TestFormatBibtexBook:
    def test_book_entry_type_and_fields(self) -> None:
        papers = [
            {
                "title": "Deep Learning",
                "authors": [{"name": "Ian Goodfellow"}],
                "year": 2016,
                "venue": "",
                "externalIds": {},
                "book_metadata": {
                    "isbn_13": "9780262035613",
                    "publisher": "MIT Press",
                    "edition": "1st",
                    "authors": [],
                },
            }
        ]
        result = format_bibtex(papers, [])
        assert "@book{goodfellow2016," in result
        assert "publisher = {MIT Press}" in result
        assert "edition = {1st}" in result
        assert "isbn = {9780262035613}" in result
        assert "journal" not in result

    def test_book_author_fallback(self) -> None:
        papers = [
            {
                "title": "Some Book",
                "authors": [],
                "year": 2020,
                "venue": "",
                "externalIds": {},
                "book_metadata": {
                    "isbn_13": "9781234567890",
                    "publisher": "Publisher",
                    "authors": ["Alice Smith", "Bob Jones"],
                },
            }
        ]
        result = format_bibtex(papers, [])
        assert "@book{" in result
        assert "author = {Alice Smith and Bob Jones}" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestFormatBibtexBook -v`
Expected: FAIL

- [ ] **Step 3: Update format_bibtex**

In `_citation_formatter.py`, update `format_bibtex` (around line 215-258). After the existing author/title/year/venue/DOI/URL/abstract/arxiv field blocks, add book-specific fields:

Replace the author block to handle fallback:

```python
        # Author: prefer S2 authors, fall back to book_metadata authors
        author_str = _format_bibtex_author(paper)
        if not author_str and entry_type == "book":
            bm = paper.get("book_metadata") or {}
            bm_authors = bm.get("authors") or []
            if bm_authors:
                author_str = " and ".join(
                    escape_bibtex(a) for a in bm_authors
                )
        if author_str:
            fields.append(f"  author = {{{author_str}}}")
```

After the venue block, add book-specific fields:

```python
        # Book-specific fields from book_metadata
        if entry_type == "book":
            bm = paper.get("book_metadata") or {}
            publisher = bm.get("publisher")
            if publisher:
                fields.append(f"  publisher = {{{escape_bibtex(publisher)}}}")
            edition = bm.get("edition")
            if edition:
                fields.append(f"  edition = {{{escape_bibtex(edition)}}}")
            isbn = bm.get("isbn_13")
            if isbn:
                fields.append(f"  isbn = {{{isbn}}}")
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestFormatBibtexBook -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: emit @book BibTeX entries with publisher/edition/isbn (#65)"
```

### Task 4.3: Add book type to CSL-JSON formatter

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py:264-360`
- Test: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_citation_formatter.py`:

```python
class TestFormatCslJsonBook:
    def test_book_type_and_fields(self) -> None:
        papers = [
            {
                "title": "Deep Learning",
                "authors": [{"name": "Ian Goodfellow"}],
                "year": 2016,
                "venue": "",
                "externalIds": {},
                "book_metadata": {
                    "isbn_13": "9780262035613",
                    "publisher": "MIT Press",
                    "authors": [],
                },
            }
        ]
        result_str = format_csl_json(papers, [])
        result = json.loads(result_str)
        entry = result["citations"][0]
        assert entry["type"] == "book"
        assert entry["publisher"] == "MIT Press"
        assert entry["ISBN"] == "9780262035613"

    def test_book_author_fallback_csl(self) -> None:
        papers = [
            {
                "title": "Some Book",
                "authors": [],
                "year": 2020,
                "venue": "",
                "externalIds": {},
                "book_metadata": {
                    "isbn_13": "9781234567890",
                    "publisher": "Publisher",
                    "authors": ["Alice Smith"],
                },
            }
        ]
        result_str = format_csl_json(papers, [])
        result = json.loads(result_str)
        entry = result["citations"][0]
        assert entry["author"][0]["family"] == "Smith"
        assert entry["author"][0]["given"] == "Alice"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestFormatCslJsonBook -v`
Expected: FAIL

- [ ] **Step 3: Update CSL-JSON formatter**

Add `"book"` to `_CSL_TYPE_MAP`:

```python
_CSL_TYPE_MAP: dict[str, str] = {
    "article": "article-journal",
    "inproceedings": "paper-conference",
    "misc": "article",
    "book": "book",
}
```

In `format_csl_json`, after the author block, add author fallback:

```python
        csl_authors = _csl_author(paper)
        if not csl_authors and entry_type == "book":
            bm = paper.get("book_metadata") or {}
            for author_name in bm.get("authors") or []:
                parsed = parse_author_name(author_name)
                ae: dict[str, str] = {}
                if parsed.last:
                    ae["family"] = parsed.last
                if parsed.first:
                    ae["given"] = parsed.first
                if parsed.prefix:
                    ae["non-dropping-particle"] = parsed.prefix
                if parsed.suffix:
                    ae["suffix"] = parsed.suffix
                if ae:
                    csl_authors.append(ae)
        if csl_authors:
            entry["author"] = csl_authors
```

After the existing fields, add book-specific fields:

```python
        if entry_type == "book":
            bm = paper.get("book_metadata") or {}
            if bm.get("publisher"):
                entry["publisher"] = bm["publisher"]
            if bm.get("isbn_13"):
                entry["ISBN"] = bm["isbn_13"]
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestFormatCslJsonBook -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: emit book type in CSL-JSON with publisher/ISBN (#65)"
```

### Task 4.4: Add book type to RIS formatter

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py:363-448`
- Test: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_citation_formatter.py`:

```python
class TestFormatRisBook:
    def test_book_type_and_fields(self) -> None:
        papers = [
            {
                "title": "Deep Learning",
                "authors": [{"name": "Ian Goodfellow"}],
                "year": 2016,
                "venue": "",
                "externalIds": {},
                "book_metadata": {
                    "isbn_13": "9780262035613",
                    "publisher": "MIT Press",
                    "authors": [],
                },
            }
        ]
        result = format_ris(papers, [])
        assert "TY  - BOOK" in result
        assert "PB  - MIT Press" in result
        assert "SN  - 9780262035613" in result

    def test_book_author_fallback_ris(self) -> None:
        papers = [
            {
                "title": "Some Book",
                "authors": [],
                "year": 2020,
                "venue": "",
                "externalIds": {},
                "book_metadata": {
                    "isbn_13": "9781234567890",
                    "publisher": "Publisher",
                    "authors": ["Alice Smith"],
                },
            }
        ]
        result = format_ris(papers, [])
        assert "TY  - BOOK" in result
        assert "AU  - Smith, Alice" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestFormatRisBook -v`
Expected: FAIL

- [ ] **Step 3: Update RIS formatter**

Add `"book"` to `_RIS_TYPE_MAP`:

```python
_RIS_TYPE_MAP: dict[str, str] = {
    "article": "JOUR",
    "inproceedings": "CONF",
    "misc": "GEN",
    "book": "BOOK",
}
```

In `format_ris`, after the author lines, add author fallback:

```python
        author_lines = _ris_author_line(paper)
        if not author_lines and entry_type == "book":
            bm = paper.get("book_metadata") or {}
            for author_name in bm.get("authors") or []:
                parsed = parse_author_name(author_name)
                name = (
                    f"{parsed.prefix} {parsed.last}" if parsed.prefix else parsed.last
                )
                if parsed.first:
                    name = f"{name}, {parsed.first}"
                if parsed.suffix:
                    name = f"{name}, {parsed.suffix}"
                if name:
                    author_lines.append(f"AU  - {name}")
        lines.extend(author_lines)
```

After the venue/DOI/URL/abstract block, add book-specific tags:

```python
        if entry_type == "book":
            bm = paper.get("book_metadata") or {}
            if bm.get("publisher"):
                lines.append(f"PB  - {bm['publisher']}")
            if bm.get("isbn_13"):
                lines.append(f"SN  - {bm['isbn_13']}")
```

- [ ] **Step 4: Run tests**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m pytest tests/test_citation_formatter.py::TestFormatRisBook -v`
Expected: PASS

- [ ] **Step 5: Run full test suite + ruff**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && python -m ruff check src/scholar_mcp/ && python -m ruff format --check src/scholar_mcp/ && python -m pytest -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: emit BOOK type in RIS with publisher/ISBN (#65)"
```

### Task 4.5: Postpone @incollection to correct milestone

- [ ] **Step 1: Find which milestone contains #64**

```bash
gh api repos/pvliesdonk/scholar-mcp/issues/64 --jq '.milestone.title // "none"'
```

- [ ] **Step 2: If #64 has a milestone, add a comment to #65 noting @incollection is deferred there. If #64 has no milestone, create one or assign to a future milestone.**

```bash
gh issue comment 65 --repo pvliesdonk/scholar-mcp \
  --body "@incollection support (for \`BookChapterRecord\`) is deferred to the milestone containing #64 (chapter-level resolution). The @book output implemented here covers the v0.5.0 scope."
```

### Task 4.6: Update docs and open PR 4

**Files:**
- Modify: `docs/tools/` (update citation docs to mention @book support)

- [ ] **Step 1: Update docs**

Document that `generate_citations` now emits `@book` entries when `book_metadata` is present on a paper record, including publisher, edition, and ISBN fields.

- [ ] **Step 2: Push branch and create PR**

```bash
git push -u origin feat/book-citation-output
gh pr create \
  --base feat/recommend-books \
  --title "feat: BibLaTeX @book output in generate_citations (#65)" \
  --body "## Summary
- \`infer_entry_type()\` detects books via \`book_metadata\` (ISBN or publisher)
- BibTeX: emits \`@book\` with \`publisher\`, \`edition\`, \`isbn\` fields
- CSL-JSON: emits \`type: \"book\"\` with \`publisher\` and \`ISBN\`
- RIS: emits \`TY - BOOK\` with \`PB\` and \`SN\` tags
- Author fallback: uses \`book_metadata.authors\` when S2 authors list is empty
- \`@incollection\` deferred to milestone containing #64

Stacked on: #PR3_NUMBER (recommend_books)
Closes #65

## Test plan
- [ ] \`TestInferEntryType\` — book detection with ISBN, publisher, fallback
- [ ] \`TestFormatBibtexBook\` — @book entry, fields, author fallback
- [ ] \`TestFormatCslJsonBook\` — book type, publisher, ISBN, author fallback
- [ ] \`TestFormatRisBook\` — BOOK type, PB/SN tags, author fallback
- [ ] All existing citation tests still pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)" \
  --milestone "v0.5.0"
```

# Book Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add book-aware enrichment and lookup to scholar-mcp via Open Library, with two new tools (`search_books`, `get_book`) and auto-enrichment on existing paper tools.

**Architecture:** Flat module addition following the patent extension pattern. New `_openlibrary_client.py` API client, `_tools_books.py` tool module, and `_book_enrichment.py` centralized enrichment function. Open Library data is cached in SQLite alongside existing paper/patent caches. Enrichment hooks into 4 existing tools (`get_paper`, `get_references`, `get_citations`, `get_citation_graph`) via a post-processing call.

**Tech Stack:** Python 3.11+, httpx (async HTTP), aiosqlite (cache), FastMCP (tool framework), respx (test mocking)

**Spec:** `docs/specs/2026-04-06-book-support-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/scholar_mcp/_openlibrary_client.py` | Open Library API client + `_normalize_book()` |
| Create | `src/scholar_mcp/_tools_books.py` | `search_books` and `get_book` MCP tools |
| Create | `src/scholar_mcp/_book_enrichment.py` | Centralized `enrich_books()` for paper dicts |
| Create | `tests/test_openlibrary_client.py` | Client unit tests |
| Create | `tests/test_tools_books.py` | Tool integration tests |
| Create | `tests/test_book_enrichment.py` | Enrichment logic tests |
| Modify | `src/scholar_mcp/_cache.py:16-137` | Book TTLs, tables, get/set methods |
| Modify | `src/scholar_mcp/_server_deps.py:18,41-47,65-74,110-118,122-128` | Import, ServiceBundle field, lifespan wiring |
| Modify | `src/scholar_mcp/_server_tools.py:46-48` | Register book tools |
| Modify | `src/scholar_mcp/_tools_search.py:120-167` | Hook enrichment into `get_paper` |
| Modify | `src/scholar_mcp/_tools_graph.py:42-184,193-235,244-493` | Hook enrichment into `get_citations`, `get_references`, `get_citation_graph` |
| Modify | `tests/conftest.py:10-14,45-61` | Add OpenLibraryClient to bundle fixture |

---

## Task 1: ISBN Utilities and Cache Tables

**Files:**
- Modify: `src/scholar_mcp/_cache.py`
- Test: `tests/test_cache_books.py` (create)

- [ ] **Step 1: Write tests for ISBN-10 to ISBN-13 conversion**

Create `tests/test_cache_books.py`:

```python
"""Tests for book cache tables and ISBN normalization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholar_mcp._cache import ScholarCache, isbn10_to_isbn13, normalize_isbn


def test_isbn10_to_isbn13_design_patterns() -> None:
    assert isbn10_to_isbn13("0201633612") == "9780201633610"


def test_isbn10_to_isbn13_writing_secure_code() -> None:
    assert isbn10_to_isbn13("0735611319") == "9780735611313"


def test_normalize_isbn_already_13() -> None:
    assert normalize_isbn("9780201633610") == "9780201633610"


def test_normalize_isbn_strips_hyphens() -> None:
    assert normalize_isbn("978-0-201-63361-0") == "9780201633610"


def test_normalize_isbn_converts_10_to_13() -> None:
    assert normalize_isbn("0201633612") == "9780201633610"


def test_normalize_isbn_invalid_returns_as_is() -> None:
    assert normalize_isbn("notanisbn") == "notanisbn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_cache_books.py -v`
Expected: FAIL — `isbn10_to_isbn13` and `normalize_isbn` not importable.

- [ ] **Step 3: Implement ISBN utilities in `_cache.py`**

Add after line 14 (after `logger = ...`) in `src/scholar_mcp/_cache.py`:

```python
def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert an ISBN-10 to ISBN-13.

    Args:
        isbn10: 10-digit ISBN string (digits only, no hyphens).

    Returns:
        13-digit ISBN string.
    """
    stem = "978" + isbn10[:9]
    total = sum(
        int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(stem)
    )
    check = (10 - total % 10) % 10
    return stem + str(check)


def normalize_isbn(isbn: str) -> str:
    """Normalize ISBN to 13-digit form with no hyphens.

    Args:
        isbn: ISBN-10 or ISBN-13, optionally with hyphens.

    Returns:
        ISBN-13 string, or original string if not a valid ISBN.
    """
    cleaned = isbn.replace("-", "").replace(" ", "")
    if len(cleaned) == 13 and cleaned.isdigit():
        return cleaned
    if len(cleaned) == 10 and cleaned[:9].isdigit():
        return isbn10_to_isbn13(cleaned)
    return isbn
```

- [ ] **Step 4: Run ISBN tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_cache_books.py::test_isbn10_to_isbn13_design_patterns tests/test_cache_books.py::test_isbn10_to_isbn13_writing_secure_code tests/test_cache_books.py::test_normalize_isbn_already_13 tests/test_cache_books.py::test_normalize_isbn_strips_hyphens tests/test_cache_books.py::test_normalize_isbn_converts_10_to_13 tests/test_cache_books.py::test_normalize_isbn_invalid_returns_as_is -v`
Expected: 6 PASSED

- [ ] **Step 5: Write tests for book cache get/set methods**

Append to `tests/test_cache_books.py`:

```python
SAMPLE_BOOK = {
    "title": "Design Patterns",
    "authors": ["Erich Gamma", "Richard Helm", "Ralph Johnson", "John Vlissides"],
    "publisher": "Addison-Wesley",
    "year": 1994,
    "isbn_13": "9780201633610",
}


async def test_get_book_by_isbn_miss(cache: ScholarCache) -> None:
    result = await cache.get_book_by_isbn("9780201633610")
    assert result is None


async def test_set_and_get_book_by_isbn(cache: ScholarCache) -> None:
    await cache.set_book_by_isbn("9780201633610", SAMPLE_BOOK)
    result = await cache.get_book_by_isbn("9780201633610")
    assert result is not None
    assert result["title"] == "Design Patterns"


async def test_get_book_by_work_miss(cache: ScholarCache) -> None:
    result = await cache.get_book_by_work("OL1168083W")
    assert result is None


async def test_set_and_get_book_by_work(cache: ScholarCache) -> None:
    await cache.set_book_by_work("OL1168083W", SAMPLE_BOOK)
    result = await cache.get_book_by_work("OL1168083W")
    assert result is not None
    assert result["title"] == "Design Patterns"


async def test_get_book_search_miss(cache: ScholarCache) -> None:
    result = await cache.get_book_search("design patterns")
    assert result is None


async def test_set_and_get_book_search(cache: ScholarCache) -> None:
    await cache.set_book_search("design patterns", [SAMPLE_BOOK])
    result = await cache.get_book_search("design patterns")
    assert result is not None
    assert len(result) == 1
    assert result[0]["title"] == "Design Patterns"
```

- [ ] **Step 6: Run cache tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_cache_books.py -v -k "cache"`
Expected: FAIL — `get_book_by_isbn` not an attribute of ScholarCache.

- [ ] **Step 7: Add book TTLs and schema tables to `_cache.py`**

Add TTL constants after `_PATENT_SEARCH_TTL` (line 28) in `src/scholar_mcp/_cache.py`:

```python
_BOOK_ISBN_TTL = 30 * 86400  # 30 days
_BOOK_WORK_TTL = 30 * 86400  # 30 days
_BOOK_SEARCH_TTL = 7 * 86400  # 7 days
```

Add tables to `_SCHEMA` before the closing `"""` (before line 122):

```sql
CREATE TABLE IF NOT EXISTS books_isbn (
    isbn      TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_isbn_cached ON books_isbn(cached_at);

CREATE TABLE IF NOT EXISTS books_openlibrary (
    work_id   TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_ol_cached ON books_openlibrary(cached_at);

CREATE TABLE IF NOT EXISTS books_search (
    query_hash TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_search_cached ON books_search(cached_at);
```

Add table names to `_TTL_TABLES` tuple (after `"patent_search"`):

```python
    "books_isbn",
    "books_openlibrary",
    "books_search",
```

- [ ] **Step 8: Add cache get/set methods to `ScholarCache`**

Add after the patent search section (after line 661) in `src/scholar_mcp/_cache.py`:

```python
    # ------------------------------------------------------------------
    # Books (Open Library)
    # ------------------------------------------------------------------

    async def get_book_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        """Return cached book data by ISBN or None if missing/stale.

        Args:
            isbn: ISBN-13 string (already normalized).

        Returns:
            Book metadata dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM books_isbn WHERE isbn = ?", (isbn,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _BOOK_ISBN_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_book_by_isbn(self, isbn: str, data: dict[str, Any]) -> None:
        """Cache book data by ISBN.

        Args:
            isbn: ISBN-13 string (already normalized).
            data: Book metadata dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO books_isbn (isbn, data, cached_at) VALUES (?, ?, ?)",
            (isbn, json.dumps(data), time.time()),
        )
        await db.commit()

    async def get_book_by_work(self, work_id: str) -> dict[str, Any] | None:
        """Return cached book data by Open Library work ID or None.

        Args:
            work_id: Open Library work ID (e.g. ``OL1168083W``).

        Returns:
            Book metadata dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM books_openlibrary WHERE work_id = ?",
            (work_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _BOOK_WORK_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_book_by_work(self, work_id: str, data: dict[str, Any]) -> None:
        """Cache book data by Open Library work ID.

        Args:
            work_id: Open Library work ID.
            data: Book metadata dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO books_openlibrary (work_id, data, cached_at) VALUES (?, ?, ?)",
            (work_id, json.dumps(data), time.time()),
        )
        await db.commit()

    async def get_book_search(self, query: str) -> list[dict[str, Any]] | None:
        """Return cached book search results or None if missing/stale.

        Args:
            query: Search query string; SHA-256 hash used as cache key.

        Returns:
            List of book metadata dicts or None.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        async with db.execute(
            "SELECT data, cached_at FROM books_search WHERE query_hash = ?",
            (query_hash,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _BOOK_SEARCH_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_book_search(
        self, query: str, data: list[dict[str, Any]]
    ) -> None:
        """Cache book search results.

        Args:
            query: Search query string; SHA-256 hash used as cache key.
            data: List of book metadata dicts.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        await db.execute(
            "INSERT OR REPLACE INTO books_search (query_hash, data, cached_at) VALUES (?, ?, ?)",
            (query_hash, json.dumps(data), time.time()),
        )
        await db.commit()
```

- [ ] **Step 9: Run all cache tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_cache_books.py -v`
Expected: All 12 tests PASSED

- [ ] **Step 10: Run full test suite to check for regressions**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest --timeout=30 -x -q`
Expected: All existing tests PASS

- [ ] **Step 11: Commit**

```bash
git add src/scholar_mcp/_cache.py tests/test_cache_books.py
git commit -m "feat: add ISBN utilities and book cache tables"
```

---

## Task 2: Open Library Client

**Files:**
- Create: `src/scholar_mcp/_openlibrary_client.py`
- Test: `tests/test_openlibrary_client.py` (create)

- [ ] **Step 1: Write tests for the Open Library client**

Create `tests/test_openlibrary_client.py`:

```python
"""Tests for Open Library API client."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from scholar_mcp._openlibrary_client import (
    OpenLibraryClient,
    _normalize_book,
)
from scholar_mcp._rate_limiter import RateLimiter

OL_BASE = "https://openlibrary.org"


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(delay=0.0)


@pytest.fixture
def ol_client(limiter: RateLimiter) -> OpenLibraryClient:
    http = httpx.AsyncClient(base_url=OL_BASE, timeout=10.0)
    return OpenLibraryClient(http, limiter)


SAMPLE_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_10": ["0201633612"],
    "isbn_13": ["9780201633610"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns", "Object-oriented programming"],
}

SAMPLE_WORK = {
    "title": "Design Patterns",
    "key": "/works/OL1168083W",
    "description": "A foundational book on software design patterns.",
    "subjects": ["Software patterns", "Object-oriented programming"],
    "authors": [{"author": {"key": "/authors/OL239963A"}, "type": {"key": "/type/author_role"}}],
}

SAMPLE_AUTHOR = {
    "name": "Erich Gamma",
    "key": "/authors/OL239963A",
}

SAMPLE_SEARCH = {
    "numFound": 1,
    "docs": [
        {
            "title": "Design Patterns",
            "author_name": ["Erich Gamma", "Richard Helm"],
            "publisher": ["Addison-Wesley"],
            "first_publish_year": 1994,
            "isbn": ["9780201633610", "0201633612"],
            "key": "/works/OL1168083W",
            "edition_key": ["OL1429049M"],
            "subject": ["Software patterns"],
            "number_of_pages_median": 395,
            "cover_i": 12345,
        }
    ],
}


@pytest.mark.respx(base_url=OL_BASE)
async def test_search(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH)
    )
    results = await ol_client.search("design patterns", limit=5)
    assert len(results) == 1
    assert results[0]["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_empty(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json={"numFound": 0, "docs": []})
    )
    results = await ol_client.search("nonexistent book xyz")
    assert results == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    result = await ol_client.get_by_isbn("9780201633610")
    assert result is not None
    assert result["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn_not_found(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/0000000000000.json").mock(
        return_value=httpx.Response(404)
    )
    result = await ol_client.get_by_isbn("0000000000000")
    assert result is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_work(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK)
    )
    result = await ol_client.get_work("OL1168083W")
    assert result is not None
    assert result["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_work_not_found(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/works/OL0000000W.json").mock(
        return_value=httpx.Response(404)
    )
    result = await ol_client.get_work("OL0000000W")
    assert result is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn_server_error(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(500)
    )
    result = await ol_client.get_by_isbn("9780201633610")
    assert result is None


def test_normalize_book_from_search_doc() -> None:
    doc = SAMPLE_SEARCH["docs"][0]
    book = _normalize_book(doc, source="search")
    assert book["title"] == "Design Patterns"
    assert book["authors"] == ["Erich Gamma", "Richard Helm"]
    assert book["publisher"] == "Addison-Wesley"
    assert book["year"] == 1994
    assert book["isbn_13"] == "9780201633610"
    assert book["openlibrary_work_id"] == "OL1168083W"
    assert book["subjects"] == ["Software patterns"]
    assert book["page_count"] == 395
    assert book["google_books_url"] is None


def test_normalize_book_from_edition() -> None:
    book = _normalize_book(SAMPLE_EDITION, source="edition")
    assert book["title"] == "Design Patterns"
    assert book["publisher"] == "Addison-Wesley"
    assert book["isbn_13"] == "9780201633610"
    assert book["isbn_10"] == "0201633612"
    assert book["openlibrary_edition_id"] == "OL1429049M"
    assert book["openlibrary_work_id"] == "OL1168083W"
    assert book["page_count"] == 395
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_openlibrary_client.py -v`
Expected: FAIL — module `_openlibrary_client` has no `OpenLibraryClient` (it currently holds the OpenAlex client, different file).

- [ ] **Step 3: Implement the Open Library client**

Create `src/scholar_mcp/_openlibrary_client.py`:

```python
"""Open Library API client for book metadata."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ._rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_COVER_BASE = "https://covers.openlibrary.org/b/isbn"

# Patterns for extracting OL identifiers from API keys.
_OL_WORK_RE = re.compile(r"OL\d+W")
_OL_EDITION_RE = re.compile(r"OL\d+M")


class OpenLibraryClient:
    """Thin async client for the Open Library API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at openlibrary.org.
        limiter: Rate limiter (~0.6s delay for ~100 req/min politeness).
    """

    def __init__(
        self, http_client: httpx.AsyncClient, limiter: RateLimiter
    ) -> None:
        self._client = http_client
        self._limiter = limiter

    async def search(
        self, query: str, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search Open Library for books.

        Args:
            query: Free-text search query.
            limit: Maximum number of results.

        Returns:
            List of raw Open Library search doc dicts.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(
                "/search.json", params={"q": query, "limit": limit}
            )
            r.raise_for_status()
            return r.json().get("docs", [])  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_search_error query=%s", query[:80])
            return []

    async def get_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        """Fetch book edition by ISBN.

        Args:
            isbn: ISBN-10 or ISBN-13 (digits only).

        Returns:
            Open Library edition dict, or None if not found.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(f"/isbn/{isbn}.json")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_isbn_error isbn=%s", isbn)
            return None

    async def get_work(self, work_id: str) -> dict[str, Any] | None:
        """Fetch work-level metadata.

        Args:
            work_id: Open Library work ID (e.g. ``OL1168083W``).

        Returns:
            Open Library work dict, or None if not found.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(f"/works/{work_id}.json")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_work_error work_id=%s", work_id)
            return None

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def _normalize_book(
    data: dict[str, Any], *, source: str = "search"
) -> dict[str, Any]:
    """Normalize an Open Library response to the standard book record shape.

    Args:
        data: Raw Open Library dict (search doc or edition).
        source: One of ``"search"`` or ``"edition"``.

    Returns:
        Normalized book record dict.
    """
    if source == "search":
        isbn_list = data.get("isbn") or []
        isbn_13 = next((i for i in isbn_list if len(i) == 13), None)
        isbn_10 = next((i for i in isbn_list if len(i) == 10), None)
        publishers = data.get("publisher") or []
        work_key = data.get("key") or ""
        work_match = _OL_WORK_RE.search(work_key)
        edition_keys = data.get("edition_key") or []
        cover_id = data.get("cover_i")
        return {
            "title": data.get("title", ""),
            "authors": data.get("author_name") or [],
            "publisher": publishers[0] if publishers else None,
            "year": data.get("first_publish_year"),
            "edition": None,
            "isbn_10": isbn_10,
            "isbn_13": isbn_13,
            "openlibrary_work_id": work_match.group(0) if work_match else None,
            "openlibrary_edition_id": edition_keys[0] if edition_keys else None,
            "cover_url": (
                f"{_COVER_BASE}/{isbn_13}-M.jpg"
                if isbn_13
                else (
                    f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                    if cover_id
                    else None
                )
            ),
            "google_books_url": None,
            "subjects": data.get("subject") or [],
            "page_count": data.get("number_of_pages_median"),
            "description": None,
        }

    # source == "edition"
    isbn_13_list = data.get("isbn_13") or []
    isbn_10_list = data.get("isbn_10") or []
    isbn_13 = isbn_13_list[0] if isbn_13_list else None
    isbn_10 = isbn_10_list[0] if isbn_10_list else None
    publishers = data.get("publishers") or []
    works = data.get("works") or []
    work_key = works[0]["key"] if works else ""
    work_match = _OL_WORK_RE.search(work_key)
    edition_key = data.get("key") or ""
    edition_match = _OL_EDITION_RE.search(edition_key)
    publish_date = data.get("publish_date") or ""
    year = None
    year_match = re.search(r"\d{4}", publish_date)
    if year_match:
        year = int(year_match.group(0))
    return {
        "title": data.get("title", ""),
        "authors": [],  # edition records lack author names; enrich from work
        "publisher": publishers[0] if publishers else None,
        "year": year,
        "edition": data.get("edition_name"),
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "openlibrary_work_id": work_match.group(0) if work_match else None,
        "openlibrary_edition_id": (
            edition_match.group(0) if edition_match else None
        ),
        "cover_url": (
            f"{_COVER_BASE}/{isbn_13}-M.jpg" if isbn_13 else None
        ),
        "google_books_url": None,
        "subjects": data.get("subjects") or [],
        "page_count": data.get("number_of_pages"),
        "description": None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_openlibrary_client.py -v`
Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_openlibrary_client.py tests/test_openlibrary_client.py
git commit -m "feat: add Open Library API client with normalization"
```

---

## Task 3: Wire OpenLibraryClient into ServiceBundle

**Files:**
- Modify: `src/scholar_mcp/_server_deps.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add OpenLibraryClient to ServiceBundle and lifespan**

In `src/scholar_mcp/_server_deps.py`:

Add import (after line 18):
```python
from ._openlibrary_client import OpenLibraryClient
```

Add constant (after line 25):
```python
_OPENLIBRARY_BASE = "https://openlibrary.org"
_OPENLIBRARY_DELAY = 0.6  # ~100 req/min politeness
```

Add field to `ServiceBundle` (after line 44, the `epo` field):
```python
    openlibrary: OpenLibraryClient
```

In the `make_service_lifespan` function, add after the `openalex = OpenAlexClient(openalex_http)` line (after line 74):
```python
    openlibrary_http = httpx.AsyncClient(
        base_url=_OPENLIBRARY_BASE,
        headers={"User-Agent": ua},
        timeout=30.0,
    )
    openlibrary_limiter = RateLimiter(delay=_OPENLIBRARY_DELAY)
    openlibrary = OpenLibraryClient(openlibrary_http, openlibrary_limiter)
```

Add `RateLimiter` import (line 15 area, add):
```python
from ._rate_limiter import RateLimiter
```

Add to `ServiceBundle(...)` instantiation (after `epo=epo,`):
```python
        openlibrary=openlibrary,
```

Add cleanup in the `finally` block (after `await openalex_http.aclose()`):
```python
        await openlibrary_http.aclose()
```

- [ ] **Step 2: Update test fixture in `tests/conftest.py`**

Add import (after line 12):
```python
from scholar_mcp._openlibrary_client import OpenLibraryClient
from scholar_mcp._rate_limiter import RateLimiter
```

Update the `bundle` fixture to include OpenLibraryClient. Replace the fixture body (lines 48-61):
```python
    s2 = S2Client(api_key=None, delay=0.0)
    openalex_http = httpx.AsyncClient(base_url="https://api.openalex.org")
    openalex = OpenAlexClient(openalex_http)
    openlibrary_http = httpx.AsyncClient(
        base_url="https://openlibrary.org", timeout=10.0
    )
    openlibrary = OpenLibraryClient(openlibrary_http, RateLimiter(delay=0.0))
    yield ServiceBundle(
        s2=s2,
        openalex=openalex,
        docling=None,
        epo=None,
        openlibrary=openlibrary,
        cache=cache,
        config=test_config,
        tasks=TaskQueue(),
    )
    await openlibrary_http.aclose()
    await openalex_http.aclose()
    await s2.aclose()
```

- [ ] **Step 3: Run full test suite to check for regressions**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest --timeout=30 -x -q`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/scholar_mcp/_server_deps.py tests/conftest.py
git commit -m "feat: wire OpenLibraryClient into ServiceBundle"
```

---

## Task 4: Book Tools (`search_books`, `get_book`)

**Files:**
- Create: `src/scholar_mcp/_tools_books.py`
- Modify: `src/scholar_mcp/_server_tools.py`
- Create: `tests/test_tools_books.py`

- [ ] **Step 1: Write tests for `search_books` tool**

Create `tests/test_tools_books.py`:

```python
"""Tests for search_books and get_book tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_books import register_book_tools

OL_BASE = "https://openlibrary.org"

SAMPLE_SEARCH_RESPONSE = {
    "numFound": 1,
    "docs": [
        {
            "title": "Design Patterns",
            "author_name": ["Erich Gamma"],
            "publisher": ["Addison-Wesley"],
            "first_publish_year": 1994,
            "isbn": ["9780201633610"],
            "key": "/works/OL1168083W",
            "edition_key": ["OL1429049M"],
            "subject": ["Software patterns"],
            "number_of_pages_median": 395,
        }
    ],
}

SAMPLE_EDITION_RESPONSE = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_13": ["9780201633610"],
    "isbn_10": ["0201633612"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns"],
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_book_tools(app)
    return app


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_books", {"query": "design patterns"}
        )
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["title"] == "Design Patterns"
    assert data[0]["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_caches_results(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
    )
    async with Client(mcp) as client:
        await client.call_tool("search_books", {"query": "design patterns"})
    # Second call should hit cache, not API
    cached = await bundle.cache.get_book_search("design patterns")
    assert cached is not None
    assert len(cached) == 1


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_isbn(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_book", {"identifier": "9780201633610"}
        )
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_isbn_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/isbn/0000000000000.json").mock(
        return_value=httpx.Response(404)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_book", {"identifier": "0000000000000"}
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_work_id(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Design Patterns",
                "key": "/works/OL1168083W",
                "description": "A book about patterns.",
                "subjects": ["Software patterns"],
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_book", {"identifier": "OL1168083W"}
        )
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["openlibrary_work_id"] == "OL1168083W"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_tools_books.py -v`
Expected: FAIL — `_tools_books` module not found.

- [ ] **Step 3: Implement `_tools_books.py`**

Create `src/scholar_mcp/_tools_books.py`:

```python
"""Book search and lookup MCP tools."""

from __future__ import annotations

import json
import logging
import re

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._cache import normalize_isbn
from ._openlibrary_client import _normalize_book
from ._rate_limiter import RateLimitedError
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

# Patterns for detecting identifier types.
_ISBN_RE = re.compile(r"^[\d\-]{10,17}$")
_OL_WORK_RE = re.compile(r"^OL\d+W$")
_OL_EDITION_RE = re.compile(r"^OL\d+M$")


def register_book_tools(mcp: FastMCP) -> None:
    """Register book search and lookup tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_books(
        query: str,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search for books by title, author, ISBN, or free text.

        Uses Open Library as the data source. For academic paper search,
        use search_papers instead.

        Args:
            query: Search query — title, author name, ISBN, or keywords.
            limit: Maximum results to return (max 50).

        Returns:
            JSON list of book records with title, authors, publisher, year,
            ISBNs, Open Library IDs, cover URL, and subjects.
        """
        limit = max(1, min(limit, 50))

        cached = await bundle.cache.get_book_search(query)
        if cached is not None:
            logger.debug("book_search_cache_hit query=%s", query[:60])
            return json.dumps(cached)

        async def _execute(*, retry: bool = True) -> str:
            docs = await bundle.openlibrary.search(query, limit=limit)
            books = [_normalize_book(doc, source="search") for doc in docs]
            await bundle.cache.set_book_search(query, books)
            return json.dumps(books)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="search_books"
            )
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "search_books"}
            )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_book(
        identifier: str,
        include_editions: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch book metadata by ISBN or Open Library ID.

        Args:
            identifier: ISBN-10, ISBN-13, Open Library work ID (e.g.
                OL1168083W), or edition ID (e.g. OL1429049M).
            include_editions: If true, fetch the work and list editions.

        Returns:
            JSON book record, or ``{"error": "not_found"}`` if not found.
        """
        cleaned = identifier.strip()

        async def _execute(*, retry: bool = True) -> str:
            # Detect identifier type
            if _OL_WORK_RE.match(cleaned):
                return await _resolve_work(cleaned, bundle)
            if _OL_EDITION_RE.match(cleaned):
                return await _resolve_work(cleaned, bundle)
            # Assume ISBN
            isbn = normalize_isbn(cleaned)
            return await _resolve_isbn(isbn, bundle)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="get_book"
            )
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "get_book"}
            )


async def _resolve_isbn(isbn: str, bundle: ServiceBundle) -> str:
    """Resolve a book by ISBN, checking cache first."""
    cached = await bundle.cache.get_book_by_isbn(isbn)
    if cached is not None:
        return json.dumps(cached)

    edition = await bundle.openlibrary.get_by_isbn(isbn)
    if edition is None:
        return json.dumps({"error": "not_found", "identifier": isbn})

    book = _normalize_book(edition, source="edition")
    await bundle.cache.set_book_by_isbn(isbn, book)
    if book.get("openlibrary_work_id"):
        await bundle.cache.set_book_by_work(book["openlibrary_work_id"], book)
    return json.dumps(book)


async def _resolve_work(work_id: str, bundle: ServiceBundle) -> str:
    """Resolve a book by Open Library work ID, checking cache first."""
    cached = await bundle.cache.get_book_by_work(work_id)
    if cached is not None:
        return json.dumps(cached)

    work = await bundle.openlibrary.get_work(work_id)
    if work is None:
        return json.dumps({"error": "not_found", "identifier": work_id})

    description = work.get("description")
    if isinstance(description, dict):
        description = description.get("value")
    book = {
        "title": work.get("title", ""),
        "authors": [],
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

- [ ] **Step 4: Register book tools in `_server_tools.py`**

Add at the end of `register_tools` in `src/scholar_mcp/_server_tools.py` (after line 48):

```python
    from ._tools_books import register_book_tools

    register_book_tools(mcp)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_tools_books.py -v`
Expected: All tests PASSED

- [ ] **Step 6: Run full test suite**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest --timeout=30 -x -q`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/scholar_mcp/_tools_books.py src/scholar_mcp/_server_tools.py tests/test_tools_books.py
git commit -m "feat: add search_books and get_book MCP tools"
```

---

## Task 5: Book Enrichment

**Files:**
- Create: `src/scholar_mcp/_book_enrichment.py`
- Create: `tests/test_book_enrichment.py`

- [ ] **Step 1: Write tests for enrichment logic**

Create `tests/test_book_enrichment.py`:

```python
"""Tests for book enrichment of paper records."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from scholar_mcp._book_enrichment import enrich_books
from scholar_mcp._server_deps import ServiceBundle

OL_BASE = "https://openlibrary.org"

SAMPLE_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_13": ["9780201633610"],
    "isbn_10": ["0201633612"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns"],
}


def _make_paper(
    *,
    paper_id: str = "p1",
    title: str = "A Paper",
    publication_types: list[str] | None = None,
    isbn: str | None = None,
) -> dict:
    paper: dict = {
        "paperId": paper_id,
        "title": title,
        "year": 2020,
    }
    if publication_types:
        paper["publicationTypes"] = publication_types
    if isbn:
        paper["externalIds"] = {"ISBN": isbn}
    return paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_triggered_by_isbn(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper = _make_paper(isbn="9780201633610")
    await enrich_books([paper], bundle)
    assert "book_metadata" in paper
    assert paper["book_metadata"]["publisher"] == "Addison-Wesley"
    assert paper["book_metadata"]["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_triggered_by_publication_type_with_isbn(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper = _make_paper(
        publication_types=["Book"], isbn="9780201633610"
    )
    await enrich_books([paper], bundle)
    assert "book_metadata" in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_skipped_for_book_type_without_isbn(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    paper = _make_paper(publication_types=["Book"])
    await enrich_books([paper], bundle)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_skipped_for_regular_paper(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    paper = _make_paper()
    await enrich_books([paper], bundle)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_failure_leaves_paper_unchanged(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(500)
    )
    paper = _make_paper(isbn="9780201633610")
    await enrich_books([paper], bundle)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_uses_cache_on_second_call(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper1 = _make_paper(isbn="9780201633610")
    await enrich_books([paper1], bundle)
    assert "book_metadata" in paper1

    # Second call — API should not be hit (cache)
    paper2 = _make_paper(isbn="9780201633610")
    await enrich_books([paper2], bundle)
    assert "book_metadata" in paper2
    assert paper2["book_metadata"]["publisher"] == "Addison-Wesley"


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_batch_multiple_papers(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    papers = [
        _make_paper(paper_id="p1", isbn="9780201633610"),
        _make_paper(paper_id="p2"),  # no ISBN, should be skipped
        _make_paper(paper_id="p3", isbn="9780201633610"),  # same ISBN, cache hit
    ]
    await enrich_books(papers, bundle)
    assert "book_metadata" in papers[0]
    assert "book_metadata" not in papers[1]
    assert "book_metadata" in papers[2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_book_enrichment.py -v`
Expected: FAIL — `_book_enrichment` module not found.

- [ ] **Step 3: Implement `_book_enrichment.py`**

Create `src/scholar_mcp/_book_enrichment.py`:

```python
"""Centralized book enrichment for paper records."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ._cache import normalize_isbn
from ._openlibrary_client import _normalize_book
from ._server_deps import ServiceBundle

logger = logging.getLogger(__name__)


def _needs_book_enrichment(paper: dict[str, Any]) -> bool:
    """Check whether a paper should be enriched with book metadata.

    Args:
        paper: S2 paper dict.

    Returns:
        True if the paper has an ISBN in externalIds.
    """
    ext = paper.get("externalIds") or {}
    if ext.get("ISBN"):
        return True
    # publicationTypes alone (without ISBN) cannot be resolved
    return False


def _extract_isbn(paper: dict[str, Any]) -> str | None:
    """Extract and normalize ISBN from a paper's externalIds.

    Args:
        paper: S2 paper dict.

    Returns:
        Normalized ISBN-13, or None.
    """
    ext = paper.get("externalIds") or {}
    isbn = ext.get("ISBN")
    if isbn:
        return normalize_isbn(isbn)
    return None


async def _enrich_one(paper: dict[str, Any], bundle: ServiceBundle) -> None:
    """Enrich a single paper dict in-place with book metadata.

    Args:
        paper: S2 paper dict (mutated in-place).
        bundle: Service bundle for API/cache access.
    """
    isbn = _extract_isbn(paper)
    if isbn is None:
        return

    try:
        cached = await bundle.cache.get_book_by_isbn(isbn)
        if cached is not None:
            paper["book_metadata"] = _to_enrichment_dict(cached)
            return

        edition = await bundle.openlibrary.get_by_isbn(isbn)
        if edition is None:
            return

        book = _normalize_book(edition, source="edition")
        await bundle.cache.set_book_by_isbn(isbn, book)
        if book.get("openlibrary_work_id"):
            await bundle.cache.set_book_by_work(
                book["openlibrary_work_id"], book
            )
        paper["book_metadata"] = _to_enrichment_dict(book)
    except Exception:
        logger.debug(
            "book_enrich_failed paper=%s isbn=%s",
            paper.get("paperId"),
            isbn,
            exc_info=True,
        )


def _to_enrichment_dict(book: dict[str, Any]) -> dict[str, Any]:
    """Extract the enrichment-relevant subset from a full book record.

    Args:
        book: Normalized book record dict.

    Returns:
        Dict with book metadata fields for paper enrichment.
    """
    return {
        "publisher": book.get("publisher"),
        "edition": book.get("edition"),
        "isbn_13": book.get("isbn_13"),
        "cover_url": book.get("cover_url"),
        "openlibrary_work_id": book.get("openlibrary_work_id"),
        "description": book.get("description"),
        "subjects": book.get("subjects") or [],
        "page_count": book.get("page_count"),
    }


async def enrich_books(
    papers: list[dict[str, Any]],
    bundle: ServiceBundle,
    *,
    concurrency: int = 5,
) -> None:
    """Enrich paper dicts in-place with book metadata from Open Library.

    Only papers with an ISBN in ``externalIds`` are enriched. Failures
    are logged and silently skipped.

    Args:
        papers: List of S2 paper dicts (mutated in-place).
        bundle: Service bundle for API/cache access.
        concurrency: Max parallel Open Library requests.
    """
    candidates = [p for p in papers if _needs_book_enrichment(p)]
    if not candidates:
        return

    sem = asyncio.Semaphore(concurrency)

    async def _bounded(paper: dict[str, Any]) -> None:
        async with sem:
            await _enrich_one(paper, bundle)

    await asyncio.gather(*(_bounded(p) for p in candidates))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_book_enrichment.py -v`
Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_book_enrichment.py tests/test_book_enrichment.py
git commit -m "feat: add centralized book enrichment for paper records"
```

---

## Task 6: Hook Enrichment into Existing Tools

**Files:**
- Modify: `src/scholar_mcp/_tools_search.py:120-167` (`get_paper`)
- Modify: `src/scholar_mcp/_tools_graph.py:42-184,193-235,244-493`
- Test: `tests/test_book_enrichment_integration.py` (create)

- [ ] **Step 1: Write integration test for enrichment in `get_paper`**

Create `tests/test_book_enrichment_integration.py`:

```python
"""Integration tests for book enrichment in existing tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_search import register_search_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OL_BASE = "https://openlibrary.org"

BOOK_PAPER = {
    "paperId": "book1",
    "title": "Design Patterns",
    "year": 1994,
    "publicationTypes": ["Book"],
    "externalIds": {"ISBN": "9780201633610"},
}

OL_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_13": ["9780201633610"],
    "isbn_10": ["0201633612"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app)
    return app


async def test_get_paper_enriches_book(mcp: FastMCP) -> None:
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/book1").mock(
            return_value=httpx.Response(200, json=BOOK_PAPER)
        )
        respx.get(f"{OL_BASE}/isbn/9780201633610.json").mock(
            return_value=httpx.Response(200, json=OL_EDITION)
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_paper", {"identifier": "book1"}
            )
    data = json.loads(result.content[0].text)
    assert "book_metadata" in data
    assert data["book_metadata"]["publisher"] == "Addison-Wesley"


async def test_get_paper_no_enrichment_for_regular_paper(mcp: FastMCP) -> None:
    regular_paper = {
        "paperId": "reg1",
        "title": "Regular Paper",
        "year": 2024,
    }
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/reg1").mock(
            return_value=httpx.Response(200, json=regular_paper)
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_paper", {"identifier": "reg1"}
            )
    data = json.loads(result.content[0].text)
    assert "book_metadata" not in data
```

- [ ] **Step 2: Run integration tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_book_enrichment_integration.py -v`
Expected: FAIL — `get_paper` does not call enrichment yet.

- [ ] **Step 3: Hook enrichment into `get_paper` in `_tools_search.py`**

In `src/scholar_mcp/_tools_search.py`:

Add import at top (after line 14):
```python
from ._book_enrichment import enrich_books
```

In the `get_paper` tool's `_execute` function, add enrichment after caching the paper and before `return json.dumps(fetched)` (around line 160). Replace:
```python
            return json.dumps(fetched)
```
with:
```python
            await enrich_books([fetched], bundle)
            return json.dumps(fetched)
```

Also enrich cached results — replace the cache hit return (line 139):
```python
            return json.dumps(data)
```
with:
```python
            await enrich_books([data], bundle)
            return json.dumps(data)
```

- [ ] **Step 4: Run integration tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest tests/test_book_enrichment_integration.py -v`
Expected: All tests PASSED

- [ ] **Step 5: Hook enrichment into `get_citations` in `_tools_graph.py`**

In `src/scholar_mcp/_tools_graph.py`:

Add import at top (after line 14):
```python
from ._book_enrichment import enrich_books
```

In the `get_citations` tool's `_execute` function, enrich papers before returning. In the filtering branch (around line 144), before `return json.dumps(result)`, extract the papers and enrich:

After line 144 (`result: dict[str, object] = {"data": filtered[offset : offset + limit]}`), insert:
```python
                papers = [
                    item.get("citingPaper", {})
                    for item in result["data"]  # type: ignore[union-attr]
                    if item.get("citingPaper")
                ]
                await enrich_books(papers, bundle)
```

In the non-filtering branch (around line 176), before `return json.dumps(result)`, insert:
```python
            papers = [
                item.get("citingPaper", {})
                for item in result.get("data") or []
                if item.get("citingPaper")
            ]
            await enrich_books(papers, bundle)
```

- [ ] **Step 6: Hook enrichment into `get_references` in `_tools_graph.py`**

In the `get_references` tool's `_execute` function (around line 227), before `return json.dumps(result)`, insert:
```python
            papers = [
                item.get("citedPaper", {})
                for item in result.get("data") or []
                if item.get("citedPaper")
            ]
            await enrich_books(papers, bundle)
```

- [ ] **Step 7: Hook enrichment into `get_citation_graph` in `_tools_graph.py`**

In the `get_citation_graph` tool's `_execute` function, after constructing `node_list` (line 462), insert before the `return json.dumps(...)`:
```python
            await enrich_books(node_list, bundle)
```

Note: `node_list` contains compact dicts (id, title, year, citationCount), which typically won't have `externalIds.ISBN`. The enrichment will skip them naturally. This hook is here for completeness in case the graph is later expanded to return full paper records.

- [ ] **Step 8: Run full test suite**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest --timeout=30 -x -q`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/scholar_mcp/_tools_search.py src/scholar_mcp/_tools_graph.py tests/test_book_enrichment_integration.py
git commit -m "feat: hook book enrichment into get_paper, get_citations, get_references, get_citation_graph"
```

---

## Task 7: Documentation and Future Issues

**Files:**
- Modify: `docs/tools/index.md`
- Modify: `README.md`

- [ ] **Step 1: Update tool documentation**

Read `docs/tools/index.md` and `README.md` to understand their current structure, then add documentation for the two new tools (`search_books`, `get_book`) and the auto-enrichment behavior following the existing patterns.

Document:
- `search_books` — parameters, return format, examples
- `get_book` — parameters, identifier formats, return format
- Auto-enrichment — when it triggers, what `book_metadata` contains
- Open Library as data source (no API key needed)

- [ ] **Step 2: Commit documentation**

```bash
git add docs/ README.md
git commit -m "docs: add book support tool documentation"
```

- [ ] **Step 3: Create GitHub issues for deferred work**

Create 10 GitHub issues for the deferred items listed in the spec (`docs/specs/2026-04-06-book-support-design.md`, "Deferred Issues" section):

1. Google Books integration (preview links, snippets, excerpts)
2. Enrichment plugin architecture (registry/pipeline refactor)
3. Dataclass migration (papers, patents, books → typed dataclasses)
4. Chapter-level resolution (F1)
5. BibLaTeX `@book` / `@incollection` output (F2)
6. WorldCat library availability (F3)
7. CrossRef enrichment for book chapters (F4)
8. Cover image caching (F5)
9. Book recommendation via subjects (F6)
10. Patent-to-book cross-referencing (F7)

Use `gh issue create` for each. Apply labels as appropriate (e.g. `enhancement`, `good first issue` for simpler ones).

- [ ] **Step 4: Final full test suite run**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run pytest --timeout=30 -q`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `cd /mnt/code/scholar-mcp/.claude/worktrees/feat+citation-generation && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: No errors

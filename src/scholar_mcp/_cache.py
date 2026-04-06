"""SQLite-backed cache for Scholar MCP Server."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert an ISBN-10 to ISBN-13.

    Args:
        isbn10: 10-digit ISBN string (digits only, no hyphens).

    Returns:
        13-digit ISBN string.
    """
    stem = "978" + isbn10[:9]
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(stem))
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


# TTLs in seconds
_PAPER_TTL = 30 * 86400  # 30 days
_CITATION_TTL = 7 * 86400  # 7 days
_REFERENCE_TTL = 7 * 86400  # 7 days
_AUTHOR_TTL = 30 * 86400  # 30 days
_OPENALEX_TTL = 30 * 86400  # 30 days
_PATENT_TTL = 90 * 86400  # 90 days
_PATENT_CLAIMS_TTL = 180 * 86400  # 180 days
_PATENT_DESC_TTL = 180 * 86400  # 180 days
_PATENT_FAMILY_TTL = 90 * 86400  # 90 days
_PATENT_LEGAL_TTL = 7 * 86400  # 7 days
_PATENT_CITATIONS_TTL = 90 * 86400  # 90 days
_PATENT_SEARCH_TTL = 7 * 86400  # 7 days
_BOOK_ISBN_TTL = 30 * 86400  # 30 days
_BOOK_WORK_TTL = 30 * 86400  # 30 days
_BOOK_SEARCH_TTL = 7 * 86400  # 7 days

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);

CREATE TABLE IF NOT EXISTS papers (
    paper_id  TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_cached_at ON papers (cached_at);

CREATE TABLE IF NOT EXISTS citations (
    paper_id   TEXT PRIMARY KEY,
    citing_ids TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_cached_at ON citations (cached_at);

CREATE TABLE IF NOT EXISTS refs (
    paper_id       TEXT PRIMARY KEY,
    referenced_ids TEXT NOT NULL,
    cached_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refs_cached_at ON refs (cached_at);

CREATE TABLE IF NOT EXISTS authors (
    author_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_authors_cached_at ON authors (cached_at);

CREATE TABLE IF NOT EXISTS openalex (
    doi       TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_openalex_cached_at ON openalex (cached_at);

CREATE TABLE IF NOT EXISTS id_aliases (
    raw_id      TEXT PRIMARY KEY,
    s2_paper_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patents (
    patent_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patents_cached ON patents(cached_at);

CREATE TABLE IF NOT EXISTS patent_claims (
    patent_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_claims_cached ON patent_claims(cached_at);

CREATE TABLE IF NOT EXISTS patent_descriptions (
    patent_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_desc_cached ON patent_descriptions(cached_at);

CREATE TABLE IF NOT EXISTS patent_families (
    patent_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_families_cached ON patent_families(cached_at);

CREATE TABLE IF NOT EXISTS patent_legal (
    patent_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_legal_cached ON patent_legal(cached_at);

CREATE TABLE IF NOT EXISTS patent_citations (
    patent_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_citations_cached ON patent_citations(cached_at);

CREATE TABLE IF NOT EXISTS patent_search (
    query_hash TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_search_cached ON patent_search(cached_at);

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
"""

_TTL_TABLES = (
    "papers",
    "citations",
    "refs",
    "authors",
    "openalex",
    "patents",
    "patent_claims",
    "patent_descriptions",
    "patent_families",
    "patent_legal",
    "patent_citations",
    "patent_search",
    "books_isbn",
    "books_openlibrary",
    "books_search",
)


def _require_open(db: aiosqlite.Connection | None) -> aiosqlite.Connection:
    """Return *db* or raise RuntimeError if not open.

    Args:
        db: Database connection or None.

    Returns:
        The open database connection.

    Raises:
        RuntimeError: If *db* is None (cache not opened yet).
    """
    if db is None:
        raise RuntimeError("Cache not open — call await cache.open() first")
    return db


class ScholarCache:
    """Async SQLite cache with TTL-based expiry.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open database connection and apply schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("cache_opened path=%s", self._db_path)

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Papers
    # ------------------------------------------------------------------

    async def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        """Return cached paper data or None if missing/stale.

        Args:
            paper_id: S2 paper ID.

        Returns:
            Paper dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM papers WHERE paper_id = ?", (paper_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if time.time() - row[1] > _PAPER_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_paper(self, paper_id: str, data: dict[str, Any]) -> None:
        """Cache paper data.

        Args:
            paper_id: S2 paper ID.
            data: Paper metadata dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO papers (paper_id, data, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Citations (list of citing paper IDs)
    # ------------------------------------------------------------------

    async def get_citations(self, paper_id: str) -> list[str] | None:
        """Return cached list of citing paper IDs or None if missing/stale.

        Args:
            paper_id: S2 paper ID.

        Returns:
            List of citing paper IDs or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT citing_ids, cached_at FROM citations WHERE paper_id = ?",
            (paper_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _CITATION_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_citations(self, paper_id: str, ids: list[str]) -> None:
        """Cache list of citing paper IDs.

        Args:
            paper_id: S2 paper ID.
            ids: List of citing paper IDs.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO citations (paper_id, citing_ids, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(ids), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # References (list of referenced paper IDs)
    # ------------------------------------------------------------------

    async def get_references(self, paper_id: str) -> list[str] | None:
        """Return cached list of referenced paper IDs or None if missing/stale.

        Args:
            paper_id: S2 paper ID.

        Returns:
            List of referenced paper IDs or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT referenced_ids, cached_at FROM refs WHERE paper_id = ?", (paper_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _REFERENCE_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_references(self, paper_id: str, ids: list[str]) -> None:
        """Cache list of referenced paper IDs.

        Args:
            paper_id: S2 paper ID.
            ids: List of referenced paper IDs.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO refs (paper_id, referenced_ids, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(ids), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Authors
    # ------------------------------------------------------------------

    async def get_author(self, author_id: str) -> dict[str, Any] | None:
        """Return cached author data or None if missing/stale.

        Args:
            author_id: S2 author ID.

        Returns:
            Author dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM authors WHERE author_id = ?", (author_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _AUTHOR_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_author(self, author_id: str, data: dict[str, Any]) -> None:
        """Cache author data.

        Args:
            author_id: S2 author ID.
            data: Author metadata dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO authors (author_id, data, cached_at) VALUES (?, ?, ?)",
            (author_id, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # OpenAlex enrichment
    # ------------------------------------------------------------------

    async def get_openalex(self, doi: str) -> dict[str, Any] | None:
        """Return cached OpenAlex data for a DOI or None if missing/stale.

        Args:
            doi: DOI string.

        Returns:
            OpenAlex work dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM openalex WHERE doi = ?", (doi,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _OPENALEX_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_openalex(self, doi: str, data: dict[str, Any]) -> None:
        """Cache OpenAlex enrichment data for a DOI.

        Args:
            doi: DOI string.
            data: OpenAlex work dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO openalex (doi, data, cached_at) VALUES (?, ?, ?)",
            (doi, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Identifier aliases (no TTL)
    # ------------------------------------------------------------------

    async def get_alias(self, raw_id: str) -> str | None:
        """Return the S2 paper ID for a raw identifier, or None if unknown.

        Args:
            raw_id: Raw identifier (e.g. ``DOI:10.1/test``, ``ARXIV:2401.0001``).

        Returns:
            S2 paper ID or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT s2_paper_id FROM id_aliases WHERE raw_id = ?", (raw_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def set_alias(self, raw_id: str, s2_paper_id: str) -> None:
        """Map a raw identifier to a canonical S2 paper ID.

        Args:
            raw_id: Raw identifier string.
            s2_paper_id: Canonical S2 paper ID.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO id_aliases (raw_id, s2_paper_id) VALUES (?, ?)",
            (raw_id, s2_paper_id),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patents
    # ------------------------------------------------------------------

    async def get_patent(self, patent_id: str) -> dict[str, Any] | None:
        """Return cached patent bibliographic data or None if missing/stale.

        Args:
            patent_id: Normalised patent ID (e.g. ``EP.1234567.A1``).

        Returns:
            Patent dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM patents WHERE patent_id = ?", (patent_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_patent(self, patent_id: str, data: dict[str, Any]) -> None:
        """Cache patent bibliographic data.

        Args:
            patent_id: Normalised patent ID.
            data: Patent metadata dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO patents (patent_id, data, cached_at) VALUES (?, ?, ?)",
            (patent_id, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patent claims
    # ------------------------------------------------------------------

    async def get_patent_claims(self, patent_id: str) -> str | None:
        """Return cached patent claims text or None if missing/stale.

        Args:
            patent_id: Normalised patent ID.

        Returns:
            Claims text or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM patent_claims WHERE patent_id = ?",
            (patent_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_CLAIMS_TTL:
            return None
        return row[0]  # type: ignore[no-any-return]

    async def set_patent_claims(self, patent_id: str, text: str) -> None:
        """Cache patent claims text.

        Args:
            patent_id: Normalised patent ID.
            text: Raw claims text.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO patent_claims (patent_id, data, cached_at) VALUES (?, ?, ?)",
            (patent_id, text, time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patent descriptions
    # ------------------------------------------------------------------

    async def get_patent_description(self, patent_id: str) -> str | None:
        """Return cached patent description text or None if missing/stale.

        Args:
            patent_id: Normalised patent ID.

        Returns:
            Description text or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM patent_descriptions WHERE patent_id = ?",
            (patent_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_DESC_TTL:
            return None
        return row[0]  # type: ignore[no-any-return]

    async def set_patent_description(self, patent_id: str, text: str) -> None:
        """Cache patent description text.

        Args:
            patent_id: Normalised patent ID.
            text: Raw description text.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO patent_descriptions (patent_id, data, cached_at) VALUES (?, ?, ?)",
            (patent_id, text, time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patent families
    # ------------------------------------------------------------------

    async def get_patent_family(self, patent_id: str) -> list[dict[str, Any]] | None:
        """Return cached patent family members or None if missing/stale.

        Args:
            patent_id: Normalised patent ID.

        Returns:
            List of family member dicts or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM patent_families WHERE patent_id = ?",
            (patent_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_FAMILY_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_patent_family(
        self, patent_id: str, data: list[dict[str, Any]]
    ) -> None:
        """Cache patent family members.

        Args:
            patent_id: Normalised patent ID.
            data: List of family member dicts.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO patent_families (patent_id, data, cached_at) VALUES (?, ?, ?)",
            (patent_id, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patent legal status
    # ------------------------------------------------------------------

    async def get_patent_legal(self, patent_id: str) -> list[dict[str, Any]] | None:
        """Return cached patent legal status events or None if missing/stale.

        Args:
            patent_id: Normalised patent ID.

        Returns:
            List of legal status event dicts or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM patent_legal WHERE patent_id = ?",
            (patent_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_LEGAL_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_patent_legal(
        self, patent_id: str, data: list[dict[str, Any]]
    ) -> None:
        """Cache patent legal status events.

        Args:
            patent_id: Normalised patent ID.
            data: List of legal status event dicts.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO patent_legal (patent_id, data, cached_at) VALUES (?, ?, ?)",
            (patent_id, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patent citations (cited references)
    # ------------------------------------------------------------------

    async def get_patent_citations(self, patent_id: str) -> dict[str, Any] | None:
        """Return cached patent citations or None if missing/stale.

        Args:
            patent_id: Normalised patent ID (e.g. ``EP.1234567.A1``).

        Returns:
            Dict with ``patent_refs`` and ``npl_refs`` keys, or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM patent_citations WHERE patent_id = ?",
            (patent_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_CITATIONS_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_patent_citations(self, patent_id: str, data: dict[str, Any]) -> None:
        """Cache patent citations (cited references).

        Args:
            patent_id: Normalised patent ID.
            data: Dict with ``patent_refs`` and ``npl_refs`` keys.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO patent_citations (patent_id, data, cached_at) VALUES (?, ?, ?)",
            (patent_id, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Patent search results
    # ------------------------------------------------------------------

    async def get_patent_search(self, query: str) -> dict[str, Any] | None:
        """Return cached patent search results or None if missing/stale.

        Args:
            query: EPO OPS query string; SHA-256 hash used as cache key.

        Returns:
            Search results dict or None.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        async with db.execute(
            "SELECT data, cached_at FROM patent_search WHERE query_hash = ?",
            (query_hash,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _PATENT_SEARCH_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_patent_search(self, query: str, data: dict[str, Any]) -> None:
        """Cache patent search results.

        Args:
            query: EPO OPS query string; SHA-256 hash used as cache key.
            data: Search results dict.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        await db.execute(
            "INSERT OR REPLACE INTO patent_search (query_hash, data, cached_at) VALUES (?, ?, ?)",
            (query_hash, json.dumps(data), time.time()),
        )
        await db.commit()

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

    async def set_book_search(self, query: str, data: list[dict[str, Any]]) -> None:
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

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def stats(self) -> dict[str, int]:
        """Return row counts and file size for all TTL tables.

        Returns:
            Dict with keys: papers, citations, refs, authors, openalex,
            db_size_bytes.
        """
        db = _require_open(self._db)
        counts: dict[str, int] = {}
        for table in _TTL_TABLES:
            async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                row = await cur.fetchone()
                counts[table] = row[0] if row else 0
        counts["db_size_bytes"] = (
            self._db_path.stat().st_size if self._db_path.exists() else 0
        )
        return counts

    async def clear(self, older_than_days: int | None = None) -> None:
        """Clear cache entries.

        Args:
            older_than_days: If set, only evict entries older than this many
                days. If None, wipes all entries in all TTL-bearing tables.
        """
        db = _require_open(self._db)
        if older_than_days is None:
            for table in _TTL_TABLES:
                await db.execute(f"DELETE FROM {table}")
        else:
            cutoff = time.time() - older_than_days * 86400
            for table in _TTL_TABLES:
                await db.execute(f"DELETE FROM {table} WHERE cached_at < ?", (cutoff,))
        await db.commit()
        logger.info("cache_cleared older_than_days=%s", older_than_days)

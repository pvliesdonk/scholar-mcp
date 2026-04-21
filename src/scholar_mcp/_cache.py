"""SQLite-backed cache for Scholar MCP Server."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

from ._record_types import (
    BookRecord,  # noqa: TC001 — runtime import needed for get_type_hints()
    StandardRecord,  # noqa: TC001 — runtime import needed for get_type_hints()
)

logger = logging.getLogger(__name__)


def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert an ISBN-10 to ISBN-13.

    ISBN-10 always maps to the 978 EAN prefix. The 979 prefix only
    exists as native ISBN-13 (no ISBN-10 equivalent).

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
    if (
        len(cleaned) == 10
        and cleaned[:9].isdigit()
        and (cleaned[9].isdigit() or cleaned[9].upper() == "X")
    ):
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
_BOOK_SUBJECT_TTL = 7 * 86400  # 7 days

_CROSSREF_TTL = 30 * 86400  # 30 days
_GOOGLE_BOOKS_TTL = 30 * 86400  # 30 days

_STANDARD_TTL = 90 * 86400  # 90 days — standards rarely change
_STANDARD_ALIAS_TTL = 90 * 86400  # 90 days
_STANDARD_SEARCH_TTL = 30 * 86400  # 30 days — standards are effectively append-only
_STANDARD_INDEX_TTL = 30 * 86400  # 30 days — re-scrape monthly

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (2);

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

CREATE TABLE IF NOT EXISTS books_subject (
    query_hash TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_subject_cached ON books_subject(cached_at);

CREATE TABLE IF NOT EXISTS crossref (
    doi       TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crossref_cached ON crossref(cached_at);

CREATE TABLE IF NOT EXISTS google_books (
    isbn      TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_google_books_cached ON google_books(cached_at);

CREATE TABLE IF NOT EXISTS standards (
    identifier TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL,
    source     TEXT,
    synced_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_standards_cached ON standards(cached_at);
-- idx_standards_source is created by _apply_migrations so v1 DBs (which
-- lack the source column until ALTER TABLE runs) don't break on open.

CREATE TABLE IF NOT EXISTS standards_aliases (
    raw_id     TEXT PRIMARY KEY,
    canonical  TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_aliases_cached ON standards_aliases(cached_at);

CREATE TABLE IF NOT EXISTS standards_search (
    query_hash TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_search_cached ON standards_search(cached_at);

CREATE TABLE IF NOT EXISTS standards_index (
    body      TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_index_cached ON standards_index(cached_at);

CREATE TABLE IF NOT EXISTS standards_sync_runs (
    body          TEXT PRIMARY KEY,
    upstream_ref  TEXT,
    added         INTEGER NOT NULL,
    updated       INTEGER NOT NULL,
    unchanged     INTEGER NOT NULL,
    withdrawn     INTEGER NOT NULL,
    errors        TEXT NOT NULL,
    started_at    REAL NOT NULL,
    finished_at   REAL NOT NULL
);
"""


async def _apply_migrations(db: aiosqlite.Connection) -> None:
    """Apply column migrations not covered by CREATE TABLE IF NOT EXISTS.

    Idempotent — safe to run on fresh or already-migrated DBs.
    """
    async with db.execute("PRAGMA table_info(standards)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "source" not in cols:
        await db.execute("ALTER TABLE standards ADD COLUMN source TEXT")
    if "synced_at" not in cols:
        await db.execute("ALTER TABLE standards ADD COLUMN synced_at REAL")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_standards_source ON standards(source)"
    )
    await db.execute("INSERT OR IGNORE INTO schema_version VALUES (2)")
    await db.commit()


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
    "books_subject",
    "crossref",
    "google_books",
    "standards",
    "standards_aliases",
    "standards_search",
    "standards_index",
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
        await _apply_migrations(self._db)
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

    async def get_book_by_isbn(self, isbn: str) -> BookRecord | None:
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

    async def set_book_by_isbn(self, isbn: str, data: BookRecord) -> None:
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

    async def get_book_by_work(self, work_id: str) -> BookRecord | None:
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

    async def set_book_by_work(self, work_id: str, data: BookRecord) -> None:
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

    async def get_book_search(self, query: str) -> list[BookRecord] | None:
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

    async def set_book_search(self, query: str, data: list[BookRecord]) -> None:
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

    async def get_book_subject(self, cache_key: str) -> list[BookRecord] | None:
        """Return cached book subject results or None if missing/stale.

        Args:
            cache_key: Subject slug used as the cache key.

        Returns:
            List of BookRecord dicts or None.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(cache_key.encode()).hexdigest()
        async with db.execute(
            "SELECT data, cached_at FROM books_subject WHERE query_hash = ?",
            (query_hash,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _BOOK_SUBJECT_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_book_subject(self, cache_key: str, data: list[BookRecord]) -> None:
        """Cache book subject results.

        Args:
            cache_key: Subject slug used as the cache key.
            data: List of BookRecord dicts.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(cache_key.encode()).hexdigest()
        await db.execute(
            "INSERT OR REPLACE INTO books_subject (query_hash, data, cached_at) VALUES (?, ?, ?)",
            (query_hash, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # CrossRef
    # ------------------------------------------------------------------

    async def get_crossref(self, doi: str) -> dict[str, Any] | None:
        """Return cached CrossRef data for a DOI or None if missing/stale.

        Args:
            doi: DOI string.

        Returns:
            CrossRef message dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM crossref WHERE doi = ?", (doi,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _CROSSREF_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_crossref(self, doi: str, data: dict[str, Any]) -> None:
        """Cache CrossRef data for a DOI.

        Args:
            doi: DOI string.
            data: CrossRef message dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO crossref (doi, data, cached_at) VALUES (?, ?, ?)",
            (doi, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Google Books
    # ------------------------------------------------------------------

    async def get_google_books(self, isbn: str) -> dict[str, Any] | None:
        """Return cached Google Books data for an ISBN or None if missing/stale.

        Args:
            isbn: ISBN string.

        Returns:
            Google Books volume dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM google_books WHERE isbn = ?", (isbn,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _GOOGLE_BOOKS_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_google_books(self, isbn: str, data: dict[str, Any]) -> None:
        """Cache Google Books data for an ISBN.

        Args:
            isbn: ISBN string.
            data: Google Books volume dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO google_books (isbn, data, cached_at) VALUES (?, ?, ?)",
            (isbn, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Standards
    # ------------------------------------------------------------------

    async def get_standard(self, identifier: str) -> StandardRecord | None:
        """Return cached standard record or None if missing.

        Synced records (``synced_at IS NOT NULL``) bypass TTL — they're
        refreshed only by a subsequent sync. Live-fetched records expire
        after ``_STANDARD_TTL`` seconds.

        Args:
            identifier: Canonical standard identifier.

        Returns:
            StandardRecord dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at, synced_at FROM standards WHERE identifier = ?",
            (identifier,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        synced_at = row[2]
        if synced_at is None and time.time() - row[1] > _STANDARD_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_standard(
        self,
        identifier: str,
        data: StandardRecord,
        *,
        source: str | None = None,
        synced: bool = False,
    ) -> None:
        """Cache a standard record.

        Args:
            identifier: Canonical standard identifier.
            data: StandardRecord dict.
            source: Populating body — one of "IETF", "NIST", "W3C", "ETSI",
                "ISO", "IEC", "IEEE", "CEN", "CENELEC", "CC". ``None`` for
                legacy call sites that have not been updated yet.
            synced: When True, marks ``synced_at=now``. Synced records never
                TTL-expire. Live-fetched callers must leave this False.
        """
        db = _require_open(self._db)
        now = time.time()
        synced_at = now if synced else None
        await db.execute(
            "INSERT OR REPLACE INTO standards "
            "(identifier, data, cached_at, source, synced_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (identifier, json.dumps(data), now, source, synced_at),
        )
        await db.commit()

    async def list_synced_standard_ids(self, source: str) -> set[str]:
        """Return identifiers of all synced standards for a given source.

        Only rows with ``synced_at IS NOT NULL`` are returned — live-fetched
        entries are excluded. Used by the sync driver to detect records that
        disappeared from the upstream dump (withdrawal detection).

        Args:
            source: Standards body key (``"ISO"``, ``"IEC"``, ``"IEEE"``, …).

        Returns:
            Set of canonical identifiers. Empty set when nothing matches.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT identifier FROM standards "
            "WHERE source = ? AND synced_at IS NOT NULL",
            (source,),
        ) as cur:
            rows = await cur.fetchall()
        return {row[0] for row in rows}

    async def search_synced_standards(
        self,
        query: str,
        *,
        source: str | None = None,
        limit: int = 10,
    ) -> list[StandardRecord]:
        """Full-text search over synced standards using SQL LIKE.

        Searches the ``identifier`` and ``title`` fields of all synced rows
        (``synced_at IS NOT NULL``). Case-insensitive on ASCII because SQLite
        LIKE is case-insensitive for ASCII by default.

        Args:
            query: Substring to match against the identifier column and the
                title field (via json_extract). ``%`` and ``_`` in the query
                are treated as literals, not LIKE wildcards.
            source: Optional body filter (``"ISO"``, ``"IEC"``, …). Pass
                ``None`` to search all synced bodies.
            limit: Maximum number of results.

        Returns:
            List of matching ``StandardRecord`` dicts.
        """
        db = _require_open(self._db)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        where = ["synced_at IS NOT NULL"]
        params: list[object] = []
        if source is not None:
            where.append("source = ?")
            params.append(source)
        where.append(
            "(identifier LIKE ? ESCAPE '\\' "
            "OR json_extract(data, '$.title') LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, limit])
        sql = "SELECT data FROM standards WHERE " + " AND ".join(where) + " LIMIT ?"
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [json.loads(row[0]) for row in rows]

    async def get_standard_alias(self, raw: str) -> str | None:
        """Return canonical identifier for a raw alias string, or None.

        Args:
            raw: Raw alias string (e.g. ``"rfc9000"``).

        Returns:
            Canonical identifier string or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT canonical, cached_at FROM standards_aliases WHERE raw_id = ?",
            (raw,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _STANDARD_ALIAS_TTL:
            return None
        return row[0]  # type: ignore[no-any-return]

    async def set_standard_alias(self, raw: str, canonical: str) -> None:
        """Cache a raw-to-canonical alias mapping.

        Args:
            raw: Raw alias string.
            canonical: Canonical identifier.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO standards_aliases (raw_id, canonical, cached_at) VALUES (?, ?, ?)",
            (raw, canonical, time.time()),
        )
        await db.commit()

    async def set_standards_batch(
        self,
        records: list[tuple[str, StandardRecord]],
        *,
        source: str | None = None,
        synced: bool = False,
    ) -> None:
        """Insert or replace a batch of standard records in a single transaction.

        Dramatically faster than calling :meth:`set_standard` in a loop because
        it performs a single ``db.commit()`` for the entire batch instead of one
        commit per record.

        Args:
            records: List of ``(identifier, StandardRecord)`` pairs.
            source: Standards body key (e.g. ``"ISO"``, ``"IEC"``).
            synced: When True, marks ``synced_at=now`` on every row.
        """
        if not records:
            return
        db = _require_open(self._db)
        now = time.time()
        synced_at = now if synced else None
        await db.executemany(
            "INSERT OR REPLACE INTO standards "
            "(identifier, data, cached_at, source, synced_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                (ident, json.dumps(data), now, source, synced_at)
                for ident, data in records
            ),
        )
        await db.commit()

    async def set_standard_aliases_batch(
        self,
        aliases: list[tuple[str, str]],
    ) -> None:
        """Insert or replace a batch of alias mappings in a single transaction.

        Args:
            aliases: List of ``(raw_id, canonical)`` pairs.
        """
        if not aliases:
            return
        db = _require_open(self._db)
        now = time.time()
        await db.executemany(
            "INSERT OR REPLACE INTO standards_aliases "
            "(raw_id, canonical, cached_at) VALUES (?, ?, ?)",
            ((raw, canonical, now) for raw, canonical in aliases),
        )
        await db.commit()

    async def get_standards_search(self, query: str) -> list[StandardRecord] | None:
        """Return cached standards search results or None if missing/stale.

        Args:
            query: Search query string; SHA-256 hash used as cache key.

        Returns:
            List of StandardRecord dicts or None.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        async with db.execute(
            "SELECT data, cached_at FROM standards_search WHERE query_hash = ?",
            (query_hash,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _STANDARD_SEARCH_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_standards_search(
        self, query: str, data: list[StandardRecord]
    ) -> None:
        """Cache standards search results.

        Args:
            query: Search query string.
            data: List of StandardRecord dicts.
        """
        db = _require_open(self._db)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        await db.execute(
            "INSERT OR REPLACE INTO standards_search (query_hash, data, cached_at) VALUES (?, ?, ?)",
            (query_hash, json.dumps(data), time.time()),
        )
        await db.commit()

    async def get_standards_index(self, body: str) -> list[dict[str, Any]] | None:
        """Return cached standards catalogue index for a body, or None if stale.

        Args:
            body: Standards body name (e.g. ``"ETSI"``).

        Returns:
            List of stub dicts (identifier, title, url) or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM standards_index WHERE body = ?", (body,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _STANDARD_INDEX_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_standards_index(self, body: str, data: list[dict[str, Any]]) -> None:
        """Cache a standards catalogue index for a body.

        Args:
            body: Standards body name.
            data: List of stub dicts (identifier, title, url).
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO standards_index (body, data, cached_at) VALUES (?, ?, ?)",
            (body, json.dumps(data), time.time()),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # Standards sync runs
    # ------------------------------------------------------------------

    async def set_sync_run(
        self,
        *,
        body: str,
        upstream_ref: str | None,
        added: int,
        updated: int,
        unchanged: int,
        withdrawn: int,
        errors: list[str],
        started_at: float,
        finished_at: float,
    ) -> None:
        """Record (or replace) the latest sync run for *body*.

        Args:
            body: Standards body key (e.g. ``"ISO"``).
            upstream_ref: Commit SHA, ``Last-Modified``, or similar marker
                indicating what upstream version was synced.
            added: Number of new records.
            updated: Number of records that changed.
            unchanged: Number of records unchanged since last sync.
            withdrawn: Number of records marked withdrawn.
            errors: Non-fatal error strings encountered this run.
            started_at: Unix timestamp (seconds) when the run started.
            finished_at: Unix timestamp (seconds) when the run finished.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO standards_sync_runs ("
            "body, upstream_ref, added, updated, unchanged, "
            "withdrawn, errors, started_at, finished_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body,
                upstream_ref,
                added,
                updated,
                unchanged,
                withdrawn,
                json.dumps(errors),
                started_at,
                finished_at,
            ),
        )
        await db.commit()

    async def get_sync_run(self, body: str) -> dict[str, Any] | None:
        """Return the last sync run record for *body*, or None.

        Args:
            body: Standards body key.

        Returns:
            Dict with keys ``body``, ``upstream_ref``, ``added``,
            ``updated``, ``unchanged``, ``withdrawn``, ``errors``,
            ``started_at``, ``finished_at``.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT body, upstream_ref, added, updated, unchanged, "
            "withdrawn, errors, started_at, finished_at "
            "FROM standards_sync_runs WHERE body = ?",
            (body,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return {
            "body": row[0],
            "upstream_ref": row[1],
            "added": row[2],
            "updated": row[3],
            "unchanged": row[4],
            "withdrawn": row[5],
            "errors": json.loads(row[6]),
            "started_at": row[7],
            "finished_at": row[8],
        }

    async def list_sync_runs(self) -> list[dict[str, Any]]:
        """Return every recorded sync run, one per body.

        Returns:
            List of dicts with the same shape as :meth:`get_sync_run`.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT body, upstream_ref, added, updated, unchanged, "
            "withdrawn, errors, started_at, finished_at "
            "FROM standards_sync_runs ORDER BY body"
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "body": r[0],
                "upstream_ref": r[1],
                "added": r[2],
                "updated": r[3],
                "unchanged": r[4],
                "withdrawn": r[5],
                "errors": json.loads(r[6]),
                "started_at": r[7],
                "finished_at": r[8],
            }
            for r in rows
        ]

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

"""SQLite-backed cache for Scholar MCP Server."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# TTLs in seconds
_PAPER_TTL = 30 * 86400       # 30 days
_CITATION_TTL = 7 * 86400     # 7 days
_REFERENCE_TTL = 7 * 86400    # 7 days
_AUTHOR_TTL = 30 * 86400      # 30 days
_OPENALEX_TTL = 30 * 86400    # 30 days

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);

CREATE TABLE IF NOT EXISTS papers (
    paper_id  TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS citation_counts (
    paper_id        TEXT PRIMARY KEY,
    citation_count  INTEGER NOT NULL,
    reference_count INTEGER NOT NULL,
    cached_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS citations (
    paper_id   TEXT PRIMARY KEY,
    citing_ids TEXT NOT NULL,
    cached_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
    paper_id       TEXT PRIMARY KEY,
    referenced_ids TEXT NOT NULL,
    cached_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS authors (
    author_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS openalex (
    doi       TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS id_aliases (
    raw_id      TEXT PRIMARY KEY,
    s2_paper_id TEXT NOT NULL
);
"""


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

    async def get_paper(self, paper_id: str) -> dict | None:
        """Return cached paper data or None if missing/stale.

        Args:
            paper_id: S2 paper ID.

        Returns:
            Paper dict or None.
        """
        assert self._db
        async with self._db.execute(
            "SELECT data, cached_at FROM papers WHERE paper_id = ?", (paper_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if time.time() - row[1] > _PAPER_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_paper(self, paper_id: str, data: dict) -> None:
        """Cache paper data.

        Args:
            paper_id: S2 paper ID.
            data: Paper metadata dict.
        """
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO papers (paper_id, data, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(data), time.time()),
        )
        await self._db.commit()

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
        assert self._db
        async with self._db.execute(
            "SELECT citing_ids, cached_at FROM citations WHERE paper_id = ?", (paper_id,)
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
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO citations (paper_id, citing_ids, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(ids), time.time()),
        )
        await self._db.commit()

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
        assert self._db
        async with self._db.execute(
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
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO refs (paper_id, referenced_ids, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(ids), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Authors
    # ------------------------------------------------------------------

    async def get_author(self, author_id: str) -> dict | None:
        """Return cached author data or None if missing/stale.

        Args:
            author_id: S2 author ID.

        Returns:
            Author dict or None.
        """
        assert self._db
        async with self._db.execute(
            "SELECT data, cached_at FROM authors WHERE author_id = ?", (author_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _AUTHOR_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_author(self, author_id: str, data: dict) -> None:
        """Cache author data.

        Args:
            author_id: S2 author ID.
            data: Author metadata dict.
        """
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO authors (author_id, data, cached_at) VALUES (?, ?, ?)",
            (author_id, json.dumps(data), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # OpenAlex enrichment
    # ------------------------------------------------------------------

    async def get_openalex(self, doi: str) -> dict | None:
        """Return cached OpenAlex data for a DOI or None if missing/stale.

        Args:
            doi: DOI string.

        Returns:
            OpenAlex work dict or None.
        """
        assert self._db
        async with self._db.execute(
            "SELECT data, cached_at FROM openalex WHERE doi = ?", (doi,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _OPENALEX_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_openalex(self, doi: str, data: dict) -> None:
        """Cache OpenAlex enrichment data for a DOI.

        Args:
            doi: DOI string.
            data: OpenAlex work dict.
        """
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO openalex (doi, data, cached_at) VALUES (?, ?, ?)",
            (doi, json.dumps(data), time.time()),
        )
        await self._db.commit()

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
        assert self._db
        async with self._db.execute(
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
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO id_aliases (raw_id, s2_paper_id) VALUES (?, ?)",
            (raw_id, s2_paper_id),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def stats(self) -> dict:
        """Return row counts and file size for all tables.

        Returns:
            Dict with keys: papers, citations, refs, authors, openalex,
            id_aliases, db_size_bytes.
        """
        assert self._db
        counts: dict[str, int] = {}
        for table in ("papers", "citation_counts", "citations", "refs", "authors", "openalex"):
            async with self._db.execute(f"SELECT COUNT(*) FROM {table}") as cur:  # noqa: S608
                row = await cur.fetchone()
                counts[table] = row[0] if row else 0
        counts["db_size_bytes"] = self._db_path.stat().st_size if self._db_path.exists() else 0
        return counts

    async def clear(self, older_than_days: int | None = None) -> None:
        """Clear cache entries.

        Args:
            older_than_days: If set, only evict entries older than this many
                days. If None, wipes all entries in all TTL-bearing tables.
        """
        assert self._db
        if older_than_days is None:
            for table in ("papers", "citation_counts", "citations", "refs", "authors", "openalex"):
                await self._db.execute(f"DELETE FROM {table}")  # noqa: S608
        else:
            cutoff = time.time() - older_than_days * 86400
            for table in ("papers", "citation_counts", "citations", "refs", "authors", "openalex"):
                await self._db.execute(  # noqa: S608
                    f"DELETE FROM {table} WHERE cached_at < ?", (cutoff,)
                )
        await self._db.commit()
        logger.info("cache_cleared older_than_days=%s", older_than_days)

"""Tests for standards cache tables."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiosqlite
import pytest

from scholar_mcp import _cache as _cache_mod
from scholar_mcp._cache import ScholarCache
from scholar_mcp._record_types import StandardRecord

SAMPLE_STANDARD: dict[str, Any] = {
    "identifier": "RFC 9000",
    "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
    "body": "IETF",
    "number": "9000",
    "status": "published",
    "full_text_available": True,
    "url": "https://www.rfc-editor.org/rfc/rfc9000",
}


async def test_get_standard_miss(cache: ScholarCache) -> None:
    result = await cache.get_standard("RFC 9000")
    assert result is None


async def test_set_and_get_standard(cache: ScholarCache) -> None:
    await cache.set_standard("RFC 9000", SAMPLE_STANDARD)
    result = await cache.get_standard("RFC 9000")
    assert result is not None
    assert result["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"


async def test_get_standard_alias_miss(cache: ScholarCache) -> None:
    result = await cache.get_standard_alias("rfc9000")
    assert result is None


async def test_set_and_get_standard_alias(cache: ScholarCache) -> None:
    await cache.set_standard_alias("rfc9000", "RFC 9000")
    result = await cache.get_standard_alias("rfc9000")
    assert result == "RFC 9000"


async def test_get_standards_search_miss(cache: ScholarCache) -> None:
    result = await cache.get_standards_search("quic transport")
    assert result is None


async def test_set_and_get_standards_search(cache: ScholarCache) -> None:
    await cache.set_standards_search("quic transport", [SAMPLE_STANDARD])
    result = await cache.get_standards_search("quic transport")
    assert result is not None
    assert len(result) == 1
    assert result[0]["identifier"] == "RFC 9000"


async def test_get_standards_index_miss(cache: ScholarCache) -> None:
    result = await cache.get_standards_index("ETSI")
    assert result is None


async def test_set_and_get_standards_index(cache: ScholarCache) -> None:
    stubs = [
        {
            "identifier": "ETSI EN 303 645",
            "title": "IoT Cyber Security",
            "url": "https://etsi.org",
        }
    ]
    await cache.set_standards_index("ETSI", stubs)
    result = await cache.get_standards_index("ETSI")
    assert result is not None
    assert result[0]["identifier"] == "ETSI EN 303 645"


async def test_get_standard_expired(cache: ScholarCache) -> None:
    await cache.set_standard("RFC 9000", SAMPLE_STANDARD)
    future = time.time() + 91 * 86400
    with patch("scholar_mcp._cache.time") as mock_time:
        mock_time.time.return_value = future
        result = await cache.get_standard("RFC 9000")
    assert result is None


def test_standard_search_ttl_is_30_days() -> None:
    assert _cache_mod._STANDARD_SEARCH_TTL == 30 * 86400


def test_standard_index_ttl_is_30_days() -> None:
    assert _cache_mod._STANDARD_INDEX_TTL == 30 * 86400


async def test_standards_table_has_source_column(cache: ScholarCache) -> None:
    async with (
        aiosqlite.connect(cache._db_path) as db,  # type: ignore[attr-defined]
        db.execute("PRAGMA table_info(standards)") as cur,
    ):
        cols = {row[1] for row in await cur.fetchall()}
    assert "source" in cols
    assert "synced_at" in cols


async def test_schema_version_is_2(cache: ScholarCache) -> None:
    async with (
        aiosqlite.connect(cache._db_path) as db,  # type: ignore[attr-defined]
        db.execute("SELECT MAX(version) FROM schema_version") as cur,
    ):
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == 2


async def test_migration_adds_source_and_synced_at_to_v1_db(tmp_path: Any) -> None:
    """Opening a v1 cache (no source/synced_at columns) triggers ALTER TABLE."""
    db_path = tmp_path / "v1.db"
    # Hand-roll a v1 standards table without source/synced_at.
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
            INSERT INTO schema_version VALUES (1);
            CREATE TABLE standards (
                identifier TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                cached_at  REAL NOT NULL
            );
            """
        )
        await db.commit()

    # Now open via ScholarCache — should run _apply_migrations.
    c = ScholarCache(db_path)
    await c.open()
    try:
        async with (
            aiosqlite.connect(c._db_path) as db,  # type: ignore[attr-defined]
            db.execute("PRAGMA table_info(standards)") as cur,
        ):
            cols = {row[1] for row in await cur.fetchall()}
        assert "source" in cols
        assert "synced_at" in cols
    finally:
        await c.close()


async def test_set_standard_with_source_stores_both_columns(
    cache: ScholarCache,
) -> None:
    await cache.set_standard("RFC 9000", SAMPLE_STANDARD, source="IETF")
    async with (
        aiosqlite.connect(cache._db_path) as db,  # type: ignore[attr-defined]
        db.execute(
            "SELECT source, synced_at FROM standards WHERE identifier = ?",
            ("RFC 9000",),
        ) as cur,
    ):
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "IETF"
    assert row[1] is None  # live-fetched, no synced_at


async def test_set_standard_synced_marks_synced_at(cache: ScholarCache) -> None:
    before = time.time()
    await cache.set_standard(
        "ISO 9001:2015", SAMPLE_STANDARD, source="ISO", synced=True
    )
    async with (
        aiosqlite.connect(cache._db_path) as db,  # type: ignore[attr-defined]
        db.execute(
            "SELECT synced_at FROM standards WHERE identifier = ?",
            ("ISO 9001:2015",),
        ) as cur,
    ):
        row = await cur.fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[0] >= before


async def test_get_standard_synced_ignores_ttl(cache: ScholarCache) -> None:
    """Synced records must never TTL-expire."""
    await cache.set_standard(
        "ISO 27001:2022", SAMPLE_STANDARD, source="ISO", synced=True
    )
    # Backdate cached_at beyond the 90-day TTL
    async with (
        aiosqlite.connect(cache._db_path) as db,  # type: ignore[attr-defined]
        db.execute(
            "UPDATE standards SET cached_at = ? WHERE identifier = ?",
            (time.time() - (180 * 86400), "ISO 27001:2022"),
        ) as _,
    ):
        await db.commit()
    result = await cache.get_standard("ISO 27001:2022")
    assert result is not None
    assert result["identifier"] == "RFC 9000"  # fixture body — we only care it returned


async def test_get_standard_live_respects_ttl(cache: ScholarCache) -> None:
    """Live-fetched records (no synced_at) still TTL-expire."""
    await cache.set_standard("RFC 1234", SAMPLE_STANDARD, source="IETF")
    async with (
        aiosqlite.connect(cache._db_path) as db,  # type: ignore[attr-defined]
        db.execute(
            "UPDATE standards SET cached_at = ? WHERE identifier = ?",
            (time.time() - (180 * 86400), "RFC 1234"),
        ) as _,
    ):
        await db.commit()
    result = await cache.get_standard("RFC 1234")
    assert result is None


async def test_sync_run_roundtrip(cache: ScholarCache) -> None:
    await cache.set_sync_run(
        body="ISO",
        upstream_ref="abc123",
        added=42,
        updated=3,
        unchanged=100,
        withdrawn=1,
        errors=[],
        started_at=1_000_000.0,
        finished_at=1_000_060.0,
    )
    row = await cache.get_sync_run("ISO")
    assert row is not None
    assert row["body"] == "ISO"
    assert row["upstream_ref"] == "abc123"
    assert row["added"] == 42
    assert row["updated"] == 3
    assert row["unchanged"] == 100
    assert row["withdrawn"] == 1
    assert row["errors"] == []
    assert row["started_at"] == 1_000_000.0
    assert row["finished_at"] == 1_000_060.0


async def test_sync_run_replaces_on_second_write(cache: ScholarCache) -> None:
    await cache.set_sync_run(
        body="IEC",
        upstream_ref="v1",
        added=1,
        updated=0,
        unchanged=0,
        withdrawn=0,
        errors=[],
        started_at=1.0,
        finished_at=2.0,
    )
    await cache.set_sync_run(
        body="IEC",
        upstream_ref="v2",
        added=5,
        updated=2,
        unchanged=10,
        withdrawn=0,
        errors=["one failure"],
        started_at=3.0,
        finished_at=4.0,
    )
    row = await cache.get_sync_run("IEC")
    assert row is not None
    assert row["upstream_ref"] == "v2"
    assert row["added"] == 5
    assert row["errors"] == ["one failure"]


async def test_sync_run_missing_returns_none(cache: ScholarCache) -> None:
    assert await cache.get_sync_run("IEEE") is None


async def test_list_synced_standard_ids_filters_by_source(tmp_path: Any) -> None:
    """list_synced_standard_ids returns only rows matching source filter."""

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        iso_a: StandardRecord = {"identifier": "ISO 9001:2015", "title": "A"}
        iso_b: StandardRecord = {"identifier": "ISO 14001:2015", "title": "B"}
        iec_a: StandardRecord = {"identifier": "IEC 60601-1:2020", "title": "C"}
        unsynced: StandardRecord = {"identifier": "ISO 27001:2022", "title": "D"}

        await cache.set_standard("ISO 9001:2015", iso_a, source="ISO", synced=True)
        await cache.set_standard("ISO 14001:2015", iso_b, source="ISO", synced=True)
        await cache.set_standard("IEC 60601-1:2020", iec_a, source="IEC", synced=True)
        await cache.set_standard("ISO 27001:2022", unsynced, source="ISO", synced=False)

        iso_ids = await cache.list_synced_standard_ids(source="ISO")
        iec_ids = await cache.list_synced_standard_ids(source="IEC")
    finally:
        await cache.close()

    assert iso_ids == {"ISO 9001:2015", "ISO 14001:2015"}
    assert iec_ids == {"IEC 60601-1:2020"}


async def test_list_synced_standard_ids_empty_source(tmp_path: Any) -> None:
    """Unknown source returns an empty set."""
    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        result = await cache.list_synced_standard_ids(source="IEEE")
    finally:
        await cache.close()

    assert result == set()


async def test_list_sync_runs(cache: ScholarCache) -> None:
    await cache.set_sync_run(
        body="ISO",
        upstream_ref="a",
        added=0,
        updated=0,
        unchanged=0,
        withdrawn=0,
        errors=[],
        started_at=1.0,
        finished_at=2.0,
    )
    await cache.set_sync_run(
        body="IEC",
        upstream_ref="b",
        added=0,
        updated=0,
        unchanged=0,
        withdrawn=0,
        errors=[],
        started_at=3.0,
        finished_at=4.0,
    )
    rows = await cache.list_sync_runs()
    bodies = {r["body"] for r in rows}
    assert bodies == {"ISO", "IEC"}


@pytest.mark.asyncio
async def test_search_synced_standards_by_identifier(tmp_path: Path) -> None:
    """Substring match on identifier returns synced records."""
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    record: StandardRecord = {
        "identifier": "ISO 9001:2015",
        "title": "Quality management systems",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    await cache.set_standard("ISO 9001:2015", record, source="ISO", synced=True)
    results = await cache.search_synced_standards("9001")
    await cache.close()
    assert len(results) == 1
    assert results[0]["identifier"] == "ISO 9001:2015"


@pytest.mark.asyncio
async def test_search_synced_standards_by_title(tmp_path: Path) -> None:
    """Substring match on title returns synced records."""
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    record: StandardRecord = {
        "identifier": "ISO 9001:2015",
        "title": "Quality management systems",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    await cache.set_standard("ISO 9001:2015", record, source="ISO", synced=True)
    results = await cache.search_synced_standards("Quality management")
    await cache.close()
    assert len(results) == 1
    assert results[0]["title"] == "Quality management systems"


@pytest.mark.asyncio
async def test_search_synced_standards_excludes_live_fetched(tmp_path: Path) -> None:
    """Records with synced=False (live-fetched) are excluded."""
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    record: StandardRecord = {
        "identifier": "ISO 9001:2015",
        "title": "Quality management systems",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    await cache.set_standard("ISO 9001:2015", record, source="ISO", synced=False)
    results = await cache.search_synced_standards("9001")
    await cache.close()
    assert results == []


@pytest.mark.asyncio
async def test_search_synced_standards_source_filter(tmp_path: Path) -> None:
    """source= kwarg restricts results to that body."""
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    iso_record: StandardRecord = {
        "identifier": "ISO 9001:2015",
        "title": "Quality management systems",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    iec_record: StandardRecord = {
        "identifier": "IEC 62443-3-3:2020",
        "title": "IT security for industrial systems",
        "body": "IEC",
        "status": "published",
        "full_text_available": False,
    }
    await cache.set_standard("ISO 9001:2015", iso_record, source="ISO", synced=True)
    await cache.set_standard(
        "IEC 62443-3-3:2020", iec_record, source="IEC", synced=True
    )
    iso_only = await cache.search_synced_standards("", source="ISO")
    await cache.close()
    assert all(r["body"] == "ISO" for r in iso_only)
    assert len(iso_only) == 1


@pytest.mark.asyncio
async def test_search_synced_standards_limit(tmp_path: Path) -> None:
    """limit= kwarg caps the result count."""
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    for i in range(5):
        record: StandardRecord = {
            "identifier": f"ISO 900{i}:2015",
            "title": f"Standard {i}",
            "body": "ISO",
            "status": "published",
            "full_text_available": False,
        }
        await cache.set_standard(f"ISO 900{i}:2015", record, source="ISO", synced=True)
    results = await cache.search_synced_standards("ISO", limit=3)
    await cache.close()
    assert len(results) == 3


@pytest.mark.asyncio
async def test_search_synced_standards_escapes_wildcards(tmp_path: Path) -> None:
    """Query containing LIKE wildcard chars is treated as literals."""
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    exact: StandardRecord = {
        "identifier": "ISO_001:2020",
        "title": "ISO 001 2020",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    near: StandardRecord = {
        "identifier": "ISO X001:2020",
        "title": "ISO X001 2020",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    await cache.set_standard("ISO_001:2020", exact, source="ISO", synced=True)
    await cache.set_standard("ISO X001:2020", near, source="ISO", synced=True)
    results = await cache.search_synced_standards("ISO_001")
    await cache.close()
    identifiers = [r["identifier"] for r in results]
    assert "ISO_001:2020" in identifiers
    assert "ISO X001:2020" not in identifiers

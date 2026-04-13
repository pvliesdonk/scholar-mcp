"""Tests for standards cache tables."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import aiosqlite

from scholar_mcp import _cache as _cache_mod
from scholar_mcp._cache import ScholarCache

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

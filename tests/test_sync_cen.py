"""Tests for _sync_cen — CEN/CENELEC harmonised-standards loader."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_harmonised_standards_table_not_empty() -> None:
    """Table has a substantial number of standards."""
    from scholar_mcp._sync_cen import _HARMONISED_STANDARDS

    assert len(_HARMONISED_STANDARDS) >= 50


def test_harmonised_standards_identifiers_unique() -> None:
    """No duplicate identifiers in the table."""
    from scholar_mcp._sync_cen import _HARMONISED_STANDARDS

    ids = [e.identifier for e in _HARMONISED_STANDARDS]
    assert len(ids) == len(set(ids)), (
        f"duplicates: {[x for x in ids if ids.count(x) > 1]}"
    )


def test_harmonised_standards_all_have_directive() -> None:
    """Every entry has a non-empty directive."""
    from scholar_mcp._sync_cen import _HARMONISED_STANDARDS

    for entry in _HARMONISED_STANDARDS:
        assert entry.directive, f"{entry.identifier} has empty directive"


def test_harmonised_standards_identifiers_start_with_en() -> None:
    """All identifiers start with 'EN '."""
    from scholar_mcp._sync_cen import _HARMONISED_STANDARDS

    for entry in _HARMONISED_STANDARDS:
        assert entry.identifier.startswith("EN "), (
            f"{entry.identifier} doesn't start with 'EN '"
        )


def test_hs_to_record_plain_en() -> None:
    """Plain EN standard maps to body='CEN', full_text_available=False."""
    from scholar_mcp._sync_cen import HarmonisedStandard, _hs_to_record

    entry = HarmonisedStandard(
        identifier="EN 55032:2015",
        title="Electromagnetic compatibility of multimedia equipment — Emission requirements",
        directive="EMC",
        status="harmonised",
        published_date="2015-11-13",
    )
    record = _hs_to_record(entry)

    assert record["identifier"] == "EN 55032:2015"
    assert record["body"] == "CEN"
    assert record["status"] == "harmonised"
    assert record["full_text_available"] is False
    assert record["price"] is None
    assert record["title"].startswith("Electromagnetic compatibility")
    assert record["published_date"] == "2015-11-13"


def test_hs_to_record_en_iso() -> None:
    """EN ISO identifier preserved verbatim, body still 'CEN'."""
    from scholar_mcp._sync_cen import HarmonisedStandard, _hs_to_record

    entry = HarmonisedStandard(
        identifier="EN ISO 13849-1:2023",
        title="Safety of machinery — Safety-related parts of control systems — Part 1: General principles for design",
        directive="Machinery",
        status="harmonised",
        published_date="2023-06-14",
    )
    record = _hs_to_record(entry)

    assert record["identifier"] == "EN ISO 13849-1:2023"
    assert record["body"] == "CEN"


def test_hs_to_record_withdrawn() -> None:
    """Withdrawn entry maps status correctly."""
    from scholar_mcp._sync_cen import HarmonisedStandard, _hs_to_record

    entry = HarmonisedStandard(
        identifier="EN 55022:2010",
        title="Information technology equipment — Radio disturbance characteristics",
        directive="EMC",
        status="withdrawn",
        published_date="2010-12-01",
    )
    record = _hs_to_record(entry)

    assert record["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_cen_loader_cold_sync(tmp_path: Path) -> None:
    """Cold sync writes all table records."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cen import _HARMONISED_STANDARDS, CENLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        report = await CENLoader().sync(cache)

        assert report.added == len(_HARMONISED_STANDARDS)
        assert report.body == "CEN"
        assert report.errors == []
        # Spot-check
        rec = await cache.get_standard("EN 55032:2015")
        assert rec is not None
        assert rec["body"] == "CEN"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cen_loader_resync_unchanged_short_circuits(tmp_path: Path) -> None:
    """Re-sync with same table hash returns unchanged report."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cen import CENLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        first = await CENLoader().sync(cache)
        second = await CENLoader().sync(cache)

        assert first.added > 0
        assert second.added == 0
        assert second.unchanged > 0
        assert second.upstream_ref == first.upstream_ref
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cen_loader_force_rewrites(tmp_path: Path) -> None:
    """force=True bypasses the hash gate."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cen import _HARMONISED_STANDARDS, CENLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        await CENLoader().sync(cache)
        forced = await CENLoader().sync(cache, force=True)

        # Everything counted as unchanged (content identical)
        assert forced.unchanged == len(_HARMONISED_STANDARDS)
        assert forced.added == 0
    finally:
        await cache.close()


# ---------------------------------------------------------------------------
# _normalise_en_identifier unit tests
# ---------------------------------------------------------------------------


def test_normalise_en_identifier_plain_unchanged() -> None:
    """Plain identifiers with no amendment or version are returned unchanged."""
    from scholar_mcp._sync_cen import _normalise_en_identifier

    assert _normalise_en_identifier("EN 55032:2015") == "EN 55032:2015"
    assert _normalise_en_identifier("EN ISO 13849-1:2023") == "EN ISO 13849-1:2023"
    assert _normalise_en_identifier("EN 61000-3-2:2019") == "EN 61000-3-2:2019"


def test_normalise_en_identifier_strips_amendment() -> None:
    """Amendment suffix +Ax:yyyy is stripped for cache-key consistency."""
    from scholar_mcp._sync_cen import _normalise_en_identifier

    assert _normalise_en_identifier("EN 349:1993+A1:2008") == "EN 349:1993"
    assert _normalise_en_identifier("EN 62368-1:2020+A11:2020") == "EN 62368-1:2020"
    assert _normalise_en_identifier("EN 71-1:2014+A1:2018") == "EN 71-1:2014"
    assert (
        _normalise_en_identifier("EN IEC 60601-1:2006+A1:2013") == "EN IEC 60601-1:2006"
    )
    assert _normalise_en_identifier("EN ISO 11161:2007+A1:2010") == "EN ISO 11161:2007"


def test_normalise_en_identifier_strips_version_token() -> None:
    """ETSI version token Vx.y.z is stripped for cache-key consistency."""
    from scholar_mcp._sync_cen import _normalise_en_identifier

    assert _normalise_en_identifier("EN 300 328 V2.2.2:2019") == "EN 300 328:2019"
    assert _normalise_en_identifier("EN 301 489-17 V3.2.4:2020") == "EN 301 489-17:2020"
    assert _normalise_en_identifier("EN 301 511 V12.5.1:2017") == "EN 301 511:2017"
    assert _normalise_en_identifier("EN 301 908-1 V13.1.1:2019") == "EN 301 908-1:2019"


# ---------------------------------------------------------------------------
# _hs_to_record normalisation tests
# ---------------------------------------------------------------------------


def test_hs_to_record_strips_amendment_suffix() -> None:
    """Amendment suffix +A1:2008 stripped from cache key."""
    from scholar_mcp._sync_cen import HarmonisedStandard, _hs_to_record

    entry = HarmonisedStandard(
        identifier="EN 349:1993+A1:2008",
        title="Safety of machinery — Minimum gaps",
        directive="Machinery",
    )
    record = _hs_to_record(entry)
    assert record["identifier"] == "EN 349:1993"


def test_hs_to_record_strips_version_suffix() -> None:
    """Version V2.2.2 stripped from cache key for RED entries."""
    from scholar_mcp._sync_cen import HarmonisedStandard, _hs_to_record

    entry = HarmonisedStandard(
        identifier="EN 300 328 V2.2.2:2019",
        title="Wideband data transmission — 2.4 GHz",
        directive="RED",
    )
    record = _hs_to_record(entry)
    assert record["identifier"] == "EN 300 328:2019"


@pytest.mark.asyncio
async def test_cen_loader_amendment_identifier_findable(tmp_path: Path) -> None:
    """Records with +A1:yyyy suffix are retrievable after sync."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cen import CENLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        await CENLoader().sync(cache)
        # EN 349:1993+A1:2008 in table → stored as EN 349:1993
        rec = await cache.get_standard("EN 349:1993")
        assert rec is not None, "amendment-suffix identifier not findable"
        assert rec["body"] == "CEN"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cen_loader_etsi_3part_identifier_findable(tmp_path: Path) -> None:
    """Records with ETSI 3-part numbers are retrievable after sync."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cen import CENLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        await CENLoader().sync(cache)
        # EN 300 328 V2.2.2:2019 in table → stored as EN 300 328:2019
        rec = await cache.get_standard("EN 300 328:2019")
        assert rec is not None, "3-part EN number not findable"
    finally:
        await cache.close()

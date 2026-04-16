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

"""Tests for _enricher_standards — standards auto-enrichment."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_record(title: str, **extras: Any) -> dict[str, Any]:
    """Build a minimal S2-style citation record for testing."""
    rec: dict[str, Any] = {"title": title}
    rec.update(extras)
    return rec


def test_can_enrich_short_standard_title() -> None:
    """'RFC 9000' is 100% coverage → True."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert enricher.can_enrich(_make_record("RFC 9000")) is True


def test_can_enrich_iso_standard_title() -> None:
    """'ISO 9001:2015' → True."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert enricher.can_enrich(_make_record("ISO 9001:2015")) is True


def test_can_enrich_nist_sp_title() -> None:
    """'NIST SP 800-53 Rev. 5' → True."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert enricher.can_enrich(_make_record("NIST SP 800-53 Rev. 5")) is True


def test_can_enrich_ieee_standard_title() -> None:
    """'IEEE 802.11-2020' → True."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert enricher.can_enrich(_make_record("IEEE 802.11-2020")) is True


def test_can_enrich_en_standard_title() -> None:
    """'EN 55032:2015' → True."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert enricher.can_enrich(_make_record("EN 55032:2015")) is True


def test_can_enrich_long_paper_title_about_standard() -> None:
    """A paper ABOUT a standard has <50% coverage → False."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    record = _make_record("Implementing ISO 27001 in healthcare: a systematic review")
    assert enricher.can_enrich(record) is False


def test_can_enrich_already_enriched_skips() -> None:
    """Record with standard_metadata already present → False."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    record = _make_record("RFC 9000", standard_metadata={"identifier": "RFC 9000"})
    assert enricher.can_enrich(record) is False


def test_can_enrich_empty_title() -> None:
    """Empty or missing title → False."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert enricher.can_enrich(_make_record("")) is False
    assert enricher.can_enrich({"paperId": "abc"}) is False


def test_can_enrich_no_match() -> None:
    """Non-standards title → False."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    enricher = StandardsEnricher()
    assert (
        enricher.can_enrich(_make_record("Machine learning for anomaly detection"))
        is False
    )


@pytest.mark.asyncio
async def test_enrich_attaches_standard_metadata() -> None:
    """When bundle.standards.get() returns a record, it's attached."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    standard_record = {
        "identifier": "RFC 9000",
        "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
        "body": "IETF",
        "status": "published",
        "full_text_available": True,
    }

    bundle = MagicMock()
    bundle.standards = AsyncMock()
    bundle.standards.get = AsyncMock(return_value=standard_record)

    enricher = StandardsEnricher()
    record = _make_record("RFC 9000")
    await enricher.enrich(record, bundle)

    assert record["standard_metadata"] == standard_record
    bundle.standards.get.assert_awaited_once_with("RFC 9000")


@pytest.mark.asyncio
async def test_enrich_cache_miss_no_metadata() -> None:
    """When bundle.standards.get() returns None, no field is attached."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    bundle = MagicMock()
    bundle.standards = AsyncMock()
    bundle.standards.get = AsyncMock(return_value=None)

    enricher = StandardsEnricher()
    record = _make_record("ISO 99999:2099")
    await enricher.enrich(record, bundle)

    assert "standard_metadata" not in record


@pytest.mark.asyncio
async def test_enrich_skips_when_no_match() -> None:
    """Title without standards pattern → no side effects."""
    from scholar_mcp._enricher_standards import StandardsEnricher

    bundle = MagicMock()
    bundle.standards = AsyncMock()

    enricher = StandardsEnricher()
    record = _make_record("Deep learning for image recognition")
    await enricher.enrich(record, bundle)

    assert "standard_metadata" not in record
    bundle.standards.get.assert_not_awaited()


def test_enricher_conforms_to_protocol() -> None:
    """StandardsEnricher satisfies the Enricher protocol."""
    from scholar_mcp._enricher_standards import StandardsEnricher
    from scholar_mcp._enrichment import Enricher

    enricher = StandardsEnricher()
    assert isinstance(enricher, Enricher)
    assert enricher.name == "standards"
    assert enricher.phase == 0
    assert enricher.tags == frozenset({"papers"})


def test_enricher_registered_in_pipeline() -> None:
    """StandardsEnricher appears in the pipeline's phase-0 enrichers."""
    from scholar_mcp._server_deps import _build_enrichment_pipeline

    pipeline = _build_enrichment_pipeline()
    phase_0_names = [e.name for e in pipeline._phases.get(0, [])]
    assert "standards" in phase_0_names

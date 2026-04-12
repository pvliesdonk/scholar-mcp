"""Tests for OpenAlexEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scholar_mcp._enricher_openalex import OpenAlexEnricher
from scholar_mcp._enrichment import Enricher


def _make_bundle(
    *,
    cache_hit: dict[str, Any] | None = None,
    api_result: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock ServiceBundle with configurable cache/API responses."""
    bundle = MagicMock()
    bundle.cache.get_openalex = AsyncMock(return_value=cache_hit)
    bundle.cache.set_openalex = AsyncMock()
    bundle.openalex.get_by_doi = AsyncMock(return_value=api_result)
    return bundle


def _oa_data(venue: str = "Nature") -> dict[str, Any]:
    """Return minimal OpenAlex work data with a venue."""
    return {
        "primary_location": {
            "source": {
                "display_name": venue,
            },
        },
    }


def test_satisfies_enricher_protocol() -> None:
    """OpenAlexEnricher must satisfy the runtime-checkable Enricher protocol."""
    enricher = OpenAlexEnricher()
    assert isinstance(enricher, Enricher)


def test_can_enrich_true_when_doi_and_no_venue() -> None:
    """Returns True when DOI is present and venue is empty."""
    enricher = OpenAlexEnricher()
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/test"},
        "venue": "",
    }
    assert enricher.can_enrich(record) is True


def test_can_enrich_true_when_doi_and_venue_missing() -> None:
    """Returns True when DOI is present and venue key is absent."""
    enricher = OpenAlexEnricher()
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/test"},
    }
    assert enricher.can_enrich(record) is True


def test_can_enrich_false_when_venue_present() -> None:
    """Returns False when venue already has a value."""
    enricher = OpenAlexEnricher()
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/test"},
        "venue": "Nature",
    }
    assert enricher.can_enrich(record) is False


def test_can_enrich_false_when_no_doi() -> None:
    """Returns False when externalIds has no DOI."""
    enricher = OpenAlexEnricher()
    record: dict[str, Any] = {
        "externalIds": {"S2": "abc123"},
        "venue": "",
    }
    assert enricher.can_enrich(record) is False


def test_can_enrich_false_when_no_external_ids() -> None:
    """Returns False when externalIds is missing entirely."""
    enricher = OpenAlexEnricher()
    record: dict[str, Any] = {"venue": ""}
    assert enricher.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_fills_venue_from_cache() -> None:
    """When cache has data, venue is filled and API is not called."""
    enricher = OpenAlexEnricher()
    oa = _oa_data("Science")
    bundle = _make_bundle(cache_hit=oa)
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/cached"},
        "venue": "",
    }

    await enricher.enrich(record, bundle)

    assert record["venue"] == "Science"
    bundle.cache.get_openalex.assert_awaited_once_with("10.1234/cached")
    bundle.openalex.get_by_doi.assert_not_awaited()
    bundle.cache.set_openalex.assert_not_awaited()


@pytest.mark.anyio
async def test_enrich_fills_venue_from_api() -> None:
    """When cache misses, API is called, result cached, and venue filled."""
    enricher = OpenAlexEnricher()
    oa = _oa_data("Nature")
    bundle = _make_bundle(cache_hit=None, api_result=oa)
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/fresh"},
        "venue": "",
    }

    await enricher.enrich(record, bundle)

    assert record["venue"] == "Nature"
    bundle.cache.get_openalex.assert_awaited_once_with("10.1234/fresh")
    bundle.openalex.get_by_doi.assert_awaited_once_with("10.1234/fresh")
    bundle.cache.set_openalex.assert_awaited_once_with("10.1234/fresh", oa)


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    """Exception during enrichment is swallowed; record stays unchanged."""
    enricher = OpenAlexEnricher()
    bundle = _make_bundle()
    bundle.cache.get_openalex = AsyncMock(side_effect=RuntimeError("boom"))
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/err"},
        "venue": "",
    }

    await enricher.enrich(record, bundle)

    assert record["venue"] == ""


@pytest.mark.anyio
async def test_enrich_no_venue_when_api_returns_none() -> None:
    """When API returns None, record stays unchanged."""
    enricher = OpenAlexEnricher()
    bundle = _make_bundle(cache_hit=None, api_result=None)
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/missing"},
        "venue": "",
    }

    await enricher.enrich(record, bundle)

    assert record["venue"] == ""
    bundle.cache.set_openalex.assert_not_awaited()


@pytest.mark.anyio
async def test_enrich_skips_when_no_display_name() -> None:
    """When OpenAlex data has no display_name, venue stays unchanged."""
    enricher = OpenAlexEnricher()
    oa = {"primary_location": {"source": {}}}
    bundle = _make_bundle(cache_hit=oa)
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/nosource"},
        "venue": "",
    }

    await enricher.enrich(record, bundle)

    assert record["venue"] == ""


@pytest.mark.anyio
async def test_enrich_skips_when_no_doi_in_record() -> None:
    """Defensive guard: enrich returns early when DOI is missing."""
    enricher = OpenAlexEnricher()
    bundle = _make_bundle()
    record: dict[str, Any] = {
        "externalIds": {},
        "venue": "",
    }

    await enricher.enrich(record, bundle)

    assert record["venue"] == ""
    bundle.cache.get_openalex.assert_not_awaited()

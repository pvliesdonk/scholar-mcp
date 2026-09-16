"""Tests for CrossRefEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scholar_mcp._enricher_crossref import CrossRefEnricher
from scholar_mcp._enrichment import Enricher


def _make_service(
    *,
    cache_hit: dict[str, Any] | None = None,
    api_result: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Service with configurable cache/API responses."""
    service = MagicMock()
    service.cache.get_crossref = AsyncMock(return_value=cache_hit)
    service.cache.set_crossref = AsyncMock()
    service.crossref.get_by_doi = AsyncMock(return_value=api_result)
    return service


def _cr_data() -> dict[str, Any]:
    """Return minimal CrossRef work metadata."""
    return {
        "DOI": "10.1234/test",
        "title": ["A Test Paper"],
        "type": "journal-article",
        "publisher": "Test Publisher",
    }


def test_satisfies_enricher_protocol() -> None:
    """CrossRefEnricher must satisfy the runtime-checkable Enricher protocol."""
    enricher = CrossRefEnricher()
    assert isinstance(enricher, Enricher)
    assert enricher.name == "crossref"
    assert enricher.phase == 0
    assert enricher.tags == frozenset({"papers"})


def test_can_enrich_true_when_doi_and_sparse_metadata() -> None:
    """Returns True when DOI is present and no crossref_metadata."""
    enricher = CrossRefEnricher()
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/test"},
    }
    assert enricher.can_enrich(record) is True


def test_can_enrich_false_when_no_doi() -> None:
    """Returns False when externalIds has no DOI."""
    enricher = CrossRefEnricher()
    record: dict[str, Any] = {
        "externalIds": {"S2": "abc123"},
    }
    assert enricher.can_enrich(record) is False


def test_can_enrich_false_when_crossref_already_present() -> None:
    """Returns False when crossref_metadata already exists."""
    enricher = CrossRefEnricher()
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/test"},
        "crossref_metadata": {"DOI": "10.1234/test", "type": "journal-article"},
    }
    assert enricher.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_fills_crossref_metadata_from_cache() -> None:
    """When cache has data, crossref_metadata is filled and API is not called."""
    enricher = CrossRefEnricher()
    cr = _cr_data()
    service = _make_service(cache_hit=cr)
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/cached"},
    }

    await enricher.enrich(record, service)

    assert record["crossref_metadata"] == cr
    service.cache.get_crossref.assert_awaited_once_with("10.1234/cached")
    service.crossref.get_by_doi.assert_not_awaited()
    service.cache.set_crossref.assert_not_awaited()


@pytest.mark.anyio
async def test_enrich_fills_crossref_metadata_from_api() -> None:
    """When cache misses, API is called, result cached, and metadata filled."""
    enricher = CrossRefEnricher()
    cr = _cr_data()
    service = _make_service(cache_hit=None, api_result=cr)
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/fresh"},
    }

    await enricher.enrich(record, service)

    assert record["crossref_metadata"] == cr
    service.cache.get_crossref.assert_awaited_once_with("10.1234/fresh")
    service.crossref.get_by_doi.assert_awaited_once_with("10.1234/fresh")
    service.cache.set_crossref.assert_awaited_once_with("10.1234/fresh", cr)


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    """Exception during enrichment is swallowed; record stays unchanged."""
    enricher = CrossRefEnricher()
    service = _make_service()
    service.cache.get_crossref = AsyncMock(side_effect=RuntimeError("boom"))
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/err"},
    }

    await enricher.enrich(record, service)

    assert "crossref_metadata" not in record

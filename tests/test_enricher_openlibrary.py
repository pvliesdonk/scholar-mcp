"""Tests for OpenLibraryEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholar_mcp._enricher_openlibrary import OpenLibraryEnricher
from scholar_mcp._enrichment import Enricher


def _make_bundle(
    *,
    cache_hit: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock ServiceBundle with configurable cache response."""
    bundle = MagicMock()
    bundle.cache.get_book_by_isbn = AsyncMock(return_value=cache_hit)
    bundle.cache.set_book_by_isbn = AsyncMock()
    bundle.cache.set_book_by_work = AsyncMock()
    bundle.openlibrary.get_by_isbn = AsyncMock(return_value=None)
    bundle.openlibrary.get_work = AsyncMock(return_value=None)
    bundle.openlibrary.get_author = AsyncMock(return_value=None)
    return bundle


def _book_cache_data() -> dict[str, Any]:
    """Return minimal cached book record."""
    return {
        "title": "Design Patterns",
        "publisher": "Addison-Wesley",
        "edition": None,
        "isbn_13": "9780201633610",
        "cover_url": None,
        "openlibrary_work_id": "OL1168083W",
        "description": None,
        "subjects": ["Software patterns"],
        "page_count": 395,
        "authors": ["Erich Gamma"],
    }


def test_satisfies_enricher_protocol() -> None:
    """OpenLibraryEnricher satisfies the runtime-checkable Enricher protocol."""
    enricher = OpenLibraryEnricher()
    assert isinstance(enricher, Enricher)
    assert enricher.name == "openlibrary"
    assert enricher.phase == 1
    assert enricher.tags == frozenset({"papers"})


def test_can_enrich_true_when_isbn_present() -> None:
    """Returns True when ISBN is present in externalIds."""
    enricher = OpenLibraryEnricher()
    record: dict[str, Any] = {
        "externalIds": {"ISBN": "9780201633610"},
    }
    assert enricher.can_enrich(record) is True


def test_can_enrich_false_when_no_isbn() -> None:
    """Returns False when externalIds has DOI but no ISBN."""
    enricher = OpenLibraryEnricher()
    record: dict[str, Any] = {
        "externalIds": {"DOI": "10.1234/test"},
    }
    assert enricher.can_enrich(record) is False


def test_can_enrich_false_when_no_external_ids() -> None:
    """Returns False when externalIds key is absent."""
    enricher = OpenLibraryEnricher()
    record: dict[str, Any] = {"title": "Some Paper"}
    assert enricher.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_uses_cache() -> None:
    """When cache has book data, book_metadata is populated and API not called."""
    enricher = OpenLibraryEnricher()
    cached = _book_cache_data()
    bundle = _make_bundle(cache_hit=cached)
    record: dict[str, Any] = {
        "paperId": "p1",
        "externalIds": {"ISBN": "9780201633610"},
    }

    await enricher.enrich(record, bundle)

    assert "book_metadata" in record
    assert record["book_metadata"]["publisher"] == "Addison-Wesley"
    bundle.cache.get_book_by_isbn.assert_awaited_once()
    bundle.openlibrary.get_by_isbn.assert_not_awaited()


@pytest.mark.anyio
async def test_enrich_handles_rate_limit_silently() -> None:
    """RateLimitedError is caught and logged; record stays unchanged."""
    from scholar_mcp._rate_limiter import RateLimitedError

    enricher = OpenLibraryEnricher()
    bundle = _make_bundle()
    record: dict[str, Any] = {
        "paperId": "p1",
        "externalIds": {"ISBN": "9780201633610"},
    }

    with patch(
        "scholar_mcp._enricher_openlibrary._enrich_one",
        new_callable=AsyncMock,
        side_effect=RateLimitedError("rate limited"),
    ):
        await enricher.enrich(record, bundle)

    assert "book_metadata" not in record


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    """Exception during enrichment is swallowed; record stays unchanged."""
    enricher = OpenLibraryEnricher()
    bundle = _make_bundle()
    record: dict[str, Any] = {
        "paperId": "p1",
        "externalIds": {"ISBN": "9780201633610"},
    }

    with patch(
        "scholar_mcp._enricher_openlibrary._enrich_one",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        await enricher.enrich(record, bundle)

    assert "book_metadata" not in record

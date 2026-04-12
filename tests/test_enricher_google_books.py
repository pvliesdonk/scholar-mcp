"""Tests for GoogleBooksEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scholar_mcp._enricher_google_books import GoogleBooksEnricher
from scholar_mcp._enrichment import Enricher


def _make_bundle(
    *,
    cache_hit: dict[str, Any] | None = None,
    api_result: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock ServiceBundle with configurable cache/API responses."""
    bundle = MagicMock()
    bundle.cache.get_google_books = AsyncMock(return_value=cache_hit)
    bundle.cache.set_google_books = AsyncMock()
    bundle.google_books.search_by_isbn = AsyncMock(return_value=api_result)
    return bundle


def _gb_data(
    preview_link: str = "https://books.google.com/preview",
    snippet: str | None = "A sample snippet",
) -> dict[str, Any]:
    """Return minimal Google Books volume data."""
    data: dict[str, Any] = {
        "volumeInfo": {
            "previewLink": preview_link,
        },
    }
    if snippet is not None:
        data["searchInfo"] = {"textSnippet": snippet}
    return data


def test_satisfies_enricher_protocol() -> None:
    """GoogleBooksEnricher must satisfy the runtime-checkable Enricher protocol."""
    enricher = GoogleBooksEnricher()
    assert isinstance(enricher, Enricher)
    assert enricher.name == "google_books"
    assert enricher.phase == 1
    assert enricher.tags == frozenset({"books"})


def test_can_enrich_true_when_isbn13() -> None:
    """Returns True when isbn_13 is present and no google_books_url."""
    enricher = GoogleBooksEnricher()
    record: dict[str, Any] = {"isbn_13": "9780201633610"}
    assert enricher.can_enrich(record) is True


def test_can_enrich_true_when_isbn10() -> None:
    """Returns True when isbn_10 is present and no google_books_url."""
    enricher = GoogleBooksEnricher()
    record: dict[str, Any] = {"isbn_10": "0201633612"}
    assert enricher.can_enrich(record) is True


def test_can_enrich_false_when_no_isbn() -> None:
    """Returns False when neither isbn_13 nor isbn_10 is present."""
    enricher = GoogleBooksEnricher()
    record: dict[str, Any] = {"title": "Some Book"}
    assert enricher.can_enrich(record) is False


def test_can_enrich_false_when_already_enriched() -> None:
    """Returns False when google_books_url is already present."""
    enricher = GoogleBooksEnricher()
    record: dict[str, Any] = {
        "isbn_13": "9780201633610",
        "google_books_url": "https://books.google.com/existing",
    }
    assert enricher.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_fills_google_books_url() -> None:
    """Cache miss: API called, result cached, fields filled."""
    enricher = GoogleBooksEnricher()
    gb = _gb_data()
    bundle = _make_bundle(cache_hit=None, api_result=gb)
    record: dict[str, Any] = {"isbn_13": "9780201633610"}

    await enricher.enrich(record, bundle)

    assert record["google_books_url"] == "https://books.google.com/preview"
    assert record["snippet"] == "A sample snippet"
    bundle.cache.get_google_books.assert_awaited_once_with("9780201633610")
    bundle.google_books.search_by_isbn.assert_awaited_once_with("9780201633610")
    bundle.cache.set_google_books.assert_awaited_once_with("9780201633610", gb)


@pytest.mark.anyio
async def test_enrich_uses_cache() -> None:
    """Cache hit: API not called, fields filled from cached data."""
    enricher = GoogleBooksEnricher()
    gb = _gb_data()
    bundle = _make_bundle(cache_hit=gb)
    record: dict[str, Any] = {"isbn_13": "9780201633610"}

    await enricher.enrich(record, bundle)

    assert record["google_books_url"] == "https://books.google.com/preview"
    assert record["snippet"] == "A sample snippet"
    bundle.cache.get_google_books.assert_awaited_once_with("9780201633610")
    bundle.google_books.search_by_isbn.assert_not_awaited()
    bundle.cache.set_google_books.assert_not_awaited()


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    """Exception during enrichment is swallowed; record stays unchanged."""
    enricher = GoogleBooksEnricher()
    bundle = _make_bundle()
    bundle.cache.get_google_books = AsyncMock(side_effect=RuntimeError("boom"))
    record: dict[str, Any] = {"isbn_13": "9780201633610"}

    await enricher.enrich(record, bundle)

    assert "google_books_url" not in record
    assert "snippet" not in record

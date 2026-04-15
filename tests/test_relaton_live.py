"""Tests for _relaton_live: slug helper + single-file live fetcher."""

from __future__ import annotations

import httpx
import pytest
import respx

ISO_9001_YAML = """
docidentifier:
  - id: "ISO 9001:2015"
    type: "ISO"
    primary: true
title:
  - content: "Quality management systems — Requirements"
    language: "en"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
link:
  - type: "src"
    content: "https://www.iso.org/standard/62085.html"
"""

IEC_62443_YAML = """
docidentifier:
  - id: "IEC 62443-3-3:2020"
    type: "IEC"
    primary: true
title:
  - content: "Industrial communication networks — IT security"
    language: "en"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
link:
  - type: "src"
    content: "https://webstore.iec.ch/publication/1234"
"""


def test_identifier_to_slug_iso() -> None:
    from scholar_mcp._relaton_live import _identifier_to_relaton_slug

    assert _identifier_to_relaton_slug("ISO 9001:2015") == "iso-9001-2015"


def test_identifier_to_slug_iso_iec_joint() -> None:
    from scholar_mcp._relaton_live import _identifier_to_relaton_slug

    assert _identifier_to_relaton_slug("ISO/IEC 27001:2022") == "iso-iec-27001-2022"


def test_identifier_to_slug_iec() -> None:
    from scholar_mcp._relaton_live import _identifier_to_relaton_slug

    assert _identifier_to_relaton_slug("IEC 62443-3-3:2020") == "iec-62443-3-3-2020"


def test_identifier_to_slug_with_amendment() -> None:
    from scholar_mcp._relaton_live import _identifier_to_relaton_slug

    assert (
        _identifier_to_relaton_slug("ISO 9001:2015/Amd 1:2020")
        == "iso-9001-2015-amd-1-2020"
    )


def test_identifier_to_slug_returns_none_for_non_iso_iec() -> None:
    from scholar_mcp._relaton_live import _identifier_to_relaton_slug

    assert _identifier_to_relaton_slug("RFC 9000") is None


def test_identifier_to_slug_rejects_compact_no_separator() -> None:
    """Compact form 'ISO9001' without a separator is rejected."""
    from scholar_mcp._relaton_live import _identifier_to_relaton_slug

    assert _identifier_to_relaton_slug("ISO9001") is None
    assert _identifier_to_relaton_slug("IEC62443") is None


@pytest.mark.asyncio
async def test_live_fetch_iso_hit() -> None:
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    with respx.mock(assert_all_called=False) as router:
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iso-9001-2015.yaml"
        ).mock(return_value=httpx.Response(200, text=ISO_9001_YAML))

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            record = await fetcher.get("ISO 9001:2015")

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    assert record["body"] == "ISO"


@pytest.mark.asyncio
async def test_live_fetch_falls_back_to_iec_when_iso_404() -> None:
    """For an ISO-prefixed identifier, ISO repo is tried first.

    When ISO returns 404, the fetcher falls back to the IEC repo.
    """
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    call_order: list[str] = []

    with respx.mock(assert_all_called=True) as router:
        # ISO repo is called first and returns 404
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iso-9001-2015.yaml"
        ).mock(side_effect=lambda _: (call_order.append("iso"), httpx.Response(404))[1])
        # IEC repo is called as fallback and succeeds
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iec/main/data/iso-9001-2015.yaml"
        ).mock(
            side_effect=lambda _: (
                call_order.append("iec"),
                httpx.Response(200, text=ISO_9001_YAML),
            )[1]
        )

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            record = await fetcher.get("ISO 9001:2015")

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    # ISO repo was attempted first, then IEC as fallback
    assert call_order == ["iso", "iec"], f"Expected ISO then IEC, got: {call_order}"


@pytest.mark.asyncio
async def test_live_fetch_falls_back_to_iso_when_iec_404() -> None:
    """For an IEC-prefixed identifier, IEC repo is tried first.

    When IEC returns 404, the fetcher falls back to the ISO repo.
    """
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    call_order: list[str] = []

    with respx.mock(assert_all_called=True) as router:
        # IEC repo is called first and returns 404
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iec/main/data/iec-62443-3-3-2020.yaml"
        ).mock(side_effect=lambda _: (call_order.append("iec"), httpx.Response(404))[1])
        # ISO repo is called as fallback and succeeds
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iec-62443-3-3-2020.yaml"
        ).mock(
            side_effect=lambda _: (
                call_order.append("iso"),
                httpx.Response(200, text=IEC_62443_YAML),
            )[1]
        )

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            record = await fetcher.get("IEC 62443-3-3:2020")

    assert record is not None
    assert record["body"] == "IEC"
    # IEC repo was attempted first, then ISO as fallback
    assert call_order == ["iec", "iso"], f"Expected IEC then ISO, got: {call_order}"


@pytest.mark.asyncio
async def test_live_fetch_returns_stub_when_both_404() -> None:
    """Neither repo has the slug → stub record with full_text_available=False."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    with respx.mock(assert_all_called=False) as router:
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iso-99999-2099.yaml"
        ).mock(return_value=httpx.Response(404))
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iec/main/data/iso-99999-2099.yaml"
        ).mock(return_value=httpx.Response(404))

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            record = await fetcher.get("ISO 99999:2099")

    assert record is not None
    assert record["identifier"] == "ISO 99999:2099"
    assert record["full_text_available"] is False
    assert record["title"] == ""
    assert record["status"] == "unknown"


@pytest.mark.asyncio
async def test_live_fetch_returns_none_for_non_slugifiable_id() -> None:
    """Identifiers the slug helper can't handle → None (not stub)."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    async with httpx.AsyncClient() as http:
        fetcher = RelatonLiveFetcher(http=http)
        result = await fetcher.get("RFC 9000")

    assert result is None


@pytest.mark.asyncio
async def test_live_fetch_returns_stub_on_server_error() -> None:
    """Non-404 server errors (5xx) are handled: stub is returned when all repos fail."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    with respx.mock(assert_all_called=True) as router:
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iso-9001-2015.yaml"
        ).mock(return_value=httpx.Response(500))
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iec/main/data/iso-9001-2015.yaml"
        ).mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            result = await fetcher.get("ISO 9001:2015")

    # Both repos returned 5xx → fall through to stub
    assert result is not None
    assert result["title"] == ""
    assert result["full_text_available"] is False
    assert result["identifier"] == "ISO 9001:2015"
    assert result["status"] == "unknown"


@pytest.mark.asyncio
async def test_live_fetch_returns_stub_on_yaml_parse_error() -> None:
    """Invalid YAML response is caught; stub is returned when all repos fail."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    bad_yaml = "!!bad\n  yaml: [\n  not closed"

    with respx.mock(assert_all_called=True) as router:
        # ISO repo returns malformed YAML
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iso-9001-2015.yaml"
        ).mock(return_value=httpx.Response(200, text=bad_yaml))
        # IEC repo returns 404
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iec/main/data/iso-9001-2015.yaml"
        ).mock(return_value=httpx.Response(404))

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            result = await fetcher.get("ISO 9001:2015")

    # YAMLError caught in ISO repo + 404 from IEC → stub
    assert result is not None
    assert result["title"] == ""
    assert result["full_text_available"] is False
    assert result["identifier"] == "ISO 9001:2015"
    assert result["status"] == "unknown"


@pytest.mark.asyncio
async def test_live_fetcher_search_returns_cache_results() -> None:
    """search() delegates to cache.search_synced_standards."""
    from unittest.mock import AsyncMock

    from scholar_mcp._record_types import StandardRecord
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    record: StandardRecord = {
        "identifier": "ISO 9001:2015",
        "title": "Quality management systems",
        "body": "ISO",
        "status": "published",
        "full_text_available": False,
    }
    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[record])

    async with httpx.AsyncClient() as http:
        fetcher = RelatonLiveFetcher(http=http, cache=mock_cache)
        results = await fetcher.search("9001", limit=5)

    mock_cache.search_synced_standards.assert_awaited_once_with("9001", limit=5)
    assert len(results) == 1
    assert results[0]["identifier"] == "ISO 9001:2015"


@pytest.mark.asyncio
async def test_live_fetcher_search_returns_empty_without_cache() -> None:
    """search() returns [] when no cache is provided."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    async with httpx.AsyncClient() as http:
        fetcher = RelatonLiveFetcher(http=http)
        results = await fetcher.search("9001")

    assert results == []

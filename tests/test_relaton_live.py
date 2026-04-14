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


@pytest.mark.asyncio
async def test_live_fetch_iso_hit() -> None:
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    with respx.mock(assert_all_called=False) as router:
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iso-9001-2015.yaml"
        ).mock(return_value=httpx.Response(200, text=ISO_9001_YAML))

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            record = await fetcher.fetch("ISO 9001:2015")

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    assert record["body"] == "ISO"


@pytest.mark.asyncio
async def test_live_fetch_falls_back_to_iec_when_iso_404() -> None:
    """For an IEC-prefixed identifier, we try IEC first; when ISO joint
    repo 404s we also try the other."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    iec_yaml = ISO_9001_YAML.replace("ISO 9001:2015", "IEC 62443-3-3:2020").replace(
        '"ISO"', '"IEC"'
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iec/main/data/iec-62443-3-3-2020.yaml"
        ).mock(return_value=httpx.Response(200, text=iec_yaml))
        # If the fetcher probes the ISO repo first, it should 404 there
        router.get(
            "https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/iec-62443-3-3-2020.yaml"
        ).mock(return_value=httpx.Response(404))

        async with httpx.AsyncClient() as http:
            fetcher = RelatonLiveFetcher(http=http)
            record = await fetcher.fetch("IEC 62443-3-3:2020")

    assert record is not None
    assert record["body"] == "IEC"


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
            record = await fetcher.fetch("ISO 99999:2099")

    assert record is not None
    assert record["identifier"] == "ISO 99999:2099"
    assert record["full_text_available"] is False
    assert record["title"] == ""


@pytest.mark.asyncio
async def test_live_fetch_returns_none_for_non_slugifiable_id() -> None:
    """Identifiers the slug helper can't handle → None (not stub)."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher

    async with httpx.AsyncClient() as http:
        fetcher = RelatonLiveFetcher(http=http)
        result = await fetcher.fetch("RFC 9000")

    assert result is None

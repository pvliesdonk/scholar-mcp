"""Tests for StandardsClient, source fetchers, and identifier resolver."""

from __future__ import annotations

import re

import httpx
import pytest
import respx

from scholar_mcp._rate_limiter import RateLimiter
from scholar_mcp._standards_client import (
    StandardsClient,
    _ETSIFetcher,
    _IETFFetcher,
    _NISTFetcher,
    _W3CFetcher,
    resolve_identifier_local,
)

# --- Resolver: IETF ---


def test_resolve_rfc_with_space() -> None:
    result = resolve_identifier_local("RFC 9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_no_space() -> None:
    result = resolve_identifier_local("rfc9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_hyphen() -> None:
    result = resolve_identifier_local("rfc-9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_tls() -> None:
    result = resolve_identifier_local("RFC 8446")
    assert result == ("RFC 8446", "IETF")


def test_resolve_bcp_with_space() -> None:
    result = resolve_identifier_local("BCP 47")
    assert result == ("BCP 47", "IETF")


def test_resolve_bcp_no_space() -> None:
    result = resolve_identifier_local("BCP47")
    assert result == ("BCP 47", "IETF")


def test_resolve_std_with_space() -> None:
    result = resolve_identifier_local("STD 66")
    assert result == ("STD 66", "IETF")


def test_resolve_std_no_space() -> None:
    result = resolve_identifier_local("STD66")
    assert result == ("STD 66", "IETF")


# --- Resolver: NIST SP ---


def test_resolve_nist_sp_full() -> None:
    result = resolve_identifier_local("NIST SP 800-53 Rev. 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_abbreviated_rev() -> None:
    result = resolve_identifier_local("SP800-53r5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_space_rev() -> None:
    result = resolve_identifier_local("nist 800-53 rev 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_no_rev() -> None:
    result = resolve_identifier_local("NIST SP 800-53")
    assert result == ("NIST SP 800-53", "NIST")


def test_resolve_nist_fips() -> None:
    result = resolve_identifier_local("FIPS 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nist_fips_no_space() -> None:
    result = resolve_identifier_local("FIPS140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir() -> None:
    result = resolve_identifier_local("NISTIR 8259A")
    assert result == ("NISTIR 8259A", "NIST")


def test_resolve_nist_fips_pub_form() -> None:
    result = resolve_identifier_local("FIPS PUB 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir_no_space() -> None:
    result = resolve_identifier_local("NISTIR8259A")
    assert result == ("NISTIR 8259A", "NIST")


# --- Resolver: W3C ---


def test_resolve_wcag_with_prefix() -> None:
    result = resolve_identifier_local("W3C WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_prefix() -> None:
    result = resolve_identifier_local("WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_space() -> None:
    result = resolve_identifier_local("WCAG2.1")
    assert result == ("WCAG 2.1", "W3C")


# --- Resolver: ETSI ---


def test_resolve_etsi_en_with_spaces() -> None:
    result = resolve_identifier_local("ETSI EN 303 645")
    assert result == ("ETSI EN 303 645", "ETSI")


def test_resolve_etsi_en_no_spaces() -> None:
    result = resolve_identifier_local("etsi en 303645")
    assert result == ("ETSI EN 303 645", "ETSI")


def test_resolve_etsi_ts_with_part_number() -> None:
    result = resolve_identifier_local("ETSI TS 102 690-1")
    assert result == ("ETSI TS 102 690-1", "ETSI")


# --- Resolver: unrecognised ---


def test_resolve_nist_bare_number() -> None:
    result = resolve_identifier_local("nist 800-53")
    assert result == ("NIST SP 800-53", "NIST")


def test_resolve_webauthn() -> None:
    result = resolve_identifier_local("WebAuthn Level 2")
    assert result == ("WebAuthn Level 2", "W3C")


def test_resolve_unknown_returns_none() -> None:
    result = resolve_identifier_local("some random text")
    assert result is None


def test_resolve_iec_series_returns_none() -> None:
    # IEC 62443 is Tier 2 — not handled by local Tier 1 resolver
    result = resolve_identifier_local("62443")
    assert result is None


# ---------------------------------------------------------------------------
# IETF fetcher tests
# ---------------------------------------------------------------------------

IETF_BASE = "https://datatracker.ietf.org"
RFC_EDITOR_BASE = "https://www.rfc-editor.org"

SAMPLE_RFC9000_DOC = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "abstract": "This document defines QUIC.",
            "std_level": "proposed_standard",
            "pub_date": "2021-05-01",
            "resource_uri": "/api/v1/doc/document/rfc9000/",
        }
    ],
    "meta": {"total_count": 1},
}

SAMPLE_RFC9000_SEARCH = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "std_level": "proposed_standard",
            "pub_date": "2021-05-01",
            "resource_uri": "/api/v1/doc/document/rfc9000/",
        }
    ],
    "meta": {"total_count": 1},
}


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_rfc(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_DOC)
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 9000")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "RFC 9000"
    assert record["body"] == "IETF"
    assert record["number"] == "9000"
    assert record["full_text_available"] is True
    assert record["full_text_url"].startswith("https://www.rfc-editor.org/")


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_bcp(respx_mock: respx.MockRouter) -> None:
    """_IETFFetcher.get() resolves BCP identifiers via Datatracker."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "name": "bcp47",
                        "title": "Tags for Identifying Languages",
                        "std_level": "best_current_practice",
                    }
                ]
            },
        )
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("BCP 47")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "BCP 47"
    assert record["url"] == "https://www.rfc-editor.org/info/bcp47"
    assert record["full_text_available"] is False


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(
            200, json={"objects": [], "meta": {"total_count": 0}}
        )
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 99999")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("QUIC transport", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "RFC 9000"


# ---------------------------------------------------------------------------
# _normalize_ietf regression tests
# ---------------------------------------------------------------------------


def test_normalize_ietf_null_std_level() -> None:
    from scholar_mcp._standards_client import _normalize_ietf

    obj = {
        "name": "rfc9000",
        "title": "QUIC",
        "std_level": None,
        "pub_date": "2021-05-01",
    }
    record = _normalize_ietf(obj)
    assert record["status"] == "published"


def test_normalize_ietf_bcp_name() -> None:
    from scholar_mcp._standards_client import _normalize_ietf

    obj = {
        "name": "bcp47",
        "title": "Tags for Identifying Languages",
        "std_level": "best_current_practice",
        "pub_date": "2009-09-01",
    }
    record = _normalize_ietf(obj)
    assert record["identifier"] == "BCP 47"
    assert record["identifier"] != "RFC 47"
    # BCP gets correct rfc-editor URL, not an RFC-style URL
    assert record["url"] == "https://www.rfc-editor.org/info/bcp47"
    # BCPs don't have a plain-text HTML page
    assert record["full_text_url"] is None
    assert record["full_text_available"] is False


def test_normalize_ietf_early_rfc_url() -> None:
    from scholar_mcp._standards_client import _normalize_ietf

    obj = {
        "name": "rfc0001",
        "title": "Host Software",
        "std_level": "unknown",
        "pub_date": "1969-04-07",
    }
    record = _normalize_ietf(obj)
    assert record["identifier"] == "RFC 1"
    assert record["number"] == "1"
    assert record["full_text_url"] is not None
    # URL uses the raw Datatracker name (rfc0001) — RFC Editor handles both forms
    assert record["full_text_url"].startswith("https://www.rfc-editor.org/rfc/rfc0001")


# ---------------------------------------------------------------------------
# NIST fetcher tests (MODS XML backend)
# ---------------------------------------------------------------------------

GITHUB_RELEASES_URL = "https://api.github.com"
GITHUB_RELEASES_CDN = "https://objects.githubusercontent.com"  # redirect target

SAMPLE_GITHUB_RELEASE = {
    "tag_name": "Jan2026",
    "assets": [
        {
            "name": "allrecords-MODS.xml",
            "url": "https://api.github.com/repos/usnistgov/NIST-Tech-Pubs/releases/assets/allrecords-MODS.xml",
            "browser_download_url": "https://github.com/usnistgov/NIST-Tech-Pubs/releases/download/Jan2026/allrecords-MODS.xml",
        }
    ],
}

SAMPLE_MODS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<modsCollection xmlns="http://www.loc.gov/mods/v3">
  <mods version="3.7">
    <titleInfo>
      <title>Security and Privacy Controls for Information Systems and Organizations</title>
    </titleInfo>
    <abstract displayLabel="Abstract">A catalog of security and privacy controls.</abstract>
    <originInfo eventType="publisher">
      <dateIssued>2020-09.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.SP.800-53r5</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>NIST special publication; NIST special pub; NIST SP</title>
        <partNumber>800-53r5</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.SP.800-53r5</identifier>
  </mods>
  <mods version="3.7">
    <titleInfo>
      <title>Minimum Security Requirements for Federal Information and Information Systems</title>
    </titleInfo>
    <originInfo eventType="publisher">
      <dateIssued>2006-03.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.FIPS.200</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>Federal information processing standards publication; FIPS</title>
        <partNumber>200</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.FIPS.200</identifier>
  </mods>
  <mods version="3.7">
    <titleInfo>
      <title>Cybersecurity Framework Version 2.0</title>
    </titleInfo>
    <originInfo eventType="publisher">
      <dateIssued>2024-02.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.CSWP.29</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>NIST cybersecurity white paper; NIST CSWP</title>
        <partNumber>29</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.CSWP.29</identifier>
  </mods>
</modsCollection>
"""


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_search_sp(respx_mock: respx.MockRouter, tmp_path) -> None:
    """search() finds SP 800-53 from MODS XML."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "NIST SP 800-53 Rev. 5"
    assert results[0]["body"] == "NIST"
    assert results[0]["number"] == "800-53"
    assert results[0]["revision"] == "Rev. 5"
    assert results[0]["full_text_available"] is False
    assert results[0]["url"]  # catalogue/DOI URL is still set


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_search_fips(respx_mock: respx.MockRouter, tmp_path) -> None:
    """search() finds FIPS 200."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("FIPS 200", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "FIPS 200"
    assert results[0]["body"] == "NIST"


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get(respx_mock: respx.MockRouter, tmp_path) -> None:
    """get() returns exact match."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 800-53 Rev. 5")
    await http.aclose()
    assert record is not None
    assert record["title"].startswith("Security and Privacy")
    assert record["scope"] is not None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get_not_found(respx_mock: respx.MockRouter, tmp_path) -> None:
    """get() returns None for unknown identifier."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 999-99")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_disk_cache_used_on_second_call(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Second fetcher instance loads from disk cache, no network call."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=SAMPLE_MODS_XML)

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        side_effect=side_effect
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)

    # First fetcher: downloads XML, saves to disk
    fetcher1 = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    await fetcher1.search("800-53", limit=1)
    assert call_count == 1

    # Second fetcher: should load from disk, not download again
    fetcher2 = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    await fetcher2.search("800-53", limit=1)
    await http.aclose()
    assert call_count == 1  # no new download


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_in_memory_cache_used_on_second_search(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Second search on same fetcher uses in-memory cache, no extra network call."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=SAMPLE_MODS_XML)

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        side_effect=side_effect
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    await fetcher.search("800-53", limit=1)
    await fetcher.search("FIPS", limit=1)
    await http.aclose()
    assert call_count == 1  # MODS XML downloaded only once


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_github_api_failure_returns_empty(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """GitHub API failure logs warning and returns empty list."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(503)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert results == []


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_stale_disk_cache_triggers_re_download(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Disk cache older than 90 days is ignored and MODS XML is re-downloaded."""
    import time

    from scholar_mcp._standards_client import _NIST_CACHE_MAX_AGE_DAYS

    # Write a stale cache file (mtime > 90 days ago)
    cache_path = tmp_path / "nist_catalogue.json"
    cache_path.write_text("[]", encoding="utf-8")
    stale_ts = time.time() - (_NIST_CACHE_MAX_AGE_DAYS + 1) * 86400
    import os

    os.utime(cache_path, (stale_ts, stale_ts))

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    # Stale cache was bypassed; MODS XML fetched and found the record
    assert len(results) == 1
    assert results[0]["identifier"] == "NIST SP 800-53 Rev. 5"


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_corrupted_disk_cache_triggers_re_download(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Corrupted JSON in disk cache falls back to fresh download."""
    cache_path = tmp_path / "nist_catalogue.json"
    cache_path.write_text("not valid json {{", encoding="utf-8")

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert len(results) == 1


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_invalid_mods_xml_returns_empty(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Malformed MODS XML logs warning and returns empty list."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=b"<not valid xml <<")
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert results == []


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_search_nistir(respx_mock: respx.MockRouter, tmp_path) -> None:
    """search() finds NISTIR series publications."""
    nistir_mods_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<modsCollection xmlns="http://www.loc.gov/mods/v3">
  <mods version="3.7">
    <titleInfo>
      <title>Usability and Security Considerations for Public Safety Mobile Authentication</title>
    </titleInfo>
    <abstract displayLabel="Abstract">This report examines usability and security.</abstract>
    <originInfo eventType="publisher">
      <dateIssued>2018-09.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.IR.8166</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>NISTIR; NIST interagency report</title>
        <partNumber>8166</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.IR.8166</identifier>
  </mods>
</modsCollection>"""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=nistir_mods_xml)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("8166", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "NISTIR 8166"
    assert results[0]["body"] == "NIST"


# ---------------------------------------------------------------------------
# W3C fetcher tests
# ---------------------------------------------------------------------------

W3C_API_BASE = "https://api.w3.org"

SAMPLE_W3C_SPEC = {
    "shortname": "WCAG21",
    "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
    "description": "Covers a wide range of recommendations for making Web content more accessible.",
    "series-version": "2.1",
    "latest-version": "https://www.w3.org/TR/WCAG21/",
    "latest-status": "Recommendation",
    "published": "2018-06-05",
    "_links": {
        "self": {"href": "https://api.w3.org/specifications/WCAG21"},
        "latest-version": {
            "href": "https://www.w3.org/TR/WCAG21/",
            "title": "Recommendation",
        },
    },
}

# Paginated stubs: 3 items across 2 pages for simplicity
SAMPLE_W3C_PAGE1 = {
    "page": 1,
    "limit": 2,
    "pages": 2,
    "total": 3,
    "_links": {
        "specifications": [
            {
                "href": "https://api.w3.org/specifications/WCAG21",
                "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
            },
            {
                "href": "https://api.w3.org/specifications/html",
                "title": "HTML Standard",
            },
        ]
    },
}

SAMPLE_W3C_PAGE2 = {
    "page": 2,
    "limit": 2,
    "pages": 2,
    "total": 3,
    "_links": {
        "specifications": [
            {
                "href": "https://api.w3.org/specifications/webauthn-2",
                "title": "Web Authentication Level 2",
            },
        ]
    },
}


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_finds_wcag(respx_mock: respx.MockRouter) -> None:
    """search() finds WCAG by title match and returns full spec."""
    respx_mock.get("/specifications").mock(
        side_effect=lambda req: (
            httpx.Response(200, json=SAMPLE_W3C_PAGE1)
            if req.url.params.get("page") in (None, "1", "")
            else httpx.Response(200, json=SAMPLE_W3C_PAGE2)
        )
    )
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("WCAG", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "W3C"
    assert "WCAG" in results[0]["title"]
    assert results[0]["full_text_available"] is True


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_stubs_cached_on_second_call(
    respx_mock: respx.MockRouter,
) -> None:
    """Stubs are fetched only once; second search reuses in-memory cache."""
    page_call_count = 0

    def page_side_effect(req):  # type: ignore[no-untyped-def]
        nonlocal page_call_count
        page_call_count += 1
        # Return a single-page response so the loop terminates after 1 request
        return httpx.Response(200, json={**SAMPLE_W3C_PAGE1, "pages": 1})

    respx_mock.get("/specifications").mock(side_effect=page_side_effect)
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    await fetcher.search("WCAG", limit=1)
    await fetcher.search("WCAG", limit=1)
    await http.aclose()
    # stubs pages fetched only once
    assert page_call_count == 1


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get(respx_mock: respx.MockRouter) -> None:
    """get() fetches individual spec by shortname."""
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("WCAG 2.1")
    await http.aclose()
    assert record is not None
    assert record["body"] == "W3C"
    assert record["full_text_available"] is True
    assert record["full_text_url"] is not None
    assert record["full_text_url"].startswith("https://www.w3.org/")


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_not_found(respx_mock: respx.MockRouter) -> None:
    """get() returns None for unknown identifier."""
    respx_mock.get("/specifications/UNKNOWNSPEC999").mock(
        return_value=httpx.Response(404)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("UNKNOWN SPEC 99.9")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_non200_returns_empty(respx_mock: respx.MockRouter) -> None:
    """search() returns [] if stubs page returns non-200."""
    respx_mock.get("/specifications").mock(return_value=httpx.Response(503))
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("WCAG", limit=5)
    await http.aclose()
    assert results == []


# ---------------------------------------------------------------------------
# ETSI fetcher tests (Joomla JSON API backend)
# ---------------------------------------------------------------------------

ETSI_BASE = "https://www.etsi.org"

SAMPLE_ETSI_JSON = [
    {
        "RowNum": "1",
        "total_count": "2",
        "wki_id": "69970",
        "TITLE": "CYBER; Cyber Security for Consumer Internet of Things: Baseline Requirements",
        "WKI_REFERENCE": "REN/CYBER-00127",
        "EDSpathname": "etsi_en/303600_303699/303645/03.01.03_60/",
        "EDSPDFfilename": "en_303645v030103p.pdf",
        "EDSARCfilename": "",
        "ETSI_DELIVERABLE": "ETSI EN 303 645 V3.1.3 (2024-09)",
        "STATUS_CODE": "12",
        "ACTION_TYPE": "PU",
        "IsCurrent": "0",
        "superseded": "0",
        "ReviewDate": None,
        "new_versions": "",
        "Scope": "Transposition of TS 103 645 v3.1.1 into an updated version.",
        "TB": "Cyber Security",
        "Keywords": "Cybersecurity,IoT,privacy",
    },
    {
        "RowNum": "2",
        "total_count": "2",
        "wki_id": "73702",
        "TITLE": "Cyber Security (CYBER); Guide to Cyber Security for Consumer IoT",
        "WKI_REFERENCE": "RTR/CYBER-00142",
        "EDSpathname": "etsi_tr/103600_103699/103621/02.01.01_60/",
        "EDSPDFfilename": "tr_103621v020101p.pdf",
        "EDSARCfilename": "",
        "ETSI_DELIVERABLE": "ETSI TR 103 621 V2.1.1 (2025-07)",
        "STATUS_CODE": "12",
        "ACTION_TYPE": "PU",
        "IsCurrent": "0",
        "superseded": "0",
        "ReviewDate": None,
        "new_versions": "",
        "Scope": None,
        "TB": "Cyber Security",
        "Keywords": "Cybersecurity,IoT",
    },
]


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search(respx_mock: respx.MockRouter) -> None:
    """search() calls Joomla JSON API and returns parsed records."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "ETSI"
    assert "303 645" in results[0]["identifier"]
    assert results[0]["full_text_available"] is True
    assert (results[0]["full_text_url"] or "").startswith(
        "https://www.etsi.org/deliver/"
    )


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_non200_returns_empty(respx_mock: respx.MockRouter) -> None:
    """search() returns [] on non-200."""
    respx_mock.get("/").mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert results == []


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get(respx_mock: respx.MockRouter) -> None:
    """get() returns first result matching identifier."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 303 645")
    await http.aclose()
    assert record is not None
    assert record["body"] == "ETSI"
    assert record["full_text_available"] is True


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_not_found(respx_mock: respx.MockRouter) -> None:
    """get() returns None when no match."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=[]))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 999 999")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_normalize_pdf_url(respx_mock: respx.MockRouter) -> None:
    """PDF URL constructed from EDSpathname + EDSPDFfilename."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=1)
    await http.aclose()
    expected_pdf = "https://www.etsi.org/deliver/etsi_en/303600_303699/303645/03.01.03_60/en_303645v030103p.pdf"
    assert results[0]["full_text_url"] == expected_pdf
    assert results[0]["url"] == expected_pdf


# ---------------------------------------------------------------------------
# StandardsClient integration tests
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=IETF_BASE)
async def test_standards_client_resolve_ietf_local(
    respx_mock: respx.MockRouter,
) -> None:
    """Local resolution needs no network call for well-known RFCs."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_DOC)
    )
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    results = await client.resolve("rfc9000")
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "RFC 9000"
    assert results[0]["body"] == "IETF"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_standards_client_search_body_filter(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_SEARCH)
    )
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    results = await client.search("QUIC", body="IETF", limit=5)
    await http.aclose()
    assert all(r["body"] == "IETF" for r in results)


async def test_standards_client_search_unknown_body() -> None:
    """Unknown body filter returns empty list without network calls."""
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    results = await client.search("anything", body="UNKNOWN")
    await http.aclose()
    assert results == []


# (NIST caching and error paths are covered by test_nist_disk_cache_used_on_second_call
#  and test_nist_github_api_failure_returns_empty above)


# ---------------------------------------------------------------------------
# ETSI additional paths
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_unexpected_response_type(
    respx_mock: respx.MockRouter,
) -> None:
    """search() returns [] when API returns a non-list JSON body."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json={"error": "bad"}))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert results == []


# ---------------------------------------------------------------------------
# StandardsClient.resolve() stub path
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=IETF_BASE)
async def test_standards_client_resolve_stub_on_fetch_fail(
    respx_mock: respx.MockRouter,
) -> None:
    """resolve() returns a stub when local resolution succeeds but API fails."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(
            200, json={"objects": [], "meta": {"total_count": 0}}
        )
    )
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    results = await client.resolve("RFC 99999")
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "RFC 99999"
    assert results[0]["body"] == "IETF"


# ---------------------------------------------------------------------------
# IETF fetcher error paths
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_non200_returns_none(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(return_value=httpx.Response(503))
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 9000")
    await http.aclose()
    assert record is None


async def test_ietf_get_unrecognised_identifier_returns_none() -> None:
    """Identifiers that don't match RFC/BCP/STD/FYI pattern return None immediately."""
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("some random text")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_search_non200_returns_empty(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(return_value=httpx.Response(503))
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("QUIC", limit=5)
    await http.aclose()
    assert results == []


def test_normalize_ietf_empty_name() -> None:
    """_normalize_ietf handles objects with empty/missing name gracefully."""
    from scholar_mcp._standards_client import _normalize_ietf

    obj = {"name": "", "title": "Unknown", "std_level": ""}
    record = _normalize_ietf(obj)
    assert record["url"] == ""
    assert record["full_text_url"] is None
    assert record["number"] == ""


# ---------------------------------------------------------------------------
# W3C normalization status branches
# ---------------------------------------------------------------------------


def test_normalize_w3c_draft_status() -> None:
    from scholar_mcp._standards_client import _normalize_w3c

    spec = {
        "shortname": "foo-1",
        "title": "Foo Working Draft",
        "latest-status": "Working Draft",
        "latest-version": "https://www.w3.org/TR/foo-1/",
    }
    record = _normalize_w3c(spec)
    assert record["status"] == "draft"


def test_normalize_w3c_retired_status() -> None:
    from scholar_mcp._standards_client import _normalize_w3c

    spec = {
        "shortname": "foo-0",
        "title": "Foo Retired",
        "latest-status": "Retired",
        "latest-version": "https://www.w3.org/TR/foo-0/",
    }
    record = _normalize_w3c(spec)
    assert record["status"] == "superseded"


def test_normalize_w3c_no_latest_url_falls_back_to_tr() -> None:
    from scholar_mcp._standards_client import _normalize_w3c

    spec = {"shortname": "myspec", "title": "My Spec", "status": "Recommendation"}
    record = _normalize_w3c(spec)
    assert record["url"] == "https://www.w3.org/TR/myspec/"


# ---------------------------------------------------------------------------
# StandardsClient concurrent search and get fallback
# ---------------------------------------------------------------------------


async def test_standards_client_search_all_bodies() -> None:
    """search() without body filter runs concurrent gather across all fetchers."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"datatracker\.ietf\.org").mock(
            return_value=httpx.Response(200, json=SAMPLE_RFC9000_SEARCH)
        )
        mock.get(url__regex=r"api\.github\.com").mock(return_value=httpx.Response(503))
        mock.get(url__regex=r"api\.w3\.org").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        mock.get(url__regex=r"www\.etsi\.org").mock(
            return_value=httpx.Response(200, json=[])
        )
        http = httpx.AsyncClient()
        client = StandardsClient(http)
        results = await client.search("QUIC", limit=5)
        await http.aclose()
    assert isinstance(results, list)


async def test_standards_client_get_fallback_to_fetchers() -> None:
    """get() with unresolvable identifier falls back to each fetcher in turn."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"datatracker\.ietf\.org").mock(
            return_value=httpx.Response(
                200, json={"objects": [], "meta": {"total_count": 0}}
            )
        )
        mock.get(url__regex=r"api\.github\.com").mock(return_value=httpx.Response(503))
        mock.get(url__regex=r"api\.w3\.org").mock(return_value=httpx.Response(404))
        mock.get(url__regex=r"www\.etsi\.org").mock(
            return_value=httpx.Response(200, json=[])
        )
        http = httpx.AsyncClient()
        client = StandardsClient(http)
        result = await client.get("some-unknown-standard-xyz")
        await http.aclose()
    assert result is None

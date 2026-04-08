"""Tests for StandardsClient, source fetchers, and identifier resolver."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._rate_limiter import RateLimiter
from scholar_mcp._standards_client import (
    _ETSIFetcher,
    _IETFFetcher,
    _NISTFetcher,
    _resolve_identifier_local,
    _W3CFetcher,
)

# --- Resolver: IETF ---


def test_resolve_rfc_with_space() -> None:
    result = _resolve_identifier_local("RFC 9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_no_space() -> None:
    result = _resolve_identifier_local("rfc9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_hyphen() -> None:
    result = _resolve_identifier_local("rfc-9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_tls() -> None:
    result = _resolve_identifier_local("RFC 8446")
    assert result == ("RFC 8446", "IETF")


def test_resolve_bcp_with_space() -> None:
    result = _resolve_identifier_local("BCP 47")
    assert result == ("BCP 47", "IETF")


def test_resolve_bcp_no_space() -> None:
    result = _resolve_identifier_local("BCP47")
    assert result == ("BCP 47", "IETF")


def test_resolve_std_with_space() -> None:
    result = _resolve_identifier_local("STD 66")
    assert result == ("STD 66", "IETF")


def test_resolve_std_no_space() -> None:
    result = _resolve_identifier_local("STD66")
    assert result == ("STD 66", "IETF")


# --- Resolver: NIST SP ---


def test_resolve_nist_sp_full() -> None:
    result = _resolve_identifier_local("NIST SP 800-53 Rev. 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_abbreviated_rev() -> None:
    result = _resolve_identifier_local("SP800-53r5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_space_rev() -> None:
    result = _resolve_identifier_local("nist 800-53 rev 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_no_rev() -> None:
    result = _resolve_identifier_local("NIST SP 800-53")
    assert result == ("NIST SP 800-53", "NIST")


def test_resolve_nist_fips() -> None:
    result = _resolve_identifier_local("FIPS 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nist_fips_no_space() -> None:
    result = _resolve_identifier_local("FIPS140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir() -> None:
    result = _resolve_identifier_local("NISTIR 8259A")
    assert result == ("NISTIR 8259A", "NIST")


def test_resolve_nist_fips_pub_form() -> None:
    result = _resolve_identifier_local("FIPS PUB 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir_no_space() -> None:
    result = _resolve_identifier_local("NISTIR8259A")
    assert result == ("NISTIR 8259A", "NIST")


# --- Resolver: W3C ---


def test_resolve_wcag_with_prefix() -> None:
    result = _resolve_identifier_local("W3C WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_prefix() -> None:
    result = _resolve_identifier_local("WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_space() -> None:
    result = _resolve_identifier_local("WCAG2.1")
    assert result == ("WCAG 2.1", "W3C")


# --- Resolver: ETSI ---


def test_resolve_etsi_en_with_spaces() -> None:
    result = _resolve_identifier_local("ETSI EN 303 645")
    assert result == ("ETSI EN 303 645", "ETSI")


def test_resolve_etsi_en_no_spaces() -> None:
    result = _resolve_identifier_local("etsi en 303645")
    assert result == ("ETSI EN 303 645", "ETSI")


# --- Resolver: unrecognised ---


def test_resolve_nist_bare_number() -> None:
    result = _resolve_identifier_local("nist 800-53")
    assert result == ("NIST SP 800-53", "NIST")


def test_resolve_webauthn() -> None:
    result = _resolve_identifier_local("WebAuthn Level 2")
    assert result == ("WebAuthn Level 2", "W3C")


def test_resolve_unknown_returns_none() -> None:
    result = _resolve_identifier_local("some random text")
    assert result is None


def test_resolve_iec_series_returns_none() -> None:
    # IEC 62443 is Tier 2 — not handled by local Tier 1 resolver
    result = _resolve_identifier_local("62443")
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
    assert "rfc-editor.org" in record["full_text_url"]


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
    assert record["identifier"] == "BCP47"
    assert record["identifier"] != "RFC 47"


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
    assert "rfc1" in record["full_text_url"]
    assert "rfc0001" not in record["full_text_url"]


# ---------------------------------------------------------------------------
# NIST fetcher tests
# ---------------------------------------------------------------------------

NIST_BASE = "https://csrc.nist.gov"

SAMPLE_NIST_SEARCH = [
    {
        "docIdentifier": "SP 800-53 Rev. 5",
        "title": "Security and Privacy Controls for Information Systems and Organizations",
        "abstract": "This publication provides a catalog of security and privacy controls.",
        "status": "Final",
        "publicationDate": "2020-09-23",
        "doiUrl": "https://doi.org/10.6028/NIST.SP.800-53r5",
        "doi": "10.6028/NIST.SP.800-53r5",
        "pdfUrl": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf",
        "series": "Special Publication (SP)",
        "number": "800-53",
        "revisionNumber": "5",
        "family": "",
    }
]


@pytest.mark.respx(base_url=NIST_BASE)
async def test_nist_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/CSRC/media/Publications/search-results-json-file/json").mock(
        return_value=httpx.Response(200, json=SAMPLE_NIST_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "NIST SP 800-53 Rev. 5"
    assert results[0]["body"] == "NIST"
    assert results[0]["full_text_available"] is True


@pytest.mark.respx(base_url=NIST_BASE)
async def test_nist_get(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/CSRC/media/Publications/search-results-json-file/json").mock(
        return_value=httpx.Response(200, json=SAMPLE_NIST_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("NIST SP 800-53 Rev. 5")
    await http.aclose()
    assert record is not None
    assert record["number"] == "800-53"
    assert record["revision"] == "Rev. 5"
    assert record["full_text_url"] is not None
    assert "nvlpubs.nist.gov" in record["full_text_url"]


@pytest.mark.respx(base_url=NIST_BASE)
async def test_nist_get_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/CSRC/media/Publications/search-results-json-file/json").mock(
        return_value=httpx.Response(200, json=[])
    )
    http = httpx.AsyncClient()
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("NIST SP 999-99")
    await http.aclose()
    assert record is None


# ---------------------------------------------------------------------------
# W3C fetcher tests
# ---------------------------------------------------------------------------

W3C_API_BASE = "https://api.w3.org"

SAMPLE_W3C_SPEC = {
    "shortname": "WCAG21",
    "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
    "description": "Covers a wide range of recommendations for making Web content more accessible.",
    "status": "Recommendation",
    "_links": {
        "self": {"href": "https://api.w3.org/specifications/WCAG21"},
        "latest-version": {"href": "https://www.w3.org/TR/WCAG21/"},
    },
    "latest-version": "https://www.w3.org/TR/WCAG21/",
    "latest-status": "Recommendation",
    "published": "2018-06-05",
}

SAMPLE_W3C_SEARCH = {
    "results": [SAMPLE_W3C_SPEC],
    "pages": 1,
    "total": 1,
}


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/specifications").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("WCAG 2.1", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "W3C"
    assert "WCAG" in results[0]["title"]


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient()
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("WCAG 2.1")
    await http.aclose()
    assert record is not None
    assert record["body"] == "W3C"
    assert record["full_text_available"] is True
    assert record["full_text_url"] is not None
    assert "w3.org/TR" in record["full_text_url"]


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/specifications/UNKNOWNSPEC999").mock(
        return_value=httpx.Response(404)
    )
    http = httpx.AsyncClient()
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("UNKNOWN SPEC 99.9")
    await http.aclose()
    assert record is None


# ---------------------------------------------------------------------------
# ETSI fetcher tests
# ---------------------------------------------------------------------------

ETSI_BASE = "https://www.etsi.org"

SAMPLE_ETSI_HTML = """
<html><body>
<table class="table">
<tr>
  <td><a href="/deliver/etsi_en/303600_303699/303645/02.01.01_60/en_303645v020101p.pdf">ETSI EN 303 645</a></td>
  <td>Cyber Security for Consumer Internet of Things: Baseline Requirements</td>
  <td>V2.1.1 (2020-06)</td>
  <td>2020-06-30</td>
</tr>
</table>
</body></html>
"""


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_index_built_on_first_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/standards-search/").mock(
        return_value=httpx.Response(200, text=SAMPLE_ETSI_HTML)
    )
    http = httpx.AsyncClient()
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "ETSI"
    assert "303 645" in results[0]["identifier"]


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_cached_index_skips_network(
    respx_mock: respx.MockRouter,
) -> None:
    """Second search with warm index should not call ETSI network."""
    call_count = 0

    def side_effect(request):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, text=SAMPLE_ETSI_HTML)

    respx_mock.get("/standards-search/").mock(side_effect=side_effect)
    http = httpx.AsyncClient()
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    await fetcher.search("303 645", limit=5)
    await fetcher.search("303 645", limit=5)  # second call — should use in-memory index
    await http.aclose()
    assert call_count == 1  # network called only once


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/standards-search/").mock(
        return_value=httpx.Response(200, text=SAMPLE_ETSI_HTML)
    )
    http = httpx.AsyncClient()
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 303 645")
    await http.aclose()
    assert record is not None
    assert record["body"] == "ETSI"
    assert record["full_text_available"] is True

"""Tests for StandardsClient, source fetchers, and identifier resolver."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from scholar_mcp._rate_limiter import RateLimiter
from scholar_mcp._standards_client import (
    _CSRC_PUBS_EXPORT_URL,
    _NIST_CACHE_FILE,
    StandardsClient,
    StandardsUpstreamError,
    _ETSIFetcher,
    _IETFFetcher,
    _NISTFetcher,
    _spell_mods_sp_number,
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


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        # The IR series with a space or NIST's DOI dots (#598).
        ("nist ir 8259", "NISTIR 8259"),
        ("NIST.IR.8259", "NISTIR 8259"),
        # NIST's DOI form of an SP.
        ("NIST.SP.800-53r5", "NIST SP 800-53 Rev. 5"),
        # An edition dash is part of the number: 800-63-3 is not 800-63.
        ("nist sp 800-63-3", "NIST SP 800-63-3"),
        ("NIST SP 800-73-4", "NIST SP 800-73-4"),
        ("NIST SP 800-63B-4", "NIST SP 800-63B-4"),
        # A letter before a compact revision stays with the number.
        ("SP800-53Ar4", "NIST SP 800-53A Rev. 4"),
        # Part, volume, version and edition, spelled out or compact.
        ("NIST SP 800-57 Part 1 Rev. 4", "NIST SP 800-57 Part 1 Rev. 4"),
        ("NIST.SP.800-57pt1r5", "NIST SP 800-57 Part 1 Rev. 5"),
        ("NIST SP 800-160 Vol. 2", "NIST SP 800-160 Vol. 2"),
        ("NIST.SP.800-160v1r1", "NIST SP 800-160 Vol. 1 Rev. 1"),
        ("NIST SP 800-55 Volume 1", "NIST SP 800-55 Vol. 1"),
        ("NIST SP 800-40 Version 2", "NIST SP 800-40 Version 2"),
        ("NIST SP 800-21 E2", "NIST SP 800-21 E2"),
        # A compact marker after a space is a page reference, not a part.
        ("NIST SP 800-53 p 12", "NIST SP 800-53"),
    ],
)
def test_resolve_nist_keeps_the_whole_document_number(raw: str, canonical: str) -> None:
    """Each form names one publication; none may lose part of its number."""
    assert resolve_identifier_local(raw) == (canonical, "NIST")


@pytest.mark.parametrize(
    ("number", "spelled"),
    [
        ("800-57pt1", "800-57 Part 1"),
        ("800-57p2", "800-57 Part 2"),
        ("800-160v2", "800-160 Vol. 2"),
        ("800-28ver2", "800-28 Version 2"),
        ("800-21e2", "800-21 E2"),
        # A four-digit "e" is a year, not an edition.
        ("260e1969", "260e1969"),
        # Two markers, or a dotted volume, are left as MODS writes them.
        ("535v1p1", "535v1p1"),
        ("500-268v1.1", "500-268v1.1"),
        ("800-53", "800-53"),
    ],
)
def test_mods_sp_number_spells_out_parts_and_volumes(number: str, spelled: str) -> None:
    """The catalogue spells an SP the way CSRC and the resolver do (#598)."""
    assert _spell_mods_sp_number(number) == spelled


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


@pytest.mark.parametrize(
    ("shorthand", "with_sp"),
    [
        ("nist 800-53r5", "nist sp 800-53r5"),
        ("nist 800-171r2", "nist sp 800-171r2"),
        ("nist 800-53 rev. 5", "nist sp 800-53 rev. 5"),
        ("nist 800-53 rev 5", "nist sp 800-53 rev 5"),
        ("nist 800-63b", "nist sp 800-63b"),
        ("nist 800-63b rev 1", "nist sp 800-63b rev 1"),
        ("nist 800-53", "nist sp 800-53"),
    ],
)
def test_resolve_nist_shorthand_matches_sp_form(shorthand: str, with_sp: str) -> None:
    # The form without "sp" names the same publication as the form with it
    # (#585): neither the compact revision nor a letter suffix may cut the
    # document number back to "800".
    assert resolve_identifier_local(shorthand) == resolve_identifier_local(with_sp)


def test_resolve_nist_shorthand_compact_revision() -> None:
    result = resolve_identifier_local("nist 800-53r5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


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


# --- Resolver: ISO / IEC ---


def test_resolve_identifier_iso_plain() -> None:
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("ISO 9001:2015") == ("ISO 9001:2015", "ISO")


def test_resolve_identifier_iso_no_space() -> None:
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("ISO9001:2015") == ("ISO 9001:2015", "ISO")


def test_resolve_identifier_iso_iec_joint() -> None:
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("ISO/IEC 27001:2022") == (
        "ISO/IEC 27001:2022",
        "ISO/IEC",
    )


def test_resolve_identifier_iso_iec_joint_reversed() -> None:
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("IEC/ISO 27001:2022") == (
        "ISO/IEC 27001:2022",
        "ISO/IEC",
    )


def test_resolve_identifier_iec_only() -> None:
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("IEC 62443-3-3:2020") == (
        "IEC 62443-3-3:2020",
        "IEC",
    )


def test_resolve_identifier_iso_multipart_number() -> None:
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("ISO 15189-2:2022") == (
        "ISO 15189-2:2022",
        "ISO",
    )


def test_resolve_identifier_bare_number_not_matched() -> None:
    """Bare '27001:2022' (no body prefix) is ambiguous — return None."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("27001:2022") is None


# --- Resolver: IEEE ---


def test_resolve_ieee_plain() -> None:
    """Plain IEEE identifier resolves to (canonical, 'IEEE')."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("IEEE 802.11-2020") == ("IEEE 802.11-2020", "IEEE")
    assert resolve_identifier_local("IEEE 1003.1-2024") == ("IEEE 1003.1-2024", "IEEE")


def test_resolve_ieee_std_variant() -> None:
    """`IEEE Std X-YYYY` form is accepted."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("IEEE Std 1588-2019")
    assert result is not None
    identifier, body = result
    assert body == "IEEE"
    assert "1588" in identifier
    assert "2019" in identifier


def test_resolve_iec_ieee_joint_dispatches_to_ieee() -> None:
    """IEC/IEEE joint → canonical form kept, dispatch body is 'IEEE'.

    The dispatch body ('IEEE') must match a StandardsClient._fetchers key.
    The record's body field (set by _yaml_to_record) will be 'IEC/IEEE'.
    """
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("IEC/IEEE 61588-2021")
    assert result is not None
    identifier, body = result
    assert identifier == "IEC/IEEE 61588-2021"
    assert body == "IEEE"  # dispatch body, not record body


def test_resolve_iso_iec_ieee_joint_dispatches_to_ieee() -> None:
    """ISO/IEC/IEEE triple-joint → dispatch body 'IEEE'."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("ISO/IEC/IEEE 42010-2011")
    assert result is not None
    identifier, body = result
    assert identifier == "ISO/IEC/IEEE 42010-2011"
    assert body == "IEEE"


@pytest.mark.asyncio
async def test_standards_client_search_ieee_delegates_to_relaton() -> None:
    """search(body='IEEE') → RelatonLiveFetcher.search() with source='IEEE'."""
    from unittest.mock import AsyncMock

    from scholar_mcp._record_types import StandardRecord
    from scholar_mcp._standards_client import StandardsClient

    record: StandardRecord = {
        "identifier": "IEEE 1003.1-2024",
        "title": "POSIX Base Specifications",
        "body": "IEEE",
        "status": "published",
        "full_text_available": False,
    }
    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[record])

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http, cache=mock_cache)
        results = await client.search("1003", body="IEEE")

    mock_cache.search_synced_standards.assert_awaited_once_with(
        "1003", source="IEEE", limit=10
    )
    assert len(results) == 1
    assert results[0]["identifier"] == "IEEE 1003.1-2024"


@pytest.mark.asyncio
async def test_standards_client_fetchers_ieee_instance_registered() -> None:
    """_fetchers['IEEE'] is a RelatonLiveFetcher with source='IEEE'."""
    from scholar_mcp._relaton_live import RelatonLiveFetcher
    from scholar_mcp._standards_client import StandardsClient

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http)
        fetcher = client._fetchers["IEEE"]

    assert isinstance(fetcher, RelatonLiveFetcher)
    assert fetcher._source == "IEEE"


# ---------------------------------------------------------------------------
# IETF fetcher tests
# ---------------------------------------------------------------------------

IETF_BASE = "https://datatracker.ietf.org"
RFC_EDITOR_BASE = "https://www.rfc-editor.org"

# Shape of datatracker /api/v1/doc/relateddocument/?relationship=obs (#637)
# for an RFC nothing obsoletes.
NO_OBSOLETING_RFCS: dict = {"meta": {"next": None}, "objects": []}  # type: ignore[type-arg]

# Shape of datatracker /api/v1/doc/docevent/?type=published_rfc (#631).
RFC9000_PUB_EVENTS = {
    "meta": {"total_count": 1},
    "objects": [
        {
            "doc": "/api/v1/doc/document/rfc9000/",
            "time": "2021-05-27T15:32:44Z",
            "type": "published_rfc",
        }
    ],
}

SAMPLE_RFC9000_DOC = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "abstract": "This document defines QUIC.",
            "std_level": "/api/v1/name/stdlevelname/ps/",
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
            "std_level": "/api/v1/name/stdlevelname/ps/",
            "resource_uri": "/api/v1/doc/document/rfc9000/",
        }
    ],
    "meta": {"total_count": 1},
}


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_rfc(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json=RFC9000_PUB_EVENTS)
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
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
    assert record["published_date"] == "2021-05"
    assert record["status"] == "published"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_historic_rfc_is_withdrawn(
    respx_mock: respx.MockRouter,
) -> None:
    """std_level arrives as a URI; its slug decides the status (#631)."""
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "doc": "/api/v1/doc/document/rfc2246/",
                        "time": "1999-01-01T08:00:00Z",
                        "type": "published_rfc",
                    }
                ]
            },
        )
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "name": "rfc2246",
                        "title": "The TLS Protocol Version 1.0",
                        "std_level": "/api/v1/name/stdlevelname/hist/",
                    }
                ]
            },
        )
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 2246")
    await http.aclose()
    assert record is not None
    assert record["status"] == "withdrawn"
    assert record["published_date"] == "1999-01"


@pytest.mark.respx(base_url=IETF_BASE)
@pytest.mark.parametrize(
    "date_response",
    [httpx.Response(503), httpx.ConnectError("no route to host")],
    ids=["status", "transport"],
)
async def test_ietf_get_keeps_record_when_date_lookup_fails(
    respx_mock: respx.MockRouter, date_response: object
) -> None:
    """A failed date lookup costs the date, not the record."""
    route = respx_mock.get("/api/v1/doc/docevent/")
    if isinstance(date_response, Exception):
        route.mock(side_effect=date_response)
    else:
        route.mock(return_value=date_response)
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_DOC)
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 9000")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "RFC 9000"
    assert record["published_date"] is None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_search_looks_up_dates_in_one_request(
    respx_mock: respx.MockRouter,
) -> None:
    """search() asks for every result's date at once, not once per row."""
    rows = [
        {
            "name": "rfc9000",
            "title": "QUIC",
            "std_level": "/api/v1/name/stdlevelname/ps/",
        },
        {
            "name": "rfc9001",
            "title": "QUIC TLS",
            "std_level": "/api/v1/name/stdlevelname/ps/",
        },
    ]
    events = respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "doc": "/api/v1/doc/document/rfc9000/",
                        "time": "2021-05-27T15:32:44Z",
                    },
                    {
                        "doc": "/api/v1/doc/document/rfc9001/",
                        "time": "2021-05-27T15:33:01Z",
                    },
                ]
            },
        )
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json={"objects": rows})
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("QUIC", limit=5)
    await http.aclose()
    assert events.call_count == 1
    params = events.calls.last.request.url.params
    assert params["doc__name__in"] == "rfc9000,rfc9001"
    assert params["type"] == "published_rfc"
    assert [r["published_date"] for r in results] == ["2021-05", "2021-05"]


def _obs(source: str, target: str) -> dict:  # type: ignore[type-arg]
    """One datatracker relateddocument row: ``source`` obsoletes ``target``."""
    return {
        "relationship": "/api/v1/name/docrelationshipname/obs/",
        "source": f"/api/v1/doc/document/{source}/",
        "target": f"/api/v1/doc/document/{target}/",
    }


def _rfc_doc(name: str, std_level: str) -> dict:  # type: ignore[type-arg]
    return {
        "objects": [
            {
                "name": name,
                "title": name.upper(),
                "std_level": f"/api/v1/name/stdlevelname/{std_level}/",
            }
        ]
    }


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_obsoleted_rfc_lists_replacements(
    respx_mock: respx.MockRouter,
) -> None:
    """An obsoleted RFC is superseded, listing every obsoleting RFC (#637)."""
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    relations = respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(
            200,
            json={
                "meta": {"next": None},
                # datatracker returns rows in no promised order
                "objects": [_obs(f"rfc{n}", "rfc2616") for n in (7235, 7230, 7231)],
            },
        )
    )
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=_rfc_doc("rfc2616", "ds"))
    )
    http = httpx.AsyncClient()
    record = await _IETFFetcher(http, RateLimiter(delay=0.0)).get("RFC 2616")
    await http.aclose()
    assert record is not None
    assert record["status"] == "superseded"
    assert record["superseded_by"] == ["RFC 7230", "RFC 7231", "RFC 7235"]
    params = relations.calls.last.request.url.params
    assert params["target__name__in"] == "rfc2616"
    assert params["relationship"] == "obs"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_obsoleted_historic_rfc_is_superseded(
    respx_mock: respx.MockRouter,
) -> None:
    """Replacement outranks Historic: RFC 2246 points at RFC 4346 (#637)."""
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json={"objects": [_obs("rfc4346", "rfc2246")]})
    )
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=_rfc_doc("rfc2246", "hist"))
    )
    http = httpx.AsyncClient()
    record = await _IETFFetcher(http, RateLimiter(delay=0.0)).get("RFC 2246")
    await http.aclose()
    assert record is not None
    assert record["status"] == "superseded"
    assert record["superseded_by"] == ["RFC 4346"]


@pytest.mark.respx(base_url=IETF_BASE)
@pytest.mark.parametrize(
    "obs_response",
    [httpx.Response(503), httpx.ConnectError("no route to host")],
    ids=["status", "transport"],
)
async def test_ietf_get_raises_when_obsoleted_by_lookup_fails(
    respx_mock: respx.MockRouter, obs_response: object
) -> None:
    """No answer on replacements must not read, and cache, as published."""
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json=RFC9000_PUB_EVENTS)
    )
    route = respx_mock.get("/api/v1/doc/relateddocument/")
    if isinstance(obs_response, Exception):
        route.mock(side_effect=obs_response)
    else:
        route.mock(return_value=obs_response)
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_DOC)
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    with pytest.raises(StandardsUpstreamError) as exc_info:
        await fetcher.get("RFC 9000")
    await http.aclose()
    assert exc_info.value.body == "IETF"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_search_looks_up_replacements_in_one_request(
    respx_mock: respx.MockRouter,
) -> None:
    """search() asks which RFCs obsolete each hit in a single request."""
    rows = [
        {"name": "rfc2616", "title": "HTTP/1.1", "std_level": "ds"},
        {"name": "rfc9110", "title": "HTTP Semantics", "std_level": "std"},
    ]
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    relations = respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(
            200,
            json={
                "meta": {"next": "/api/v1/doc/relateddocument/?offset=1000"},
                "objects": [_obs("rfc7230", "rfc2616")],
            },
        )
    )
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json={"objects": rows})
    )
    http = httpx.AsyncClient()
    results = await _IETFFetcher(http, RateLimiter(delay=0.0)).search("HTTP")
    await http.aclose()
    assert relations.call_count == 1
    assert relations.calls.last.request.url.params["target__name__in"] == (
        "rfc2616,rfc9110"
    )
    assert [(r["status"], r["superseded_by"]) for r in results] == [
        ("superseded", ["RFC 7230"]),
        ("published", []),
    ]


def test_group_obsoleting_rfcs_skips_non_rfc_sources() -> None:
    """Only a published RFC replaces one; a draft source is ignored."""
    from scholar_mcp._standards_client import _group_obsoleting_rfcs

    grouped = _group_obsoleting_rfcs(
        [
            _obs("draft-ietf-httpbis-semantics", "rfc7231"),
            _obs("rfc9110", "rfc7231"),
            _obs("rfc9110", "rfc7231"),
            {"source": None, "target": "/api/v1/doc/document/rfc1/"},
        ]
    )
    assert grouped == {"rfc7231": ["RFC 9110"]}


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
                        "std_level": None,
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
    # No date request for a sub-series: respx would fail an unmocked call.
    assert record["published_date"] is None
    assert record["identifier"] == "BCP 47"
    assert record["url"] == "https://www.rfc-editor.org/info/bcp47"
    assert record["full_text_available"] is False


@pytest.mark.respx(base_url=IETF_BASE)
@pytest.mark.parametrize(
    ("identifier", "name"),
    [
        ("RFC 793", "rfc793"),
        ("RFC 1", "rfc1"),
        ("RFC 9000", "rfc9000"),
        ("BCP 47", "bcp47"),
    ],
)
async def test_ietf_get_asks_for_unpadded_name(
    respx_mock: respx.MockRouter, identifier: str, name: str
) -> None:
    """datatracker names RFCs without zero padding; rfc0793 matches nothing (#633)."""
    route = respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    await fetcher.get(identifier)
    await http.aclose()
    assert route.calls.last.request.url.params["name"] == name


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
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json=RFC9000_PUB_EVENTS)
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
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
    }
    record = _normalize_ietf(obj)
    assert record["status"] == "published"


def test_normalize_ietf_bcp_name() -> None:
    from scholar_mcp._standards_client import _normalize_ietf

    obj = {
        "name": "bcp47",
        "title": "Tags for Identifying Languages",
        "std_level": None,
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
        "name": "rfc1",
        "title": "Host Software",
        "std_level": "/api/v1/name/stdlevelname/unkn/",
    }
    record = _normalize_ietf(obj)
    assert record["status"] == "draft"
    assert record["identifier"] == "RFC 1"
    assert record["number"] == "1"
    assert record["full_text_url"] is not None
    # datatracker names RFCs without zero padding (#633), and the URL uses that name
    assert record["full_text_url"].startswith("https://www.rfc-editor.org/rfc/rfc1.")


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

NIST_FIXTURES = Path(__file__).parent / "fixtures" / "standards" / "nist"
# Verbatim entries of CSRC's pubs-export.json (Last-Modified 2026-11-14) and
# the matching <mods> records of NIST-Tech-Pubs release Oct2026 (#639).
CSRC_EXPORT_ENTRIES = json.loads(
    (NIST_FIXTURES / "csrc_pubs_export_sample.json").read_text(encoding="utf-8")
)
CSRC_MODS_XML = (NIST_FIXTURES / "mods_sample.xml").read_bytes()


def _csrc_export_zip(entries: object) -> bytes:
    """Pack export entries the way CSRC serves them: one JSON file in a zip."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("pubs-export.json", json.dumps(entries))
    return buffer.getvalue()


def _mock_csrc_export(
    respx_mock: respx.MockRouter, response: httpx.Response | None = None
) -> respx.Route:
    """Serve CSRC's publications export, by default with no entries."""
    return respx_mock.get(_CSRC_PUBS_EXPORT_URL).mock(
        return_value=response or httpx.Response(200, content=_csrc_export_zip([]))
    )


SAMPLE_MODS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<modsCollection xmlns="http://www.loc.gov/mods/v3">
  <mods version="3.7">
    <titleInfo>
      <title>Report on the static analysis tool exposition (SATE) IV</title>
    </titleInfo>
    <originInfo eventType="publisher">
      <dateIssued>2013.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.SP.500-297</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>NIST special publication; NIST special pub; NIST SP</title>
        <partNumber></partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.SP.500-297</identifier>
  </mods>
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
    _mock_csrc_export(respx_mock)
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
    _mock_csrc_export(respx_mock)
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
    _mock_csrc_export(respx_mock)
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
    _mock_csrc_export(respx_mock)
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 999-99")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get_ignores_malformed_catalogue_entry(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """A catalogue entry carrying no part number never stands in for a real one.

    NIST publishes records whose series partNumber is empty; they normalise to
    the bare identifier "NIST SP ", which is a prefix of every other SP
    identifier. Matching on substrings therefore returned that one entry for
    thousands of requests (#400).
    """
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    _mock_csrc_export(respx_mock)
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 800-53 Rev. 5")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "NIST SP 800-53 Rev. 5"


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get_absent_identifier_does_not_match_a_prefix(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """An identifier absent from the catalogue resolves to nothing."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    _mock_csrc_export(respx_mock)
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 800-92")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get_does_not_widen_to_a_longer_identifier(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """get() never substitutes a longer identifier for the one asked for.

    "NIST SP 800-53" is a real publication line but not a catalogue entry; the
    entries are per-revision. Returning Rev. 5 for it picked whichever revision
    came first in document order rather than the current one, so the honest
    answer is that the canonical identifier asked for is not in the catalogue.
    """
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    _mock_csrc_export(respx_mock)
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 800-53")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_disk_cache_used_on_second_call(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Second fetcher instance loads from disk cache, no network call."""
    call_count = 0

    def side_effect(request):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=SAMPLE_MODS_XML)

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        side_effect=side_effect
    )
    _mock_csrc_export(respx_mock)
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

    def side_effect(request):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=SAMPLE_MODS_XML)

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        side_effect=side_effect
    )
    _mock_csrc_export(respx_mock)
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
    _mock_csrc_export(respx_mock)
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
    cache_path = tmp_path / _NIST_CACHE_FILE
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
    _mock_csrc_export(respx_mock)
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
    cache_path = tmp_path / _NIST_CACHE_FILE
    cache_path.write_text("not valid json {{", encoding="utf-8")

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    _mock_csrc_export(respx_mock)
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert len(results) == 1


async def test_nist_disk_cache_from_before_637_reads_superseded_by_as_a_list(
    tmp_path,
) -> None:
    """A catalogue file written with superseded_by: null is still served.

    No route is mocked, so a download attempt would fail the test.
    """
    cache_path = tmp_path / _NIST_CACHE_FILE
    cache_path.write_text(
        json.dumps(
            [
                {
                    "identifier": "NIST SP 800-53 Rev. 5",
                    "title": "Security and Privacy Controls",
                    "number": "800-53",
                    "superseded_by": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert [r["superseded_by"] for r in results] == [[]]


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_disk_cache_that_is_not_a_list_triggers_re_download(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    cache_path = tmp_path / _NIST_CACHE_FILE
    cache_path.write_text('{"not": "a list"}', encoding="utf-8")
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    _mock_csrc_export(respx_mock)
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
    _mock_csrc_export(respx_mock)
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
    _mock_csrc_export(respx_mock)
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("8166", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "NISTIR 8166"
    assert results[0]["body"] == "NIST"


async def _csrc_fetcher_get(
    respx_mock: respx.MockRouter, tmp_path: Path, identifier: str
) -> dict[str, object] | None:
    """Look ``identifier`` up in the real-data fixtures, CSRC export included."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=CSRC_MODS_XML)
    )
    _mock_csrc_export(
        respx_mock,
        httpx.Response(200, content=_csrc_export_zip(CSRC_EXPORT_ENTRIES)),
    )
    async with httpx.AsyncClient(base_url=GITHUB_RELEASES_URL) as http:
        fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
        record = await fetcher.get(identifier)
    return dict(record) if record is not None else None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        # The issue's example: one entry, withdrawn, naming its replacement.
        ("FIPS 186-4", ("superseded", ["FIPS 186-5"], "2024-02-03")),
        # Four update entries; three "supersede" each other under the same
        # identifier, only upd3 names a different publication.
        (
            "NIST SP 800-53 Rev. 4",
            ("superseded", ["NIST SP 800-53 Rev. 5"], "2021-09-23"),
        ),
        # The newest entry is active, yet names FIPS 140-3: the replacement
        # outranks the stated status (#637).
        ("FIPS 140-2", ("superseded", ["FIPS 140-3"], None)),
        # A replacement in the IR series is spelled the catalogue's way.
        ("FIPS 39", ("superseded", ["NISTIR 7298"], "1993-04-29")),
        # Withdrawn with no replacement named.
        ("NIST SP 800-106", ("withdrawn", [], "2022-12-15")),
        # An older final entry and a draft are withdrawn; the newest final
        # entry is active.
        ("FIPS 197", ("published", [], None)),
        ("NIST SP 800-53 Rev. 5", ("published", [], None)),
        # CSRC does not list it: the MODS reading stands.
        ("NISTIR 7298", ("published", [], None)),
        # MODS writes "800-57pt1r4" and "800-28ver2"; CSRC spells them out,
        # and so does the catalogue now (#598).
        (
            "NIST SP 800-57 Part 1 Rev. 4",
            ("superseded", ["NIST SP 800-57 Part 1 Rev. 5"], "2020-05-04"),
        ),
        ("NIST SP 800-28 Version 2", ("published", [], None)),
    ],
)
async def test_nist_get_reports_csrc_withdrawal_and_replacement(
    respx_mock: respx.MockRouter,
    tmp_path: Path,
    identifier: str,
    expected: tuple[str, list[str], str | None],
) -> None:
    """Status, superseded_by and withdrawn_date, in that order."""
    record = await _csrc_fetcher_get(respx_mock, tmp_path, identifier)
    assert record is not None
    assert (
        record["status"],
        record["superseded_by"],
        record["withdrawn_date"],
    ) == expected


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
@pytest.mark.parametrize(
    "legacy_name", ["nist_catalogue.json", "nist_catalogue_csrc.json"]
)
async def test_nist_catalogue_cached_with_csrc_data_and_legacy_file_removed(
    respx_mock: respx.MockRouter, tmp_path: Path, legacy_name: str
) -> None:
    """The catalogue on disk carries CSRC's data; older files are gone.

    A file written before #639 says every publication is published, and one
    written before #598 names SP parts and volumes the old way, so neither is
    read nor left behind.
    """
    legacy = tmp_path / legacy_name
    legacy.write_text(
        json.dumps([{"identifier": "FIPS 186-4", "status": "published"}]),
        encoding="utf-8",
    )
    record = await _csrc_fetcher_get(respx_mock, tmp_path, "FIPS 186-4")
    assert record is not None
    assert record["status"] == "superseded"
    assert not legacy.exists()
    stored = json.loads((tmp_path / _NIST_CACHE_FILE).read_text(encoding="utf-8"))
    assert {r["identifier"]: r["status"] for r in stored}["FIPS 186-4"] == (
        "superseded"
    )


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
@pytest.mark.parametrize(
    "export",
    [
        httpx.Response(503),
        httpx.Response(200, content=b"<html>maintenance</html>"),
        httpx.Response(200, content=_csrc_export_zip({"not": "a list"})),
        httpx.ConnectError("refused"),
    ],
    ids=["refused", "not-a-zip", "not-a-list", "unreachable"],
)
async def test_nist_export_failure_raises_and_caches_nothing(
    respx_mock: respx.MockRouter,
    tmp_path: Path,
    export: httpx.Response | Exception,
) -> None:
    """Without the export, a withdrawn publication would read as published.

    No MODS route is registered: the 84 MB catalogue is not downloaded when
    the export already failed, and a request for it would fail this test.
    """
    route = respx_mock.get(_CSRC_PUBS_EXPORT_URL)
    if isinstance(export, Exception):
        route.mock(side_effect=export)
    else:
        route.mock(return_value=export)
    async with httpx.AsyncClient(base_url=GITHUB_RELEASES_URL) as http:
        fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
        with pytest.raises(StandardsUpstreamError) as caught:
            await fetcher.get("FIPS 186-4")
    assert caught.value.body == "NIST"
    assert not (tmp_path / _NIST_CACHE_FILE).exists()


# ---------------------------------------------------------------------------
# W3C fetcher tests
# ---------------------------------------------------------------------------

W3C_API_BASE = "https://api.w3.org"

# Shape of https://api.w3.org/specifications/WCAG21 as served 2026-11-14,
# description shortened. The object has no top-level status or date (#630).
SAMPLE_W3C_SPEC = {
    "shortlink": "https://www.w3.org/TR/WCAG21/",
    "description": "<p>Web Content Accessibility Guidelines (WCAG) 2.1 covers a wide range of recommendations for making Web content more accessible.</p>",
    "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
    "shortname": "WCAG21",
    "editor-draft": "https://w3c.github.io/wcag/guidelines/",
    "series-version": "2.1",
    "_links": {
        "self": {"href": "https://api.w3.org/specifications/WCAG21"},
        "version-history": {
            "href": "https://api.w3.org/specifications/WCAG21/versions"
        },
        "first-version": {
            "href": "https://api.w3.org/specifications/WCAG21/versions/20170228",
            "title": "First Public Working Draft",
        },
        "latest-version": {
            "href": "https://api.w3.org/specifications/WCAG21/versions/20250506",
            "title": "Recommendation",
        },
        "series": {"href": "https://api.w3.org/specification-series/wcag"},
    },
}

# Shape of https://api.w3.org/specifications/html401 as served 2026-11-14.
SAMPLE_W3C_RETIRED_SPEC = {
    "shortlink": "https://www.w3.org/TR/html401/",
    "description": "<p>This specification defines the HyperText Markup Language (HTML).</p>",
    "title": "HTML 4.01 Specification",
    "shortname": "html401",
    "series-version": "4.01",
    "_links": {
        "self": {"href": "https://api.w3.org/specifications/html401"},
        "latest-version": {
            "href": "https://api.w3.org/specifications/html401/versions/20180327",
            "title": "Retired",
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

    def page_side_effect(req):  # type: ignore[no-untyped-def]  # noqa: ARG001
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
# ETSI fetcher tests (standards search data endpoint)
# ---------------------------------------------------------------------------

ETSI_BASE = "https://www.etsi.org"
ETSI_DATA_PATH = "/custom/standardssearch/data.php"

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
    """search() calls the data endpoint and returns parsed records."""
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON)
    )
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
async def test_etsi_search_non200_raises(respx_mock: respx.MockRouter) -> None:
    """A refused request is not an empty result set (#401).

    This assertion is the inverse of the one it replaces. Returning ``[]`` here
    is what made an outage indistinguishable from "ETSI publishes no such
    standard", which is the opposite of what a 403 means.
    """
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    with pytest.raises(StandardsUpstreamError) as excinfo:
        await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert excinfo.value.body == "ETSI"
    assert excinfo.value.status == 403


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_html_body_raises(respx_mock: respx.MockRouter) -> None:
    """The reported failure: 200 carrying the ETSI homepage instead of JSON.

    [observed 2026-09-19] The live endpoint answers 200 with
    ``content-type: text/html`` and a body opening ``<!doctype html>``. The
    status alone reads as success, so the detail has to carry the reason.
    """
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="<!doctype html><html><head><title>ETSI</title></head></html>",
        )
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    with pytest.raises(StandardsUpstreamError) as excinfo:
        await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert excinfo.value.status == 200
    assert excinfo.value.detail


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_transport_error_raises(
    respx_mock: respx.MockRouter,
) -> None:
    """A request that never reached ETSI carries no status."""
    respx_mock.get(ETSI_DATA_PATH).mock(
        side_effect=httpx.ConnectError("no route to host")
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    with pytest.raises(StandardsUpstreamError) as excinfo:
        await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert excinfo.value.status is None


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_non_list_json_raises(respx_mock: respx.MockRouter) -> None:
    """Valid JSON of the wrong shape is still an answer this client cannot read."""
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json={"error": "unavailable"})
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    with pytest.raises(StandardsUpstreamError):
        await fetcher.search("303 645", limit=5)
    await http.aclose()


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_propagates_upstream_error(
    respx_mock: respx.MockRouter,
) -> None:
    """get() must not turn a refused request into None, which reads as absent."""
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    with pytest.raises(StandardsUpstreamError):
        await fetcher.get("ETSI EN 303 645")
    await http.aclose()


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get(respx_mock: respx.MockRouter) -> None:
    """get() returns the row matching the identifier."""
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON)
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 303 645")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "ETSI EN 303 645"
    assert record["body"] == "ETSI"
    assert record["full_text_available"] is True


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_not_found(respx_mock: respx.MockRouter) -> None:
    """get() returns None when no match."""
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(200, json=[]))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 999 999")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_normalize_pdf_url(respx_mock: respx.MockRouter) -> None:
    """PDF URL constructed from EDSpathname + EDSPDFfilename."""
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON)
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=1)
    await http.aclose()
    expected_pdf = "https://www.etsi.org/deliver/etsi_en/303600_303699/303645/03.01.03_60/en_303645v030103p.pdf"
    assert results[0]["full_text_url"] == expected_pdf
    assert results[0]["url"] == expected_pdf


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_requests_data_endpoint(respx_mock: respx.MockRouter) -> None:
    """search() asks data.php for title and number matches, with scope text.

    ``content=1`` also matches document text, which made an unknown identifier
    return thousands of unrelated rows; without ``includeScope=1`` every row's
    ``Scope`` is null (#624).
    """
    route = respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=[])
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    await fetcher.search("ETSI EN 303 645")
    await http.aclose()
    params = route.calls.last.request.url.params
    assert params["search"] == "ETSI EN 303 645"
    assert params["content"] == "0"
    assert params["includeScope"] == "1"
    assert "option" not in params
    # Keyword results leave out old editions; only get() asks for them (#640).
    assert (params["withdrawn"], params["historical"], params["superseded"]) == (
        "0",
        "0",
        "0",
    )


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_skips_rows_for_other_identifiers(
    respx_mock: respx.MockRouter,
) -> None:
    """get() returns the row for the requested identifier, not the first row.

    A search for ``ETSI EN 303 645`` also returns ``ETSI TS 103 929``, whose
    title mentions it, so the first row is not necessarily the one asked for.
    """
    other = {
        **SAMPLE_ETSI_JSON[1],
        "ETSI_DELIVERABLE": "ETSI TS 103 929 V1.2.1 (2023-05)",
    }
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=[other, SAMPLE_ETSI_JSON[0]])
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("etsi en  303 645")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "ETSI EN 303 645"


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_none_when_only_other_identifiers(
    respx_mock: respx.MockRouter,
) -> None:
    """Rows for other deliverables are not a match for the one asked for."""
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=[SAMPLE_ETSI_JSON[1]])
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 303 645")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_normalize_row_fields(respx_mock: respx.MockRouter) -> None:
    """Title, version, date, status, scope and committee map from a row."""
    withdrawn = {**SAMPLE_ETSI_JSON[1], "ACTION_TYPE": "WD"}
    respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, json=[SAMPLE_ETSI_JSON[0], withdrawn])
    )
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    first, second = await fetcher.search("303 645")
    await http.aclose()
    assert first["identifier"] == "ETSI EN 303 645"
    assert first["aliases"] == ["ETSI EN 303 645 V3.1.3 (2024-09)"]
    assert first["number"] == "303 645"
    assert first["title"] == (
        "CYBER; Cyber Security for Consumer Internet of Things: Baseline Requirements"
    )
    assert first["revision"] == "3.1.3"
    assert first["published_date"] == "2024-09"
    assert first["status"] == "published"
    assert (
        first["scope"] == "Transposition of TS 103 645 v3.1.1 into an updated version."
    )
    assert first["committee"] == "Cyber Security"
    assert second["status"] == "withdrawn"
    assert second["scope"] is None


# ---------------------------------------------------------------------------
# StandardsClient integration tests
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=IETF_BASE)
async def test_standards_client_resolve_ietf_local(
    respx_mock: respx.MockRouter,
) -> None:
    """Local resolution needs no network call for well-known RFCs."""
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json=RFC9000_PUB_EVENTS)
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
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
    respx_mock.get("/api/v1/doc/docevent/").mock(
        return_value=httpx.Response(200, json=RFC9000_PUB_EVENTS)
    )
    respx_mock.get("/api/v1/doc/relateddocument/").mock(
        return_value=httpx.Response(200, json=NO_OBSOLETING_RFCS)
    )
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


def _w3c_spec_with_status(status_title: str) -> dict:  # type: ignore[type-arg]
    links = dict(SAMPLE_W3C_SPEC["_links"])  # type: ignore[call-overload]
    links["latest-version"] = {**links["latest-version"], "title": status_title}
    return {**SAMPLE_W3C_SPEC, "_links": links}


@pytest.mark.parametrize(
    ("status_title", "expected"),
    [
        ("Recommendation", "published"),
        ("Working Draft", "draft"),
        ("Retired", "superseded"),
        ("Superseded Recommendation", "superseded"),
    ],
)
def test_normalize_w3c_status_from_latest_version(
    status_title: str, expected: str
) -> None:
    """Status comes from the latest version link's title, the only place it is."""
    from scholar_mcp._standards_client import _normalize_w3c

    assert _normalize_w3c(_w3c_spec_with_status(status_title))["status"] == expected


def test_normalize_w3c_reads_api_shape() -> None:
    """URL, date and identifier come from the keys the API actually sends."""
    from scholar_mcp._standards_client import _normalize_w3c

    record = _normalize_w3c(SAMPLE_W3C_RETIRED_SPEC)
    assert record["identifier"] == "html401"
    assert record["aliases"] == ["HTML 4.01 Specification"]
    assert record["url"] == "https://www.w3.org/TR/html401/"
    assert record["full_text_url"] == "https://www.w3.org/TR/html401/"
    assert record["published_date"] == "2018-03-27"
    assert record["status"] == "superseded"


def test_normalize_w3c_mapped_shortname_keeps_resolver_name() -> None:
    """A shortname the resolver knows by name is reported under that name."""
    from scholar_mcp._standards_client import _normalize_w3c

    record = _normalize_w3c(SAMPLE_W3C_SPEC)
    assert record["identifier"] == "WCAG 2.1"
    assert record["aliases"] == [
        "WCAG21",
        "Web Content Accessibility Guidelines (WCAG) 2.1",
    ]


def test_normalize_w3c_no_shortlink_falls_back_to_tr() -> None:
    from scholar_mcp._standards_client import _normalize_w3c

    spec = {"shortname": "myspec", "title": "My Spec"}
    record = _normalize_w3c(spec)
    assert record["url"] == "https://www.w3.org/TR/myspec/"
    assert record["status"] == "published"
    assert record["published_date"] is None


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_identifier_round_trips_through_get(
    respx_mock: respx.MockRouter,
) -> None:
    """get() finds a record by the identifier search() returned for it (#630)."""
    respx_mock.get("/specifications").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "pages": 1,
                "_links": {
                    "specifications": [
                        {
                            "href": "https://api.w3.org/specifications/html401",
                            "title": "HTML 4.01 Specification",
                        }
                    ]
                },
            },
        )
    )
    respx_mock.get("/specifications/html401").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_RETIRED_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    (found,) = await fetcher.search("HTML 4.01")
    again = await fetcher.get(found["identifier"])
    await http.aclose()
    assert again is not None
    assert again["identifier"] == found["identifier"]


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
        mock.get(url__regex=r"csrc\.nist\.gov").mock(
            return_value=httpx.Response(200, content=_csrc_export_zip([]))
        )
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
        mock.get(url__regex=r"csrc\.nist\.gov").mock(
            return_value=httpx.Response(200, content=_csrc_export_zip([]))
        )
        mock.get(url__regex=r"api\.w3\.org").mock(return_value=httpx.Response(404))
        mock.get(url__regex=r"www\.etsi\.org").mock(
            return_value=httpx.Response(200, json=[])
        )
        http = httpx.AsyncClient()
        client = StandardsClient(http)
        result = await client.get("some-unknown-standard-xyz")
        await http.aclose()
    assert result is None


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_search_with_failures_reports_a_refused_body(
    respx_mock: respx.MockRouter,
) -> None:
    """A body that refused the request is reported, not returned as empty."""
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    records, failures = await client.search_with_failures("QUIC", body="ETSI", limit=5)
    await http.aclose()
    assert records == []
    assert [f.body for f in failures] == ["ETSI"]
    assert failures[0].status == 403


async def test_search_all_bodies_keeps_results_and_reports_failures() -> None:
    """A failing body must not be silently dropped from an all-bodies search.

    The reported symptom: an unfiltered search returned IETF results with no
    sign that ETSI had failed, so the answer read as complete (#401).
    """
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"datatracker\.ietf\.org").mock(
            return_value=httpx.Response(200, json=SAMPLE_RFC9000_SEARCH)
        )
        mock.get(url__regex=r"api\.github\.com").mock(return_value=httpx.Response(503))
        mock.get(url__regex=r"csrc\.nist\.gov").mock(
            return_value=httpx.Response(200, content=_csrc_export_zip([]))
        )
        mock.get(url__regex=r"api\.w3\.org").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        mock.get(url__regex=r"www\.etsi\.org").mock(return_value=httpx.Response(403))
        http = httpx.AsyncClient()
        client = StandardsClient(http)
        records, failures = await client.search_with_failures("QUIC", limit=5)
        await http.aclose()
    # The working bodies still answer ...
    assert any(r.get("body") == "IETF" for r in records)
    # ... and the failing one is named rather than dropped.
    assert [f.body for f in failures] == ["ETSI"]


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_get_with_failures_reports_instead_of_reading_as_absent(
    respx_mock: respx.MockRouter,
) -> None:
    """A resolved body that failed yields no record *and* a failure."""
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    record, failures = await client.get_with_failures("ETSI EN 303 645")
    await http.aclose()
    assert record is None
    assert [f.body for f in failures] == ["ETSI"]


async def test_get_fallback_continues_past_a_failing_fetcher() -> None:
    """One failing fetcher must not end the fallback walk.

    ETSI sits fourth in fetcher order, so a raise there would leave the
    Relaton, CC and CEN fetchers never tried.
    """
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"datatracker\.ietf\.org").mock(
            return_value=httpx.Response(
                200, json={"objects": [], "meta": {"total_count": 0}}
            )
        )
        mock.get(url__regex=r"api\.github\.com").mock(return_value=httpx.Response(503))
        mock.get(url__regex=r"csrc\.nist\.gov").mock(
            return_value=httpx.Response(200, content=_csrc_export_zip([]))
        )
        mock.get(url__regex=r"api\.w3\.org").mock(return_value=httpx.Response(404))
        mock.get(url__regex=r"www\.etsi\.org").mock(return_value=httpx.Response(403))
        http = httpx.AsyncClient()
        client = StandardsClient(http)
        record, failures = await client.get_with_failures("some-unknown-standard-xyz")
        await http.aclose()
    assert record is None
    assert [f.body for f in failures] == ["ETSI"]


async def test_search_keeps_its_plain_signature() -> None:
    """search() still returns records only, so existing callers are unaffected."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"www\.etsi\.org").mock(return_value=httpx.Response(403))
        http = httpx.AsyncClient()
        client = StandardsClient(http)
        results = await client.search("QUIC", body="ETSI", limit=5)
        await http.aclose()
    assert results == []


async def test_get_with_failures_returns_a_record_found_after_a_failure() -> None:
    """A later fetcher's record survives an earlier fetcher's failure.

    The walk continuing is only half the contract: what it found afterwards
    has to come back, with the failure recorded beside it.
    """
    from unittest.mock import AsyncMock, patch

    failing = AsyncMock()
    failing.get = AsyncMock(
        side_effect=StandardsUpstreamError("ETSI", status=403, detail="refused")
    )
    working = AsyncMock()
    working.get = AsyncMock(return_value={"identifier": "X 1", "body": "CEN"})

    http = httpx.AsyncClient()
    client = StandardsClient(http)
    with patch.object(client, "_one_fetcher_per_type", return_value=[failing, working]):
        record, failures = await client.get_with_failures("some-unknown-standard-xyz")
    await http.aclose()
    assert record == {"identifier": "X 1", "body": "CEN"}
    assert [f.body for f in failures] == ["ETSI"]


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_resolve_returns_the_stub_when_the_source_failed(
    respx_mock: respx.MockRouter,
) -> None:
    """resolve() keeps its stub behaviour when a source never answered.

    A failure now reaches the same branch a ``None`` already did, so the
    caller still gets the canonical form rather than an exception. Reporting
    the failure properly is resolve()'s own change to make; #401 deliberately
    left that shape alone.
    """
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    records = await client.resolve("ETSI EN 303 645")
    await http.aclose()
    assert len(records) == 1
    assert records[0]["identifier"] == "ETSI EN 303 645"
    assert records[0]["title"] == ""


@pytest.mark.asyncio
async def test_standards_client_search_iso_delegates_to_relaton() -> None:
    """search(body='ISO') routes to RelatonLiveFetcher.search() with source='ISO'."""
    from unittest.mock import AsyncMock

    from scholar_mcp._record_types import StandardRecord
    from scholar_mcp._standards_client import StandardsClient

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
        client = StandardsClient(http, cache=mock_cache)
        results = await client.search("9001", body="ISO")

    mock_cache.search_synced_standards.assert_awaited_once_with(
        "9001", source="ISO", limit=10
    )
    assert len(results) == 1
    assert results[0]["identifier"] == "ISO 9001:2015"


@pytest.mark.asyncio
async def test_standards_client_search_iec_delegates_to_relaton() -> None:
    """search(body='IEC') routes to RelatonLiveFetcher.search() with source='IEC'."""
    from unittest.mock import AsyncMock

    from scholar_mcp._record_types import StandardRecord
    from scholar_mcp._standards_client import StandardsClient

    record: StandardRecord = {
        "identifier": "IEC 62443-3-3:2020",
        "title": "Industrial communication networks — IT security",
        "body": "IEC",
        "status": "published",
        "full_text_available": False,
    }
    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[record])

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http, cache=mock_cache)
        results = await client.search("62443", body="IEC")

    mock_cache.search_synced_standards.assert_awaited_once_with(
        "62443", source="IEC", limit=10
    )
    assert len(results) == 1
    assert results[0]["identifier"] == "IEC 62443-3-3:2020"


@pytest.mark.asyncio
async def test_standards_client_search_iso_iec_uses_no_source_filter() -> None:
    """search(body='ISO/IEC') routes to unfiltered RelatonLiveFetcher variant."""
    from unittest.mock import AsyncMock

    from scholar_mcp._standards_client import StandardsClient

    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[])

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http, cache=mock_cache)
        await client.search("27001", body="ISO/IEC")

    mock_cache.search_synced_standards.assert_awaited_once_with(
        "27001", source=None, limit=10
    )


@pytest.mark.asyncio
async def test_standards_client_search_no_body_hits_relaton_cache_once() -> None:
    """All-bodies search invokes the Relaton cache once, CC cache once, CEN cache once.

    Regression guard: the three RelatonLiveFetcher instances (ISO, IEC,
    ISO/IEC) should be deduped to the source=None variant in the no-body
    path so the cache isn't queried three times for overlapping results.
    The CC and CEN fetchers also query the cache separately.
    """
    from unittest.mock import AsyncMock

    import respx

    from scholar_mcp._standards_client import StandardsClient

    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[])

    with respx.mock(assert_all_called=False) as router:
        # Stub out the non-Relaton fetchers so the test doesn't hit the network.
        router.route(host__regex=r".*").mock(return_value=httpx.Response(200, json=[]))
        async with httpx.AsyncClient() as http:
            client = StandardsClient(http, cache=mock_cache)
            await client.search("test-query")

    assert mock_cache.search_synced_standards.await_count == 3
    calls = mock_cache.search_synced_standards.call_args_list
    # First call is ISO/IEC Relaton with source=None
    # Second call is CC with source="CC"
    # Third call is CEN with source="CEN"
    assert any(call[1].get("source") is None for call in calls), (
        "ISO/IEC Relaton fetch missing"
    )
    assert any(call[1].get("source") == "CC" for call in calls), "CC fetch missing"
    assert any(call[1].get("source") == "CEN" for call in calls), "CEN fetch missing"


@pytest.mark.asyncio
async def test_standards_client_fetchers_all_implement_protocol() -> None:
    """Every fetcher in _fetchers satisfies _StandardsFetcher at runtime."""
    from scholar_mcp._standards_client import StandardsClient, _StandardsFetcher

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http)
        for name, fetcher in client._fetchers.items():
            assert isinstance(fetcher, _StandardsFetcher), (
                f"Fetcher for '{name}' ({type(fetcher).__name__}) "
                f"does not implement _StandardsFetcher Protocol"
            )


# --- Resolver: CC (Common Criteria) ---


def test_resolve_cc_version_only() -> None:
    """`CC:2022` resolves to body 'CC'."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("CC:2022")
    assert result is not None
    identifier, body = result
    assert body == "CC"
    assert "2022" in identifier


def test_resolve_cc_part() -> None:
    """`CC:2022 Part 1` and `Common Criteria 2022 Part 1` resolve to CC."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("CC:2022 Part 1") == ("CC:2022 Part 1", "CC")
    result = resolve_identifier_local("Common Criteria 2022 Part 1")
    assert result is not None
    assert result[1] == "CC"
    assert "2022 Part 1" in result[0]


def test_resolve_cc_3_1_revision() -> None:
    """`CC 3.1 R5` resolves to CC:2017 Part 1 (default part for unqualified version)."""
    from scholar_mcp._standards_client import resolve_identifier_local

    for raw in ("CC 3.1 R5", "CC 3.1 Revision 5", "Common Criteria 3.1 R5"):
        result = resolve_identifier_local(raw)
        assert result is not None, raw
        assert result == ("CC:2017 Part 1", "CC"), f"{raw} → {result}"


def test_resolve_cem_form() -> None:
    """`CEM:2022` and `Common Evaluation Methodology 2022` resolve to CC."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("CEM:2022") == ("CEM:2022", "CC")
    result = resolve_identifier_local("Common Evaluation Methodology 2022")
    assert result is not None
    assert result[1] == "CC"


def test_resolve_cc_pp_bsi() -> None:
    """`BSI-CC-PP-0099-V2-2017` resolves to body 'CC'."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("BSI-CC-PP-0099-V2-2017") == (
        "BSI-CC-PP-0099-V2-2017",
        "CC",
    )


def test_resolve_cc_pp_kecs() -> None:
    """`KECS-PP-0822-2017` resolves to body 'CC'."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("KECS-PP-0822-2017") == (
        "KECS-PP-0822-2017",
        "CC",
    )


def test_resolve_cc_pp_niap_pp_form() -> None:
    """`PP_MD_v3.1` (NIAP alternate form) resolves to body 'CC'."""
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("PP_MD_v3.1") == ("PP_MD_v3.1", "CC")


def test_resolve_iso_15408_still_dispatches_to_iso_iec() -> None:
    """`ISO/IEC 15408-1:2022` keeps dispatching to ISO/IEC.

    The record itself is owned by CC sync but the dispatch body matches
    the _fetchers key — `_fetchers["ISO/IEC"]` is what reads the cache
    where CC wrote the dual record.
    """
    from scholar_mcp._standards_client import resolve_identifier_local

    assert resolve_identifier_local("ISO/IEC 15408-1:2022") == (
        "ISO/IEC 15408-1:2022",
        "ISO/IEC",
    )


@pytest.mark.asyncio
async def test_standards_client_fetchers_cc_instance_registered() -> None:
    """`_fetchers['CC']` is a `_CCFetcher`."""
    from scholar_mcp._standards_client import StandardsClient, _CCFetcher

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http)
        fetcher = client._fetchers["CC"]
    assert isinstance(fetcher, _CCFetcher)


@pytest.mark.asyncio
async def test_standards_client_search_cc_delegates_to_cache() -> None:
    """`search(query, body='CC')` forwards `source='CC'` to the cache."""
    from unittest.mock import AsyncMock

    from scholar_mcp._record_types import StandardRecord
    from scholar_mcp._standards_client import StandardsClient

    record: StandardRecord = {
        "identifier": "CC:2022 Part 1",
        "title": "CC Part 1",
        "body": "CC",
        "status": "published",
        "full_text_available": True,
    }
    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[record])
    mock_cache.get_standard = AsyncMock(return_value=None)

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http, cache=mock_cache)
        results = await client.search("Part 1", body="CC")

    mock_cache.search_synced_standards.assert_awaited_once_with(
        "Part 1", source="CC", limit=10
    )
    assert results == [record]


@pytest.mark.asyncio
async def test_cc_fetcher_cache_miss_logs_warning_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`_CCFetcher.get` on a cache miss logs WARNING and returns None."""
    import logging
    from unittest.mock import AsyncMock

    from scholar_mcp._standards_client import _CCFetcher

    mock_cache = AsyncMock()
    mock_cache.get_standard = AsyncMock(return_value=None)

    fetcher = _CCFetcher(cache=mock_cache)
    with caplog.at_level(logging.WARNING, logger="scholar_mcp._standards_client"):
        result = await fetcher.get("Some-Unknown-PP-0001-2024")

    assert result is None
    assert any(
        "cc_cache_miss" in rec.message and "sync-standards" in rec.message
        for rec in caplog.records
    )


def test_resolve_en_plain() -> None:
    """Plain EN identifier resolves to body 'CEN'."""
    assert resolve_identifier_local("EN 55032:2015") == ("EN 55032:2015", "CEN")


def test_resolve_en_iso() -> None:
    """EN ISO identifier resolves to body 'CEN'."""
    assert resolve_identifier_local("EN ISO 13849-1:2023") == (
        "EN ISO 13849-1:2023",
        "CEN",
    )


def test_resolve_en_iec() -> None:
    """EN IEC identifier resolves to body 'CEN'."""
    assert resolve_identifier_local("EN IEC 62443-3-3:2020") == (
        "EN IEC 62443-3-3:2020",
        "CEN",
    )


def test_resolve_en_iso_iec() -> None:
    """EN ISO/IEC identifier resolves to body 'CEN'."""
    assert resolve_identifier_local("EN ISO/IEC 27001:2022") == (
        "EN ISO/IEC 27001:2022",
        "CEN",
    )


def test_resolve_etsi_en_still_dispatches_to_etsi() -> None:
    """ETSI EN 303 645 must still dispatch to 'ETSI', not 'CEN'.

    Regression guard: the ETSI regex requires explicit 'ETSI' prefix,
    so it wins by position over the generic EN regex.
    """
    result = resolve_identifier_local("ETSI EN 303 645")
    assert result is not None
    assert result[1] == "ETSI"


@pytest.mark.asyncio
async def test_cen_fetcher_registered() -> None:
    """_fetchers['CEN'] is a _CENFetcher."""
    from scholar_mcp._standards_client import _CENFetcher

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http)
        fetcher = client._fetchers["CEN"]
    assert isinstance(fetcher, _CENFetcher)


@pytest.mark.asyncio
async def test_cen_fetcher_cache_miss_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_CENFetcher.get on cache miss logs WARNING with sync hint."""
    import logging
    from unittest.mock import AsyncMock

    from scholar_mcp._standards_client import _CENFetcher

    mock_cache = AsyncMock()
    mock_cache.get_standard = AsyncMock(return_value=None)

    fetcher = _CENFetcher(cache=mock_cache)
    with caplog.at_level(logging.WARNING, logger="scholar_mcp._standards_client"):
        result = await fetcher.get("EN 99999:2099")

    assert result is None
    assert any(
        "cen_cache_miss" in rec.message and "sync-standards" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_standards_client_search_cen_delegates_to_cache() -> None:
    """search(body='CEN') forwards source='CEN' to the cache."""
    from unittest.mock import AsyncMock

    from scholar_mcp._record_types import StandardRecord

    record: StandardRecord = {
        "identifier": "EN 55032:2015",
        "title": "EMC of multimedia equipment",
        "body": "CEN",
        "status": "harmonised",
        "full_text_available": False,
    }
    mock_cache = AsyncMock()
    mock_cache.search_synced_standards = AsyncMock(return_value=[record])
    mock_cache.get_standard = AsyncMock(return_value=None)

    async with httpx.AsyncClient() as http:
        client = StandardsClient(http, cache=mock_cache)
        results = await client.search("55032", body="CEN")

    mock_cache.search_synced_standards.assert_awaited_once_with(
        "55032", source="CEN", limit=10
    )
    assert results == [record]


def test_resolve_en_etsi_3part_number() -> None:
    """EN 300 328 V2.2.2:2019 resolves to CEN with normalised identifier."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("EN 300 328 V2.2.2:2019")
    assert result is not None
    identifier, body = result
    assert body == "CEN"
    assert identifier == "EN 300 328:2019"


def test_resolve_en_etsi_3part_without_version() -> None:
    """EN 301 489-1:2019 (no version suffix) also resolves."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("EN 301 489-1:2019")
    assert result is not None
    assert result[1] == "CEN"
    assert "301 489-1" in result[0]


def test_resolve_en_etsi_3part_with_subpart() -> None:
    """EN 3-part with subpart (EN 301 489-17 V3.2.4:2020) resolves to CEN."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("EN 301 489-17 V3.2.4:2020")
    assert result is not None
    assert result == ("EN 301 489-17:2020", "CEN")


def test_resolve_en_etsi_3part_large_version() -> None:
    """EN 3-part with large version number (V12.5.1) resolves to CEN."""
    from scholar_mcp._standards_client import resolve_identifier_local

    result = resolve_identifier_local("EN 301 511 V12.5.1:2017")
    assert result is not None
    assert result == ("EN 301 511:2017", "CEN")


# ---------------------------------------------------------------------------
# W3C replacements (#638)
# ---------------------------------------------------------------------------

_W3C_FIXTURES = (
    __import__("pathlib").Path(__file__).parent / "fixtures" / "standards" / "w3c"
)


def _w3c_fixture(name: str) -> dict:
    """A W3C API response, saved verbatim on 2026-11-15."""
    return json.loads((_W3C_FIXTURES / name).read_text())


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_replaced_spec_lists_its_replacement(
    respx_mock: respx.MockRouter,
) -> None:
    """Web Forms 2.0's last version is a Working Draft; HTML5 replaced it."""
    respx_mock.get("/specifications/web-forms-2").mock(
        return_value=httpx.Response(200, json=_w3c_fixture("web-forms-2.json"))
    )
    collection = respx_mock.get("/specifications/web-forms-2/superseded").mock(
        return_value=httpx.Response(
            200, json=_w3c_fixture("web-forms-2-superseded.json")
        )
    )
    fetcher = _W3CFetcher(httpx.AsyncClient(), RateLimiter(delay=0.0))

    record = await fetcher.get("web-forms-2")

    assert record is not None
    assert record["status"] == "superseded"
    assert record["superseded_by"] == ["HTML5"]
    assert collection.calls.last.request.url.params["items"] == "100"


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_without_replacement_link_makes_no_second_request(
    respx_mock: respx.MockRouter,
) -> None:
    """Retired HTML 4.01 names no replacement; only the spec itself is fetched."""
    respx_mock.get("/specifications/html401").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_RETIRED_SPEC)
    )
    fetcher = _W3CFetcher(httpx.AsyncClient(), RateLimiter(delay=0.0))

    record = await fetcher.get("html401")

    assert record is not None
    assert record["status"] == "superseded"
    assert record["superseded_by"] == []
    assert len(respx_mock.calls) == 1


@pytest.mark.parametrize("failure", ["status", "transport"])
@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_raises_when_replacement_lookup_fails(
    respx_mock: respx.MockRouter, failure: str
) -> None:
    """A lost answer would read as the stated Working Draft, so it raises."""
    respx_mock.get("/specifications/web-forms-2").mock(
        return_value=httpx.Response(200, json=_w3c_fixture("web-forms-2.json"))
    )
    route = respx_mock.get("/specifications/web-forms-2/superseded")
    if failure == "status":
        route.mock(return_value=httpx.Response(503))
    else:
        route.mock(side_effect=httpx.ConnectError("refused"))
    fetcher = _W3CFetcher(httpx.AsyncClient(), RateLimiter(delay=0.0))

    with pytest.raises(StandardsUpstreamError) as excinfo:
        await fetcher.get("web-forms-2")

    assert excinfo.value.body == "W3C"
    assert excinfo.value.status == (503 if failure == "status" else None)


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_lists_replacements_too(
    respx_mock: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    """search() reads the link like get(); a second page is logged, not read."""
    respx_mock.get("/specifications").mock(
        return_value=httpx.Response(
            200,
            json={
                "pages": 1,
                "_links": {
                    "specifications": [
                        {
                            "href": f"{W3C_API_BASE}/specifications/web-forms-2",
                            "title": "Web Forms 2.0",
                        }
                    ]
                },
            },
        )
    )
    respx_mock.get("/specifications/web-forms-2").mock(
        return_value=httpx.Response(200, json=_w3c_fixture("web-forms-2.json"))
    )
    respx_mock.get("/specifications/web-forms-2/superseded").mock(
        return_value=httpx.Response(
            200, json={**_w3c_fixture("web-forms-2-superseded.json"), "pages": 2}
        )
    )
    fetcher = _W3CFetcher(httpx.AsyncClient(), RateLimiter(delay=0.0))

    with caplog.at_level("WARNING"):
        results = await fetcher.search("web forms")

    assert [r["superseded_by"] for r in results] == [["HTML5"]]
    assert "w3c_superseded_by_truncated" in caplog.text


def test_w3c_identifiers_from_a_real_collection() -> None:
    """RDF/XML's 1999 syntax was replaced by six RDF 1.0 and 1.1 documents."""
    from scholar_mcp._standards_client import _w3c_identifiers

    links = _w3c_fixture("REC-rdf-syntax-superseded.json")["_links"]["superseded"]
    assert _w3c_identifiers(links) == [
        "rdf11-xml",
        "rdf10-primer",
        "rdf11-schema",
        "rdf10-semantics",
        "rdf-testcases",
        "rdf-concepts-10",
    ]


def test_w3c_identifiers_maps_names_and_skips_repeats_and_junk() -> None:
    from scholar_mcp._standards_client import _w3c_identifiers

    html5 = {"href": f"{W3C_API_BASE}/specifications/html5", "title": "HTML5"}
    assert _w3c_identifiers([html5, "junk", html5, {"href": ""}]) == ["HTML5"]


# ---------------------------------------------------------------------------
# ETSI withdrawn, historical and replaced deliverables (#640)
# ---------------------------------------------------------------------------

_ETSI_FIXTURES = _W3C_FIXTURES.parent / "etsi"
ETSI_SUPERSEDED_PATH = "/custom/standardssearch/superseded.php"


def _etsi_fixture(name: str) -> str:
    """A data.php or superseded.php response body, saved verbatim on 2026-11-15."""
    return (_ETSI_FIXTURES / name).read_text()


def _etsi_lookup(respx_mock: respx.MockRouter, fixture: str) -> respx.Route:
    return respx_mock.get(ETSI_DATA_PATH).mock(
        return_value=httpx.Response(200, text=_etsi_fixture(fixture))
    )


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_replaced_deliverable_names_its_replacement(
    respx_mock: respx.MockRouter,
) -> None:
    """EN 300 328-1's newest edition was replaced by EN 300 328 V1.4.1."""
    lookup = _etsi_lookup(respx_mock, "lookup-en-300-328-1.json")
    replaced = respx_mock.get(ETSI_SUPERSEDED_PATH).mock(
        return_value=httpx.Response(
            200, text=_etsi_fixture("superseded-en-300-328-1.json")
        )
    )
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    record = await fetcher.get("ETSI EN 300 328-1")

    assert record is not None
    assert (record["revision"], record["status"]) == ("1.3.1", "superseded")
    assert record["superseded_by"] == ["ETSI EN 300 328"]
    params = lookup.calls.last.request.url.params
    assert (params["withdrawn"], params["historical"], params["superseded"]) == (
        "1",
        "1",
        "1",
    )
    assert replaced.calls.last.request.url.params["wki_id"] == "9863"


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_historical_deliverable_is_withdrawn(
    respx_mock: respx.MockRouter,
) -> None:
    """EN 300 833 is historical (STATUS_CODE 13): found, withdrawn, no lookup."""
    _etsi_lookup(respx_mock, "lookup-en-300-833.json")
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    record = await fetcher.get("ETSI EN 300 833")

    assert record is not None
    assert record["status"] == "withdrawn"
    assert record["superseded_by"] == []
    # No superseded.php route: respx fails any request to it.


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_picks_the_newest_edition_over_a_replaced_one(
    respx_mock: respx.MockRouter,
) -> None:
    """EN 303 645's lookup also lists the replaced V2.1.1; V3.1.3 is current."""
    _etsi_lookup(respx_mock, "lookup-en-303-645.json")
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    record = await fetcher.get("ETSI EN 303 645")

    assert record is not None
    assert (record["revision"], record["status"]) == ("3.1.3", "published")
    # No superseded.php route: respx fails any request to it.


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_replaced_edition_with_no_named_replacement(
    respx_mock: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    """superseded.php's 200 error object: still superseded, on its own flag."""
    _etsi_lookup(respx_mock, "lookup-en-300-328-1.json")
    respx_mock.get(ETSI_SUPERSEDED_PATH).mock(
        return_value=httpx.Response(
            200, text=_etsi_fixture("superseded-none-named.json")
        )
    )
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    with caplog.at_level("INFO"):
        record = await fetcher.get("ETSI EN 300 328-1")

    assert record is not None
    assert (record["status"], record["superseded_by"]) == ("superseded", [])
    assert "etsi_superseded_none_named" in caplog.text


@pytest.mark.parametrize("failure", ["status", "transport", "html"])
@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_raises_when_replacement_lookup_fails(
    respx_mock: respx.MockRouter, failure: str
) -> None:
    _etsi_lookup(respx_mock, "lookup-en-300-328-1.json")
    route = respx_mock.get(ETSI_SUPERSEDED_PATH)
    if failure == "status":
        route.mock(return_value=httpx.Response(403))
    elif failure == "transport":
        route.mock(side_effect=httpx.ConnectError("refused"))
    else:
        route.mock(return_value=httpx.Response(200, text="<html></html>"))
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    with pytest.raises(StandardsUpstreamError) as excinfo:
        await fetcher.get("ETSI EN 300 328-1")

    assert excinfo.value.body == "ETSI"


def test_etsi_edition_order_by_date_then_version() -> None:
    """An unparsable edition sorts first."""
    from scholar_mcp._standards_client import _etsi_edition_order

    assert _etsi_edition_order({"ETSI_DELIVERABLE": "ETSI EN 1"}) == ("", ())
    assert _etsi_edition_order(
        {"ETSI_DELIVERABLE": "ETSI EN 303 645 V3.1.3 (2024-09)"}
    ) == ("2024-09", (3, 1, 3))


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_replacement_list_drops_junk_and_self(
    respx_mock: respx.MockRouter,
) -> None:
    _etsi_lookup(respx_mock, "lookup-en-300-328-1.json")
    other = {"ETSI_DELIVERABLE": "ETSI EN 300 328 V1.4.1 (2003-04)"}
    own = {"ETSI_DELIVERABLE": "ETSI EN 300 328-1 V1.4.1 (2003-04)"}
    respx_mock.get(ETSI_SUPERSEDED_PATH).mock(
        return_value=httpx.Response(200, json=["junk", other, own, other])
    )
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    record = await fetcher.get("ETSI EN 300 328-1")

    assert record is not None
    assert record["superseded_by"] == ["ETSI EN 300 328"]


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_logs_a_lookup_longer_than_one_page(
    respx_mock: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    rows = json.loads(_etsi_fixture("lookup-en-303-645.json"))
    rows = [{**r, "total_count": "120"} for r in rows]
    respx_mock.get(ETSI_DATA_PATH).mock(return_value=httpx.Response(200, json=rows))
    fetcher = _ETSIFetcher(httpx.AsyncClient(base_url=ETSI_BASE), RateLimiter(0.0))

    with caplog.at_level("WARNING"):
        record = await fetcher.get("ETSI EN 303 645")

    assert record is not None
    assert "etsi_lookup_truncated" in caplog.text

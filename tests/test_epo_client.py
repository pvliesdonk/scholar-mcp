"""Tests for EpoClient — async wrapper around python-epo-ops-client."""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from pypdf import PdfReader, PdfWriter
from requests.exceptions import HTTPError

from scholar_mcp._epo_client import (
    EpoClient,
    EpoRateLimitedError,
    _parse_pdf_instance,
    _parse_throttle_header,
)
from scholar_mcp._patent_numbers import DocdbNumber
from scholar_mcp._rate_limiter import RateLimitedError

# ---------------------------------------------------------------------------
# Inline XML fixtures
# ---------------------------------------------------------------------------

_BIBLIO_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1" family-id="54321">
      <bibliographic-data>
        <publication-reference>
          <document-id document-id-type="docdb">
            <country>EP</country><doc-number>1234567</doc-number><kind>A1</kind><date>20200115</date>
          </document-id>
        </publication-reference>
        <invention-title lang="en">Test Patent</invention-title>
        <abstract lang="en"><p>Test abstract.</p></abstract>
        <parties><applicants><applicant data-format="docdb" sequence="1"><applicant-name><name>TEST CORP</name></applicant-name></applicant></applicants><inventors/></parties>
        <patent-classifications/>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

_SEARCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="1">
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country><doc-number>1234567</doc-number><kind>A1</kind>
        </document-id>
      </ops:publication-reference>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>"""

_CLAIMS_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1">
      <claims lang="en">
        <claim><claim-text>1. A method for testing.</claim-text></claim>
      </claims>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

_DESCRIPTION_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1">
      <description lang="en">
        <p num="0001">Test description.</p>
      </description>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

_FAMILY_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:patent-family>
    <ops:family-member family-id="54321">
      <publication-reference xmlns="http://www.epo.org/exchange">
        <document-id document-id-type="docdb">
          <country>EP</country><doc-number>1234567</doc-number>
          <kind>A1</kind><date>20200115</date>
        </document-id>
      </publication-reference>
    </ops:family-member>
  </ops:patent-family>
</ops:world-patent-data>"""

_EPO_FIXTURES = Path(__file__).parent / "fixtures" / "epo"

# The invented fixture this replaced wrapped `ops:legal-event` elements in
# `ops:register-documents`; OPS sends neither, so the parser matched nothing
# and every legal lookup came back empty while the suite stayed green (#390).
_LEGAL_RESPONSE_XML = (_EPO_FIXTURES / "legal_ep1000000a1.xml").read_bytes()


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------


def _mock_response(
    content: bytes,
    status_code: int = 200,
    throttle: str = "green",
) -> MagicMock:
    """Create a fake requests.Response for use with mocked epo_ops methods.

    Args:
        content: Raw response body bytes.
        status_code: HTTP status code.
        throttle: EPO traffic light colour word for X-Throttling-Control header.

    Returns:
        MagicMock configured to behave like a requests.Response.
    """
    resp = MagicMock(spec=requests.Response)
    resp.content = content
    resp.status_code = status_code
    resp.headers = {"X-Throttling-Control": f"{throttle} (search={throttle}:30)"}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_throttle_response(
    color: str, *, service_colors: dict[str, str] | None = None
) -> MagicMock:
    """Create a fake response with a configurable X-Throttling-Control header.

    Args:
        color: The overall traffic-light colour (e.g. ``"green"``, ``"busy"``).
        service_colors: Optional mapping of service name to colour, used to
            build the per-service section of the header (e.g.
            ``{"search": "green", "retrieval": "green"}``).

    Returns:
        MagicMock with ``headers`` dict containing the constructed header.
    """
    response = MagicMock()
    if service_colors:
        parts = ", ".join(f"{svc}={c}:100" for svc, c in service_colors.items())
        header_value = f"{color} ({parts})"
    else:
        header_value = color
    response.headers = {"X-Throttling-Control": header_value}
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ops_client() -> MagicMock:
    """Return a MagicMock that stands in for epo_ops.Client."""
    return MagicMock()


@pytest.fixture
def epo_client(mock_ops_client: MagicMock) -> EpoClient:
    """Return an EpoClient wired with the mock_ops_client."""
    return EpoClient(
        consumer_key="key",
        consumer_secret="secret",
        _client=mock_ops_client,
    )


@pytest.fixture
def mock_epo_client() -> EpoClient:
    """EpoClient with a mocked underlying ops client."""
    epo = EpoClient(consumer_key="key", consumer_secret="secret", _client=MagicMock())
    return epo


# ---------------------------------------------------------------------------
# search() tests
# ---------------------------------------------------------------------------


async def test_search_returns_parsed_results(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """search() returns the dict produced by parse_search_xml."""
    mock_ops_client.published_data_search.return_value = _mock_response(_SEARCH_XML)

    result = await epo_client.search("ti=Test")

    assert result["total_count"] == 1
    assert result["references"][0]["country"] == "EP"
    assert result["references"][0]["number"] == "1234567"


async def test_search_passes_cql_and_range(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """search() forwards cql_query, range_begin, and range_end to the client."""
    mock_ops_client.published_data_search.return_value = _mock_response(_SEARCH_XML)

    await epo_client.search("ti=Example", range_begin=5, range_end=15)

    mock_ops_client.published_data_search.assert_called_once_with(
        "ti=Example", range_begin=5, range_end=15
    )


async def test_search_default_range(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """search() uses range_begin=1, range_end=25 by default."""
    mock_ops_client.published_data_search.return_value = _mock_response(_SEARCH_XML)

    await epo_client.search("ti=Test")

    mock_ops_client.published_data_search.assert_called_once_with(
        "ti=Test", range_begin=1, range_end=25
    )


async def test_search_returns_empty_on_404(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """search() returns empty results when EPO returns 404 (no results found)."""
    fake_response = MagicMock(spec=requests.Response)
    fake_response.status_code = 404
    mock_ops_client.published_data_search.side_effect = HTTPError(
        response=fake_response
    )

    result = await epo_client.search('ct="doi:nonexistent"')

    assert result == {"total_count": 0, "references": []}


async def test_search_re_raises_non_404_http_errors(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """search() re-raises HTTPError for non-404 status codes."""
    fake_response = MagicMock(spec=requests.Response)
    fake_response.status_code = 500
    mock_ops_client.published_data_search.side_effect = HTTPError(
        response=fake_response
    )

    with pytest.raises(HTTPError):
        await epo_client.search("ti=Test")


# ---------------------------------------------------------------------------
# get_biblio() tests
# ---------------------------------------------------------------------------


async def test_get_biblio_returns_parsed_dict(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_biblio() returns the dict produced by parse_biblio_xml."""
    mock_ops_client.published_data.return_value = _mock_response(_BIBLIO_XML)

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_biblio(doc)

    assert result["title"] == "Test Patent"
    assert result["applicants"] == ["TEST CORP"]
    assert result["publication_number"] == "EP.1234567.A1"


async def test_get_biblio_calls_published_data_with_correct_args(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_biblio() calls published_data with 'publication', Docdb input, endpoint='biblio'."""
    import epo_ops.models

    mock_ops_client.published_data.return_value = _mock_response(_BIBLIO_XML)

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    await epo_client.get_biblio(doc)

    call_args = mock_ops_client.published_data.call_args
    assert call_args.args[0] == "publication"
    inp = call_args.args[1]
    assert isinstance(inp, epo_ops.models.Docdb)
    assert inp.number == "1234567"
    assert inp.country_code == "EP"
    assert inp.kind_code == "A1"
    assert call_args.kwargs.get("endpoint") == "biblio"


async def test_get_biblio_defaults_kind_to_A_when_empty(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_biblio() uses kind_code='A' when DocdbNumber.kind is empty string."""
    import epo_ops.models

    mock_ops_client.published_data.return_value = _mock_response(_BIBLIO_XML)

    doc = DocdbNumber(country="EP", number="1234567", kind="")
    await epo_client.get_biblio(doc)

    call_args = mock_ops_client.published_data.call_args
    inp = call_args.args[1]
    assert isinstance(inp, epo_ops.models.Docdb)
    assert inp.kind_code == "A"


# ---------------------------------------------------------------------------
# Throttle / rate-limiting tests
# ---------------------------------------------------------------------------


async def test_green_throttle_does_not_raise(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Green traffic light does not raise any error."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="green"
    )
    # Should not raise
    await epo_client.search("ti=Test")


async def test_idle_throttle_does_not_raise(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Idle traffic light (API at rest) does not raise any error."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="idle"
    )
    # Should not raise
    await epo_client.search("ti=Test")


async def test_yellow_throttle_raises_epo_rate_limited_error(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Yellow traffic light raises EpoRateLimitedError."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="yellow"
    )
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await epo_client.search("ti=Test")
    assert exc_info.value.color == "yellow"


async def test_red_throttle_raises_epo_rate_limited_error(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Red traffic light raises EpoRateLimitedError."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="red"
    )
    with pytest.raises(EpoRateLimitedError):
        await epo_client.search("ti=Test")


async def test_black_throttle_raises_runtime_error(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Black traffic light raises RuntimeError (daily quota exhausted, not retryable)."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="black"
    )
    with pytest.raises(RuntimeError, match="daily quota exhausted"):
        await epo_client.search("ti=Test")


async def test_black_throttle_does_not_raise_epo_rate_limited_error(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Black traffic light must NOT raise EpoRateLimitedError (it is not retryable)."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="black"
    )
    with pytest.raises(RuntimeError):
        await epo_client.search("ti=Test")
    # If we reach here without EpoRateLimitedError, the test passes implicitly;
    # but also confirm it's not an EpoRateLimitedError subclass
    try:
        await epo_client.search("ti=Test")
    except RuntimeError:
        pass  # expected
    except EpoRateLimitedError:
        pytest.fail("Black throttle should raise RuntimeError, not EpoRateLimitedError")


async def test_throttle_on_get_biblio(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Yellow throttle on get_biblio also raises EpoRateLimitedError."""
    mock_ops_client.published_data.return_value = _mock_response(
        _BIBLIO_XML, throttle="yellow"
    )
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(EpoRateLimitedError):
        await epo_client.get_biblio(doc)


def test_check_throttle_overall_busy_search_green_does_not_raise() -> None:
    """overall=busy but search=green: search calls should NOT raise."""
    response = _mock_throttle_response(
        "busy", service_colors={"search": "green", "retrieval": "green"}
    )
    epo = EpoClient(consumer_key="key", consumer_secret="secret", _client=MagicMock())
    epo._check_throttle(response, service="search")  # must not raise


def test_check_throttle_overall_green_search_yellow_raises() -> None:
    """overall=green but search=yellow: search calls SHOULD raise."""
    response = _mock_throttle_response("green", service_colors={"search": "yellow"})
    epo = EpoClient(consumer_key="key", consumer_secret="secret", _client=MagicMock())
    with pytest.raises(EpoRateLimitedError):
        epo._check_throttle(response, service="search")


# ---------------------------------------------------------------------------
# Inheritance test
# ---------------------------------------------------------------------------


def test_epo_rate_limited_error_is_subclass_of_rate_limited_error() -> None:
    """EpoRateLimitedError must be a subclass of RateLimitedError."""
    assert issubclass(EpoRateLimitedError, RateLimitedError)


def test_epo_rate_limited_error_stores_color() -> None:
    """EpoRateLimitedError stores the colour and has a descriptive message."""
    err = EpoRateLimitedError("yellow")
    assert err.color == "yellow"
    assert "yellow" in str(err)


# ---------------------------------------------------------------------------
# get_claims() tests
# ---------------------------------------------------------------------------


async def test_get_claims_returns_text(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_claims() returns parsed claims text."""
    mock_ops_client.published_data.return_value = _mock_response(_CLAIMS_RESPONSE_XML)
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_claims(doc)
    assert "method for testing" in result


async def test_get_claims_calls_with_claims_endpoint(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_claims() passes endpoint='claims' to published_data."""
    mock_ops_client.published_data.return_value = _mock_response(_CLAIMS_RESPONSE_XML)
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    await epo_client.get_claims(doc)
    call_args = mock_ops_client.published_data.call_args
    assert call_args.kwargs.get("endpoint") == "claims"


# ---------------------------------------------------------------------------
# get_description() tests
# ---------------------------------------------------------------------------


async def test_get_description_returns_text(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_description() returns parsed description text."""
    mock_ops_client.published_data.return_value = _mock_response(
        _DESCRIPTION_RESPONSE_XML
    )
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_description(doc)
    assert "Test description" in result


async def test_get_description_calls_with_description_endpoint(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_description() passes endpoint='description' to published_data."""
    mock_ops_client.published_data.return_value = _mock_response(
        _DESCRIPTION_RESPONSE_XML
    )
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    await epo_client.get_description(doc)
    call_args = mock_ops_client.published_data.call_args
    assert call_args.kwargs.get("endpoint") == "description"


# ---------------------------------------------------------------------------
# get_family() tests
# ---------------------------------------------------------------------------


async def test_get_family_returns_members(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_family() returns parsed family member list."""
    mock_ops_client.family.return_value = _mock_response(_FAMILY_RESPONSE_XML)
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_family(doc)
    assert len(result) == 1
    assert result[0]["country"] == "EP"


async def test_get_family_calls_family_method(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_family() calls client.family with 'publication' and Docdb input."""
    mock_ops_client.family.return_value = _mock_response(_FAMILY_RESPONSE_XML)
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    await epo_client.get_family(doc)
    mock_ops_client.family.assert_called_once()
    call_args = mock_ops_client.family.call_args
    assert call_args.args[0] == "publication"


# ---------------------------------------------------------------------------
# get_legal() tests
# ---------------------------------------------------------------------------


async def test_get_legal_returns_events(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_legal() returns parsed legal event list."""
    mock_ops_client.legal.return_value = _mock_response(_LEGAL_RESPONSE_XML)
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_legal(doc)
    assert len(result) == 50
    assert result[0]["code"] == "17Q"
    assert result[0]["description"] == "FIRST EXAMINATION REPORT DESPATCHED"


async def test_get_legal_calls_legal_method(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_legal() calls client.legal with 'publication' and Docdb input."""
    mock_ops_client.legal.return_value = _mock_response(_LEGAL_RESPONSE_XML)
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    await epo_client.get_legal(doc)
    mock_ops_client.legal.assert_called_once()
    call_args = mock_ops_client.legal.call_args
    assert call_args.args[0] == "publication"


# ---------------------------------------------------------------------------
# aclose() test
# ---------------------------------------------------------------------------


async def test_aclose_is_noop(epo_client: EpoClient) -> None:
    """aclose() completes without error (no-op cleanup)."""
    await epo_client.aclose()  # Must not raise


# ---------------------------------------------------------------------------
# _parse_throttle_header tests
# ---------------------------------------------------------------------------


def test_parse_throttle_header_full() -> None:
    """Full header with overall and per-service breakdown is parsed correctly."""
    header = "busy (images=green:100, search=yellow:2, retrieval=green:50)"
    result = _parse_throttle_header(header)
    assert result["_overall"] == "busy"
    assert result["search"] == "yellow"
    assert result["retrieval"] == "green"
    assert result["images"] == "green"


def test_parse_throttle_header_no_subservices() -> None:
    """Header with only an overall color (no parenthesised section) is handled."""
    result = _parse_throttle_header("green")
    assert result == {"_overall": "green"}


def test_parse_throttle_header_missing_header() -> None:
    """Empty string defaults to _overall=green."""
    result = _parse_throttle_header("")
    assert result == {"_overall": "green"}


def test_parse_throttle_header_all_colors() -> None:
    """All known EPO throttle colors are preserved verbatim."""
    for color in ("green", "yellow", "red", "black", "idle"):
        result = _parse_throttle_header(color)
        assert result["_overall"] == color


# ---------------------------------------------------------------------------
# EpoRateLimitedError.service tests
# ---------------------------------------------------------------------------


def test_rate_limited_error_has_service_attribute() -> None:
    """EpoRateLimitedError stores service as a keyword-only attribute."""
    err = EpoRateLimitedError("yellow", service="search")
    assert err.service == "search"
    assert err.color == "yellow"
    assert "search=yellow" in str(err)


def test_rate_limited_error_default_service() -> None:
    """EpoRateLimitedError defaults to _overall when service not specified."""
    err = EpoRateLimitedError("red")
    assert err.service == "_overall"


# ---------------------------------------------------------------------------
# Pre-flight throttle cache tests
# ---------------------------------------------------------------------------


async def test_preflight_cache_prevents_second_search_call(
    mock_epo_client: EpoClient,
) -> None:
    """After a throttled search response, the next call raises from cache without network."""
    # Simulate a throttled search response being returned by the EPO search endpoint
    throttled_response = _mock_throttle_response(
        "green", service_colors={"search": "yellow"}
    )
    mock_epo_client._client.published_data_search.return_value = throttled_response

    with pytest.raises(EpoRateLimitedError):
        await mock_epo_client.search("ti=test")

    # Second call should raise from cache, not touch the network again
    mock_epo_client._client.published_data_search.reset_mock()
    with pytest.raises(EpoRateLimitedError):
        await mock_epo_client.search("ti=test")

    mock_epo_client._client.published_data_search.assert_not_called()


async def test_preflight_retrieval_blocks_get_biblio(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight blocks get_biblio when retrieval service is throttled."""
    # Seed the cache with a throttled retrieval color
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "yellow"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await mock_epo_client.get_biblio(doc)
    assert exc_info.value.service == "retrieval"
    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_retrieval_blocks_get_claims(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight blocks get_claims when retrieval service is throttled."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "yellow"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await mock_epo_client.get_claims(doc)
    assert exc_info.value.service == "retrieval"
    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_retrieval_blocks_get_description(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight blocks get_description when retrieval service is throttled."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "yellow"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await mock_epo_client.get_description(doc)
    assert exc_info.value.service == "retrieval"
    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_retrieval_blocks_get_citations(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight blocks get_citations when retrieval service is throttled."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "yellow"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await mock_epo_client.get_citations(doc)
    assert exc_info.value.service == "retrieval"
    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_inpadoc_blocks_get_legal(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight blocks get_legal when inpadoc service is throttled."""
    mock_epo_client._throttle_cache = {"_overall": "green", "inpadoc": "yellow"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await mock_epo_client.get_legal(doc)
    assert exc_info.value.service == "inpadoc"
    mock_epo_client._client.legal.assert_not_called()


async def test_preflight_inpadoc_blocks_get_family(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight blocks get_family when inpadoc service is throttled."""
    mock_epo_client._throttle_cache = {"_overall": "green", "inpadoc": "yellow"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await mock_epo_client.get_family(doc)
    assert exc_info.value.service == "inpadoc"
    mock_epo_client._client.family.assert_not_called()


async def test_preflight_retrieval_black_raises_runtime_error(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight raises RuntimeError (not EpoRateLimitedError) for retrieval=black."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "black"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_biblio(doc)

    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_retrieval_black_raises_runtime_error_claims(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight raises RuntimeError for retrieval=black on get_claims."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "black"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_claims(doc)

    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_retrieval_black_raises_runtime_error_description(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight raises RuntimeError for retrieval=black on get_description."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "black"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_description(doc)

    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_retrieval_black_raises_runtime_error_citations(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight raises RuntimeError for retrieval=black on get_citations."""
    mock_epo_client._throttle_cache = {"_overall": "green", "retrieval": "black"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_citations(doc)

    mock_epo_client._client.published_data.assert_not_called()


async def test_preflight_inpadoc_black_raises_runtime_error(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight raises RuntimeError (not EpoRateLimitedError) for inpadoc=black."""
    mock_epo_client._throttle_cache = {"_overall": "green", "inpadoc": "black"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_family(doc)

    mock_epo_client._client.family.assert_not_called()


async def test_preflight_inpadoc_black_raises_runtime_error_legal(
    mock_epo_client: EpoClient,
) -> None:
    """Pre-flight raises RuntimeError for inpadoc=black on get_legal."""
    mock_epo_client._throttle_cache = {"_overall": "green", "inpadoc": "black"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1000000", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_legal(doc)

    mock_epo_client._client.legal.assert_not_called()


def test_is_service_throttled_falls_back_to_overall(
    mock_epo_client: EpoClient,
) -> None:
    """_is_service_throttled returns True when service absent but _overall is throttled."""
    # Cache has only _overall=red, no service-specific key
    mock_epo_client._throttle_cache = {"_overall": "red"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    assert mock_epo_client._is_service_throttled("search") is True


def test_is_service_throttled_overall_green_no_service_key(
    mock_epo_client: EpoClient,
) -> None:
    """_is_service_throttled returns False when _overall=green and service key absent."""
    mock_epo_client._throttle_cache = {"_overall": "green"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    assert mock_epo_client._is_service_throttled("search") is False


async def test_preflight_cache_expires_after_60s(
    mock_epo_client: EpoClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-flight cache expires after 60 seconds and lets the next call through."""
    throttled_response = _mock_throttle_response(
        "green", service_colors={"search": "yellow"}
    )
    mock_epo_client._client.published_data_search.return_value = throttled_response

    with pytest.raises(EpoRateLimitedError):
        await mock_epo_client.search("ti=test")

    # Advance monotonic time by 61 seconds
    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 61)

    # The cache is now stale — call goes through (hits network again)
    mock_epo_client._client.published_data_search.reset_mock()
    with pytest.raises(EpoRateLimitedError):  # still fails but from network, not cache
        await mock_epo_client.search("ti=test")

    mock_epo_client._client.published_data_search.assert_called_once()


# ---------------------------------------------------------------------------
# _parse_pdf_link tests
# ---------------------------------------------------------------------------


def _real_inquiry(name: str) -> bytes:
    """Read a verbatim captured EPO image-inquiry response.

    Args:
        name: File name under ``tests/fixtures/epo``.

    Returns:
        The raw response bytes exactly as EPO sent them.
    """
    return (_EPO_FIXTURES / name).read_bytes()


@pytest.mark.parametrize(
    "fixture_name,expected_link,expected_pages",
    [
        (
            "images_inquiry_ep3491801b1.xml",
            "published-data/images/EP/3491801/B1/fullimage",
            21,
        ),
        (
            "images_inquiry_wo2019016210a1.xml",
            "published-data/images/WO/2019016210/A1/fullimage",
            29,
        ),
    ],
    ids=["ep-b1", "wo-a1"],
)
def test_parse_pdf_link_reads_the_shape_epo_actually_sends(
    fixture_name: str, expected_link: str, expected_pages: int
) -> None:
    """The parser works against verbatim EPO responses, not hand-written ones.

    EPO nests the MIME type as element text inside
    ``ops:document-format-options``. The fixtures this replaced put it in a
    ``desc`` attribute on a direct child, which EPO never sends -- so the
    parser passed its tests while returning None for every real patent (#371).
    """
    instance = _parse_pdf_instance(_real_inquiry(fixture_name))
    assert instance is not None
    assert instance.link == expected_link
    # The page count drives how many OPS calls the download makes (#379).
    assert instance.pages == expected_pages


def test_parse_pdf_link_ignores_non_fulldocument_instances() -> None:
    """A real response also carries Drawing and FirstPageClipping instances.

    Those offer application/pdf too, so matching on the format alone would
    return a thumbnail link. Only the FullDocument instance is the document.
    """
    instance = _parse_pdf_instance(_real_inquiry("images_inquiry_wo2019016210a1.xml"))
    assert instance is not None
    link = instance.link
    assert "thumbnail" not in link
    assert "firstpage" not in link


def _make_inquiry_xml(pages: int | None) -> bytes:
    """Build an image-inquiry response with a chosen page count.

    Args:
        pages: Value for ``number-of-pages``; ``None`` omits the attribute.

    Returns:
        XML bytes in the shape EPO sends (see tests/fixtures/epo).
    """
    attr = "" if pages is None else f' number-of-pages="{pages}"'
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance desc="FullDocument" link="published-data/images/EP/1234567/A1/fullimage"{attr}>
        <ops:document-format-options>
          <ops:document-format>application/pdf</ops:document-format>
        </ops:document-format-options>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>""".encode()


# These two are trimmed to the shape EPO actually sends, cross-checked against
# the verbatim captures in tests/fixtures/epo. They previously carried
# `<ops:document-format desc="application/pdf"/>` as a direct child, an
# attribute shape that appears in no real response (#371).
_IMAGE_INQUIRY_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance desc="FullDocument" link="published-data/images/EP/1234567/A1/fullimage" number-of-pages="5">
        <ops:document-format-options>
          <ops:document-format>application/pdf</ops:document-format>
          <ops:document-format>application/tiff</ops:document-format>
        </ops:document-format-options>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>"""

# Derived, not captured: every patent probed while fixing #371 offered a PDF,
# so no real no-PDF response was available. The element shape is real; only
# the absence of application/pdf is constructed.
_IMAGE_INQUIRY_NO_PDF_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance desc="FullDocument" link="published-data/images/EP/1234567/A1/fullimage" number-of-pages="5">
        <ops:document-format-options>
          <ops:document-format>application/tiff</ops:document-format>
        </ops:document-format-options>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>"""

_IMAGE_INQUIRY_NO_FULL_DOC_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance desc="Thumbnail" link="some/path" number-of-pages="1">
        <ops:document-format desc="image/png"/>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>"""


def test_parse_pdf_link_returns_link_from_valid_xml() -> None:
    """_parse_pdf_link extracts the link attribute from a FullDocument PDF instance."""
    instance = _parse_pdf_instance(_IMAGE_INQUIRY_XML)
    assert instance is not None
    assert instance.link == "published-data/images/EP/1234567/A1/fullimage"
    assert instance.pages == 5


def test_parse_pdf_link_returns_none_when_no_pdf_format() -> None:
    """_parse_pdf_link returns None when FullDocument has no PDF format child."""
    link = _parse_pdf_instance(_IMAGE_INQUIRY_NO_PDF_XML)
    assert link is None


def test_parse_pdf_link_returns_none_when_no_full_document() -> None:
    """_parse_pdf_link returns None when there is no FullDocument instance."""
    link = _parse_pdf_instance(_IMAGE_INQUIRY_NO_FULL_DOC_XML)
    assert link is None


def test_parse_pdf_link_returns_none_on_parse_error() -> None:
    """_parse_pdf_link returns None (and logs) on malformed XML."""
    link = _parse_pdf_instance(b"not xml at all <<<!>>")
    assert link is None


def test_parse_pdf_link_reraises_rate_limit_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_parse_pdf_link re-raises RateLimitedError / EpoRateLimitedError without swallowing."""
    import scholar_mcp._epo_client as _mod

    monkeypatch.setattr(
        _mod._lxml_etree,
        "fromstring",
        lambda _data: (_ for _ in ()).throw(EpoRateLimitedError("yellow")),
    )
    with pytest.raises(EpoRateLimitedError):
        _parse_pdf_instance(b"<xml/>")


# ---------------------------------------------------------------------------
# get_pdf() tests
# ---------------------------------------------------------------------------


async def test_get_pdf_returns_pdf_bytes(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_pdf() returns a merged PDF covering every advertised page.

    The fixture advertises five pages, and OPS serves one per call, so five
    calls merge into a five-page document.
    """
    mock_ops_client.published_data.return_value = _mock_response(_IMAGE_INQUIRY_XML)
    mock_ops_client.image.side_effect = [
        _mock_response(_one_page_pdf(f"page-{n}")) for n in range(1, 6)
    ]

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_pdf(doc)

    assert result[:5] == b"%PDF-"
    assert _page_count(result) == 5
    mock_ops_client.published_data.assert_called_once()
    assert mock_ops_client.image.call_count == 5


def _one_page_pdf(marker: str) -> bytes:
    """Build a valid single-page PDF, the way OPS returns one page per call.

    Args:
        marker: Text drawn on the page, so merged output can be traced back
            to the page it came from.

    Returns:
        PDF bytes with exactly one page.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page.merge_page(page)  # no-op; keeps the page object realised
    writer.add_metadata({"/Title": marker})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _page_count(pdf: bytes) -> int:
    """Count pages in a PDF the authoritative way.

    Args:
        pdf: PDF bytes.

    Returns:
        The number of pages.
    """
    return len(PdfReader(io.BytesIO(pdf)).pages)


async def test_get_pdf_fetches_every_page_and_merges(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """A 3-page document is 3 OPS calls merged into one 3-page PDF.

    OPS serves one page per image call, so anything less than every page
    silently drops the claims and description (#379).
    """
    mock_ops_client.published_data.return_value = _mock_response(
        _make_inquiry_xml(pages=3)
    )
    mock_ops_client.image.side_effect = [
        _mock_response(_one_page_pdf(f"page-{n}")) for n in (1, 2, 3)
    ]

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_pdf(doc)

    assert _page_count(result) == 3
    assert mock_ops_client.image.call_count == 3
    assert [c.kwargs["range"] for c in mock_ops_client.image.call_args_list] == [
        1,
        2,
        3,
    ]


async def test_get_pdf_single_page_document_makes_one_call(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """A 1-page document costs exactly one call; no needless paging."""
    mock_ops_client.published_data.return_value = _mock_response(
        _make_inquiry_xml(pages=1)
    )
    mock_ops_client.image.return_value = _mock_response(_one_page_pdf("only"))

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    result = await epo_client.get_pdf(doc)

    assert _page_count(result) == 1
    assert mock_ops_client.image.call_count == 1


async def test_get_pdf_without_a_page_count_fetches_the_first_page(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A missing number-of-pages degrades to page one, and says so.

    Guessing a page count would either truncate silently or hammer OPS; one
    page plus a warning is the honest floor.
    """
    mock_ops_client.published_data.return_value = _mock_response(
        _make_inquiry_xml(pages=None)
    )
    mock_ops_client.image.return_value = _mock_response(_one_page_pdf("only"))

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with caplog.at_level(logging.WARNING, logger="scholar_mcp._epo_client"):
        result = await epo_client.get_pdf(doc)

    assert _page_count(result) == 1
    assert mock_ops_client.image.call_count == 1
    assert "epo_pdf_page_count_missing" in caplog.text


@pytest.mark.parametrize(
    "raw,reason",
    [("not-a-number", "unparsable"), ("0", "not positive"), ("-3", "negative")],
    ids=["unparsable", "zero", "negative"],
)
def test_parse_pdf_instance_rejects_a_nonsense_page_count(
    raw: str, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A page count that cannot be trusted becomes None, not a bad loop bound.

    Feeding a zero or negative count into the download loop would fetch
    nothing and merge an empty document; a string would raise mid-download.
    """
    xml = _make_inquiry_xml(pages=1).replace(
        b'number-of-pages="1"', f'number-of-pages="{raw}"'.encode()
    )
    with caplog.at_level(logging.WARNING, logger="scholar_mcp._epo_client"):
        instance = _parse_pdf_instance(xml)

    assert instance is not None, reason
    assert instance.pages is None


async def test_get_pdf_raises_value_error_when_no_pdf_available(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """get_pdf() raises ValueError when the inquiry returns no PDF link."""
    mock_ops_client.published_data.return_value = _mock_response(
        _IMAGE_INQUIRY_NO_PDF_XML
    )

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(ValueError, match="No PDF available"):
        await epo_client.get_pdf(doc)


async def test_get_pdf_preflight_blocks_when_throttled(
    mock_epo_client: EpoClient,
) -> None:
    """get_pdf() pre-flight raises EpoRateLimitedError when retrieval is throttled."""
    mock_epo_client._throttle_cache = {"retrieval": "yellow", "_overall": "green"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(EpoRateLimitedError, match="retrieval"):
        await mock_epo_client.get_pdf(doc)

    mock_epo_client._client.published_data.assert_not_called()


async def test_get_pdf_preflight_black_raises_runtime_error(
    mock_epo_client: EpoClient,
) -> None:
    """get_pdf() pre-flight raises RuntimeError when quota is exhausted (black)."""
    mock_epo_client._throttle_cache = {"retrieval": "black", "_overall": "green"}
    mock_epo_client._throttle_cache_ts = time.monotonic()

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await mock_epo_client.get_pdf(doc)


async def test_get_pdf_second_throttle_check_raises(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_pdf() raises when the images light turns amber before the download.

    The inquiry bills ``retrieval`` and the page download bills ``images``
    (they are different OPS operations), so this pre-flight is about the
    images light specifically.
    """
    # Step 1 returns green so _check_throttle passes; step-2 pre-flight returns True.
    mock_ops_client.published_data.return_value = _mock_response(_IMAGE_INQUIRY_XML)

    call_count = 0

    def throttled_on_second_call(service: str) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            epo_client._throttle_cache = {"images": "yellow", "_overall": "green"}
            epo_client._throttle_cache_ts = time.monotonic()
            return True
        return False

    monkeypatch.setattr(epo_client, "_is_service_throttled", throttled_on_second_call)

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(EpoRateLimitedError, match="images"):
        await epo_client.get_pdf(doc)

    mock_ops_client.image.assert_not_called()


async def test_get_pdf_second_throttle_check_black_raises_runtime_error(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_pdf() raises RuntimeError if images goes black between step-1 and step-2."""
    mock_ops_client.published_data.return_value = _mock_response(_IMAGE_INQUIRY_XML)

    call_count = 0

    def black_on_second_call(service: str) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            epo_client._throttle_cache = {"images": "black", "_overall": "green"}
            epo_client._throttle_cache_ts = time.monotonic()
            return True
        return False

    monkeypatch.setattr(epo_client, "_is_service_throttled", black_on_second_call)

    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(RuntimeError, match="daily quota"):
        await epo_client.get_pdf(doc)

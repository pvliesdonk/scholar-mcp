"""Tests for EpoClient — async wrapper around python-epo-ops-client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
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


async def test_black_throttle_raises_epo_rate_limited_error(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """Black traffic light raises EpoRateLimitedError."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="black"
    )
    with pytest.raises(EpoRateLimitedError) as exc_info:
        await epo_client.search("ti=Test")
    assert exc_info.value.color == "black"


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
# aclose() test
# ---------------------------------------------------------------------------


async def test_aclose_is_noop(epo_client: EpoClient) -> None:
    """aclose() completes without error (no-op cleanup)."""
    await epo_client.aclose()  # Must not raise

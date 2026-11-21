"""Identifying the paper a patent's NPL names without a DOI (#59).

The citation strings are the ones EPO returned for DE102025108780A1 and
DE102025118534A1 on 2026-11-21; the title-match responses follow the shapes
recorded in docs/design/reference/semantic-scholar-api.md.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from scholar_mcp._npl_titles import (
    MAX_TITLE_MATCHES,
    attach_title_candidates,
    extract_arxiv_id,
    guess_title,
)
from scholar_mcp._rate_limiter import RateLimitedError
from scholar_mcp._s2_client import S2Client
from scholar_mcp._tools_patent import _npl_s2_id

S2_BASE = "https://api.semanticscholar.org/graph/v1"

_GERMAN = (
    "- CHOLLET, François: Xception: Deep learning with depthwise separable "
    "convolutions. Preprint. [v2] Tue, 11 Oct 2016. S. 1-14."
)
_SHORT = (
    "- Lee KB, Cheon S, Kim CO (2017) A Convolutional Neural Network for Fault "
    "Classification and Diagnosis in Semiconductor Manufacturing Processes; IEEE "
    "T Semiconduct M 30: 135{142 * citation found in description,inline NPL citation *"
)
_QUOTED = (
    '- DIETRICH HARTMANN, KARLHEINZ LEHNER: "Technische Expertensysteme '
    'und ihre Anwendung", 1 January 1990, SPRINGER'
)
_WIKI = "- Outline of object recognition. In: Wikipedia, The Free Encyclopedia."
_SHORT_TITLE = "- LECUN, Yann ; BENGIO, Yoshua: Deep learning. In: Nature, 2015"


@pytest.mark.parametrize(
    ("raw", "doi", "expected"),
    [
        ("HOWARD, A.: MobileNets. CoRR, abs/1704.04861, (2017)", None, "1704.04861"),
        ("Some paper, arXiv:1610.02357v2 [cs.CV]", None, "1610.02357"),
        ("x", "10.48550/arXiv.1610.02357", "1610.02357"),
        ("A paper. DOI 10.1109/TSM.2017.2676245", "10.1109/TSM.2017.2676245", None),
        ("Report 1234.5678 of the committee", None, None),
    ],
)
def test_extract_arxiv_id(raw: str, doi: str | None, expected: str | None) -> None:
    assert extract_arxiv_id(raw, doi) == expected


@pytest.mark.parametrize(
    ("raw", "doi", "expected"),
    [
        (
            "A paper. DOI 10.1109/TSM.2017.2676245",
            "10.1109/TSM.2017.2676245",
            "DOI:10.1109/TSM.2017.2676245",
        ),
        (
            "CHOLLET: Xception. https://doi.org/10.48550/arXiv.1610.02357",
            "10.48550/arXiv.1610.02357",
            "ARXIV:1610.02357",
        ),
        ("HOWARD: MobileNets. CoRR, abs/1704.04861", None, "ARXIV:1704.04861"),
        ("A book, 1990", None, None),
    ],
)
def test_npl_s2_id(raw: str, doi: str | None, expected: str | None) -> None:
    assert _npl_s2_id(raw, doi) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_GERMAN, "Xception: Deep learning with depthwise separable convolutions"),
        (
            _SHORT,
            "A Convolutional Neural Network for Fault Classification and "
            "Diagnosis in Semiconductor Manufacturing Processes",
        ),
        (_QUOTED, "Technische Expertensysteme und ihre Anwendung"),
        ('- HARTMANN: "Expertensysteme", 1990, SPRINGER', None),  # quoted, too short
        ("Smith et al., Ch. 5, pp. 100-150, In: Advanced Methods, 2020", None),
        (_SHORT_TITLE, None),  # two significant words
        ("No structure at all here", None),
    ],
)
def test_guess_title(raw: str, expected: str | None) -> None:
    assert guess_title(raw) == expected


def _s2(**match: Any) -> AsyncMock:
    s2 = AsyncMock()
    s2.match_title = AsyncMock(**match)
    return s2


_XCEPTION = {
    "paperId": "5b6e",
    "title": "Xception: Deep Learning with Depthwise Separable Convolutions",
    "year": 2016,
}


async def test_plausible_match_becomes_an_unconfirmed_candidate() -> None:
    entries: list[dict[str, Any]] = [{"raw": _GERMAN, "confidence": None}]
    await attach_title_candidates(entries, _s2(return_value=_XCEPTION), "EP.1.A1")
    assert entries[0]["candidate"] == _XCEPTION
    assert entries[0]["confidence"] == "unconfirmed"
    assert entries[0]["match"] == "title"
    assert "paper" not in entries[0]


@pytest.mark.parametrize(
    "candidate",
    [
        {**_XCEPTION, "year": 2024},  # same title, wrong year
        {**_XCEPTION, "title": "Xception networks for depth estimation"},
        {"paperId": "x", "title": ""},
    ],
    ids=["wrong-year", "different-title", "no-title"],
)
async def test_implausible_match_is_dropped(candidate: dict[str, Any]) -> None:
    entries: list[dict[str, Any]] = [{"raw": _GERMAN, "confidence": None}]
    await attach_title_candidates(entries, _s2(return_value=candidate), "EP.1.A1")
    assert "candidate" not in entries[0]
    assert entries[0]["confidence"] is None


async def test_identified_and_web_references_are_not_looked_up() -> None:
    entries: list[dict[str, Any]] = [
        {"raw": _GERMAN, "paper": {"paperId": "p"}},
        {"raw": _GERMAN, "book": {"title": "b"}},
        {"raw": _GERMAN, "isbn": "9783540521556"},
        {"raw": _GERMAN, "doi": "10.1/x"},
        {"raw": _WIKI},
        {"raw": _GERMAN + " https://example.org/paper"},
    ]
    s2 = _s2(return_value=_XCEPTION)
    await attach_title_candidates(entries, s2, "EP.1.A1")
    s2.match_title.assert_not_called()


async def test_lookups_are_capped(caplog: pytest.LogCaptureFixture) -> None:
    entries: list[dict[str, Any]] = [
        {"raw": _GERMAN} for _ in range(MAX_TITLE_MATCHES + 3)
    ]
    s2 = _s2(return_value=None)
    with caplog.at_level(logging.INFO):
        await attach_title_candidates(entries, s2, "EP.1.A1")
    assert s2.match_title.await_count == MAX_TITLE_MATCHES
    assert "npl_title_match_capped patent=EP.1.A1" in caplog.messages


@pytest.mark.parametrize(
    ("error", "event"),
    [
        (RateLimitedError(), "npl_title_match_rate_limited"),
        (httpx.ConnectError("down"), "npl_title_match_failed"),
    ],
    ids=["rate-limited", "failed"],
)
async def test_lookups_stop_at_the_first_failure(
    error: Exception, event: str, caplog: pytest.LogCaptureFixture
) -> None:
    entries: list[dict[str, Any]] = [{"raw": _GERMAN}, {"raw": _SHORT}]
    s2 = _s2(side_effect=error)
    with caplog.at_level(logging.INFO):
        await attach_title_candidates(entries, s2, "EP.1.A1")
    assert s2.match_title.await_count == 1
    assert all("candidate" not in e for e in entries)
    assert any(m.startswith(event) for m in caplog.messages)


@pytest.fixture
async def s2_client() -> Any:
    client = S2Client(api_key=None, delay=0.0)
    yield client
    await client.aclose()


@respx.mock
async def test_match_title_returns_the_best_match(s2_client: S2Client) -> None:
    route = respx.get(f"{S2_BASE}/paper/search/match").mock(
        return_value=httpx.Response(
            200, json={"data": [{**_XCEPTION, "matchScore": 209.97}]}
        )
    )
    paper = await s2_client.match_title("Xception", fields="title,year")
    assert paper is not None
    assert paper["paperId"] == "5b6e"
    assert route.calls[0].request.url.params["query"] == "Xception"


@respx.mock
async def test_match_title_not_found_is_none(s2_client: S2Client) -> None:
    respx.get(f"{S2_BASE}/paper/search/match").mock(
        return_value=httpx.Response(404, json={"error": "Title match not found"})
    )
    assert await s2_client.match_title("totalGarbageNonsense", fields="title") is None


@respx.mock
async def test_match_title_other_errors_raise(s2_client: S2Client) -> None:
    respx.get(f"{S2_BASE}/paper/search/match").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await s2_client.match_title("Xception", fields="title")


async def test_citations_resolve_arxiv_ids_and_attach_candidates(service: Any) -> None:
    """Through get_patent's citations section: arXiv exact, title unconfirmed."""
    from unittest.mock import MagicMock

    from scholar_mcp._epo_client import EpoClient
    from scholar_mcp._patent_numbers import DocdbNumber
    from scholar_mcp._tools_patent import _fetch_patent_sections

    stub = "k"
    epo = EpoClient(consumer_key=stub, consumer_secret=stub, _client=MagicMock())
    epo.get_biblio = AsyncMock(return_value={"title": "Patent"})  # type: ignore[method-assign]
    epo.get_citations = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "patent_refs": [],
            "npl_refs": [
                {"raw": "HOWARD, A.: MobileNets. CoRR, abs/1704.04861, (2017)"},
                {"raw": _GERMAN},
            ],
        }
    )
    service.s2.batch_resolve = AsyncMock(return_value=[{"paperId": "mn"}])
    service.s2.match_title = AsyncMock(return_value=_XCEPTION)

    result = await _fetch_patent_sections(
        doc=DocdbNumber("DE", "102025108780", "A1"),
        sections=["citations"],
        epo=epo,
        cache=service.cache,
        s2=service.s2,
    )

    mobilenet, xception = result["citations"]["npl_refs"]
    assert service.s2.batch_resolve.await_args.args[0] == ["ARXIV:1704.04861"]
    assert mobilenet["paper"] == {"paperId": "mn"}
    assert mobilenet["confidence"] == "high"
    assert xception["candidate"] == _XCEPTION
    assert xception["confidence"] == "unconfirmed"


async def test_match_without_a_year_to_compare_is_kept() -> None:
    """With no year on either side, the title check alone decides."""
    raw = "- CHOLLET, François: Xception: Deep learning with depthwise separable convolutions."
    entries: list[dict[str, Any]] = [{"raw": raw, "confidence": None}]
    candidate = {k: v for k, v in _XCEPTION.items() if k != "year"}
    await attach_title_candidates(entries, _s2(return_value=candidate), "EP.1.A1")
    assert entries[0]["candidate"] == candidate


@pytest.mark.parametrize(
    "raw",
    [
        "In: " * 50_000,
        "(" + "1999 " * 50_000,
        "a" * 200_000 + ": title words here",
        ". " * 100_000,
    ],
    ids=["many-in-colons", "unclosed-years", "long-authors", "many-sentences"],
)
def test_guess_title_stays_fast_on_hostile_text(raw: str) -> None:
    """Citation text is untrusted: no input may make the guess slow."""
    import time

    started = time.perf_counter()
    guess_title(raw)
    assert time.perf_counter() - started < 1.0

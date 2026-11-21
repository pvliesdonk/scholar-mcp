"""Books cited by a patent's non-patent literature (#70).

The citation strings are shaped like the ones EPO returned on 2026-11-21 for
patents matching ``ct=ISBN``.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import Jobs

from scholar_mcp._cache import checked_isbn13
from scholar_mcp._epo_client import EpoClient
from scholar_mcp._tools_patent import register_patent_tools
from scholar_mcp.domain import Service
from tests.conftest import tasks_server

_BOOK = "VAJNA, Sándor [et al.]: CAx für Ingenieure. Wiesbaden : Springer, 2018. ISBN 978-3-662-54623-9."
_CHAPTER = (
    "HARTMANN, Dietrich: Einführung in Expertensysteme. In: Technische "
    "Expertensysteme. Berlin : Springer, 1990. Kap. 1, S. 1-44. ISBN 978-3-540-52155-6."
)
_PAPER_WITH_ISBN = (
    "PHANG, K.: A 3-V CMOS optical preamplifier. In: Proceedings of ISCAS 1998, "
    "S. 305-308. ISBN 0-7803-4455-3. DOI 10.1109/ISCAS.1998.704011"
)
_BAD_ISBN = "Some handbook, 2001. ISBN 978-3-662-54623-0."

_EDITION = {
    "title": "CAx für Ingenieure",
    "publishers": ["Springer"],
    "publish_date": "2018",
    "isbn_13": ["9783662546239"],
    "key": "/books/OL1M",
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("978-3-662-54623-9", "9783662546239"),
        ("9783540521556", "9783540521556"),
        ("0-7803-4455-3", "9780780344556"),
        ("080442957X", "9780804429573"),
        ("978-3-662-54623-0", None),  # wrong check digit
        ("0-7803-4455-4", None),
        ("2020123456", None),  # a ten-digit number that is no ISBN
        ("0143-8166", None),  # an ISSN
        ("", None),
    ],
)
def test_checked_isbn13(raw: str, expected: str | None) -> None:
    assert checked_isbn13(raw) == expected


def _app(service: Service, jobs: Jobs, npl: list[str]) -> FastMCP:
    citations = {"patent_refs": [], "npl_refs": [{"raw": r, "doi": None} for r in npl]}
    stub = "k"
    epo = EpoClient(consumer_key=stub, consumer_secret=stub, _client=MagicMock())
    epo.get_biblio = AsyncMock(return_value={"title": "Patent"})  # type: ignore[method-assign]
    epo.get_citations = AsyncMock(return_value=citations)  # type: ignore[method-assign]
    service.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]  # noqa: ARG001
        yield {"service": service}

    app = tasks_server("test", lifespan=lifespan)
    register_patent_tools(app, jobs)
    return app


async def _npl_refs(app: FastMCP) -> list[dict[str, Any]]:
    async with Client(app) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "DE102025118911A1", "sections": ["citations"]},
        )
    return json.loads(result.content[0].text)["citations"]["npl_refs"]  # type: ignore[no-any-return]


async def test_cited_books_are_resolved(service: Service, slow_jobs: Jobs) -> None:
    service.openlibrary.get_by_isbn = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda isbn: _EDITION if isbn == "9783662546239" else None
    )
    service.s2.batch_resolve = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"paperId": "p1", "title": "A 3-V CMOS optical preamplifier"}]
    )
    app = _app(service, slow_jobs, [_BOOK, _CHAPTER, _PAPER_WITH_ISBN, _BAD_ISBN])

    book, chapter, paper, bad = await _npl_refs(app)

    assert book["book"]["title"] == "CAx für Ingenieure"
    assert book["confidence"] == "high"
    # Open Library has no edition: the validated ISBN is kept for the caller.
    assert "book" not in chapter
    assert chapter["isbn"] == "9783540521556"
    assert chapter["chapter_info"]["isbn"] == "9783540521556"  # kept alongside
    # A resolved paper is not also looked up as a book.
    assert paper["paper"]["paperId"] == "p1"
    assert "book" not in paper and "isbn" not in paper
    # An ISBN with a wrong check digit is not looked up.
    assert "book" not in bad and "isbn" not in bad
    looked_up = [c.args[0] for c in service.openlibrary.get_by_isbn.await_args_list]
    assert sorted(looked_up) == ["9783540521556", "9783662546239"]


async def test_resolved_books_are_cached(service: Service, slow_jobs: Jobs) -> None:
    service.openlibrary.get_by_isbn = AsyncMock(return_value=_EDITION)  # type: ignore[method-assign]
    app = _app(service, slow_jobs, [_BOOK])

    first = await _npl_refs(app)
    second = await _npl_refs(app)

    assert first[0]["book"] == second[0]["book"]
    service.openlibrary.get_by_isbn.assert_awaited_once()


async def test_open_library_failure_keeps_the_isbn(
    service: Service, slow_jobs: Jobs, caplog: pytest.LogCaptureFixture
) -> None:
    service.openlibrary.get_by_isbn = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.ConnectError("down")
    )
    app = _app(service, slow_jobs, [_BOOK])

    with caplog.at_level(logging.WARNING):
        (entry,) = await _npl_refs(app)

    assert entry["isbn"] == "9783662546239"
    assert entry["confidence"] is None
    assert any("npl_book_resolution_failed" in m for m in caplog.messages)

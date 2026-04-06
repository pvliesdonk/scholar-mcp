"""Tests for book enrichment of paper records."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._book_enrichment import enrich_books
from scholar_mcp._server_deps import ServiceBundle

OL_BASE = "https://openlibrary.org"

SAMPLE_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_13": ["9780201633610"],
    "isbn_10": ["0201633612"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns"],
}


def _make_paper(
    *,
    paper_id: str = "p1",
    title: str = "A Paper",
    publication_types: list[str] | None = None,
    isbn: str | None = None,
) -> dict:
    paper: dict = {
        "paperId": paper_id,
        "title": title,
        "year": 2020,
    }
    if publication_types:
        paper["publicationTypes"] = publication_types
    if isbn:
        paper["externalIds"] = {"ISBN": isbn}
    return paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_triggered_by_isbn(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper = _make_paper(isbn="9780201633610")
    await enrich_books([paper], bundle)
    assert "book_metadata" in paper
    assert paper["book_metadata"]["publisher"] == "Addison-Wesley"
    assert paper["book_metadata"]["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_triggered_by_publication_type_with_isbn(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper = _make_paper(publication_types=["Book"], isbn="9780201633610")
    await enrich_books([paper], bundle)
    assert "book_metadata" in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_skipped_for_book_type_without_isbn(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    paper = _make_paper(publication_types=["Book"])
    await enrich_books([paper], bundle)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_skipped_for_regular_paper(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    paper = _make_paper()
    await enrich_books([paper], bundle)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_failure_leaves_paper_unchanged(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(return_value=httpx.Response(500))
    paper = _make_paper(isbn="9780201633610")
    await enrich_books([paper], bundle)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_uses_cache_on_second_call(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper1 = _make_paper(isbn="9780201633610")
    await enrich_books([paper1], bundle)
    assert "book_metadata" in paper1

    # Second call — API should not be hit (cache)
    paper2 = _make_paper(isbn="9780201633610")
    await enrich_books([paper2], bundle)
    assert "book_metadata" in paper2
    assert paper2["book_metadata"]["publisher"] == "Addison-Wesley"


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_batch_multiple_papers(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    papers = [
        _make_paper(paper_id="p1", isbn="9780201633610"),
        _make_paper(paper_id="p2"),  # no ISBN, should be skipped
        _make_paper(paper_id="p3", isbn="9780201633610"),  # same ISBN, cache hit
    ]
    await enrich_books(papers, bundle)
    assert "book_metadata" in papers[0]
    assert "book_metadata" not in papers[1]
    assert "book_metadata" in papers[2]

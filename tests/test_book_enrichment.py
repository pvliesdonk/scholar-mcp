"""Tests for book enrichment of paper records."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._book_enrichment import (
    _extract_author_keys,
    enrich_authors_from_work,
    enrich_books,
)
from scholar_mcp._rate_limiter import RateLimitedError
from scholar_mcp.domain import Service

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
    respx_mock: respx.MockRouter, service: Service
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper = _make_paper(isbn="9780201633610")
    await enrich_books([paper], service)
    assert "book_metadata" in paper
    assert paper["book_metadata"]["publisher"] == "Addison-Wesley"
    assert paper["book_metadata"]["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_triggered_by_publication_type_with_isbn(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper = _make_paper(publication_types=["Book"], isbn="9780201633610")
    await enrich_books([paper], service)
    assert "book_metadata" in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_skipped_for_book_type_without_isbn(
    respx_mock: respx.MockRouter,  # noqa: ARG001
    service: Service,
) -> None:
    paper = _make_paper(publication_types=["Book"])
    await enrich_books([paper], service)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_skipped_for_regular_paper(
    respx_mock: respx.MockRouter,  # noqa: ARG001
    service: Service,
) -> None:
    paper = _make_paper()
    await enrich_books([paper], service)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_failure_leaves_paper_unchanged(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(return_value=httpx.Response(500))
    paper = _make_paper(isbn="9780201633610")
    await enrich_books([paper], service)
    assert "book_metadata" not in paper


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_uses_cache_on_second_call(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    paper1 = _make_paper(isbn="9780201633610")
    await enrich_books([paper1], service)
    assert "book_metadata" in paper1

    # Second call — API should not be hit (cache)
    paper2 = _make_paper(isbn="9780201633610")
    await enrich_books([paper2], service)
    assert "book_metadata" in paper2
    assert paper2["book_metadata"]["publisher"] == "Addison-Wesley"


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_edition_without_work_id(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """Edition without a works key skips the work-cache write."""
    edition_no_work = {
        "title": "Standalone Edition",
        "publishers": ["Publisher"],
        "isbn_13": ["9781111111111"],
        "key": "/books/OL8888888M",
    }
    respx_mock.get("/isbn/9781111111111.json").mock(
        return_value=httpx.Response(200, json=edition_no_work)
    )
    paper = _make_paper(isbn="9781111111111")
    await enrich_books([paper], service)
    assert "book_metadata" in paper
    assert paper["book_metadata"]["isbn_13"] == "9781111111111"
    assert paper["book_metadata"]["openlibrary_work_id"] is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_batch_multiple_papers(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    papers = [
        _make_paper(paper_id="p1", isbn="9780201633610"),
        _make_paper(paper_id="p2"),  # no ISBN, should be skipped
        _make_paper(paper_id="p3", isbn="9780201633610"),  # same ISBN, cache hit
    ]
    await enrich_books(papers, service)
    assert "book_metadata" in papers[0]
    assert "book_metadata" not in papers[1]
    assert "book_metadata" in papers[2]


def test_to_enrichment_dict_includes_authors() -> None:
    from scholar_mcp._book_enrichment import _to_enrichment_dict

    book: dict = {
        "title": "Test",
        "authors": ["Alice", "Bob"],
        "publisher": "Publisher",
        "edition": None,
        "isbn_13": "9781234567890",
        "cover_url": None,
        "openlibrary_work_id": "OL123W",
        "description": None,
        "subjects": [],
        "page_count": None,
    }
    result = _to_enrichment_dict(book)
    assert result["authors"] == ["Alice", "Bob"]


def test_to_enrichment_dict_empty_authors_defaults_to_list() -> None:
    from scholar_mcp._book_enrichment import _to_enrichment_dict

    book: dict = {"title": "Test"}
    result = _to_enrichment_dict(book)
    assert result["authors"] == []


# --- _extract_author_keys branch coverage ---


def test_extract_author_keys_skips_non_dict_entries() -> None:
    """Non-dict entries in work['authors'] are ignored."""
    work = {"authors": ["not-a-dict", None, 42]}
    assert _extract_author_keys(work) == []


def test_extract_author_keys_skips_non_dict_author_value() -> None:
    """Entry dict where 'author' is not a dict is ignored."""
    work = {"authors": [{"author": "/authors/OL123A"}]}
    assert _extract_author_keys(work) == []


def test_extract_author_keys_happy_path() -> None:
    work = {
        "authors": [
            {"author": {"key": "/authors/OL239963A"}},
            {"author": {"key": "/authors/OL239964A"}},
        ]
    }
    assert _extract_author_keys(work) == ["/authors/OL239963A", "/authors/OL239964A"]


# --- enrich_authors_from_work branch coverage ---


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrich_authors_already_populated(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """Early-returns without fetching when authors already set."""
    book: dict = {"authors": ["Already Here"], "openlibrary_work_id": "OL1W"}
    await enrich_authors_from_work(book, service)
    assert book["authors"] == ["Already Here"]
    assert not respx_mock.calls


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrich_authors_work_returns_none(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """No-ops when the work endpoint returns 404."""
    respx_mock.get("/works/OL999W.json").mock(return_value=httpx.Response(404))
    book: dict = {"authors": [], "openlibrary_work_id": "OL999W"}
    await enrich_authors_from_work(book, service)
    assert book["authors"] == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrich_authors_work_has_no_author_keys(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """No-ops when the work has no recognisable author entries."""
    respx_mock.get("/works/OL1W.json").mock(
        return_value=httpx.Response(200, json={"title": "Anon", "authors": []})
    )
    book: dict = {"authors": [], "openlibrary_work_id": "OL1W"}
    await enrich_authors_from_work(book, service)
    assert book["authors"] == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrich_authors_all_author_fetches_return_none(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """No-ops when every get_author call returns None (404)."""
    respx_mock.get("/works/OL1W.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "authors": [{"author": {"key": "/authors/OL999A"}}],
            },
        )
    )
    respx_mock.get("/authors/OL999A.json").mock(return_value=httpx.Response(404))
    book: dict = {"authors": [], "openlibrary_work_id": "OL1W"}
    await enrich_authors_from_work(book, service)
    assert book["authors"] == []


# --- _enrich_one RateLimitedError propagation ---


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrichment_rate_limited_error_propagates(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """RateLimitedError is re-raised, not swallowed."""
    respx_mock.get("/isbn/9780201633610.json").mock(
        side_effect=RateLimitedError("rate limited")
    )
    paper = _make_paper(isbn="9780201633610")
    with pytest.raises(RateLimitedError):
        await enrich_books([paper], service)


# --- #403: a failed author lookup must not be cached as "no authors" ---


@pytest.mark.respx(base_url=OL_BASE)
async def test_fill_authors_from_cache_uses_the_work_row(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """The cached work record answers without touching the network (#403).

    `batch_resolve` resolves ISBNs concurrently, so enriching there over the
    network would fan out one work fetch per ISBN against a rate-limited API --
    plausibly the condition that emptied the authors in the first place. The
    cache-only path costs nothing.
    """
    from scholar_mcp._book_enrichment import fill_authors_from_cache

    await service.cache.set_book_by_work(
        "OL6030812W", {"title": "Design Patterns", "authors": ["Erich Gamma"]}
    )
    book: dict = {"authors": [], "openlibrary_work_id": "OL6030812W"}

    await fill_authors_from_cache(book, service)

    assert book["authors"] == ["Erich Gamma"]
    assert not respx_mock.calls


@pytest.mark.respx(base_url=OL_BASE)
async def test_enrich_authors_uses_the_cache_without_touching_the_network(
    respx_mock: respx.MockRouter, service: Service
) -> None:
    """#403's own scenario: the work row already held the authors.

    Open Library refusing the request is what left ``authors: []`` cached for
    30 days while the work record for the same book sat in the cache with
    every author present. No route is registered here, so reaching for the
    network at all fails the test -- which is the assertion.
    """
    from scholar_mcp._book_enrichment import enrich_authors_from_work

    await service.cache.set_book_by_work(
        "OL6030812W",
        {"title": "Design Patterns", "authors": ["Erich Gamma", "Richard Helm"]},
    )
    book: dict = {"authors": [], "openlibrary_work_id": "OL6030812W"}

    await enrich_authors_from_work(book, service)

    assert book["authors"] == ["Erich Gamma", "Richard Helm"]
    assert not respx_mock.calls


async def test_cache_book_record_will_not_clobber_a_richer_work_row(
    service: Service,
) -> None:
    """An empty author list must not overwrite a work row that has authors.

    `set_book_by_work` is INSERT OR REPLACE, so before #403 a weak resolver
    could destroy authors that `_resolve_work` had already resolved correctly.
    """
    from scholar_mcp._book_enrichment import cache_book_record

    await service.cache.set_book_by_work(
        "OL6030812W", {"title": "Design Patterns", "authors": ["Erich Gamma"]}
    )
    thin: dict = {
        "title": "Design Patterns",
        "authors": [],
        "openlibrary_work_id": "OL6030812W",
    }

    await cache_book_record(thin, service, isbn="9780201633610")

    kept = await service.cache.get_book_by_work("OL6030812W")
    assert kept is not None
    assert kept["authors"] == ["Erich Gamma"]


async def test_cache_book_record_writes_the_work_row_when_none_exists(
    service: Service,
) -> None:
    """With nothing cached, the record is written even with no authors.

    Refusing to cache would make a genuinely author-less book re-fetch on
    every request.
    """
    from scholar_mcp._book_enrichment import cache_book_record

    thin: dict = {"title": "Anon", "authors": [], "openlibrary_work_id": "OL999W"}

    await cache_book_record(thin, service, isbn="9780000000000")

    written = await service.cache.get_book_by_work("OL999W")
    assert written is not None
    assert written["authors"] == []
    by_isbn = await service.cache.get_book_by_isbn("9780000000000")
    assert by_isbn is not None


async def test_fill_authors_from_cache_leaves_existing_authors_alone(
    service: Service,
) -> None:
    """A record that already has authors is never second-guessed by the cache.

    The cached work row can be staler than what this call just resolved, so
    the guard has to come before the lookup.
    """
    from scholar_mcp._book_enrichment import fill_authors_from_cache

    await service.cache.set_book_by_work(
        "OL6030812W", {"title": "Design Patterns", "authors": ["Stale Name"]}
    )
    book: dict = {"authors": ["Erich Gamma"], "openlibrary_work_id": "OL6030812W"}

    await fill_authors_from_cache(book, service)

    assert book["authors"] == ["Erich Gamma"]


async def test_fill_authors_from_cache_no_ops_without_a_work_id(
    service: Service,
) -> None:
    """With no work ID there is no key to look the authors up under."""
    from scholar_mcp._book_enrichment import fill_authors_from_cache

    book: dict = {"authors": []}

    await fill_authors_from_cache(book, service)

    assert book["authors"] == []

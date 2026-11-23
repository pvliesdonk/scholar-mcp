"""Tests for mapping CrossRef book-chapter works onto ``chapter_info``."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from scholar_mcp._enricher_crossref_chapter import (
    CrossRefChapterEnricher,
    chapter_info_from_crossref,
    clean_crossref_text,
    parent_doi,
)
from scholar_mcp._enrichment import Enricher
from scholar_mcp._rate_limiter import RateLimitedError
from tests.fixtures.crossref_chapters import (
    cambridge_chapter,
    cambridge_parent,
    elsevier_chapter,
    ieee_chapter,
    springer_chapter,
    springer_parent,
)


def _service(
    *, cached: dict[str, Any] | None = None, fetched: dict[str, Any] | None = None
) -> MagicMock:
    """Return a mock service whose CrossRef cache and client answer as given."""
    service = MagicMock()
    service.cache.get_crossref = AsyncMock(return_value=cached)
    service.cache.set_crossref = AsyncMock()
    service.crossref.get_by_doi = AsyncMock(return_value=fetched)
    return service


# ---------------------------------------------------------------------------
# Pure mapping
# ---------------------------------------------------------------------------


def test_series_chapter_takes_book_title_from_last_container_title() -> None:
    """With two container titles the first is the series, the last the book."""
    info = chapter_info_from_crossref(springer_chapter(), None)
    assert info["parent_title"] == (
        "Cultural Heritage-Based Sustainable Tourism Approaches"
    )


def test_series_chapter_with_parent_gets_editors_and_subtitle() -> None:
    """Editors and the book subtitle come from the parent book record."""
    info = chapter_info_from_crossref(springer_chapter(), springer_parent())
    assert info == {
        "citation_source": "crossref",
        "chapter_title": "Heritage Trails and Local Economies",
        "parent_title": (
            "Cultural Heritage-Based Sustainable Tourism Approaches: "
            "Case Studies from the Mediterranean"
        ),
        "parent_doi": "10.1007/978-3-031-93275-5",
        "editors": ["Maria Rossi", "Jan de Vries"],
        "publisher": "Springer Nature Switzerland",
        "publisher_location": "Cham",
        "edition": "1",
        "isbn": "9783031932748",
        "pages": "15-32",
        "page_start": 15,
        "page_end": 32,
    }


def test_print_isbn_is_chosen_by_isbn_type_not_order() -> None:
    """The electronic ISBN listed first is not reported over the print one."""
    info = chapter_info_from_crossref(springer_chapter(), None)
    assert info["isbn"] == "9783031932748"


def test_electronic_isbn_is_used_when_no_print_isbn() -> None:
    """A chapter with only an electronic ISBN reports that one."""
    info = chapter_info_from_crossref(cambridge_chapter(), None)
    assert info["isbn"] == "9781139199100"


def test_isbn_with_bad_check_digit_is_skipped() -> None:
    """An ISBN whose check digit fails is not reported."""
    chapter = ieee_chapter()
    chapter["ISBN"] = ["9781119000007"]
    chapter["isbn-type"] = [{"value": "9781119000007", "type": "print"}]
    assert "isbn" not in chapter_info_from_crossref(chapter, None)


def test_isbn_falls_back_to_parent_book() -> None:
    """A chapter without ISBN takes its parent book's print ISBN."""
    chapter = springer_chapter()
    del chapter["ISBN"], chapter["isbn-type"]
    info = chapter_info_from_crossref(chapter, springer_parent())
    assert info["isbn"] == "9783031932748"


def test_isbn_from_untyped_list_when_isbn_type_missing() -> None:
    """Without ``isbn-type`` the ``ISBN`` array is used as given."""
    chapter = elsevier_chapter()
    del chapter["isbn-type"]
    assert chapter_info_from_crossref(chapter, None)["isbn"] == "9780123739476"


def test_chapter_editor_wins_over_parent_editor() -> None:
    """Editors deposited on the chapter take precedence over the book's."""
    info = chapter_info_from_crossref(cambridge_chapter(), cambridge_parent())
    assert info["editors"] == ["Helen Clark"]


def test_escaped_markup_in_container_title_is_stripped() -> None:
    """``&lt;I&gt;`` is unescaped, then stripped, and whitespace collapsed."""
    info = chapter_info_from_crossref(cambridge_chapter(), None)
    assert info["parent_title"] == "Studies in Ancient Law"


def test_non_numeric_page_range_keeps_raw_string_only() -> None:
    """``xiii-xiii`` is reported as ``pages`` without integer bounds."""
    info = chapter_info_from_crossref(cambridge_chapter(), None)
    assert info["pages"] == "xiii-xiii"
    assert "page_start" not in info
    assert "page_end" not in info


def test_electronic_page_suffix_keeps_raw_string_only() -> None:
    """``639-650.e3`` is not forced into integers."""
    info = chapter_info_from_crossref(elsevier_chapter(), None)
    assert info["pages"] == "639-650.e3"
    assert "page_start" not in info


def test_single_numeric_page_sets_start_only() -> None:
    """A single page number sets ``page_start`` and no ``page_end``."""
    chapter = ieee_chapter()
    chapter["page"] = "42"
    info = chapter_info_from_crossref(chapter, None)
    assert info["page_start"] == 42
    assert "page_end" not in info


def test_chapter_without_optional_fields_maps_what_exists() -> None:
    """No page, author, location or edition: those keys are absent."""
    info = chapter_info_from_crossref(ieee_chapter(), None)
    assert info == {
        "citation_source": "crossref",
        "chapter_title": "Channel Models",
        "parent_title": "Wireless Systems Handbook",
        "parent_doi": "10.1109/9781119000000",
        "publisher": "IEEE",
        "isbn": "9781119000006",
    }


def test_chapter_without_container_title_takes_parent_title() -> None:
    """When the chapter has no container title the parent's title is used."""
    chapter = cambridge_chapter()
    chapter["container-title"] = []
    info = chapter_info_from_crossref(chapter, cambridge_parent())
    assert info["parent_title"] == "Studies in Ancient Law"


def test_subtitle_already_in_title_is_not_repeated() -> None:
    """A container title that already holds the subtitle is left as is."""
    chapter = springer_chapter()
    chapter["container-title"] = [
        "Cultural Heritage-Based Sustainable Tourism Approaches: "
        "Case Studies from the Mediterranean"
    ]
    info = chapter_info_from_crossref(chapter, springer_parent())
    assert info["parent_title"].count("Case Studies") == 1


def test_organisation_editor_uses_name() -> None:
    """An editor without given or family name is reported by ``name``."""
    parent = springer_parent()
    parent["editor"] = [{"name": "Heritage Council"}, {"given": " "}, "junk"]
    info = chapter_info_from_crossref(springer_chapter(), parent)
    assert info["editors"] == ["Heritage Council"]


def test_clean_crossref_text_keeps_plain_text() -> None:
    """Text without markup passes through unchanged."""
    assert clean_crossref_text("Law in Context") == "Law in Context"
    assert clean_crossref_text("<i>A</i> &amp; B") == "A & B"


@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        (
            {"is-part-of": [{"id-type": "doi", "id": "https://doi.org/10.1/b"}]},
            "10.1/b",
        ),
        (
            {"is-part-of": [{"id-type": "doi", "id": "http://dx.doi.org/10.1/b"}]},
            "10.1/b",
        ),
        ({"is-part-of": [{"id-type": "doi", "id": "10.1/b"}]}, "10.1/b"),
        ({"is-part-of": [{"id-type": "issn", "id": "1234-5678"}]}, None),
        ({"is-part-of": [{"id-type": "doi", "id": "https://doi.org/10.1/A"}]}, None),
        ({"is-part-of": ["junk"]}, None),
        ({}, None),
    ],
    ids=["url", "dx-url", "bare", "not-doi", "self-link", "junk", "none"],
)
def test_parent_doi(relation: dict[str, Any], expected: str | None) -> None:
    """``is-part-of`` URLs are reduced to a bare DOI; self links are ignored."""
    assert parent_doi({"DOI": "10.1/a", "relation": relation}) == expected


# ---------------------------------------------------------------------------
# Enricher
# ---------------------------------------------------------------------------


def test_satisfies_enricher_protocol() -> None:
    """The enricher satisfies the protocol and runs after the CrossRef one."""
    enricher = CrossRefChapterEnricher()
    assert isinstance(enricher, Enricher)
    assert enricher.phase == 1
    assert enricher.tags == frozenset({"papers"})


def test_registered_in_pipeline_after_crossref() -> None:
    """The production pipeline runs the chapter enricher in a later phase."""
    from scholar_mcp.domain import _build_enrichment_pipeline

    pipeline = _build_enrichment_pipeline()
    assert "crossref" in [e.name for e in pipeline._phases[0]]
    assert "crossref_chapter" in [e.name for e in pipeline._phases[1]]


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"crossref_metadata": {"type": "book-chapter"}}, True),
        ({"crossref_metadata": {"type": "journal-article"}}, False),
        ({"externalIds": {"DOI": "10.1/a"}}, False),
        (
            {
                "crossref_metadata": {"type": "book-chapter"},
                "chapter_info": {"citation_source": "crossref"},
            },
            False,
        ),
    ],
    ids=["chapter", "article", "no-crossref", "already-mapped"],
)
def test_can_enrich(record: dict[str, Any], expected: bool) -> None:
    """Only a CrossRef book chapter without ``chapter_info`` is enriched."""
    assert CrossRefChapterEnricher().can_enrich(record) is expected


async def test_enrich_fetches_and_caches_parent() -> None:
    """A cache miss fetches the parent book once and caches it by its DOI."""
    parent = springer_parent()
    service = _service(fetched=parent)
    record: dict[str, Any] = {"crossref_metadata": springer_chapter()}

    await CrossRefChapterEnricher().enrich(record, service)

    service.crossref.get_by_doi.assert_awaited_once_with("10.1007/978-3-031-93275-5")
    service.cache.set_crossref.assert_awaited_once_with(
        "10.1007/978-3-031-93275-5", parent
    )
    assert record["chapter_info"]["editors"] == ["Maria Rossi", "Jan de Vries"]
    assert record["crossref_metadata"] == springer_chapter()


async def test_enrich_uses_cached_parent() -> None:
    """A cached parent book is not fetched again."""
    service = _service(cached=springer_parent())
    record: dict[str, Any] = {"crossref_metadata": springer_chapter()}

    await CrossRefChapterEnricher().enrich(record, service)

    service.crossref.get_by_doi.assert_not_awaited()
    service.cache.set_crossref.assert_not_awaited()
    assert record["chapter_info"]["editors"] == ["Maria Rossi", "Jan de Vries"]


async def test_enrich_without_parent_link_makes_no_request() -> None:
    """An Elsevier chapter without is-part-of is mapped from itself alone."""
    service = _service()
    record: dict[str, Any] = {"crossref_metadata": elsevier_chapter()}

    await CrossRefChapterEnricher().enrich(record, service)

    service.cache.get_crossref.assert_not_awaited()
    service.crossref.get_by_doi.assert_not_awaited()
    assert record["chapter_info"] == {
        "citation_source": "crossref",
        "chapter_title": "Introduction",
        "parent_title": "Encyclopedia of Applied Examples",
        "publisher": "Elsevier",
        "isbn": "9780123739476",
        "pages": "639-650.e3",
    }


async def test_enrich_when_parent_lookup_finds_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A parent CrossRef cannot return still yields chapter_info, logged at DEBUG."""
    service = _service(fetched=None)
    record: dict[str, Any] = {"crossref_metadata": springer_chapter()}

    with caplog.at_level(
        logging.DEBUG, logger="scholar_mcp._enricher_crossref_chapter"
    ):
        await CrossRefChapterEnricher().enrich(record, service)

    service.cache.set_crossref.assert_not_awaited()
    info = record["chapter_info"]
    assert info["citation_source"] == "crossref"
    assert "editors" not in info
    assert info["parent_doi"] == "10.1007/978-3-031-93275-5"
    assert any(
        r.msg.startswith("crossref_chapter_without_parent") for r in caplog.records
    )
    assert all(r.levelno == logging.DEBUG for r in caplog.records)


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("database is locked"),
        ValueError("corrupt cached row"),
        httpx.ConnectError("unreachable"),
    ],
    ids=["cache-locked", "cache-corrupt", "transport"],
)
async def test_enrich_when_parent_lookup_raises(error: Exception) -> None:
    """An expected cache or transport failure is a missing parent."""
    service = _service()
    service.cache.get_crossref = AsyncMock(side_effect=error)
    record: dict[str, Any] = {"crossref_metadata": springer_chapter()}

    await CrossRefChapterEnricher().enrich(record, service)

    assert record["chapter_info"]["parent_title"] == (
        "Cultural Heritage-Based Sustainable Tourism Approaches"
    )


async def test_enrich_when_parent_lookup_is_throttled() -> None:
    """A throttled parent lookup maps the chapter without the book's fields."""
    service = _service()
    service.crossref.get_by_doi = AsyncMock(side_effect=RateLimitedError())
    record: dict[str, Any] = {"crossref_metadata": springer_chapter()}

    await CrossRefChapterEnricher().enrich(record, service)

    assert "editors" not in record["chapter_info"]
    service.cache.set_crossref.assert_not_awaited()


async def test_enrich_lets_unexpected_parent_errors_propagate() -> None:
    """A bug in the parent lookup reaches the pipeline instead of hiding."""
    service = _service()
    service.cache.get_crossref = AsyncMock(side_effect=RuntimeError("bug"))
    record: dict[str, Any] = {"crossref_metadata": springer_chapter()}

    with pytest.raises(RuntimeError):
        await CrossRefChapterEnricher().enrich(record, service)
    assert "chapter_info" not in record


# ---------------------------------------------------------------------------
# Through get_paper's pipeline, against mocked HTTP
# ---------------------------------------------------------------------------


@respx.mock
async def test_pipeline_maps_chapter_and_caches_parent(service: Any) -> None:
    """CrossRef enrichment then chapter mapping, parent served from cache next."""
    from scholar_mcp._enricher_crossref import CrossRefEnricher
    from scholar_mcp._enrichment import EnrichmentPipeline

    chapter_doi = "10.1007/978-3-031-93275-5_2"
    parent_url = "https://api.crossref.org/works/10.1007/978-3-031-93275-5"
    respx.get(f"https://api.crossref.org/works/{chapter_doi}").mock(
        return_value=httpx.Response(200, json={"message": springer_chapter()})
    )
    parent_route = respx.get(parent_url).mock(
        return_value=httpx.Response(200, json={"message": springer_parent()})
    )
    pipeline = EnrichmentPipeline([CrossRefEnricher(), CrossRefChapterEnricher()])

    first: dict[str, Any] = {"externalIds": {"DOI": chapter_doi}}
    second: dict[str, Any] = {"externalIds": {"DOI": chapter_doi}}
    await pipeline.enrich([first], service)
    await pipeline.enrich([second], service)

    assert first["chapter_info"]["citation_source"] == "crossref"
    assert first["chapter_info"]["editors"] == ["Maria Rossi", "Jan de Vries"]
    assert second["chapter_info"] == first["chapter_info"]
    assert first["crossref_metadata"]["type"] == "book-chapter"
    assert parent_route.call_count == 1


@respx.mock
async def test_pipeline_throttled_parent_still_maps_chapter(service: Any) -> None:
    """A 429 on the parent leaves the chapter mapped without editors."""
    from scholar_mcp._enricher_crossref import CrossRefEnricher
    from scholar_mcp._enrichment import EnrichmentPipeline

    chapter_doi = "10.1007/978-3-031-93275-5_2"
    respx.get(f"https://api.crossref.org/works/{chapter_doi}").mock(
        return_value=httpx.Response(200, json={"message": springer_chapter()})
    )
    respx.get("https://api.crossref.org/works/10.1007/978-3-031-93275-5").mock(
        return_value=httpx.Response(429)
    )
    pipeline = EnrichmentPipeline([CrossRefEnricher(), CrossRefChapterEnricher()])
    record: dict[str, Any] = {"externalIds": {"DOI": chapter_doi}}

    await pipeline.enrich([record], service)

    assert record["chapter_info"]["citation_source"] == "crossref"
    assert "editors" not in record["chapter_info"]
    assert await service.cache.get_crossref("10.1007/978-3-031-93275-5") is None

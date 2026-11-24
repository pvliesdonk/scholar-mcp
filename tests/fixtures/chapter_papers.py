"""Semantic Scholar paper records for book chapters, for the citation tests.

The S2 side of the chapters in :mod:`tests.fixtures.crossref_chapters`: the
DOI, title and authors S2 would return for each. Constructed, not captured.
``chapter_info`` is not written by hand; :func:`with_chapter_info` builds it
from the CrossRef fixtures with the enricher's own mapping, so the
formatter tests read the shape the enrichment pipeline produces.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from scholar_mcp._enricher_crossref_chapter import chapter_info_from_crossref

if TYPE_CHECKING:
    from scholar_mcp._record_types import PaperRecord

# The Springer series chapter, with the one author CrossRef lists.
_SPRINGER_PAPER: dict[str, Any] = {
    "paperId": "5f1c0d2e9a7b4c3d2e1f0a9b8c7d6e5f4a3b2c1d",
    "title": "Heritage Trails and Local Economies",
    "year": 2025,
    "venue": "Advances in Science, Technology & Innovation",
    "authors": [{"authorId": "11", "name": "Ana Silva"}],
    "externalIds": {"DOI": "10.1007/978-3-031-93275-5_2"},
    "publicationTypes": ["Book"],
}

# The IEEE chapter: no author in CrossRef and none in S2 either.
_IEEE_PAPER: dict[str, Any] = {
    "paperId": "0a1b2c3d4e5f60718293a4b5c6d7e8f901234567",
    "title": "Channel Models",
    "year": None,
    "venue": "",
    "authors": [],
    "externalIds": {"DOI": "10.1109/9781119000000.ch3"},
}

# The Elsevier chapter, no is-part-of link; page "639-650.e3".
_ELSEVIER_PAPER: dict[str, Any] = {
    "paperId": "1b2c3d4e5f60718293a4b5c6d7e8f9012345678a",
    "title": "Introduction",
    "year": 2008,
    "venue": "Encyclopedia of Applied Examples",
    "authors": [{"authorId": "12", "name": "Lee Chen"}],
    "externalIds": {"DOI": "10.1016/b978-0-12-373947-6.00001-2"},
}

# The Cambridge preface: front matter with no author, an editor on the
# chapter record, page "xiii-xiii" and an edition number.
_CAMBRIDGE_PAPER: dict[str, Any] = {
    "paperId": "3d4e5f60718293a4b5c6d7e8f9012345678ab1c2",
    "title": "Preface",
    "year": 2012,
    "venue": "",
    "authors": [],
    "externalIds": {"DOI": "10.1017/cbo9781139199100.007"},
}

# A conference paper Springer deposits as a CrossRef book-chapter (LNCS):
# S2 reports it as a conference paper.
_LNCS_PAPER: dict[str, Any] = {
    "paperId": "2c3d4e5f60718293a4b5c6d7e8f9012345678ab1",
    "title": "U-Net: Convolutional Networks for Biomedical Image Segmentation",
    "year": 2015,
    "venue": "International Conference on Medical Image Computing and "
    "Computer-Assisted Intervention",
    "authors": [{"authorId": "13", "name": "O. Ronneberger"}],
    "externalIds": {"DOI": "10.1007/978-3-319-24574-4_28"},
    "publicationTypes": ["JournalArticle", "Conference"],
}


def springer_paper() -> dict[str, Any]:
    """Return the S2 record of the Springer series chapter."""
    return copy.deepcopy(_SPRINGER_PAPER)


def ieee_paper() -> dict[str, Any]:
    """Return the S2 record of the IEEE chapter, which names no author."""
    return copy.deepcopy(_IEEE_PAPER)


def elsevier_paper() -> dict[str, Any]:
    """Return the S2 record of the Elsevier chapter."""
    return copy.deepcopy(_ELSEVIER_PAPER)


def cambridge_paper() -> dict[str, Any]:
    """Return the S2 record of the Cambridge preface, which names no author."""
    return copy.deepcopy(_CAMBRIDGE_PAPER)


def lncs_paper() -> dict[str, Any]:
    """Return the S2 record of a conference paper deposited as a chapter."""
    return copy.deepcopy(_LNCS_PAPER)


def with_chapter_info(
    paper: dict[str, Any],
    chapter: dict[str, Any],
    parent: dict[str, Any] | None = None,
) -> PaperRecord:
    """Attach the ``chapter_info`` the enricher maps from CrossRef records.

    Args:
        paper: An S2 paper record (mutated and returned).
        chapter: The CrossRef chapter work.
        parent: The CrossRef parent-book work, or ``None``.

    Returns:
        The paper, carrying ``chapter_info``.
    """
    paper["chapter_info"] = chapter_info_from_crossref(chapter, parent)
    return paper  # type: ignore[return-value]

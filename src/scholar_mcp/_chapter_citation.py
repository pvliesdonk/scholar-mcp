"""Book-chapter fields for BibTeX, CSL-JSON and RIS citations (#593).

A paper whose ``chapter_info`` came from a CrossRef ``book-chapter`` work
(see ``docs/design/crossref-book-chapters.md``) is cited as a chapter:
BibTeX ``@incollection``, CSL ``chapter``, RIS ``CHAP``. Why those types and
which field carries each part is recorded in
``docs/design/reference/chapter-citation-entry-types.md``. The names
(authors, editors) are formatted by :mod:`scholar_mcp._citation_formatter`;
this module builds the book-level fields around them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._bibtex_escape import escape_bibtex

if TYPE_CHECKING:
    from ._record_types import BookChapterRecord, PaperRecord

# The entry type :func:`scholar_mcp._citation_formatter.infer_entry_type`
# returns for a chapter.
CHAPTER_ENTRY_TYPE = "incollection"


def chapter_of(paper: PaperRecord) -> BookChapterRecord | None:
    """Return the CrossRef chapter data of a paper, when it names its book.

    Only ``citation_source: "crossref"`` counts: the parsed shape (#64)
    reaches patent NPL entries and ``batch_resolve``, never this path. A
    record without ``parent_title`` names no book to cite it in.

    Args:
        paper: Paper metadata dict.

    Returns:
        The paper's ``chapter_info``, or ``None`` when it is not a chapter
        of a known book.
    """
    info = paper.get("chapter_info")
    if not info or info.get("citation_source") != "crossref":
        return None
    return info if info.get("parent_title") else None


def editors_as_paper(info: BookChapterRecord) -> PaperRecord:
    """Wrap a chapter's editors as an S2-style author list.

    Lets the S2 author formatters write the book's editors exactly as they
    write a paper's authors.

    Args:
        info: The chapter's ``chapter_info``.

    Returns:
        A record holding only ``authors``, one entry per editor.
    """
    return {"authors": [{"name": name} for name in info.get("editors") or []]}


def bibtex_chapter_fields(info: BookChapterRecord, editor: str) -> list[str]:
    """Build the BibTeX fields of a chapter's book.

    Args:
        info: The chapter's ``chapter_info``.
        editor: The formatted ``editor`` value, empty when there are none.

    Returns:
        ``booktitle``, ``editor``, ``pages``, ``publisher``, ``address``,
        ``edition`` and ``isbn``, each only when present, in that order.
    """
    values: list[tuple[str, str | None]] = [
        ("booktitle", _escaped(info.get("parent_title"))),
        ("editor", editor),
        ("pages", _escaped(info.get("pages"))),
        ("publisher", _escaped(info.get("publisher"))),
        ("address", _escaped(info.get("publisher_location"))),
        ("edition", _escaped(info.get("edition"))),
        ("isbn", info.get("isbn")),
    ]
    return [f"  {name} = {{{value}}}" for name, value in values if value]


def _escaped(value: str | None) -> str | None:
    """Escape a BibTeX field value, passing ``None`` through."""
    return escape_bibtex(value) if value else None


def csl_chapter_fields(
    info: BookChapterRecord, editors: list[dict[str, str]]
) -> dict[str, Any]:
    """Build the CSL-JSON variables of a chapter's book.

    Args:
        info: The chapter's ``chapter_info``.
        editors: The editors as CSL name dicts, empty when there are none.

    Returns:
        ``container-title``, ``editor``, ``page``, ``publisher``,
        ``publisher-place``, ``edition`` and ``ISBN``, each only when present.
    """
    values: dict[str, Any] = {
        "container-title": info.get("parent_title"),
        "editor": editors,
        "page": info.get("pages"),
        "publisher": info.get("publisher"),
        "publisher-place": info.get("publisher_location"),
        "edition": info.get("edition"),
        "ISBN": info.get("isbn"),
    }
    return {key: value for key, value in values.items() if value}


def _ris_page_lines(info: BookChapterRecord) -> list[str]:
    """Build the RIS ``SP`` and ``EP`` tags.

    A range of exactly two parts is split at its hyphen (``xiii-xiii``,
    ``639-650.e3``); any other form goes whole into ``SP``, because
    splitting ``P3-660-P3-660`` would invent a start page.
    """
    pages = info.get("pages")
    if not pages:
        return []
    parts = pages.split("-")
    if len(parts) == 2 and all(parts):
        return [f"SP  - {parts[0]}", f"EP  - {parts[1]}"]
    return [f"SP  - {pages}"]


def ris_chapter_lines(info: BookChapterRecord, editor_lines: list[str]) -> list[str]:
    """Build the RIS tags of a chapter's book.

    Args:
        info: The chapter's ``chapter_info``.
        editor_lines: One ``A2`` tag per editor, empty when there are none.

    Returns:
        ``T2`` (book title), the ``A2`` editors, ``SP``/``EP``, ``PB``,
        ``CY``, ``ET`` and ``SN``, each only when present, in that order.
    """
    lines = [f"T2  - {info.get('parent_title')}", *editor_lines]
    lines.extend(_ris_page_lines(info))
    tagged = [
        ("PB", info.get("publisher")),
        ("CY", info.get("publisher_location")),
        ("ET", info.get("edition")),
        ("SN", info.get("isbn")),
    ]
    lines.extend(f"{tag}  - {value}" for tag, value in tagged if value)
    return lines

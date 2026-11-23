"""Map a CrossRef ``book-chapter`` work onto a paper record's ``chapter_info``.

The field rules come from ``docs/design/reference/crossref-book-chapter-fields.md``:
the book title is the *last* ``container-title`` element, editors usually live
on the parent book record reached through ``relation.is-part-of``, and every
chapter field except ``publisher`` is optional.
"""

from __future__ import annotations

import html
import logging
import re
import sqlite3
from typing import Any

import httpx

from ._cache import checked_isbn13
from ._rate_limiter import RateLimitedError

logger = logging.getLogger(__name__)

_DOI_URL_PREFIX = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
_MARKUP_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_WHITESPACE = re.compile(r"\s+")
_NUMERIC_RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")


def clean_crossref_text(value: str) -> str:
    """Unescape HTML entities and strip inline markup from a CrossRef string.

    Unescaping runs first, so an escaped tag such as ``&lt;I&gt;`` is
    stripped too.

    Args:
        value: A title string as CrossRef deposited it.

    Returns:
        The plain text with runs of whitespace collapsed.
    """
    text = _MARKUP_TAG.sub("", html.unescape(value))
    return _WHITESPACE.sub(" ", text).strip()


def _first_text(work: dict[str, Any], key: str) -> str | None:
    """Return the first non-empty cleaned string of an array field."""
    for item in work.get(key) or []:
        if isinstance(item, str) and (text := clean_crossref_text(item)):
            return text
    return None


def parent_doi(chapter: dict[str, Any]) -> str | None:
    """Return the bare DOI of the book a chapter is part of.

    CrossRef gives the ``relation.is-part-of`` id as a full
    ``https://doi.org/`` URL; the prefix is stripped. A link back to the
    chapter itself is ignored.

    Args:
        chapter: The CrossRef work of the chapter.

    Returns:
        The parent book's DOI, or ``None`` when the chapter has no link.
    """
    links = (chapter.get("relation") or {}).get("is-part-of") or []
    own = str(chapter.get("DOI") or "").lower()
    for link in links:
        if not isinstance(link, dict) or link.get("id-type") != "doi":
            continue
        doi = _DOI_URL_PREFIX.sub("", str(link.get("id") or "")).strip()
        if doi and doi.lower() != own:
            return doi
    return None


def _book_title(chapter: dict[str, Any], parent: dict[str, Any] | None) -> str | None:
    """Return the parent book title, with the parent's subtitle when known.

    The last ``container-title`` element is the book; with two elements the
    first is the series.
    """
    titles = [
        text
        for item in chapter.get("container-title") or []
        if isinstance(item, str) and (text := clean_crossref_text(item))
    ]
    title = titles[-1] if titles else None
    if parent is None:
        return title
    title = title or _first_text(parent, "title")
    subtitle = _first_text(parent, "subtitle")
    if title and subtitle and subtitle.lower() not in title.lower():
        return f"{title}: {subtitle}"
    return title


def _names(people: Any) -> list[str]:
    """Return display names ("Given Family", or ``name``) of CrossRef people."""
    names: list[str] = []
    for person in people or []:
        if not isinstance(person, dict):
            continue
        parts = [person.get("given"), person.get("family")]
        name = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
        name = name or str(person.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _isbn(work: dict[str, Any]) -> str | None:
    """Return the print ISBN of a work, else its electronic one.

    ``isbn-type``, not the order of ``ISBN``, says which is print. An ISBN
    whose check digit fails is skipped; the digits are kept as given.
    """
    typed = [
        (str(entry.get("type")), str(entry.get("value") or ""))
        for entry in work.get("isbn-type") or []
        if isinstance(entry, dict)
    ]
    ordered = [v for t, v in typed if t == "print"] + [
        v for t, v in typed if t != "print"
    ]
    ordered += [str(v) for v in work.get("ISBN") or []]
    for value in ordered:
        if checked_isbn13(value) is not None:
            return value.replace("-", "").replace(" ", "").upper()
    return None


def _pages(page: Any) -> dict[str, Any]:
    """Map a CrossRef ``page`` string onto ``pages`` and, when numeric, ints.

    ``page`` takes forms such as ``xiii-xiii`` and ``639-650.e3``, so the raw
    string is always kept and ``page_start``/``page_end`` are set only when
    both ends are plain numbers.
    """
    if not isinstance(page, str) or not page.strip():
        return {}
    raw = page.strip()
    out: dict[str, Any] = {"pages": raw}
    m = _NUMERIC_RANGE.match(raw)
    if m:
        out["page_start"] = int(m.group(1))
        if m.group(2):
            out["page_end"] = int(m.group(2))
    return out


def _string_field(
    chapter: dict[str, Any], parent: dict[str, Any] | None, key: str
) -> str | None:
    """Return a string field from the chapter, else from its parent book."""
    for work in (chapter, parent or {}):
        value = work.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def chapter_info_from_crossref(
    chapter: dict[str, Any], parent: dict[str, Any] | None
) -> dict[str, Any]:
    """Build a ``chapter_info`` dict from a CrossRef chapter and its book.

    Args:
        chapter: The CrossRef work of type ``book-chapter``.
        parent: The CrossRef work of the parent book, or ``None`` when the
            chapter has no link to it or the lookup failed.

    Returns:
        ``chapter_info`` with ``citation_source: "crossref"`` and each field
        CrossRef holds: ``chapter_title``, ``parent_title``, ``parent_doi``,
        ``editors``, ``pages`` (plus ``page_start``/``page_end`` when
        numeric), ``publisher``, ``publisher_location``, ``edition`` and
        ``isbn``. Absent fields are left out.
    """
    info: dict[str, Any] = {"citation_source": "crossref"}
    optional: dict[str, Any] = {
        "chapter_title": _first_text(chapter, "title"),
        "parent_title": _book_title(chapter, parent),
        "parent_doi": parent_doi(chapter),
        "editors": _names(chapter.get("editor"))
        or _names((parent or {}).get("editor")),
        "publisher": _string_field(chapter, parent, "publisher"),
        "publisher_location": _string_field(chapter, parent, "publisher-location"),
        "edition": _string_field(chapter, parent, "edition-number"),
        "isbn": _isbn(chapter) or (_isbn(parent) if parent else None),
    }
    info.update({k: v for k, v in optional.items() if v})
    info.update(_pages(chapter.get("page")))
    return info


async def _fetch_parent(doi: str, service: Any) -> dict[str, Any] | None:
    """Return the CrossRef work of a parent book, through the CrossRef cache.

    A missing, throttled or failed lookup is a normal outcome: the chapter
    is mapped without its book's fields. Only the expected failures are
    caught (throttling, HTTP and transport errors, cache errors and a
    corrupt cached row); anything else is a bug and propagates to the
    pipeline's guard.

    Args:
        doi: The parent book's DOI.
        service: Domain service providing the cache and CrossRef client.

    Returns:
        The parent work, or ``None`` when it could not be fetched.
    """
    try:
        cached = await service.cache.get_crossref(doi)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        parent = await service.crossref.get_by_doi(doi)
        if parent is not None:
            await service.cache.set_crossref(doi, parent)
        return parent  # type: ignore[no-any-return]
    except RateLimitedError:
        return None
    except (httpx.HTTPError, sqlite3.Error, ValueError):
        logger.debug("crossref_parent_fetch_failed parent_doi=%s", doi, exc_info=True)
        return None


class CrossRefChapterEnricher:
    """Adds ``chapter_info`` to papers whose CrossRef work is a book chapter.

    Runs after :class:`~scholar_mcp._enricher_crossref.CrossRefEnricher` and
    reads the ``crossref_metadata`` it stored, so a record that already holds
    that key gets chapter info too. The parent book is fetched once through
    ``relation.is-part-of`` and cached like any CrossRef work.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (1 = after the CrossRef enricher).
        tags: Labels used to filter enricher selection.
    """

    name: str = "crossref_chapter"
    phase: int = 1
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True for a CrossRef book chapter without ``chapter_info``.

        Args:
            record: The paper record dict to inspect.

        Returns:
            ``True`` when ``crossref_metadata`` is a ``book-chapter`` work and
            the record has no ``chapter_info`` yet.
        """
        if record.get("chapter_info"):
            return False
        work = record.get("crossref_metadata")
        return isinstance(work, dict) and work.get("type") == "book-chapter"

    async def enrich(self, record: dict[str, Any], service: Any) -> None:
        """Set ``record["chapter_info"]`` from the chapter and its parent book.

        Args:
            record: The paper record dict to enrich in place.
            service: Domain service providing the cache and CrossRef client.
        """
        chapter: dict[str, Any] = record["crossref_metadata"]
        book_doi = parent_doi(chapter)
        parent = await _fetch_parent(book_doi, service) if book_doi else None
        if book_doi and parent is None:
            logger.debug(
                "crossref_chapter_without_parent doi=%s parent_doi=%s",
                chapter.get("DOI"),
                book_doi,
            )
        record["chapter_info"] = chapter_info_from_crossref(chapter, parent)
        logger.debug(
            "crossref_chapter_mapped doi=%s parent_doi=%s has_parent=%s",
            chapter.get("DOI"),
            book_doi,
            parent is not None,
        )

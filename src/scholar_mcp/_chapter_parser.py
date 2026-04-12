"""Chapter citation string parser.

Extracts chapter-level hints (chapter number, page range, parent book
title, ISBN) from free-form academic citation strings using heuristic
regex patterns.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Chapter number: "Chapter 3", "Ch. 12", "Chap. 5" (case-insensitive)
_RE_CHAPTER = re.compile(
    r"\b(?:chapter|chap\.|ch\.)\s+(\d+)\b",
    re.IGNORECASE,
)

# Page range: "pp. 45-67", "p. 123", "pages 100-150"
# Dashes: hyphen (-), en-dash (U+2013), em-dash (U+2014)
_DASH = r"[-\u2013\u2014]"
_RE_PAGES = re.compile(
    r"\b(?:pp?\.|pages?)\s+(\d+)(?:\s*" + _DASH + r"\s*(\d+))?",
    re.IGNORECASE,
)

# Parent book title: "In: {title}" up to comma+year or end of string
_RE_PARENT = re.compile(
    r"\bIn:\s+(.+?)(?=,\s*\d{4}|$)",
    re.IGNORECASE,
)

# ISBN-13: starts with 97[89], 13 digits, optional hyphens/spaces between groups
_RE_ISBN13 = re.compile(
    r"\b97[89](?:[-\s]?\d){10}\b",
)

# ISBN-10: 10 chars where first 9 are digits and last is digit or X,
# with optional hyphens/spaces between groups.
# Negative lookahead prevents matching the tail of an ISBN-13.
_RE_ISBN10 = re.compile(
    r"(?<!\d)(?!97[89])\d(?:[-\s]?\d){8}[-\s]?[\dXx](?!\d)",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _clean_isbn(raw: str) -> str:
    """Strip hyphens and spaces from an ISBN string.

    Args:
        raw: Raw ISBN string possibly containing hyphens or spaces.

    Returns:
        ISBN digits (and optional trailing X) with no separators.
    """
    return re.sub(r"[-\s]", "", raw).upper()


@dataclass
class ChapterHint:
    """Structured hints extracted from a chapter citation string.

    All fields default to ``None`` when not found in the citation.

    Attributes:
        chapter_number: Numeric chapter identifier when present.
        page_start: First page of the cited chapter or passage.
        page_end: Last page of the cited chapter or passage, or ``None``
            when only a single page was given.
        parent_title: Title of the containing book extracted from an
            ``In: {title}`` clause.
        isbn: Cleaned ISBN (hyphens/spaces removed) of the containing
            work, or ``None`` when not found.
    """

    chapter_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    parent_title: str | None = None
    isbn: str | None = None

    @property
    def has_chapter_info(self) -> bool:
        """Return True if any primary chapter discriminator is present.

        Returns:
            ``True`` when at least one of *chapter_number*, *page_start*,
            or *isbn* is not ``None``; ``False`` otherwise.
        """
        return any(
            v is not None for v in (self.chapter_number, self.page_start, self.isbn)
        )


def parse_chapter_hint(citation: str) -> ChapterHint:
    """Extract chapter-level hints from a free-form citation string.

    Uses heuristic regex patterns to detect chapter numbers, page
    ranges, parent book titles, and ISBNs embedded in academic
    citation text.  Returns a :class:`ChapterHint` with any matched
    fields populated; unmatched fields remain ``None``.

    Args:
        citation: Raw citation string, e.g.
            ``"Goodfellow et al., Deep Learning, Ch. 3, pp. 45-67,
            ISBN 978-0-262-03561-3"``.

    Returns:
        :class:`ChapterHint` populated with any values found.
    """
    hint = ChapterHint()

    # Chapter number
    m = _RE_CHAPTER.search(citation)
    if m:
        hint.chapter_number = int(m.group(1))
        logger.debug("parse_chapter_hint chapter_number=%s", hint.chapter_number)

    # Page range
    m = _RE_PAGES.search(citation)
    if m:
        hint.page_start = int(m.group(1))
        hint.page_end = int(m.group(2)) if m.group(2) else None
        logger.debug(
            "parse_chapter_hint page_start=%s page_end=%s",
            hint.page_start,
            hint.page_end,
        )

    # Parent book title
    m = _RE_PARENT.search(citation)
    if m:
        hint.parent_title = m.group(1).strip()
        logger.debug("parse_chapter_hint parent_title=%s", hint.parent_title)

    # ISBN — prefer ISBN-13 over ISBN-10
    m13 = _RE_ISBN13.search(citation)
    if m13:
        hint.isbn = _clean_isbn(m13.group())
        logger.debug("parse_chapter_hint isbn=%s (isbn13)", hint.isbn)
    else:
        m10 = _RE_ISBN10.search(citation)
        if m10:
            hint.isbn = _clean_isbn(m10.group())
            logger.debug("parse_chapter_hint isbn=%s (isbn10)", hint.isbn)

    return hint


def hint_to_dict(hint: ChapterHint) -> dict[str, Any]:
    """Convert a ChapterHint to a chapter_info dict for JSON output.

    Args:
        hint: Parsed chapter hint.

    Returns:
        Dict with populated fields and ``citation_source`` set to ``"parsed"``.
    """
    info: dict[str, Any] = {"citation_source": "parsed"}
    if hint.chapter_number is not None:
        info["chapter_number"] = hint.chapter_number
    if hint.page_start is not None:
        info["page_start"] = hint.page_start
    if hint.page_end is not None:
        info["page_end"] = hint.page_end
    if hint.parent_title is not None:
        info["chapter_title"] = hint.parent_title
    return info

"""The book a cited chapter sits in (#64).

A parsed ``chapter_info`` names a part of a book when it has a chapter
number, a page range or an ``In:`` clause. With a valid ISBN as well, that
ISBN is the containing book's, and the book found for it is recorded as
``chapter_info["parent_book"]``. The reasons are in
``docs/design/patent-npl-resolution.md``, "The book a chapter sits in".
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ._cache import checked_isbn13

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from ._record_types import BookRecord

    # Looks a book up by ISBN; None when no record is found.
    BookResolver = Callable[[str], Awaitable[BookRecord | None]]

logger = logging.getLogger(__name__)

# Keys that make a parsed citation a part of a book rather than the book.
_PART_KEYS = ("chapter_number", "page_start", "parent_title")


def parent_book_isbn(chapter_info: Mapping[str, Any] | None) -> str | None:
    """Return the ISBN-13 of the book a cited part sits in, if there is one.

    An ISBN alone names the whole book (a cited book, or a book's own DOI),
    which is no parent of itself, so a chapter number, page range or
    ``In:`` title must be present too.

    Args:
        chapter_info: A parsed ``chapter_info`` dict, or ``None``.

    Returns:
        The validated ISBN-13, or ``None``.
    """
    if not chapter_info or not any(k in chapter_info for k in _PART_KEYS):
        return None
    return checked_isbn13(chapter_info.get("isbn") or "")


async def attach_parent_book(
    chapter_info: dict[str, Any], resolve_book: BookResolver
) -> None:
    """Look up the containing book and record it as ``parent_book``.

    Best-effort: a book that is not found, or a lookup that fails, leaves
    ``chapter_info`` as it was, with its ``isbn`` for the caller to use.

    Args:
        chapter_info: A parsed ``chapter_info`` dict, changed in place.
        resolve_book: ISBN lookup.
    """
    isbn = parent_book_isbn(chapter_info)
    if isbn is None:
        return
    try:
        book = await resolve_book(isbn)
    except Exception:
        logger.debug("chapter_parent_book_failed isbn=%s", isbn, exc_info=True)
        return
    if book is not None:
        chapter_info["parent_book"] = book

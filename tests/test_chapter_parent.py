"""The book a cited chapter sits in (#64)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from scholar_mcp._chapter_parent import attach_parent_book, parent_book_isbn

_BOOK: dict[str, Any] = {"title": "Deep Learning", "isbn_13": "9780262035613"}


@pytest.mark.parametrize(
    ("chapter_info", "expected"),
    [
        # A part of a book: chapter, page range or "In:" clause, plus an ISBN.
        ({"chapter_number": 5, "isbn": "9780262035613"}, "9780262035613"),
        ({"page_start": 1, "page_end": 44, "isbn": "9780262035613"}, "9780262035613"),
        ({"parent_title": "Deep Learning", "isbn": "0-7803-4455-3"}, "9780780344556"),
        # An ISBN alone names the whole book (a cited book, a book DOI).
        ({"isbn": "9780262035613"}, None),
        # No ISBN, or one whose check digit fails: nothing to look up.
        ({"chapter_number": 5}, None),
        ({"chapter_number": 5, "isbn": "9780262035610"}, None),
        (None, None),
    ],
    ids=[
        "chapter",
        "pages",
        "in-clause-isbn10",
        "isbn-only",
        "no-isbn",
        "bad-check-digit",
        "no-chapter-info",
    ],
)
def test_parent_book_isbn(
    chapter_info: dict[str, Any] | None, expected: str | None
) -> None:
    assert parent_book_isbn(chapter_info) == expected


async def test_found_book_becomes_the_parent_book() -> None:
    info: dict[str, Any] = {"chapter_number": 5, "isbn": "9780262035613"}
    resolve = AsyncMock(return_value=_BOOK)

    await attach_parent_book(info, resolve)

    assert info["parent_book"] == _BOOK
    resolve.assert_awaited_once_with("9780262035613")


async def test_whole_book_is_not_looked_up() -> None:
    info: dict[str, Any] = {"isbn": "9780262035613"}
    resolve = AsyncMock(return_value=_BOOK)

    await attach_parent_book(info, resolve)

    assert "parent_book" not in info
    resolve.assert_not_awaited()


async def test_unknown_book_leaves_no_parent_book() -> None:
    info: dict[str, Any] = {"page_start": 3, "isbn": "9780262035613"}

    await attach_parent_book(info, AsyncMock(return_value=None))

    assert "parent_book" not in info
    assert info["isbn"] == "9780262035613"


async def test_failing_lookup_leaves_no_parent_book(
    caplog: pytest.LogCaptureFixture,
) -> None:
    info: dict[str, Any] = {"page_start": 3, "isbn": "9780262035613"}
    resolve = AsyncMock(side_effect=httpx.ConnectError("down"))

    with caplog.at_level(logging.DEBUG):
        await attach_parent_book(info, resolve)

    assert "parent_book" not in info
    assert any(
        r.getMessage() == "chapter_parent_book_failed isbn=9780262035613"
        for r in caplog.records
    )

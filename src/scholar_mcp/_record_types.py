"""Typed record definitions for Scholar MCP."""

from __future__ import annotations

from typing import TypedDict


class BookRecord(TypedDict, total=False):
    """Typed representation of a normalized book record.

    All fields use ``total=False`` because records are JSON-serialized
    and may have absent fields from cache deserialization or partial
    API responses.
    """

    title: str
    authors: list[str]
    publisher: str | None
    year: int | None
    edition: str | None
    isbn_10: str | None
    isbn_13: str | None
    openlibrary_work_id: str | None
    openlibrary_edition_id: str | None
    cover_url: str | None
    google_books_url: str | None
    subjects: list[str]
    page_count: int | None
    description: str | None

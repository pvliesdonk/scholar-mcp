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
    worldcat_url: str | None
    snippet: str | None
    cover_path: str | None


class BookChapterRecord(TypedDict, total=False):
    """Chapter-level metadata within a book.

    Used when citation strings reference specific chapters or page
    ranges. ``citation_source`` indicates whether data came from
    CrossRef (structured) or regex parsing (heuristic).
    """

    chapter_title: str
    chapter_number: int
    page_start: int
    page_end: int
    parent_book: BookRecord
    citation_source: str  # "crossref" | "parsed"


class StandardRecord(TypedDict, total=False):
    """Typed representation of a normalized standards record.

    All fields use ``total=False`` because records are JSON-serialised
    and may have absent fields from partial API responses or cache.
    """

    identifier: str  # canonical: "NIST SP 800-53 Rev. 5", "RFC 9000"
    aliases: list[str]  # alt forms seen in citations
    title: str
    body: str  # "NIST" | "IETF" | "W3C" | "ETSI"
    number: str  # "800-53", "9000", "2.1"
    revision: str | None  # "Rev. 5", "2022", "3rd edition"
    status: str  # "published" | "withdrawn" | "superseded" | "draft"
    published_date: str | None
    withdrawn_date: str | None
    superseded_by: str | None
    supersedes: list[str]
    scope: str | None  # abstract / scope statement
    committee: str | None
    url: str  # canonical catalogue URL
    full_text_url: str | None  # direct PDF/HTML link if freely available
    full_text_available: bool  # True for all Tier 1 sources
    price: str | None  # None for Tier 1; populated for Tier 2
    related: list[str]  # related standard identifiers

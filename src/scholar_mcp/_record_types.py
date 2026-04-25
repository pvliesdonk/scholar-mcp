"""Typed record definitions for Scholar MCP."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class S2Author(TypedDict, total=False):
    """Author sub-record as returned by Semantic Scholar.

    Fields are optional because S2 responses vary by requested
    ``fields`` and by corpus coverage.
    """

    authorId: str | None
    name: str


class S2ExternalIds(TypedDict, total=False):
    """External identifier map returned by Semantic Scholar.

    Keys are the identifier schemes S2 recognises. All values are
    strings (or absent).
    """

    DOI: str
    ArXiv: str
    ISBN: str
    PubMed: str
    PubMedCentral: str
    MAG: str
    ACL: str
    DBLP: str
    CorpusId: int


class S2Tldr(TypedDict, total=False):
    """TLDR summary structure returned by Semantic Scholar."""

    model: str
    text: str


class S2OpenAccessPdf(TypedDict, total=False):
    """Open-access PDF descriptor returned by Semantic Scholar."""

    url: str
    status: str
    license: str | None


class PaperRecord(TypedDict, total=False):
    """Typed representation of a Semantic Scholar paper record.

    Fields mirror the camelCase names returned by the S2 Graph API and
    align with :data:`scholar_mcp._s2_client.FIELD_SETS`. ``total=False``
    because any subset of fields may be present depending on the
    requested field set and what the S2 corpus has indexed, and records
    round-trip through JSON cache serialisation.

    The final two fields (``book_metadata``, ``crossref_metadata``) are
    attached in-place by enrichers rather than returned by S2 itself.
    """

    paperId: str
    title: str
    year: int | None
    venue: str | None
    citationCount: int
    referenceCount: int
    abstract: str | None
    authors: list[S2Author]
    externalIds: S2ExternalIds | None
    fieldsOfStudy: list[str] | None
    tldr: S2Tldr | None
    openAccessPdf: S2OpenAccessPdf | None

    # Enrichment-added fields (populated by enrichers, not by S2).
    book_metadata: dict[str, Any]
    crossref_metadata: dict[str, Any]


class PatentRecord(TypedDict, total=False):
    """Typed representation of an EPO OPS patent biblio record.

    Fields mirror the dict returned by
    :func:`scholar_mcp._epo_xml.parse_biblio_xml`. ``total=False``
    because records round-trip through JSON cache serialisation and
    partial EPO responses may omit fields.
    """

    title: str
    abstract: str
    applicants: list[str]
    inventors: list[str]
    publication_number: str
    publication_date: str
    filing_date: str
    priority_date: str
    family_id: str
    classifications: list[str]
    url: str


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
    parent_title: str
    parent_book: BookRecord
    isbn: str
    citation_source: Literal["crossref", "parsed"]


class StandardRecord(TypedDict, total=False):
    """Typed representation of a normalized standards record.

    All fields use ``total=False`` because records are JSON-serialised
    and may have absent fields from partial API responses or cache.
    """

    identifier: str  # canonical: "NIST SP 800-53 Rev. 5", "RFC 9000"
    aliases: list[str]  # alt forms seen in citations
    title: str
    body: str  # "NIST" | "IETF" | "W3C" | "ETSI" | "ISO" | "IEC" | "ISO/IEC"
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

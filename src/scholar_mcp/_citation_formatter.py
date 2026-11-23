"""Citation formatting for BibTeX, CSL-JSON, and RIS."""

from __future__ import annotations

import json
import unicodedata
from typing import TYPE_CHECKING, Any, cast

from ._bibtex_escape import escape_bibtex
from ._chapter_citation import (
    CHAPTER_ENTRY_TYPE,
    bibtex_chapter_fields,
    chapter_of,
    csl_chapter_fields,
    editors_as_paper,
    ris_chapter_lines,
)
from ._citation_names import parse_author_name
from ._patent_citation import patent_bibtex_entry, patent_csl_entry, patent_ris_record

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TypeAlias

    from ._record_types import PaperRecord, PatentRecord

    CitationRecord: TypeAlias = PaperRecord | PatentRecord

# Conference keywords for entry type inference.
_CONFERENCE_KEYWORDS = ("conference", "proceedings", "workshop", "symposium")

# S2 reports a conference paper in ``publicationTypes``, which is authoritative
# where the venue name is not: "Neural Information Processing Systems" and
# "Computer Vision and Pattern Recognition" carry none of the keywords above.
_CONFERENCE_TYPE = "Conference"
# Entry types whose container is not the S2 venue.
_NO_VENUE_TYPES = frozenset({"book", CHAPTER_ENTRY_TYPE})
# What a citation error says when it names no reason.
_UNKNOWN_ERROR = "unknown error"


def _ascii_fold(text: str) -> str:
    """Fold Unicode to ASCII for BibTeX keys."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def is_patent_record(record: CitationRecord) -> bool:
    """Say whether a citation record is a patent rather than a paper.

    Args:
        record: A paper or patent record.

    Returns:
        ``True`` when the record carries ``publication_number``.
    """
    return "publication_number" in record


def generate_bibtex_key(paper: PaperRecord, seen_keys: set[str]) -> str:
    """Generate a BibTeX citation key in authorYear style.

    Args:
        paper: Paper metadata dict with ``authors`` and ``year``.
        seen_keys: Set of already-used keys (mutated to include the new key).

    Returns:
        Unique citation key string.
    """
    authors = paper.get("authors") or []
    if authors:
        parsed = parse_author_name(authors[0].get("name", ""))
        last = _ascii_fold(parsed.last) if parsed.last else "anon"
    else:
        last = "anon"

    year = paper.get("year")
    base = f"{last}{year}" if year is not None else last

    if base not in seen_keys:
        seen_keys.add(base)
        return base

    for suffix_ord in range(ord("a"), ord("z") + 1):
        candidate = f"{base}{chr(suffix_ord)}"
        if candidate not in seen_keys:
            seen_keys.add(candidate)
            return candidate

    # Extremely unlikely fallback.
    i = len(seen_keys)
    while True:
        candidate = f"{base}_{i}"
        if candidate not in seen_keys:
            seen_keys.add(candidate)
            return candidate
        i += 1


def _is_conference_paper(paper: PaperRecord) -> bool:
    """Say whether S2's publication type or the venue name marks a conference.

    Args:
        paper: Paper metadata dict.

    Returns:
        ``True`` when ``publicationTypes`` holds ``Conference`` or the venue
        name carries one of :data:`_CONFERENCE_KEYWORDS`.
    """
    venue = (paper.get("venue") or "").lower()
    publication_types = paper.get("publicationTypes") or []
    return _CONFERENCE_TYPE in publication_types or any(
        kw in venue for kw in _CONFERENCE_KEYWORDS
    )


def infer_entry_type(paper: PaperRecord) -> str:
    """Infer BibTeX entry type from paper metadata.

    A paper whose CrossRef ``chapter_info`` names its book is a chapter
    (``incollection``) unless the conference test below marks it as a
    conference paper: Springer deposits proceedings papers (LNCS) as
    CrossRef book chapters, and those that test catches stay
    ``inproceedings``. A chapter outranks ``book_metadata``.

    A paper counts as a conference paper when S2 says so in
    ``publicationTypes``, or, for a record without that field, when its venue
    name carries one of :data:`_CONFERENCE_KEYWORDS`. Both are checked ahead
    of the arXiv fallback, so a conference paper that also has a preprint is
    not reported as ``misc``.

    Args:
        paper: Paper metadata dict.

    Returns:
        One of ``"incollection"``, ``"book"``, ``"article"``,
        ``"inproceedings"``, or ``"misc"``.
    """
    conference = _is_conference_paper(paper)
    if chapter_of(paper) is not None and not conference:
        return CHAPTER_ENTRY_TYPE
    book_meta = paper.get("book_metadata")
    if book_meta and (book_meta.get("isbn_13") or book_meta.get("publisher")):
        return "book"
    if conference:
        return "inproceedings"
    external_ids = paper.get("externalIds") or {}
    if external_ids.get("ArXiv") and not paper.get("venue"):
        return "misc"
    return "article"


def _format_bibtex_author(paper: PaperRecord) -> str:
    """Format author list for BibTeX using 'von Last, First' form.

    Names with a nobiliary particle use 'von Last, First'
    (e.g. 'van Houten, Jan'). Names are joined by ' and '.

    Args:
        paper: Paper metadata dict with an ``authors`` list.

    Returns:
        BibTeX author string with names joined by `` and ``.
    """
    authors = paper.get("authors") or []
    parts: list[str] = []
    for author in authors:
        parsed = parse_author_name(author.get("name", ""))
        # BibTeX name format: [von] Last, [Suffix,] First
        surname = f"{parsed.prefix} {parsed.last}" if parsed.prefix else parsed.last
        name_parts = [surname]
        if parsed.suffix:
            name_parts.append(parsed.suffix)
        if parsed.first:
            name_parts.append(parsed.first)
        if surname:
            parts.append(", ".join(name_parts))
    return " and ".join(parts)


def _paper_url(paper: PaperRecord) -> str | None:
    """Extract best URL from paper metadata.

    Args:
        paper: Paper metadata dict.

    Returns:
        Open-access PDF URL, DOI URL, or ``None`` if unavailable.
    """
    oa = paper.get("openAccessPdf")
    if oa and isinstance(oa, dict) and oa.get("url"):
        return str(oa["url"])
    doi = (paper.get("externalIds") or {}).get("DOI")
    if doi:
        return f"https://doi.org/{doi}"
    return None


def _book_authors_as_paper(paper: PaperRecord) -> PaperRecord:
    """Wrap a book's ``book_metadata`` authors as an S2-style author list.

    The S2 author formatters (:func:`_format_bibtex_author`,
    :func:`_csl_author`, :func:`_ris_author_line`) read
    ``{"authors": [{"name": ...}]}``, so this lets each format a book's
    authors exactly as it formats a paper's.

    Args:
        paper: Paper metadata dict with optional ``book_metadata``.

    Returns:
        A record holding only ``authors``, one entry per book author.
    """
    bm = paper.get("book_metadata") or {}
    return {"authors": [{"name": a} for a in bm.get("authors") or []]}


def format_bibtex(
    papers: Sequence[CitationRecord], errors: list[dict[str, Any]]
) -> str:
    """Format papers and patents as BibTeX entries.

    Papers become ``@article``, ``@inproceedings``, ``@incollection``,
    ``@book`` or ``@misc`` entries; patents become biblatex ``@patent``
    entries. Entries keep the order of *papers*, and all share one
    citation-key namespace.

    Args:
        papers: Paper and patent records, in output order.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        BibTeX string with all entries and error comments.
    """
    lines: list[str] = []

    for error in errors:
        ident = error.get("identifier", "unknown")
        reason = error.get("reason", _UNKNOWN_ERROR)
        lines.append(f"% Could not resolve: {ident} ({reason})")

    if errors and papers:
        lines.append("")

    seen_keys: set[str] = set()
    for record in papers:
        if is_patent_record(record):
            lines.append(patent_bibtex_entry(cast("PatentRecord", record), seen_keys))
        else:
            lines.append(_paper_bibtex_entry(cast("PaperRecord", record), seen_keys))

    return "\n\n".join(lines)


def _bibtex_author_field(paper: PaperRecord, entry_type: str) -> list[str]:
    """Build the BibTeX ``author`` field, if the paper names any author.

    S2 authors are preferred; a book without them falls back to its
    ``book_metadata`` authors, formatted the same way.

    Args:
        paper: Paper metadata dict.
        entry_type: BibTeX entry type from :func:`infer_entry_type`.

    Returns:
        A one-element list with the ``author`` field, or an empty list.
    """
    author_str = _format_bibtex_author(paper)
    if not author_str and entry_type == "book":
        author_str = _format_bibtex_author(_book_authors_as_paper(paper))
    return [f"  author = {{{author_str}}}"] if author_str else []


def _bibtex_venue_field(paper: PaperRecord, entry_type: str) -> list[str]:
    """Build the BibTeX venue field: ``booktitle`` or ``journal``.

    Args:
        paper: Paper metadata dict.
        entry_type: BibTeX entry type from :func:`infer_entry_type`.

    Returns:
        A one-element list with the venue field, or an empty list for a book,
        a chapter (its book comes from ``chapter_info``) or a paper without a
        venue.
    """
    venue = paper.get("venue")
    if not venue or entry_type in _NO_VENUE_TYPES:
        return []
    name = "booktitle" if entry_type == "inproceedings" else "journal"
    return [f"  {name} = {{{escape_bibtex(venue)}}}"]


def _bibtex_book_fields(paper: PaperRecord) -> list[str]:
    """Build the BibTeX ``publisher``, ``edition`` and ``isbn`` fields.

    Args:
        paper: Paper metadata dict with optional ``book_metadata``.

    Returns:
        The book fields present in ``book_metadata``, in that order.
    """
    bm = paper.get("book_metadata") or {}
    fields: list[str] = []
    publisher = bm.get("publisher")
    if publisher:
        fields.append(f"  publisher = {{{escape_bibtex(publisher)}}}")
    edition = bm.get("edition")
    if edition:
        fields.append(f"  edition = {{{escape_bibtex(edition)}}}")
    isbn = bm.get("isbn_13")
    if isbn:
        fields.append(f"  isbn = {{{isbn}}}")
    return fields


def _bibtex_link_fields(paper: PaperRecord) -> list[str]:
    """Build the BibTeX ``doi``, ``url``, ``abstract`` and arXiv fields.

    Args:
        paper: Paper metadata dict.

    Returns:
        The fields present on the paper, in that order; an arXiv id adds
        both ``eprint`` and ``archivePrefix``.
    """
    fields: list[str] = []
    external_ids = paper.get("externalIds") or {}
    doi = external_ids.get("DOI")
    if doi:
        fields.append(f"  doi = {{{escape_bibtex(doi)}}}")
    url = _paper_url(paper)
    if url:
        fields.append(f"  url = {{{escape_bibtex(url)}}}")
    abstract = paper.get("abstract")
    if abstract:
        fields.append(f"  abstract = {{{escape_bibtex(abstract)}}}")
    arxiv = external_ids.get("ArXiv")
    if arxiv:
        fields.append(f"  eprint = {{{arxiv}}}")
        fields.append("  archivePrefix = {arXiv}")
    return fields


def _paper_bibtex_entry(paper: PaperRecord, seen_keys: set[str]) -> str:
    """Format one paper as a BibTeX entry.

    Args:
        paper: Paper metadata dict.
        seen_keys: Citation keys already used (mutated to include this one).

    Returns:
        The ``@type{key, ...}`` entry.
    """
    entry_type = infer_entry_type(paper)
    key = generate_bibtex_key(paper, seen_keys)

    fields = _bibtex_author_field(paper, entry_type)
    title = paper.get("title")
    if title:
        fields.append(f"  title = {{{{{escape_bibtex(title)}}}}}")
    year = paper.get("year")
    if year is not None:
        fields.append(f"  year = {{{year}}}")
    fields.extend(_bibtex_venue_field(paper, entry_type))
    if entry_type == "book":
        fields.extend(_bibtex_book_fields(paper))
    chapter = chapter_of(paper) if entry_type == CHAPTER_ENTRY_TYPE else None
    if chapter is not None:
        editor = _format_bibtex_author(editors_as_paper(chapter))
        fields.extend(bibtex_chapter_fields(chapter, editor))
    fields.extend(_bibtex_link_fields(paper))

    entry = f"@{entry_type}{{{key},\n"
    if fields:
        entry += ",\n".join(fields) + ",\n"
    entry += "}"
    return entry


_CSL_TYPE_MAP: dict[str, str] = {
    "article": "article-journal",
    "inproceedings": "paper-conference",
    "misc": "article",
    "book": "book",
    CHAPTER_ENTRY_TYPE: "chapter",
}


def _csl_author(paper: PaperRecord) -> list[dict[str, str]]:
    """Format authors for CSL-JSON.

    Args:
        paper: Paper metadata dict with an ``authors`` list.

    Returns:
        List of CSL author dicts with ``family``, ``given``,
        ``non-dropping-particle``, and ``suffix`` keys as applicable.
    """
    authors = paper.get("authors") or []
    result: list[dict[str, str]] = []
    for author in authors:
        parsed = parse_author_name(author.get("name", ""))
        entry: dict[str, str] = {}
        if parsed.last:
            entry["family"] = parsed.last
        if parsed.first:
            entry["given"] = parsed.first
        if parsed.prefix:
            entry["non-dropping-particle"] = parsed.prefix
        if parsed.suffix:
            entry["suffix"] = parsed.suffix
        if entry:
            result.append(entry)
    return result


def format_csl_json(
    papers: Sequence[CitationRecord], errors: list[dict[str, Any]]
) -> str:
    """Format papers and patents as CSL-JSON.

    Patents become CSL ``patent`` items. Items keep the order of *papers*,
    and all share one citation-key namespace.

    Args:
        papers: Paper and patent records, in output order.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        JSON string with ``citations`` array and ``errors`` array.
    """
    seen_keys: set[str] = set()
    citations: list[dict[str, Any]] = []

    for record in papers:
        if is_patent_record(record):
            citations.append(patent_csl_entry(cast("PatentRecord", record), seen_keys))
        else:
            citations.append(_paper_csl_entry(cast("PaperRecord", record), seen_keys))

    error_list = [
        {
            "identifier": e.get("identifier", "unknown"),
            "reason": e.get("reason", _UNKNOWN_ERROR),
        }
        for e in errors
    ]

    return json.dumps({"citations": citations, "errors": error_list})


def _csl_link_fields(paper: PaperRecord) -> dict[str, Any]:
    """Build the CSL ``DOI``, ``URL`` and ``abstract`` fields.

    Args:
        paper: Paper metadata dict.

    Returns:
        The fields present on the paper, in that order.
    """
    fields: dict[str, Any] = {}
    doi = (paper.get("externalIds") or {}).get("DOI")
    if doi:
        fields["DOI"] = doi
    url = _paper_url(paper)
    if url:
        fields["URL"] = url
    abstract = paper.get("abstract")
    if abstract:
        fields["abstract"] = abstract
    return fields


def _csl_book_fields(paper: PaperRecord) -> dict[str, Any]:
    """Build the CSL ``publisher`` and ``ISBN`` fields from ``book_metadata``.

    Args:
        paper: Paper metadata dict with optional ``book_metadata``.

    Returns:
        The book fields present, in that order.
    """
    bm = paper.get("book_metadata") or {}
    fields: dict[str, Any] = {}
    if bm.get("publisher"):
        fields["publisher"] = bm["publisher"]
    if bm.get("isbn_13"):
        fields["ISBN"] = bm["isbn_13"]
    return fields


def _paper_csl_entry(paper: PaperRecord, seen_keys: set[str]) -> dict[str, Any]:
    """Format one paper as a CSL-JSON item.

    Args:
        paper: Paper metadata dict.
        seen_keys: Citation keys already used (mutated to include this one).

    Returns:
        The CSL item, its keys in the order CSL output has always used.
    """
    entry_type = infer_entry_type(paper)
    entry: dict[str, Any] = {
        "id": generate_bibtex_key(paper, seen_keys),
        "type": _CSL_TYPE_MAP.get(entry_type, "article-journal"),
    }
    title = paper.get("title")
    if title:
        entry["title"] = title

    csl_authors = _csl_author(paper)
    if not csl_authors and entry_type == "book":
        csl_authors = _csl_author(_book_authors_as_paper(paper))
    if csl_authors:
        entry["author"] = csl_authors

    year = paper.get("year")
    if year is not None:
        entry["issued"] = {"date-parts": [[year]]}
    venue = paper.get("venue")
    if venue and entry_type not in _NO_VENUE_TYPES:
        entry["container-title"] = venue
    entry.update(_csl_link_fields(paper))
    if entry_type == "book":
        entry.update(_csl_book_fields(paper))
    chapter = chapter_of(paper) if entry_type == CHAPTER_ENTRY_TYPE else None
    if chapter is not None:
        editors = _csl_author(editors_as_paper(chapter))
        entry.update(csl_chapter_fields(chapter, editors))
    return entry


_RIS_TYPE_MAP: dict[str, str] = {
    "article": "JOUR",
    "inproceedings": "CONF",
    "misc": "GEN",
    "book": "BOOK",
    CHAPTER_ENTRY_TYPE: "CHAP",
}


def _ris_author_line(paper: PaperRecord, tag: str = "AU") -> list[str]:
    """Format one name tag per author for RIS, ``AU`` unless *tag* says.

    Args:
        paper: Paper metadata dict with an ``authors`` list.
        tag: The RIS tag to write, ``A2`` for a chapter's book editors.

    Returns:
        List of ``<tag>  - Last, First`` tag strings.
    """
    authors = paper.get("authors") or []
    lines: list[str] = []
    for author in authors:
        parsed = parse_author_name(author.get("name", ""))
        name = f"{parsed.prefix} {parsed.last}" if parsed.prefix else parsed.last
        if parsed.first:
            name = f"{name}, {parsed.first}"
        if parsed.suffix:
            name = f"{name}, {parsed.suffix}"
        if name:
            lines.append(f"{tag}  - {name}")
    return lines


def format_ris(papers: Sequence[CitationRecord], errors: list[dict[str, Any]]) -> str:
    """Format papers and patents as RIS records.

    Patents become ``PAT`` records. Records keep the order of *papers*.

    Args:
        papers: Paper and patent records, in output order.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        RIS-formatted string with all records and error comments.
    """
    blocks: list[str] = []

    for error in errors:
        ident = error.get("identifier", "unknown")
        reason = error.get("reason", _UNKNOWN_ERROR)
        blocks.append(f"% Could not resolve: {ident} ({reason})")

    for record in papers:
        if is_patent_record(record):
            blocks.append(patent_ris_record(cast("PatentRecord", record)))
        else:
            blocks.append(_paper_ris_record(cast("PaperRecord", record)))

    return "\n\n".join(blocks)


def _ris_venue_line(paper: PaperRecord, entry_type: str) -> list[str]:
    """Build the RIS venue tag: ``BT`` for a conference, ``JO`` otherwise.

    Args:
        paper: Paper metadata dict.
        entry_type: BibTeX entry type from :func:`infer_entry_type`.

    Returns:
        A one-element list with the venue tag, or an empty list for a book,
        a chapter or a paper without a venue.
    """
    venue = paper.get("venue")
    if not venue or entry_type in _NO_VENUE_TYPES:
        return []
    tag = "BT" if entry_type == "inproceedings" else "JO"
    return [f"{tag}  - {venue}"]


def _ris_link_lines(paper: PaperRecord) -> list[str]:
    """Build the RIS ``DO``, ``UR`` and ``AB`` tags.

    Args:
        paper: Paper metadata dict.

    Returns:
        The tags present on the paper, in that order.
    """
    lines: list[str] = []
    doi = (paper.get("externalIds") or {}).get("DOI")
    if doi:
        lines.append(f"DO  - {doi}")
    url = _paper_url(paper)
    if url:
        lines.append(f"UR  - {url}")
    abstract = paper.get("abstract")
    if abstract:
        lines.append(f"AB  - {abstract}")
    return lines


def _ris_book_lines(paper: PaperRecord) -> list[str]:
    """Build the RIS ``PB`` and ``SN`` tags from ``book_metadata``.

    Args:
        paper: Paper metadata dict with optional ``book_metadata``.

    Returns:
        The book tags present, in that order.
    """
    bm = paper.get("book_metadata") or {}
    lines: list[str] = []
    if bm.get("publisher"):
        lines.append(f"PB  - {bm['publisher']}")
    if bm.get("isbn_13"):
        lines.append(f"SN  - {bm['isbn_13']}")
    return lines


def _paper_ris_record(paper: PaperRecord) -> str:
    """Format one paper as a RIS record.

    Args:
        paper: Paper metadata dict.

    Returns:
        The record, from its ``TY`` tag to its closing ``ER`` tag.
    """
    entry_type = infer_entry_type(paper)
    lines: list[str] = [f"TY  - {_RIS_TYPE_MAP.get(entry_type, 'GEN')}"]

    author_lines = _ris_author_line(paper)
    if not author_lines and entry_type == "book":
        author_lines = _ris_author_line(_book_authors_as_paper(paper))
    lines.extend(author_lines)

    title = paper.get("title")
    if title:
        lines.append(f"TI  - {title}")
    year = paper.get("year")
    if year is not None:
        lines.append(f"PY  - {year}///")
    lines.extend(_ris_venue_line(paper, entry_type))
    lines.extend(_ris_link_lines(paper))
    if entry_type == "book":
        lines.extend(_ris_book_lines(paper))
    chapter = chapter_of(paper) if entry_type == CHAPTER_ENTRY_TYPE else None
    if chapter is not None:
        editor_lines = _ris_author_line(editors_as_paper(chapter), tag="A2")
        lines.extend(ris_chapter_lines(chapter, editor_lines))
    lines.append("ER  -")
    return "\n".join(lines)

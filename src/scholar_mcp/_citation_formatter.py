"""Citation formatting for BibTeX, CSL-JSON, and RIS."""

from __future__ import annotations

import json
import unicodedata
from typing import TYPE_CHECKING, Any

from ._citation_names import parse_author_name

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._record_types import PaperRecord

# BibTeX special characters that must be escaped.
_BIBTEX_ESCAPES: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "$": r"\$",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Common Unicode → LaTeX replacements (combining diacritics approach).
_UNICODE_TO_LATEX: dict[str, str] = {
    "\u0300": "`",  # grave
    "\u0301": "'",  # acute
    "\u0302": "^",  # circumflex
    "\u0303": "~",  # tilde
    "\u0304": "=",  # macron
    "\u0308": '"',  # diaeresis / umlaut
    "\u030c": "v",  # caron
    "\u0327": "c",  # cedilla
    "\u0328": "k",  # ogonek
}

# Conference keywords for entry type inference.
_CONFERENCE_KEYWORDS = ("conference", "proceedings", "workshop", "symposium")


def escape_bibtex(text: str) -> str:
    """Escape special characters and convert Unicode to LaTeX commands.

    Args:
        text: Raw text string.

    Returns:
        BibTeX-safe string with special chars escaped and common
        Unicode accented characters converted to LaTeX commands.
    """
    nfd = unicodedata.normalize("NFD", text)
    result: list[str] = []
    i = 0
    while i < len(nfd):
        ch = nfd[i]
        if (
            i + 1 < len(nfd)
            and unicodedata.category(nfd[i + 1]) == "Mn"
            and nfd[i + 1] in _UNICODE_TO_LATEX
        ):
            accent = _UNICODE_TO_LATEX[nfd[i + 1]]
            base = _BIBTEX_ESCAPES.get(ch, ch)
            result.append(f"{{\\{accent}{base}}}")
            i += 2
        else:
            # Check if this is a base char followed by an unmapped
            # combining mark — normalise back to NFC to avoid orphaning.
            if (
                i + 1 < len(nfd)
                and unicodedata.category(nfd[i + 1]) == "Mn"
                and nfd[i + 1] not in _UNICODE_TO_LATEX
            ):
                composed = unicodedata.normalize("NFC", ch + nfd[i + 1])
                result.append(composed)
                i += 2
            else:
                result.append(_BIBTEX_ESCAPES.get(ch, ch))
                i += 1
    return "".join(result)


def _ascii_fold(text: str) -> str:
    """Fold Unicode to ASCII for BibTeX keys."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


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


def infer_entry_type(paper: PaperRecord) -> str:
    """Infer BibTeX entry type from paper metadata.

    Args:
        paper: Paper metadata dict.

    Returns:
        One of ``"book"``, ``"article"``, ``"inproceedings"``, or ``"misc"``.
    """
    book_meta = paper.get("book_metadata")
    if book_meta and (book_meta.get("isbn_13") or book_meta.get("publisher")):
        return "book"
    venue = (paper.get("venue") or "").lower()
    if any(kw in venue for kw in _CONFERENCE_KEYWORDS):
        return "inproceedings"
    external_ids = paper.get("externalIds") or {}
    if external_ids.get("ArXiv") and not venue:
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


def format_bibtex(papers: Sequence[PaperRecord], errors: list[dict[str, Any]]) -> str:
    """Format papers as BibTeX entries.

    Args:
        papers: List of paper metadata dicts.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        BibTeX string with all entries and error comments.
    """
    lines: list[str] = []

    for error in errors:
        ident = error.get("identifier", "unknown")
        reason = error.get("reason", "unknown error")
        lines.append(f"% Could not resolve: {ident} ({reason})")

    if errors and papers:
        lines.append("")

    seen_keys: set[str] = set()
    for paper in papers:
        entry_type = infer_entry_type(paper)
        key = generate_bibtex_key(paper, seen_keys)

        fields: list[str] = []

        # Author: prefer S2 authors, fall back to book_metadata authors.
        # Synthesise {"name": ...} entries so _format_bibtex_author applies
        # parse_author_name and produces the {Last, First} BibTeX convention.
        author_str = _format_bibtex_author(paper)
        if not author_str and entry_type == "book":
            bm = paper.get("book_metadata") or {}
            bm_authors = bm.get("authors") or []
            if bm_authors:
                author_str = _format_bibtex_author(
                    {"authors": [{"name": a} for a in bm_authors]}
                )
        if author_str:
            fields.append(f"  author = {{{author_str}}}")

        title = paper.get("title")
        if title:
            fields.append(f"  title = {{{{{escape_bibtex(title)}}}}}")

        year = paper.get("year")
        if year is not None:
            fields.append(f"  year = {{{year}}}")

        venue = paper.get("venue")
        if venue:
            if entry_type == "inproceedings":
                fields.append(f"  booktitle = {{{escape_bibtex(venue)}}}")
            elif entry_type != "book":
                fields.append(f"  journal = {{{escape_bibtex(venue)}}}")

        # Book-specific fields from book_metadata
        if entry_type == "book":
            bm = paper.get("book_metadata") or {}
            publisher = bm.get("publisher")
            if publisher:
                fields.append(f"  publisher = {{{escape_bibtex(publisher)}}}")
            edition = bm.get("edition")
            if edition:
                fields.append(f"  edition = {{{escape_bibtex(edition)}}}")
            isbn = bm.get("isbn_13")
            if isbn:
                fields.append(f"  isbn = {{{isbn}}}")

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

        entry = f"@{entry_type}{{{key},\n"
        if fields:
            entry += ",\n".join(fields) + ",\n"
        entry += "}"
        lines.append(entry)

    return "\n\n".join(lines)


_CSL_TYPE_MAP: dict[str, str] = {
    "article": "article-journal",
    "inproceedings": "paper-conference",
    "misc": "article",
    "book": "book",
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


def format_csl_json(papers: Sequence[PaperRecord], errors: list[dict[str, Any]]) -> str:
    """Format papers as CSL-JSON.

    Args:
        papers: List of paper metadata dicts.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        JSON string with ``citations`` array and ``errors`` array.
    """
    seen_keys: set[str] = set()
    citations: list[dict[str, Any]] = []

    for paper in papers:
        entry_type = infer_entry_type(paper)
        key = generate_bibtex_key(paper, seen_keys)

        entry: dict[str, Any] = {
            "id": key,
            "type": _CSL_TYPE_MAP.get(entry_type, "article-journal"),
        }

        title = paper.get("title")
        if title:
            entry["title"] = title

        csl_authors = _csl_author(paper)
        if not csl_authors and entry_type == "book":
            bm = paper.get("book_metadata") or {}
            for author_name in bm.get("authors") or []:
                parsed = parse_author_name(author_name)
                ae: dict[str, str] = {}
                if parsed.last:
                    ae["family"] = parsed.last
                if parsed.first:
                    ae["given"] = parsed.first
                if parsed.prefix:
                    ae["non-dropping-particle"] = parsed.prefix
                if parsed.suffix:
                    ae["suffix"] = parsed.suffix
                if ae:
                    csl_authors.append(ae)
        if csl_authors:
            entry["author"] = csl_authors

        year = paper.get("year")
        if year is not None:
            entry["issued"] = {"date-parts": [[year]]}

        venue = paper.get("venue")
        if venue and entry_type != "book":
            entry["container-title"] = venue

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        if doi:
            entry["DOI"] = doi

        url = _paper_url(paper)
        if url:
            entry["URL"] = url

        abstract = paper.get("abstract")
        if abstract:
            entry["abstract"] = abstract

        if entry_type == "book":
            bm = paper.get("book_metadata") or {}
            if bm.get("publisher"):
                entry["publisher"] = bm["publisher"]
            if bm.get("isbn_13"):
                entry["ISBN"] = bm["isbn_13"]

        citations.append(entry)

    error_list = [
        {
            "identifier": e.get("identifier", "unknown"),
            "reason": e.get("reason", "unknown error"),
        }
        for e in errors
    ]

    return json.dumps({"citations": citations, "errors": error_list})


_RIS_TYPE_MAP: dict[str, str] = {
    "article": "JOUR",
    "inproceedings": "CONF",
    "misc": "GEN",
    "book": "BOOK",
}


def _ris_author_line(paper: PaperRecord) -> list[str]:
    """Format one AU tag per author for RIS.

    Args:
        paper: Paper metadata dict with an ``authors`` list.

    Returns:
        List of ``AU  - Last, First`` tag strings.
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
            lines.append(f"AU  - {name}")
    return lines


def format_ris(papers: Sequence[PaperRecord], errors: list[dict[str, Any]]) -> str:
    """Format papers as RIS records.

    Args:
        papers: List of paper metadata dicts.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        RIS-formatted string with all records and error comments.
    """
    blocks: list[str] = []

    for error in errors:
        ident = error.get("identifier", "unknown")
        reason = error.get("reason", "unknown error")
        blocks.append(f"% Could not resolve: {ident} ({reason})")

    for paper in papers:
        entry_type = infer_entry_type(paper)
        ris_type = _RIS_TYPE_MAP.get(entry_type, "GEN")
        lines: list[str] = [f"TY  - {ris_type}"]

        author_lines = _ris_author_line(paper)
        if not author_lines and entry_type == "book":
            bm = paper.get("book_metadata") or {}
            for author_name in bm.get("authors") or []:
                parsed = parse_author_name(author_name)
                name = (
                    f"{parsed.prefix} {parsed.last}" if parsed.prefix else parsed.last
                )
                if parsed.first:
                    name = f"{name}, {parsed.first}"
                if parsed.suffix:
                    name = f"{name}, {parsed.suffix}"
                if name:
                    author_lines.append(f"AU  - {name}")
        lines.extend(author_lines)

        title = paper.get("title")
        if title:
            lines.append(f"TI  - {title}")

        year = paper.get("year")
        if year is not None:
            lines.append(f"PY  - {year}///")

        venue = paper.get("venue")
        if venue:
            if entry_type == "inproceedings":
                lines.append(f"BT  - {venue}")
            elif entry_type != "book":
                lines.append(f"JO  - {venue}")

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        if doi:
            lines.append(f"DO  - {doi}")

        url = _paper_url(paper)
        if url:
            lines.append(f"UR  - {url}")

        abstract = paper.get("abstract")
        if abstract:
            lines.append(f"AB  - {abstract}")

        if entry_type == "book":
            bm = paper.get("book_metadata") or {}
            if bm.get("publisher"):
                lines.append(f"PB  - {bm['publisher']}")
            if bm.get("isbn_13"):
                lines.append(f"SN  - {bm['isbn_13']}")

        lines.append("ER  -")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)

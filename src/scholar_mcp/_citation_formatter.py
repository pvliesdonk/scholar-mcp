"""Citation formatting for BibTeX, CSL-JSON, and RIS."""

from __future__ import annotations

import unicodedata
from typing import Any

from ._citation_names import parse_author_name

# BibTeX special characters that must be escaped.
_BIBTEX_ESCAPES: dict[str, str] = {
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


def generate_bibtex_key(paper: dict[str, Any], seen_keys: set[str]) -> str:
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

    candidate = f"{base}_{len(seen_keys)}"
    seen_keys.add(candidate)
    return candidate


def infer_entry_type(paper: dict[str, Any]) -> str:
    """Infer BibTeX entry type from paper metadata.

    Args:
        paper: Paper metadata dict.

    Returns:
        One of ``"article"``, ``"inproceedings"``, or ``"misc"``.
    """
    venue = (paper.get("venue") or "").lower()
    if any(kw in venue for kw in _CONFERENCE_KEYWORDS):
        return "inproceedings"
    external_ids = paper.get("externalIds") or {}
    if external_ids.get("ArXiv") and not venue:
        return "misc"
    return "article"


def _format_bibtex_author(paper: dict[str, Any]) -> str:
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
        if parsed.prefix:
            parts.append(f"{parsed.prefix} {parsed.last}, {parsed.first}")
        elif parsed.first:
            parts.append(f"{parsed.last}, {parsed.first}")
        else:
            parts.append(parsed.last)
        if parsed.suffix:
            parts[-1] += f", {parsed.suffix}"
    return " and ".join(parts)


def _paper_url(paper: dict[str, Any]) -> str | None:
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


def format_bibtex(papers: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
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

        author_str = _format_bibtex_author(paper)
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
            else:
                fields.append(f"  journal = {{{escape_bibtex(venue)}}}")

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        if doi:
            fields.append(f"  doi = {{{doi}}}")

        url = _paper_url(paper)
        if url:
            fields.append(f"  url = {{{url}}}")

        abstract = paper.get("abstract")
        if abstract:
            fields.append(f"  abstract = {{{escape_bibtex(abstract)}}}")

        arxiv = external_ids.get("ArXiv")
        if arxiv:
            fields.append(f"  eprint = {{{arxiv}}}")
            fields.append("  archiveprefix = {arXiv}")

        entry = f"@{entry_type}{{{key},\n"
        if fields:
            entry += ",\n".join(fields) + ",\n"
        entry += "}"
        lines.append(entry)

    return "\n\n".join(lines)

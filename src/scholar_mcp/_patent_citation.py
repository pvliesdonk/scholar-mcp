"""Patent entries for the BibTeX, CSL-JSON and RIS citation formats.

How each format represents a patent, and which kind codes mark an
application, is sourced in
``docs/design/reference/patent-citation-formats.md``; what this module does
on top of that (names, keys, the fields left out) is recorded in
``docs/design/patent-citations.md``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from ._bibtex_escape import escape_bibtex

if TYPE_CHECKING:
    from ._record_types import PatentParties, PatentRecord

PublicationStatus = Literal["application", "grant", "unknown"]

_APPLICATION: PublicationStatus = "application"
_GRANT: PublicationStatus = "grant"
_UNKNOWN: PublicationStatus = "unknown"


def _kinds(
    applications: tuple[str, ...], grants: tuple[str, ...]
) -> dict[str, PublicationStatus]:
    """Map each kind code of one office to its publication status.

    Args:
        applications: Kind codes that publish an application.
        grants: Kind codes that publish a granted patent.

    Returns:
        Kind code to status.
    """
    table: dict[str, PublicationStatus] = dict.fromkeys(applications, _APPLICATION)
    table.update(dict.fromkeys(grants, _GRANT))
    return table


# Kind codes as the reference page sources them. EP A3 (a separately
# published search report) is read as an application publication.
_KIND_STATUS: dict[str, dict[str, PublicationStatus]] = {
    "EP": _kinds(("A1", "A2", "A3", "A8", "A9"), ("B1", "B2", "B3", "B8", "B9")),
    "US": _kinds(
        ("A1", "A2", "A9", "P1", "P4", "P9"),
        ("B1", "B2", "B9", "E", "S", "P2", "P3", "A"),
    ),
    "DE": _kinds(("A1", "A8", "A9"), ("B3", "B4", "B8", "B9", "C5")),
}

# The PCT grants no patents: every WO publication is an application.
_ALWAYS_APPLICATION = "WO"

# biblatex localisation-key suffixes. They are not ISO codes (EP is "eu"),
# and biblatex's "fr" and "uk" keys are left out: no FR or GB kind code is
# sourced, so neither could ever be chosen.
_BIBLATEX_SUFFIX: dict[str, str] = {"DE": "de", "EP": "eu", "US": "us"}

_CC_TAG = re.compile(r"\s*\[[A-Z]{2}\]\s*$")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def publication_status(country: str, kind: str) -> PublicationStatus:
    """Say whether a publication is an application or a granted patent.

    Args:
        country: Two-letter office code, such as ``EP``.
        kind: Kind code, such as ``B1``; may be empty.

    Returns:
        ``"application"`` or ``"grant"`` for a sourced code, ``"unknown"``
        for any other office or kind code.
    """
    office = country.upper()
    if office == _ALWAYS_APPLICATION:
        return _APPLICATION
    return _KIND_STATUS.get(office, {}).get(kind.upper(), _UNKNOWN)


def person_name(name: str) -> tuple[str, str] | None:
    """Split a ``Family, Given`` name at its first comma.

    Every later comma part is a given name, so ``VAN LIESDONK, Peter,
    Petrus`` gives ``("VAN LIESDONK", "Peter Petrus")``.

    Args:
        name: One party name as EPO supplies it.

    Returns:
        ``(family, given)``, or ``None`` for a name with no comma (or no
        family part), which is not split.
    """
    family, sep, rest = name.partition(",")
    family = family.strip()
    if not sep or not family:
        return None
    given = " ".join(part.strip() for part in rest.split(",") if part.strip())
    return family, given


def _party_names(parties: PatentParties | None) -> list[str]:
    """Pick the names of one party list.

    The original spelling keeps the ``Family, Given`` comma, so it is
    preferred; the standardised one is used only when no original name
    exists, with its trailing ``[CC]`` tag removed.

    Args:
        parties: The record's ``applicants`` or ``inventors``.

    Returns:
        The non-empty names, in EPO's order.
    """
    if not parties:
        return []
    original = [n.strip() for n in parties.get("original") or [] if n.strip()]
    if original:
        return original
    standardised = (
        _CC_TAG.sub("", n).strip() for n in parties.get("standardised") or []
    )
    return [n for n in standardised if n]


def _split_number(record: PatentRecord) -> tuple[str, str, str]:
    """Split the dotted DOCDB publication number into its three parts.

    Args:
        record: Patent record with ``publication_number`` (``EP.3491801.B1``).

    Returns:
        ``(country, number, kind)``; a missing part is an empty string.
    """
    parts = (record.get("publication_number") or "").strip().split(".")
    parts += [""] * (3 - len(parts))
    country, number, kind = (p.strip() for p in parts[:3])
    return country.upper(), number, kind.upper()


def _spaced_number(record: PatentRecord) -> str:
    """Return the publication number with spaces: ``EP 3491801 B1``.

    Args:
        record: Patent record.

    Returns:
        The non-empty parts joined by single spaces.
    """
    return " ".join(p for p in _split_number(record) if p)


def _compact_number(record: PatentRecord) -> str:
    """Return the publication number without separators: ``EP3491801B1``.

    Args:
        record: Patent record.

    Returns:
        The parts joined with nothing between them.
    """
    return "".join(_split_number(record))


def _date_parts(value: str | None) -> tuple[str, str, str] | None:
    """Split a ``YYYY-MM-DD`` date.

    Args:
        value: Date string from the record, or ``None``.

    Returns:
        ``(year, month, day)``, or ``None`` when the value is not in that form.
    """
    match = _DATE.match(value or "")
    if match is None:
        return None
    year, month, day = match.groups()
    return year, month, day


def _record_status(record: PatentRecord) -> tuple[str, PublicationStatus]:
    """Return the record's office code and publication status.

    Args:
        record: Patent record.

    Returns:
        ``(country, status)``.
    """
    country, _number, kind = _split_number(record)
    return country, publication_status(country, kind)


def patent_key(record: PatentRecord, seen_keys: set[str]) -> str:
    """Build a citation key from the publication number: ``ep3491801b1``.

    Args:
        record: Patent record.
        seen_keys: Keys already used by papers and patents (mutated to
            include the new key).

    Returns:
        The lower-case compact number, with ``_2``, ``_3`` and so on when it
        repeats.
    """
    base = _compact_number(record).lower() or "patent"
    key = base
    suffix = 2
    while key in seen_keys:
        key = f"{base}_{suffix}"
        suffix += 1
    seen_keys.add(key)
    return key


def _bibtex_person(name: str) -> str:
    """Format one inventor for a BibTeX name list.

    Args:
        name: Party name.

    Returns:
        ``Family, Given`` (or ``Family``), or the whole name braced when it
        has no comma.
    """
    split = person_name(name)
    if split is None:
        return f"{{{escape_bibtex(name)}}}"
    family, given = split
    if not given:
        return escape_bibtex(family)
    return f"{escape_bibtex(family)}, {escape_bibtex(given)}"


def _bibtex_corporate(names: list[str]) -> str:
    """Join applicants as braced corporate names.

    Args:
        names: Applicant names.

    Returns:
        ``{A} and {B}``.
    """
    return " and ".join(f"{{{escape_bibtex(n)}}}" for n in names)


def _bibtex_party_fields(record: PatentRecord) -> list[str]:
    """Build the BibTeX ``author`` and ``holder`` fields.

    Inventors are the authors and applicants the holders. With no inventors
    the applicants become the authors, since biblatex requires ``author``,
    and there is no ``holder``.

    Args:
        record: Patent record.

    Returns:
        The fields present, ``author`` first.
    """
    inventors = _party_names(record.get("inventors"))
    applicants = _party_names(record.get("applicants"))
    fields: list[str] = []
    if inventors:
        authors = " and ".join(_bibtex_person(n) for n in inventors)
        fields.append(f"  author = {{{authors}}}")
        if applicants:
            fields.append(f"  holder = {{{_bibtex_corporate(applicants)}}}")
    elif applicants:
        fields.append(f"  author = {{{_bibtex_corporate(applicants)}}}")
    return fields


def _bibtex_type_fields(record: PatentRecord) -> list[str]:
    """Build the BibTeX ``type`` and ``location`` fields.

    Args:
        record: Patent record.

    Returns:
        A ``patreq``/``patent`` key for a known status, plus ``location``
        for WO (which has no key of its own) or for an unknown status (which
        gets no ``type``).
    """
    country, status = _record_status(record)
    if status == _UNKNOWN:
        return [f"  location = {{{country}}}"] if country else []
    prefix = "patreq" if status == _APPLICATION else "patent"
    suffix = _BIBLATEX_SUFFIX.get(country)
    if suffix is None:
        return [f"  type = {{{prefix}}}", f"  location = {{{country}}}"]
    return [f"  type = {{{prefix}{suffix}}}"]


def _bibtex_text_fields(record: PatentRecord) -> list[str]:
    """Build the BibTeX ``url`` and ``abstract`` fields.

    Args:
        record: Patent record.

    Returns:
        The fields present, in that order.
    """
    fields: list[str] = []
    url = record.get("url")
    if url:
        fields.append(f"  url = {{{escape_bibtex(url)}}}")
    abstract = record.get("abstract")
    if abstract:
        fields.append(f"  abstract = {{{escape_bibtex(abstract)}}}")
    return fields


def patent_bibtex_entry(record: PatentRecord, seen_keys: set[str]) -> str:
    """Format one patent as a biblatex ``@patent`` entry.

    Args:
        record: Patent record.
        seen_keys: Citation keys already used (mutated to include this one).

    Returns:
        The ``@patent{key, ...}`` entry.
    """
    key = patent_key(record, seen_keys)
    fields = _bibtex_party_fields(record)
    title = record.get("title")
    if title:
        fields.append(f"  title = {{{{{escape_bibtex(title)}}}}}")
    number = _spaced_number(record)
    if number:
        fields.append(f"  number = {{{number}}}")
    published = _date_parts(record.get("publication_date"))
    if published:
        fields.append(f"  date = {{{'-'.join(published)}}}")
    fields.extend(_bibtex_type_fields(record))
    fields.extend(_bibtex_text_fields(record))
    entry = f"@patent{{{key},\n"
    if fields:
        entry += ",\n".join(fields) + ",\n"
    return entry + "}"


def _csl_person(name: str) -> dict[str, str]:
    """Format one inventor as a CSL name.

    Args:
        name: Party name.

    Returns:
        ``{"family", "given"}``, or ``{"literal"}`` for a name with no comma.
    """
    split = person_name(name)
    if split is None:
        return {"literal": name}
    family, given = split
    return {"family": family, "given": given} if given else {"family": family}


def _csl_date(value: str | None) -> dict[str, Any] | None:
    """Format a ``YYYY-MM-DD`` date as CSL ``date-parts``.

    Args:
        value: Date string, or ``None``.

    Returns:
        The CSL date, or ``None`` when the value is not in that form.
    """
    parts = _date_parts(value)
    if parts is None:
        return None
    return {"date-parts": [[int(p) for p in parts]]}


def _csl_dates(record: PatentRecord) -> dict[str, Any]:
    """Build the CSL ``issued`` and ``submitted`` dates.

    Args:
        record: Patent record.

    Returns:
        ``issued`` from the publication date and ``submitted`` from the
        filing date, each only when present.
    """
    fields: dict[str, Any] = {}
    issued = _csl_date(record.get("publication_date"))
    if issued:
        fields["issued"] = issued
    submitted = _csl_date(record.get("filing_date"))
    if submitted:
        fields["submitted"] = submitted
    return fields


def patent_csl_entry(record: PatentRecord, seen_keys: set[str]) -> dict[str, Any]:
    """Format one patent as a CSL-JSON ``patent`` item.

    Applicants are left out: CSL has no assignee variable.

    Args:
        record: Patent record.
        seen_keys: Citation keys already used (mutated to include this one).

    Returns:
        The CSL item.
    """
    entry: dict[str, Any] = {"id": patent_key(record, seen_keys), "type": "patent"}
    title = record.get("title")
    if title:
        entry["title"] = title
    inventors = _party_names(record.get("inventors"))
    if inventors:
        entry["author"] = [_csl_person(n) for n in inventors]
    country, status = _record_status(record)
    if country:
        entry["authority"] = country
    number = _spaced_number(record)
    if number:
        entry["number"] = number
    if status == _APPLICATION:
        entry["genre"] = "patent application"
    entry.update(_csl_dates(record))
    for target, value in (
        ("URL", record.get("url")),
        ("abstract", record.get("abstract")),
    ):
        if value:
            entry[target] = value
    return entry


def _ris_person(name: str) -> str:
    """Format one inventor for a RIS ``AU`` tag.

    Args:
        name: Party name.

    Returns:
        ``Family, Given`` (or ``Family``), or the name as is when it has no
        comma.
    """
    split = person_name(name)
    if split is None:
        return name
    family, given = split
    return f"{family}, {given}" if given else family


def _ris_date_lines(record: PatentRecord) -> list[str]:
    """Build the RIS ``PY`` and ``DA`` tags from the publication date.

    Args:
        record: Patent record.

    Returns:
        ``PY  - YYYY///`` and ``DA  - YYYY/MM/DD``, or nothing.
    """
    parts = _date_parts(record.get("publication_date"))
    if parts is None:
        return []
    return [f"PY  - {parts[0]}///", f"DA  - {'/'.join(parts)}"]


def patent_ris_record(record: PatentRecord) -> str:
    """Format one patent as a RIS ``PAT`` record.

    Args:
        record: Patent record.

    Returns:
        The record, from its ``TY`` tag to its closing ``ER`` tag.
    """
    lines = ["TY  - PAT"]
    lines.extend(
        f"AU  - {_ris_person(n)}" for n in _party_names(record.get("inventors"))
    )
    title = record.get("title")
    if title:
        lines.append(f"TI  - {title}")
    lines.extend(_ris_date_lines(record))
    applicants = _party_names(record.get("applicants"))
    if applicants:
        lines.append(f"PB  - {'; '.join(applicants)}")
    number = _compact_number(record)
    if number:
        lines.append(f"SN  - {number}")
    for tag, value in (("UR", record.get("url")), ("AB", record.get("abstract"))):
        if value:
            lines.append(f"{tag}  - {value}")
    lines.append("ER  -")
    return "\n".join(lines)

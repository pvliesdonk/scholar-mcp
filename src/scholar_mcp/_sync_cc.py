"""Common Criteria framework + Protection Profile loader.

Loads CC framework documents (CC:2022 / CC:2017 / CEM) as a hard-coded
table — the set of framework documents is small (~10 entries) and changes
on a multi-year cadence, so an explicit table beats fragile HTML scraping.
Dual-published documents (e.g. CC:2022 Part 1 == ISO/IEC 15408-1:2022)
write two records cross-linked via ``related`` so callers can look up by
either committee's identifier and find the same content.

Protection Profile records load from the CC portal's published
``pps.csv``; identifier extraction uses per-scheme regex with a composite
fallback. PP parsing and the ``CCLoader`` class land in subsequent
commits in this PR.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._record_types import StandardRecord
else:
    StandardRecord = dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CCFrameworkEntry:
    """One framework document, optionally dual-published as an ISO record.

    Attributes:
        cc_identifier: Canonical CC form (e.g. ``"CC:2022 Part 1"``,
            ``"CEM:2022"``).
        iso_identifier: Canonical ISO form when the document is dual-
            published, otherwise ``None``. Examples:
            ``"ISO/IEC 15408-1:2022"``, ``"ISO/IEC 18045:2022"``.
        title: Full title shared by both records (CC and ISO publish the
            same content under different cover pages).
        cc_pdf_url: Direct link to the freely-downloadable CC PDF on
            commoncriteriaportal.org. Both records inherit this URL,
            which is the primary value of the CC loader vs. ISO's
            paywalled metadata.
        published_date: ISO-format date (``YYYY-MM-DD``) of publication.
        cc_version: CC version string (``"2022"``, ``"3.1 R5"``, etc.).
            Used for alias generation.
    """

    cc_identifier: str
    iso_identifier: str | None
    title: str
    cc_pdf_url: str
    published_date: str
    cc_version: str


def _framework_to_records(entry: CCFrameworkEntry) -> list[StandardRecord]:
    """Yield 1 (CC-only) or 2 (CC + ISO dual-publication) records.

    Each record carries the same ``full_text_url`` (the free CC PDF) and
    ``full_text_available=True``. The two records cross-link via the
    ``related`` field so an LLM looking up either form discovers the
    equivalence.
    """
    cc_record: StandardRecord = {
        "identifier": entry.cc_identifier,
        "title": entry.title,
        "body": "CC",
        "status": "published",
        "published_date": entry.published_date,
        "url": entry.cc_pdf_url,
        "full_text_url": entry.cc_pdf_url,
        "full_text_available": True,
        "price": None,
        "related": [entry.iso_identifier] if entry.iso_identifier else [],
    }
    if entry.iso_identifier is None:
        return [cc_record]

    iso_record: StandardRecord = {
        "identifier": entry.iso_identifier,
        "title": entry.title,
        "body": "ISO/IEC",
        "status": "published",
        "published_date": entry.published_date,
        "url": entry.cc_pdf_url,
        "full_text_url": entry.cc_pdf_url,
        "full_text_available": True,
        "price": None,
        "related": [entry.cc_identifier],
    }
    return [cc_record, iso_record]


def _framework_aliases(entry: CCFrameworkEntry) -> list[str]:
    """Return alias strings that should resolve to ``entry.cc_identifier``.

    Aliases cover common citation variants the LLM might encounter, e.g.
    ``"Common Criteria 2022 Part 1"`` (long form), ``"CC 2022 Part 1"``
    (no colon), etc. The standards_aliases table maps each alias to the
    canonical CC identifier.
    """
    aliases: list[str] = []
    cc_id = entry.cc_identifier  # e.g. "CC:2022 Part 1"

    if ":" in cc_id:
        prefix, rest = cc_id.split(":", 1)
        aliases.append(f"{prefix} {rest}")
        if prefix == "CC":
            aliases.append(f"Common Criteria {rest}")
            aliases.append(f"Common Criteria:{rest}")
        elif prefix == "CEM":
            aliases.append(f"Common Evaluation Methodology {rest}")
            aliases.append(f"Common Evaluation Methodology:{rest}")

    return aliases


# Hard-coded table of CC framework documents. Update when CCRA publishes
# a new release (typically every 5 years; CC:2017 → CC:2022 was a 5-year
# gap). PDF URLs verified via the live-smoke test
# `test_live_framework_pdf_urls_resolve_real`.
_FRAMEWORK_DOCS: list[CCFrameworkEntry] = [
    # CC:2022 Release 1 (Nov 2022) — Parts 1-3 dual-published as ISO/IEC 15408:2022
    CCFrameworkEntry(
        cc_identifier="CC:2022 Part 1",
        iso_identifier="ISO/IEC 15408-1:2022",
        title=(
            "Information security, cybersecurity and privacy protection — "
            "Evaluation criteria for IT security — "
            "Part 1: Introduction and general model"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART1R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    ),
    CCFrameworkEntry(
        cc_identifier="CC:2022 Part 2",
        iso_identifier="ISO/IEC 15408-2:2022",
        title=(
            "Information security, cybersecurity and privacy protection — "
            "Evaluation criteria for IT security — "
            "Part 2: Security functional components"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART2R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    ),
    CCFrameworkEntry(
        cc_identifier="CC:2022 Part 3",
        iso_identifier="ISO/IEC 15408-3:2022",
        title=(
            "Information security, cybersecurity and privacy protection — "
            "Evaluation criteria for IT security — "
            "Part 3: Security assurance components"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART3R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    ),
    # CC:2022 Parts 4-5 are CC-only (no ISO equivalent)
    CCFrameworkEntry(
        cc_identifier="CC:2022 Part 4",
        iso_identifier=None,
        title="Common Criteria for Information Technology Security Evaluation — "
        "Part 4: Framework for the specification of evaluation methods and activities",
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART4R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    ),
    CCFrameworkEntry(
        cc_identifier="CC:2022 Part 5",
        iso_identifier=None,
        title="Common Criteria for Information Technology Security Evaluation — "
        "Part 5: Pre-defined packages of security requirements",
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART5R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    ),
    # CC:2017 (CC 3.1 Revision 5) — dual-published as ISO/IEC 15408:2009/2008
    CCFrameworkEntry(
        cc_identifier="CC:2017 Part 1",
        iso_identifier="ISO/IEC 15408-1:2009",
        title=(
            "Common Criteria for Information Technology Security Evaluation — "
            "Part 1: Introduction and general model, Version 3.1 Revision 5"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CCPART1V3.1R5.pdf",
        published_date="2017-04-01",
        cc_version="3.1 R5",
    ),
    CCFrameworkEntry(
        cc_identifier="CC:2017 Part 2",
        iso_identifier="ISO/IEC 15408-2:2008",
        title=(
            "Common Criteria for Information Technology Security Evaluation — "
            "Part 2: Security functional components, Version 3.1 Revision 5"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CCPART2V3.1R5.pdf",
        published_date="2017-04-01",
        cc_version="3.1 R5",
    ),
    CCFrameworkEntry(
        cc_identifier="CC:2017 Part 3",
        iso_identifier="ISO/IEC 15408-3:2008",
        title=(
            "Common Criteria for Information Technology Security Evaluation — "
            "Part 3: Security assurance components, Version 3.1 Revision 5"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CCPART3V3.1R5.pdf",
        published_date="2017-04-01",
        cc_version="3.1 R5",
    ),
    # CEM
    CCFrameworkEntry(
        cc_identifier="CEM:2022",
        iso_identifier="ISO/IEC 18045:2022",
        title=(
            "Information security, cybersecurity and privacy protection — "
            "Evaluation criteria for IT security — "
            "Methodology for IT security evaluation"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CEM2022R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    ),
    CCFrameworkEntry(
        cc_identifier="CEM:2017",
        iso_identifier="ISO/IEC 18045:2008",
        title=(
            "Common Methodology for Information Technology Security Evaluation — "
            "Evaluation methodology, Version 3.1 Revision 5"
        ),
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CEMV3.1R5.pdf",
        published_date="2017-04-01",
        cc_version="3.1 R5",
    ),
]


# Per-scheme regex extracting a stable PP identifier from the Protection
# Profile URL filename. Each pattern is keyed by the scheme code
# (column "Scheme" in pps.csv: KR, DE, FR, US, ES, …).
_PP_SCHEME_PATTERNS: dict[str, re.Pattern[str]] = {
    "KR": re.compile(r"(KECS-PP-\d+-\d{4})"),
    "DE": re.compile(r"(BSI-CC-PP-\d+(?:-V\d+)?-\d{4})"),
    # ANSSI uses an underscore between year and number on disk; we
    # canonicalise to slash form via _extract_pp_id.
    "FR": re.compile(r"(ANSSI-CC-PP-\d{4}[_/]\d+)"),
    "US": re.compile(r"(NIAP-PP-[A-Za-z0-9_-]+|PP_[A-Za-z0-9_]+_v\d+(?:\.\d+)*)"),
    "ES": re.compile(r"(CCN-PP-\d+-\d{4})"),
}


def _extract_pp_id(scheme: str, pp_url: str, fallback_name: str) -> str:
    """Extract a stable PP identifier from the Protection Profile URL.

    Args:
        scheme: 2-letter scheme code from the CSV ``Scheme`` column.
        pp_url: Full URL to the PP PDF (may be empty).
        fallback_name: PP product name to use when no per-scheme regex
            matches; produces a composite ``CC PP {scheme}-{name}`` form.

    Returns:
        The extracted scheme-prefixed ID (e.g. ``"BSI-CC-PP-0099-V2-2017"``)
        or, on no match, the composite fallback. Never returns an empty
        string — callers can assume a usable identifier.
    """
    pattern = _PP_SCHEME_PATTERNS.get(scheme.upper())
    if pattern is not None:
        match = pattern.search(pp_url)
        if match:
            ident = match.group(1)
            # ANSSI canonicalisation: 2014_01 → 2014/01
            if scheme.upper() == "FR":
                m = re.match(r"(ANSSI-CC-PP-)(\d{4})[_/](\d+)$", ident)
                if m:
                    ident = f"{m.group(1)}{m.group(2)}/{m.group(3)}"
            return ident
    logger.debug("cc_pp_id_fallback scheme=%s name=%s", scheme, fallback_name)
    return f"CC PP {scheme}-{fallback_name}"


def _normalise_date(raw: str) -> str | None:
    """Convert ``MM/DD/YYYY`` → ``YYYY-MM-DD``; return None on parse failure."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        logger.debug("cc_pp_date_parse_failed raw=%s", raw)
        return None


def _pp_row_to_record(row: dict[str, str]) -> StandardRecord | None:
    """Map a pps.csv row to a StandardRecord, or None if unusable.

    Required fields: ``Protection Profile`` (URL), ``Name``, ``Scheme``.
    Missing or empty fields → None and a DEBUG log.
    """
    pp_url = (row.get("Protection Profile") or "").strip()
    name = (row.get("Name") or "").strip()
    scheme = (row.get("Scheme") or "").strip()
    if not pp_url or not name or not scheme:
        logger.debug(
            "cc_pp_row_skip reason=missing_required name=%s scheme=%s pp_url=%s",
            name,
            scheme,
            bool(pp_url),
        )
        return None

    identifier = _extract_pp_id(scheme, pp_url, name)
    archived = (row.get("Archived Date") or "").strip()
    status = "archived" if archived else "published"
    cert_url = (row.get("Certification Report URL") or "").strip()

    record: StandardRecord = {
        "identifier": identifier,
        "title": name,
        "body": "CC",
        "status": status,
        "published_date": _normalise_date(row.get("Certification Date") or ""),
        "url": cert_url or pp_url,
        "full_text_url": pp_url,
        "full_text_available": True,
        "price": None,
    }
    if archived:
        record["withdrawn_date"] = _normalise_date(archived)
    return record

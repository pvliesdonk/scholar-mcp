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
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._record_types import StandardRecord

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

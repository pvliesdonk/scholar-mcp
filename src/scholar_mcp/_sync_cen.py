"""CEN/CENELEC harmonised-standards loader.

Loads a curated table of EU harmonised standards from the major directives
(EMC, RED, Machinery, MDR, CRA, GPSR). The table is the single source of
truth — no upstream HTTP fetch, no EUR-Lex Formex XML parsing. Updates
happen by editing ``_HARMONISED_STANDARDS`` in this file; see
scholar-mcp#139 for the quarterly review cadence.

All records use ``body="CEN"`` regardless of whether the standard was
published by CEN or CENELEC — the distinction adds no value for LLM
citation resolution. EN ISO / EN IEC adoptions are stored under their
``EN`` prefix; no cross-linking to the ISO/IEC records.

Design reference: ``docs/specs/2026-04-16-pr4b-cen-loader-design.md``.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._standards_sync import SyncReport

if TYPE_CHECKING:
    from ._protocols import CacheProtocol
    from ._record_types import StandardRecord
else:
    StandardRecord = dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarmonisedStandard:
    """One entry in the hard-coded harmonised-standards table.

    Attributes:
        identifier: Canonical EN form, e.g. ``"EN 55032:2015"``,
            ``"EN ISO 13849-1:2023"``.
        title: Full title of the standard.
        directive: EU directive shorthand (``"EMC"``, ``"RED"``,
            ``"Machinery"``, ``"CRA"``, ``"MDR"``, ``"GPSR"``).
        status: ``"harmonised"`` for active OJ listings,
            ``"withdrawn"`` for standards removed by a later decision.
        published_date: ISO-format date or None.
    """

    identifier: str
    title: str
    directive: str
    status: str = "harmonised"
    published_date: str | None = None


def _hs_to_record(entry: HarmonisedStandard) -> StandardRecord:
    """Map a table entry to a StandardRecord.

    All CEN records are paywalled (``full_text_available=False``) and
    carry no catalogue URL (the CEN portal is unreliable).
    """
    record: StandardRecord = {
        "identifier": entry.identifier,
        "title": entry.title,
        "body": "CEN",
        "status": entry.status,
        "published_date": entry.published_date,
        "url": "",
        "full_text_url": None,
        "full_text_available": False,
        "price": None,
        "related": [],
    }
    return record


# Identity fields for change detection on re-sync.
_CEN_RECORD_IDENTITY_FIELDS = (
    "title",
    "status",
    "published_date",
    "body",
)


def _cen_record_changed(
    old: dict[str, Any] | StandardRecord, new: StandardRecord
) -> bool:
    """True when any identity field differs between *old* and *new*."""
    for field_name in _CEN_RECORD_IDENTITY_FIELDS:
        if old.get(field_name) != new.get(field_name):
            return True
    return False


# ---- Hard-coded table ----
# Update when new EU implementing decisions publish (~2-3x per directive
# per year). See scholar-mcp#139 for the quarterly review cadence.
# Source: https://single-market-economy.ec.europa.eu/single-market/
#         european-standards/harmonised-standards_en

_HARMONISED_STANDARDS: list[HarmonisedStandard] = [
    # ---- EMC Directive 2014/30/EU ----
    HarmonisedStandard(
        identifier="EN 55032:2015",
        title="Electromagnetic compatibility of multimedia equipment — Emission requirements",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55035:2017",
        title="Electromagnetic compatibility of multimedia equipment — Immunity requirements",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-3-2:2019",
        title="Electromagnetic compatibility — Limits for harmonic current emissions",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-3-3:2013",
        title="Electromagnetic compatibility — Limitation of voltage changes, voltage fluctuations and flicker",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-4-2:2009",
        title="Electromagnetic compatibility — Electrostatic discharge immunity test",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-4-3:2006",
        title="Electromagnetic compatibility — Radiated, radio-frequency, electromagnetic field immunity test",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-4-4:2012",
        title="Electromagnetic compatibility — Electrical fast transient/burst immunity test",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-4-5:2014",
        title="Electromagnetic compatibility — Surge immunity test",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-4-6:2014",
        title="Electromagnetic compatibility — Immunity to conducted disturbances, induced by radio-frequency fields",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-4-11:2004",
        title="Electromagnetic compatibility — Voltage dips, short interruptions and voltage variations immunity tests",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55011:2016",
        title="Industrial, scientific and medical equipment — Radio-frequency disturbance characteristics",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55014-1:2017",
        title="Electromagnetic compatibility — Requirements for household appliances — Part 1: Emission",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55014-2:2015",
        title="Electromagnetic compatibility — Requirements for household appliances — Part 2: Immunity",
        directive="EMC",
    ),
    # ---- RED 2014/53/EU ----
    HarmonisedStandard(
        identifier="EN 300 328 V2.2.2:2019",
        title="Wideband transmission systems — Data transmission equipment operating in the 2,4 GHz band",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 489-1 V2.2.3:2019",
        title="Electromagnetic compatibility standard for radio equipment and services — Part 1: Common technical requirements",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 489-17 V3.2.4:2020",
        title="Electromagnetic compatibility standard for radio equipment — Part 17: Specific conditions for broadband data transmission systems",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 62311:2020",
        title="Assessment of electronic and electrical equipment related to human exposure restrictions for electromagnetic fields",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 893 V2.1.1:2017",
        title="5 GHz RLAN — Harmonised standard for access to radio spectrum",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 303 345-1 V1.1.1:2019",
        title="Broadcast Sound Receivers — Part 1: General requirements",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 303 413 V1.2.1:2021",
        title="Satellite Earth Stations and Systems — GNSS receivers",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 300 220-1 V3.1.1:2017",
        title="Short Range Devices operating in the frequency range 25 MHz to 1000 MHz — Part 1",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 300 220-2 V3.2.1:2018",
        title="Short Range Devices operating in the frequency range 25 MHz to 1000 MHz — Part 2",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 300 440 V2.2.1:2018",
        title="Short Range Devices — Radio equipment to be used in the 1 GHz to 40 GHz frequency range",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 511 V12.5.1:2017",
        title="Mobile communication — GSM/DCS — Harmonised standard for access to radio spectrum",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 908-1 V13.1.1:2019",
        title="IMT cellular networks — Part 1: Introduction and common requirements",
        directive="RED",
    ),
    # ---- Machinery Directive 2006/42/EC ----
    HarmonisedStandard(
        identifier="EN ISO 12100:2010",
        title="Safety of machinery — General principles for design — Risk assessment and risk reduction",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 13849-1:2023",
        title="Safety of machinery — Safety-related parts of control systems — Part 1: General principles for design",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 13849-2:2012",
        title="Safety of machinery — Safety-related parts of control systems — Part 2: Validation",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN 60204-1:2018",
        title="Safety of machinery — Electrical equipment of machines — Part 1: General requirements",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 14120:2015",
        title="Safety of machinery — Guards — General requirements for the design and construction of fixed and movable guards",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 13857:2019",
        title="Safety of machinery — Safety distances to prevent hazard zones being reached by upper and lower limbs",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 4413:2010",
        title="Hydraulic fluid power — General rules and safety requirements for systems and their components",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 4414:2010",
        title="Pneumatic fluid power — General rules and safety requirements for systems and their components",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN 349:1993+A1:2008",
        title="Safety of machinery — Minimum gaps to avoid crushing of parts of the human body",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 13850:2015",
        title="Safety of machinery — Emergency stop function — Principles for design",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 14119:2013",
        title="Safety of machinery — Interlocking devices associated with guards — Principles for design and selection",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN 62061:2005+A2:2015",
        title="Safety of machinery — Functional safety of safety-related control systems",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 11161:2007+A1:2010",
        title="Safety of machinery — Integrated manufacturing systems — Basic requirements",
        directive="Machinery",
    ),
    # ---- MDR 2017/745 (Medical Devices Regulation) ----
    HarmonisedStandard(
        identifier="EN ISO 13485:2016",
        title="Medical devices — Quality management systems — Requirements for regulatory purposes",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 14971:2019",
        title="Medical devices — Application of risk management to medical devices",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN 62304:2006+A1:2015",
        title="Medical device software — Software life cycle processes",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN IEC 60601-1:2006+A1:2013",
        title="Medical electrical equipment — Part 1: General requirements for basic safety and essential performance",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN 62366-1:2015",
        title="Medical devices — Application of usability engineering to medical devices — Part 1",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 10993-1:2020",
        title="Biological evaluation of medical devices — Part 1: Evaluation and testing within a risk management process",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 11135:2014",
        title="Sterilization of health-care products — Ethylene oxide",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 11137-1:2015",
        title="Sterilization of health care products — Radiation — Part 1: Requirements",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 15223-1:2021",
        title="Medical devices — Symbols to be used with information to be supplied by the manufacturer — Part 1",
        directive="MDR",
    ),
    # ---- CRA (Cyber Resilience Act) ----
    HarmonisedStandard(
        identifier="EN IEC 62443-4-1:2018",
        title="Security for industrial automation and control systems — Part 4-1: Secure product development lifecycle requirements",
        directive="CRA",
    ),
    HarmonisedStandard(
        identifier="EN IEC 62443-4-2:2019",
        title="Security for industrial automation and control systems — Part 4-2: Technical security requirements for IACS components",
        directive="CRA",
    ),
    HarmonisedStandard(
        identifier="EN IEC 62443-3-3:2019",
        title="Security for industrial automation and control systems — Part 3-3: System security requirements and security levels",
        directive="CRA",
    ),
    HarmonisedStandard(
        identifier="EN ISO/IEC 27001:2022",
        title="Information security, cybersecurity and privacy protection — Information security management systems — Requirements",
        directive="CRA",
    ),
    # ---- GPSR (General Product Safety Regulation) ----
    HarmonisedStandard(
        identifier="EN 71-1:2014+A1:2018",
        title="Safety of toys — Part 1: Mechanical and physical properties",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 71-2:2020",
        title="Safety of toys — Part 2: Flammability",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 71-3:2019+A1:2021",
        title="Safety of toys — Part 3: Migration of certain elements",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 14988:2017+A1:2020",
        title="Children's high chairs and their accessories — Safety requirements and test methods",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 1130:2019",
        title="Furniture — Cribs and cradles for domestic use — Safety requirements and test methods",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 716-1:2017+A1:2020",
        title="Furniture — Children's cots and folding cots for domestic use — Part 1: Safety requirements",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 12790:2009",
        title="Child care articles — Reclined cradles",
        directive="GPSR",
    ),
    # ---- LVD (Low Voltage Directive) 2014/35/EU ----
    HarmonisedStandard(
        identifier="EN 62368-1:2020+A11:2020",
        title="Audio/video, information and communication technology equipment — Part 1: Safety requirements",
        directive="LVD",
    ),
    HarmonisedStandard(
        identifier="EN 60335-1:2012+A2:2019",
        title="Household and similar electrical appliances — Safety — Part 1: General requirements",
        directive="LVD",
    ),
    HarmonisedStandard(
        identifier="EN 61010-1:2010+A1:2019",
        title="Safety requirements for electrical equipment for measurement, control, and laboratory use — Part 1",
        directive="LVD",
    ),
    HarmonisedStandard(
        identifier="EN 60950-1:2006+A2:2013",
        title="Information technology equipment — Safety — Part 1: General requirements",
        directive="LVD",
        status="withdrawn",
    ),
]


def _compute_table_hash() -> str:
    """SHA256 of the table's identifiers + statuses, for change detection."""
    content = "|".join(
        f"{e.identifier}:{e.status}"
        for e in sorted(_HARMONISED_STANDARDS, key=lambda e: e.identifier)
    )
    return hashlib.sha256(content.encode()).hexdigest()


class CENLoader:
    """CEN/CENELEC harmonised-standards sync loader.

    Conforms to the Loader Protocol. The hard-coded
    ``_HARMONISED_STANDARDS`` table is the single source of truth —
    no upstream HTTP fetch. Re-sync with an unchanged table
    short-circuits via a content hash.

    Quarterly review cadence tracked in scholar-mcp#139.
    """

    body = "CEN"

    async def sync(self, cache: CacheProtocol, *, force: bool = False) -> SyncReport:
        """Write the harmonised-standards table into *cache*.

        Args:
            cache: Open cache.
            force: Bypass the content-hash check and rewrite all records.
        """
        started_at = time.time()
        errors: list[str] = []
        added = updated = unchanged = withdrawn = 0

        table_hash = _compute_table_hash()
        previous = await cache.get_sync_run(self.body)
        previous_hash = previous.get("upstream_ref") if previous else None

        if not force and previous_hash == table_hash:
            existing_count = len(await cache.list_synced_standard_ids(source=self.body))
            logger.info(
                "sync_cen_unchanged hash=%s count=%s", table_hash, existing_count
            )
            return SyncReport(
                body=self.body,
                added=0,
                updated=0,
                unchanged=existing_count,
                withdrawn=0,
                errors=errors,
                upstream_ref=table_hash,
                started_at=started_at,
                finished_at=time.time(),
            )

        prev_ids = await cache.list_synced_standard_ids(source=self.body)
        current_ids: set[str] = set()

        for entry in _HARMONISED_STANDARDS:
            record = _hs_to_record(entry)
            ident = record["identifier"]
            current_ids.add(ident)
            existing = await cache.get_standard(ident)
            if existing is None:
                added += 1
            elif _cen_record_changed(existing, record):
                updated += 1
            else:
                unchanged += 1
            await cache.set_standard(ident, record, source=self.body, synced=True)

        # Withdrawal: prev_ids - current_ids are standards removed from the
        # table (a code change). Same >50% guard for safety.
        missing = prev_ids - current_ids
        if prev_ids and len(missing) > 0.5 * len(prev_ids):
            errors.append(
                f"withdrawal pass aborted: {len(missing)}/{len(prev_ids)} "
                "ids missing (>50% — likely a bug in the table edit)"
            )
            logger.warning(
                "cen_withdrawal_aborted missing=%s prev=%s",
                len(missing),
                len(prev_ids),
            )
        else:
            for ident in missing:
                existing = await cache.get_standard(ident)
                if existing is None:
                    continue
                from typing import cast

                withdrawn_record = cast(
                    "StandardRecord", {**existing, "status": "withdrawn"}
                )
                await cache.set_standard(
                    ident, withdrawn_record, source=self.body, synced=True
                )
                withdrawn += 1

        logger.info(
            "sync_cen_done hash=%s added=%s updated=%s unchanged=%s withdrawn=%s",
            table_hash,
            added,
            updated,
            unchanged,
            withdrawn,
        )

        return SyncReport(
            body=self.body,
            added=added,
            updated=updated,
            unchanged=unchanged,
            withdrawn=withdrawn,
            errors=errors,
            upstream_ref=table_hash,
            started_at=started_at,
            finished_at=time.time(),
        )

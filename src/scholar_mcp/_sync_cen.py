"""CEN/CENELEC harmonised-standards loader.

Loads a curated table of EU harmonised standards from the major directives
and regulations (EMC, RED, Machinery, MDR, LVD, Toys, GPSR). The table is the single source of
truth — no upstream HTTP fetch, no EUR-Lex Formex XML parsing. Updates
happen by editing ``_HARMONISED_STANDARDS`` in this file; see
scholar-mcp#139 for the quarterly review cadence.

All records use ``body="CEN"`` regardless of whether the standard was
published by CEN or CENELEC — the distinction adds no value for LLM
citation resolution. EN ISO / EN IEC adoptions are stored under their
``EN`` prefix; no cross-linking to the ISO/IEC records.

Design reference: ``docs/design/history/specs/2026-04-16-pr4b-cen-loader-design.md``.
"""

from __future__ import annotations

import hashlib
import logging
import re
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

_AMENDMENT_SUFFIX_RE = re.compile(r"\+A\d+:\d{4}$")


def _normalise_en_identifier(identifier: str) -> str:
    """Strip amendment suffix and version notation for cache-key normalisation.

    ``EN 349:1993+A1:2008`` → ``EN 349:1993``
    ``EN 300 328 V2.2.2:2019`` → ``EN 300 328:2019``

    Args:
        identifier: Raw identifier string from the harmonised-standards table.

    Returns:
        Normalised identifier suitable for use as a cache key.
    """
    # Strip amendment suffix: +A1:2008, +A2:2019, +A11:2020
    ident = _AMENDMENT_SUFFIX_RE.sub("", identifier)
    # Strip ETSI-style version notation: V2.2.2, V1.1.1 etc.
    ident = re.sub(r"\s+V[\d.]+(?=\s*[:\s-]\s*\d{4})", "", ident)
    return ident.strip()


@dataclass(frozen=True)
class HarmonisedStandard:
    """One entry in the hard-coded harmonised-standards table.

    Attributes:
        identifier: Canonical EN form, e.g. ``"EN 55032:2015"``,
            ``"EN ISO 13849-1:2023"``.
        title: Full title of the standard.
        directive: EU act shorthand (``"EMC"``, ``"RED"``, ``"Machinery"``,
            ``"MDR"``, ``"LVD"``, ``"Toys"``, ``"GPSR"``).
        status: ``"harmonised"`` for active OJ listings,
            ``"withdrawn"`` for standards removed by a later decision.
        published_date: ISO-format date or None.
        withdrawn_date: The date the reference stopped giving presumption
            of conformity, for a withdrawn entry.
        superseded_by: Table identifiers of the standards the OJ names in
            its place, for a withdrawn entry.
    """

    identifier: str
    title: str
    directive: str
    status: str = "harmonised"
    published_date: str | None = None
    withdrawn_date: str | None = None
    superseded_by: tuple[str, ...] = ()


def _hs_to_record(entry: HarmonisedStandard) -> StandardRecord:
    """Map a table entry to a StandardRecord.

    All CEN records are paywalled (``full_text_available=False``) and
    carry no catalogue URL (the CEN portal is unreliable).

    The cache key (``identifier``) is normalised: amendment suffixes such as
    ``+A1:2008`` and ETSI-style version tokens such as ``V2.2.2`` are stripped
    so that ``resolve_identifier_local`` and the cache lookup agree on the same
    key form.
    """
    normalised_id = _normalise_en_identifier(entry.identifier)
    record: StandardRecord = {
        "identifier": normalised_id,
        "title": entry.title,
        "body": "CEN",
        "status": entry.status,
        "published_date": entry.published_date,
        "withdrawn_date": entry.withdrawn_date,
        "superseded_by": [_normalise_en_identifier(s) for s in entry.superseded_by],
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
    "withdrawn_date",
    "superseded_by",
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
# Reviewed 2026-11-20 against the OJ citations (#139). Each entry is the
# reference as cited, with the latest cited amendment as its "+A" suffix
# (corrigenda left out); the summary lists and decisions are linked from
# https://single-market-economy.ec.europa.eu/single-market/european-standards/harmonised-standards_en
# Not in the table, because nothing is cited under them yet: the Cyber
# Resilience Act (EU) 2024/2847 (its standardisation request M/606 is due
# from 30.11.2026), the Machinery Regulation (EU) 2023/1230 and the Toy
# Safety Regulation (EU) 2025/2509. Review again each quarter (#594).
_HARMONISED_STANDARDS: list[HarmonisedStandard] = [
    # ---- EMC Directive 2014/30/EU: Decision (EU) 2019/1326 as amended up
    # to 2022/910, and the OJ C 246 communication of 13.7.2018 ----
    HarmonisedStandard(
        identifier="EN 55032:2015+A11:2020",
        title="Electromagnetic compatibility of multimedia equipment — Emission requirements",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55035:2017+A11:2020",
        title="Electromagnetic compatibility of multimedia equipment — Immunity requirements",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-3-2:2014",
        title="Electromagnetic compatibility — Limits for harmonic current emissions",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-3-3:2013",
        title="Electromagnetic compatibility — Limitation of voltage changes, voltage fluctuations and flicker",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-6-1:2007",
        title="Electromagnetic compatibility — Generic standards — Immunity for residential, commercial and light-industrial environments",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-6-2:2005",
        title="Electromagnetic compatibility — Generic standards — Immunity for industrial environments",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-6-3:2007+A1:2011",
        title="Electromagnetic compatibility — Generic standards — Emission standard for residential, commercial and light-industrial environments",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 61000-6-4:2007+A1:2011",
        title="Electromagnetic compatibility — Generic standards — Emission standard for industrial environments",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55011:2016+A11:2020",
        title="Industrial, scientific and medical equipment — Radio-frequency disturbance characteristics",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55014-1:2017+A11:2020",
        title="Electromagnetic compatibility — Requirements for household appliances — Part 1: Emission",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN 55014-2:1997+A2:2008",
        title="Electromagnetic compatibility — Requirements for household appliances — Part 2: Immunity",
        directive="EMC",
    ),
    HarmonisedStandard(
        identifier="EN IEC 55015:2019+A11:2020",
        title="Limits and methods of measurement of radio disturbance characteristics of electrical lighting and similar equipment",
        directive="EMC",
    ),
    # ---- RED 2014/53/EU: Decision (EU) 2022/2191 as amended up to
    # 2026/2003. ETSI standards are cited by version; the year is that of
    # ETSI's published file ----
    HarmonisedStandard(
        identifier="EN 300 328 V2.2.2:2019",
        title="Wideband transmission systems — Data transmission equipment operating in the 2,4 GHz band",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 489-17 V3.3.1:2024",
        title="Electromagnetic compatibility standard for radio equipment and services — Part 17: Specific conditions for broadband and wideband data transmission systems",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 893 V2.1.1:2017",
        title="5 GHz RLAN — Harmonised standard covering the essential requirements of Article 3(2)",
        directive="RED",
        # Still cited until 15.05.2028 (Decision (EU) 2025/893).
    ),
    HarmonisedStandard(
        identifier="EN 301 893 V2.2.1:2024",
        title="5 GHz WAS/RLAN — Harmonised standard for access to radio spectrum",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 303 413 V1.2.1:2021",
        title="Satellite Earth Stations and Systems — GNSS receivers",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 300 220-2 V3.1.1:2017",
        title="Short Range Devices operating in the frequency range 25 MHz to 1000 MHz — Part 2: Non specific radio equipment",
        directive="RED",
        # Still cited until 11.06.2027 (Decision (EU) 2025/2499).
    ),
    HarmonisedStandard(
        identifier="EN 300 220-2 V3.3.1:2025",
        title="Short Range Devices operating in the frequency range 25 MHz to 1000 MHz with power levels up to 500 mW — Part 2: Non specific radio equipment",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 300 440 V2.1.1:2017",
        title="Short Range Devices — Radio equipment to be used in the 1 GHz to 40 GHz frequency range",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 511 V12.5.1:2017",
        title="Global System for Mobile communications (GSM) — Mobile Stations (MS) equipment",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 301 908-1 V13.1.1:2019",
        title="IMT cellular networks — Part 1: Introduction and common requirements",
        directive="RED",
        status="withdrawn",
        withdrawn_date="2023-09-29",
        superseded_by=("EN 301 908-1 V15.2.1:2023",),
    ),
    HarmonisedStandard(
        identifier="EN 301 908-1 V15.2.1:2023",
        title="IMT cellular networks — Part 1: Introduction and common requirements — Release 15",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 18031-1:2024",
        title="Common security requirements for radio equipment — Part 1: Internet connected radio equipment",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 18031-2:2024",
        title="Common security requirements for radio equipment — Part 2: Radio equipment processing data, namely internet connected radio equipment, childcare radio equipment, toys radio equipment and wearable radio equipment",
        directive="RED",
    ),
    HarmonisedStandard(
        identifier="EN 18031-3:2024",
        title="Common security requirements for radio equipment — Part 3: Internet connected radio equipment processing virtual money or monetary value",
        directive="RED",
    ),
    # ---- Machinery Directive 2006/42/EC: Decision (EU) 2023/1586 as
    # amended up to 2026/2015, which repeals it from 20.01.2027 together
    # with the Directive. Every entry still marked harmonised here loses
    # its presumption that day, unless the first list under Regulation
    # (EU) 2023/1230 cites it again ----
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
        status="withdrawn",
        withdrawn_date="2022-09-03",
        superseded_by=("EN ISO 13854:2019",),
    ),
    HarmonisedStandard(
        identifier="EN ISO 13854:2019",
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
        identifier="EN ISO 14119:2025+A11:2026",
        title="Safety of machinery — Interlocking devices associated with guards — Principles for design and selection",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN 62061:2005+A2:2015",
        title="Safety of machinery — Functional safety of safety-related electrical, electronic and programmable electronic control systems",
        directive="Machinery",
        status="withdrawn",
        withdrawn_date="2023-10-11",
        superseded_by=("EN IEC 62061:2021+A1:2024",),
    ),
    HarmonisedStandard(
        identifier="EN IEC 62061:2021+A1:2024",
        title="Safety of machinery — Functional safety of safety-related control systems",
        directive="Machinery",
    ),
    HarmonisedStandard(
        identifier="EN ISO 11161:2007+A1:2010",
        title="Safety of machinery — Integrated manufacturing systems — Basic requirements",
        directive="Machinery",
    ),
    # ---- MDR (EU) 2017/745: Decision (EU) 2021/1182 as amended up to
    # 2026/2479 ----
    HarmonisedStandard(
        identifier="EN ISO 13485:2016+A11:2021",
        title="Medical devices — Quality management systems — Requirements for regulatory purposes",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 14971:2019+A11:2021",
        title="Medical devices — Application of risk management to medical devices",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN 60601-1:2006+A13:2024",
        title="Medical electrical equipment — Part 1: General requirements for basic safety and essential performance",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 10993-1:2025",
        title="Biological evaluation of medical devices — Part 1: Requirements and general principles for the evaluation of biological safety within a risk management process",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 11135:2014+A1:2019",
        title="Sterilization of health-care products — Ethylene oxide — Requirements for the development, validation and routine control of a sterilization process for medical devices",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 11137-1:2015+A2:2019",
        title="Sterilization of health care products — Radiation — Part 1: Requirements for the development, validation and routine control of a sterilization process for medical devices",
        directive="MDR",
        # Still cited until 10.05.2028 (Decision (EU) 2026/2479).
    ),
    HarmonisedStandard(
        identifier="EN ISO 11137-1:2026",
        title="Sterilization of health care products — Radiation — Part 1: Requirements for the development, validation and routine control of a sterilization process for medical devices",
        directive="MDR",
    ),
    HarmonisedStandard(
        identifier="EN ISO 15223-1:2021+A1:2025",
        title="Medical devices — Symbols to be used with information to be supplied by the manufacturer — Part 1: General requirements",
        directive="MDR",
    ),
    # ---- Toy Safety Directive 2009/48/EC: Decision (EU) 2023/740 as
    # amended up to 2026/2032 ----
    HarmonisedStandard(
        identifier="EN 71-1:2014+A1:2018",
        title="Safety of toys — Part 1: Mechanical and physical properties",
        directive="Toys",
    ),
    HarmonisedStandard(
        identifier="EN 71-2:2020",
        title="Safety of toys — Part 2: Flammability",
        directive="Toys",
    ),
    HarmonisedStandard(
        identifier="EN 71-3:2019+A2:2024",
        title="Safety of toys — Part 3: Migration of certain elements",
        directive="Toys",
    ),
    # ---- GPSR (EU) 2023/988: Decision (EU) 2026/901 ----
    HarmonisedStandard(
        identifier="EN 14988:2017+A2:2024",
        title="Children's high chairs — Requirements and test methods",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 1130:2019",
        title="Furniture — Cribs and cradles for domestic use — Safety requirements and test methods",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 716-1:2017",
        title="Furniture — Children's cots and folding cots for domestic use — Part 1: Safety requirements",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 12790-1:2023",
        title="Child care articles — Reclined cradles — Part 1: Safety requirements",
        directive="GPSR",
    ),
    HarmonisedStandard(
        identifier="EN 12790-2:2023",
        title="Child care articles — Reclined cradles — Part 2: Test methods",
        directive="GPSR",
    ),
    # ---- LVD 2014/35/EU: Decision (EU) 2023/2723 as amended up to
    # 2025/1488 ----
    HarmonisedStandard(
        identifier="EN 62368-1:2014",
        title="Audio/video, information and communication technology equipment — Part 1: Safety requirements",
        directive="LVD",
    ),
    HarmonisedStandard(
        identifier="EN 60335-1:2012+A15:2021",
        title="Household and similar electrical appliances — Safety — Part 1: General requirements",
        directive="LVD",
    ),
    HarmonisedStandard(
        identifier="EN 61010-1:2010+A1:2019",
        title="Safety requirements for electrical equipment for measurement, control, and laboratory use — Part 1: General requirements",
        directive="LVD",
    ),
    HarmonisedStandard(
        identifier="EN 60950-1:2006+A2:2013",
        title="Information technology equipment — Safety — Part 1: General requirements",
        directive="LVD",
        status="withdrawn",
        withdrawn_date="2020-12-20",
        superseded_by=("EN 62368-1:2014",),
    ),
]


def _compute_table_hash() -> str:
    """SHA256 of the table's identity fields for change detection.

    Includes every field a record carries, so that any content change (not
    just identifier or status) triggers a re-sync.
    """
    content = "|".join(
        f"{_normalise_en_identifier(e.identifier)}:{e.title}:{e.status}:"
        f"{e.published_date}:{e.withdrawn_date}:{','.join(e.superseded_by)}"
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
        added = updated = unchanged = 0

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

        # Removal: prev_ids - current_ids are standards dropped from the
        # table (a code change). A standard the OJ withdrew stays in the table
        # as a withdrawn entry, so a dropped one never belonged there (#139)
        # and its row goes. Same >50% guard for safety.
        missing = prev_ids - current_ids
        removed = 0
        if prev_ids and len(missing) > 0.5 * len(prev_ids):
            errors.append(
                f"removal pass aborted: {len(missing)}/{len(prev_ids)} "
                "ids missing (>50% — likely a bug in the table edit)"
            )
            logger.warning(
                "cen_removal_aborted missing=%s prev=%s",
                len(missing),
                len(prev_ids),
            )
        else:
            removed = await cache.delete_synced_standards(self.body, sorted(missing))

        logger.info(
            "sync_cen_done hash=%s added=%s updated=%s unchanged=%s removed=%s",
            table_hash,
            added,
            updated,
            unchanged,
            removed,
        )

        return SyncReport(
            body=self.body,
            added=added,
            updated=updated,
            unchanged=unchanged,
            withdrawn=0,
            errors=errors,
            removed=removed,
            upstream_ref=table_hash,
            started_at=started_at,
            finished_at=time.time(),
        )

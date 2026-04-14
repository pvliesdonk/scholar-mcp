"""Relaton YAML → StandardRecord mapper and loader.

Shared between the ISO and IEC sync loaders; the joint-standard detection
logic lives in :func:`_canonical_identifier_and_body`.

Design reference: ``docs/specs/2026-04-13-pr2-iso-iec-relaton-design.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._record_types import StandardRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelatonConfig:
    """Per-body Relaton sync configuration."""

    body: str  # "ISO" or "IEC"
    repo: str  # "relaton/relaton-data-iso"
    branch: str = "main"


_RELATON_BODIES: dict[str, RelatonConfig] = {
    "ISO": RelatonConfig(body="ISO", repo="relaton/relaton-data-iso"),
    "IEC": RelatonConfig(body="IEC", repo="relaton/relaton-data-iec"),
}


# Map Relaton docstatus.stage codes → StandardRecord.status
_STAGE_TO_STATUS = {
    "60.60": "published",
    "90.20": "published",  # periodic review
    "90.60": "published",
    "90.92": "published",  # confirmed
    "90.93": "published",  # to be revised
    "95.99": "withdrawn",
    "95.60": "withdrawn",
}


def _canonical_identifier_and_body(
    docidentifiers: list[dict[str, Any]],
) -> tuple[str, str] | None:
    """Return ``(identifier, body)`` for a Relaton doc, or ``None`` if unknown.

    Joint detection rules:
    - If the docidentifier list contains BOTH a ``type=ISO`` entry and a
      ``type=IEC`` entry, the standard is joint → ``body="ISO/IEC"``.
    - If only one of ``{ISO, IEC}`` types is present → ``body=that type``.
    - Otherwise the primary entry's ``type`` determines both.
    """
    if not docidentifiers:
        return None

    iso_entries = [d for d in docidentifiers if str(d.get("type", "")).upper() == "ISO"]
    iec_entries = [d for d in docidentifiers if str(d.get("type", "")).upper() == "IEC"]
    primary_entries = [d for d in docidentifiers if d.get("primary")]

    if iso_entries and iec_entries:
        # Joint — prefer an entry whose id already contains the slash form
        joint = next(
            (
                d
                for d in iso_entries + iec_entries
                if "ISO/IEC" in str(d.get("id", ""))
                or "IEC/ISO" in str(d.get("id", ""))
            ),
            iso_entries[0],
        )
        ident = str(joint.get("id", "")).strip()
        # Normalise reversed joint form
        ident = ident.replace("IEC/ISO", "ISO/IEC")
        if not ident.startswith("ISO/IEC"):
            # docidentifier had plain ISO text in the ISO entry for a joint doc
            ident = (
                "ISO/IEC " + ident[len("ISO ") :] if ident.startswith("ISO ") else ident
            )
        return ident, "ISO/IEC"

    if iso_entries:
        return str(iso_entries[0].get("id", "")).strip(), "ISO"
    if iec_entries:
        return str(iec_entries[0].get("id", "")).strip(), "IEC"
    if primary_entries:
        ident = str(primary_entries[0].get("id", "")).strip()
        body = str(primary_entries[0].get("type", "")).upper()
        if ident and body:
            return ident, body
    return None


def _first_link_of_type(links: list[dict[str, Any]] | None, wanted: str) -> str | None:
    if not links:
        return None
    for link in links:
        if str(link.get("type", "")).lower() == wanted:
            content = link.get("content")
            if isinstance(content, str) and content:
                return content
    return None


def _first_title(titles: list[Any] | None) -> str:
    if not titles:
        return ""
    first = titles[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        content = first.get("content")
        if isinstance(content, str):
            return content
    return ""


def _published_date(dates: list[dict[str, Any]] | None) -> str | None:
    if not dates:
        return None
    for entry in dates:
        if str(entry.get("type", "")).lower() == "published":
            value = entry.get("value")
            if isinstance(value, str):
                return value
    return None


def _superseded_by(relations: list[dict[str, Any]] | None) -> str | None:
    if not relations:
        return None
    for rel in relations:
        if str(rel.get("type", "")).lower() != "obsoleted-by":
            continue
        bibitem = rel.get("bibitem") or {}
        for ident in bibitem.get("docidentifier", []) or []:
            if ident.get("id"):
                return str(ident["id"])
    return None


def _supersedes(relations: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    if not relations:
        return out
    for rel in relations:
        if str(rel.get("type", "")).lower() != "obsoletes":
            continue
        bibitem = rel.get("bibitem") or {}
        for ident in bibitem.get("docidentifier", []) or []:
            if ident.get("id"):
                out.append(str(ident["id"]))
    return out


def _committee(editorialgroup: dict[str, Any] | None) -> str | None:
    if not editorialgroup:
        return None
    tcs = editorialgroup.get("technical_committee") or editorialgroup.get(
        "technical-committee"
    )
    if not tcs:
        return None
    if isinstance(tcs, list) and tcs:
        first = tcs[0]
        if isinstance(first, dict) and first.get("name"):
            return str(first["name"])
    return None


def _yaml_to_record(
    doc: dict[str, Any],
) -> tuple[StandardRecord | None, list[str]]:
    """Map a parsed Relaton YAML document to ``(StandardRecord, aliases)``.

    Returns ``(None, [])`` on schema mismatches that prevent extracting an
    identifier or title. Callers treat the missing record as a non-fatal
    skip and append an error message for the report.

    Args:
        doc: Parsed Relaton YAML.

    Returns:
        Tuple of ``(StandardRecord | None, alias_identifiers)``.
    """
    docidentifiers = doc.get("docidentifier") or []
    canonical = _canonical_identifier_and_body(docidentifiers)
    if canonical is None:
        return None, []
    identifier, body = canonical
    if not identifier:
        return None, []

    title = _first_title(doc.get("title"))
    if not title:
        return None, []

    stage = str((doc.get("docstatus") or {}).get("stage", "")).strip()
    status = _STAGE_TO_STATUS.get(stage, "published")

    url = _first_link_of_type(doc.get("link"), "src") or ""
    full_text_url = _first_link_of_type(doc.get("link"), "obp") or _first_link_of_type(
        doc.get("link"), "pub"
    )

    scope_value: str | None = None
    abstracts = doc.get("abstract") or []
    if abstracts:
        first = abstracts[0]
        if isinstance(first, dict):
            content = first.get("content")
            if isinstance(content, str):
                scope_value = content

    record: StandardRecord = {
        "identifier": identifier,
        "title": title,
        "body": body,
        "status": status,
        "published_date": _published_date(doc.get("date")),
        "superseded_by": _superseded_by(doc.get("relation")),
        "supersedes": _supersedes(doc.get("relation")),
        "scope": scope_value,
        "committee": _committee(doc.get("editorialgroup")),
        "url": url,
        "full_text_url": full_text_url,
        "full_text_available": False,
        "price": None,
        "related": [],
    }

    aliases: list[str] = []
    for entry in docidentifiers:
        alias = entry.get("id")
        if not isinstance(alias, str):
            continue
        if alias == identifier:
            continue
        aliases.append(alias)

    return record, aliases


# Fields we treat as identity for change detection. Everything else (e.g.
# aliases, transient cache metadata) is ignored.
_RECORD_IDENTITY_FIELDS = (
    "title",
    "status",
    "published_date",
    "withdrawn_date",
    "superseded_by",
    "supersedes",
    "scope",
    "committee",
    "url",
    "full_text_url",
    "full_text_available",
    "body",
)


def _record_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """True when any identity field differs between ``old`` and ``new``."""
    for field_name in _RECORD_IDENTITY_FIELDS:
        if old.get(field_name) != new.get(field_name):
            return True
    return False

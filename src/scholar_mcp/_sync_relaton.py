"""Relaton YAML → StandardRecord mapper and loader.

Shared between the ISO and IEC sync loaders; the joint-standard detection
logic lives in :func:`_canonical_identifier_and_body`.

Design reference: ``docs/specs/2026-04-13-pr2-iso-iec-relaton-design.md``.
"""

from __future__ import annotations

import logging
import tarfile
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import httpx
import yaml

from ._protocols import CacheProtocol
from ._standards_sync import SyncReport

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
            # docidentifier had plain ISO or IEC text in the entry for a joint doc
            if ident.startswith("ISO "):
                ident = "ISO/IEC " + ident[len("ISO ") :]
            elif ident.startswith("IEC "):
                ident = "ISO/IEC " + ident[len("IEC ") :]
            # else: leave as-is (unusual upstream shape)
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
        idents = bibitem.get("docid") or bibitem.get("docidentifier") or []
        for ident in idents:
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
        idents = bibitem.get("docid") or bibitem.get("docidentifier") or []
        for ident in idents:
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
    docidentifiers = doc.get("docid") or doc.get("docidentifier") or []
    canonical = _canonical_identifier_and_body(docidentifiers)
    if canonical is None:
        logger.debug("relaton_yaml_skip reason=%s identifier=%s", "no_canonical", "")
        return None, []
    identifier, body = canonical
    if not identifier:
        logger.debug(
            "relaton_yaml_skip reason=%s identifier=%s", "empty_identifier", ""
        )
        return None, []

    title = _first_title(doc.get("title"))
    if not title:
        logger.debug(
            "relaton_yaml_skip reason=%s identifier=%s", "no_title", identifier
        )
        return None, []

    stage = str((doc.get("docstatus") or {}).get("stage", "")).strip()
    if stage and stage not in _STAGE_TO_STATUS:
        logger.debug("relaton_unknown_stage stage=%s identifier=%s", stage, identifier)
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


def _record_changed(old: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    """True when any identity field differs between ``old`` and ``new``."""
    for field_name in _RECORD_IDENTITY_FIELDS:
        if old.get(field_name) != new.get(field_name):
            return True
    return False


_GITHUB_API = "https://api.github.com"


class RelatonLoader:
    """One instance per body (ISO or IEC). Conforms to the Loader protocol.

    The full sync algorithm is documented in
    ``docs/specs/2026-04-13-pr2-iso-iec-relaton-design.md``.
    """

    def __init__(
        self,
        body: str,
        *,
        http: httpx.AsyncClient,
        token: str | None = None,
    ) -> None:
        config = _RELATON_BODIES.get(body.upper())
        if config is None:
            raise ValueError(f"unsupported Relaton body: {body!r}")
        self._config = config
        self._http = http
        self._token = token

    @property
    def body(self) -> str:
        return self._config.body

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    async def _head_sha(self) -> str:
        url = f"{_GITHUB_API}/repos/{self._config.repo}/commits/{self._config.branch}"
        response = await self._http.get(url, headers=self._headers())
        response.raise_for_status()
        sha = response.json().get("sha")
        if not isinstance(sha, str) or not sha:
            raise RuntimeError(f"missing sha in response from {url}")
        return sha

    async def sync(self, cache: CacheProtocol, *, force: bool = False) -> SyncReport:
        """Pull upstream YAML into *cache*, returning a SyncReport.

        Args:
            cache: Open cache.
            force: If True, bypass the SHA freshness check and re-sync.
        """
        started_at = time.time()
        errors: list[str] = []

        sha = await self._head_sha()

        previous = await cache.get_sync_run(self.body)
        previous_sha = previous.get("upstream_ref") if previous else None

        if not force and previous_sha == sha:
            existing_count = len(await cache.list_synced_standard_ids(source=self.body))
            logger.info(
                "sync_relaton_unchanged body=%s sha=%s count=%s",
                self.body,
                sha,
                existing_count,
            )
            return SyncReport(
                body=self.body,
                added=0,
                updated=0,
                unchanged=existing_count,
                withdrawn=0,
                errors=errors,
                upstream_ref=sha,
                started_at=started_at,
                finished_at=time.time(),
            )

        added = updated = unchanged = 0
        current_ids: set[str] = set()

        # Snapshot prev_ids BEFORE the tarball loop so the withdrawal guard
        # denominator reflects the prior state, not the post-insertion state.
        prev_ids = await cache.list_synced_standard_ids(source=self.body)

        tar_url = f"{_GITHUB_API}/repos/{self._config.repo}/tarball/{sha}"
        with tempfile.TemporaryFile(suffix=".tar.gz") as tmp:
            async with self._http.stream(
                "GET", tar_url, headers=self._headers(), follow_redirects=True
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=1 << 20):
                    tmp.write(chunk)
            tmp.seek(0)
            with tarfile.open(fileobj=tmp, mode="r:gz") as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    if not member.name.endswith(".yaml"):
                        continue
                    if "/data/" not in member.name:
                        continue

                    handle = tar.extractfile(member)
                    if handle is None:
                        continue
                    try:
                        doc = yaml.safe_load(handle.read())
                    except yaml.YAMLError as exc:
                        errors.append(f"unparseable: {member.name}: {exc}")
                        continue
                    if not isinstance(doc, dict):
                        errors.append(f"unparseable: {member.name}: not a mapping")
                        continue

                    record, aliases = _yaml_to_record(doc)
                    if record is None:
                        errors.append(f"unparseable: {member.name}")
                        continue

                    identifier = record["identifier"]
                    current_ids.add(identifier)

                    existing = await cache.get_standard(identifier)
                    if existing is None:
                        added += 1
                    elif _record_changed(existing, record):
                        updated += 1
                    else:
                        unchanged += 1

                    await cache.set_standard(
                        identifier, record, source=self.body, synced=True
                    )
                    for alias in aliases:
                        await cache.set_standard_alias(alias, identifier)

        logger.info(
            "sync_relaton_done body=%s sha=%s added=%s updated=%s unchanged=%s errors=%s",
            self.body,
            sha,
            added,
            updated,
            unchanged,
            len(errors),
        )

        # Withdrawal detection — guarded against partial-tarball disasters.
        # prev_ids was snapshotted BEFORE the extraction loop so the denominator
        # reflects the prior state (not the post-insertion state).
        withdrawn = 0
        missing = prev_ids - current_ids
        if prev_ids and len(missing) > 0.5 * len(prev_ids):
            errors.append(
                f"withdrawal pass aborted: {len(missing)}/{len(prev_ids)} ids "
                "missing (>50% — likely partial sync)"
            )
            logger.warning(
                "sync_relaton_withdrawal_aborted body=%s missing=%s prev=%s",
                self.body,
                len(missing),
                len(prev_ids),
            )
        else:
            for ident in missing:
                existing = await cache.get_standard(ident)
                if existing is None:
                    continue
                updated_record = cast(
                    "StandardRecord", {**existing, "status": "withdrawn"}
                )
                await cache.set_standard(
                    ident, updated_record, source=self.body, synced=True
                )
                withdrawn += 1
            if withdrawn:
                logger.info(
                    "sync_relaton_withdrawn body=%s count=%s",
                    self.body,
                    withdrawn,
                )

        return SyncReport(
            body=self.body,
            added=added,
            updated=updated,
            unchanged=unchanged,
            withdrawn=withdrawn,
            errors=errors,
            upstream_ref=sha,
            started_at=started_at,
            finished_at=time.time(),
        )

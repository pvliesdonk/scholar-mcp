"""Relaton YAML → StandardRecord mapper and loader.

Shared between the ISO and IEC sync loaders; the joint-standard detection
logic lives in :func:`_canonical_identifier_and_body`.

Design reference: ``docs/design/history/specs/2026-04-13-pr2-iso-iec-relaton-design.md``.
External behaviour: ``docs/design/reference/relaton-data-v2.md`` (the ``v2``
branch and its record shape) and ``docs/design/reference/relaton-titles.md``
(the title list).
"""

from __future__ import annotations

import asyncio
import logging
import re
import tarfile
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, BinaryIO, cast

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

    body: str  # "ISO", "IEC", or "IEEE"
    repo: str  # "relaton/relaton-data-iso"
    # ``main`` stopped receiving data when the repositories moved to ``v2``
    # (#641); ``docs/design/reference/relaton-data-v2.md``.
    branch: str = "v2"


_RELATON_BODIES: dict[str, RelatonConfig] = {
    "ISO": RelatonConfig(body="ISO", repo="relaton/relaton-data-iso"),
    "IEC": RelatonConfig(body="IEC", repo="relaton/relaton-data-iec"),
    "IEEE": RelatonConfig(body="IEEE", repo="relaton/relaton-data-ieee"),
}

# Per-body denylist of upstream slugs that another loader owns. The CC
# loader (see _sync_cc.py) writes ISO/IEC 15408 and ISO/IEC 18045 records
# directly so it can attach the freely-downloadable CC PDF as full_text_url
# (the relaton-data-iso versions describe the same content but inherit
# ISO's paywall). The slug here is the lowercase-hyphen form derived from
# the YAML filename inside the tarball.
_RELATON_SKIP_SLUGS: dict[str, frozenset[str]] = {
    "ISO": frozenset(
        {
            "iso-iec-15408-1-2022",
            "iso-iec-15408-2-2022",
            "iso-iec-15408-3-2022",
            "iso-iec-15408-1-2009",
            "iso-iec-15408-2-2008",
            "iso-iec-15408-3-2008",
            "iso-iec-18045-2022",
            "iso-iec-18045-2008",
        }
    ),
}

# ISO and IEC write the harmonized stage code ``NN.NN``; IEEE writes a word,
# or nothing and leaves the state to ``ext.standard_status``.
_HARMONIZED_STAGE = re.compile(r"\d\d\.\d\d")
_STAGE_WORD_TO_STATUS = {
    "draft": "draft",
    "approved": "published",
    "published": "published",
    "withdrawn": "withdrawn",
    "superseded": "superseded",
}
_IEEE_STANDARD_STATUS = {
    "Active": "published",
    "Inactive": "withdrawn",
    "Superseded": "superseded",
}
# IEC names why an edition was withdrawn; these two mean a new edition.
_IEC_REPLACED_STAGENAMES = frozenset({"REVISED", "REPLACED"})


def _canonical_identifier_and_body(
    docidentifiers: list[dict[str, Any]],
) -> tuple[str, str] | None:
    """Return ``(identifier, body)`` for a Relaton doc, or ``None`` if unknown.

    Joint detection rules (checked in order of specificity):

    - ISO + IEC + IEEE types present → ``body="ISO/IEC/IEEE"``
    - IEC + IEEE types present (no ISO) → ``body="IEC/IEEE"``
    - ISO + IEC types present (no IEEE) → ``body="ISO/IEC"``
    - IEEE-only → ``body="IEEE"``
    - ISO-only / IEC-only → respective body
    - Otherwise fall back to the primary entry's ``type``.

    Entries with ``scope: trademark`` are filtered out before picking the
    canonical identifier (they hold a ™ variant of the same id). Each entry
    holds its identifier under ``content``.
    """
    if not docidentifiers:
        return None

    def _is_trademark(entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        return str(entry.get("scope", "")).lower() == "trademark"

    non_tm = [d for d in docidentifiers if isinstance(d, dict) and not _is_trademark(d)]
    if not non_tm:
        return None

    iso_entries = [d for d in non_tm if str(d.get("type", "")).upper() == "ISO"]
    iec_entries = [d for d in non_tm if str(d.get("type", "")).upper() == "IEC"]
    ieee_entries = [d for d in non_tm if str(d.get("type", "")).upper() == "IEEE"]

    if iso_entries and iec_entries and ieee_entries:
        ident = str(ieee_entries[0].get("content", "")).strip()
        ident = _normalise_joint(ident, "ISO/IEC/IEEE")
        return ident, "ISO/IEC/IEEE"

    if iec_entries and ieee_entries:
        ident = str(ieee_entries[0].get("content", "")).strip()
        ident = _normalise_joint(ident, "IEC/IEEE")
        return ident, "IEC/IEEE"

    if iso_entries and iec_entries:
        joint = next(
            (
                d
                for d in iso_entries + iec_entries
                if "ISO/IEC" in str(d.get("content", ""))
                or "IEC/ISO" in str(d.get("content", ""))
            ),
            iso_entries[0],
        )
        ident = str(joint.get("content", "")).strip()
        ident = _normalise_joint(ident, "ISO/IEC")
        return ident, "ISO/IEC"

    if ieee_entries:
        return str(ieee_entries[0].get("content", "")).strip(), "IEEE"
    if iso_entries:
        return str(iso_entries[0].get("content", "")).strip(), "ISO"
    if iec_entries:
        return str(iec_entries[0].get("content", "")).strip(), "IEC"

    primary_entries = [d for d in non_tm if d.get("primary")]
    if primary_entries:
        ident = str(primary_entries[0].get("content", "")).strip()
        body = str(primary_entries[0].get("type", "")).upper()
        if ident and body:
            return ident, body
    return None


def _normalise_joint(ident: str, joint_prefix: str) -> str:
    """Rewrite *ident* so it starts with *joint_prefix*.

    Handles upstream shapes like ``ISO 42010:2011`` (IEEE entry uses ISO
    prefix) or ``IEC/ISO 27001:2022`` (reversed slash order).
    """
    if ident.startswith(joint_prefix):
        return ident
    ident = ident.replace("IEC/ISO", "ISO/IEC")
    ident = ident.replace("IEEE/IEC", "IEC/IEEE")
    ident = ident.replace("IEEE/ISO/IEC", "ISO/IEC/IEEE")
    if ident.startswith(joint_prefix):
        return ident
    for prefix in ("ISO/IEC/IEEE ", "IEC/IEEE ", "ISO/IEC ", "IEEE ", "IEC ", "ISO "):
        if ident.startswith(prefix):
            return f"{joint_prefix} {ident[len(prefix) :]}"
    return f"{joint_prefix} {ident}"


def _first_link_of_type(links: list[dict[str, Any]] | None, wanted: str) -> str | None:
    if not links:
        return None
    for link in links:
        if not isinstance(link, dict):
            continue
        if str(link.get("type", "")).lower() == wanted:
            content = link.get("content")
            if isinstance(content, str) and content:
                return content
    return None


def _title_content(entry: Any) -> str:
    """Return a title entry's text: a bare string, or a mapping's ``content``."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        content = entry.get("content")
        if isinstance(content, str):
            return content
    return ""


def _is_english(entry: dict[str, Any]) -> bool:
    """Whether a title entry is in English.

    ``language`` is a list in relaton-data-iso, a bare string in
    relaton-data-iec and null in relaton-data-ieee.
    """
    language = entry.get("language")
    if isinstance(language, str):
        return language == "en"
    return isinstance(language, list) and "en" in language


def _full_title(titles: list[Any] | None) -> str:
    """Return the full title from a Relaton ``title`` list.

    Relaton lists a title's parts (``title-intro``, ``title-main``,
    ``title-part``) beside the composed ``main`` title, once per language. The
    intro alone is shared by whole series, so taking the first entry gave
    ISO/IEC 27001 and 27002 the same title (#480). Prefers the English
    ``main``, then any ``main``, then the first entry.

    See ``docs/design/reference/relaton-titles.md``.

    Args:
        titles: The document's ``title`` list.

    Returns:
        The title text, or ``""`` when there is none.
    """
    if not titles:
        return ""
    mains = [t for t in titles if isinstance(t, dict) and t.get("type") == "main"]
    for entry in [t for t in mains if _is_english(t)] + mains:
        if content := _title_content(entry):
            return content
    return _title_content(titles[0])


def _content(value: Any) -> str:
    """Return a Relaton ``{content: ...}`` mapping's text, or ``""``."""
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content.strip()
    return ""


def _published_date(dates: list[dict[str, Any]] | None) -> str | None:
    if not dates:
        return None
    for entry in dates:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type", "")).lower() == "published":
            value = entry.get("at")
            if isinstance(value, str):
                return value
    return None


def _related_identifiers(
    relations: list[dict[str, Any]] | None, relation_type: str
) -> list[str]:
    """Return the identifier of each related document of one type, in order.

    v2 writes the type in camel case (``obsoletedBy``, ``obsoletes``) and
    gives each related bibitem one identifier, the primary one.

    Args:
        relations: The record's ``relation`` list, or None.
        relation_type: The relation type to collect, as v2 spells it.

    Returns:
        Each related identifier once, in first-seen order; empty when there
        is none. IEEE repeats a relation (``IEEE Std 776-1992`` names
        ``IEEE Std 776-2018`` twice).
    """
    found: list[str] = []
    for rel in relations or []:
        if not isinstance(rel, dict) or rel.get("type") != relation_type:
            continue
        bibitem = rel.get("bibitem")
        if not isinstance(bibitem, dict):
            continue
        ident = next(
            (c for c in map(_content, bibitem.get("docidentifier") or []) if c), None
        )
        if ident is not None and ident not in found:
            found.append(ident)
    return found


def _harmonized_status(code: str) -> str:
    """Map an ISO/IEC harmonized stage code (``NN.NN``) to a record status.

    60.60 and every 90 code are a published edition; 95.99 and 95.60 a
    withdrawn one. Below 60.60 the document is a draft, unless the substage
    is 98, which ends the project.
    """
    major, substage = code.split(".")
    if code in ("95.99", "95.60"):
        return "withdrawn"
    if code == "60.60" or major in ("90", "95"):
        return "published"
    if substage == "98":
        return "withdrawn"
    return "draft"


def _status(doc: dict[str, Any], identifier: str) -> str:
    """Return the record status from the stage, before any replacement.

    See ``docs/design/reference/relaton-data-v2.md`` for each body's stage.

    Args:
        doc: Parsed Relaton YAML.
        identifier: The record's identifier, for the log line only.

    Returns:
        ``published``, ``withdrawn``, ``superseded`` or ``draft``.
    """
    stage_block = doc.get("status") or {}
    ext = doc.get("ext") or {}
    stage = _content(stage_block.get("stage"))
    substage = _content(stage_block.get("substage"))
    code = f"{stage}.{substage}" if substage else stage
    if _HARMONIZED_STAGE.fullmatch(code):
        status = _harmonized_status(code)
        replaced = _content(ext.get("stagename")) in _IEC_REPLACED_STAGENAMES
        return "superseded" if status == "withdrawn" and replaced else status
    if stage.lower() in _STAGE_WORD_TO_STATUS:
        return _STAGE_WORD_TO_STATUS[stage.lower()]
    standard_status = ext.get("standard_status")
    if standard_status in _IEEE_STANDARD_STATUS:
        return _IEEE_STANDARD_STATUS[standard_status]
    logger.debug("relaton_unknown_stage stage=%s identifier=%s", code, identifier)
    return "published"


def _committee(contributors: list[dict[str, Any]] | None) -> str | None:
    """Return the committee that authored the document, or None.

    v2 lists it as a ``subdivision`` of the author organisation. ISO names
    the committee in its ``identifier`` (``ISO/IEC JTC 1/SC 27``); IEC puts
    only the number there and ``TC 65`` in the name; IEEE gives only a name.
    """
    for contributor in contributors or []:
        if not isinstance(contributor, dict):
            continue
        roles = [
            r.get("type") for r in contributor.get("role") or [] if isinstance(r, dict)
        ]
        if "author" not in roles:
            continue
        organization = contributor.get("organization") or {}
        for subdivision in organization.get("subdivision") or []:
            if not isinstance(subdivision, dict):
                continue
            ident = next(map(_content, subdivision.get("identifier") or []), "")
            if any(ch.isalpha() for ch in ident):
                return ident
            name = next(map(_content, subdivision.get("name") or []), "")
            if name:
                return name
    return None


def _aliases(docidentifiers: list[Any], identifier: str) -> list[str]:
    """Return every other identifier of the record, except the undated one.

    ISO gives each edition an ``iso-undated`` entry (``ISO/IEC 27001``); as an
    alias it would point at whichever edition the sync wrote last.
    """
    aliases: list[str] = []
    for entry in docidentifiers:
        if not isinstance(entry, dict) or entry.get("type") == "iso-undated":
            continue
        alias = _content(entry)
        if alias and alias != identifier:
            aliases.append(alias)
    return aliases


def _yaml_to_record(
    doc: dict[str, Any],
) -> tuple[StandardRecord | None, list[str]]:
    """Map a parsed Relaton v2 YAML document to ``(StandardRecord, aliases)``.

    Returns ``(None, [])`` on schema mismatches that prevent extracting an
    identifier or title. Callers treat the missing record as a non-fatal
    skip and append an error message for the report.

    A withdrawn record that names its replacement (``obsoletedBy``) reports
    ``superseded`` and lists it. A record that is still current keeps an
    empty ``superseded_by``, although ISO links a confirmed edition to the
    draft of its revision.

    Args:
        doc: Parsed Relaton YAML.

    Returns:
        Tuple of ``(StandardRecord | None, alias_identifiers)``.
    """
    docidentifiers = doc.get("docidentifier") or []
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

    title = _full_title(doc.get("title"))
    if not title:
        logger.debug(
            "relaton_yaml_skip reason=%s identifier=%s", "no_title", identifier
        )
        return None, []

    status = _status(doc, identifier)
    superseded_by: list[str] = []
    if status in ("withdrawn", "superseded"):
        superseded_by = _related_identifiers(doc.get("relation"), "obsoletedBy")
        if superseded_by:
            status = "superseded"

    sources = doc.get("source")
    url = _first_link_of_type(sources, "src") or ""
    full_text_url = _first_link_of_type(sources, "obp") or _first_link_of_type(
        sources, "pub"
    )

    scope_value: str | None = None
    abstracts = doc.get("abstract") or []
    if abstracts:
        scope_value = _content(abstracts[0]) or None

    record: StandardRecord = {
        "identifier": identifier,
        "title": title,
        "body": body,
        "status": status,
        "published_date": _published_date(doc.get("date")),
        "superseded_by": superseded_by,
        "supersedes": _related_identifiers(doc.get("relation"), "obsoletes"),
        "scope": scope_value,
        "committee": _committee(doc.get("contributor")),
        "url": url,
        "full_text_url": full_text_url,
        "full_text_available": False,
        "price": None,
        "related": [],
    }
    return record, _aliases(docidentifiers, identifier)


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


def _parse_tarball_sync(
    fileobj: BinaryIO,
    body: str,
    skip_slugs: frozenset[str],
) -> tuple[list[tuple[str, StandardRecord, list[str]]], list[str]]:
    """Parse a Relaton .tar.gz and return (records, errors).

    Runs synchronously so callers can hand it to ``asyncio.to_thread()``
    to avoid blocking the event loop during CPU-bound tarfile + YAML work.

    Args:
        fileobj: Seeked-to-zero file object containing the .tar.gz bytes.
        body: Standards body key, used only for debug logging.
        skip_slugs: Slug denylist for this body (slugs owned by another loader).

    Returns:
        Tuple of ``(records, errors)`` where each record is
        ``(identifier, StandardRecord, aliases)``.
    """
    records: list[tuple[str, StandardRecord, list[str]]] = []
    errors: list[str] = []
    _LOG_EVERY = 2000

    with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            if not member.name.endswith(".yaml"):
                continue
            # IEC's data/projects/ holds work items, not publications.
            if "/data/" not in member.name or "/data/projects/" in member.name:
                continue

            slug = member.name.rsplit("/", 1)[-1].removesuffix(".yaml")
            if slug in skip_slugs:
                logger.debug(
                    "sync_relaton_skip_owned_by_other body=%s slug=%s", body, slug
                )
                continue

            handle = tar.extractfile(member)
            if (
                handle is None
            ):  # pragma: no cover — only non-regular members, already filtered
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

            # _yaml_to_record guarantees identifier is set when it returns non-None
            records.append((cast("str", record.get("identifier")), record, aliases))

            if len(records) % _LOG_EVERY == 0:
                logger.info(
                    "sync_relaton_parsing body=%s parsed=%s", body, len(records)
                )

    return records, errors


class RelatonLoader:
    """One instance per body (ISO, IEC, or IEEE). Conforms to the Loader protocol.

    The full sync algorithm is documented in
    ``docs/design/history/specs/2026-04-13-pr2-iso-iec-relaton-design.md``.
    Since #641 it reads the ``v2`` branch and deletes, rather than
    withdraws, the identifiers a dump stops listing; see
    ``docs/design/reference/relaton-data-v2.md``.
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

        # Snapshot prev_ids BEFORE the tarball loop so the removal pass
        # compares against the prior state, not the post-insertion state.
        prev_ids = await cache.list_synced_standard_ids(source=self.body)

        tar_url = f"{_GITHUB_API}/repos/{self._config.repo}/tarball/{sha}"
        logger.info("sync_relaton_downloading body=%s sha=%s", self.body, sha)
        with tempfile.TemporaryFile(suffix=".tar.gz") as tmp:
            async with self._http.stream(
                "GET", tar_url, headers=self._headers(), follow_redirects=True
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=1 << 20):
                    tmp.write(chunk)
            tmp.seek(0)
            # CPU-bound tarfile + YAML parsing runs in a thread pool so the
            # event loop stays responsive during the multi-second extraction.
            logger.info("sync_relaton_parsing_start body=%s", self.body)
            parsed, parse_errors = await asyncio.to_thread(
                _parse_tarball_sync,
                tmp,
                self.body,
                _RELATON_SKIP_SLUGS.get(self.body, frozenset()),
            )
        errors.extend(
            parse_errors
        )  # parsed is a fully-materialised list; tmp is now closed
        logger.info(
            "sync_relaton_parsed body=%s records=%s errors=%s",
            self.body,
            len(parsed),
            len(errors),
        )

        # Change detection: reads only (no writes yet).
        # Track records seen within this tarball to handle within-batch
        # duplicates (e.g. trademark vs plain variants mapping to the same id).
        # Keyed dicts ensure only the final winning value per identifier/alias
        # is sent to the batch write — no redundant INSERT OR REPLACE pairs.
        in_current_batch: dict[str, StandardRecord] = {}
        unique_aliases: dict[str, str] = {}

        for identifier, record, aliases in parsed:
            current_ids.add(identifier)

            if identifier in in_current_batch:
                # Within-tarball duplicate (e.g. trademark variant followed by
                # plain variant for the same canonical id).
                if _record_changed(in_current_batch[identifier], record):
                    updated += 1
                else:
                    unchanged += 1
            else:
                existing = await cache.get_standard(identifier)
                if existing is None:
                    added += 1
                elif _record_changed(existing, record):
                    updated += 1
                else:
                    unchanged += 1

            in_current_batch[identifier] = record
            for alias in aliases:
                unique_aliases[alias] = identifier

        # Batch-write all records and aliases in a single transaction each.
        logger.info(
            "sync_relaton_writing body=%s records=%s aliases=%s",
            self.body,
            len(in_current_batch),
            len(unique_aliases),
        )
        await cache.set_standards_batch(
            list(in_current_batch.items()), source=self.body, synced=True
        )
        await cache.set_standard_aliases_batch(list(unique_aliases.items()))

        logger.info(
            "sync_relaton_done body=%s sha=%s added=%s updated=%s unchanged=%s errors=%s",
            self.body,
            sha,
            added,
            updated,
            unchanged,
            len(errors),
        )

        removed = await self._remove_missing(cache, prev_ids, current_ids, errors)

        return SyncReport(
            body=self.body,
            added=added,
            updated=updated,
            unchanged=unchanged,
            withdrawn=0,
            errors=errors,
            removed=removed,
            upstream_ref=sha,
            started_at=started_at,
            finished_at=time.time(),
        )

    async def _remove_missing(
        self,
        cache: CacheProtocol,
        prev_ids: set[str],
        current_ids: set[str],
        errors: list[str],
    ) -> int:
        """Delete the synced rows this run's dump no longer lists.

        v2 keeps a withdrawn edition in the dump at stage 95.99, so an
        identifier that disappears was renamed or advanced from draft, not
        withdrawn. Refuses when the dump holds under half the previous count,
        which a truncated download would.

        Args:
            cache: Open cache.
            prev_ids: Synced identifiers of this body before the run.
            current_ids: Identifiers parsed from this run's dump.
            errors: The report's error list; a refusal is appended to it.

        Returns:
            How many rows were deleted.
        """
        missing = prev_ids - current_ids
        if not missing:
            return 0
        if len(current_ids) < 0.5 * len(prev_ids):
            errors.append(
                f"removal pass aborted: dump lists {len(current_ids)} ids, "
                f"under half of the {len(prev_ids)} synced before"
            )
            logger.warning(
                "sync_relaton_removal_aborted body=%s current=%s prev=%s",
                self.body,
                len(current_ids),
                len(prev_ids),
            )
            return 0
        removed = await cache.delete_synced_standards(self.body, sorted(missing))
        logger.info("sync_relaton_removed body=%s count=%s", self.body, removed)
        return removed

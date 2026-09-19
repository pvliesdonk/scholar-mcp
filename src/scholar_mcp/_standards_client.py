"""Standards lookup client: identifier resolver, source fetchers, StandardsClient."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from xml.etree import ElementTree as ET

import httpx

from ._protocols import CacheProtocol
from ._rate_limiter import RateLimiter
from ._record_types import StandardRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns for local identifier resolution
# ---------------------------------------------------------------------------

# IETF RFC: "RFC 9000", "rfc9000", "rfc-9000", "RFC9000"
_IETF_RFC_RE = re.compile(r"(?i)\brfc[-\s]?(\d+)\b")
# IETF BCP: "BCP 47", "BCP47"
_IETF_BCP_RE = re.compile(r"(?i)\bbcp[-\s]?(\d+)\b")
# IETF STD: "STD 66", "STD66"
_IETF_STD_RE = re.compile(r"(?i)\bstd[-\s]?(\d+)\b")

# NIST SP with optional revision: "SP 800-53 Rev. 5", "SP800-53r5", "NIST SP 800-53 Rev 5"
_NIST_SP_REV_RE = re.compile(
    r"(?i)\b(?:nist\s+)?sp\s*(\d{3,4}(?:-\d+)?[A-Z]?)\s*r(?:ev\.?\s*)?(\d)\b"
)
# NIST SP without revision: "NIST SP 800-53", "SP800-53", "nist 800-53"
_NIST_SP_RE = re.compile(r"(?i)\b(?:nist\s+)?sp\s*(\d{3,4}(?:-\d+)?[A-Z]?)\b")
# NIST SP shorthand: "nist 800-53 rev 5" (number only after "nist")
_NIST_NUM_REV_RE = re.compile(r"(?i)\bnist\s+(\d{3,4}(?:-\d+)?)\s+r(?:ev\.?\s*)?(\d)\b")
_NIST_NUM_RE = re.compile(r"(?i)\bnist\s+(\d{3,4}(?:-\d+)?)\b")
# NIST FIPS: "FIPS 140-3", "FIPS140-3", "FIPS PUB 140-3"
_NIST_FIPS_RE = re.compile(r"(?i)\bfips(?:\s+pub)?\s*(\d{1,3}(?:-\d+)?)\b")
# NIST IR: "NISTIR 8259A", "NISTIR8259A"
_NIST_IR_RE = re.compile(r"(?i)\bnistir\s*(\d{4}[A-Z]?)\b")

# W3C: "WCAG 2.1", "WCAG2.1", "W3C WCAG 2.1", "WebAuthn Level 2"
_W3C_WCAG_RE = re.compile(r"(?i)\bwcag\s*(\d+\.\d+)\b")
_W3C_WEBAUTHN_RE = re.compile(r"(?i)\bwebauthn\s+level\s+(\d+)\b")

# ETSI: "ETSI EN 303 645", "etsi en 303645", "ETSI TS 102 165"
# Require explicit "etsi" prefix to avoid false positives with other European bodies (CEN, CENELEC)
_ETSI_RE = re.compile(
    r"(?i)\betsi\s+(EN|TS|TR|ES|EG)\s*(\d{3})\s*[\s-]?\s*(\d{3}(?:-\d+)?)\b"
)

# CEN/CENELEC: European Norm identifiers.
# Checked AFTER ETSI (which requires explicit "ETSI" prefix) to avoid
# "ETSI EN 303 645" matching the generic EN pattern.
# Order: EN ISO/IEC > EN ISO > EN IEC > plain EN (most-specific first).
_EN_ISO_IEC_RE = re.compile(
    r"(?i)\bEN\s+ISO/IEC\s+(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b"
)
_EN_ISO_RE = re.compile(r"(?i)\bEN\s+ISO\s+(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
_EN_IEC_RE = re.compile(r"(?i)\bEN\s+IEC\s+(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
_EN_RE = re.compile(
    r"(?i)\bEN\s+"
    r"("
    r"\d{3}\s+\d{3}(?:-\d+)?"  # ETSI 3-part: 300 328, 301 489-17
    r"|\d{1,5}(?:-\d+)*(?:\.\d+)*"  # plain: 55032, 61000-3-2
    r")"
    r"(?:\s+V[\d.]+)?"  # optional version: V2.2.2
    r"\s*[:\s-]\s*(\d{4})\b"
)

# IEEE triple-joint with ISO and IEC (must precede other IEEE and joint patterns):
#   "ISO/IEC/IEEE 42010-2011", "ISO/IEC/IEEE 42010:2011"
_ISO_IEC_IEEE_JOINT_RE = re.compile(
    r"(?i)\biso[/\s]*iec[/\s]*ieee\s*"
    r"(\d{1,5}(?:-\d+)*(?:\.\d+)*)\s*[:\s-]\s*(\d{4})\b"
)
# IEEE joint with IEC (must precede plain IEEE and the ISO/IEC joint):
#   "IEC/IEEE 61588-2021", "IEEE/IEC 61588-2021"
_IEC_IEEE_JOINT_RE = re.compile(
    r"(?i)\b(?:iec[/\s]*ieee|ieee[/\s]*iec)\s*"
    r"(\d{1,5}(?:-\d+)*(?:\.\d+)*)\s*[:\s-]\s*(\d{4})\b"
)
# ISO joint with IEC (must precede plain ISO and plain IEC):
#   "ISO/IEC 27001:2022", "ISO IEC 27001:2022", "IEC/ISO 27001:2022"
_ISO_IEC_JOINT_RE = re.compile(
    r"(?i)\b(?:iso[/\s]*iec|iec[/\s]*iso)\s*"
    r"(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b"
)
# ISO alone: "ISO 9001:2015", "ISO9001:2015", "iso 15189-2:2022"
_ISO_RE = re.compile(r"(?i)\biso\s*(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
# IEC alone: "IEC 62443-3-3:2020"
_IEC_RE = re.compile(r"(?i)\biec\s*(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
# IEEE alone (with optional 'Std' token):
#   "IEEE 802.11-2020", "IEEE Std 1588-2019", "IEEE 1003.1-2024"
_IEEE_RE = re.compile(
    r"(?i)\bieee(?:\s+std)?\s+"
    r"(\d{1,5}(?:-\d+)*(?:\.\d+)*)\s*[-\s]\s*(\d{4})\b"
)

# CC version: "CC:2022", "CC 2022", "Common Criteria 2022"
_CC_VERSION_RE = re.compile(
    r"(?i)\b(?:cc|common\s+criteria)[:\s]\s*(\d{4})\b(?!\s+part)"
)
# CC with part: "CC:2022 Part 1", "Common Criteria 2022 Part 1"
_CC_PART_RE = re.compile(
    r"(?i)\b(?:cc|common\s+criteria)[:\s]\s*(\d{4})\s+part\s+(\d)\b"
)
# CC 3.1 Revision: "CC 3.1 R5", "CC 3.1 Revision 5", "Common Criteria 3.1 R5"
_CC_REV_RE = re.compile(
    r"(?i)\b(?:cc|common\s+criteria)\s+3\.1\s+r(?:ev(?:ision)?\.?)?\s*(\d)\b"
)
# CEM: "CEM:2022", "Common Evaluation Methodology 2022"
_CEM_RE = re.compile(
    r"(?i)\b(?:cem|common\s+evaluation\s+methodology)[:\s]\s*(\d{4})\b"
)
# CC Protection Profile schemes (BSI, KECS, ANSSI, NIAP, CCN)
_CC_PP_RE = re.compile(
    r"\b("
    r"BSI-CC-PP-\d+(?:-V\d+)?-\d{4}"
    r"|KECS-PP-\d+-\d{4}"
    r"|ANSSI-CC-PP-\d{4}/\d+"
    r"|CCN-PP-\d+-\d{4}"
    r"|NIAP-PP-[A-Za-z0-9_-]+"
    r"|PP_[A-Za-z0-9_]+_v\d+(?:\.\d+)*"
    r")\b"
)


def resolve_identifier_local(raw: str) -> tuple[str, str] | None:
    """Attempt to resolve *raw* to (canonical_identifier, body) using only regex.

    Returns ``None`` when no Tier 1 pattern matches.

    Args:
        raw: Raw citation string from a paper reference.

    Returns:
        Tuple of (canonical_identifier, body) or None.
    """
    s = raw.strip()

    # CC Protection Profile (very specific scheme prefix — check first)
    m = _CC_PP_RE.search(s)
    if m:
        return m.group(1), "CC"

    # CC with part: "CC:2022 Part 1" / "Common Criteria 2022 Part 1"
    m = _CC_PART_RE.search(s)
    if m:
        return f"CC:{m.group(1)} Part {m.group(2)}", "CC"

    # CC 3.1 Revision: "CC 3.1 R5" / "CC 3.1 Revision 5"
    m = _CC_REV_RE.search(s)
    if m:
        return "CC:2017 Part 1", "CC"

    # CEM: "CEM:2022" / "Common Evaluation Methodology 2022"
    m = _CEM_RE.search(s)
    if m:
        return f"CEM:{m.group(1)}", "CC"

    # CC version only: "CC:2022" / "Common Criteria 2022"
    m = _CC_VERSION_RE.search(s)
    if m:
        return f"CC:{m.group(1)}", "CC"

    # IEEE patterns (check before IETF STD to prevent "IEEE Std X" from matching _IETF_STD_RE)
    # ISO/IEC/IEEE triple-joint (must precede other IEEE joints and plain IEEE)
    m = _ISO_IEC_IEEE_JOINT_RE.search(s)
    if m:
        return f"ISO/IEC/IEEE {m.group(1)}-{m.group(2)}", "IEEE"

    # IEC/IEEE joint (precedes plain IEEE and the plain ISO/IEC joint)
    m = _IEC_IEEE_JOINT_RE.search(s)
    if m:
        return f"IEC/IEEE {m.group(1)}-{m.group(2)}", "IEEE"

    # IEEE alone (must come before IETF STD check to prevent "IEEE Std X" from matching STD)
    m = _IEEE_RE.search(s)
    if m:
        return f"IEEE {m.group(1)}-{m.group(2)}", "IEEE"

    # IETF RFC (check before NIST to avoid "RFC" matching NIST patterns)
    m = _IETF_RFC_RE.search(s)
    if m:
        return f"RFC {int(m.group(1))}", "IETF"

    # IETF BCP
    m = _IETF_BCP_RE.search(s)
    if m:
        return f"BCP {int(m.group(1))}", "IETF"

    # IETF STD
    m = _IETF_STD_RE.search(s)
    if m:
        return f"STD {int(m.group(1))}", "IETF"

    # NIST FIPS
    m = _NIST_FIPS_RE.search(s)
    if m:
        return f"FIPS {m.group(1)}", "NIST"

    # NIST IR
    m = _NIST_IR_RE.search(s)
    if m:
        return f"NISTIR {m.group(1).upper()}", "NIST"

    # NIST SP with revision (must check before without-revision to capture rev)
    m = _NIST_SP_REV_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)} Rev. {m.group(2)}", "NIST"

    # NIST SP without revision
    m = _NIST_SP_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)}", "NIST"

    # NIST shorthand with revision: "nist 800-53 rev 5"
    m = _NIST_NUM_REV_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)} Rev. {m.group(2)}", "NIST"

    # NIST shorthand without revision: "nist 800-53"
    m = _NIST_NUM_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)}", "NIST"

    # W3C WCAG
    m = _W3C_WCAG_RE.search(s)
    if m:
        return f"WCAG {m.group(1)}", "W3C"

    # W3C WebAuthn
    m = _W3C_WEBAUTHN_RE.search(s)
    if m:
        return f"WebAuthn Level {m.group(1)}", "W3C"

    # ETSI
    m = _ETSI_RE.search(s)
    if m:
        return f"ETSI {m.group(1).upper()} {m.group(2)} {m.group(3)}", "ETSI"

    # CEN/CENELEC EN (must come after ETSI to avoid "ETSI EN" collision)
    m = _EN_ISO_IEC_RE.search(s)
    if m:
        return f"EN ISO/IEC {m.group(1)}:{m.group(2)}", "CEN"

    m = _EN_ISO_RE.search(s)
    if m:
        return f"EN ISO {m.group(1)}:{m.group(2)}", "CEN"

    m = _EN_IEC_RE.search(s)
    if m:
        return f"EN IEC {m.group(1)}:{m.group(2)}", "CEN"

    m = _EN_RE.search(s)
    if m:
        return f"EN {m.group(1)}:{m.group(2)}", "CEN"

    # ISO/IEC joint (check before plain ISO and plain IEC)
    m = _ISO_IEC_JOINT_RE.search(s)
    if m:
        return f"ISO/IEC {m.group(1)}:{m.group(2)}", "ISO/IEC"

    # ISO
    m = _ISO_RE.search(s)
    if m:
        return f"ISO {m.group(1)}:{m.group(2)}", "ISO"

    # IEC
    m = _IEC_RE.search(s)
    if m:
        return f"IEC {m.group(1)}:{m.group(2)}", "IEC"

    return None


# ---------------------------------------------------------------------------
# Structural protocol shared by all registered fetchers
# ---------------------------------------------------------------------------


class StandardsUpstreamError(Exception):
    """Raised when a standards source never gave a usable answer.

    ``None`` from ``get`` and ``[]`` from ``search`` mean the source answered
    and holds no such standard. A request that was refused, never arrived, or
    came back in a shape this client cannot read means the opposite, and
    collapsing the two leaves a caller unable to tell "no such standard" from
    "ask again later" (#401).

    Attributes:
        body: The source body that failed, e.g. ``"ETSI"``.
        status: The upstream HTTP status, or ``None`` when the request never
            produced a response.
        detail: What was wrong, phrased for the caller-facing payload. A 200
            carrying HTML needs this: the status alone reads as success.
    """

    def __init__(
        self, body: str, *, status: int | None = None, detail: str = ""
    ) -> None:
        self.body = body
        self.status = status
        self.detail = detail
        super().__init__(f"{body} upstream error: {detail or status}")


@runtime_checkable
class _StandardsFetcher(Protocol):
    """Structural type shared by all body fetchers in StandardsClient.

    Every fetcher registered in ``_fetchers`` must expose both ``.get()``
    and ``.search()``. The Protocol is ``runtime_checkable`` so tests can
    use ``isinstance`` to verify conformance.

    ``None`` from ``get`` and ``[]`` from ``search`` mean the source answered
    and holds no such standard. A fetcher *may* instead raise
    :class:`StandardsUpstreamError` when it never got a usable answer, and
    :class:`StandardsClient` handles both: a failing source is reported
    alongside whatever the others returned, never as an absence. The fetchers
    that still swallow their own upstream failures are tracked in #453.
    """

    async def get(self, identifier: str) -> StandardRecord | None: ...

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]: ...


# ---------------------------------------------------------------------------
# IETF source fetcher
# ---------------------------------------------------------------------------

_IETF_DATATRACKER = "https://datatracker.ietf.org"
_RFC_EDITOR_BASE = "https://www.rfc-editor.org"


class _IETFFetcher:
    """Fetches RFC metadata from the IETF Datatracker REST API.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~0.5s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single IETF document by identifier (RFC, BCP, STD, FYI).

        Args:
            identifier: Canonical IETF identifier (e.g. "RFC 9000", "BCP 47").

        Returns:
            Populated StandardRecord or None if not found.
        """
        m = re.match(r"(?i)(rfc|bcp|std|fyi)\s*(\d+)", identifier)
        if not m:
            return None
        doc_type = m.group(1).lower()
        n = int(m.group(2))
        # Datatracker uses zero-padded names for RFC, bare numbers for BCP/STD/FYI
        name = f"rfc{n:04d}" if doc_type == "rfc" else f"{doc_type}{n}"
        await self._limiter.acquire()
        resp = await self._http.get(
            f"{_IETF_DATATRACKER}/api/v1/doc/document/",
            params={"name": name, "format": "json"},
        )
        if resp.status_code != 200:
            logger.warning(
                "ietf_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return None
        data = resp.json()
        objects = data.get("objects") or []
        if not objects:
            return None
        return _normalize_ietf(objects[0])

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search RFCs by title keyword.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"{_IETF_DATATRACKER}/api/v1/doc/document/",
            params={
                "type": "rfc",
                "title__icontains": query,
                "format": "json",
                "limit": limit,
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "ietf_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return []
        objects = (resp.json().get("objects") or [])[:limit]
        return [_normalize_ietf(obj) for obj in objects]


def _normalize_ietf(obj: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a Datatracker document object to a StandardRecord.

    Args:
        obj: Raw Datatracker ``/api/v1/doc/document/`` object.

    Returns:
        Populated StandardRecord.
    """
    name = obj.get("name", "")  # e.g. "rfc9000"
    n = re.sub(r"[^\d]", "", name)
    is_rfc = bool(re.match(r"(?i)^rfc\d+$", name))
    if is_rfc:
        identifier = f"RFC {int(n)}" if n else name.upper()
    elif n:
        # BCP/STD/FYI: produce "PREFIX NUMBER" to match resolve_identifier_local
        prefix = re.sub(r"\d.*", "", name).upper()
        identifier = f"{prefix} {int(n)}"
    else:
        identifier = name.upper()

    if n:
        # Use the original `name` in the URL so BCP/STD get correct RFC Editor pages
        url = f"{_RFC_EDITOR_BASE}/info/{name}"
        # Only RFCs have a plain-text HTML page; BCP/STD are index pages
        full_text_url: str | None = (
            f"{_RFC_EDITOR_BASE}/rfc/{name}.html" if is_rfc else None
        )
        full_text_available = is_rfc
        number = str(int(n)) if is_rfc else name
    else:
        url = ""
        full_text_url = None
        full_text_available = False
        number = ""

    # Build alias list, excluding the canonical identifier itself
    _raw_aliases = [name, name.upper().replace("RFC", "RFC ")]
    return StandardRecord(
        identifier=identifier,
        aliases=[a for a in _raw_aliases if a != identifier],
        title=obj.get("title", ""),
        body="IETF",
        number=number,
        revision=None,
        status=_map_ietf_status(obj.get("std_level") or ""),
        published_date=obj.get("pub_date"),
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=obj.get("abstract"),
        committee=None,
        url=url,
        full_text_url=full_text_url,
        full_text_available=full_text_available,
        price=None,
        related=[],
    )


def _map_ietf_status(std_level: str | None) -> str:
    """Map IETF std_level to a human-readable status string.

    Args:
        std_level: Datatracker std_level value (may be None when API returns null).

    Returns:
        Status string: "published", "withdrawn", etc.
    """
    mapping = {
        "proposed_standard": "published",
        "draft_standard": "published",
        "internet_standard": "published",
        "informational": "published",
        "experimental": "published",
        "best_current_practice": "published",
        "historic": "withdrawn",
        "unknown": "draft",
        "": "published",
    }
    key = (std_level or "").lower()
    return mapping.get(key, "published")


# ---------------------------------------------------------------------------
# NIST source fetcher
# ---------------------------------------------------------------------------

_NIST_GITHUB_API = "https://api.github.com"
_NIST_MODS_RELEASE_URL = (
    f"{_NIST_GITHUB_API}/repos/usnistgov/NIST-Tech-Pubs/releases/latest"
)
_NIST_MODS_ASSET_NAME = "allrecords-MODS.xml"
_NIST_MODS_NS = "http://www.loc.gov/mods/v3"
_NIST_CACHE_MAX_AGE_DAYS = 90


class _NISTFetcher:
    """Fetches NIST publication metadata from NIST-Tech-Pubs MODS XML releases.

    Downloads the MODS XML catalogue from the latest GitHub release of
    https://github.com/usnistgov/NIST-Tech-Pubs on first use, parses it,
    and caches parsed records to disk as JSON. Subsequent calls within 90 days
    load from disk without network I/O.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter.
        cache_dir: Directory for persistent JSON cache. If None, no disk
            caching is used (data is re-downloaded every process restart).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        cache_dir: Path | None = None,
    ) -> None:
        self._http = http
        self._limiter = limiter
        self._cache_dir = cache_dir
        self._catalogue: list[Any] | None = None
        self._lock = asyncio.Lock()

    def _cache_path(self) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / "nist_catalogue.json"

    def _load_from_disk(self) -> list[Any] | None:
        """Load cached catalogue from disk if it exists and is fresh."""
        path = self._cache_path()
        if path is None or not path.exists():
            return None
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if age_days > _NIST_CACHE_MAX_AGE_DAYS:
            logger.info(
                "nist_catalogue_stale age_days=%.0f threshold=%d — re-downloading",
                age_days,
                _NIST_CACHE_MAX_AGE_DAYS,
            )
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("nist_catalogue_disk_load_failed err=%s", exc)
            return None

    def _save_to_disk(self, records: list[Any]) -> None:
        path = self._cache_path()
        if path is None:
            return
        try:
            path.write_text(json.dumps(records), encoding="utf-8")
            logger.info("nist_catalogue_cached path=%s count=%d", path, len(records))
        except OSError as exc:
            logger.warning("nist_catalogue_disk_save_failed err=%s", exc)

    async def _fetch_mods_url(self) -> str | None:
        """Get the download URL for the latest MODS XML asset from GitHub releases."""
        await self._limiter.acquire()
        resp = await self._http.get(
            _NIST_MODS_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            logger.warning(
                "nist_github_api_error status=%d url=%s",
                resp.status_code,
                str(resp.url),
            )
            return None
        data = resp.json()
        for asset in data.get("assets", []):
            if asset.get("name") == _NIST_MODS_ASSET_NAME:
                # Prefer the GitHub API asset URL (api.github.com) so we can
                # request it with Accept: application/octet-stream and follow
                # the redirect; fall back to browser_download_url.
                return str(asset.get("url") or asset["browser_download_url"])
        logger.warning("nist_mods_asset_not_found release=%s", data.get("tag_name"))
        return None

    async def _fetch_all(self) -> list[Any]:
        """Return parsed NIST catalogue, using disk cache when available."""
        if self._catalogue is not None:
            return self._catalogue
        async with self._lock:
            if self._catalogue is not None:
                return self._catalogue
            cached = self._load_from_disk()
            if cached is not None:
                self._catalogue = cached
                logger.debug("nist_catalogue_loaded_from_disk count=%d", len(cached))
                return self._catalogue

            mods_url = await self._fetch_mods_url()
            if mods_url is None:
                return []

            await self._limiter.acquire()
            resp = await self._http.get(
                mods_url,
                headers={"Accept": "application/octet-stream"},
                follow_redirects=True,
            )
            if resp.status_code != 200:
                logger.warning("nist_mods_download_error status=%d", resp.status_code)
                return []
            records = _parse_nist_mods(resp.content)
            if not records:
                logger.warning("nist_mods_empty_after_parse url=%s", mods_url)
                return []
            logger.info("nist_catalogue_parsed count=%d", len(records))
            self._save_to_disk(records)
            self._catalogue = records
        return self._catalogue

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search NIST publications by keyword in identifier or title.

        Args:
            query: Search string (e.g. "800-53", "FIPS 140").
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        all_pubs = await self._fetch_all()
        q = query.lower()
        matches = [
            p
            for p in all_pubs
            if q in (p.get("identifier") or "").lower()
            or q in (p.get("title") or "").lower()
            or q in (p.get("number") or "").lower()
        ]
        return matches[:limit]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single NIST publication by canonical identifier.

        The match is exact, case-insensitively. It used to also accept either
        string containing the other, which made the catalogue's malformed
        entries contagious: a record whose series partNumber is empty
        normalises to "NIST SP ", a prefix of every other SP identifier, so it
        answered for thousands of unrelated requests (#400). Containment also
        widened a request to a different document -- "NISTIR 8259" to
        "NISTIR 8259PT" -- picking by document order rather than by relevance.

        Callers reach this with an already-canonical identifier from
        ``resolve_identifier_local``, which emits exactly the spelling this
        catalogue uses, so tolerant matching bought nothing. ``search`` is
        where substring matching belongs and still does it.

        Args:
            identifier: Canonical NIST identifier (e.g. "NIST SP 800-53 Rev. 5").

        Returns:
            Populated StandardRecord or None if not found.
        """
        all_pubs = await self._fetch_all()
        id_lower = identifier.lower()
        for pub in all_pubs:
            if (pub.get("identifier") or "").lower() == id_lower:
                return pub  # type: ignore[no-any-return]
        return None


def _parse_nist_mods(xml_bytes: bytes) -> list[StandardRecord]:
    """Parse a NIST-Tech-Pubs MODS XML file into a list of StandardRecords.

    Only records belonging to recognised NIST series (SP, FIPS, NISTIR) are
    returned. Other series (internal reports, white papers without a series
    label) are skipped.

    Args:
        xml_bytes: Raw bytes of allrecords-MODS.xml.

    Returns:
        List of populated StandardRecord dicts.
    """
    ns = f"{{{_NIST_MODS_NS}}}"
    records: list[StandardRecord] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("nist_mods_parse_error err=%s", exc)
        return []

    for mods in root.findall(f"{ns}mods"):
        record = _normalize_nist_mods(mods, ns)
        if record is not None:
            records.append(record)
    return records


def _normalize_nist_mods(mods: ET.Element, ns: str) -> StandardRecord | None:
    """Normalise a single <mods> element to a StandardRecord.

    Args:
        mods: A ``<mods>`` XML element.
        ns: Namespace prefix string, e.g. ``"{http://www.loc.gov/mods/v3}"``.

    Returns:
        Populated StandardRecord or None if the record is not a recognised
        NIST series publication.
    """
    # Series metadata
    series_el = None
    for ri in mods.findall(f"{ns}relatedItem"):
        if ri.get("type") == "series":
            series_el = ri
            break
    if series_el is None:
        return None

    series_title_el = series_el.find(f"{ns}titleInfo/{ns}title")
    part_el = series_el.find(f"{ns}titleInfo/{ns}partNumber")
    series_title = (
        (series_title_el.text or "").lower() if series_title_el is not None else ""
    )
    part_number = part_el.text.strip() if part_el is not None and part_el.text else ""

    if "special publication" in series_title or "nist sp" in series_title:
        body_prefix = "NIST SP"
    elif (
        "nistir" in series_title
        or "interagency" in series_title
        or "internal report" in series_title
    ):
        body_prefix = "NISTIR"
    elif "fips" in series_title:
        body_prefix = "FIPS"
    else:
        return None  # skip unrecognised series

    # partNumber → number + optional revision (e.g. "800-53r5" → "800-53", "5")
    m = re.match(r"^(.*?)r(\d+)$", part_number)
    if m:
        number = m.group(1)
        revision = m.group(2)
    else:
        number = part_number
        revision = None

    # Canonical identifier
    if body_prefix == "NIST SP":
        canonical = f"NIST SP {number}"
        if revision:
            canonical += f" Rev. {revision}"
    elif body_prefix == "NISTIR":
        canonical = f"NISTIR {number.upper()}"
    else:
        canonical = f"FIPS {number}"

    # Title
    title_el = mods.find(f"{ns}titleInfo/{ns}title")
    subtitle_el = mods.find(f"{ns}titleInfo/{ns}subTitle")
    title = (title_el.text or "").strip() if title_el is not None else ""
    if subtitle_el is not None and subtitle_el.text:
        title = f"{title}: {subtitle_el.text.strip()}"

    # Abstract
    abstract_el = mods.find(f"{ns}abstract")
    scope = (
        abstract_el.text.strip()
        if abstract_el is not None and abstract_el.text
        else None
    )

    # URL (primary display location)
    url = ""
    for url_el in mods.findall(f"{ns}location/{ns}url"):
        if url_el.get("usage") == "primary display":
            url = (url_el.text or "").strip()
            break
    if not url:
        url_el_fallback = mods.find(f"{ns}location/{ns}url")
        if url_el_fallback is not None:
            url = (url_el_fallback.text or "").strip()

    # Publication date (strip trailing dot)
    pub_date = None
    for date_el in mods.iter(f"{ns}dateIssued"):
        if date_el.text:
            pub_date = date_el.text.strip().rstrip(".")
            break

    return StandardRecord(
        identifier=canonical,
        aliases=[],
        title=title,
        body="NIST",
        number=number,
        revision=f"Rev. {revision}" if revision else None,
        status="published",
        published_date=pub_date,
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=scope,
        committee=None,
        url=url,
        full_text_url=None,  # MODS URL is a catalogue/DOI page, not a direct PDF link
        full_text_available=False,
        price=None,
        related=[],
    )


# ---------------------------------------------------------------------------
# W3C source fetcher
# ---------------------------------------------------------------------------

_W3C_API = "https://api.w3.org"
_W3C_TR = "https://www.w3.org/TR"

# Map common W3C spec names to their shortname for the API
_W3C_SHORTNAME_MAP: dict[str, str] = {
    "WCAG 2.1": "WCAG21",
    "WCAG 2.2": "WCAG22",
    "WCAG 2.0": "WCAG20",
    "WCAG 3.0": "wcag-3.0",
    "WebAuthn Level 1": "webauthn-1",
    "WebAuthn Level 2": "webauthn-2",
    "HTML5": "html5",
    "HTML Living Standard": "html",
}


class _W3CFetcher:
    """Fetches W3C specification metadata from the W3C API.

    On first search, downloads all specification stubs (paginated, ~1682 total)
    and caches them in memory as ``{shortname, title}`` pairs. Subsequent
    searches filter in-memory without network I/O.  Individual spec fetches
    via ``get()`` always hit the API directly.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~0.5s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter
        self._stubs: list[dict[str, str]] | None = None  # [{shortname, title}]
        self._lock = asyncio.Lock()

    def _to_shortname(self, identifier: str) -> str:
        """Convert a human-readable W3C identifier to an API shortname.

        Args:
            identifier: Human-readable identifier like "WCAG 2.1".

        Returns:
            API shortname like "WCAG21".
        """
        if identifier in _W3C_SHORTNAME_MAP:
            return _W3C_SHORTNAME_MAP[identifier]
        return re.sub(r"[\s.]", "", identifier)

    async def _ensure_stubs(self) -> list[dict[str, str]]:
        """Download all spec stubs (paginated) and cache in memory.

        Returns:
            List of ``{shortname, title}`` dicts.
        """
        if self._stubs is not None:
            return self._stubs
        async with self._lock:
            if self._stubs is not None:
                return self._stubs
            stubs: list[dict[str, str]] = []
            page = 1
            while True:
                await self._limiter.acquire()
                resp = await self._http.get(
                    f"{_W3C_API}/specifications",
                    params={"page": page, "limit": 100},
                )
                if resp.status_code != 200:
                    logger.warning(
                        "w3c_stubs_error status=%d page=%d", resp.status_code, page
                    )
                    break
                data = resp.json()
                page_specs = data.get("_links", {}).get("specifications") or []
                for spec in page_specs:
                    href = spec.get("href", "")
                    shortname = href.rstrip("/").rsplit("/", 1)[-1]
                    title = spec.get("title", "")
                    if shortname:
                        stubs.append({"shortname": shortname, "title": title})
                pages = data.get("pages", 1)
                if page >= pages:
                    break
                page += 1
            self._stubs = stubs
            logger.info("w3c_stubs_cached count=%d", len(stubs))
        return self._stubs

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single W3C specification by identifier.

        Args:
            identifier: Human-readable identifier (e.g. "WCAG 2.1").

        Returns:
            Populated StandardRecord or None if not found.
        """
        shortname = self._to_shortname(identifier)
        await self._limiter.acquire()
        resp = await self._http.get(f"{_W3C_API}/specifications/{shortname}")
        if resp.status_code != 200:
            logger.warning(
                "w3c_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return None
        return _normalize_w3c(resp.json())

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search W3C specifications by keyword against cached stubs.

        Downloads all stubs on first call (paginated). Filters by title
        client-side, then fetches full spec objects for the top matches.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        stubs = await self._ensure_stubs()
        if not stubs:
            return []
        q = query.lower()
        matches = [
            s for s in stubs if q in s["title"].lower() or q in s["shortname"].lower()
        ][:limit]

        results: list[StandardRecord] = []
        for stub in matches:
            await self._limiter.acquire()
            resp = await self._http.get(
                f"{_W3C_API}/specifications/{stub['shortname']}"
            )
            if resp.status_code == 200:
                results.append(_normalize_w3c(resp.json()))
            else:
                logger.debug(
                    "w3c_spec_fetch_failed shortname=%s status=%d",
                    stub["shortname"],
                    resp.status_code,
                )
        return results


def _normalize_w3c(spec: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a W3C API specification object to a StandardRecord.

    Args:
        spec: Raw W3C API specification object.

    Returns:
        Populated StandardRecord.
    """
    title = spec.get("title", "")
    shortname = spec.get("shortname", "")
    latest_url: str | None = (
        spec.get("latest-version")
        or ((spec.get("_links") or {}).get("latest-version", {}).get("href", ""))
        or None
    )
    if not latest_url:
        latest_url = f"{_W3C_TR}/{shortname}/"

    status_raw = (spec.get("latest-status") or spec.get("status") or "").lower()
    if "recommendation" in status_raw:
        status = "published"
    elif "draft" in status_raw or "working" in status_raw:
        status = "draft"
    elif "retired" in status_raw or "superseded" in status_raw:
        status = "superseded"
    else:
        status = "published"

    return StandardRecord(
        identifier=title,
        aliases=[shortname],
        title=title,
        body="W3C",
        number=shortname,
        revision=None,
        status=status,
        published_date=spec.get("published"),
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=spec.get("description"),
        committee=None,
        url=latest_url or f"{_W3C_TR}/{shortname}/",
        full_text_url=latest_url,
        full_text_available=bool(latest_url),
        price=None,
        related=[],
    )


# ---------------------------------------------------------------------------
# ETSI source fetcher (Joomla JSON API)
# ---------------------------------------------------------------------------

_ETSI_BASE = "https://www.etsi.org"
_ETSI_JOOMLA_PARAMS: dict[str, str | int] = {
    "option": "com_standardssearch",
    "view": "data",
    "format": "json",
    "version": "0",
    "published": "1",
    "onApproval": "1",
    "withdrawn": "0",
    "historical": "0",
    "isCurrent": "1",
    "superseded": "0",
    "startDate": "1988-01-15",
    "sort": "1",
    "title": "1",
    "etsiNumber": "1",
    "content": "1",
}


class _ETSIFetcher:
    """Fetches ETSI standard metadata via the ETSI website Joomla JSON endpoint.

    Calls ``https://www.etsi.org/?option=com_standardssearch&view=data&format=json``
    which is the server-side AJAX endpoint backing the ETSI standards search page.

    [observed 2026-09-19] That request now returns ``200`` with
    ``content-type: text/html``. The cause is this client, not ETSI being
    down: ``option=com_standardssearch`` is a Joomla component, and
    ``www.etsi.org`` is served by WordPress today (``wp-admin/admin-ajax.php``,
    ``wp-content``, ``wp-json``). The query string routes nowhere, so the site
    answers with a page. The live standards-search page mentions neither
    ``com_standardssearch`` nor ``format=json``.

    Five request shapes were tried -- plain, ``Accept: application/json``,
    ``X-Requested-With: XMLHttpRequest``, ``Referer``, and a browser
    ``User-Agent`` -- and every one returned the same page, so this is not a
    header or bot-protection problem.

    Which interface replaced it is unestablished: #454. Until then every such
    answer is reported as an upstream failure, which is what it is, rather
    than as an absent standard.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~1s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search ETSI standards by keyword.

        An empty list means ETSI answered and publishes no such standard. Every
        other outcome raises, because a caller that cannot tell those apart
        reports an outage as an absence (#401).

        Args:
            query: Search string (e.g. "303 645", "IoT security").
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.

        Raises:
            StandardsUpstreamError: ETSI refused the request, never received
                it, or answered in a shape this client cannot read.
        """
        await self._limiter.acquire()
        params = {**_ETSI_JOOMLA_PARAMS, "search": query, "page": 1}
        # Each failure keeps logging where the detail is in hand, then raises,
        # so operators see what they saw before and callers get a decision.
        try:
            resp = await self._http.get(f"{_ETSI_BASE}/", params=params)
        except httpx.HTTPError as exc:
            logger.warning("etsi_api_request_failed error=%s", exc)
            raise StandardsUpstreamError(
                "ETSI", detail=f"request never reached ETSI: {exc}"
            ) from exc
        if resp.status_code != 200:
            logger.warning(
                "etsi_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            raise StandardsUpstreamError(
                "ETSI", status=resp.status_code, detail="ETSI refused the request"
            )
        try:
            items: list[dict] = resp.json()  # type: ignore[type-arg]
        except json.JSONDecodeError as exc:
            logger.warning(
                "etsi_api_json_decode_error url=%s err=%s", str(resp.url), exc
            )
            # The observed failure is a 200 carrying the ETSI homepage, so the
            # status says "success" and only the content type explains itself.
            raise StandardsUpstreamError(
                "ETSI",
                status=resp.status_code,
                detail=(
                    "answered with a non-JSON body (content-type: "
                    f"{resp.headers.get('content-type', 'unknown')})"
                ),
            ) from exc
        if not isinstance(items, list):
            logger.warning("etsi_api_unexpected_response type=%s", type(items).__name__)
            raise StandardsUpstreamError(
                "ETSI",
                status=resp.status_code,
                detail=f"expected a JSON array, got {type(items).__name__}",
            )
        return [_normalize_etsi(item) for item in items[:limit]]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single ETSI standard by canonical identifier.

        ``None`` means ETSI answered and holds no such standard. A failure
        propagates from :meth:`search` rather than collapsing into ``None``,
        which would tell the caller to stop asking about a standard that may
        well exist (#401).

        Args:
            identifier: Canonical identifier (e.g. "ETSI EN 303 645").

        Returns:
            Populated StandardRecord, or None when ETSI reports no match.

        Raises:
            StandardsUpstreamError: propagated from :meth:`search`.
        """
        results = await self.search(identifier, limit=1)
        return results[0] if results else None


def _normalize_etsi(item: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a single ETSI Joomla API result item to a StandardRecord.

    Args:
        item: A single dict from the Joomla JSON API response array.

    Returns:
        Populated StandardRecord.
    """
    deliverable = item.get("ETSI_DELIVERABLE", "")
    title = item.get("TITLE", "")
    pathname = item.get("EDSpathname", "")
    pdffile = item.get("EDSPDFfilename", "")
    scope = item.get("Scope") or None
    tb = item.get("TB") or None

    # Canonical identifier: strip trailing version string, e.g.
    # "ETSI EN 303 645 V3.1.3 (2024-09)" → "ETSI EN 303 645"
    # "ETSI TS 102 690-1 V2.0.16 (2013-09)" → "ETSI TS 102 690-1"
    canonical = deliverable.split(" V")[0].strip()

    # Version from deliverable string
    vm = re.search(r"V([\d.]+)\s+\((\d{4}-\d{2})\)", deliverable)
    version = vm.group(1) if vm else None
    pub_date = vm.group(2) if vm else None

    action_type = (item.get("ACTION_TYPE") or "").upper()
    status = "withdrawn" if action_type == "WD" else "published"

    pdf_url: str | None = None
    if pathname and pdffile:
        pdf_url = f"{_ETSI_BASE}/deliver/{pathname}{pdffile}"

    return StandardRecord(
        identifier=canonical,
        aliases=[deliverable] if deliverable != canonical else [],
        title=title,
        body="ETSI",
        number=re.sub(r"^ETSI\s+\w+\s+", "", canonical),
        revision=version,
        status=status,
        published_date=pub_date,
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=scope,
        committee=tb,
        url=pdf_url or f"{_ETSI_BASE}/standards",
        full_text_url=pdf_url,
        full_text_available=pdf_url is not None,
        price=None,
        related=[],
    )


class _CCFetcher:
    """Cache-only fetcher for Common Criteria standards.

    CC has no live API — all records are populated by ``CCLoader`` via
    ``sync-standards --body CC``. This fetcher delegates ``get`` and
    ``search`` to the cache and emits a WARNING on cache miss with the
    sync-command hint so operators see the gap.

    Conforms to the ``_StandardsFetcher`` Protocol.
    """

    def __init__(self, *, cache: CacheProtocol | None = None) -> None:
        """Initialise the fetcher.

        Args:
            cache: Optional cache. When ``None``, ``get`` always returns
                ``None`` and ``search`` returns ``[]``.
        """
        self._cache = cache

    async def get(self, identifier: str) -> StandardRecord | None:
        """Return cached CC record, or ``None`` (with WARNING log)."""
        if self._cache is None:
            logger.warning(
                "cc_cache_miss identifier=%s reason=no_cache_configured",
                identifier,
            )
            return None
        record = await self._cache.get_standard(identifier)
        if record is None:
            logger.warning(
                "cc_cache_miss identifier=%s hint=%s",
                identifier,
                "run sync-standards --body CC",
            )
        return record

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search synced CC records via the cache."""
        if self._cache is None:
            return []
        return await self._cache.search_synced_standards(
            query, source="CC", limit=limit
        )


class _CENFetcher:
    """Cache-only fetcher for CEN/CENELEC harmonised standards.

    CEN has no live API — all records are populated by ``CENLoader`` via
    ``sync-standards --body CEN``. This fetcher delegates ``get`` and
    ``search`` to the cache and emits a WARNING on cache miss.

    Conforms to the ``_StandardsFetcher`` Protocol.
    """

    def __init__(self, *, cache: CacheProtocol | None = None) -> None:
        """Initialise the fetcher.

        Args:
            cache: Optional cache. When ``None``, ``get`` always returns
                ``None`` and ``search`` returns ``[]``.
        """
        self._cache = cache

    async def get(self, identifier: str) -> StandardRecord | None:
        """Return cached CEN record, or ``None`` (with WARNING log)."""
        if self._cache is None:
            logger.warning(
                "cen_cache_miss identifier=%s reason=no_cache_configured",
                identifier,
            )
            return None
        record = await self._cache.get_standard(identifier)
        if record is None:
            logger.warning(
                "cen_cache_miss identifier=%s hint=%s",
                identifier,
                "run sync-standards --body CEN",
            )
        return record

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search synced CEN records via the cache."""
        if self._cache is None:
            return []
        return await self._cache.search_synced_standards(
            query, source="CEN", limit=limit
        )


# ---------------------------------------------------------------------------
# StandardsClient — public orchestrator
# ---------------------------------------------------------------------------


def _collect_search(
    outcomes: list[Any],
    limit: int,
) -> tuple[list[StandardRecord], list[StandardsUpstreamError]]:
    """Split gathered search outcomes into records and reportable failures.

    Merging only the lists is what let an all-bodies search read as complete
    while one body was down (#401), so a source that failed is named here
    rather than dropped.

    Anything that is not a :class:`StandardsUpstreamError` is logged and
    skipped, which is what this loop did silently with every exception before.

    Args:
        outcomes: Results of ``asyncio.gather(..., return_exceptions=True)``.
        limit: Maximum records to return.

    Returns:
        The merged records, capped at ``limit``, and the failures to report.
    """
    merged: list[StandardRecord] = []
    failures: list[StandardsUpstreamError] = []
    for outcome in outcomes:
        if isinstance(outcome, StandardsUpstreamError):
            failures.append(outcome)
        elif isinstance(outcome, BaseException):
            logger.warning(
                "standards_search_fetcher_crashed err=%r", outcome, exc_info=outcome
            )
        elif isinstance(outcome, list):
            # The list check is the one this loop already had. The Protocol
            # and mypy make anything else unreachable, but extending on a
            # non-list would splice a string apart rather than skip it.
            merged.extend(outcome)
    return merged[:limit], failures


class StandardsClient:
    """Unified client for Tier 1 standards sources.

    Routes search and lookup requests to the appropriate source fetcher
    (IETF, NIST, W3C, ETSI) based on the body parameter or identifier prefix.

    All four source fetchers share a single ``httpx.AsyncClient``. ETSI
    maintains an in-memory catalogue index to avoid per-query scraping.

    Args:
        http: Shared httpx async client. Closed by ``aclose()``.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        cache_dir: Path | None = None,
        cache: CacheProtocol | None = None,
    ) -> None:
        from ._relaton_live import RelatonLiveFetcher

        self._http = http
        # Four RelatonLiveFetcher instances (ISO, IEC, IEEE, ISO/IEC) so each
        # body key can carry its own source filter when search() delegates to
        # the cache. The ISO/IEC variant uses source=None to cover
        # joint-committee records and must be listed last so it wins the type
        # dedup in _one_fetcher_per_type() for all-bodies searches.
        self._fetchers: dict[str, _StandardsFetcher] = {
            "IETF": _IETFFetcher(http, RateLimiter(delay=0.5)),
            "NIST": _NISTFetcher(http, RateLimiter(delay=1.0), cache_dir=cache_dir),
            "W3C": _W3CFetcher(http, RateLimiter(delay=0.5)),
            "ETSI": _ETSIFetcher(http, RateLimiter(delay=1.0)),
            "ISO": RelatonLiveFetcher(http=http, cache=cache, source="ISO"),
            "IEC": RelatonLiveFetcher(http=http, cache=cache, source="IEC"),
            "IEEE": RelatonLiveFetcher(http=http, cache=cache, source="IEEE"),
            "ISO/IEC": RelatonLiveFetcher(http=http, cache=cache, source=None),
            "CC": _CCFetcher(cache=cache),
            "CEN": _CENFetcher(cache=cache),
        }

    async def search(
        self,
        query: str,
        *,
        body: str | None = None,
        limit: int = 10,
    ) -> list[StandardRecord]:
        """Search standards by query string, optionally filtered to one body.

        Args:
            query: Identifier, title, or free text.
            body: Optional body filter: "IETF", "NIST", "W3C", "ETSI",
                "ISO", "IEC", "ISO/IEC", "IEEE", "CC", or "CEN". ISO / IEC /
                ISO/IEC / IEEE / CC / CEN results come from the locally synced
                cache; run ``sync-standards`` first for non-empty results.
            limit: Maximum results.

        Returns:
            List of StandardRecord dicts.
        """
        records, _ = await self.search_with_failures(query, body=body, limit=limit)
        return records

    async def search_with_failures(
        self,
        query: str,
        *,
        body: str | None = None,
        limit: int = 10,
    ) -> tuple[list[StandardRecord], list[StandardsUpstreamError]]:
        """Search standards, naming any source that never answered.

        :meth:`search` drops the failures for callers that cannot act on
        them. Callers that report to a user take them, because an empty
        result and a source that was down are different answers (#401).

        Args:
            query: Identifier, title, or free text.
            body: Optional body filter, as for :meth:`search`.
            limit: Maximum results.

        Returns:
            The matching records, and the failures gathered while finding
            them. A failing body never removes another body's results.
        """
        if body is not None:
            fetcher = self._fetchers.get(body.upper())
            if fetcher is None:
                return [], []
            try:
                return await fetcher.search(query, limit=limit), []
            except StandardsUpstreamError as exc:
                return [], [exc]

        # Search all sources concurrently, one call per fetcher type. For
        # RelatonLiveFetcher specifically, the ISO/IEC variant (source=None)
        # returns unfiltered Relaton records and subsumes the ISO/IEC-scoped
        # instances — last-wins overwrite keeps it (dict insertion order:
        # ISO → IEC → ISO/IEC). This is a deliberate, type-based dedup; if
        # a second instance of any non-Relaton type is ever registered, the
        # earlier one will be silently skipped.
        one_per_type = self._one_fetcher_per_type()
        outcomes = await asyncio.gather(
            *(f.search(query, limit=limit) for f in one_per_type),
            return_exceptions=True,
        )
        return _collect_search(list(outcomes), limit)

    async def get(self, identifier: str) -> StandardRecord | None:
        """Resolve and fetch a single standard by identifier.

        Attempts local regex resolution first; if unambiguous, routes to the
        matching source fetcher. Falls back to searching all fetchers.

        Args:
            identifier: Canonical or fuzzy identifier.

        Returns:
            Populated StandardRecord or None.
        """
        record, _ = await self.get_with_failures(identifier)
        return record

    async def get_with_failures(
        self, identifier: str
    ) -> tuple[StandardRecord | None, list[StandardsUpstreamError]]:
        """Fetch one standard, naming any source that never answered.

        ``(None, [])`` means the sources answered and hold no such standard.
        ``(None, [failure])`` means nobody could say, which a caller must not
        report as an absence (#401).

        Args:
            identifier: Canonical or fuzzy identifier.

        Returns:
            The record if one was found, and the failures gathered on the way.
        """
        failures: list[StandardsUpstreamError] = []
        resolved = resolve_identifier_local(identifier)
        if resolved is not None:
            canonical, body = resolved
            fetcher = self._fetchers.get(body)
            if fetcher is not None:
                try:
                    return await fetcher.get(canonical), failures
                except StandardsUpstreamError as exc:
                    return None, [exc]

        # No local resolution — try one fetcher per type. See
        # :meth:`_one_fetcher_per_type` for the dedup contract. A source that
        # fails is recorded and the walk continues: ETSI sits fourth, so
        # stopping here would leave Relaton, CC and CEN never tried.
        for fetcher in self._one_fetcher_per_type():
            try:
                result = await fetcher.get(identifier)
            except StandardsUpstreamError as exc:
                failures.append(exc)
                continue
            if result is not None:
                return result, failures
        return None, failures

    def _one_fetcher_per_type(self) -> list[_StandardsFetcher]:
        """Return one fetcher per concrete fetcher class.

        Used by the all-bodies paths of :meth:`search` and :meth:`get` so that
        fetchers registered under multiple body keys are only invoked once.

        For :class:`RelatonLiveFetcher` (registered under ``ISO``, ``IEC``,
        ``IEEE``, ``ISO/IEC``), the last-wins overwrite keeps the ``ISO/IEC``
        variant whose ``source=None`` returns all synced Relaton records — the
        ISO-, IEC-, and IEEE-scoped instances would be subsumed by it.
        Insertion order of ``self._fetchers`` (``ISO`` → ``IEC`` → ``IEEE`` →
        ``ISO/IEC``) is load-bearing.

        Non-Relaton fetchers appear exactly once today; if a second instance
        of any of those types is ever added, it will replace the earlier one
        — register distinct wrapper types if that matters.
        """
        by_type: dict[type[object], _StandardsFetcher] = {}
        for f in self._fetchers.values():
            by_type[type(f)] = f
        return list(by_type.values())

    async def resolve(self, raw: str) -> list[StandardRecord]:
        """Resolve a raw citation string to one or more StandardRecords.

        Returns a single-item list when unambiguous, multiple items when
        the raw string matches multiple standards, a stub record (title="")
        when locally resolved but the source fetch failed, or an empty list
        when completely unresolvable.

        Args:
            raw: Raw citation string.

        Returns:
            List of matching StandardRecord dicts.
        """
        resolved = resolve_identifier_local(raw)
        if resolved is not None:
            canonical, body = resolved
            fetcher = self._fetchers.get(body)
            if fetcher:
                try:
                    record = await fetcher.get(canonical)
                except StandardsUpstreamError:
                    # Falls through to the stub below, which is what a failed
                    # fetch already produced here. Reporting this failure to
                    # the caller is resolve()'s own change to make, not this
                    # one's; the stub's shortcomings are pre-existing.
                    record = None
                if record is not None:
                    return [record]
            # Identifier resolved locally but source fetch failed — return minimal stub
            # so callers can still surface the canonical form rather than "not found"
            logger.warning(
                "standards_fetch_failed canonical=%s body=%s", canonical, body
            )
            return [
                StandardRecord(
                    identifier=canonical, body=body, title="", full_text_available=False
                )
            ]

        # No local resolution — fall back to API search across all bodies
        results = await self.search(raw, limit=5)
        return results

    async def download(self, url: str) -> bytes:
        """Download a URL and return the raw content bytes.

        Encapsulates the HTTP client so callers do not access ``_http`` directly.

        Args:
            url: URL to fetch (follows redirects).

        Returns:
            Raw response body bytes.

        Raises:
            httpx.HTTPStatusError: If the response status indicates an error.
        """
        resp = await self._http.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

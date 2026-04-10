"""Standards lookup client: identifier resolver, source fetchers, StandardsClient."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx

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


def resolve_identifier_local(raw: str) -> tuple[str, str] | None:
    """Attempt to resolve *raw* to (canonical_identifier, body) using only regex.

    Returns ``None`` when no Tier 1 pattern matches.

    Args:
        raw: Raw citation string from a paper reference.

    Returns:
        Tuple of (canonical_identifier, body) or None.
    """
    s = raw.strip()

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

    return None


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

        Args:
            identifier: Canonical NIST identifier (e.g. "NIST SP 800-53 Rev. 5").

        Returns:
            Populated StandardRecord or None if not found.
        """
        all_pubs = await self._fetch_all()
        id_lower = identifier.lower()
        for pub in all_pubs:
            pub_id = (pub.get("identifier") or "").lower()
            if pub_id == id_lower or id_lower in pub_id or pub_id in id_lower:
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
    This endpoint is not behind Cloudflare bot protection.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~1s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search ETSI standards by keyword.

        Args:
            query: Search string (e.g. "303 645", "IoT security").
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        await self._limiter.acquire()
        params = {**_ETSI_JOOMLA_PARAMS, "search": query, "page": 1}
        try:
            resp = await self._http.get(f"{_ETSI_BASE}/", params=params)
        except httpx.HTTPError as exc:
            logger.warning("etsi_api_request_failed error=%s", exc)
            return []
        if resp.status_code != 200:
            logger.warning(
                "etsi_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return []
        try:
            items: list[dict] = resp.json()  # type: ignore[type-arg]
        except json.JSONDecodeError as exc:
            logger.warning(
                "etsi_api_json_decode_error url=%s err=%s", str(resp.url), exc
            )
            return []
        if not isinstance(items, list):
            logger.warning("etsi_api_unexpected_response type=%s", type(items).__name__)
            return []
        return [_normalize_etsi(item) for item in items[:limit]]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single ETSI standard by canonical identifier.

        Args:
            identifier: Canonical identifier (e.g. "ETSI EN 303 645").

        Returns:
            Populated StandardRecord or None if not found.
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


# ---------------------------------------------------------------------------
# StandardsClient — public orchestrator
# ---------------------------------------------------------------------------


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
        self, http: httpx.AsyncClient, *, cache_dir: Path | None = None
    ) -> None:
        self._http = http
        self._fetchers: dict[
            str, _IETFFetcher | _NISTFetcher | _W3CFetcher | _ETSIFetcher
        ] = {
            "IETF": _IETFFetcher(http, RateLimiter(delay=0.5)),
            "NIST": _NISTFetcher(http, RateLimiter(delay=1.0), cache_dir=cache_dir),
            "W3C": _W3CFetcher(http, RateLimiter(delay=0.5)),
            "ETSI": _ETSIFetcher(http, RateLimiter(delay=1.0)),
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
            body: Optional body filter: "NIST", "IETF", "W3C", or "ETSI".
            limit: Maximum results.

        Returns:
            List of StandardRecord dicts.
        """
        if body is not None:
            fetcher = self._fetchers.get(body.upper())
            if fetcher is None:
                return []
            return await fetcher.search(query, limit=limit)

        # Search all sources concurrently and merge
        results_per_body = await asyncio.gather(
            *(f.search(query, limit=limit) for f in self._fetchers.values()),
            return_exceptions=True,
        )
        merged: list[StandardRecord] = []
        for r in results_per_body:
            if isinstance(r, list):
                merged.extend(r)
        return merged[:limit]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Resolve and fetch a single standard by identifier.

        Attempts local regex resolution first; if unambiguous, routes to the
        matching source fetcher. Falls back to searching all fetchers.

        Args:
            identifier: Canonical or fuzzy identifier.

        Returns:
            Populated StandardRecord or None.
        """
        resolved = resolve_identifier_local(identifier)
        if resolved is not None:
            canonical, body = resolved
            fetcher = self._fetchers.get(body)
            if fetcher:
                return await fetcher.get(canonical)

        # No local resolution — try each fetcher
        for fetcher in self._fetchers.values():
            result = await fetcher.get(identifier)
            if result is not None:
                return result
        return None

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
                record = await fetcher.get(canonical)
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

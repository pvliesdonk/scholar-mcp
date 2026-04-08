"""Standards lookup client: identifier resolver, source fetchers, StandardsClient."""

from __future__ import annotations

import asyncio
import logging
import re

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
_ETSI_RE = re.compile(r"(?i)\betsi\s+(EN|TS|TR|ES|EG)\s*(\d{3})\s*[\s-]?\s*(\d{3})\b")


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

_NIST_BASE = "https://csrc.nist.gov"
_NIST_PUBLICATIONS_JSON = "/CSRC/media/Publications/search-results-json-file/json"


class _NISTFetcher:
    """Fetches NIST CSRC publication metadata.

    Uses the NIST CSRC publications JSON endpoint as a searchable catalogue.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~1s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter
        self._catalogue: list[dict] | None = None  # type: ignore[type-arg]
        self._lock = asyncio.Lock()

    async def _fetch_all(self) -> list[dict]:  # type: ignore[type-arg]
        """Fetch the full NIST publications JSON catalogue with in-memory caching.

        Uses double-checked locking to prevent concurrent full-catalogue
        downloads when multiple coroutines call this before the first fetch
        completes.

        Returns:
            Raw list of publication objects from CSRC.
        """
        if self._catalogue is not None:
            return self._catalogue
        async with self._lock:
            if self._catalogue is not None:  # re-check after acquiring
                return self._catalogue
            await self._limiter.acquire()
            resp = await self._http.get(f"{_NIST_BASE}{_NIST_PUBLICATIONS_JSON}")
            if resp.status_code != 200:
                logger.warning(
                    "nist_api_error status=%d url=%s", resp.status_code, str(resp.url)
                )
                return []
            data = resp.json()
            if isinstance(data, list):
                self._catalogue = data
            else:
                self._catalogue = data.get("response", data.get("publications", []))
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
            if q in (p.get("docIdentifier") or "").lower()
            or q in (p.get("title") or "").lower()
            or q in (p.get("number") or "").lower()
        ]
        return [_normalize_nist(p) for p in matches[:limit]]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single NIST publication by canonical identifier.

        Searches the catalogue and returns the first exact or close match.

        Args:
            identifier: Canonical NIST identifier (e.g. "NIST SP 800-53 Rev. 5").

        Returns:
            Populated StandardRecord or None if not found.
        """
        all_pubs = await self._fetch_all()
        id_lower = identifier.lower()
        for pub in all_pubs:
            doc_id = (pub.get("docIdentifier") or "").lower()
            if doc_id == id_lower or doc_id in id_lower or id_lower in doc_id:
                return _normalize_nist(pub)
        return None


def _normalize_nist(pub: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a NIST CSRC publication object to a StandardRecord.

    Args:
        pub: Raw publication object from the CSRC JSON feed.

    Returns:
        Populated StandardRecord.
    """
    doc_id = pub.get("docIdentifier", "")
    series = pub.get("series", "")
    number = pub.get("number", "")
    rev = pub.get("revisionNumber", "")

    if "SP" in series or "Special Publication" in series:
        canonical = f"NIST SP {number}"
        if rev:
            canonical += f" Rev. {rev}"
    elif "FIPS" in series:
        canonical = f"FIPS {number}"
    elif "NISTIR" in series or "Interagency" in series:
        canonical = f"NISTIR {number}"
    else:
        canonical = doc_id or f"NIST {number}"

    pdf_url: str | None = pub.get("pdfUrl") or pub.get("doiUrl")
    status_raw = (pub.get("status") or "").lower()
    if "final" in status_raw:
        status = "published"
    elif "draft" in status_raw:
        status = "draft"
    else:
        status = "published"

    return StandardRecord(
        identifier=canonical,
        aliases=[doc_id] if doc_id and doc_id != canonical else [],
        title=pub.get("title", ""),
        body="NIST",
        number=number,
        revision=f"Rev. {rev}" if rev else None,
        status=status,
        published_date=pub.get("publicationDate"),
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=pub.get("abstract"),
        committee=None,
        url=pub.get("doiUrl") or f"{_NIST_BASE}/publications/detail/{number}",
        full_text_url=pdf_url,
        full_text_available=pdf_url is not None,
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

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~0.5s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    def _to_shortname(self, identifier: str) -> str:
        """Convert a human-readable W3C identifier to an API shortname.

        Args:
            identifier: Human-readable identifier like "WCAG 2.1".

        Returns:
            API shortname like "WCAG21".
        """
        if identifier in _W3C_SHORTNAME_MAP:
            return _W3C_SHORTNAME_MAP[identifier]
        # Fallback: strip spaces and dots
        return re.sub(r"[\s.]", "", identifier)

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
        """Search W3C specifications by keyword.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"{_W3C_API}/specifications",
            params={"q": query, "limit": limit},
        )
        if resp.status_code != 200:
            logger.warning(
                "w3c_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return []
        data = resp.json()
        results_list = data.get("results")
        specs = (
            results_list
            if results_list is not None
            else data.get("_embedded", {}).get("specifications", [])
        )[:limit]
        return [_normalize_w3c(s) for s in specs]


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
# ETSI source fetcher (catalogue index + scraping)
# ---------------------------------------------------------------------------

_ETSI_BASE = "https://www.etsi.org"
_ETSI_SEARCH = "/standards-search/"


class _ETSIFetcher:
    """Fetches ETSI standard metadata by scraping the ETSI standards search page.

    On first call, builds an in-memory index from the catalogue page (a few
    seconds). Subsequent calls search the in-memory index without network I/O.
    The index is rebuilt when ``_index`` is None (e.g. after process restart).

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~2s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter
        self._index: list[StandardRecord] | None = None
        self._lock = asyncio.Lock()

    async def _ensure_index(self) -> list[StandardRecord]:
        """Return in-memory index, building it from the ETSI catalogue if needed.

        Uses double-checked locking to prevent concurrent scrapes when multiple
        coroutines call this before the first scrape completes.

        Returns:
            List of stub StandardRecord dicts covering the ETSI catalogue.
        """
        if self._index is not None:
            return self._index
        async with self._lock:
            if self._index is not None:  # re-check after acquiring
                return self._index
            self._index = await self._scrape_catalogue()
        return self._index

    async def _scrape_catalogue(self) -> list[StandardRecord]:
        """Scrape the ETSI standards search page to build a catalogue index.

        Returns:
            List of StandardRecord stubs (identifier, title, url).
        """
        from bs4 import BeautifulSoup

        await self._limiter.acquire()
        resp = await self._http.get(f"{_ETSI_BASE}{_ETSI_SEARCH}")
        if resp.status_code != 200:
            logger.warning("etsi_catalogue_scrape_failed status=%d", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        records: list[StandardRecord] = []

        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = cells[0].find("a")
            if not link:
                continue
            raw_id = link.get_text(strip=True)
            title = cells[1].get_text(strip=True)
            href = str(link.get("href") or "")
            pdf_url = f"{_ETSI_BASE}{href}" if href.startswith("/") else href
            m = _ETSI_RE.search(raw_id)
            if not m:
                continue
            canonical = f"ETSI {m.group(1).upper()} {m.group(2)} {m.group(3)}"
            records.append(
                StandardRecord(
                    identifier=canonical,
                    aliases=[raw_id] if raw_id != canonical else [],
                    title=title,
                    body="ETSI",
                    number=f"{m.group(2)} {m.group(3)}",
                    revision=None,
                    status="published",
                    published_date=(
                        cells[3].get_text(strip=True) if len(cells) > 3 else None
                    ),
                    withdrawn_date=None,
                    superseded_by=None,
                    supersedes=[],
                    scope=None,
                    committee=None,
                    url=f"{_ETSI_BASE}{_ETSI_SEARCH}",
                    full_text_url=pdf_url if pdf_url.endswith(".pdf") else None,
                    full_text_available=pdf_url.endswith(".pdf"),
                    price=None,
                    related=[],
                )
            )

        if not records:
            logger.warning(
                "etsi_catalogue_empty — page may be a JS SPA or returned no table rows; "
                "ETSI lookups will return no results until the index is rebuilt"
            )
        else:
            logger.info("etsi_catalogue_indexed count=%d", len(records))
        return records

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search the ETSI catalogue index by keyword.

        Builds the index on first call (inline scrape). Subsequent calls use
        the in-memory cache.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        index = await self._ensure_index()
        q = query.lower().replace(" ", "").replace("-", "")
        matches = [
            r
            for r in index
            if q
            in (r.get("identifier") or "").lower().replace(" ", "").replace("-", "")
            or q in (r.get("title") or "").lower()
        ]
        return matches[:limit]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single ETSI standard by canonical identifier.

        Args:
            identifier: Canonical identifier (e.g. "ETSI EN 303 645").

        Returns:
            Populated StandardRecord or None if not found.
        """
        results = await self.search(identifier, limit=1)
        return results[0] if results else None


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

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._fetchers: dict[
            str, _IETFFetcher | _NISTFetcher | _W3CFetcher | _ETSIFetcher
        ] = {
            "IETF": _IETFFetcher(http, RateLimiter(delay=0.5)),
            "NIST": _NISTFetcher(http, RateLimiter(delay=1.0)),
            "W3C": _W3CFetcher(http, RateLimiter(delay=0.5)),
            "ETSI": _ETSIFetcher(http, RateLimiter(delay=2.0)),
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

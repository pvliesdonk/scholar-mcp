"""Standards lookup client: identifier resolver, source fetchers, StandardsClient."""

from __future__ import annotations

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


def _resolve_identifier_local(raw: str) -> tuple[str, str] | None:
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
        """Fetch a single RFC by identifier (e.g. "RFC 9000").

        Args:
            identifier: Canonical RFC identifier.

        Returns:
            Populated StandardRecord or None if not found.
        """
        m = re.match(r"(?i)rfc\s*(\d+)", identifier)
        if not m:
            return None
        n = int(m.group(1))
        await self._limiter.acquire()
        resp = await self._http.get(
            f"{_IETF_DATATRACKER}/api/v1/doc/document/",
            params={"name": f"rfc{n:04d}", "format": "json"},
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
    # BCP/STD/FYI names must not be prefixed with "RFC"
    identifier = f"RFC {int(n)}" if re.match(r"(?i)^rfc\d+$", name) else name.upper()

    if n:
        url = f"{_RFC_EDITOR_BASE}/info/rfc{int(n)}"
        full_text_url: str | None = f"{_RFC_EDITOR_BASE}/rfc/rfc{int(n)}.html"
        full_text_available = True
        number = str(int(n))
    else:
        url = ""
        full_text_url = None
        full_text_available = False
        number = ""

    return StandardRecord(
        identifier=identifier,
        aliases=[name, name.upper().replace("RFC", "RFC ")],
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
        committee=(
            obj.get("group", {}).get("acronym")
            if isinstance(obj.get("group"), dict)
            else None
        ),
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

    async def _fetch_all(self) -> list[dict]:  # type: ignore[type-arg]
        """Fetch the full NIST publications JSON catalogue.

        Returns:
            Raw list of publication objects from CSRC.
        """
        await self._limiter.acquire()
        resp = await self._http.get(f"{_NIST_BASE}{_NIST_PUBLICATIONS_JSON}")
        if resp.status_code != 200:
            logger.warning(
                "nist_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("response", data.get("publications", []))  # type: ignore[no-any-return]

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

"""Single-file live-fetch fallback for ISO / IEC / ISO/IEC identifiers.

Used by :class:`StandardsClient` when ``get_standard(identifier)`` misses
the cache AND no sync has been run. Avoids the "false negative until sync
runs" trap by doing one cheap ``raw.githubusercontent.com`` GET per call.

Lives alongside ``_sync_relaton.py``; the two modules share the same YAML
mapper so synced and live-fetched records have identical shape.
"""

from __future__ import annotations

import logging
import re

import httpx
import yaml

from ._record_types import StandardRecord
from ._sync_relaton import _yaml_to_record

logger = logging.getLogger(__name__)

_RAW_BASE = "https://raw.githubusercontent.com/relaton"


def _identifier_to_relaton_slug(identifier: str) -> str | None:
    """Convert a canonical ISO/IEC/ISO/IEC identifier to its Relaton filename slug.

    Examples:
        >>> _identifier_to_relaton_slug("ISO 9001:2015")
        'iso-9001-2015'
        >>> _identifier_to_relaton_slug("ISO/IEC 27001:2022")
        'iso-iec-27001-2022'
        >>> _identifier_to_relaton_slug("IEC 62443-3-3:2020")
        'iec-62443-3-3-2020'
        >>> _identifier_to_relaton_slug("ISO 9001:2015/Amd 1:2020")
        'iso-9001-2015-amd-1-2020'

    Returns ``None`` when the prefix is not one of ISO, IEC, or ISO/IEC.
    """
    stripped = identifier.strip()
    upper = stripped.upper()
    if not (
        upper.startswith("ISO/IEC")
        or upper.startswith("ISO ")
        or upper.startswith("IEC ")
        or (upper.startswith("ISO") and upper[3:4].isdigit())
        or (upper.startswith("IEC") and upper[3:4].isdigit())
    ):
        return None

    slug = stripped.lower()
    # Normalise "iso/iec" and the rarer reversed form before general substitution
    slug = slug.replace("iec/iso", "iso-iec")
    slug = slug.replace("iso/iec", "iso-iec")
    # Any whitespace, colon, slash, or ampersand becomes a hyphen
    slug = re.sub(r"[\s:/&]+", "-", slug)
    # Collapse repeated hyphens and strip leading/trailing
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or None


def _identifier_prefers_iec(identifier: str) -> bool:
    """Plain 'IEC xxx' identifiers prefer the IEC repo first."""
    upper = identifier.strip().upper()
    return upper.startswith("IEC ") or (
        upper.startswith("IEC") and upper[3:4].isdigit()
    )


class RelatonLiveFetcher:
    """Fetches a single Relaton YAML file on demand over HTTPS.

    Registered into ``StandardsClient._fetchers`` for keys ``ISO``, ``IEC``,
    and ``ISO/IEC``. Returns ``None`` for identifiers outside that set.
    """

    def __init__(self, *, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _try_repo(self, repo: str, slug: str) -> dict[str, object] | None:
        url = f"{_RAW_BASE}/{repo}/main/data/{slug}.yaml"
        try:
            response = await self._http.get(url)
        except httpx.HTTPError as exc:
            logger.debug("relaton_live_http_error url=%s err=%s", url, exc)
            return None
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning(
                "relaton_live_bad_status url=%s status=%s",
                url,
                response.status_code,
            )
            return None
        try:
            doc = yaml.safe_load(response.text)
        except yaml.YAMLError as exc:
            logger.warning("relaton_live_parse_error url=%s err=%s", url, exc)
            return None
        if not isinstance(doc, dict):
            return None
        return doc

    async def fetch(self, identifier: str) -> StandardRecord | None:
        """Return a parsed record for *identifier*, or a stub, or ``None``."""
        slug = _identifier_to_relaton_slug(identifier)
        if slug is None:
            return None

        repos = (
            ["relaton-data-iec", "relaton-data-iso"]
            if _identifier_prefers_iec(identifier)
            else ["relaton-data-iso", "relaton-data-iec"]
        )
        for repo in repos:
            doc = await self._try_repo(repo, slug)
            if doc is None:
                continue
            record, _ = _yaml_to_record(doc)
            if record is not None:
                return record

        # 404 in both repos — return a stub so callers can surface
        # "resolved but catalogue entry unavailable" rather than a bare None.
        upper = identifier.strip().upper()
        if upper.startswith("ISO/IEC") or "IEC/ISO" in upper:
            body = "ISO/IEC"
        elif upper.startswith("IEC"):
            body = "IEC"
        else:
            body = "ISO"
        stub: StandardRecord = {
            "identifier": identifier,
            "title": "",
            "body": body,
            "full_text_available": False,
        }
        return stub

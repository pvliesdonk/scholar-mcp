"""Single-file live-fetch fallback for ISO / IEC / IEEE Relaton standards.

Used by :class:`StandardsClient` when ``get_standard(identifier)`` misses
the cache AND no sync has been run. Avoids the "false negative until sync
runs" trap by doing one cheap ``raw.githubusercontent.com`` GET per call.

Covers pure ISO, IEC, IEEE plus their joint forms: ISO/IEC, IEC/IEEE,
ISO/IEC/IEEE. Per-body filename conventions (ISO lowercase-hyphen vs.
IEEE uppercase-underscore) are handled by :func:`_identifier_to_relaton_slug`.

Lives alongside ``_sync_relaton.py``; the two modules share the same YAML
mapper so synced and live-fetched records have identical shape.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import httpx
import yaml

from ._record_types import StandardRecord
from ._sync_relaton import _yaml_to_record

if TYPE_CHECKING:
    from ._protocols import CacheProtocol

logger = logging.getLogger(__name__)

_RAW_BASE = "https://raw.githubusercontent.com/relaton"


def _identifier_to_relaton_slug(identifier: str) -> str | None:
    """Convert an identifier to its Relaton filename slug.

    Dispatch on body prefix:

    - IEEE / IEC/IEEE / ISO/IEC/IEEE → uppercase-underscore form preserving
      internal dots and intra-token hyphens
      (``IEEE 1003.1-2024`` → ``IEEE_1003.1-2024``;
       ``ISO/IEC/IEEE 42010-2011`` → ``ISO_IEC_IEEE_42010-2011``).
    - ISO / IEC / ISO/IEC → lowercase-hyphen form (unchanged from PR 2).

    Returns ``None`` when the prefix isn't recognized.
    """
    stripped = identifier.strip()
    upper = stripped.upper()

    # IEEE slugging (uppercase-underscore) — check before ISO/IEC since
    # ISO/IEC/IEEE and IEC/IEEE are IEEE-repo joints.
    if (
        upper.startswith("IEEE ")
        or (upper.startswith("IEEE") and upper[4:5] in {" ", "_"})
        or upper.startswith("IEC/IEEE")
        or upper.startswith("ISO/IEC/IEEE")
    ):
        return _ieee_slug(stripped)

    # ISO/IEC/IEC/ISO slugging (lowercase-hyphen) — PR 2 behavior.
    if not (
        upper.startswith("ISO/IEC")
        or upper.startswith("ISO ")
        or upper.startswith("IEC ")
        or (upper.startswith("ISO") and upper[3:4] in {" ", "-"})
        or (upper.startswith("IEC") and upper[3:4] in {" ", "-"})
    ):
        return None

    slug = stripped.lower()
    slug = slug.replace("iec/iso", "iso-iec")
    slug = slug.replace("iso/iec", "iso-iec")
    slug = re.sub(r"[\s:/&]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or None


def _ieee_slug(identifier: str) -> str | None:
    """IEEE filename slug: uppercase, underscores between tokens, dots kept.

    Examples:
        IEEE 1003.1-2024        → IEEE_1003.1-2024
        IEEE Std 1588-2019      → IEEE_Std_1588-2019
        IEC/IEEE 61588-2021     → IEC_IEEE_61588-2021
        ISO/IEC/IEEE 42010-2011 → ISO_IEC_IEEE_42010-2011
    """
    slug = re.sub(r"[/\s]+", "_", identifier.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or None


def _repo_order_for(identifier: str) -> list[str]:
    """Return the ordered list of relaton-data-* repos to probe.

    The first repo that returns a parseable YAML wins. All 404s → stub
    record.
    """
    upper = identifier.strip().upper()
    if (
        upper.startswith("IEEE ")
        or (upper.startswith("IEEE") and upper[4:5] in {" ", "_"})
        or upper.startswith("IEC/IEEE")
        or upper.startswith("ISO/IEC/IEEE")
    ):
        if upper.startswith("ISO/IEC/IEEE"):
            return ["relaton-data-ieee", "relaton-data-iso", "relaton-data-iec"]
        if upper.startswith("IEC/IEEE"):
            return ["relaton-data-ieee", "relaton-data-iec"]
        return ["relaton-data-ieee"]
    if upper.startswith("IEC "):
        return ["relaton-data-iec", "relaton-data-iso"]
    return ["relaton-data-iso", "relaton-data-iec"]


class RelatonLiveFetcher:
    """Fetches a single Relaton YAML file on demand over HTTPS.

    Registered into ``StandardsClient._fetchers`` for keys ``ISO``, ``IEC``,
    ``ISO/IEC``, and ``IEEE``. Returns ``None`` for identifiers the slug
    helper can't convert (e.g. ``RFC 9000``).
    """

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        cache: CacheProtocol | None = None,
        source: str | None = None,
    ) -> None:
        """Initialise the fetcher.

        Args:
            http: Shared ``httpx.AsyncClient``.
            cache: Optional cache for :meth:`search`. When ``None``,
                :meth:`search` returns an empty list.
            source: Optional ``source`` filter forwarded to the cache on
                :meth:`search`. Used by :class:`StandardsClient` to keep
                ``body="ISO"`` and ``body="IEC"`` searches scoped.
        """
        self._http = http
        self._cache = cache
        self._source = source

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

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search synced ISO / IEC / ISO/IEC standards by keyword.

        Delegates to the cache's ``search_synced_standards`` method. Returns
        an empty list if no cache was provided at construction time (i.e.,
        ``sync-standards`` has not been run or the fetcher is in a test
        context without a cache).

        Args:
            query: Substring to match against identifier and title.
            limit: Maximum number of results.

        Returns:
            List of matching ``StandardRecord`` dicts.
        """
        if self._cache is None:
            logger.debug("relaton_live_search_no_cache query=%s", query)
            return []
        return await self._cache.search_synced_standards(
            query, source=self._source, limit=limit
        )

    async def get(self, identifier: str) -> StandardRecord | None:
        """Return a parsed record for *identifier*, or a stub, or ``None``."""
        slug = _identifier_to_relaton_slug(identifier)
        if slug is None:
            return None

        for repo in _repo_order_for(identifier):
            doc = await self._try_repo(repo, slug)
            if doc is None:
                continue
            record, _ = _yaml_to_record(doc)
            if record is not None:
                return record

        # All repos 404 — return a stub so callers can surface
        # "resolved but catalogue entry unavailable" rather than None.
        upper = identifier.strip().upper()
        if upper.startswith("ISO/IEC/IEEE"):
            body = "ISO/IEC/IEEE"
        elif upper.startswith("IEC/IEEE"):
            body = "IEC/IEEE"
        elif upper.startswith("IEEE"):
            body = "IEEE"
        elif upper.startswith("ISO/IEC"):
            body = "ISO/IEC"
        elif upper.startswith("IEC"):
            body = "IEC"
        else:
            body = "ISO"
        stub: StandardRecord = {
            "identifier": identifier,
            "title": "",
            "body": body,
            "status": "unknown",
            "full_text_available": False,
        }
        return stub

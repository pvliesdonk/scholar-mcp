"""Single-file live-fetch fallback for ISO / IEC / IEEE Relaton standards.

Used by :class:`StandardsClient` when ``get_standard(identifier)`` misses
the cache AND no sync has been run. Avoids the "false negative until sync
runs" trap by doing one cheap ``raw.githubusercontent.com`` GET per call.

Covers pure ISO, IEC, IEEE plus their joint forms: ISO/IEC, IEC/IEEE,
ISO/IEC/IEEE. Reads each repository's ``v2`` branch, where every body names
its files the same way: :func:`_identifier_to_relaton_slug`, and
``docs/design/reference/relaton-data-v2.md``.

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
from ._sync_relaton import _IEC_IEEE, _ISO_IEC_IEEE, _yaml_to_record

if TYPE_CHECKING:
    from ._protocols import CacheProtocol

logger = logging.getLogger(__name__)

_RAW_BASE = "https://raw.githubusercontent.com/relaton"
_BRANCH = "v2"
# v2 filenames: the identifier lowercased, every run of other characters a
# hyphen, except + & _ [ ] which stay.
_SLUG_SEPARATORS = re.compile(r"[^a-z0-9+&_\[\]]+")
# The resolver drops "Std" ("IEEE 802.11-2016"); the v2 file keeps it.
_IEEE_BARE_NUMBER = re.compile(r"^IEEE (?=C?\d)", re.IGNORECASE)
_PREFIXES = ("IEEE ", "IEEE_", "ISO ", "ISO/", "ISO-", "IEC ", "IEC/", "IEC-")


def _identifier_to_relaton_slug(identifier: str) -> str | None:
    """Convert an identifier to its Relaton v2 filename slug.

    The identifier is lowercased and every run of characters other than
    letters, digits and ``+ & _ [ ]`` becomes one hyphen
    (``ISO/IEC 27001:2022`` → ``iso-iec-27001-2022``). A plain IEEE number
    gains the ``Std`` the resolver strips (``IEEE 802.11-2016`` →
    ``ieee-std-802-11-2016``).

    Args:
        identifier: Canonical identifier from the resolver.

    Returns:
        The slug, or ``None`` when the prefix is not ISO, IEC or IEEE.
    """
    stripped = identifier.strip()
    upper = stripped.upper()
    if not upper.startswith(_PREFIXES):
        return None
    stripped = _IEEE_BARE_NUMBER.sub("IEEE Std ", stripped)
    slug = _SLUG_SEPARATORS.sub("-", stripped.lower()).strip("-")
    return slug or None


def _repo_order_for(identifier: str) -> list[str]:
    """Return the ordered list of relaton-data-* repos to probe.

    The first repo whose YAML parses cleanly wins. All other outcomes
    (404, non-404 error, unparseable YAML) are treated the same by
    :meth:`RelatonLiveFetcher.get` — it moves on to the next repo. When
    all repos exhaust without a parseable result, the caller returns a
    stub record.
    """
    upper = identifier.strip().upper()
    if (
        upper.startswith("IEEE ")
        or (upper.startswith("IEEE") and upper[4:5] in {" ", "_"})
        or upper.startswith(_IEC_IEEE)
        or upper.startswith(_ISO_IEC_IEEE)
    ):
        if upper.startswith(_ISO_IEC_IEEE):
            return ["relaton-data-ieee", "relaton-data-iso", "relaton-data-iec"]
        if upper.startswith(_IEC_IEEE):
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
        url = f"{_RAW_BASE}/{repo}/{_BRANCH}/data/{slug}.yaml"
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

        # All repos exhausted without a parseable result — return a stub so
        # callers can surface "resolved but catalogue entry unavailable"
        # rather than None.
        upper = identifier.strip().upper()
        if upper.startswith(_ISO_IEC_IEEE):
            body = _ISO_IEC_IEEE
        elif upper.startswith(_IEC_IEEE):
            body = _IEC_IEEE
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

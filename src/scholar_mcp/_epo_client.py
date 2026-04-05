"""Async wrapper around the synchronous python-epo-ops-client library."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import epo_ops
import epo_ops.models

from scholar_mcp._epo_xml import parse_biblio_xml, parse_search_xml
from scholar_mcp._rate_limiter import RateLimitedError

if TYPE_CHECKING:
    from scholar_mcp._patent_numbers import DocdbNumber

logger = logging.getLogger(__name__)


class EpoRateLimitedError(RateLimitedError):
    """Raised when EPO traffic light is yellow, red, or black."""

    def __init__(self, color: str) -> None:
        self.color = color
        super().__init__(f"EPO rate limited: traffic light is {color}")


class EpoClient:
    """Async client for the EPO Open Patent Services (OPS) API.

    Wraps the synchronous ``python-epo-ops-client`` library, offloading
    blocking I/O to a thread via :func:`asyncio.to_thread`.  A single
    :class:`asyncio.Lock` serialises all calls because the underlying
    ``epo_ops.Client`` is not thread-safe.

    Args:
        consumer_key: EPO OPS consumer key.
        consumer_secret: EPO OPS consumer secret.
        _client: Optional pre-built client instance (for testing).  When
            provided, ``consumer_key`` and ``consumer_secret`` are ignored.
    """

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        *,
        _client: Any = None,
    ) -> None:
        if _client is not None:
            self._client = _client
        else:
            self._client = epo_ops.Client(
                key=consumer_key,
                secret=consumer_secret,
                middlewares=[],
            )
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_docdb_input(self, doc: DocdbNumber) -> epo_ops.models.Docdb:
        """Convert a :class:`DocdbNumber` to an ``epo_ops.models.Docdb`` instance.

        Args:
            doc: Parsed DOCDB patent number.

        Returns:
            ``epo_ops.models.Docdb`` ready for use as the ``input`` argument
            to ``epo_ops.Client`` methods.
        """
        return epo_ops.models.Docdb(
            number=doc.number,
            country_code=doc.country,
            kind_code=doc.kind or "A",
        )

    def _check_throttle(self, response: Any) -> None:
        """Inspect the X-Throttling-Control header and raise if not green.

        The header format is:
        ``green (search=green:30, retrieval=green:200, ...)``.
        The first word is the overall traffic-light colour.

        Args:
            response: A ``requests.Response``-like object with a ``headers``
                dict attribute.

        Raises:
            EpoRateLimitedError: When the traffic-light colour is anything
                other than ``"green"``.
        """
        header = response.headers.get("X-Throttling-Control", "green")
        color = header.split()[0].lower() if header else "green"
        if color != "green":
            logger.warning("epo_throttle color=%s", color)
            raise EpoRateLimitedError(color)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        cql_query: str,
        range_begin: int = 1,
        range_end: int = 25,
    ) -> dict[str, Any]:
        """Search EPO published data using a CQL query.

        Args:
            cql_query: CQL (Contextual Query Language) search expression.
            range_begin: First result number in the requested range (1-based).
            range_end: Last result number in the requested range (inclusive).

        Returns:
            Parsed search results dict with keys ``total_count`` and
            ``references`` (see :func:`parse_search_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data_search,
                cql_query,
                range_begin=range_begin,
                range_end=range_end,
            )
        self._check_throttle(response)
        return parse_search_xml(response.content)

    async def get_biblio(self, doc: DocdbNumber) -> dict[str, Any]:
        """Fetch bibliographic data for a single patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Parsed bibliographic metadata dict (see :func:`parse_biblio_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="biblio",
            )
        self._check_throttle(response)
        return parse_biblio_xml(response.content)

    async def aclose(self) -> None:
        """No-op cleanup.

        The underlying synchronous ``epo_ops.Client`` holds no persistent
        resources that require explicit teardown.
        """

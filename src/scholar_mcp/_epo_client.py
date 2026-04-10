"""Async wrapper around the synchronous python-epo-ops-client library."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any

import epo_ops
import epo_ops.models
from requests.exceptions import HTTPError

from scholar_mcp._epo_xml import (
    parse_biblio_xml,
    parse_citations_from_biblio,
    parse_claims_xml,
    parse_description_xml,
    parse_family_xml,
    parse_legal_xml,
    parse_search_xml,
)
from scholar_mcp._rate_limiter import RateLimitedError

if TYPE_CHECKING:
    from scholar_mcp._patent_numbers import DocdbNumber

logger = logging.getLogger(__name__)


def _parse_throttle_header(header: str) -> dict[str, str]:
    """Parse X-Throttling-Control into {service: color, '_overall': color}.

    Args:
        header: The X-Throttling-Control header value, e.g.
            ``"busy (images=green:100, search=yellow:2, retrieval=green:50)"``.
            Pass an empty string to get the green default.

    Returns:
        Dict with ``"_overall"`` key holding the first token, plus one entry
        per ``name=color:count`` pair found in the parenthesised section.
        Colors are lowercased. Missing header defaults to
        ``{"_overall": "green"}``.
    """
    parts = header.strip().split(None, 1)
    result: dict[str, str] = {"_overall": parts[0].lower() if parts else "green"}
    if len(parts) > 1:
        for match in re.finditer(r"(\w+)=(\w+):\d+", parts[1]):
            result[match.group(1).lower()] = match.group(2).lower()
    return result


def _parse_pdf_link(inquiry_xml: bytes) -> str | None:
    """Extract the FullDocument PDF link path from an EPO image inquiry response.

    Args:
        inquiry_xml: Raw XML bytes from ``published_data(..., endpoint='images')``.

    Returns:
        The ``link`` attribute value for the FullDocument PDF instance, or
        ``None`` if no PDF is available.
    """
    try:
        from lxml import etree

        root = etree.fromstring(inquiry_xml)
        ns = {"ops": "http://ops.epo.org"}
        for el in root.xpath(
            "//ops:document-instance[@desc='FullDocument']", namespaces=ns
        ):
            for fmt in el:
                if fmt.get("desc") == "application/pdf":
                    link = el.get("link")
                    return str(link) if link is not None else None
        return None
    except Exception as exc:
        logger.warning("epo_pdf_link_parse_failed err=%s", exc)
        return None


class EpoRateLimitedError(RateLimitedError):
    """Raised when the EPO OPS API throttles a request."""

    def __init__(self, color: str, *, service: str = "_overall") -> None:
        self.color = color
        self.service = service
        super().__init__(f"EPO rate limited: {service}={color}")


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
        self._throttle_cache: dict[str, str] = {}
        self._throttle_cache_ts: float = 0.0

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

    def _is_service_throttled(self, service: str) -> bool:
        """Check if a service is known to be throttled from the cache.

        Args:
            service: The EPO service name, e.g. ``"search"``.

        Returns:
            ``True`` if the cache is fresh (< 60 s old) and the service color
            is not green or idle. ``False`` if the cache is stale or the service
            is not throttled.
        """
        if time.monotonic() - self._throttle_cache_ts > 60:
            return False
        cached = self._throttle_cache
        color = cached.get(service, cached.get("_overall", "green"))
        return color not in ("green", "idle")

    def _check_throttle(self, response: Any, service: str = "_overall") -> None:
        """Check the throttle header and raise if the relevant service is throttled.

        Args:
            response: The HTTP response object with a ``headers`` dict-like attribute.
            service: The EPO service to check (e.g. ``"search"``, ``"retrieval"``,
                ``"inpadoc"``). Defaults to ``"_overall"``.

        Raises:
            RuntimeError: If the daily quota is exhausted.
            EpoRateLimitedError: If the service color is not green or idle.
        """
        header = response.headers.get("X-Throttling-Control", "green")
        throttle = _parse_throttle_header(header)
        # Update cache
        self._throttle_cache = throttle
        self._throttle_cache_ts = time.monotonic()
        color = throttle.get(service, throttle["_overall"])
        if color == "black":
            raise RuntimeError("EPO daily quota exhausted. Please try again tomorrow.")
        if color not in ("green", "idle"):
            logger.warning("epo_throttle service=%s color=%s", service, color)
            raise EpoRateLimitedError(color, service=service)

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
        if self._is_service_throttled("search"):
            cached_color = self._throttle_cache.get(
                "search", self._throttle_cache.get("_overall", "red")
            )
            if cached_color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(cached_color, service="search")
        try:
            async with self._lock:
                response = await asyncio.to_thread(
                    self._client.published_data_search,
                    cql_query,
                    range_begin=range_begin,
                    range_end=range_end,
                )
        except HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                # EPO returns 404 with SERVER.EntityNotFound when no results match.
                logger.debug("epo_search_no_results cql=%s", cql_query)
                return {"total_count": 0, "references": []}
            raise
        self._check_throttle(response, service="search")
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
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="retrieval")
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="biblio",
            )
        self._check_throttle(response, service="retrieval")
        return parse_biblio_xml(response.content)

    async def get_claims(self, doc: DocdbNumber) -> str:
        """Fetch claims text for a patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Claims text as a single string (see :func:`parse_claims_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="retrieval")
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="claims",
            )
        self._check_throttle(response, service="retrieval")
        return parse_claims_xml(response.content)

    async def get_description(self, doc: DocdbNumber) -> str:
        """Fetch description text for a patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Description text as a single string (see :func:`parse_description_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="retrieval")
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="description",
            )
        self._check_throttle(response, service="retrieval")
        return parse_description_xml(response.content)

    async def get_family(self, doc: DocdbNumber) -> list[dict[str, str]]:
        """Fetch patent family members.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            List of family member dicts (see :func:`parse_family_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        if self._is_service_throttled("inpadoc"):
            cached = self._throttle_cache
            color = cached.get("inpadoc", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="inpadoc")
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.family,
                "publication",
                inp,
            )
        self._check_throttle(response, service="inpadoc")
        return parse_family_xml(response.content)

    async def get_legal(self, doc: DocdbNumber) -> list[dict[str, str]]:
        """Fetch legal status events for a patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            List of legal event dicts (see :func:`parse_legal_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        if self._is_service_throttled("inpadoc"):
            cached = self._throttle_cache
            color = cached.get("inpadoc", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="inpadoc")
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.legal,
                "publication",
                inp,
            )
        self._check_throttle(response, service="inpadoc")
        return parse_legal_xml(response.content)

    async def get_citations(self, doc: DocdbNumber) -> dict[str, list[dict[str, Any]]]:
        """Fetch cited references (patent and NPL) for a patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Dict with ``patent_refs`` and ``npl_refs`` lists
            (see :func:`parse_citations_from_biblio`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="retrieval")
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="biblio",
            )
        self._check_throttle(response, service="retrieval")
        return parse_citations_from_biblio(response.content)

    async def get_pdf(self, doc: DocdbNumber) -> bytes:
        """Download full-document PDF for a patent via EPO OPS image service.

        Two-step process: first fetches the image inquiry to get the PDF link
        path, then downloads the PDF using that path.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Raw PDF bytes.

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
            ValueError: If no PDF is available for this patent.
        """
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            if color == "black":
                raise RuntimeError(
                    "EPO daily quota exhausted. Please try again tomorrow."
                )
            raise EpoRateLimitedError(color, service="retrieval")

        inp = self._to_docdb_input(doc)

        # Step 1: image inquiry to get the PDF link path
        async with self._lock:
            inquiry_resp = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="images",
            )
        self._check_throttle(inquiry_resp, service="retrieval")

        pdf_link = _parse_pdf_link(inquiry_resp.content)
        if pdf_link is None:
            raise ValueError(
                f"No PDF available for patent {doc.country}{doc.number}{doc.kind or ''}"
            )

        # Step 2: download the PDF
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            raise EpoRateLimitedError(color, service="retrieval")

        async with self._lock:
            pdf_resp = await asyncio.to_thread(
                self._client.image,
                pdf_link,
                range=1,
                document_format="application/pdf",
            )
        self._check_throttle(pdf_resp, service="retrieval")
        return bytes(pdf_resp.content)

    async def aclose(self) -> None:
        """No-op cleanup.

        The underlying synchronous ``epo_ops.Client`` holds no persistent
        resources that require explicit teardown.
        """

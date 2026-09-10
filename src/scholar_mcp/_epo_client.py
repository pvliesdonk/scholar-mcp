"""Async wrapper around the synchronous python-epo-ops-client library."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

import epo_ops
import epo_ops.models
from lxml import etree as _lxml_etree
from pypdf import PdfReader, PdfWriter
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
    from collections.abc import Awaitable, Callable

    from scholar_mcp._patent_numbers import DocdbNumber
    from scholar_mcp._record_types import PatentRecord

T = TypeVar("T")

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


@dataclass(frozen=True)
class _PdfInstance:
    """The FullDocument instance EPO offers as a PDF.

    Attributes:
        link: Image-service path to fetch pages from.
        pages: Page count from ``number-of-pages``. ``None`` when EPO omitted
            it, which the caller treats as "fetch page one and say so" rather
            than guessing a count.
    """

    link: str
    pages: int | None


def _parse_pdf_instance(inquiry_xml: bytes) -> _PdfInstance | None:
    """Extract the FullDocument PDF link path from an EPO image inquiry response.

    EPO advertises the available formats as the *text* of
    ``ops:document-format`` elements, wrapped in ``document-format-options``::

        <ops:document-instance desc="FullDocument" link="...">
          <ops:document-format-options>
            <ops:document-format>application/pdf</ops:document-format>

    The descendant axis is deliberate: it matches whether or not the wrapper
    is present, without depending on the exact nesting depth. Matching a
    ``desc`` attribute instead is what made this return ``None`` for every
    real patent while its hand-written fixtures passed (#371); verbatim
    captured responses now live in ``tests/fixtures/epo``.

    Only the FullDocument instance qualifies. A real response also carries
    ``Drawing`` and ``FirstPageClipping`` instances that offer
    ``application/pdf``, so matching on the format alone would hand back a
    thumbnail.

    Args:
        inquiry_xml: Raw XML bytes from ``published_data(..., endpoint='images')``.

    Returns:
        The FullDocument PDF instance, or ``None`` if no PDF is available.
    """
    try:
        root = _lxml_etree.fromstring(inquiry_xml)
        ns = {"ops": "http://ops.epo.org"}
        for el in root.xpath(
            "//ops:document-instance[@desc='FullDocument']", namespaces=ns
        ):
            formats = {
                str(text).strip()
                for text in el.xpath(".//ops:document-format/text()", namespaces=ns)
            }
            link = el.get("link")
            if "application/pdf" in formats and link is not None:
                return _PdfInstance(str(link), _page_count_of(el))
        return None
    except (RateLimitedError, EpoRateLimitedError):
        raise
    except _lxml_etree.LxmlError as exc:
        logger.warning("epo_pdf_link_parse_failed err=%s", exc)
        return None


def _page_count_of(element: Any) -> int | None:
    """Read ``number-of-pages`` off a document-instance element.

    Args:
        element: The ``ops:document-instance`` element.

    Returns:
        The page count, or ``None`` when the attribute is absent or not a
        positive integer.
    """
    raw = element.get("number-of-pages")
    if raw is None:
        return None
    try:
        pages = int(raw)
    except ValueError:
        logger.warning("epo_pdf_page_count_unparsable raw=%s", raw)
        return None
    return pages if pages > 0 else None


def _merge_pdf_pages(pages: list[bytes]) -> bytes:
    """Concatenate single-page PDFs into one document.

    Args:
        pages: One PDF per page, in document order.

    Returns:
        The merged PDF bytes.
    """
    writer = PdfWriter()
    for page_pdf in pages:
        for page in PdfReader(io.BytesIO(page_pdf)).pages:
            writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class EpoQuotaExhaustedError(RuntimeError):
    """Raised when EPO reports the daily quota spent (a ``black`` light).

    Subclasses :class:`RuntimeError`, which is what this condition was raised
    as before it had a type, so existing handlers keep working. Having the
    type means callers can distinguish "come back tomorrow" from "wait a
    minute" without matching on the message.
    """

    def __init__(self) -> None:
        super().__init__("EPO daily quota exhausted. Please try again tomorrow.")


class EpoRateLimitedError(RateLimitedError):
    """Raised when the EPO OPS API throttles a request."""

    def __init__(self, color: str, *, service: str = "_overall") -> None:
        self.color = color
        self.service = service
        super().__init__(f"EPO rate limited: {service}={color}")


EPO_REPORTED_ERRORS: tuple[type[Exception], ...] = (
    RateLimitedError,  # the base of EpoRateLimitedError; covers both
    EpoQuotaExhaustedError,
)
"""Upstream conditions the patent tools report to the caller as payloads.

Never swallow these. A handler that catches broadly and re-raises a
hand-written tuple has to be updated whenever a new EPO condition appears,
and missing one turns a reportable failure into a silent empty result --
which is exactly what happened to ``EpoQuotaExhaustedError`` when it gained
its own type. Re-raise on this name instead so there is one list to keep.
"""

_THROTTLE_CACHE_TTL_S = 60.0
"""How long a seen traffic-light colour is trusted without re-probing EPO."""

_THROTTLE_RETRY_DELAY_S = _THROTTLE_CACHE_TTL_S + 5.0
"""First backoff wait, deliberately longer than the throttle cache lives.

A shorter wait would be wasted: :meth:`EpoClient._is_service_throttled` still
holds the last-seen colour and would short-circuit the retry without ever
reaching EPO, so the attempt would fail exactly as the first one did and burn
a retry doing it. Waiting past the cache means every retry genuinely re-probes.
"""

_THROTTLE_MAX_RETRIES = 2
"""Retries after the first failure. With the delay above, roughly three
minutes of patience, which the traffic light usually clears well inside."""


def epo_error_payload(
    exc: Exception,
) -> dict[str, Any]:
    """Turn a terminal EPO failure into a caller-facing payload.

    Both cases are expected rather than exceptional, and both are more useful
    to the calling model as a payload it can reason about than as an error.
    The distinction that matters is whether waiting helps, so ``retryable``
    carries it explicitly instead of leaving the caller to read the message.

    Args:
        exc: The failure that survived :func:`with_epo_retry`.

    Returns:
        An error mapping with ``retryable`` set.
    """
    if isinstance(exc, EpoQuotaExhaustedError):
        logger.warning("epo_unavailable detail=%s", exc)
        return {"error": "epo_unavailable", "detail": str(exc), "retryable": False}
    logger.info("epo_throttled detail=%s", exc)
    return {
        "error": "rate_limited",
        "detail": str(exc),
        "retryable": True,
        "hint": (
            "The EPO service was busy and did not clear while waiting. "
            "Try calling this tool again in a minute or two."
        ),
    }


async def with_epo_retry(
    coro_func: Callable[[], Awaitable[T]],
    *,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> T:
    """Call *coro_func*, retrying with backoff while EPO reports a throttle.

    The EPO analogue of :func:`~._rate_limiter.with_s2_retry`. Without it a
    throttled call fails in milliseconds -- the traffic light is consulted
    before any network request -- which leaves nothing for the jobs framework
    to promote and hands the caller an immediate error instead of a result.

    Only :class:`EpoRateLimitedError` is retried. Daily-quota exhaustion
    arrives as :class:`EpoQuotaExhaustedError` and will not clear today, so
    it propagates on the first attempt rather than costing the caller several
    minutes of waiting for the same answer.

    Both knobs default to the module constants, resolved *at call time* so a
    test can shrink the wait by patching them rather than sleeping for real
    minutes.

    Args:
        coro_func: Zero-argument async callable to invoke.
        max_retries: Attempts after the first failure. Defaults to
            :data:`_THROTTLE_MAX_RETRIES`.
        base_delay: Seconds to wait before the first retry, doubled each time.
            Defaults to :data:`_THROTTLE_RETRY_DELAY_S`.

    Returns:
        Whatever *coro_func* returns.

    Raises:
        EpoRateLimitedError: If every attempt is throttled.
        EpoQuotaExhaustedError: Immediately, if EPO reports the daily quota
            spent -- it will not clear today, so waiting costs the caller
            minutes for the same answer.
    """
    retries = _THROTTLE_MAX_RETRIES if max_retries is None else max_retries
    delay_base = _THROTTLE_RETRY_DELAY_S if base_delay is None else base_delay
    for attempt in range(retries + 1):
        try:
            return await coro_func()
        except EpoRateLimitedError as exc:
            if attempt == retries:
                raise
            delay = delay_base * 2**attempt
            logger.info(
                "epo_throttled_retrying service=%s color=%s attempt=%d delay_s=%.0f",
                exc.service,
                exc.color,
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable: the loop either returns or raises")


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
        if time.monotonic() - self._throttle_cache_ts > _THROTTLE_CACHE_TTL_S:
            return False
        cached = self._throttle_cache
        color = cached.get(service, cached.get("_overall", "green"))
        return color not in ("green", "idle")

    def _throttle_color(self, service: str) -> str:
        """Resolve a service's cached traffic-light colour.

        Shares its fallback chain with :meth:`_is_service_throttled` so the
        two can never disagree -- reporting a colour of ``green`` while
        refusing to proceed is a contradiction a caller cannot act on.

        Args:
            service: The EPO service name, e.g. ``"images"``.

        Returns:
            The cached colour, falling back to the overall light.
        """
        cached = self._throttle_cache
        return cached.get(service, cached.get("_overall", "green"))

    def _check_throttle(self, response: Any, service: str = "_overall") -> None:
        """Check the throttle header and raise if the relevant service is throttled.

        Args:
            response: The HTTP response object with a ``headers`` dict-like attribute.
            service: The EPO service to check (e.g. ``"search"``, ``"retrieval"``,
                ``"inpadoc"``). Defaults to ``"_overall"``.

        Raises:
            EpoQuotaExhaustedError: If the daily quota is exhausted.
            EpoRateLimitedError: If the service color is not green or idle.
        """
        header = response.headers.get("X-Throttling-Control", "green")
        throttle = _parse_throttle_header(header)
        # Update cache
        self._throttle_cache = throttle
        self._throttle_cache_ts = time.monotonic()
        color = throttle.get(service, throttle["_overall"])
        if color == "black":
            raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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

    async def get_biblio(self, doc: DocdbNumber) -> PatentRecord:
        """Fetch bibliographic data for a single patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Parsed bibliographic metadata record (see :func:`parse_biblio_xml`).

        Raises:
            EpoRateLimitedError: When the EPO traffic light is not green.
        """
        if self._is_service_throttled("retrieval"):
            cached = self._throttle_cache
            color = cached.get("retrieval", cached.get("_overall", "red"))
            if color == "black":
                raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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
                raise EpoQuotaExhaustedError
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

        instance = _parse_pdf_instance(inquiry_resp.content)
        if instance is None:
            raise ValueError(
                f"No PDF available for patent {doc.country}{doc.number}{doc.kind or ''}"
            )

        if instance.pages is None:
            # Guessing a count would either truncate silently -- the defect
            # this replaced -- or hammer OPS until it 404s. One page, loudly.
            logger.warning(
                "epo_pdf_page_count_missing link=%s detail=fetching_first_page_only",
                instance.link,
            )
        page_count = instance.pages or 1

        # Step 2: download every page. OPS serves exactly one page per image
        # call -- Range is a page selector, not a range, and omitting it is a
        # 404 -- so the document is reassembled here (#379).
        logger.debug("epo_pdf_download link=%s pages=%d", instance.link, page_count)
        pages: list[bytes] = []
        for page_no in range(1, page_count + 1):
            pages.append(await self._fetch_pdf_page(instance.link, page_no))
        return await asyncio.to_thread(_merge_pdf_pages, pages)

    async def _fetch_pdf_page(self, link: str, page_no: int) -> bytes:
        """Fetch one page of a patent PDF, respecting the throttle first.

        The traffic light is checked before every page rather than once per
        document: a 21-page patent is 21 calls, and EPO can turn amber
        part-way through.

        Both the ``images`` and ``retrieval`` lights are consulted. Which of
        them OPS bills an image download against is not something the
        throttle header reveals, and confirming it would mean driving a
        shared quota off green, so this honours whichever is stricter.
        ``retrieval`` is tested first only so the error keeps naming the
        service this path has always named.

        Args:
            link: Image-service path from the inquiry response.
            page_no: 1-based page number.

        Returns:
            Raw PDF bytes for that single page.

        Raises:
            EpoQuotaExhaustedError: When the daily quota is spent.
            EpoRateLimitedError: When either light is not green.
        """
        # retrieval first: it is the light this path has always reported, so
        # an error keeps naming it when both are amber.
        for service in ("retrieval", "images"):
            if self._is_service_throttled(service):
                color = self._throttle_color(service)
                if color == "black":
                    raise EpoQuotaExhaustedError
                raise EpoRateLimitedError(color, service=service)

        async with self._lock:
            pdf_resp = await asyncio.to_thread(
                self._client.image,
                link,
                range=page_no,
                document_format="application/pdf",
            )
        # Names retrieval, but caches every colour in the header, so the next
        # page's pre-check sees a fresh images light too.
        self._check_throttle(pdf_resp, service="retrieval")
        return bytes(pdf_resp.content)

    async def aclose(self) -> None:
        """No-op cleanup.

        The underlying synchronous ``epo_ops.Client`` holds no persistent
        resources that require explicit teardown.
        """

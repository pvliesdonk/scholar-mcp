"""Patent search and retrieval MCP tools."""

from __future__ import annotations

import asyncio as _asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from pathlib import Path

    from fastmcp_pvl_core import Jobs, JobsConfig

    from ._npl_resolution import BookResolver

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool
from requests.exceptions import HTTPError

from ._book_enrichment import resolve_book_by_isbn
from ._epo_client import (
    EPO_REPORTED_ERRORS,
    EpoClient,
    epo_error_payload,
    with_epo_retry,
)
from ._epo_xml import biblio_has_data
from ._npl_resolution import resolve_npl_refs
from ._patent_numbers import DocdbNumber, normalize
from ._protocols import CacheProtocol
from ._s2_client import S2Client
from ._s2_jobs import register_s2_tool
from ._server_deps import get_service
from ._text_window import DEFAULT_MAX_TEXT_CHARS, page_text
from .domain import Service

logger = logging.getLogger(__name__)

# Mapping from date_type parameter to EPO CQL field name.
_DATE_FIELDS: dict[str, str] = {
    "publication": "pd",
    "filing": "ad",
    "priority": "prd",
}


_EPO_NOT_CONFIGURED: dict[str, Any] = {
    "error": "epo_not_configured",
    "detail": (
        "EPO OPS credentials are not set. "
        "Configure SCHOLAR_MCP_EPO_CONSUMER_KEY and "
        "SCHOLAR_MCP_EPO_CONSUMER_SECRET."
    ),
}
"""Answer for every patent tool when EPO credentials are absent.

Copied on return so a caller mutating the response cannot corrupt it.
"""


async def _run_epo(
    coro_func: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Run an EPO operation with backoff, reporting terminal failures.

    The single place the patent tools reach EPO through, so all four answer a
    throttle or an exhausted quota the same way.

    Args:
        coro_func: Zero-argument async callable performing the EPO work.

    Returns:
        The operation's result, or an error mapping from
        :func:`_epo_error_payload`.
    """
    try:
        return await with_epo_retry(coro_func)
    except EPO_REPORTED_ERRORS as exc:
        return epo_error_payload(exc)


EPO_SEARCH_RANGE_MAX = 100
"""Most results one OPS search request returns (``Range=1-100``), per EPO's
OPS FAQ; see ``docs/design/reference/epo-ops-search.md`` (#488)."""


def _cql_escape(s: str) -> str:
    """Escape special characters for EPO CQL double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _cql_date(value: str | None, name: str) -> str | None:
    """Normalise a ``YYYY-MM-DD`` or ``YYYYMMDD`` date to ``YYYYMMDD``.

    Args:
        value: The date, or ``None``.
        name: The parameter it came from, for the error.

    Returns:
        The digits, or ``None`` when *value* is empty.

    Raises:
        ValueError: When the date has anything but digits and hyphens.
    """
    if not value:
        return None
    digits = value.replace("-", "")
    if not digits.isdigit():
        raise ValueError(f"Invalid {name}: {value!r}")
    return digits


def _cql_date_clause(
    date_from: str | None, date_to: str | None, date_type: str
) -> str | None:
    """Build the CQL date-range clause, or ``None`` without a bound.

    Args:
        date_from: Lower bound, or ``None``.
        date_to: Upper bound, or ``None``.
        date_type: ``"publication"``, ``"filing"`` or ``"priority"``.

    Returns:
        A ``within``, ``>=`` or ``<=`` clause on the date field.
    """
    field = _DATE_FIELDS.get(date_type, "pd")
    d_from = _cql_date(date_from, "date_from")
    d_to = _cql_date(date_to, "date_to")
    if d_from is not None and d_to is not None:
        return f'{field} within "{d_from},{d_to}"'
    if d_from is not None:
        return f"{field} >= {d_from}"
    if d_to is not None:
        return f"{field} <= {d_to}"
    return None


def _build_cql(
    query: str | None = None,
    *,
    cpc_classification: str | None = None,
    applicant: str | None = None,
    inventor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    date_type: str = "publication",
    jurisdiction: str | None = None,
) -> str:
    """Build an EPO CQL query string from individual filter parameters.

    Translates tool parameters into Contextual Query Language (CQL) clauses
    joined with ``AND``.  When *query* is provided it is mapped to a
    title+abstract search (``ta=`` field); omitting it allows searching purely
    by structured filters (inventor, applicant, CPC, date, jurisdiction).

    Args:
        query: Free-text search string — mapped to ``ta="query"``.  Optional;
            when omitted the search relies entirely on the filter parameters.
        cpc_classification: CPC classification code, e.g. ``"H01M10/00"``.
        applicant: Applicant name, mapped to ``pa=``.
        inventor: Inventor name, mapped to ``in=``.
        date_from: Lower bound date string, e.g. ``"2020-01-01"`` or
            ``"20200101"``.
        date_to: Upper bound date string, e.g. ``"2023-12-31"`` or
            ``"20231231"``.
        date_type: Which date field to constrain — ``"publication"`` (``pd``),
            ``"filing"`` (``ad``), or ``"priority"`` (``prd``).
        jurisdiction: Two-letter patent authority code, e.g. ``"EP"`` or
            ``"WO"``.

    Returns:
        A CQL expression string ready for the EPO OPS search endpoint.

    Raises:
        ValueError: When no search criteria are provided at all.
    """
    text_fields = (
        ("ta", query),
        ("cpc", cpc_classification),
        ("pa", applicant),
        ("in", inventor),
    )
    parts = [f'{name}="{_cql_escape(v)}"' for name, v in text_fields if v is not None]
    date_clause = _cql_date_clause(date_from, date_to, date_type)
    if date_clause is not None:
        parts.append(date_clause)
    if jurisdiction is not None:
        parts.append(f'pn="{_cql_escape(jurisdiction)}"')

    if not parts:
        raise ValueError(
            "At least one search criterion is required: query, inventor, applicant, "
            "cpc_classification, jurisdiction, or a date range."
        )

    return " AND ".join(parts)


async def search_patents(
    query: str | None = None,
    cpc_classification: str | None = None,
    applicant: str | None = None,
    inventor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    date_type: Literal["publication", "filing", "priority"] = "publication",
    jurisdiction: str | None = None,
    limit: int = 10,
    offset: int = 0,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Search for patents in the European Patent Office database.

    Covers European patents and global patents via INPADOC (100+ patent
    offices). At least one parameter must be provided. For keyword search,
    ``query`` searches titles and abstracts. To find all patents by an
    inventor or applicant, omit ``query`` and use only the structured
    filters. For academic paper search, use search_papers instead.

    Returns at most 100 patents per call; a larger ``limit`` is capped at
    100, so page further with ``offset``. EPO serves only the first 2,000
    results of a search, so narrow the query rather than paging past them.

    When EPO reports itself busy this waits for it to clear, which can take a
    few minutes, so the call may answer with a job handle to poll using
    ``get_job_result`` rather than the result itself. Do not reason about EPO
    throttle states yourself.

    Args:
        query: Keyword search over patent titles and abstracts.
            Optional; omit when searching purely by inventor, applicant,
            CPC code, or date.
        cpc_classification: CPC classification code to filter by,
            such as ``"H01M10/00"`` for lithium-ion batteries.
        applicant: Applicant (assignee) name to filter by.
        inventor: Inventor name to filter by.
        date_from: Earliest date (``YYYY-MM-DD``).
        date_to: Latest date (``YYYY-MM-DD``).
        date_type: Date field to apply the range to: ``"publication"``,
            ``"filing"`` or ``"priority"``.
        jurisdiction: Restrict to a single patent authority, such as
            ``"EP"``, ``"WO"`` or ``"US"``.
        limit: Maximum results to return (default 10, max 100).
        offset: Pagination offset (0-based).
        service: Injected service.

    Returns:
        A mapping with ``total_count`` and a ``references`` list, or an
        error mapping if the EPO client is not configured or the API fails.
        A busy EPO service is waited out rather than failed on, which can
        take a few minutes; the call is then handed back as
        ``{"status": "working", "job_id": "..."}`` and the result retrieved
        with ``get_job_result``. If the service never clears, the outcome
        is ``{"error": "rate_limited", "retryable": true}`` with a hint,
        and an exhausted daily quota is ``{"error": "epo_unavailable",
        "retryable": false}``. Do not manage or reason about EPO throttle
        states directly.
    """
    epo = service.epo
    if epo is None:
        return dict(_EPO_NOT_CONFIGURED)

    try:
        cql = _build_cql(
            query,
            cpc_classification=cpc_classification,
            applicant=applicant,
            inventor=inventor,
            date_from=date_from,
            date_to=date_to,
            date_type=date_type,
            jurisdiction=jurisdiction,
        )
    except ValueError as exc:
        return {"error": "invalid_query", "detail": str(exc)}
    range_begin = offset + 1  # EPO OPS uses 1-based ranges
    range_end = offset + max(1, min(limit, EPO_SEARCH_RANGE_MAX))
    cache_key = f"{cql}|{range_begin}-{range_end}"

    cached = await service.cache.get_patent_search(cache_key)
    if cached is not None:
        logger.debug("patent_search_cache_hit cql=%s", cql)
        return cached

    result = await _run_epo(
        lambda: epo.search(cql, range_begin=range_begin, range_end=range_end)
    )
    if "error" in result:
        return result
    await service.cache.set_patent_search(cache_key, result)
    return result


async def get_patent(
    patent_number: str,
    sections: (
        list[Literal["biblio", "claims", "description", "family", "legal", "citations"]]
        | None
    ) = None,
    text_offset: int = 0,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Get detailed information about a single patent.

    Accepts patent numbers in any format (EP, WO, US, etc.). By default
    returns bibliographic data only; use the sections parameter to
    request additional detail (claims, description, family members, legal
    status, cited references). Claims and description come as Markdown:
    one numbered block per claim, and description paragraphs under ``##``
    section headings with their paragraph numbers (``[0001]``). The
    description is paged; when ``next_offset`` is present, call again with
    that value as ``text_offset``. Claims and description are null when EPO
    holds no full text for the publication; fetch_patent_pdf then has the
    document. When sections includes 'citations', non-patent literature
    references are resolved on a best-effort basis: one with a DOI or arXiv
    ID to a Semantic Scholar ``paper``, otherwise one with an ISBN to an Open
    Library ``book``. A reference with neither may carry a title-matched
    ``candidate`` with ``confidence: "unconfirmed"``: verify it before citing
    it. Every reference keeps its raw citation string, plus its ``isbn`` when
    it has one.

    When EPO reports itself busy this waits for it to clear, which can take a
    few minutes, so the call may answer with a job handle to poll using
    ``get_job_result`` rather than the result itself. Do not reason about EPO
    throttle states yourself.

    Args:
        patent_number: Patent number in any common format, such as
            ``"EP1234567A1"``, ``"WO2024/123456"`` or ``"US11,234,567B2"``.
        sections: Sections to include in the response. Defaults to
            ``["biblio"]``. Available sections: biblio, claims,
            description, family, legal, citations.
        text_offset: Character offset in the description at which the page
            starts.
        max_chars: Maximum description characters to return, capped at
            20,000; null returns the rest of the description.
        service: Injected service.

    Returns:
        A mapping with ``patent_number`` (normalised DOCDB format) and the
        requested section data, or an error mapping on failure. With a
        description, it also carries ``text_offset``,
        ``text_returned_chars``, ``text_total_chars``, ``text_truncated``
        and, when more follows, ``next_offset``, all counting description
        characters. A busy EPO service is waited out rather than failed on, which can
        take a few minutes; the call is then handed back as
        ``{"status": "working", "job_id": "..."}`` and the result retrieved
        with ``get_job_result``. If the service never clears, the outcome
        is ``{"error": "rate_limited", "retryable": true}`` with a hint,
        and an exhausted daily quota is ``{"error": "epo_unavailable",
        "retryable": false}``. Do not manage or reason about EPO throttle
        states directly.
    """
    epo = service.epo
    if epo is None:
        return dict(_EPO_NOT_CONFIGURED)

    try:
        doc = normalize(patent_number)
    except ValueError as exc:
        return {"error": "invalid_patent_number", "detail": str(exc)}

    effective_sections = (
        list(dict.fromkeys(sections)) if sections is not None else ["biblio"]
    )

    result = await _run_epo(
        lambda: _fetch_patent_sections(
            doc=doc,
            sections=effective_sections,
            epo=epo,
            cache=service.cache,
            s2=service.s2,
            resolve_book=lambda isbn: resolve_book_by_isbn(isbn, service),
        )
    )
    return page_text(
        result, "description", text_offset=text_offset, max_chars=max_chars
    )


async def get_citing_patents(
    paper_id: str,
    limit: int = 10,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Find patents that cite a given academic paper.

    Coverage is incomplete: it relies on EPO OPS citation search, which
    does not capture all patent-to-paper citations. Best results with
    DOIs of well-known, highly cited papers. Returns confirmed matches
    only, not an exhaustive list.

    When EPO reports itself busy this waits for it to clear, which can take a
    few minutes, so the call may answer with a job handle to poll using
    ``get_job_result`` rather than the result itself. Do not reason about EPO
    throttle states yourself.

    Args:
        paper_id: Paper identifier (DOI preferred, also accepts
            title keywords).
        limit: Maximum number of citing patents to return
            (default 10, max 25).
        service: Injected service.

    Returns:
        A mapping with ``paper_id``, a ``patents`` list (each with biblio
        data and ``match_source``), ``total_count``, and a ``note`` about
        coverage limitations.
        A busy EPO service is waited out rather than failed on, which can
        take a few minutes; the call is then handed back as
        ``{"status": "working", "job_id": "..."}`` and the result retrieved
        with ``get_job_result``. If the service never clears, the outcome
        is ``{"error": "rate_limited", "retryable": true}`` with a hint,
        and an exhausted daily quota is ``{"error": "epo_unavailable",
        "retryable": false}``. Do not manage or reason about EPO throttle
        states directly.
    """
    epo = service.epo
    if epo is None:
        return dict(_EPO_NOT_CONFIGURED)

    effective_limit = min(limit, 25)

    return await _run_epo(
        lambda: _get_citing_patents(paper_id=paper_id, epo=epo, limit=effective_limit)
    )


async def _download_patent_pdf(
    epo: EpoClient, doc: DocdbNumber, pdf_path: Path
) -> dict[str, Any] | None:
    """Fetch a patent PDF to *pdf_path* unless it is already there.

    A throttle is waited out by :func:`with_epo_retry` rather than failed on;
    because each wait outlasts the traffic-light cache, a throttled fetch
    runs long enough to be promoted to a background job. What survives the
    retries is reported as a payload rather than raised, so the caller keeps
    the guidance the old queue's poller used to synthesise.

    Args:
        epo: The configured EPO OPS client.
        doc: The normalised patent number.
        pdf_path: Destination path; an existing file short-circuits.

    Returns:
        ``None`` once the PDF is on disk, or an error mapping describing why
        it is not.
    """
    if pdf_path.exists():
        return None
    try:
        pdf_bytes = await with_epo_retry(lambda: epo.get_pdf(doc))
    except ValueError as exc:
        return {"error": "pdf_not_available", "detail": str(exc)}
    except EPO_REPORTED_ERRORS as exc:
        return epo_error_payload(exc)
    await _asyncio.to_thread(pdf_path.write_bytes, pdf_bytes)
    logger.info("patent_pdf_downloaded path=%s bytes=%d", pdf_path, len(pdf_bytes))
    return None


def _patent_pdf_stem(doc: DocdbNumber) -> str:
    """Return the cache filename stem for a patent's PDF and Markdown.

    The normalised DOCDB triple is already unique per publication, so the stem
    needs no hash suffix. The suffix it used to carry hashed the *raw* caller
    string, which split one patent across spellings: ``EP 3491801 B1`` and
    ``EP3491801B1`` produced different filenames, so the second call
    re-downloaded every page and re-ran the conversion (#402).

    Args:
        doc: Normalised patent number.

    Returns:
        Filename stem, for example ``patent_EP3491801B1``.
    """
    readable = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
    return f"patent_{readable}"


async def fetch_patent_pdf(
    patent_number: str,
    use_vlm: bool = False,
    text_offset: int = 0,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Download a patent PDF via authenticated EPO OPS and convert to Markdown.

    Downloads the full-document PDF for a patent using the authenticated
    EPO Open Patent Services session, saves it locally, and if docling is
    configured converts it to Markdown. EPO serves patent images one page
    per request, so a long patent costs one request per page and the
    document is reassembled before conversion.

    Not all patents have full text available through OPS: WO and older EP
    patents sometimes lack PDFs. Returns an error in that case.

    A previously downloaded and converted patent answers immediately;
    a fresh download plus conversion typically takes 1-5 minutes and is
    returned as a background job handle instead.

    When EPO reports itself busy this waits for it to clear, which can take a
    few minutes, so the call may answer with a job handle to poll using
    ``get_job_result`` rather than the result itself. Do not reason about EPO
    throttle states yourself.

    Markdown is returned in pages of at most 20,000 characters. When
    ``next_offset`` is present, call this tool again with that value as
    ``text_offset``; the cached conversion makes later pages inexpensive.
    Set ``max_chars`` to null only when the client can accept the complete
    document in one response.

    Args:
        patent_number: Patent number in any format (EP, WO, US and others),
            such as ``EP3491801B1``, ``EP 3491801 B1`` or ``US10123456B2``.
        use_vlm: Use VLM enrichment for formulas and figures (requires
            VLM to be configured).
        text_offset: Character offset at which the Markdown page starts.
        max_chars: Maximum Markdown characters to return, capped at 20,000.
            Pass ``null`` for the complete text.

    Returns:
        ``pdf_path`` and optionally ``markdown`` / ``md_path``.
    """
    epo = service.epo
    if epo is None:
        return dict(_EPO_NOT_CONFIGURED)

    try:
        doc = normalize(patent_number)
    except ValueError:
        return {
            "error": "invalid_patent_number",
            "detail": f"Could not parse patent number: {patent_number!r}",
        }

    stem = _patent_pdf_stem(doc)

    pdf_dir = service.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{stem}.pdf"

    error = await _download_patent_pdf(epo, doc, pdf_path)
    if error is not None:
        return error

    result: dict[str, Any] = {"pdf_path": str(pdf_path)}
    docling = service.docling
    if docling is None:
        return result

    vlm_suffix = "_vlm" if use_vlm and docling.vlm_available else ""
    md_dir = service.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{stem}{vlm_suffix}.md"

    if md_path.exists():
        markdown = await _asyncio.to_thread(md_path.read_text, encoding="utf-8")
    else:
        try:
            pdf_bytes_for_conv = await _asyncio.to_thread(pdf_path.read_bytes)
            markdown = await docling.convert(
                pdf_bytes_for_conv, pdf_path.name, use_vlm=use_vlm
            )
        except Exception:
            # Conversion is optional enrichment: the PDF is already on
            # disk, so report that rather than failing the whole call.
            logger.exception("docling_convert_failed path=%s", pdf_path)
            return result
        await _asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

    result["markdown"] = markdown
    result["md_path"] = str(md_path)
    result["vlm_used"] = use_vlm and docling.vlm_available
    skip_reason = docling.vlm_skip_reason(use_vlm)
    if skip_reason:
        result["vlm_skip_reason"] = skip_reason
    return page_text(
        result,
        "markdown",
        text_offset=text_offset,
        max_chars=max_chars,
    )


# The reference page these tools are listed on (scripts/gen_reference.py).
_GROUP = "group:patents"


def register_patent_tools(
    mcp: FastMCP, jobs: Jobs, jobs_config: JobsConfig | None = None
) -> None:
    """Register patent search and retrieval tools on *mcp*.

    Each tool is a module-level coroutine registered here rather than a
    closure defined inside this function, so a tool's own complexity is
    budgeted against the tool instead of accumulating on the registrar.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics. Every tool here is long-running:
            EPO throttling is waited out rather than failed on, so a
            throttled call is promoted to a background job.
    """
    register_long_running_tool(
        mcp,
        jobs,
        tags={_GROUP, "patent"},
        annotations={
            "title": "Search Patents",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(search_patents)
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        tags={_GROUP, "patent"},
        annotations={
            "title": "Get Patent",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_patent)
    register_long_running_tool(
        mcp,
        jobs,
        tags={_GROUP, "patent"},
        annotations={
            "title": "Get Citing Patents",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_citing_patents)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Fetch Patent PDF",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        # Both visibility tags matter: "write" hides it in read-only mode,
        # "patent" hides it when EPO is unconfigured. `disable` matches on any
        # tag, so carrying both keeps it in step with its three siblings (#316).
        # _GROUP only names its reference page.
        tags={_GROUP, "write", "patent"},
    )(fetch_patent_pdf)


# All available patent sections.
_AVAILABLE_SECTIONS = {
    "biblio",
    "claims",
    "description",
    "family",
    "legal",
    "citations",
}


def _is_http_404(exc: HTTPError) -> bool:
    """Return whether an OPS ``HTTPError`` carries a 404 response.

    Args:
        exc: The error raised by python-epo-ops-client.

    Returns:
        ``True`` when the response status is 404.
    """
    return exc.response is not None and exc.response.status_code == 404


async def _fetch_fulltext(
    get_cached: Callable[[], Awaitable[str | None]],
    fetch: Callable[[], Awaitable[str]],
    store: Callable[[str], Awaitable[None]],
) -> str | None:
    """Read a claims or description section, from the cache or from EPO.

    OPS answers 404 when it holds no full text for a publication, which is
    common (US11234567B2 has none), so that is ``None`` rather than a
    failure. It is not cached: the next call asks again.

    Args:
        get_cached: Reads the cached text, ``None`` when absent.
        fetch: Fetches and parses the section from EPO.
        store: Caches fetched text.

    Returns:
        The section text, or ``None`` when EPO has no full text.
    """
    cached = await get_cached()
    if cached is not None:
        return cached
    try:
        text = await fetch()
    except HTTPError as exc:
        if not _is_http_404(exc):
            raise
        return None
    await store(text)
    return text


@dataclass(frozen=True)
class _SectionContext:
    """What every section fetcher of one ``get_patent`` call needs."""

    doc: DocdbNumber
    epo: EpoClient
    cache: CacheProtocol
    s2: S2Client | None
    resolve_book: BookResolver | None

    @property
    def patent_id(self) -> str:
        """The DOCDB number the caches are keyed on."""
        return self.doc.docdb


async def _cached(
    get_cached: Callable[[], Awaitable[Any]],
    fetch: Callable[[], Awaitable[Any]],
    store: Callable[[Any], Awaitable[None]],
) -> Any:
    """Return a cached section, or fetch it from EPO and cache it.

    Args:
        get_cached: Reads the cached value, ``None`` when absent.
        fetch: Fetches the section from EPO.
        store: Caches a fetched value.

    Returns:
        The section value.
    """
    cached = await get_cached()
    if cached is not None:
        return cached
    value = await fetch()
    await store(value)
    return value


async def _section_biblio(ctx: _SectionContext) -> dict[str, Any]:
    """Fetch the biblio section, which also tells whether the patent exists.

    Args:
        ctx: Section context.

    Returns:
        ``{"biblio": ...}``, or ``{"_not_found": True}`` when OPS has no such
        publication.
    """
    cached = await ctx.cache.get_patent(ctx.patent_id)
    if cached is not None:
        return {"biblio": cached}
    try:
        biblio = await ctx.epo.get_biblio(ctx.doc)
    except HTTPError as exc:
        if not _is_http_404(exc):
            raise
        # OPS answers a nonexistent publication with 404 (#475).
        return {"_not_found": True}
    if not biblio_has_data(biblio):
        return {"_not_found": True}
    await ctx.cache.set_patent(ctx.patent_id, biblio)
    return {"biblio": biblio}


async def _section_claims(ctx: _SectionContext) -> dict[str, Any]:
    """Fetch the claims section (see :func:`_fetch_fulltext`)."""
    claims = await _fetch_fulltext(
        lambda: ctx.cache.get_patent_claims(ctx.patent_id),
        lambda: ctx.epo.get_claims(ctx.doc),
        lambda text: ctx.cache.set_patent_claims(ctx.patent_id, text),
    )
    return {"claims": claims}


async def _section_description(ctx: _SectionContext) -> dict[str, Any]:
    """Fetch the description section (see :func:`_fetch_fulltext`)."""
    description = await _fetch_fulltext(
        lambda: ctx.cache.get_patent_description(ctx.patent_id),
        lambda: ctx.epo.get_description(ctx.doc),
        lambda text: ctx.cache.set_patent_description(ctx.patent_id, text),
    )
    return {"description": description}


async def _section_family(ctx: _SectionContext) -> dict[str, Any]:
    """Fetch the family section."""
    family = await _cached(
        lambda: ctx.cache.get_patent_family(ctx.patent_id),
        lambda: ctx.epo.get_family(ctx.doc),
        lambda value: ctx.cache.set_patent_family(ctx.patent_id, value),
    )
    return {"family": family}


async def _section_legal(ctx: _SectionContext) -> dict[str, Any]:
    """Fetch the legal-events section."""
    legal = await _cached(
        lambda: ctx.cache.get_patent_legal(ctx.patent_id),
        lambda: ctx.epo.get_legal(ctx.doc),
        lambda value: ctx.cache.set_patent_legal(ctx.patent_id, value),
    )
    return {"legal": legal}


async def _section_citations(ctx: _SectionContext) -> dict[str, Any]:
    """Fetch the citations section, resolving its NPL references.

    Only the raw EPO citations are cached; NPL resolution reruns on every
    call so it reflects the current paper and book indexes.

    Args:
        ctx: Section context.

    Returns:
        ``{"citations": {"patent_refs": [...], "npl_refs": [...]}}``.
    """
    citations = await _cached(
        lambda: ctx.cache.get_patent_citations(ctx.patent_id),
        lambda: ctx.epo.get_citations(ctx.doc),
        lambda value: ctx.cache.set_patent_citations(ctx.patent_id, value),
    )
    npl_refs = await resolve_npl_refs(
        citations["npl_refs"],
        s2=ctx.s2,
        resolve_book=ctx.resolve_book,
        patent_id=ctx.patent_id,
    )
    return {
        "citations": {"patent_refs": citations["patent_refs"], "npl_refs": npl_refs}
    }


_SECTION_FETCHERS: dict[str, Callable[[_SectionContext], Awaitable[dict[str, Any]]]] = {
    "biblio": _section_biblio,
    "claims": _section_claims,
    "description": _section_description,
    "family": _section_family,
    "legal": _section_legal,
    "citations": _section_citations,
}


def _raise_section_failure(outcomes: Sequence[object]) -> None:
    """Re-raise the first section failure, EPO's reportable states first.

    A throttle or exhausted quota must reach ``_run_epo``'s retry and
    reporting, whichever section happened to fail first.

    Args:
        outcomes: What each section fetcher returned or raised.

    Raises:
        BaseException: The first EPO-reported error, else the first failure.
    """
    for outcome in outcomes:
        if isinstance(outcome, EPO_REPORTED_ERRORS):
            raise outcome
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome


async def _fetch_patent_sections(
    *,
    doc: DocdbNumber,
    sections: Sequence[str],
    epo: EpoClient,
    cache: CacheProtocol,
    s2: S2Client | None = None,
    resolve_book: BookResolver | None = None,
) -> dict[str, Any]:
    """Fetch requested sections for a patent, with caching.

    Sections are fetched concurrently via ``asyncio.gather``.  Actual EPO
    API calls are serialised by the ``asyncio.Lock`` inside ``EpoClient``,
    so no additional concurrency limiting is needed here.  When the
    ``citations`` section is requested, non-patent literature (NPL)
    references are resolved on a best-effort basis
    (:func:`scholar_mcp._npl_resolution.resolve_npl_refs`).

    Args:
        doc: Normalised DOCDB patent number.
        sections: List of section names to include.
        epo: EPO client instance.
        cache: Cache instance with patent get/set methods.
        s2: Optional S2 client for NPL resolution.
        resolve_book: Optional ISBN lookup for NPL references that cite a
            book; without it, no book is resolved.

    Returns:
        A mapping with patent_number and the requested section data.
    """
    ctx = _SectionContext(doc, epo, cache, s2, resolve_book)
    names = [s for s in sections if s in _SECTION_FETCHERS]
    # Always probe biblio for not-found detection, even when not requested.
    if "biblio" not in names:
        names.append("biblio")
    outcomes = await _asyncio.gather(
        *(_SECTION_FETCHERS[name](ctx) for name in names), return_exceptions=True
    )
    parts = [o for o in outcomes if isinstance(o, dict)]

    # A nonexistent patent also fails every other section, so their errors
    # give way to the not-found answer.
    if any(part.get("_not_found") for part in parts):
        return {
            "error": "patent_not_found",
            "detail": (
                f"Patent {ctx.patent_id} not found or has no data. "
                "Check the number format."
            ),
        }
    _raise_section_failure(outcomes)

    result: dict[str, Any] = {"patent_number": ctx.patent_id}
    for part in parts:
        result.update(part)
    # Drop biblio when it was fetched only as the not-found probe.
    if "biblio" not in sections:
        result.pop("biblio", None)
    return result


async def _get_citing_patents(
    *,
    paper_id: str,
    epo: EpoClient,
    limit: int = 10,
) -> dict[str, Any]:
    """Search EPO OPS for patents citing a paper.

    Uses the ``ct=`` (cited document) CQL field to find patents whose
    cited references mention the given identifier. Fetches biblio for
    each result.

    Args:
        paper_id: Paper identifier (DOI or keywords).
        epo: EPO client instance.
        limit: Max results.

    Returns:
        A mapping with paper_id, a patents list, total_count, and note.
    """
    cql = f'ct="{_cql_escape(paper_id)}"'
    try:
        search_result = await epo.search(cql, range_begin=1, range_end=limit)
    except EPO_REPORTED_ERRORS:
        # Reportable upstream state: let it reach _run_epo, which turns it
        # into a payload. Swallowing it here would answer a throttle or an
        # exhausted quota with an empty, successful-looking result.
        raise
    except Exception:
        logger.warning("citing_patent_search_failed paper=%s", paper_id)
        return {
            "paper_id": paper_id,
            "patents": [],
            "total_count": 0,
            "note": "EPO citation search failed. Try a different identifier format.",
        }

    patents: list[dict[str, Any]] = []
    for ref in search_result.get("references", []):
        doc = DocdbNumber(ref["country"], ref["number"], ref.get("kind", ""))
        try:
            biblio = await epo.get_biblio(doc)
            patents.append({**biblio, "match_source": "epo_search"})
        except EPO_REPORTED_ERRORS:
            raise
        except Exception:
            logger.warning("citing_patent_biblio_failed patent=%s", doc.docdb)

    return {
        "paper_id": paper_id,
        "patents": patents,
        "total_count": search_result.get("total_count", 0),
        "note": (
            "Coverage is incomplete. Results come from EPO OPS citation "
            "search and may not capture all patent-to-paper citations."
        ),
    }

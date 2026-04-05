"""Patent search and retrieval MCP tools."""

from __future__ import annotations

import asyncio as _asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._epo_client import EpoClient, EpoRateLimitedError
from ._patent_numbers import DocdbNumber, normalize
from ._rate_limiter import RateLimitedError
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

# Mapping from date_type parameter to EPO CQL field name.
_DATE_FIELDS: dict[str, str] = {
    "publication": "pd",
    "filing": "ad",
    "priority": "prd",
}


def _cql_escape(s: str) -> str:
    """Escape special characters for EPO CQL double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_cql(
    query: str,
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
    joined with ``AND``.  The *query* text is always mapped to a title+abstract
    search (``ta=`` field).

    Args:
        query: Free-text search string — mapped to ``ta="query"``.
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
    """
    parts: list[str] = [f'ta="{_cql_escape(query)}"']

    if cpc_classification is not None:
        parts.append(f'cpc="{_cql_escape(cpc_classification)}"')

    if applicant is not None:
        parts.append(f'pa="{_cql_escape(applicant)}"')

    if inventor is not None:
        parts.append(f'in="{_cql_escape(inventor)}"')

    if date_from is not None or date_to is not None:
        field = _DATE_FIELDS.get(date_type, "pd")
        # Normalise YYYY-MM-DD → YYYYMMDD
        d_from = date_from.replace("-", "") if date_from else None
        d_to = date_to.replace("-", "") if date_to else None
        if d_from and not d_from.isdigit():
            raise ValueError(f"Invalid date_from: {date_from!r}")
        if d_to and not d_to.isdigit():
            raise ValueError(f"Invalid date_to: {date_to!r}")
        if d_from is not None and d_to is not None:
            parts.append(f"{field} within {d_from},{d_to}")
        elif d_from is not None:
            parts.append(f"{field} >= {d_from}")
        else:
            parts.append(f"{field} <= {d_to}")

    if jurisdiction is not None:
        parts.append(f'pn="{_cql_escape(jurisdiction)}"')

    return " AND ".join(parts)


def register_patent_tools(mcp: FastMCP) -> None:
    """Register patent search and retrieval tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        tags={"patent"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_patents(
        query: str,
        cpc_classification: str | None = None,
        applicant: str | None = None,
        inventor: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        date_type: Literal["publication", "filing", "priority"] = "publication",
        jurisdiction: str | None = None,
        limit: int = 10,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search for patents in the European Patent Office database.

        Covers European patents and global patents via INPADOC (100+ patent
        offices). Accepts natural language queries. Use CPC classification
        codes, applicant names, or date ranges to narrow results. For
        academic paper search, use search_papers instead.

        Args:
            query: Natural language or keyword search query.
            cpc_classification: CPC classification code to filter by,
                e.g. ``"H01M10/00"`` for lithium-ion batteries.
            applicant: Applicant (assignee) name to filter by.
            inventor: Inventor name to filter by.
            date_from: Earliest date (``YYYY-MM-DD``).
            date_to: Latest date (``YYYY-MM-DD``).
            date_type: Date field to apply range to — ``"publication"``,
                ``"filing"``, or ``"priority"``.
            jurisdiction: Restrict to a single patent authority, e.g.
                ``"EP"``, ``"WO"``, or ``"US"``.
            limit: Maximum results to return (default 10).
            offset: Pagination offset (0-based).
            bundle: Injected service bundle.

        Returns:
            JSON string with ``total_count`` and ``references`` list, or an
            error dict if the EPO client is not configured or the API fails.
        """
        if bundle.epo is None:
            return json.dumps(
                {
                    "error": "epo_not_configured",
                    "detail": (
                        "EPO OPS credentials are not set. "
                        "Configure SCHOLAR_MCP_EPO_CONSUMER_KEY and "
                        "SCHOLAR_MCP_EPO_CONSUMER_SECRET."
                    ),
                }
            )

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
        range_begin = offset + 1  # EPO OPS uses 1-based ranges
        range_end = offset + limit
        cache_key = f"{cql}|{range_begin}-{range_end}"

        # Check cache first
        cached = await bundle.cache.get_patent_search(cache_key)
        if cached is not None:
            logger.debug("patent_search_cache_hit cql=%s", cql)
            return json.dumps(cached)

        async def _execute(*, retry: bool = True) -> str:
            # Note: retry flag is accepted for task queue compatibility but
            # EPO client does not yet have a retry-aware path (unlike S2).
            # The queued re-attempt still defers work away from the request.
            result = await bundle.epo.search(  # type: ignore[union-attr]
                cql,
                range_begin=range_begin,
                range_end=range_end,
            )
            await bundle.cache.set_patent_search(cache_key, result)
            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except (RateLimitedError, EpoRateLimitedError):
            task_id = bundle.tasks.submit(_execute(retry=True), tool="search_patents")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "search_patents"}
            )

    @mcp.tool(
        tags={"patent"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_patent(
        patent_number: str,
        sections: (
            list[
                Literal[
                    "biblio", "claims", "description", "family", "legal", "citations"
                ]
            ]
            | None
        ) = None,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Get detailed information about a single patent.

        Accepts patent numbers in any format (EP, WO, US, etc.). By default
        returns bibliographic data only -- use the sections parameter to
        request additional detail (claims, description, family members, legal
        status, cited references). When sections includes 'citations',
        non-patent literature references are resolved to Semantic Scholar
        papers on a best-effort basis; unresolved references are returned as
        raw citation strings.

        Args:
            patent_number: Patent number in any common format, e.g.
                ``"EP1234567A1"``, ``"WO2024/123456"``, or ``"US11,234,567B2"``.
            sections: Sections to include in the response. Defaults to
                ``["biblio"]``. Available sections: biblio, claims,
                description, family, legal.  Citations reserved for Phase 3.
            bundle: Injected service bundle.

        Returns:
            JSON string with ``patent_number`` (normalised DOCDB format) and
            the requested section data, or an error dict on failure.
        """
        if bundle.epo is None:
            return json.dumps(
                {
                    "error": "epo_not_configured",
                    "detail": (
                        "EPO OPS credentials are not set. "
                        "Configure SCHOLAR_MCP_EPO_CONSUMER_KEY and "
                        "SCHOLAR_MCP_EPO_CONSUMER_SECRET."
                    ),
                }
            )

        try:
            doc = normalize(patent_number)
        except ValueError as exc:
            return json.dumps(
                {
                    "error": "invalid_patent_number",
                    "detail": str(exc),
                }
            )

        effective_sections = sections if sections is not None else ["biblio"]

        async def _execute(*, retry: bool = True) -> str:
            # Note: retry flag accepted for task queue compatibility;
            # EPO client does not yet have a retry-aware path.
            return await _fetch_patent_sections(
                doc=doc,
                sections=effective_sections,
                epo=bundle.epo,  # type: ignore[arg-type]
                cache=bundle.cache,
            )

        try:
            return await _execute(retry=False)
        except (RateLimitedError, EpoRateLimitedError):
            task_id = bundle.tasks.submit(_execute(retry=True), tool="get_patent")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "get_patent"}
            )


# Sections available in Phase 2 (fetched concurrently).
_AVAILABLE_SECTIONS = {"biblio", "claims", "description", "family", "legal"}

# Maximum concurrent EPO requests per get_patent call.
_SECTION_CONCURRENCY = 3


async def _fetch_patent_sections(
    *,
    doc: DocdbNumber,
    sections: Sequence[str],
    epo: EpoClient,
    cache: Any,
) -> str:
    """Fetch requested sections for a patent, with cache and concurrency.

    Sections are fetched concurrently (bounded by a semaphore) and each
    result is cached independently.  Sections not yet implemented
    (e.g. ``"citations"``) produce a notice rather than an error.

    Args:
        doc: Normalised DOCDB patent number.
        sections: List of section names to include.
        epo: EPO client instance.
        cache: Cache instance with patent get/set methods.

    Returns:
        JSON string with patent_number and requested section data.
    """
    patent_id = doc.docdb
    result: dict[str, Any] = {"patent_number": patent_id}
    sem = _asyncio.Semaphore(_SECTION_CONCURRENCY)

    async def _fetch_biblio() -> None:
        cached = await cache.get_patent(patent_id)
        if cached is not None:
            result["biblio"] = cached
            return
        async with sem:
            biblio = await epo.get_biblio(doc)
        if not biblio.get("title") and not biblio.get("applicants"):
            result["_not_found"] = True
            return
        await cache.set_patent(patent_id, biblio)
        result["biblio"] = biblio

    async def _fetch_claims() -> None:
        cached = await cache.get_patent_claims(patent_id)
        if cached is not None:
            result["claims"] = cached
            return
        async with sem:
            claims = await epo.get_claims(doc)
        await cache.set_patent_claims(patent_id, claims)
        result["claims"] = claims

    async def _fetch_description() -> None:
        cached = await cache.get_patent_description(patent_id)
        if cached is not None:
            result["description"] = cached
            return
        async with sem:
            desc = await epo.get_description(doc)
        await cache.set_patent_description(patent_id, desc)
        result["description"] = desc

    async def _fetch_family() -> None:
        cached = await cache.get_patent_family(patent_id)
        if cached is not None:
            result["family"] = cached
            return
        async with sem:
            family = await epo.get_family(doc)
        await cache.set_patent_family(patent_id, family)
        result["family"] = family

    async def _fetch_legal() -> None:
        cached = await cache.get_patent_legal(patent_id)
        if cached is not None:
            result["legal"] = cached
            return
        async with sem:
            legal = await epo.get_legal(doc)
        await cache.set_patent_legal(patent_id, legal)
        result["legal"] = legal

    fetcher_map: dict[str, Any] = {
        "biblio": _fetch_biblio,
        "claims": _fetch_claims,
        "description": _fetch_description,
        "family": _fetch_family,
        "legal": _fetch_legal,
    }

    fetchers = [fetcher_map[s]() for s in sections if s in fetcher_map]
    await _asyncio.gather(*fetchers)

    # Detect not-found from biblio fetch
    if result.pop("_not_found", False):
        return json.dumps(
            {
                "error": "patent_not_found",
                "detail": (
                    f"Patent {patent_id} not found or has no data. "
                    "Check the number format."
                ),
            }
        )

    # Note any sections not yet available (e.g. citations)
    unavailable = [s for s in sections if s not in _AVAILABLE_SECTIONS]
    if unavailable:
        result["notice"] = (
            f"Sections {unavailable} are not yet available. Coming in Phase 3."
        )

    return json.dumps(result)

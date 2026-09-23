"""Search and retrieval MCP tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._paper_cache import resolve_paper
from ._s2_client import FIELD_SETS, s2_error_payload
from ._s2_jobs import register_s2_tool
from ._server_deps import get_service
from .domain import Service

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs, JobsConfig


def _covers_author_page(cached: dict[str, Any], limit: int) -> bool:
    """Return whether a cached author record can answer a request for *limit*.

    A record is authoritative when it carries at least as many publications as
    the caller asked for, or when it already holds every publication the author
    has. The second case matters because a cached record shorter than *limit*
    is not necessarily incomplete — the author may simply have fewer papers.

    Args:
        cached: The cached author record.
        limit: Publications the caller asked for.

    Returns:
        True when the record can be served without a live request.
    """
    papers = cached.get("papers") or []
    total = cached.get("paperCount")
    wanted = min(limit, total) if isinstance(total, int) else limit
    return len(papers) >= wanted


def _author_page(data: dict[str, Any], limit: int) -> dict[str, Any]:
    """Return a copy of *data* whose ``papers`` list is cut to *limit*.

    A negative *limit* is treated as zero, so it yields no publications
    rather than trimming that many from the end of the list.

    Args:
        data: An author record, cached or freshly fetched.
        limit: Publications per page.

    Returns:
        A copy of *data* holding at most *limit* publications.
    """
    page = dict(data)
    papers = page.get("papers")
    if isinstance(papers, list):
        page["papers"] = papers[: max(0, limit)]
    return page


async def search_papers(
    query: str,
    fields: Literal["compact", "standard", "full"] = "compact",
    limit: int = 10,
    offset: int = 0,
    year_start: int | None = None,
    year_end: int | None = None,
    fields_of_study: list[str] | None = None,
    venue: str | None = None,
    min_citations: int | None = None,
    sort: Literal["relevance", "citations", "year"] = "relevance",
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Search Semantic Scholar for papers matching a query.

    Usually completes in a few seconds.

    Answers directly in normal use. Should the call run long it continues in
    the background and returns a job handle to poll with ``get_job_result``.

    Args:
        query: Keyword or semantic search query.
        fields: Field set preset — compact, standard, or full.
        limit: Maximum results to return (max 100).
        offset: Pagination offset.
        year_start: Earliest publication year (inclusive).
        year_end: Latest publication year (inclusive).
        fields_of_study: Filter by fields, e.g. ["Computer Science"].
        venue: Filter by venue name.
        min_citations: Minimum citation count.
        sort: Sort order — relevance, citations, or year.
        service: Injected service.

    Returns:
        A mapping with ``data`` (list of papers) and ``total``.
    """
    year: str | None = None
    if year_start is not None and year_end is not None:
        year = f"{year_start}-{year_end}"
    elif year_start is not None:
        year = f"{year_start}-"
    elif year_end is not None:
        year = f"-{year_end}"

    s2_sort = {
        "relevance": None,
        "citations": "citationCount:desc",
        "year": "publicationDate:desc",
    }.get(sort)
    fos = ",".join(fields_of_study) if fields_of_study else None

    try:
        return await service.s2.search_papers(
            query,
            fields=FIELD_SETS[fields],
            limit=limit,
            offset=offset,
            year=year,
            fieldsOfStudy=fos,
            venue=venue,
            minCitationCount=min_citations,
            sort=s2_sort,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": query}
        return s2_error_payload(exc)


async def get_paper(
    identifier: str,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Fetch full metadata for a single paper.

    A cached paper answers immediately. Otherwise the record is fetched and
    enriched; should that run long it continues in the background and returns
    a job handle to poll with ``get_job_result``.

    Args:
        identifier: Paper identifier — DOI, S2 paper ID, arXiv ID
            (prefix with ``ARXIV:``), ACM ID (``ACM:``), or PubMed ID
            (``PMID:``).
        service: Injected service.

    Returns:
        A mapping with full paper metadata, or
        ``{"error": "not_found", "identifier": "..."}`` if not found.
    """
    try:
        paper = await resolve_paper(service.cache, service.s2.get_paper, identifier)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": identifier}
        return s2_error_payload(exc)

    await service.enrichment.enrich([paper], service, tags=frozenset({"papers"}))
    return dict(paper)


async def get_author(
    identifier: str,
    limit: int = 20,
    offset: int = 0,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Fetch author profile and publications, or search by name.

    If *identifier* looks like a numeric S2 author ID, fetches the author
    directly. Otherwise performs a name search and returns up to 5 candidates
    for disambiguation.

    Answers directly in normal use. Should the call run long it continues in
    the background and returns a job handle to poll with ``get_job_result``.

    Args:
        identifier: S2 author ID (numeric string) or free-text author name.
        limit: Publications per page (only used for direct ID lookup).
        offset: Publication page offset (only used for direct ID lookup).
        service: Injected service.

    Returns:
        A mapping with author data and a paginated ``papers`` list, or
        ``{"candidates": [...]}`` for name searches.
    """
    if identifier.isdigit():
        if offset == 0:
            cached = await service.cache.get_author(identifier)
            if cached is not None and _covers_author_page(cached, limit):
                return _author_page(cached, limit)
        try:
            data = await service.s2.get_author(identifier, limit=limit, offset=offset)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"error": "not_found", "identifier": identifier}
            return s2_error_payload(exc)
        if offset == 0:
            await service.cache.set_author(identifier, data)
        return _author_page(data, limit)

    # Name search — return candidates for disambiguation
    try:
        candidates = await service.s2.search_authors(identifier, limit=5)
    except httpx.HTTPStatusError as exc:
        return s2_error_payload(exc)
    return {"candidates": candidates}


def register_search_tools(
    mcp: FastMCP, jobs: Jobs, jobs_config: JobsConfig | None = None
) -> None:
    """Register search and retrieval tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics. These tools defer promptly on an S2
            throttle, then continue retrying through the job.
    """
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        annotations={
            "title": "Search Papers",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(search_papers)
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        annotations={
            "title": "Get Paper",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_paper)
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        annotations={
            "title": "Get Author",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_author)

"""Search and retrieval MCP tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._s2_client import FIELD_SETS, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

logger = logging.getLogger(__name__)


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
    bundle: ServiceBundle = Depends(get_bundle),
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
        bundle: Injected service bundle.

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
        return await bundle.s2.search_papers(
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
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Fetch full metadata for a single paper.

    A cached paper answers immediately. Otherwise the record is fetched and
    enriched; should that run long it continues in the background and returns
    a job handle to poll with ``get_job_result``.

    Args:
        identifier: Paper identifier — DOI, S2 paper ID, arXiv ID
            (prefix with ``ARXIV:``), ACM ID (``ACM:``), or PubMed ID
            (``PMID:``).
        bundle: Injected service bundle.

    Returns:
        A mapping with full paper metadata, or
        ``{"error": "not_found", "identifier": "..."}`` if not found.
    """
    cached_id = await bundle.cache.get_alias(identifier) or identifier
    data = await bundle.cache.get_paper(cached_id)
    if data:
        logger.debug("cache_hit identifier=%s", identifier)
        await bundle.enrichment.enrich([data], bundle, tags=frozenset({"papers"}))
        return dict(data)

    try:
        fetched = await bundle.s2.get_paper(identifier)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": identifier}
        return s2_error_payload(exc)

    paper_id: str = fetched.get("paperId") or ""
    if paper_id:
        await bundle.cache.set_paper(paper_id, fetched)
        if identifier != paper_id:
            await bundle.cache.set_alias(identifier, paper_id)

    await bundle.enrichment.enrich([fetched], bundle, tags=frozenset({"papers"}))
    return dict(fetched)


async def get_author(
    identifier: str,
    limit: int = 20,
    offset: int = 0,
    bundle: ServiceBundle = Depends(get_bundle),
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
        bundle: Injected service bundle.

    Returns:
        A mapping with author data and a paginated ``papers`` list, or
        ``{"candidates": [...]}`` for name searches.
    """
    if identifier.isdigit():
        if offset == 0:
            cached = await bundle.cache.get_author(identifier)
            if cached:
                return dict(cached)
        try:
            data = await bundle.s2.get_author(identifier, limit=limit, offset=offset)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"error": "not_found", "identifier": identifier}
            return s2_error_payload(exc)
        if offset == 0:
            await bundle.cache.set_author(identifier, data)
        return dict(data)

    # Name search — return candidates for disambiguation
    try:
        candidates = await bundle.s2.search_authors(identifier, limit=5)
    except httpx.HTTPStatusError as exc:
        return s2_error_payload(exc)
    return {"candidates": candidates}


def register_search_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register search and retrieval tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics. These tools always retry a rate-limited
            upstream, so a throttled call runs long enough to be promoted
            rather than being handed back as an error.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Search Papers",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(search_papers)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get Paper",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_paper)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get Author",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_author)

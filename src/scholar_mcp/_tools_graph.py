"""Citation graph MCP tools."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._s2_client import FIELD_SETS, log_s2_error, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

logger = logging.getLogger(__name__)

# Pagination limits for client-side min_citations filtering.
# S2 returns citations newest-first; high-citation papers are typically
# older, so we must paginate deeply to reach them.
_S2_PAGE_SIZE = 1000
_MAX_UPSTREAM_SCAN = 10_000  # get_citations tool
_MAX_PER_NODE_SCAN = 5_000  # get_citation_graph BFS per node


@dataclass
class _FilteredScan:
    """Outcome of paginating S2 while filtering on citation count.

    Attributes:
        items: The citations that met the threshold, in upstream order.
        scanned: How many upstream records were examined.
        exhausted: True when S2 ran out of data before the scan cap.
        error: A caller-facing error mapping when the scan failed.
    """

    items: list[dict[str, Any]]
    scanned: int
    exhausted: bool
    error: dict[str, Any] | None = None


async def _scan_citations_for_threshold(
    bundle: ServiceBundle,
    identifier: str,
    *,
    fields: str,
    year: str | None,
    fos: str | None,
    min_citations: int,
    needed: int,
) -> _FilteredScan:
    """Page through citations, keeping those above *min_citations*.

    S2's citations endpoint has no ``minCitationCount``, and returns results
    newest-first, so the highly-cited papers a caller wants are usually deep
    in the list. This walks up to :data:`_MAX_UPSTREAM_SCAN` records to find
    them.

    Args:
        bundle: Injected service bundle.
        identifier: The cited paper.
        fields: Comma-separated S2 field set.
        year: Optional year-range filter.
        fos: Optional fields-of-study filter.
        min_citations: Threshold a citing paper must meet.
        needed: How many matches are required before stopping.

    Returns:
        The scan outcome; ``error`` is set when the upstream call failed.
    """
    items: list[dict[str, Any]] = []
    scanned = 0
    while len(items) < needed and scanned < _MAX_UPSTREAM_SCAN:
        batch = min(_S2_PAGE_SIZE, _MAX_UPSTREAM_SCAN - scanned)
        try:
            page = await bundle.s2.get_citations(
                identifier,
                fields=fields,
                limit=batch,
                offset=scanned,
                year=year,
                fieldsOfStudy=fos,
            )
        except httpx.HTTPStatusError as exc:
            error = (
                {"error": "not_found", "identifier": identifier}
                if exc.response.status_code == 404
                else s2_error_payload(exc)
            )
            return _FilteredScan(items, scanned, False, error)
        data = page.get("data") or []
        items.extend(
            item
            for item in data
            if (cc := item.get("citingPaper", {}).get("citationCount")) is not None
            and cc >= min_citations
        )
        scanned += len(data)
        if len(data) < batch:
            return _FilteredScan(items, scanned, True)
    return _FilteredScan(items, scanned, False)


async def get_citations(
    identifier: str,
    fields: Literal["compact", "standard", "full"] = "compact",
    limit: int = 20,
    offset: int = 0,
    year_start: int | None = None,
    year_end: int | None = None,
    fields_of_study: list[str] | None = None,
    min_citations: int | None = None,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Fetch papers that cite the given paper (forward citations).

    Paging deeply to satisfy ``min_citations`` can run long; such a call
    continues in the background and returns a job handle to poll with
    ``get_job_result``.

    Args:
        identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
        fields: Field set preset for returned paper records.
        limit: Max results (pagination).
        offset: Pagination offset.
        year_start: Filter citing papers published from this year.
        year_end: Filter citing papers published up to this year.
        fields_of_study: Filter by field of study.
        min_citations: Minimum citation count of citing papers.
            Applied client-side (S2 does not support this filter on
            the citations endpoint).  Papers with unknown citation
            counts are excluded.  Pagination (``offset``/``limit``)
            is applied to the filtered results.  The tool paginates
            through up to 10 000 upstream results to find qualifying
            papers.

    Note:
        High-citation seed papers (>1 000 citations) tend to attract
        many survey and application-domain citing papers that reference
        the work only tangentially.  To focus on direct research
        lineage, combine ``min_citations`` with ``year_end`` to cap
        the expansion period, or use ``fields_of_study`` to restrict
        to a single discipline.

    Returns:
        JSON with ``data`` list of ``{"citingPaper": {...}}`` dicts.
    """
    year: str | None = None
    if year_start is not None and year_end is not None:
        year = f"{year_start}-{year_end}"
    elif year_start is not None:
        year = f"{year_start}-"
    elif year_end is not None:
        year = f"-{year_end}"

    fos = ",".join(fields_of_study) if fields_of_study else None

    async def _execute() -> dict[str, Any]:
        if min_citations is not None:
            scan = await _scan_citations_for_threshold(
                bundle,
                identifier,
                fields=FIELD_SETS[fields],
                year=year,
                fos=fos,
                min_citations=min_citations,
                needed=offset + limit,
            )
            if scan.error is not None:
                return scan.error
            page_items = scan.items[offset : offset + limit]
            result: dict[str, Any] = {"data": page_items}
            # A short page when S2 is exhausted means the offset ran past the
            # matches, not that the scan cap truncated anything.
            if (
                not scan.exhausted
                and scan.scanned >= _MAX_UPSTREAM_SCAN
                and len(scan.items) < offset + limit
            ):
                result["warning"] = (
                    f"Scanned {scan.scanned} upstream results "
                    f"(cap: {_MAX_UPSTREAM_SCAN}); some qualifying "
                    "papers may exist beyond this window."
                )
            papers = [
                item.get("citingPaper", {})
                for item in page_items
                if item.get("citingPaper")
            ]
            await bundle.enrichment.enrich(papers, bundle, tags=frozenset({"papers"}))
            return result

        try:
            result = await bundle.s2.get_citations(
                identifier,
                fields=FIELD_SETS[fields],
                limit=limit,
                offset=offset,
                year=year,
                fieldsOfStudy=fos,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"error": "not_found", "identifier": identifier}
            return s2_error_payload(exc)
        data_list: list[dict[str, Any]] = result.get("data") or []
        citing_papers = [
            item.get("citingPaper", {}) for item in data_list if item.get("citingPaper")
        ]
        await bundle.enrichment.enrich(
            citing_papers, bundle, tags=frozenset({"papers"})
        )
        return result

    return await _execute()


async def get_references(
    identifier: str,
    fields: Literal["compact", "standard", "full"] = "compact",
    limit: int = 50,
    offset: int = 0,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Fetch papers referenced by the given paper (backward references).

    Should the call run long it continues in the background and returns a
    job handle to poll with ``get_job_result``.

    Args:
        identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
        fields: Field set preset for returned paper records.
        limit: Max results.
        offset: Pagination offset.

    Returns:
        JSON with ``data`` list of ``{"citedPaper": {...}}`` dicts.
    """

    async def _execute() -> dict[str, Any]:
        try:
            result = await bundle.s2.get_references(
                identifier,
                fields=FIELD_SETS[fields],
                limit=limit,
                offset=offset,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"error": "not_found", "identifier": identifier}
            return s2_error_payload(exc)
        papers = [
            item.get("citedPaper", {})
            for item in result.get("data") or []
            if item.get("citedPaper")
        ]
        await bundle.enrichment.enrich(papers, bundle, tags=frozenset({"papers"}))
        return result

    return await _execute()


@dataclass(frozen=True)
class _GraphFilters:
    """Filters applied while expanding a node's neighbours.

    Bundled rather than passed individually because the two expanders need
    the same six values, and a six-parameter helper is its own smell.

    Attributes:
        fields: Comma-separated S2 field set.
        year: Server-side year-range filter, where the endpoint supports it.
        fos: Server-side fields-of-study filter.
        min_citations: Client-side citation-count threshold.
        year_start: Client-side lower year bound, for the references
            endpoint, which applies no server-side filters at all.
        year_end: Client-side upper year bound, same reason.
        fetch_limit: Page size when no threshold forces deep pagination.
    """

    fields: str
    year: str | None
    fos: str | None
    min_citations: int | None
    year_start: int | None
    year_end: int | None
    fetch_limit: int


def _node_from(paper: dict[str, Any]) -> dict[str, object]:
    """Build a graph node from an S2 paper record.

    Args:
        paper: The S2 record.

    Returns:
        The node mapping.
    """
    return {
        "id": paper.get("paperId"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
    }


async def _seed_nodes(
    bundle: ServiceBundle, seed_batch: list[str]
) -> dict[str, dict[str, object]]:
    """Resolve seed metadata so seed nodes carry titles and years.

    A failure here is not fatal: the graph is still walkable from bare ids,
    so the seeds simply keep null metadata.

    Args:
        bundle: Injected service bundle.
        seed_batch: Seed identifiers, already capped.

    Returns:
        Seed id to node mapping, in the order given.
    """
    try:
        resolved = await bundle.s2.batch_resolve(
            seed_batch, fields=FIELD_SETS["compact"]
        )
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            log_s2_error(exc)
        resolved = [None] * len(seed_batch)
    return {
        seed_id: {
            "id": seed_id,
            "title": data.get("title") if data else None,
            "year": data.get("year") if data else None,
            "citationCount": data.get("citationCount") if data else None,
        }
        for seed_id, data in zip(seed_batch, resolved, strict=False)
    }


async def _expand_citations(
    bundle: ServiceBundle, paper_id: str, filters: _GraphFilters, room: int
) -> list[tuple[str, dict[str, object], dict[str, object]]]:
    """Collect papers citing *paper_id*, newest-first, honouring the threshold.

    With ``min_citations`` set this pages deeply, because S2 returns
    citations newest-first while highly-cited papers are usually older.
    Upstream failures yield what was collected so far rather than aborting
    the walk.

    Args:
        bundle: Injected service bundle.
        paper_id: The node being expanded.
        filters: Active filters and page size.
        room: How many more nodes the graph can still hold.

    Returns:
        ``(id, node, edge)`` triples.
    """
    found: list[tuple[str, dict[str, object], dict[str, object]]] = []
    deep = filters.min_citations is not None
    scan_cap = _MAX_PER_NODE_SCAN if deep else filters.fetch_limit
    offset = 0
    try:
        while offset < scan_cap and len(found) < room:
            batch = min(
                _S2_PAGE_SIZE if deep else filters.fetch_limit, scan_cap - offset
            )
            result = await bundle.s2.get_citations(
                paper_id,
                fields=filters.fields,
                limit=batch,
                offset=offset,
                year=filters.year,
                fieldsOfStudy=filters.fos,
            )
            data = result.get("data") or []
            for item in data:
                paper = item.get("citingPaper", {})
                pid = paper.get("paperId")
                cites = paper.get("citationCount")
                if not pid:
                    continue
                if filters.min_citations is not None and (
                    cites is None or cites < filters.min_citations
                ):
                    continue
                found.append(
                    (
                        pid,
                        _node_from(paper),
                        {"source": pid, "target": paper_id, "direction": "cites"},
                    )
                )
            offset += len(data)
            if len(data) < batch or not deep:
                break
    except httpx.HTTPStatusError as exc:
        log_s2_error(exc)
    except httpx.HTTPError:
        pass
    return found


def _passes_reference_filters(paper: dict[str, Any], filters: _GraphFilters) -> bool:
    """Check a referenced paper against the client-side filters.

    The references endpoint supports no server-side filtering, so every
    filter is applied here.

    Args:
        paper: The referenced S2 record.
        filters: Active filters.

    Returns:
        True when the paper should join the graph.
    """
    year = paper.get("year")
    cites = paper.get("citationCount")
    if filters.min_citations is not None and (
        cites is None or cites < filters.min_citations
    ):
        return False
    if filters.year_start is not None and (year is None or year < filters.year_start):
        return False
    return not (
        filters.year_end is not None and (year is None or year > filters.year_end)
    )


async def _expand_references(
    bundle: ServiceBundle, paper_id: str, filters: _GraphFilters
) -> list[tuple[str, dict[str, object], dict[str, object]]]:
    """Collect the papers *paper_id* references.

    Args:
        bundle: Injected service bundle.
        paper_id: The node being expanded.
        filters: Active filters and page size.

    Returns:
        ``(id, node, edge)`` triples.
    """
    found: list[tuple[str, dict[str, object], dict[str, object]]] = []
    try:
        result = await bundle.s2.get_references(
            paper_id, fields=filters.fields, limit=filters.fetch_limit, offset=0
        )
    except httpx.HTTPStatusError as exc:
        log_s2_error(exc)
        return found
    except httpx.HTTPError:
        return found
    for item in result.get("data") or []:
        paper = item.get("citedPaper", {})
        pid = paper.get("paperId")
        if not pid or not _passes_reference_filters(paper, filters):
            continue
        found.append(
            (
                pid,
                _node_from(paper),
                {"source": paper_id, "target": pid, "direction": "cites"},
            )
        )
    return found


@dataclass
class _Walk:
    """What a breadth-first expansion produced.

    Attributes:
        nodes: Discovered nodes, keyed by paper id, seeds first.
        edges: Every edge seen, before pruning to surviving nodes.
        depth_reached: Deepest hop actually expanded.
        truncated: True when ``max_nodes`` stopped the walk early.
    """

    nodes: dict[str, dict[str, object]]
    edges: list[dict[str, object]]
    depth_reached: int
    truncated: bool


async def _walk_graph(
    bundle: ServiceBundle,
    seeds: dict[str, dict[str, object]],
    *,
    direction: str,
    depth: int,
    max_nodes: int,
    filters: _GraphFilters,
) -> _Walk:
    """Expand outward from *seeds* until depth or the node budget runs out.

    Args:
        bundle: Injected service bundle.
        seeds: Seed nodes, keyed by paper id.
        direction: ``citations``, ``references`` or ``both``.
        depth: Maximum hops to expand.
        max_nodes: Node budget; reaching it truncates the walk.
        filters: Active filters and page size.

    Returns:
        The :class:`_Walk` outcome.
    """
    nodes = dict(seeds)
    edges: list[dict[str, object]] = []
    queue: deque[tuple[str, int]] = deque((sid, 0) for sid in seeds)
    visited: set[str] = set(seeds)
    depth_reached = 0

    while queue:
        paper_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        depth_reached = max(depth_reached, current_depth + 1)

        found: list[tuple[str, dict[str, object], dict[str, object]]] = []
        if direction in ("citations", "both"):
            found += await _expand_citations(
                bundle, paper_id, filters, max_nodes - len(nodes)
            )
        if direction in ("references", "both"):
            found += await _expand_references(bundle, paper_id, filters)

        for pid, node, edge in found:
            edges.append(edge)
            if len(nodes) >= max_nodes:
                return _Walk(nodes, edges, depth_reached, truncated=True)
            nodes.setdefault(pid, node)
            if pid not in visited:
                visited.add(pid)
                queue.append((pid, current_depth + 1))

    return _Walk(nodes, edges, depth_reached, truncated=False)


async def get_citation_graph(
    seed_ids: list[str],
    direction: Literal["citations", "references", "both"] = "citations",
    depth: int = 1,
    max_nodes: int = 100,
    year_start: int | None = None,
    year_end: int | None = None,
    fields_of_study: list[str] | None = None,
    min_citations: int | None = None,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Traverse the citation graph from one or more seed papers.

    Performs BFS up to *depth* hops. Returns nodes (paper records) and
    directed edges. Hard-caps at *max_nodes* to prevent runaway expansion.

    Traversal makes one rate-limited request per node, so anything past a
    shallow, narrow graph runs long: expect a job handle to poll with
    ``get_job_result`` rather than the graph itself.

    Args:
        seed_ids: 1-10 paper identifiers to start from.
        direction: Expand via citations, references, or both.
        depth: Number of hops (1-3).
        max_nodes: Hard cap on total nodes returned.
        year_start: Filter expanded papers to this year and later.
        year_end: Filter expanded papers to this year and earlier.
        fields_of_study: Filter by field.
        min_citations: Minimum citation count of expanded papers.

    Note:
        High-citation seed papers (>1 000 citations) tend to attract
        many survey and application-domain citing papers that reference
        the work only tangentially.  To focus on direct research
        lineage, combine ``min_citations`` with ``year_end`` to cap
        the expansion period, or use ``fields_of_study`` to restrict
        to a single discipline.

    Returns:
        JSON ``{"nodes": [...], "edges": [...], "stats": {...}}``.
    """
    clamped_depth = max(1, min(depth, 3))

    year: str | None = None
    if year_start is not None and year_end is not None:
        year = f"{year_start}-{year_end}"
    elif year_start is not None:
        year = f"{year_start}-"
    elif year_end is not None:
        year = f"-{year_end}"
    fos = ",".join(fields_of_study) if fields_of_study else None

    async def _execute() -> dict[str, Any]:
        seed_batch = seed_ids[:10]
        # With client-side filters active, pull more candidates per node so
        # filtering does not exhaust the pool before reaching qualifying
        # papers. Applies to citations (S2 returns newest-first) and to
        # references (where every filter is client-side).
        has_client_filters = (
            min_citations is not None or year is not None or fos is not None
        )
        walk = await _walk_graph(
            bundle,
            await _seed_nodes(bundle, seed_batch),
            direction=direction,
            depth=clamped_depth,
            max_nodes=max_nodes,
            filters=_GraphFilters(
                fields=FIELD_SETS["compact"],
                year=year,
                fos=fos,
                min_citations=min_citations,
                year_start=year_start,
                year_end=year_end,
                fetch_limit=500 if has_client_filters else 50,
            ),
        )

        node_list = list(walk.nodes.values())[:max_nodes]
        node_ids = {n["id"] for n in node_list}
        edge_list = [
            e for e in walk.edges if e["source"] in node_ids and e["target"] in node_ids
        ]

        await bundle.enrichment.enrich(node_list, bundle, tags=frozenset({"papers"}))
        return {
            "nodes": node_list,
            "edges": edge_list,
            "stats": {
                "total_nodes": len(node_list),
                "total_edges": len(edge_list),
                "depth_reached": walk.depth_reached,
                "truncated": walk.truncated,
            },
        }

    return await _execute()


async def _cached_neighbour_ids(
    bundle: ServiceBundle, paper_id: str, *, kind: str
) -> list[str]:
    """Return one direction's neighbour ids, reading through the cache.

    Args:
        bundle: Injected service bundle.
        paper_id: The paper whose neighbours are wanted.
        kind: ``"references"`` or ``"citations"``.

    Returns:
        Neighbour paper ids; empty when the upstream call failed.
    """
    if kind == "references":
        cached = await bundle.cache.get_references(paper_id)
        fetch, item_key, store = (
            bundle.s2.get_references,
            "citedPaper",
            bundle.cache.set_references,
        )
    else:
        cached = await bundle.cache.get_citations(paper_id)
        fetch, item_key, store = (
            bundle.s2.get_citations,
            "citingPaper",
            bundle.cache.set_citations,
        )
    if cached is not None:
        return list(cached)
    try:
        result = await fetch(paper_id, fields="paperId", limit=100, offset=0)
    except httpx.HTTPStatusError as exc:
        log_s2_error(exc)
        return []
    ids = [
        item[item_key]["paperId"]
        for item in (result.get("data") or [])
        if item.get(item_key, {}).get("paperId")
    ]
    await store(paper_id, ids)
    return ids


async def _neighbours(
    bundle: ServiceBundle, paper_id: str, direction: str
) -> list[str]:
    """Return neighbour ids in the requested direction(s).

    Args:
        bundle: Injected service bundle.
        paper_id: The paper whose neighbours are wanted.
        direction: ``references``, ``citations`` or ``both``.

    Returns:
        Neighbour paper ids.
    """
    found: list[str] = []
    if direction in ("references", "both"):
        found += await _cached_neighbour_ids(bundle, paper_id, kind="references")
    if direction in ("citations", "both"):
        found += await _cached_neighbour_ids(bundle, paper_id, kind="citations")
    return found


async def _path_records(bundle: ServiceBundle, path: list[str]) -> list[dict[str, Any]]:
    """Turn a list of paper ids into records, falling back to bare ids.

    Args:
        bundle: Injected service bundle.
        path: Paper ids in path order.

    Returns:
        One record per id.
    """
    records: list[dict[str, Any]] = []
    for pid in path:
        cached = await bundle.cache.get_paper(pid)
        records.append(dict(cached) if cached else {"paperId": pid})
    return records


async def find_bridge_papers(
    source_id: str,
    target_id: str,
    max_depth: int = 4,
    direction: Literal["citations", "references", "both"] = "both",
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Find the shortest citation path between two papers.

    Uses BFS over the citation/reference graph. Leverages cached
    citation and reference lists to minimise API calls.

    The search walks outward one rate-limited request per node, so it
    commonly runs long and returns a job handle to poll with
    ``get_job_result`` rather than the path itself.

    Args:
        source_id: Starting paper S2 ID.
        target_id: Target paper S2 ID.
        max_depth: Maximum hops to search (default 4).
        direction: Expand via citations, references, or both.

    Returns:
        JSON ``{"found": true, "path": [...]}`` or ``{"found": false}``.
    """

    async def _execute() -> dict[str, Any]:
        queue: deque[tuple[str, list[str]]] = deque([(source_id, [source_id])])
        visited: set[str] = {source_id}

        while queue:
            current_id, path = queue.popleft()
            if len(path) > max_depth + 1:
                continue

            for neighbour_id in await _neighbours(bundle, current_id, direction):
                if neighbour_id == target_id:
                    return {
                        "found": True,
                        "path": await _path_records(bundle, [*path, target_id]),
                    }
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    queue.append((neighbour_id, [*path, neighbour_id]))

        return {"found": False}

    return await _execute()


def register_graph_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register citation graph tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics. ``get_citation_graph`` and
            ``find_bridge_papers`` walk the graph breadth-first, one
            rate-limited request per node, so they routinely outrun the soft
            deadline and are promoted.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get Citations",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_citations)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get References",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_references)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get Citation Graph",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_citation_graph)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Find Bridge Papers",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(find_bridge_papers)

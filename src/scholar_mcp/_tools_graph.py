"""Citation graph MCP tools."""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._book_enrichment import enrich_books
from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

# Pagination limits for client-side min_citations filtering.
# S2 returns citations newest-first; high-citation papers are typically
# older, so we must paginate deeply to reach them.
_S2_PAGE_SIZE = 1000
_MAX_UPSTREAM_SCAN = 10_000  # get_citations tool
_MAX_PER_NODE_SCAN = 5_000  # get_citation_graph BFS per node


def register_graph_tools(mcp: FastMCP) -> None:
    """Register citation graph tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
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
    ) -> str:
        """Fetch papers that cite the given paper (forward citations).

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

        filtering = min_citations is not None

        async def _execute(*, retry: bool = True) -> str:
            if filtering:
                # S2 citations endpoint does not support
                # minCitationCount — paginate through upstream results
                # and filter client-side.  S2 returns citations
                # newest-first so high-citation papers (typically older)
                # may be deep in the list.
                needed = offset + limit
                filtered: list[dict[str, object]] = []
                s2_offset = 0
                exhausted = False
                while len(filtered) < needed and s2_offset < _MAX_UPSTREAM_SCAN:
                    batch = min(_S2_PAGE_SIZE, _MAX_UPSTREAM_SCAN - s2_offset)
                    try:
                        page = await bundle.s2.get_citations(
                            identifier,
                            fields=FIELD_SETS[fields],
                            limit=batch,
                            offset=s2_offset,
                            year=year,
                            fieldsOfStudy=fos,
                            retry=retry,
                        )
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 404:
                            return json.dumps(
                                {
                                    "error": "not_found",
                                    "identifier": identifier,
                                }
                            )
                        return json.dumps(
                            {
                                "error": "upstream_error",
                                "status": exc.response.status_code,
                            }
                        )
                    data = page.get("data") or []
                    for item in data:
                        cc = item.get("citingPaper", {}).get("citationCount")
                        if cc is not None and cc >= min_citations:
                            filtered.append(item)
                    s2_offset += len(data)
                    if len(data) < batch:
                        exhausted = True
                        break

                # When exhausted is True, S2 has no more data — an
                # empty slice here simply means the offset is beyond
                # the available filtered results (not a truncation).
                result: dict[str, object] = {"data": filtered[offset : offset + limit]}
                if (
                    not exhausted
                    and s2_offset >= _MAX_UPSTREAM_SCAN
                    and len(filtered) < needed
                ):
                    result["warning"] = (
                        f"Scanned {s2_offset} upstream results "
                        f"(cap: {_MAX_UPSTREAM_SCAN}); some qualifying "
                        "papers may exist beyond this window."
                    )
                papers = [
                    item.get("citingPaper", {})
                    for item in result["data"]  # type: ignore[union-attr]
                    if item.get("citingPaper")
                ]
                await enrich_books(papers, bundle)
                return json.dumps(result)

            try:
                result = await bundle.s2.get_citations(
                    identifier,
                    fields=FIELD_SETS[fields],
                    limit=limit,
                    offset=offset,
                    year=year,
                    fieldsOfStudy=fos,
                    retry=retry,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return json.dumps({"error": "not_found", "identifier": identifier})
                return json.dumps(
                    {
                        "error": "upstream_error",
                        "status": exc.response.status_code,
                    }
                )
            papers = [
                item.get("citingPaper", {})
                for item in result.get("data") or []
                if item.get("citingPaper")
            ]
            await enrich_books(papers, bundle)
            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True), tool="get_citations")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "get_citations"}
            )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_references(
        identifier: str,
        fields: Literal["compact", "standard", "full"] = "compact",
        limit: int = 50,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch papers referenced by the given paper (backward references).

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
            fields: Field set preset for returned paper records.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            JSON with ``data`` list of ``{"citedPaper": {...}}`` dicts.
        """

        async def _execute(*, retry: bool = True) -> str:
            try:
                result = await bundle.s2.get_references(
                    identifier,
                    fields=FIELD_SETS[fields],
                    limit=limit,
                    offset=offset,
                    retry=retry,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return json.dumps({"error": "not_found", "identifier": identifier})
                return json.dumps(
                    {"error": "upstream_error", "status": exc.response.status_code}
                )
            papers = [
                item.get("citedPaper", {})
                for item in result.get("data") or []
                if item.get("citedPaper")
            ]
            await enrich_books(papers, bundle)
            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True), tool="get_references")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "get_references"}
            )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
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
    ) -> str:
        """Traverse the citation graph from one or more seed papers.

        Performs BFS up to *depth* hops. Returns nodes (paper records) and
        directed edges. Hard-caps at *max_nodes* to prevent runaway expansion.

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

        async def _execute(*, retry: bool = True) -> str:
            nodes: dict[str, dict[str, object]] = {}
            edges: list[dict[str, object]] = []
            bfs_queue: deque[tuple[str, int]] = deque()

            # Resolve seed metadata so nodes have titles/years populated
            seed_batch = seed_ids[:10]
            try:
                seed_results = await bundle.s2.batch_resolve(
                    seed_batch,
                    fields=FIELD_SETS["compact"],
                    retry=retry,
                )
            except (httpx.HTTPError, ValueError):
                seed_results = [None] * len(seed_batch)

            for seed_id, seed_data in zip(seed_batch, seed_results, strict=False):
                nodes[seed_id] = {
                    "id": seed_id,
                    "title": seed_data.get("title") if seed_data else None,
                    "year": seed_data.get("year") if seed_data else None,
                    "citationCount": (
                        seed_data.get("citationCount") if seed_data else None
                    ),
                }
                bfs_queue.append((seed_id, 0))

            visited: set[str] = set(seed_ids[:10])
            truncated = False
            actual_depth_reached = 0

            # When client-side filters are active, fetch more candidates
            # per node so filtering doesn't exhaust the pool before
            # reaching qualifying papers.  Applied to both citations
            # (S2 returns newest-first) and references (all filters
            # are client-side).
            has_client_filters = (
                min_citations is not None or year is not None or fos is not None
            )
            fetch_limit = 500 if has_client_filters else 50

            while bfs_queue:
                paper_id, current_depth = bfs_queue.popleft()
                if current_depth >= clamped_depth:
                    continue
                actual_depth_reached = max(actual_depth_reached, current_depth + 1)

                new_nodes: list[tuple[str, dict[str, object]]] = []

                if direction in ("citations", "both"):
                    try:
                        # When min_citations is set, paginate through
                        # upstream results — S2 returns citations
                        # newest-first and qualifying papers may be
                        # deep in the list.
                        scan_cap = (
                            _MAX_PER_NODE_SCAN
                            if min_citations is not None
                            else fetch_limit
                        )
                        s2_off = 0
                        while (
                            s2_off < scan_cap
                            and len(nodes) + len(new_nodes) < max_nodes
                        ):
                            batch = min(
                                _S2_PAGE_SIZE
                                if min_citations is not None
                                else fetch_limit,
                                scan_cap - s2_off,
                            )
                            result = await bundle.s2.get_citations(
                                paper_id,
                                fields=FIELD_SETS["compact"],
                                limit=batch,
                                offset=s2_off,
                                year=year,
                                fieldsOfStudy=fos,
                                retry=retry,
                            )
                            data = result.get("data") or []
                            for item in data:
                                p = item.get("citingPaper", {})
                                pid = p.get("paperId")
                                if not pid:
                                    continue
                                p_cites = p.get("citationCount")
                                if min_citations is not None and (
                                    p_cites is None or p_cites < min_citations
                                ):
                                    continue
                                node = {
                                    "id": pid,
                                    "title": p.get("title"),
                                    "year": p.get("year"),
                                    "citationCount": p_cites,
                                }
                                new_nodes.append((pid, node))
                                edges.append(
                                    {
                                        "source": pid,
                                        "target": paper_id,
                                        "direction": "cites",
                                    }
                                )
                            s2_off += len(data)
                            if len(data) < batch or min_citations is None:
                                break
                    except httpx.HTTPError:
                        pass

                if direction in ("references", "both"):
                    try:
                        result = await bundle.s2.get_references(
                            paper_id,
                            fields=FIELD_SETS["compact"],
                            limit=fetch_limit,
                            offset=0,
                            retry=retry,
                        )
                        for item in result.get("data") or []:
                            p = item.get("citedPaper", {})
                            pid = p.get("paperId")
                            if not pid:
                                continue
                            # S2 references endpoint doesn't support
                            # server-side filters — apply client-side
                            p_year = p.get("year")
                            p_cites = p.get("citationCount")
                            if min_citations is not None and (
                                p_cites is None or p_cites < min_citations
                            ):
                                continue
                            if year_start is not None and (
                                p_year is None or p_year < year_start
                            ):
                                continue
                            if year_end is not None and (
                                p_year is None or p_year > year_end
                            ):
                                continue
                            node = {
                                "id": pid,
                                "title": p.get("title"),
                                "year": p_year,
                                "citationCount": p_cites,
                            }
                            new_nodes.append((pid, node))
                            edges.append(
                                {
                                    "source": paper_id,
                                    "target": pid,
                                    "direction": "cites",
                                }
                            )
                    except httpx.HTTPError:
                        pass

                for pid, node in new_nodes:
                    if len(nodes) >= max_nodes:
                        truncated = True
                        break
                    nodes.setdefault(pid, node)
                    if pid not in visited:
                        visited.add(pid)
                        bfs_queue.append((pid, current_depth + 1))

                if truncated:
                    break

            node_list = list(nodes.values())[:max_nodes]
            node_ids = {n["id"] for n in node_list}
            edge_list = [
                e for e in edges if e["source"] in node_ids and e["target"] in node_ids
            ]

            await enrich_books(node_list, bundle)
            return json.dumps(
                {
                    "nodes": node_list,
                    "edges": edge_list,
                    "stats": {
                        "total_nodes": len(node_list),
                        "total_edges": len(edge_list),
                        "depth_reached": actual_depth_reached,
                        "truncated": truncated,
                    },
                }
            )

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="get_citation_graph"
            )
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task_id,
                    "tool": "get_citation_graph",
                }
            )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def find_bridge_papers(
        source_id: str,
        target_id: str,
        max_depth: int = 4,
        direction: Literal["citations", "references", "both"] = "both",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Find the shortest citation path between two papers.

        Uses BFS over the citation/reference graph. Leverages cached
        citation and reference lists to minimise API calls.

        Args:
            source_id: Starting paper S2 ID.
            target_id: Target paper S2 ID.
            max_depth: Maximum hops to search (default 4).
            direction: Expand via citations, references, or both.

        Returns:
            JSON ``{"found": true, "path": [...]}`` or ``{"found": false}``.
        """

        async def _execute(*, retry: bool = True) -> str:
            bfs_queue: deque[tuple[str, list[str]]] = deque([(source_id, [source_id])])
            visited: set[str] = {source_id}

            async def _get_neighbours(paper_id: str) -> list[str]:
                neighbours: list[str] = []
                if direction in ("references", "both"):
                    cached = await bundle.cache.get_references(paper_id)
                    if cached is None:
                        try:
                            result = await bundle.s2.get_references(
                                paper_id,
                                fields="paperId",
                                limit=100,
                                offset=0,
                                retry=retry,
                            )
                            cached = [
                                item["citedPaper"]["paperId"]
                                for item in (result.get("data") or [])
                                if item.get("citedPaper", {}).get("paperId")
                            ]
                            await bundle.cache.set_references(paper_id, cached)
                        except httpx.HTTPStatusError:
                            cached = []
                    neighbours.extend(cached)
                if direction in ("citations", "both"):
                    cached_cit = await bundle.cache.get_citations(paper_id)
                    if cached_cit is None:
                        try:
                            result = await bundle.s2.get_citations(
                                paper_id,
                                fields="paperId",
                                limit=100,
                                offset=0,
                                retry=retry,
                            )
                            cached_cit = [
                                item["citingPaper"]["paperId"]
                                for item in (result.get("data") or [])
                                if item.get("citingPaper", {}).get("paperId")
                            ]
                            await bundle.cache.set_citations(paper_id, cached_cit)
                        except httpx.HTTPStatusError:
                            cached_cit = []
                    neighbours.extend(cached_cit)
                return neighbours

            while bfs_queue:
                current_id, path = bfs_queue.popleft()
                if len(path) > max_depth + 1:
                    continue

                neighbours = await _get_neighbours(current_id)
                for neighbour_id in neighbours:
                    if neighbour_id == target_id:
                        full_path = [*path, target_id]
                        path_records = []
                        for pid in full_path:
                            cached_paper = await bundle.cache.get_paper(pid)
                            if cached_paper:
                                path_records.append(cached_paper)
                            else:
                                path_records.append({"paperId": pid})
                        return json.dumps({"found": True, "path": path_records})
                    if neighbour_id not in visited:
                        visited.add(neighbour_id)
                        bfs_queue.append((neighbour_id, [*path, neighbour_id]))

            return json.dumps({"found": False})

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="find_bridge_papers"
            )
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task_id,
                    "tool": "find_bridge_papers",
                }
            )

"""Citation graph MCP tools."""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


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

        async def _execute(*, retry: bool = True) -> str:
            try:
                result = await bundle.s2.get_citations(
                    identifier,
                    fields=FIELD_SETS[fields],
                    limit=limit,
                    offset=offset,
                    year=year,
                    fieldsOfStudy=fos,
                    minCitationCount=min_citations,
                    retry=retry,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return json.dumps({"error": "not_found", "identifier": identifier})
                return json.dumps(
                    {"error": "upstream_error", "status": exc.response.status_code}
                )
            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True))
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
            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True))
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

            for seed_id, seed_data in zip(seed_batch, seed_results, strict=True):
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

            while bfs_queue:
                paper_id, current_depth = bfs_queue.popleft()
                if current_depth >= clamped_depth:
                    continue
                actual_depth_reached = max(actual_depth_reached, current_depth + 1)

                new_nodes: list[tuple[str, dict[str, object]]] = []

                if direction in ("citations", "both"):
                    try:
                        result = await bundle.s2.get_citations(
                            paper_id,
                            fields=FIELD_SETS["compact"],
                            limit=50,
                            offset=0,
                            year=year,
                            fieldsOfStudy=fos,
                            minCitationCount=min_citations,
                            retry=retry,
                        )
                        for item in result.get("data", []):
                            p = item.get("citingPaper", {})
                            if pid := p.get("paperId"):
                                node = {
                                    "id": pid,
                                    "title": p.get("title"),
                                    "year": p.get("year"),
                                    "citationCount": p.get("citationCount"),
                                }
                                new_nodes.append((pid, node))
                                edges.append(
                                    {
                                        "source": pid,
                                        "target": paper_id,
                                        "direction": "cites",
                                    }
                                )
                    except httpx.HTTPError:
                        pass

                if direction in ("references", "both"):
                    try:
                        result = await bundle.s2.get_references(
                            paper_id,
                            fields=FIELD_SETS["compact"],
                            limit=50,
                            offset=0,
                            retry=retry,
                        )
                        for item in result.get("data", []):
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
            task_id = bundle.tasks.submit(_execute(retry=True))
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
                                for item in result.get("data", [])
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
                                for item in result.get("data", [])
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
            task_id = bundle.tasks.submit(_execute(retry=True))
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task_id,
                    "tool": "find_bridge_papers",
                }
            )

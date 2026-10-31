# Citation graph

## `get_citations`

**Get Citations.** Read-only. Reaches outside the server.

Fetch papers that cite the given paper (forward citations).

Returns at most 1000 citing papers per call; a larger `limit` is capped at 1000, so page further with `offset`.

Paging deeply to satisfy `min_citations` can run long; such a call continues in the background and returns a job handle to poll with `get_job_result`.

**Parameters**

| Name              | Type                          | Default     | Description                                                                                                                                                                                                                                                                                                                       |
| ----------------- | ----------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `identifier`      | `string`                      | required    | Paper identifier (DOI, S2 ID, ARXIV:, etc.).                                                                                                                                                                                                                                                                                      |
| `fields`          | `compact \| standard \| full` | `"compact"` | Field set preset for returned paper records.                                                                                                                                                                                                                                                                                      |
| `limit`           | `integer`                     | `20`        | Max results (pagination, max 1000).                                                                                                                                                                                                                                                                                               |
| `offset`          | `integer`                     | `0`         | Pagination offset.                                                                                                                                                                                                                                                                                                                |
| `year_start`      | `integer \| null`             | `null`      | Filter citing papers published from this year.                                                                                                                                                                                                                                                                                    |
| `year_end`        | `integer \| null`             | `null`      | Filter citing papers published up to this year.                                                                                                                                                                                                                                                                                   |
| `fields_of_study` | `array of string \| null`     | `null`      | Filter by field of study.                                                                                                                                                                                                                                                                                                         |
| `min_citations`   | `integer \| null`             | `null`      | Minimum citation count of citing papers. Applied client-side (S2 does not support this filter on the citations endpoint). Papers with unknown citation counts are excluded. Pagination (`offset`/`limit`) is applied to the filtered results. The tool paginates through up to 10 000 upstream results to find qualifying papers. |

**Returns**

JSON with `data` list of `{"citingPaper": {...}}` dicts.

## `get_references`

**Get References.** Read-only. Reaches outside the server.

Fetch papers referenced by the given paper (backward references).

Returns at most 1000 references per call; a larger `limit` is capped at 1000, so page further with `offset`.

Should the call run long it continues in the background and returns a job handle to poll with `get_job_result`.

**Parameters**

| Name         | Type                          | Default     | Description                                  |
| ------------ | ----------------------------- | ----------- | -------------------------------------------- |
| `identifier` | `string`                      | required    | Paper identifier (DOI, S2 ID, ARXIV:, etc.). |
| `fields`     | `compact \| standard \| full` | `"compact"` | Field set preset for returned paper records. |
| `limit`      | `integer`                     | `50`        | Max results (max 1000).                      |
| `offset`     | `integer`                     | `0`         | Pagination offset.                           |

**Returns**

JSON with `data` list of `{"citedPaper": {...}}` dicts.

## `get_citation_graph`

**Get Citation Graph.** Read-only. Reaches outside the server.

Traverse the citation graph from one or more seed papers.

Performs BFS up to *depth* hops. Returns nodes (paper records) and directed edges. Hard-caps at *`max_nodes`* to prevent runaway expansion.

Traversal makes one rate-limited request per node, so anything past a shallow, narrow graph runs long: expect a job handle to poll with `get_job_result` rather than the graph itself.

A Semantic Scholar throttle defers the same walk. Poll the job handle; the resumed graph does not mark the throttled request as partial.

A failed upstream request does not abort the walk. When one happens, `stats.partial` is true, `stats.failed_requests` counts them, and a `warning` key explains what was not fetched. Treat such a graph as incomplete: a missing node or edge is unknown, not absent. This is distinct from `stats.truncated`, which means `max_nodes` stopped an otherwise successful walk.

**Parameters**

| Name              | Type                              | Default       | Description                                      |
| ----------------- | --------------------------------- | ------------- | ------------------------------------------------ |
| `seed_ids`        | `array of string`                 | required      | 1-10 paper identifiers to start from.            |
| `direction`       | `citations \| references \| both` | `"citations"` | Expand via citations, references, or both.       |
| `depth`           | `integer`                         | `1`           | Number of hops (1-3).                            |
| `max_nodes`       | `integer`                         | `100`         | Hard cap on total nodes returned.                |
| `year_start`      | `integer \| null`                 | `null`        | Filter expanded papers to this year and later.   |
| `year_end`        | `integer \| null`                 | `null`        | Filter expanded papers to this year and earlier. |
| `fields_of_study` | `array of string \| null`         | `null`        | Filter by field.                                 |
| `min_citations`   | `integer \| null`                 | `null`        | Minimum citation count of expanded papers.       |

**Returns**

JSON `{"nodes": [...], "edges": [...], "stats": {...}}`, where `stats` carries `total_nodes`, `total_edges`, `depth_reached`, `truncated`, `partial` and `failed_requests`. A `warning` key joins the top level when `partial` is true.

A response looks like:

```
{
  "nodes": [{"id": "...", "title": "...", "year": 2024, "citationCount": 42}, ...],
  "edges": [{"source": "id1", "target": "id2"}, ...],
  "stats": {
    "total_nodes": 42,
    "total_edges": 67,
    "depth_reached": 2,
    "truncated": false,
    "partial": false,
    "failed_requests": 0
  }
}
```

Partial graphs

Only a non-429 upstream failure makes a graph partial; a 429 pauses the same walk in a job. The top-level `warning` key names the statuses and the operations affected.

Controlling graph size

Start with `depth=1` and a small `max_nodes` to get an overview, then increase as needed. `depth=3` with `direction=both` can produce large graphs.

See [Citation Graphs guide](https://pvliesdonk.github.io/scholar-mcp/unstable/use/citation-graphs/index.md) for usage patterns.

## `find_bridge_papers`

**Find Bridge Papers.** Read-only. Reaches outside the server.

Find the shortest citation path between two papers.

Uses BFS over the citation/reference graph. Uses cached citation and reference lists to minimise API calls.

The search walks outward one rate-limited request per node, so it commonly runs long and returns a job handle to poll with `get_job_result` rather than the path itself.

A Semantic Scholar throttle defers the same search. Poll the job handle; the resumed search does not mark the throttled request as partial.

A failed upstream request does not abort the search. When one happens, `partial` is true, `failed_requests` counts them, and a `warning` key explains what was not fetched. A partial `{"found": false}` is not evidence that no path exists, and a partial `{"found": true}` path is not guaranteed to be the shortest one.

**Parameters**

| Name        | Type                              | Default  | Description                                |
| ----------- | --------------------------------- | -------- | ------------------------------------------ |
| `source_id` | `string`                          | required | Starting paper S2 ID.                      |
| `target_id` | `string`                          | required | Target paper S2 ID.                        |
| `max_depth` | `integer`                         | `4`      | Maximum hops to search (default 4).        |
| `direction` | `citations \| references \| both` | `"both"` | Expand via citations, references, or both. |

**Returns**

JSON `{"found": true, "path": [...]}` or `{"found": false}`, either way carrying `partial` and `failed_requests`. A `warning` key joins them when `partial` is true.

A response looks like:

```
{
  "found": true,
  "path": [
    {"paperId": "source", "title": "...", ...},
    {"paperId": "bridge", "title": "...", ...},
    {"paperId": "target", "title": "...", ...}
  ]
}
```

If no path exists within `max_depth`, `path` is absent.

Partial searches

Only a non-429 upstream failure makes a search partial; a 429 pauses the same search in a job. The `warning` key names the statuses and the operations affected.

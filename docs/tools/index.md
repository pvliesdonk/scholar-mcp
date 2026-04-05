# Tools

Scholar MCP provides 15 tools across six categories. All tools return JSON.

All tools include [MCP tool annotations](https://spec.modelcontextprotocol.io/specification/2025-03-26/server/tools/#annotations):

- Read-only tools: `readOnlyHint=true`, `destructiveHint=false`, `openWorldHint=true`
- Write tools (PDF): `readOnlyHint=false`, `destructiveHint=false`, `openWorldHint=true`
- Task polling tools: `readOnlyHint=true`, `destructiveHint=false`, `openWorldHint=false`

## Async Task Queue

Long-running operations return immediately with a task ID instead of blocking:

- **PDF tools** always queue (unless the result is already cached locally)
- **S2 tools** queue when the Semantic Scholar API responds with HTTP 429 (rate limited)

When a tool queues an operation, it returns:

```json
{"queued": true, "task_id": "a1b2c3d4e5f6", "tool": "fetch_paper_pdf"}
```

Poll with `get_task_result` to check status and retrieve the result. Task results expire after 10 minutes (S2 tools) or 1 hour (PDF tools).

## Search & Retrieval

### `search_papers`

Full-text search across the Semantic Scholar corpus.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | *(required)* | Search query string |
| `fields` | string | `"compact"` | Field set: `compact`, `standard`, or `full` |
| `limit` | int | `10` | Results per page (max 100) |
| `offset` | int | `0` | Pagination offset |
| `year_start` | int | -- | Filter: earliest publication year |
| `year_end` | int | -- | Filter: latest publication year |
| `fields_of_study` | list[string] | -- | S2 field-of-study names (e.g. `["Computer Science", "Physics"]`) |
| `venue` | string | -- | Filter by venue name |
| `min_citations` | int | -- | Minimum citation count |
| `sort` | string | `"relevance"` | Sort order: `relevance`, `citations`, or `year` |

**Returns:** `{"data": [...], "total": N}` where each item contains the requested field set.

**Field sets:**

- **compact** -- `paperId`, `title`, `year`, `venue`, `citationCount`
- **standard** -- compact + `authors`, `externalIds`, `abstract`
- **full** -- standard + `tldr`, `openAccessPdf`, `fieldsOfStudy`, `referenceCount`

---

### `get_paper`

Fetch full metadata for a single paper.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | DOI, S2 paper ID, `ARXIV:id`, `ACM:id`, or `PMID:id` |

**Returns:** Full paper metadata (always uses the `full` field set) or `{"error": "not_found"}`.

Results are cached for 30 days. Identifier aliases (e.g. DOI to S2 ID) are cached permanently.

---

### `get_author`

Fetch an author profile or search by name.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | Numeric S2 author ID for direct lookup, or a name string for search |
| `limit` | int | `20` | Max publications to return (direct lookup) |
| `offset` | int | `0` | Pagination offset for publications |

**Returns:**

- **Direct lookup** (numeric ID): author profile with paginated publications list
- **Name search** (text): `{"candidates": [...]}` with up to 5 matching authors

---

## Citation Graph

### `get_citations`

Forward citations -- papers that cite the given paper.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | Paper ID (DOI, S2 ID, etc.) |
| `fields` | string | `"compact"` | Field set for citing papers |
| `limit` | int | `20` | Max results (max 1000) |
| `offset` | int | `0` | Pagination offset |
| `year_start` | int | -- | Filter: earliest year |
| `year_end` | int | -- | Filter: latest year |
| `fields_of_study` | list[string] | -- | Field-of-study filter |
| `min_citations` | int | -- | Minimum citation count filter |

**Returns:** `{"data": [{"citingPaper": {...}}, ...]}`.

---

### `get_references`

Backward references -- papers cited by the given paper.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | Paper ID (DOI, S2 ID, etc.) |
| `fields` | string | `"compact"` | Field set for cited papers |
| `limit` | int | `50` | Max results (max 1000) |
| `offset` | int | `0` | Pagination offset |

**Returns:** `{"data": [{"citedPaper": {...}}, ...]}`.

---

### `get_citation_graph`

BFS traversal from one or more seed papers, collecting nodes and edges.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `seed_ids` | list[string] | *(required)* | 1--10 seed paper IDs |
| `direction` | string | `"citations"` | `citations` (forward), `references` (backward), or `both` |
| `depth` | int | `1` | BFS depth (1--3, clamped) |
| `max_nodes` | int | `100` | Hard cap on collected nodes |
| `year_start` | int | -- | Filter: earliest year |
| `year_end` | int | -- | Filter: latest year |
| `fields_of_study` | list[string] | -- | Field-of-study filter |
| `min_citations` | int | -- | Minimum citation count filter |

**Returns:**

```json
{
  "nodes": [{"id": "...", "title": "...", "year": 2024, "citationCount": 42}, ...],
  "edges": [{"source": "id1", "target": "id2"}, ...],
  "stats": {
    "total_nodes": 42,
    "total_edges": 67,
    "depth_reached": 2,
    "truncated": false
  }
}
```

!!! tip "Controlling graph size"
    Start with `depth=1` and a small `max_nodes` to get an overview, then increase as needed. `depth=3` with `direction=both` can produce very large graphs.

See [Citation Graphs guide](../guides/citation-graphs.md) for usage patterns.

---

### `find_bridge_papers`

Find the shortest citation path between two papers.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `source_id` | string | *(required)* | Starting paper ID |
| `target_id` | string | *(required)* | Target paper ID |
| `max_depth` | int | `4` | Maximum BFS depth |
| `direction` | string | `"both"` | `citations`, `references`, or `both` |

**Returns:**

```json
{
  "found": true,
  "path": [
    {"paperId": "source", "title": "...", ...},
    {"paperId": "bridge", "title": "...", ...},
    {"paperId": "target", "title": "...", ...}
  ]
}
```

Or `{"found": false}` if no path exists within `max_depth`.

---

## Recommendations

### `recommend_papers`

Paper recommendations based on positive (and optional negative) examples.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `positive_ids` | list[string] | *(required)* | 1--5 S2 paper IDs as positive examples |
| `negative_ids` | list[string] | -- | S2 paper IDs to steer recommendations away from |
| `limit` | int | `10` | Number of recommendations |
| `fields` | string | `"standard"` | Field set for returned papers |

**Returns:** JSON list of recommended papers.

!!! tip
    Recommendations work best with 3--5 positive examples that represent the topic you're interested in. Adding 1--2 negative examples that are close but off-topic helps narrow results.

---

## Utility

### `batch_resolve`

Resolve up to 100 identifiers to full metadata in a single call.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifiers` | list[string] | *(required)* | Up to 100 IDs: S2 paper IDs, `DOI:xxx`, or plain DOIs |
| `fields` | string | `"standard"` | Field set |

**Returns:** JSON list of `{"identifier": "...", "paper": {...}}` or `{"identifier": "...", "error": "not_found"}`.

Papers not found in Semantic Scholar are automatically tried via OpenAlex (by DOI). Results from OpenAlex include `"source": "openalex"`.

---

### `enrich_paper`

Augment Semantic Scholar metadata with OpenAlex data.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | S2 paper ID or `DOI:xxx` |
| `fields` | list[string] | *(required)* | Fields to retrieve: `affiliations`, `funders`, `oa_status`, `concepts` |

**Available fields:**

| Field | Description |
|---|---|
| `affiliations` | Institution display names from author affiliations |
| `funders` | Funding organization names |
| `oa_status` | Open access status string (e.g. `gold`, `green`, `hybrid`); also includes `is_oa` boolean |
| `concepts` | List of `{"name": "...", "score": 0.95}` topic concepts |

Results are cached for 30 days.

---

## PDF Conversion

!!! warning "Write-tagged tools"
    All PDF tools are tagged as write operations. They are hidden by default when `SCHOLAR_MCP_READ_ONLY=true`. Set `SCHOLAR_MCP_READ_ONLY=false` to enable them.

### `fetch_paper_pdf`

Download the open-access PDF for a paper.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | Paper ID (DOI, S2 ID, etc.) |

**Returns:** `{"path": "/data/scholar-mcp/pdfs/<id>.pdf"}` or an error:

- `{"error": "no_oa_pdf"}` -- paper has no open-access PDF URL
- `{"error": "download_failed"}` -- HTTP error downloading the PDF

---

### `convert_pdf_to_markdown`

Convert a local PDF file to Markdown via docling-serve.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | *(required)* | Absolute path to a PDF file |
| `use_vlm` | bool | `false` | Enable VLM enrichment for formulas and figures |

**Returns:** `{"markdown": "...", "path": "/data/scholar-mcp/md/<name>.md", "vlm_used": true/false}`.

When `use_vlm` is requested but VLM is not configured, the response includes a `vlm_skip_reason` field (e.g. `"vlm_api_url_not_configured"`).

!!! tip "Start without VLM"
    Standard conversion handles most papers well. Only retry with `use_vlm=true` when the result has garbled formulas or missing figure descriptions. VLM enrichment processes each formula and figure image individually via an external vision model, which is significantly slower.

**Caching:** Standard and VLM conversions are cached separately (`<stem>.md` vs `<stem>_vlm.md`), so switching modes never overwrites a previous conversion.

Requires `SCHOLAR_MCP_DOCLING_URL` to be set. VLM enrichment additionally requires `SCHOLAR_MCP_VLM_API_URL` and `SCHOLAR_MCP_VLM_API_KEY`.

---

### `fetch_and_convert`

Full pipeline: resolve paper, download PDF, convert to Markdown.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | Paper ID (DOI, S2 ID, etc.) |
| `use_vlm` | bool | `false` | Enable VLM enrichment |

**Returns:** On full success:

```json
{
  "metadata": {"paperId": "...", "title": "...", ...},
  "markdown": "# Paper Title\n...",
  "pdf_path": "/data/scholar-mcp/pdfs/<id>.pdf",
  "md_path": "/data/scholar-mcp/md/<id>.md",
  "vlm_used": false
}
```

Partial results are returned if a later stage fails (e.g. metadata + error if no OA PDF is available). When VLM is requested but not configured, the response includes `vlm_skip_reason`.

!!! tip "Start without VLM"
    Same advice as `convert_pdf_to_markdown` — try standard first, add VLM only if formulas or figures are missing. VLM and standard conversions are cached separately (`<id>.md` vs `<id>_vlm.md`).

See [PDF Conversion guide](../guides/pdf-conversion.md) for setup instructions.

---

## Task Polling

### `get_task_result`

Poll for the result of a background task.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | string | *(required)* | Task ID returned by a queued operation |

**Returns:**

```json
{"task_id": "a1b2c3d4e5f6", "status": "completed", "result": "{...}"}
```

Status values: `pending`, `running`, `completed`, `failed`. The `result` field contains the original tool output as a JSON string (only present when `completed`). On `failed`, an `error` field describes the failure.

---

### `list_tasks`

List all active (non-expired) background tasks.

**Returns:** JSON list of `{"task_id": "...", "status": "..."}` dicts.

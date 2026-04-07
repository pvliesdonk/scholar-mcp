# Tools

Scholar MCP provides 22 tools across nine categories. All tools return JSON.

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

## Book Search

Book tools use [Open Library](https://openlibrary.org/) as their data source. No API key is required. Rate limits are handled automatically; if the Open Library API is temporarily unavailable, calls queue and return a task ID (see [Async Task Queue](#async-task-queue)).

### `search_books`

Search for books by title, author, or free text via Open Library. For best results, use the `title` and `author` parameters rather than `query` — they use dedicated search indexes and return far better results.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | `null` | Free-text fallback. Use `title`/`author` when known. |
| `title` | string | `null` | Book title or partial title (recommended). |
| `author` | string | `null` | Author name (recommended). |
| `limit` | int | `10` | Maximum results to return (max 50) |

At least one of `query`, `title`, or `author` must be provided.

When only `query` is given, it is first tried as a title search (better relevance) and falls back to free-text if no results are found. When `author` is given with multiple tokens (e.g. "Frank Duffy") and initial results are thin, a broadened search is automatically attempted to catch name variants (e.g. Frank → Francis).

**Returns:** JSON list of book records. Each record contains:

```json
[
  {
    "title": "Deep Learning",
    "authors": ["Ian Goodfellow", "Yoshua Bengio", "Aaron Courville"],
    "publisher": "MIT Press",
    "year": 2016,
    "edition": null,
    "isbn_10": "0262035618",
    "isbn_13": "9780262035613",
    "openlibrary_work_id": "OL17953442W",
    "openlibrary_edition_id": "OL26423929M",
    "cover_url": "https://covers.openlibrary.org/b/isbn/9780262035613-M.jpg",
    "google_books_url": null,
    "subjects": ["Machine learning", "Artificial intelligence"],
    "page_count": 800,
    "description": null
  }
]
```

---

### `get_book`

Fetch full metadata for a single book by ISBN or Open Library identifier.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | ISBN-10, ISBN-13, Open Library work ID, or edition ID |
| `include_editions` | bool | `false` | If true, fetch work and list editions |

**Identifier formats:**

| Format | Example |
|---|---|
| ISBN-13 | `9780262035613` |
| ISBN-10 | `0262035618` |
| ISBN with hyphens | `978-0-262-03561-3` |
| Open Library work ID | `OL17953442W` |
| Open Library edition ID | `OL26423929M` |

**Returns:** A single book record (same shape as items returned by `search_books`), or `{"error": "not_found", "identifier": "..."}` if not found.

Results are cached. Work and edition lookups are cached by their respective Open Library IDs; ISBN lookups are also stored under the resolved ISBN-13.

---

### `recommend_books`

Recommend books for a subject via the Open Library subject API. Results are sorted by edition count (a proxy for popularity).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `subject` | string | *(required)* | Subject or topic (e.g. "machine learning", "algorithms", "computer vision") |
| `limit` | int | `10` | Maximum results to return (max 50) |

**Returns:** A JSON list of book records. Each record has the same shape as `search_books` results, with fields populated from the Open Library subject API (title, authors, Open Library work ID, cover URL). ISBN and edition fields are `null` since subject results are work-level.

Results are cached for 7 days, keyed by the normalized subject slug. Up to 50 results are fetched and cached; the `limit` parameter slices the cached pool on return.

---

## Auto-Enrichment

When `get_paper`, `get_citations`, `get_references`, or `get_citation_graph` retrieves a paper that has an ISBN in its `externalIds` field, Open Library metadata is automatically fetched and attached as a `book_metadata` key on the paper record.

**Trigger condition:** `externalIds.ISBN` is present and non-empty.

**Added field:** `book_metadata` — a dict containing:

| Field | Description |
|---|---|
| `publisher` | Publisher name |
| `edition` | Edition string (e.g. `"2nd ed."`) |
| `isbn_13` | ISBN-13 |
| `cover_url` | Cover image URL (from Open Library covers) |
| `openlibrary_work_id` | Open Library work ID (e.g. `OL17953442W`) |
| `description` | Work description, if available |
| `subjects` | List of subject strings |
| `page_count` | Page count, if known |
| `authors` | List of author name strings (resolved from Open Library work metadata) |

Enrichment failures are silently skipped — if Open Library is unreachable or the ISBN is not found, the paper record is returned without `book_metadata`. Up to 5 concurrent Open Library requests are made per batch.

---

## Utility

### `batch_resolve`

Resolve up to 100 paper, patent, or book identifiers to full metadata in a single call.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifiers` | list[string] | *(required)* | Up to 100 IDs: S2 paper IDs, `DOI:xxx`, plain DOIs, patent numbers (e.g. `EP1234567A1`), or ISBNs (prefixed `ISBN:`, e.g. `ISBN:9780262035613`) |
| `fields` | string | `"standard"` | Field set (applies to paper results only) |

**Returns:** JSON list of resolved items:

- **Paper results** have a `"paper"` key. Papers not found in Semantic Scholar are automatically tried via OpenAlex (by DOI); results from OpenAlex include `"source": "openalex"`.
- **Patent results** have a `"patent"` key and `"source_type": "patent"`. Patent numbers are auto-detected by their two-letter country prefix (e.g. `EP`, `US`, `WO`) and routed to the EPO OPS API.
- **Book results** have a `"book"` key and `"source_type": "book"`. ISBNs (prefixed with `ISBN:`) are routed to Open Library.
- **Unresolved items** have an `"error"` key.

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

## Citation Generation

### `generate_citations`

Generate formatted citations for one or more papers. Resolves papers via Semantic Scholar, optionally enriches with OpenAlex metadata, and formats as BibTeX, CSL-JSON, or RIS.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `paper_ids` | list[string] | *(required)* | Paper identifiers (S2 IDs, DOIs, arXiv IDs, etc.). Max 100. |
| `citation_format` | string | `"bibtex"` | Output format: `bibtex`, `csl-json`, or `ris` |
| `enrich` | boolean | `true` | Attempt OpenAlex enrichment for missing venue data |

**BibTeX output** includes entry type inference (`@article`, `@inproceedings`, `@misc`), proper author formatting (`{Last}, First`), title casing preservation, DOI, arXiv eprint fields, and special character escaping.

**CSL-JSON output** returns `{"citations": [...], "errors": [...]}` -- the citations array contains standard CSL-JSON objects compatible with Zotero, Mendeley, Pandoc, and other CSL processors.

**RIS output** uses standard RIS tags (`TY`, `AU`, `TI`, `PY`, `JO`/`BT`, `DO`, `UR`, `AB`, `ER`).

Papers that fail to resolve are reported inline (BibTeX/RIS: as comments, CSL-JSON: in the errors array) rather than failing the entire request. When all papers fail, a structured error is returned: `{"error": "no_papers_resolved", "failed": [...]}`.

!!! tip "Enrichment"
    When `enrich` is enabled and a paper has no venue but has a DOI, the tool queries OpenAlex to fill in the venue name. This improves citation quality for papers where Semantic Scholar has incomplete metadata.

---

## Patent Search

!!! note "Credentials required"
    Patent tools require EPO OPS credentials. When `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET` are not set, these tools are automatically hidden. See [EPO OPS configuration](../configuration.md#epo-open-patent-services) for setup instructions.

### `search_patents`

Search for patents across 100+ patent offices via the EPO Open Patent Services (OPS) API.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | *(required)* | Natural language or keyword search query |
| `cpc_classification` | string | -- | CPC classification code filter (e.g. `"H01M10/00"`) |
| `applicant` | string | -- | Applicant (assignee) name filter |
| `inventor` | string | -- | Inventor name filter |
| `date_from` | string | -- | Earliest date (`YYYY-MM-DD`) |
| `date_to` | string | -- | Latest date (`YYYY-MM-DD`) |
| `date_type` | string | `"publication"` | Date field: `publication`, `filing`, or `priority` |
| `jurisdiction` | string | -- | Country code filter (e.g. `EP`, `US`, `WO`) |
| `limit` | int | `10` | Results per page (max 100) |
| `offset` | int | `0` | Pagination offset |

**Returns:** `{"total_count": N, "references": [...]}` where each reference has `country`, `number`, and `kind` fields.

!!! tip "Query syntax"
    The tool translates parameters into EPO CQL internally. The `query` parameter maps to title+abstract search. Use the filter parameters for structured queries — they are properly escaped and quoted.

---

### `get_patent`

Fetch detailed information for a single patent by its publication number.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `patent_number` | string | *(required)* | Patent number in any format (e.g. `EP1234567A1`, `WO2024/123456`, `US11,234,567B2`) |
| `sections` | list[string] | `["biblio"]` | Sections to retrieve |

**Available sections:**

| Section | Description | Status |
|---|---|---|
| `biblio` | Bibliographic metadata (title, applicants, inventors, dates, classifications, abstract) | Available |
| `claims` | Patent claims text (English preferred) | Available |
| `description` | Full patent description text (English preferred) | Available |
| `family` | Patent family members across jurisdictions (country, number, kind, date) | Available |
| `legal` | Legal status events (date, code, description) | Available |
| `citations` | Patent and non-patent literature citations, with Semantic Scholar resolution for NPL | Available |

Sections are fetched concurrently where possible (cache lookups run in parallel; EPO API calls are serialised by the client). Each section is cached independently with appropriate TTLs.

**Returns:** A JSON object with keys matching the requested sections:

```json
{
  "patent_number": "EP.1234567.A1",
  "biblio": {
    "title": "...",
    "abstract": "...",
    "applicants": ["..."],
    "inventors": ["..."],
    "publication_number": "EP.1234567.A1",
    "publication_date": "2020-01-15",
    "filing_date": "2019-06-01",
    "priority_date": "2019-01-15",
    "family_id": "12345678",
    "classifications": ["H04L29/06"],
    "url": "https://worldwide.espacenet.com/..."
  },
  "claims": "1. A method for...\n\n2. The method of claim 1...",
  "family": [
    {"country": "US", "number": "11234567", "kind": "B2", "date": "2021-03-01"}
  ],
  "legal": [
    {"date": "2019-05-01", "code": "APPLICATION", "description": "Application filed"}
  ],
  "citations": {
    "patent_refs": [
      {"country": "US", "number": "9876543", "kind": "B2"}
    ],
    "npl_refs": [
      {"raw": "Smith et al., \"Widget Processing\", 2018, doi:10.1234/test", "paper": {"paperId": "abc123", "title": "Widget Processing"}, "confidence": "high"},
      {"raw": "Doe, \"Advanced Widgets\", 2019", "confidence": null}
    ]
  }
}
```

When `citations` is requested, non-patent literature (NPL) references are resolved against Semantic Scholar on a best-effort basis. References with a DOI are resolved with `"confidence": "high"`. References without a DOI or that fail to resolve have `"confidence": null`.

---

### `get_citing_patents`

Find patents that cite a given academic paper. Coverage is incomplete -- relies on EPO OPS citation search, which does not capture all patent-to-paper citations. Best results with DOIs of well-known papers.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `paper_id` | string | *(required)* | Paper identifier (DOI preferred) |
| `limit` | int | `10` | Maximum citing patents to return (max 25) |

**Returns:**

```json
{
  "paper_id": "10.1234/test",
  "patents": [
    {"title": "...", "publication_number": "EP.9999999.A1", "match_source": "epo_search", ...}
  ],
  "total_count": 1,
  "note": "Coverage is incomplete. Results come from EPO OPS citation search..."
}
```

!!! warning "Incomplete coverage"
    Not all patent-to-paper citations are captured by EPO OPS. Use this tool for discovery, not exhaustive analysis.

---

## PDF Conversion

!!! warning "Write-tagged tools"
    All PDF tools are tagged as write operations. They are hidden by default when `SCHOLAR_MCP_READ_ONLY=true`. Set `SCHOLAR_MCP_READ_ONLY=false` to enable them.

### `fetch_paper_pdf`

Download the PDF for a paper. Tries the Semantic Scholar open-access URL first, then falls back to alternative sources: ArXiv (from `externalIds`), PubMed Central, and Unpaywall (by DOI, requires `SCHOLAR_MCP_CONTACT_EMAIL`).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `identifier` | string | *(required)* | Paper ID (DOI, S2 ID, etc.) |

**Returns:** `{"path": "/data/scholar-mcp/pdfs/<id>.pdf", "source": "s2_oa"}` or an error:

- `{"error": "no_oa_pdf"}` -- no PDF URL found from any source
- `{"error": "download_failed"}` -- HTTP error downloading the PDF

The `source` field indicates where the PDF was obtained: `s2_oa`, `arxiv`, `pmc`, or `unpaywall`.

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

Full pipeline: resolve paper, download PDF, convert to Markdown. Uses the same alternative source fallback as `fetch_paper_pdf`.

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
  "pdf_source": "s2_oa",
  "vlm_used": false
}
```

Partial results are returned if a later stage fails (e.g. metadata + error if no OA PDF is available). The `pdf_source` field indicates the download source. When VLM is requested but not configured, the response includes `vlm_skip_reason`.

!!! tip "Start without VLM"
    Same advice as `convert_pdf_to_markdown` — try standard first, add VLM only if formulas or figures are missing. VLM and standard conversions are cached separately (`<id>.md` vs `<id>_vlm.md`).

See [PDF Conversion guide](../guides/pdf-conversion.md) for setup instructions.

---

### `fetch_pdf_by_url`

Download a PDF from any URL and optionally convert to Markdown. Use this when you have found an alternative PDF link (e.g. from an author's homepage, a preprint server, or an institutional repository).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | string | *(required)* | Direct URL to a PDF file |
| `filename` | string | -- | Filename stem for caching (e.g. `"smith2024_attention"`). Derived from the URL if omitted. |
| `use_vlm` | bool | `false` | Enable VLM enrichment for formulas and figures |

**Returns:** On success (with docling configured):

```json
{
  "pdf_path": "/data/scholar-mcp/pdfs/<filename>.pdf",
  "markdown": "# Paper Title\n...",
  "md_path": "/data/scholar-mcp/md/<filename>.md",
  "vlm_used": false
}
```

Without docling, only `pdf_path` is returned. The PDF is cached by filename, so subsequent calls with the same filename return immediately.

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

While the task is in progress (`pending` or `running`), the response includes extra fields:

```json
{
  "task_id": "a1b2c3d4e5f6",
  "status": "running",
  "elapsed_seconds": 45,
  "tool": "convert_pdf_to_markdown",
  "hint": "PDF conversion typically takes 1-5 minutes depending on page count."
}
```

The `hint` field gives expected duration — keep polling until the task completes.

---

### `list_tasks`

List all active (non-expired) background tasks.

**Returns:** JSON list of `{"task_id": "...", "status": "..."}` dicts.

# Patents

Patent tools reach the EPO Open Patent Services API and need EPO OPS credentials. Without `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET` they're hidden. [Obtaining EPO OPS credentials](https://pvliesdonk.github.io/scholar-mcp/unstable/reference/configuration/#patents-obtaining-epo-ops-credentials) covers setup.

## `search_patents`

**Search Patents.** Read-only. Reaches outside the server. Tags: `patent`.

Search for patents in the European Patent Office database.

Covers European patents and global patents via INPADOC (100+ patent offices). At least one parameter must be provided. For keyword search, `query` searches titles and abstracts. To find all patents by an inventor or applicant, omit `query` and use only the structured filters. For academic paper search, use `search_papers` instead.

When EPO reports itself busy this waits for it to clear, which can take a few minutes, so the call may answer with a job handle to poll using `get_job_result` rather than the result itself. Do not reason about EPO throttle states yourself.

**Parameters**

| Name                 | Type                                | Default         | Description                                                                                                                      |
| -------------------- | ----------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `query`              | `string \| null`                    | `null`          | Keyword search over patent titles and abstracts. Optional; omit when searching purely by inventor, applicant, CPC code, or date. |
| `cpc_classification` | `string \| null`                    | `null`          | CPC classification code to filter by, such as `"H01M10/00"` for lithium-ion batteries.                                           |
| `applicant`          | `string \| null`                    | `null`          | Applicant (assignee) name to filter by.                                                                                          |
| `inventor`           | `string \| null`                    | `null`          | Inventor name to filter by.                                                                                                      |
| `date_from`          | `string \| null`                    | `null`          | Earliest date (`YYYY-MM-DD`).                                                                                                    |
| `date_to`            | `string \| null`                    | `null`          | Latest date (`YYYY-MM-DD`).                                                                                                      |
| `date_type`          | `publication \| filing \| priority` | `"publication"` | Date field to apply the range to: `"publication"`, `"filing"` or `"priority"`.                                                   |
| `jurisdiction`       | `string \| null`                    | `null`          | Restrict to a single patent authority, such as `"EP"`, `"WO"` or `"US"`.                                                         |
| `limit`              | `integer`                           | `10`            | Maximum results to return (default 10).                                                                                          |
| `offset`             | `integer`                           | `0`             | Pagination offset (0-based).                                                                                                     |

**Returns**

A mapping with `total_count` and a `references` list, or an error mapping if the EPO client is not configured or the API fails. A busy EPO service is waited out rather than failed on, which can take a few minutes; the call is then handed back as `{"status": "working", "job_id": "..."}` and the result retrieved with `get_job_result`. If the service never clears, the outcome is `{"error": "rate_limited", "retryable": true}` with a hint, and an exhausted daily quota is `{"error": "epo_unavailable", "retryable": false}`. Do not manage or reason about EPO throttle states directly.

Each entry in `references` has `country`, `number`, and `kind` fields.

Query syntax

The tool translates parameters into EPO CQL internally. `query` will not find patents where the keyword appears only in inventor/applicant names. Combining `query` with filters applies both constraints.

## `get_patent`

**Get Patent.** Read-only. Reaches outside the server. Tags: `patent`.

Get detailed information about a single patent.

Accepts patent numbers in any format (EP, WO, US, etc.). By default returns bibliographic data only; use the sections parameter to request additional detail (claims, description, family members, legal status, cited references). When sections includes 'citations', non-patent literature references are resolved to Semantic Scholar papers on a best-effort basis; unresolved references are returned as raw citation strings.

When EPO reports itself busy this waits for it to clear, which can take a few minutes, so the call may answer with a job handle to poll using `get_job_result` rather than the result itself. Do not reason about EPO throttle states yourself.

**Parameters**

| Name            | Type                                                                               | Default  | Description                                                                                                                                                                                                                                    |
| --------------- | ---------------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `patent_number` | `string`                                                                           | required | Patent number in any common format, such as `"EP1234567A1"`, `"WO2024/123456"` or `"US11,234,567B2"`.                                                                                                                                          |
| `sections`      | `array of biblio \| claims \| description \| family \| legal \| citations \| null` | `null`   | Sections to include in the response. Defaults to `["biblio"]`. Available sections: biblio, claims, description, family, legal, citations. When citations is included, NPL references are resolved via Semantic Scholar on a best-effort basis. |

**Returns**

A mapping with `patent_number` (normalised DOCDB format) and the requested section data, or an error mapping on failure. A busy EPO service is waited out rather than failed on, which can take a few minutes; the call is then handed back as `{"status": "working", "job_id": "..."}` and the result retrieved with `get_job_result`. If the service never clears, the outcome is `{"error": "rate_limited", "retryable": true}` with a hint, and an exhausted daily quota is `{"error": "epo_unavailable", "retryable": false}`. Do not manage or reason about EPO throttle states directly.

**Available sections:**

| Section       | Description                                                                             | Status    |
| ------------- | --------------------------------------------------------------------------------------- | --------- |
| `biblio`      | Bibliographic metadata (title, applicants, inventors, dates, classifications, abstract) | Available |
| `claims`      | Patent claims text (English preferred)                                                  | Available |
| `description` | Full patent description text (English preferred)                                        | Available |
| `family`      | Patent family members across jurisdictions (country, number, kind, date)                | Available |
| `legal`       | Legal status events (date, code, description, country)                                  | Available |
| `citations`   | Patent and non-patent literature citations, with Semantic Scholar resolution for NPL    | Available |

`country` is the contracting state a legal event concerns. EPO sends it only on the event types that name one, such as `PG25` (lapsed in a state), `REG` and `PGFP`, so it is an empty string on the rest. It is what distinguishes the otherwise identical `PG25` events a patent accumulates as it lapses state by state.

Sections are fetched concurrently where possible (cache lookups run in parallel; EPO API calls are serialised by the client). Each section is cached independently with appropriate TTLs.

A response has keys matching the requested sections:

```
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
    {"date": "2021-07-30", "code": "PG25", "description": "LAPSED IN A CONTRACTING STATE [...]", "country": "BG"}
  ],
  "citations": {
    "patent_refs": [
      {"country": "US", "number": "9876543", "kind": "B2"}
    ],
    "npl_refs": [
      {"raw": "Smith et al., \"Widget Processing\", 2018, doi:10.1234/test", "paper": {"paperId": "abc123", "title": "Widget Processing"}, "confidence": "high"},
      {"raw": "Doe, \"Advanced Widgets\", Ch. 5, pp. 112-130, 2019", "confidence": null, "chapter_info": {"citation_source": "parsed", "chapter_number": 5, "page_start": 112, "page_end": 130}}
    ]
  }
}
```

In `citations`, NPL references with a DOI are resolved with `"confidence": "high"`. A DOI is recognised after `doi:`, `DOI`, or in a `doi.org` link, and one that does not resolve is still returned in `doi`. References without a DOI or that fail to resolve have `"confidence": null`. When citation strings contain chapter patterns (such as "Ch. 5" or "pp. 112-130"), a `chapter_info` dict is included with parsed chapter and page information.

## `get_citing_patents`

**Get Citing Patents.** Read-only. Reaches outside the server. Tags: `patent`.

Find patents that cite a given academic paper.

Coverage is incomplete: it relies on EPO OPS citation search, which does not capture all patent-to-paper citations. Best results with DOIs of well-known, highly cited papers. Returns confirmed matches only, not an exhaustive list.

When EPO reports itself busy this waits for it to clear, which can take a few minutes, so the call may answer with a job handle to poll using `get_job_result` rather than the result itself. Do not reason about EPO throttle states yourself.

**Parameters**

| Name       | Type      | Default  | Description                                                      |
| ---------- | --------- | -------- | ---------------------------------------------------------------- |
| `paper_id` | `string`  | required | Paper identifier (DOI preferred, also accepts title keywords).   |
| `limit`    | `integer` | `10`     | Maximum number of citing patents to return (default 10, max 25). |

**Returns**

A mapping with `paper_id`, a `patents` list (each with biblio data and `match_source`), `total_count`, and a `note` about coverage limitations. A busy EPO service is waited out rather than failed on, which can take a few minutes; the call is then handed back as `{"status": "working", "job_id": "..."}` and the result retrieved with `get_job_result`. If the service never clears, the outcome is `{"error": "rate_limited", "retryable": true}` with a hint, and an exhausted daily quota is `{"error": "epo_unavailable", "retryable": false}`. Do not manage or reason about EPO throttle states directly.

A response looks like:

```
{
  "paper_id": "10.1234/test",
  "patents": [
    {"title": "...", "publication_number": "EP.9999999.A1", "match_source": "epo_search", ...}
  ],
  "total_count": 1,
  "note": "Coverage is incomplete. Results come from EPO OPS citation search..."
}
```

## `fetch_patent_pdf`

**Fetch Patent PDF.** Changes state, not destructive. Reaches outside the server. Tags: `patent`, `write`.

Download a patent PDF via authenticated EPO OPS and convert to Markdown.

Downloads the full-document PDF for a patent using the authenticated EPO Open Patent Services session, saves it locally, and if docling is configured converts it to Markdown. EPO serves patent images one page per request, so a long patent costs one request per page and the document is reassembled before conversion.

Not all patents have full text available through OPS: WO and older EP patents sometimes lack PDFs. Returns an error in that case.

A previously downloaded and converted patent answers immediately; a fresh download plus conversion typically takes 1-5 minutes and is returned as a background job handle instead.

When EPO reports itself busy this waits for it to clear, which can take a few minutes, so the call may answer with a job handle to poll using `get_job_result` rather than the result itself. Do not reason about EPO throttle states yourself.

Markdown is returned in pages of at most 20,000 characters. When `next_offset` is present, call this tool again with that value as `text_offset`; the cached conversion makes later pages inexpensive. Set `max_chars` to null only when the client can accept the complete document in one response.

**Parameters**

| Name            | Type              | Default  | Description                                                                                                    |
| --------------- | ----------------- | -------- | -------------------------------------------------------------------------------------------------------------- |
| `patent_number` | `string`          | required | Patent number in any format (EP, WO, US and others), such as `EP3491801B1`, `EP 3491801 B1` or `US10123456B2`. |
| `use_vlm`       | `boolean`         | `false`  | Use VLM enrichment for formulas and figures (requires VLM to be configured).                                   |
| `text_offset`   | `integer`         | `0`      | Character offset at which the Markdown page starts.                                                            |
| `max_chars`     | `integer \| null` | `20000`  | Maximum Markdown characters to return, capped at 20,000. Pass `null` for the complete text.                    |

**Returns**

`pdf_path` and optionally `markdown` / `md_path`.

A response looks like `{"pdf_path": "/data/scholar-mcp/pdfs/<stem>.pdf", "markdown": "...", "md_path": "/data/scholar-mcp/md/<stem>.md"}` when docling is configured, or just `{"pdf_path": "..."}` without it.

When `markdown` is present, the response also reports `text_offset`, `text_returned_chars`, `text_total_chars`, and `text_truncated`.

A patent with no PDF available through OPS returns `{"error": "pdf_not_available"}`.

Download time

A 21-page patent takes roughly 20 seconds to download; longer patents scale linearly, which is part of why this tool commonly answers with a job handle.

Write-tagged

This tool carries both gates: it is hidden when `SCHOLAR_MCP_READ_ONLY=true`, and like every patent tool it is hidden when EPO OPS credentials are not set.

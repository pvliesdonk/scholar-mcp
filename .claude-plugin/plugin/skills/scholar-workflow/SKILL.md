---
name: scholar-workflow
description: Use when the user asks you to search, retrieve, or reason about scholarly sources — papers, patents, books, or standards — guides tool selection, chaining, and cross-domain workflows.
---

# Working effectively with scholarly sources

When the user asks about academic literature, prior art, citations, patents,
books, or standards, use the scholar-mcp tools as described below. The server
covers four source domains: **papers**, **patents**, **books**, and
**standards**. Each domain has its own tools, but they cross-reference
naturally — a paper may cite a patent, a patent's NPL section may reference a
paper, and a paper with an ISBN is automatically enriched with book metadata.

## Choosing the right search entry point

| User intent | Tool | Key parameters |
|---|---|---|
| Find papers on a topic | `search_papers` | `query`, `year_start`/`year_end`, `fields_of_study`, `venue`, `min_citations`, `sort` |
| Look up a specific paper | `get_paper` | `identifier` — DOI, S2 ID, `ARXIV:id`, `ACM:id`, `PMID:id` |
| Find an author's work | `get_author` | Numeric S2 author ID for profile, or name string for disambiguation |
| Find patents | `search_patents` | `query`, `cpc_classification`, `applicant`, `inventor`, `jurisdiction`, date filters |
| Look up a specific patent | `get_patent` | `patent_number`, `sections` (biblio, claims, description, family, legal, citations) |
| Find books | `search_books` | Prefer `title`/`author` over `query` — dedicated indexes give better recall |
| Look up a book by ISBN | `get_book` | `identifier` — ISBN-10, ISBN-13, OL work ID, or edition ID |
| Find a standard | `search_standards` | `query`, optional `body` filter (NIST, IETF, W3C, ETSI) |
| Normalise a messy citation | `resolve_standard_identifier` | `raw` — e.g. "rfc9000", "nist 800-53", "wcag 2.2" |
| Resolve a mixed list of IDs | `batch_resolve` | `identifiers` — mix of DOIs, S2 IDs, patent numbers, `ISBN:` prefixed ISBNs |

**Domain-sticky traversal:** a paper's references mostly point to other
papers; a patent's family members are other patents; a standard often cites
other standards. Follow the domain naturally — don't switch tools mid-chain
unless the data leads you there (e.g. a patent's NPL citations resolve to
papers).

## Literature search strategies

### Broad survey

1. `search_papers` with a broad query. Use `sort="citations"` and
   `min_citations` to surface influential work quickly.
2. Pick the most relevant hit and call `get_citations` to see who built on it.
3. Call `get_references` on the same paper to see what it builds on.
4. If the topic spans disciplines, use `fields_of_study` to split searches
   (e.g. search once for "Computer Science", once for "Medicine").

### Targeted lookup

- When the user gives a DOI, arXiv ID, or other identifier, go straight to
  `get_paper`. Don't search first.
- For author-centric queries, `get_author` with a name returns up to 5
  disambiguation candidates. Ask the user to pick before fetching
  publications — don't guess.

### Patent prior art

1. `search_patents` with keywords, CPC codes, or applicant names.
2. `get_patent` with `sections=["biblio", "citations"]` — the citations
   section includes NPL references automatically resolved to S2 papers.
3. `get_citing_patents` finds patents that cite a given paper (coverage is
   incomplete — EPO OPS does not capture all citations).

### Standards lookup

- `resolve_standard_identifier` handles messy input ("rfc 9000",
  "NIST SP 800-53 rev5") and normalises to canonical form. Use it first when
  the user gives an informal name.
- `get_standard` with `fetch_full_text=true` downloads and converts the
  standard via docling (requires `SCHOLAR_MCP_DOCLING_URL`). This may block
  until conversion completes; it only returns a task ID if rate-limited.

## Citation graph traversal

### Forward and backward citations

- `get_citations` — papers that cite a given paper (forward). Supports year,
  field, and minimum citation count filters.
- `get_references` — papers cited by a given paper (backward).
- Both return paginated results. Use `offset` for additional pages.

### BFS graph expansion

`get_citation_graph` does breadth-first expansion from 1–10 seed papers.

- `depth` 1 is usually sufficient for a neighbourhood view. Depth 2–3
  expands rapidly — always set `max_nodes` to cap growth.
- `direction="both"` finds the densest cluster but doubles API calls per hop.
  Use `"citations"` or `"references"` when the user has a clear direction.
- Combine with `year_start`/`year_end` and `min_citations` to keep results
  focused. When filters are active, the tool fetches more candidates per node
  to compensate for filtering losses.

### Bridge papers

`find_bridge_papers` finds the shortest citation path between two papers.
Useful for connecting seemingly unrelated work. Searches up to `max_depth`
hops (default 4). Use `direction="both"` for best coverage.

## Recommendations

`recommend_papers` takes 1–5 positive paper IDs and optional negative IDs.
The positive examples define the topic; negatives steer away from unwanted
areas. For best results, pick positive examples that span the desired topic
rather than clustering around one sub-area.

`recommend_books` takes a subject string (e.g. "machine learning", "algorithms")
and returns popular books from Open Library sorted by edition count.

## Citation generation

`generate_citations` produces BibTeX, CSL-JSON, or RIS for up to 100 papers.

- `enrich=true` (the default) adds OpenAlex venue metadata for more complete
  BibTeX entries (journal names, volumes, pages).
- Unresolved paper IDs are included in the output with a "not found" note
  rather than silently dropped.

## Enrichment

- **Book enrichment** is automatic: any paper with an ISBN in `externalIds`
  gets a `book_metadata` field (publisher, edition, cover URL, subjects)
  from Open Library. No extra tool call needed.
- `enrich_paper` adds OpenAlex fields (affiliations, funders, OA status,
  concepts) on demand. Useful when the user needs institutional or funding
  context beyond what S2 provides.

## Full-text retrieval and PDF conversion

PDF tools are write-tagged and hidden in read-only mode (the default). The
user must set `SCHOLAR_MCP_READ_ONLY=false` and have a running docling-serve
instance (`SCHOLAR_MCP_DOCLING_URL`) for Markdown conversion.

### Papers

- `fetch_paper_pdf` downloads the PDF with automatic fallback: S2 open-access
  → ArXiv → PubMed Central → Unpaywall.
- `fetch_and_convert` does fetch + convert in one call — usually what users
  want.
- `fetch_pdf_by_url` handles arbitrary PDF URLs (e.g. an author's website).
- `convert_pdf_to_markdown` converts a local PDF file to Markdown — use this
  when you already have the PDF on disk (e.g. a paywalled paper obtained
  manually). Accepts an absolute `file_path`.

### Patents

- `fetch_patent_pdf` downloads via authenticated EPO OPS. Not all patents
  have PDFs available (older patents, some WO publications).

### Standards

- `get_standard` with `fetch_full_text=true` fetches and converts in one call.

### VLM enrichment

Pass `use_vlm=true` to `fetch_and_convert`, `fetch_pdf_by_url`,
`fetch_patent_pdf`, or `convert_pdf_to_markdown` for better formula and figure
extraction. (`get_standard` uses docling internally but does not expose the VLM
flag.) Requires `SCHOLAR_MCP_VLM_API_URL` and `SCHOLAR_MCP_VLM_API_KEY`.
VLM and standard conversions are cached separately — switching modes never
overwrites previous results.

## Handling queued operations

PDF downloads (`fetch_paper_pdf`), patent PDF fetches (`fetch_patent_pdf`),
full pipeline runs (`fetch_and_convert`), and any tool that hits a rate limit
return a task ID:

```json
{"queued": true, "task_id": "abc123", "tool": "..."}
```

Poll with `get_task_result(task_id="abc123")`. The response includes
`status`, `elapsed_seconds`, and a `hint` while running.

`list_tasks` shows all active tasks. Don't poll in a tight loop — tasks
typically complete in 10–30 seconds (PDF download) or 1–5 minutes (PDF
conversion with VLM).

## Do not

- Do not call `search_papers` when the user gives a specific identifier —
  use `get_paper` directly.
- Do not call `get_author` with a name and then silently pick the first
  candidate — ask the user to disambiguate.
- Do not set `depth` > 2 in `get_citation_graph` without also setting a
  tight `max_nodes` cap — the graph expands exponentially.
- Do not use `fetch_pdf_by_url` for EPO OPS patent URLs — they require
  authentication. Use `fetch_patent_pdf` instead.
- Do not forget `batch_resolve` when the user gives a mixed list of
  identifiers — it routes each to the correct backend automatically.

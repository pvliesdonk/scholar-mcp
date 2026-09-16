# Scholar MCP

Scholarly papers, patents, books, standards and PDF conversion

## Getting started

- [Installation](https://pvliesdonk.github.io/scholar-mcp/unstable/installation/index.md)
- [Configuration](https://pvliesdonk.github.io/scholar-mcp/unstable/configuration/index.md)
- [Tools](https://pvliesdonk.github.io/scholar-mcp/unstable/tools/index.md)

## Features

Scholar MCP exposes 29 tools that let LLM-powered applications search, cross-reference, and retrieve scholarly sources across four peer domains:

- **Papers**: full-text search (year, venue, field, citation filters); single-paper lookup by DOI / S2 ID / arXiv / ACM / PubMed; author profile and name search; forward citations, backward references, BFS citation graph, shortest-path bridge discovery; recommendations from positive/negative examples; BibTeX/CSL-JSON/RIS citation generation; OpenAlex enrichment (affiliations, funders, OA status, and concepts).
- **Patents**: search across 100+ patent offices via EPO OPS with CPC / applicant / inventor / jurisdiction filters; biblio, claims, description, family, legal and citations sections; NPL-to-paper resolution via Semantic Scholar and paper-to-patent citation discovery; patent PDF download via EPO OPS.
- **Books**: search by title/author/keywords via Open Library; lookup by ISBN or Open Library ID; subject recommendations. Papers with an ISBN are automatically enriched with publisher/edition/cover/subject metadata.
- **Standards**: identifier resolution, search, and metadata retrieval for NIST, IETF, W3C, and ETSI, with optional full-text fetch and Markdown conversion via docling.
- **Cross-source Utility**: resolve up to 100 mixed identifiers (paper DOIs, patent numbers, ISBNs) to full metadata in one call.
- **PDF conversion**: download PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures; automatic fallback to ArXiv, PubMed Central, and Unpaywall; direct URL download for alternative versions.
- **Background jobs**: slow work returns a job handle to poll with `get_job_result`, while a fast call or a cache hit answers directly.

Results are cached in a local SQLite database with per-table TTLs to reduce API calls and speed up repeated lookups.

Coverage by domain

Per-domain depth varies: papers have the richest tool surface and standards the least. That reflects public data availability, not a value hierarchy: writing a paper typically needs all four source types for citations and prior art. Parity work is tracked in [GitHub issues](https://github.com/pvliesdonk/scholar-mcp/issues) and [milestones](https://github.com/pvliesdonk/scholar-mcp/milestones), the roadmap shows intent, not a completeness commitment.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                       MCP Client                              │
│             (Claude Desktop, Claude Code, etc.)               │
└──────────────────────────┬────────────────────────────────────┘
                           │ stdio / HTTP / SSE
┌──────────────────────────▼────────────────────────────────────┐
│                  scholar-mcp (FastMCP)                        │
│                                                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐ ┌──────────┐  │
│  │ Papers │ │Patents │ │ Books  │ │ Standards │ │   PDF    │  │
│  │  (10)  │ │  (4)   │ │  (3)   │ │    (3)    │ │   (4)    │  │
│  └────┬───┘ └────┬───┘ └────┬───┘ └─────┬─────┘ └─────┬────┘  │
│       │         │          │           │             │       │
│       + Cross-source Utility (1) · Job Polling (1)          │
│                                                               │
│  ┌────▼─────────▼──────────▼───────────▼─────────────▼────┐  │
│  │                  SQLite Cache (TTL)                    │  │
│  └───┬──────┬──────────┬───────┬──────────┬─────────┬─────┘  │
└──────┼──────┼──────────┼───────┼──────────┼─────────┼────────┘
       │      │          │       │          │         │
  ┌────▼───┐ ┌▼────────┐ ┌▼────┐ ┌▼──────┐ ┌▼───────┐ ┌▼──────┐
  │Semantic│ │OpenAlex │ │ EPO │ │ Open  │ │ NIST / │ │docling│
  │Scholar │ │   API   │ │ OPS │ │Library│ │  IETF /│ │ -serve│
  │  API   │ │         │ │     │ │       │ │  W3C / │ │(opt.) │
  │        │ │         │ │     │ │       │ │  ETSI  │ │       │
  └────────┘ └─────────┘ └─────┘ └───────┘ └────────┘ └───────┘
```

## What you can do

- **Survey a field**: "Find the 20 most-cited papers on graph neural networks from 2020 to 2024 and draft a literature review outline." Composes `search_papers` + `get_citations` + `enrich_paper`.
- **Trace a citation path**: "What's the shortest citation path from 'Attention is All You Need' to 'RLHF for dialogue agents'?" Uses `find_bridge_papers` + `get_citation_graph`.
- **Cross-reference prior art**: "For this patent family, list academic papers it cites and any books or standards that show up in the description." Composes `get_patent` + `batch_resolve` + standards/book enrichment.
- **Generate a bibliography**: "Emit BibTeX for these 30 DOIs with OpenAlex venue data." Uses `generate_citations`.
- **Look up a standard**: "What's the latest status of RFC 9000, and fetch the Markdown full text." Uses `resolve_standard_identifier` + `get_standard`.

# Scholar MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server for the scholarly citation landscape -- **papers**, **patents**, **books**, and **standards** -- giving LLMs a unified way to search, cross-reference, and retrieve prior art across all four source types via [Semantic Scholar](https://www.semanticscholar.org/), [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops), [Open Library](https://openlibrary.org/), and standards bodies, with [OpenAlex](https://openalex.org/) enrichment and optional [docling-serve](https://github.com/DS4SD/docling-serve) PDF/full-text conversion.

## What it does

Scholar MCP exposes 27 tools that let LLM-powered applications search, cross-reference, and retrieve scholarly sources across four peer domains:

- **Papers** -- full-text search (year, venue, field, citation filters); single-paper lookup by DOI / S2 ID / arXiv / ACM / PubMed; author profile and name search; forward citations, backward references, BFS citation graph, shortest-path bridge discovery; recommendations from positive/negative examples; BibTeX/CSL-JSON/RIS citation generation; OpenAlex enrichment (affiliations, funders, OA status, and concepts).
- **Patents** -- search across 100+ patent offices via EPO OPS with CPC / applicant / inventor / jurisdiction filters; biblio, claims, description, family, legal and citations sections; NPL-to-paper resolution via Semantic Scholar and paper-to-patent citation discovery.
- **Books** -- search by title/author/keywords via Open Library; lookup by ISBN or Open Library ID; subject recommendations. Papers with an ISBN are automatically enriched with publisher/edition/cover/subject metadata.
- **Standards** -- identifier resolution, search, and metadata retrieval for NIST, IETF, W3C, and ETSI, with optional full-text fetch and Markdown conversion via docling.
- **Cross-source utility** -- resolve up to 100 mixed identifiers (paper DOIs, patent numbers, ISBNs) to full metadata in one call.
- **PDF conversion** -- download PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures; automatic fallback to ArXiv, PubMed Central, and Unpaywall; direct URL download for alternative versions.
- **Async task queue** -- long-running operations return immediately with a task ID; poll for results with `get_task_result`.

Results are cached in a local SQLite database with per-table TTLs to minimize API calls and speed up repeated lookups.

!!! info "Coverage by domain"
    Per-domain depth is uneven — papers currently have the richest tool surface, standards the leanest. That reflects public data availability, not a value hierarchy: writing a paper typically needs all four source types for citations and prior art. Parity work is tracked in [GitHub issues](https://github.com/pvliesdonk/scholar-mcp/issues) and [milestones](https://github.com/pvliesdonk/scholar-mcp/milestones) — the roadmap shows intent, not a completeness commitment.

## Quick start

=== "uvx (recommended)"

    ```bash
    uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
    ```

=== "pip"

    ```bash
    pip install 'pvliesdonk-scholar-mcp[mcp]'
    scholar-mcp serve
    ```

=== "Docker"

    ```bash
    docker run -v scholar-mcp-data:/data/scholar-mcp \
               ghcr.io/pvliesdonk/scholar-mcp:latest
    ```

!!! tip "API key optional but recommended"
    The server works without a Semantic Scholar API key, but unauthenticated requests are limited to ~1 req/s and will hit 429 throttles quickly during multi-step operations like citation graph traversal. [Request a free key](https://www.semanticscholar.org/product/api#api-key-form) to get ~10 req/s. Pass it via `SCHOLAR_MCP_S2_API_KEY=your-key`.

See [Installation](installation.md) for all methods including Linux packages.

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
│       + Cross-source Utility (1) · Task Polling (2)          │
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

## Next steps

- [Installation](installation.md) -- all installation methods
- [Configuration](configuration.md) -- environment variable reference
- [Tools](tools/index.md) -- full tool reference with parameters
- [Claude Desktop setup](guides/claude-desktop.md) -- get started with Claude Desktop
- [Docker deployment](deployment/docker.md) -- production Docker Compose setup

# Scholar MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server providing structured academic literature access via [Semantic Scholar](https://www.semanticscholar.org/), with [OpenAlex](https://openalex.org/) enrichment and optional [docling-serve](https://github.com/DS4SD/docling-serve) PDF conversion.

## What it does

Scholar MCP exposes 13 tools that let LLM-powered applications search, explore, and retrieve academic papers:

- **Search & retrieval** -- find papers by keyword, look up by DOI/arXiv/S2 ID, search authors
- **Citation graph** -- traverse forward citations, backward references, build citation graphs, discover bridge papers between fields
- **Recommendations** -- get paper suggestions from positive and negative examples
- **OpenAlex enrichment** -- augment Semantic Scholar metadata with affiliations, funders, OA status, and concepts
- **PDF conversion** -- download open-access PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures

Results are cached in a local SQLite database with per-table TTLs to minimize API calls and speed up repeated lookups.

## Quick start

=== "uvx (recommended)"

    ```bash
    SCHOLAR_MCP_S2_API_KEY=your-key uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
    ```

=== "pip"

    ```bash
    pip install 'pvliesdonk-scholar-mcp[mcp]'
    SCHOLAR_MCP_S2_API_KEY=your-key scholar-mcp serve
    ```

=== "Docker"

    ```bash
    docker run -e SCHOLAR_MCP_S2_API_KEY=your-key \
               -v scholar-mcp-data:/data/scholar-mcp \
               ghcr.io/pvliesdonk/scholar-mcp:latest
    ```

See [Installation](installation.md) for all methods including Linux packages.

## Architecture

```
┌──────────────────────────────────────────────┐
│               MCP Client                     │
│     (Claude Desktop, Claude Code, etc.)      │
└──────────────┬───────────────────────────────┘
               │ stdio / HTTP / SSE
┌──────────────▼───────────────────────────────┐
│           scholar-mcp (FastMCP)              │
│                                              │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Search  │ │ Citation │ │    PDF       │  │
│  │ Tools   │ │ Graph    │ │ Conversion   │  │
│  └────┬────┘ └────┬─────┘ └──────┬───────┘  │
│       │           │              │           │
│  ┌────▼───────────▼──────────────▼────────┐  │
│  │          SQLite Cache (TTL)            │  │
│  └────┬───────────┬──────────────┬────────┘  │
└───────┼───────────┼──────────────┼───────────┘
        │           │              │
   ┌────▼────┐ ┌────▼─────┐ ┌─────▼──────┐
   │Semantic │ │ OpenAlex │ │  docling-  │
   │Scholar  │ │   API    │ │   serve    │
   │  API    │ │          │ │ (optional) │
   └─────────┘ └──────────┘ └────────────┘
```

## Next steps

- [Installation](installation.md) -- all installation methods
- [Configuration](configuration.md) -- environment variable reference
- [Tools](tools/index.md) -- full tool reference with parameters
- [Claude Desktop setup](guides/claude-desktop.md) -- get started with Claude Desktop
- [Docker deployment](deployment/docker.md) -- production Docker Compose setup

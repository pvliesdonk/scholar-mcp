# scholar-mcp

A [FastMCP](https://github.com/jlowin/fastmcp) server providing structured academic literature access via [Semantic Scholar](https://www.semanticscholar.org/), with [OpenAlex](https://openalex.org/) enrichment and optional [docling-serve](https://github.com/DS4SD/docling-serve) PDF conversion.

## Features

### Search & Retrieval
- **`search_papers`** — full-text search with year, field-of-study, venue, and citation-count filters
- **`get_paper`** — fetch full metadata for a single paper by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID
- **`get_author`** — fetch author profile and publications, or search by name

### Citation Graph
- **`get_citations`** — forward citations (papers that cite a given paper)
- **`get_references`** — backward references (papers cited by a given paper)
- **`get_citation_graph`** — BFS traversal returning nodes + edges up to configurable depth
- **`find_bridge_papers`** — shortest citation path between two papers

### Recommendations
- **`recommend_papers`** — paper recommendations from positive (and optional negative) examples

### Utility
- **`batch_resolve`** — resolve up to 100 identifiers to full metadata in one call
- **`enrich_paper`** — augment S2 metadata with OpenAlex fields (open-access URL, topics, concepts)

### PDF Conversion (requires docling-serve)
- **`fetch_paper_pdf`** — download open-access PDF for a paper
- **`convert_pdf_to_markdown`** — convert local PDF to Markdown via docling-serve
- **`fetch_and_convert`** — full pipeline: fetch OA PDF → convert to Markdown

### Cache Management (CLI)
- **`scholar-mcp cache stats`** — show cache row counts and file size
- **`scholar-mcp cache clear [--older-than N]`** — clear cache entries

## Quick Start

### With `uvx`

```bash
# stdio transport (default, for Claude Desktop / MCP clients)
SCHOLAR_MCP_S2_API_KEY=your-key uvx --from pvliesdonk-scholar-mcp scholar-mcp serve

# HTTP transport
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve --transport http --port 8000
```

> **Note:** The PyPI package is `pvliesdonk-scholar-mcp`. The CLI command installed is `scholar-mcp`.

### With Docker

```bash
docker run -e SCHOLAR_MCP_S2_API_KEY=your-key \
           -v scholar-mcp-data:/data/scholar-mcp \
           ghcr.io/pvliesdonk/scholar-mcp:latest
```

## Configuration

All settings are controlled via environment variables with the `SCHOLAR_MCP_` prefix.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | — | Semantic Scholar API key (optional; unauthenticated rate limit applies without it) |
| `SCHOLAR_MCP_READ_ONLY` | `true` | If `true`, write-tagged tools (`fetch_paper_pdf`) are hidden |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Directory for the SQLite cache database |
| `SCHOLAR_MCP_DOCLING_URL` | — | Base URL of a running docling-serve instance (e.g. `http://localhost:5001`) |
| `SCHOLAR_MCP_VLM_API_URL` | — | OpenAI-compatible VLM endpoint for formula/figure-enriched PDF conversion |
| `SCHOLAR_MCP_VLM_API_KEY` | — | API key for the VLM endpoint |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name for VLM-enriched conversion |
| `SCHOLAR_MCP_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SCHOLAR_MCP_BEARER_TOKEN` | — | Bearer token for HTTP transport authentication |
| `SCHOLAR_MCP_OIDC_ISSUER` | — | OIDC issuer URL for JWT authentication |
| `SCHOLAR_MCP_OIDC_AUDIENCE` | — | Expected audience for OIDC tokens |

## Docker Compose

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"
      SCHOLAR_MCP_VLM_API_URL: "${VLM_API_URL}"
      SCHOLAR_MCP_VLM_API_KEY: "${VLM_API_KEY}"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
      SCHOLAR_MCP_READ_ONLY: "false"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.scholar-mcp.rule=Host(`scholar-mcp.yourdomain.com`)"
      - "traefik.http.routers.scholar-mcp.middlewares=authelia@docker"

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped

volumes:
  scholar-mcp-data:
```

## Cache Management

```bash
# Show cache statistics
scholar-mcp cache stats

# Clear all cached data (preserves identifier aliases)
scholar-mcp cache clear

# Remove entries older than 30 days
scholar-mcp cache clear --older-than 30

# Override cache directory
scholar-mcp cache stats --cache-dir /path/to/cache
```

## Development

```bash
# Install with dev dependencies
uv sync --extra dev --extra mcp

# Run tests
uv run pytest

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run mypy src/
```

## License

MIT

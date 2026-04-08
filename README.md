# scholar-mcp

<!-- mcp-name: io.github.pvliesdonk/scholar-mcp -->

[![CI](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/)
[![License](https://img.shields.io/github/license/pvliesdonk/scholar-mcp)](https://github.com/pvliesdonk/scholar-mcp/blob/main/LICENSE)
[![Docker](https://img.shields.io/badge/ghcr.io-scholar--mcp-blue)](https://ghcr.io/pvliesdonk/scholar-mcp)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/scholar-mcp/)
[![llms.txt](https://img.shields.io/badge/llms.txt-available-green)](https://pvliesdonk.github.io/scholar-mcp/llms.txt)

A [FastMCP](https://github.com/jlowin/fastmcp) server providing structured academic literature access via [Semantic Scholar](https://www.semanticscholar.org/), with [OpenAlex](https://openalex.org/) enrichment and optional [docling-serve](https://github.com/DS4SD/docling-serve) PDF conversion.

## Features

- **Search & retrieval** -- full-text paper search with year, venue, field-of-study, and citation-count filters; single-paper lookup by DOI, S2 ID, arXiv ID, and more; author profile and name search
- **Citation graph** -- forward citations, backward references, BFS graph traversal up to configurable depth, and shortest-path bridge paper discovery
- **Recommendations** -- paper recommendations from positive (and optional negative) examples via the S2 recommendation API
- **Citation generation** -- format paper metadata as BibTeX, CSL-JSON, or RIS citations with automatic entry type inference, author name parsing, and OpenAlex venue enrichment
- **Book search** -- search and fetch book metadata via [Open Library](https://openlibrary.org/) (no API key required); papers with an ISBN are automatically enriched with publisher, edition, cover URL, and subject data
- **OpenAlex enrichment** -- augment paper metadata with open-access URLs, affiliations, funders, concepts, and OA status
- **Patent search & cross-referencing** -- search and retrieve patents via [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops) covering 100+ patent offices, with cited reference extraction, NPL-to-paper resolution via Semantic Scholar, and paper-to-patent citation discovery; EPO credentials are optional -- paper search works without them
- **PDF conversion** -- download open-access PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures; automatic fallback to ArXiv, PubMed Central, and Unpaywall when Semantic Scholar has no OA link; direct URL download for PDFs found elsewhere
- **Intelligent caching** -- SQLite-backed cache with per-table TTLs (30 days for papers/authors, 7 days for citations/references) and identifier aliasing
- **Authentication** -- bearer token, OIDC (OAuth 2.1), or both simultaneously (multi-auth)
- **Multi-transport** -- stdio (Claude Desktop), HTTP (streamable-http), and SSE transports
- **Linux packages** -- `.deb` and `.rpm` packages with systemd service and security hardening

## Installation

### With `uvx` (recommended)

```bash
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

### With `pip`

```bash
pip install 'pvliesdonk-scholar-mcp[mcp]'
scholar-mcp serve
```

### With Docker

```bash
docker run -v scholar-mcp-data:/data/scholar-mcp \
           ghcr.io/pvliesdonk/scholar-mcp:latest
```

### Linux packages

Download `.deb` or `.rpm` from the [latest release](https://github.com/pvliesdonk/scholar-mcp/releases/latest):

```bash
# Debian/Ubuntu
sudo dpkg -i scholar-mcp_*.deb

# RHEL/Fedora
sudo rpm -i scholar-mcp-*.rpm
```

> **Note:** The PyPI package is `pvliesdonk-scholar-mcp`. The CLI command installed is `scholar-mcp`.

## Quick Start

### stdio transport (Claude Desktop / MCP clients)

```bash
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

> **API key optional but recommended:** The server works without a Semantic Scholar API key, but unauthenticated requests are limited to ~1 req/s and will hit 429 throttles quickly during multi-step operations like citation graph traversal. [Request a free key](https://www.semanticscholar.org/product/api#api-key-form) to get ~10 req/s.

Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {
        "SCHOLAR_MCP_S2_API_KEY": "your-key"
      }
    }
  }
}
```

### HTTP transport

```bash
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve --transport http --port 8000
```

## Configuration

All settings are controlled via environment variables with the `SCHOLAR_MCP_` prefix.

### Core

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | -- | Semantic Scholar API key ([request one](https://www.semanticscholar.org/product/api#api-key-form)); optional but recommended for higher rate limits |
| `SCHOLAR_MCP_READ_ONLY` | `true` | If `true`, write-tagged tools (`fetch_paper_pdf`, `convert_pdf_to_markdown`, `fetch_and_convert`, `fetch_pdf_by_url`) are hidden |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Directory for the SQLite cache database and downloaded PDFs |
| `SCHOLAR_MCP_CONTACT_EMAIL` | -- | Included in the OpenAlex User-Agent for [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication#the-polite-pool) access (faster rate limits); also enables Unpaywall PDF lookups |
| `SCHOLAR_MCP_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SCHOLAR_MCP_LOG_FORMAT` | `console` | Log output format: `console` (human-readable) or `json` (structured, for log aggregators) |

### PDF Conversion (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_DOCLING_URL` | -- | Base URL of a running [docling-serve](https://github.com/DS4SD/docling-serve) instance (e.g. `http://localhost:5001`) |
| `SCHOLAR_MCP_VLM_API_URL` | -- | OpenAI-compatible VLM endpoint for formula/figure-enriched PDF conversion |
| `SCHOLAR_MCP_VLM_API_KEY` | -- | API key for the VLM endpoint |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name for VLM-enriched conversion |

### Patent Search (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | -- | EPO OPS consumer key ([register at developers.epo.org](https://developers.epo.org/user/register)); both key and secret must be set for patent tools to appear |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | -- | EPO OPS consumer secret |

### Authentication (optional)

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_BEARER_TOKEN` | -- | Static bearer token for HTTP transport authentication |
| `SCHOLAR_MCP_BASE_URL` | -- | Public base URL, required for OIDC (e.g. `https://mcp.example.com`) |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | -- | OIDC discovery endpoint URL |
| `SCHOLAR_MCP_OIDC_CLIENT_ID` | -- | OIDC client ID |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | -- | OIDC client secret |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` | -- | JWT signing key; required on Linux/Docker to survive restarts (`openssl rand -hex 32`) |

## MCP Tools

### Search & Retrieval

| Tool | Description |
|---|---|
| `search_papers` | Full-text search with year, venue, field-of-study, and citation-count filters. Returns up to 100 results with pagination. |
| `get_paper` | Fetch full metadata for a single paper by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID. |
| `get_author` | Fetch author profile with publications, or search by name. |

### Citation Graph

| Tool | Description |
|---|---|
| `get_citations` | Forward citations (papers that cite a given paper) with optional filters. |
| `get_references` | Backward references (papers cited by a given paper). |
| `get_citation_graph` | BFS traversal from seed papers, returning nodes + edges up to configurable depth. |
| `find_bridge_papers` | Shortest citation path between two papers. |

### Recommendations

| Tool | Description |
|---|---|
| `recommend_papers` | Paper recommendations from 1--5 positive examples and optional negative examples. |

### Book Search

| Tool | Description |
|---|---|
| `search_books` | Search for books by title, author, ISBN, or keywords via Open Library. Returns up to 50 results. |
| `get_book` | Fetch book metadata by ISBN-10, ISBN-13, Open Library work ID (`OL...W`), or edition ID (`OL...M`). |
| `recommend_books` | Recommend books for a subject via Open Library, sorted by popularity. |

> Papers with an ISBN in their `externalIds` are automatically enriched with `book_metadata` (publisher, edition, cover URL, subjects, and more) from Open Library when fetched via `get_paper`, `get_citations`, `get_references`, or `get_citation_graph`.

### Utility

| Tool | Description |
|---|---|
| `batch_resolve` | Resolve up to 100 identifiers to full metadata in one call, with OpenAlex fallback. |
| `enrich_paper` | Augment S2 metadata with OpenAlex fields (affiliations, funders, OA status, concepts). |

### Citation Generation

| Tool | Description |
|---|---|
| `generate_citations` | Generate BibTeX, CSL-JSON, or RIS citations for up to 100 papers, with automatic entry type inference and optional OpenAlex venue enrichment. |

### Patent Search (requires EPO OPS credentials)

| Tool | Description |
|---|---|
| `search_patents` | Search patents across 100+ patent offices via EPO OPS. |
| `get_patent` | Fetch bibliographic metadata for a single patent by publication number. |

> Patent tools are hidden when `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET` are not set.

### PDF Conversion (requires docling-serve)

| Tool | Description |
|---|---|
| `fetch_paper_pdf` | Download PDF for a paper (S2 open-access, then ArXiv/PMC/Unpaywall fallback). |
| `convert_pdf_to_markdown` | Convert a local PDF to Markdown via docling-serve. |
| `fetch_and_convert` | Full pipeline: fetch PDF (with fallback), convert to Markdown, return both. |
| `fetch_pdf_by_url` | Download a PDF from any URL and optionally convert to Markdown. |

> PDF tools are write-tagged and hidden when `SCHOLAR_MCP_READ_ONLY=true` (the default).

### Task Polling

| Tool | Description |
|---|---|
| `get_task_result` | Poll for the result of a background task by ID. |
| `list_tasks` | List all active background tasks. |

> Long-running operations (PDF download/conversion) and rate-limited S2 requests return `{"queued": true, "task_id": "..."}` immediately. Use `get_task_result` to poll for the result.

## Docker Compose

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"
      SCHOLAR_MCP_VLM_API_URL: "${VLM_API_URL:-}"
      SCHOLAR_MCP_VLM_API_KEY: "${VLM_API_KEY:-}"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
      SCHOLAR_MCP_READ_ONLY: "false"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.scholar-mcp.rule=Host(`scholar-mcp.yourdomain.com`)"

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped

volumes:
  scholar-mcp-data:
```

## Cache Management

```bash
# Show cache statistics (row counts, database size)
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
# Install with dev and MCP dependencies
uv sync --extra dev --extra mcp

# Run tests
uv run pytest

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run mypy src/

# Build docs locally
uv sync --extra docs
uv run mkdocs serve
```

## License

MIT

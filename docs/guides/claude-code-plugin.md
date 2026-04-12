# Claude Code Plugin

Install Scholar MCP as a Claude Code plugin for automatic tool and skill availability in every session.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed. The plugin launches the server via `uvx`, which ships with `uv`.

## Install

```bash
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

## Configure

The only recommended configuration is a Semantic Scholar API key. The server works without one, but unauthenticated requests are limited to ~1 req/s and will hit 429 throttles during multi-step operations. [Request a free key](https://www.semanticscholar.org/product/api#api-key-form) to get ~10 req/s.

Add to your shell profile:

=== "macOS / Linux"

    ```bash
    echo 'export SCHOLAR_MCP_S2_API_KEY=your-key' >> ~/.zshrc
    ```

=== "Windows PowerShell"

    ```powershell
    [Environment]::SetEnvironmentVariable(
        "SCHOLAR_MCP_S2_API_KEY",
        "your-key",
        "User")
    ```

### Optional environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SCHOLAR_MCP_READ_ONLY` | `true` | Hide write tools (PDF download/conversion). |
| `SCHOLAR_MCP_CONTACT_EMAIL` | -- | OpenAlex polite pool + Unpaywall PDF lookups. |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | SQLite cache and PDF storage. Set a writable local path (e.g. `~/Documents/scholar-mcp`) — the default is for Docker. |
| `SCHOLAR_MCP_DOCLING_URL` | -- | [docling-serve](https://github.com/DS4SD/docling-serve) URL for PDF-to-Markdown. |
| `SCHOLAR_MCP_VLM_API_URL` | -- | OpenAI-compatible VLM endpoint for formula/figure enrichment. |
| `SCHOLAR_MCP_VLM_API_KEY` | -- | API key for the VLM endpoint. |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name for VLM-enriched conversion. |
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | -- | EPO OPS key (enables patent tools). |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | -- | EPO OPS secret. |
| `FASTMCP_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

For the full list, see [Configuration](../configuration.md).

## What you get

27 tools across four scholarly source domains:

- **Papers** -- search, lookup, author search, citations, references, BFS graph traversal, bridge papers, recommendations, BibTeX/CSL-JSON/RIS generation, OpenAlex enrichment.
- **Patents** -- search 100+ offices via EPO OPS, full patent sections, family/legal/citations, NPL-to-paper resolution.
- **Books** -- search, ISBN/OLID lookup, subject recommendations via Open Library.
- **Standards** -- identifier resolution, search, and metadata for NIST, IETF, W3C, ETSI.
- **PDF conversion** -- download and convert to Markdown via docling-serve, with optional VLM enrichment for formulas and figures.

## Update

```bash
/plugin update scholar-mcp@pvliesdonk
```

## Uninstall

```bash
/plugin uninstall scholar-mcp@pvliesdonk
```

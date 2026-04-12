# scholar-mcp (Claude Code plugin)

Scholarly-sources MCP server for **papers**, **patents**, **books**, and
**standards** -- search, cross-reference, and retrieve prior art across
Semantic Scholar, EPO OPS, Open Library, and standards bodies (NIST, IETF,
W3C, ETSI).

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed on your machine. The plugin's
  `.mcp.json` launches the server via `uvx`, which is distributed with `uv`.

## Install

```bash
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

## Configure

Set your Semantic Scholar API key (optional but strongly recommended for
higher rate limits):

```bash
echo 'export SCHOLAR_MCP_S2_API_KEY=your-key' >> ~/.zshrc
```

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | -- | [Free API key](https://www.semanticscholar.org/product/api#api-key-form) for ~10 req/s (vs ~1 without). |
| `SCHOLAR_MCP_READ_ONLY` | `true` | Hide write tools (PDF download/conversion). |
| `SCHOLAR_MCP_CONTACT_EMAIL` | -- | OpenAlex polite pool + Unpaywall access. |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | SQLite cache and PDF storage. Set a writable local path (e.g. `~/Documents/scholar-mcp`) — the default is for Docker. |
| `SCHOLAR_MCP_DOCLING_URL` | -- | docling-serve URL for PDF-to-Markdown. |
| `SCHOLAR_MCP_VLM_API_URL` | -- | OpenAI-compatible VLM endpoint for formula/figure enrichment. |
| `SCHOLAR_MCP_VLM_API_KEY` | -- | API key for the VLM endpoint. |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name for VLM-enriched conversion. |
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | -- | EPO OPS key (enables patent tools). |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | -- | EPO OPS secret. |
| `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` | -- | Google Books API key (higher rate limits). |
| `FASTMCP_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

For the full list of env vars, see the
[Configuration reference](https://pvliesdonk.github.io/scholar-mcp/configuration/).

## What you get

28 tools across four scholarly source domains:

- **Papers** -- search, single-paper lookup, author search, forward/backward
  citations, BFS graph traversal, shortest-path bridge, recommendations,
  BibTeX/CSL-JSON/RIS generation, OpenAlex enrichment.
- **Patents** -- search 100+ offices via EPO OPS, full patent sections,
  family/legal/citations, NPL-to-paper resolution.
- **Books** -- search, ISBN/OLID lookup, subject recommendations via
  Open Library; Google Books excerpts and previews; WorldCat permalinks;
  cover image caching.
- **Standards** -- identifier resolution, search, and metadata for NIST,
  IETF, W3C, ETSI.
- **PDF conversion** -- download and convert to Markdown via docling-serve,
  with optional VLM enrichment for formulas and figures.

## Updating

```bash
/plugin update scholar-mcp@pvliesdonk
```

## Documentation

Full docs: <https://pvliesdonk.github.io/scholar-mcp/>
Issues: <https://github.com/pvliesdonk/scholar-mcp/issues>
License: MIT.

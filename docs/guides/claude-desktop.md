# Claude Desktop Setup

This guide walks you through setting up Scholar MCP with Claude Desktop, from basic search to full PDF conversion.

## Step 1: Basic setup

Add the server to your Claude Desktop configuration (`claude_desktop_config.json`):

=== "macOS"

    ```
    ~/Library/Application Support/Claude/claude_desktop_config.json
    ```

=== "Windows"

    ```
    %APPDATA%\Claude\claude_desktop_config.json
    ```

=== "Linux"

    ```
    ~/.config/Claude/claude_desktop_config.json
    ```

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {}
    }
  }
}
```

Restart Claude Desktop. You should see the Scholar MCP tools in the tool list.

!!! note
    Without an API key, Semantic Scholar limits you to ~1 request per second. This works fine for occasional lookups but may feel slow during multi-step explorations.

## Step 2: Add an API key

[Request a Semantic Scholar API key](https://www.semanticscholar.org/product/api#api-key-form) (free, approval usually takes a few days).

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {
        "SCHOLAR_MCP_S2_API_KEY": "your-key-here"
      }
    }
  }
}
```

This bumps the rate limit to ~10 req/s, making graph traversals and batch operations much faster.

## Step 3: Enable PDF conversion

To download and convert open-access PDFs, you need:

1. A running [docling-serve](https://github.com/DS4SD/docling-serve) instance
2. Write mode enabled (`READ_ONLY=false`)

Start docling-serve:

```bash
docker run -p 5001:5001 ghcr.io/ds4sd/docling-serve:latest
```

Update your config:

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {
        "SCHOLAR_MCP_S2_API_KEY": "your-key-here",
        "SCHOLAR_MCP_DOCLING_URL": "http://localhost:5001",
        "SCHOLAR_MCP_READ_ONLY": "false",
        "SCHOLAR_MCP_CACHE_DIR": "/tmp/scholar-mcp"
      }
    }
  }
}
```

!!! tip "Cache directory"
    When running locally, set `SCHOLAR_MCP_CACHE_DIR` to a writable directory like `/tmp/scholar-mcp` or `~/.local/share/scholar-mcp`. The default (`/data/scholar-mcp`) is designed for Docker.

## Step 4: Add OpenAlex polite pool

Set your contact email to get faster OpenAlex rate limits:

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {
        "SCHOLAR_MCP_S2_API_KEY": "your-key-here",
        "SCHOLAR_MCP_DOCLING_URL": "http://localhost:5001",
        "SCHOLAR_MCP_READ_ONLY": "false",
        "SCHOLAR_MCP_CACHE_DIR": "/tmp/scholar-mcp",
        "SCHOLAR_MCP_CONTACT_EMAIL": "you@example.com"
      }
    }
  }
}
```

## Example prompts

Once configured, try asking Claude:

- *"Search for recent papers on retrieval-augmented generation published after 2023"*
- *"Get the citation graph for this paper: DOI:10.48550/arXiv.2005.11401 with depth 2"*
- *"Find a bridge paper connecting attention mechanisms and graph neural networks"*
- *"Enrich this paper with OpenAlex data: DOI:10.1038/s41586-021-03819-2"*
- *"Download and convert the PDF for arXiv:2005.11401 to Markdown"* (requires Step 3)

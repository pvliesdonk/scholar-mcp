# PDF Conversion

Scholar MCP can download open-access PDFs and convert them to Markdown using [docling-serve](https://github.com/DS4SD/docling-serve). This guide covers setup and usage.

## Requirements

- A running [docling-serve](https://github.com/DS4SD/docling-serve) instance
- `SCHOLAR_MCP_READ_ONLY=false` (PDF tools are write-tagged)

## Setup

### 1. Start docling-serve

The simplest way is Docker:

```bash
docker run -p 5001:5001 ghcr.io/ds4sd/docling-serve:latest
```

### 2. Configure scholar-mcp

Set the docling URL and disable read-only mode:

```bash
export SCHOLAR_MCP_DOCLING_URL=http://localhost:5001
export SCHOLAR_MCP_READ_ONLY=false
```

### 3. Verify

Start the server and check the logs. You should see:

```
INFO scholar_mcp._server_deps: docling_configured url=http://localhost:5001
```

## Tools

Three tools are available once configured:

| Tool | What it does |
|---|---|
| `fetch_paper_pdf` | Downloads the open-access PDF for a paper |
| `convert_pdf_to_markdown` | Converts a local PDF file to Markdown |
| `fetch_and_convert` | Full pipeline: find paper, download PDF, convert to Markdown |

PDFs are stored in `$SCHOLAR_MCP_CACHE_DIR/pdfs/` and Markdown files in `$SCHOLAR_MCP_CACHE_DIR/md/`.

## VLM enrichment

Standard conversion uses OCR only. For papers with complex formulas or figures, you can enable VLM (Vision-Language Model) enrichment:

```bash
export SCHOLAR_MCP_VLM_API_URL=https://api.openai.com/v1
export SCHOLAR_MCP_VLM_API_KEY=sk-...
export SCHOLAR_MCP_VLM_MODEL=gpt-4o
```

When VLM is configured, tools accept a `use_vlm=true` parameter that:

- Extracts LaTeX formulas from images
- Generates text descriptions of figures
- Produces higher-quality Markdown output

!!! note "Cost and speed"
    VLM enrichment makes API calls to the configured endpoint for each page with formulas or figures. This is slower and incurs additional costs compared to standard conversion.

## Docker Compose with docling-serve

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"
      SCHOLAR_MCP_READ_ONLY: "false"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped

volumes:
  scholar-mcp-data:
```

## Limitations

- **Open-access only**: `fetch_paper_pdf` uses the `openAccessPdf.url` field from Semantic Scholar. Papers without an OA URL cannot be downloaded.
- **Conversion quality varies**: OCR quality depends on the PDF source. Scanned papers produce lower-quality results than born-digital PDFs.
- **docling-serve polling**: Conversion is asynchronous. The server polls docling-serve for completion with a timeout of ~10 minutes (200 polls at 3-second intervals).

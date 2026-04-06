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

Four tools are available once configured:

| Tool | What it does |
|---|---|
| `fetch_paper_pdf` | Downloads the PDF for a paper (tries OA, then ArXiv/PMC/Unpaywall) |
| `convert_pdf_to_markdown` | Converts a local PDF file to Markdown |
| `fetch_and_convert` | Full pipeline: find paper, download PDF, convert to Markdown |
| `fetch_pdf_by_url` | Downloads a PDF from any URL and optionally converts to Markdown |

PDFs are stored in `$SCHOLAR_MCP_CACHE_DIR/pdfs/` and Markdown files in `$SCHOLAR_MCP_CACHE_DIR/md/`.

## VLM enrichment

Standard conversion uses OCR only. For papers with complex formulas or figures, you can enable VLM (Vision-Language Model) enrichment:

```bash
export SCHOLAR_MCP_VLM_API_URL=https://api.openai.com/v1
export SCHOLAR_MCP_VLM_API_KEY=sk-...
export SCHOLAR_MCP_VLM_MODEL=gpt-4o
```

When VLM is configured, tools accept a `use_vlm=true` parameter that:

- Extracts LaTeX formulas from formula images
- Generates text descriptions of figures
- Produces higher-quality Markdown for math-heavy and figure-heavy papers

VLM enrichment runs on top of the standard OCR pipeline — it processes each extracted formula and figure image individually via the configured vision model, not full pages.

!!! tip "Start without VLM"
    Standard conversion handles most papers well. Only retry with `use_vlm=true` when the result has garbled formulas or missing figure descriptions.

!!! note "Cost and speed"
    VLM enrichment makes API calls to the configured endpoint for each formula and figure. This is slower and incurs additional costs compared to standard conversion.

### Caching

VLM and standard conversions are cached separately:

- Standard: `$SCHOLAR_MCP_CACHE_DIR/md/<name>.md`
- VLM: `$SCHOLAR_MCP_CACHE_DIR/md/<name>_vlm.md`

Switching between modes never overwrites a previous conversion. When VLM is requested but not configured, the response includes a `vlm_skip_reason` field explaining why (e.g. `"vlm_api_url_not_configured"`).

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

## Async task queue

All PDF tools run in the background and return a task ID immediately:

```json
{"queued": true, "task_id": "a1b2c3d4e5f6", "tool": "fetch_paper_pdf"}
```

Use `get_task_result` with the `task_id` to poll for completion. PDF task results are retained for 1 hour.

The only exception is `convert_pdf_to_markdown` when the markdown output file already exists locally — in that case, the cached result is returned directly.

## Alternative PDF sources

When a paper has no open-access PDF URL in Semantic Scholar, `fetch_paper_pdf` and `fetch_and_convert` automatically try alternative sources:

1. **ArXiv** — If the paper has an `externalIds.ArXiv` field, the PDF is fetched from `arxiv.org/pdf/<id>.pdf`.
2. **PubMed Central** — If the paper has a `PubMedCentral` external ID, the PDF is fetched from NCBI.
3. **Unpaywall** — If the paper has a DOI and `SCHOLAR_MCP_CONTACT_EMAIL` is set, the [Unpaywall API](https://unpaywall.org/products/api) is queried for an OA PDF location.

The `source` field in the response indicates where the PDF came from: `s2_oa`, `arxiv`, `pmc`, or `unpaywall`.

For PDFs found through other means (author homepages, institutional repositories, etc.), use `fetch_pdf_by_url` with the direct URL.

!!! tip "Enable Unpaywall"
    Set `SCHOLAR_MCP_CONTACT_EMAIL` to your email address to enable Unpaywall lookups. This is also used for the OpenAlex polite pool.

## Limitations

- **Paywalled papers**: Alternative resolution only finds openly available versions. Truly paywalled papers require manual download followed by `convert_pdf_to_markdown`, or use `fetch_pdf_by_url` if you find a link.
- **Conversion quality varies**: OCR quality depends on the PDF source. Scanned papers produce lower-quality results than born-digital PDFs.
- **docling-serve polling**: Conversion is asynchronous internally. The server polls docling-serve for completion with a timeout of ~10 minutes (200 polls at 3-second intervals). This happens in the background task, so the MCP client is not blocked.

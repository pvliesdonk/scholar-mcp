---
description: "How to download open-access PDFs and convert them to Markdown with docling-serve, with or without VLM enrichment."
kind: how-to
---

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
INFO scholar_mcp.domain: docling_configured url=http://localhost:5001
```

## Tools

Four tools are available once configured:

| Tool | What it does |
|---|---|
| `fetch_paper_pdf` | Downloads the PDF for a paper (tries OA, then ArXiv/PMC/Unpaywall) |
| `convert_pdf_to_markdown` | Converts a local PDF file to Markdown |
| `fetch_and_convert` | Full pipeline: looks up the paper and downloads and converts its PDF |
| `fetch_pdf_by_url` | Downloads a PDF from a public URL and optionally converts to Markdown |

PDFs are stored in `$SCHOLAR_MCP_CACHE_DIR/pdfs/` and Markdown files in `$SCHOLAR_MCP_CACHE_DIR/md/`.

Downloads are accepted only when the response body begins with the PDF header
`%PDF-`. Other successful HTTP responses return `not_pdf` before conversion;
an existing cached file without that header is fetched again. The check does
not validate the complete PDF structure.

## Reading converted text

Document tools return at most 20,000 Markdown characters by default. A paged
response includes the current `text_offset`, the returned and total character
counts, and `next_offset` when more text remains. Call the same tool again with
`text_offset` set to `next_offset`; the conversion is already cached, so this
does not repeat the expensive work.

Set `max_chars` to a smaller positive integer for shorter pages. Values above
20,000 are capped. Set it to `null` only when the MCP client can accept the
complete converted document in one response.

## VLM enrichment

Standard conversion uses OCR only. For papers with complex formulas or figures, you can enable VLM (Vision-Language Model) enrichment:

```bash
export SCHOLAR_MCP_VLM_API_URL=https://api.openai.com/v1
export SCHOLAR_MCP_VLM_API_KEY=sk-...
export SCHOLAR_MCP_VLM_MODEL=gpt-4o
```

The endpoint must accept OpenAI chat completion requests that cap the output with `max_completion_tokens`, the parameter current OpenAI models require in place of `max_tokens`.

When VLM is configured, tools accept a `use_vlm=true` parameter that:

- Extracts LaTeX formulas from formula images
- Generates text descriptions of figures
- Produces higher-quality Markdown for math-heavy and figure-heavy papers

VLM enrichment runs on top of the standard OCR pipeline, it processes each extracted formula and figure image individually via the configured vision model, not full pages.

!!! tip "Start without VLM"
    Standard conversion handles most papers well. Only retry with `use_vlm=true` when the result has garbled formulas or missing figure descriptions.

!!! note "Cost and speed"
    VLM enrichment makes API calls to the configured endpoint for each formula and figure. This is slower and incurs additional costs compared to standard conversion.

### Caching

VLM and standard conversions are cached separately:

- Standard: `$SCHOLAR_MCP_CACHE_DIR/md/<name>.md`
- VLM: `$SCHOLAR_MCP_CACHE_DIR/md/<name>_vlm.md`

Switching between modes never overwrites a previous conversion. When VLM is requested but not configured, the response includes a `vlm_skip_reason` field explaining why (such as `"vlm_api_url_not_configured"`).

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

## Background jobs

PDF tools answer directly when they can. A download or conversion that takes
longer than `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` (25 seconds by default)
continues in the background, and the call returns a handle right away:

```json
{"status": "working", "job_id": "hwex4wg6taLmasPZWPM7gQ", "poll_with": "get_job_result",
 "retry_after_s": 5.0, "message": "..."}
```

Use `get_job_result` with the `job_id` to poll for completion. Job records are
retained for `SCHOLAR_MCP_JOBS_RESULT_TTL_S`, one hour by default.

A cached result needs no job. An already-downloaded PDF is never fetched
twice, and every tool that converts reuses an existing Markdown file rather
than converting again, so calling one twice for the same paper converts once.
Standard and VLM results are separate files, so switching `use_vlm` still
converts. To force a fresh conversion, delete the cached `.md` file.

## Alternative PDF sources

When a paper has no open-access PDF URL in Semantic Scholar, or that URL fails or serves a landing page instead of a PDF, `fetch_paper_pdf` and `fetch_and_convert` try alternative sources one after another and stop at the first one that serves a PDF:

1. **ArXiv**, If the paper has an `externalIds.ArXiv` field, the PDF is fetched from `arxiv.org/pdf/<id>.pdf`.
2. **PubMed Central**, If the paper has a `PubMedCentral` external ID, the PDF is fetched from NCBI.
3. **Unpaywall**, If the paper has a DOI and `SCHOLAR_MCP_CONTACT_EMAIL` is set, the [Unpaywall API](https://unpaywall.org/products/api) is queried for an OA PDF location.

The `source` field in the response indicates where the PDF came from: `s2_oa`, `arxiv`, `pmc`, or `unpaywall`. When no source serves a PDF, `error` and `pdf_source` describe the last source tried, and `attempts` lists every source in order with its URL, error and detail. Unpaywall is only queried once the sources before it have failed.

For PDFs found through other means (author homepages, institutional repositories, etc.), use `fetch_pdf_by_url` with the direct URL. By default it refuses URLs and redirects that lead to a loopback, private or link-local address. `fetch_paper_pdf` and `fetch_and_convert` apply the same check to the URLs they find in paper metadata, and move on to the next source when one is refused. An operator who needs to fetch from an intranet repository sets `SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE=true`.

!!! tip "Enable Unpaywall"
    Set `SCHOLAR_MCP_CONTACT_EMAIL` to your email address to enable Unpaywall lookups. This is also used for the OpenAlex polite pool.

## Access links for licensed papers

Some papers have no open copy, but your library licenses them. You can configure links into your library's systems, and when `fetch_paper_pdf` or `fetch_and_convert` can't get a PDF (`no_oa_pdf`, `download_failed` or `not_pdf`), the response lists them under `access_links`, in your order. `get_paper` lists them too, ahead of any download attempt. Scholar MCP builds these links but never opens them. Your browser, or an agent on your network, can use them where your library's licence applies.

Without any configuration, the list holds one link, `https://doi.org/<DOI>`, labelled `Publisher (DOI)`. It leads to the publisher's page, which on a network with licence access (many universities and research institutes) often opens the full text directly. Set `SCHOLAR_MCP_ACCESS_LINKS='[]'` to turn links off.

To offer your library's routes, set `SCHOLAR_MCP_ACCESS_LINKS` to a JSON list of `label` and `template` pairs. Your list replaces the default, so include the DOI link yourself if you want it. A template is a URL with placeholders:

| Placeholder | Becomes |
|---|---|
| `{doi}` | The DOI, escaped so it is safe in a URL path or query |
| `{doi_url}` | `https://doi.org/<DOI>`, fully encoded, to wrap inside another link |
| `{openurl}` | An OpenURL 1.0 citation: DOI, PubMed ID, title, journal, year and authors, and the ISSN, volume, issue and pages when known |
| `{openurl_0_1}` | The same citation in the older OpenURL 0.1 form |
| `{openurl_hybrid}` | Both forms in one link |

A template is skipped for a paper it can't be filled for, such as `{doi}` for a paper without a DOI. The OpenURL forms still work without a DOI when the paper has a title, and the journal's ISSN, volume and pages help a resolver find such a paper in your library's holdings.

This configures a library on OCLC WorldCat, with its link resolver first and its inter-library loan form second:

```bash
SCHOLAR_MCP_ACCESS_LINKS='[
  {"label": "Library full text", "template": "https://example.on.worldcat.org/atoztitles/link?{openurl}"},
  {"label": "Library order form", "template": "https://123456.account.worldcat.org/account/route/wsill/openurl?{openurl}"},
  {"label": "Publisher", "template": "https://doi.org/{doi}"}
]'
```

To find your library's resolver address, turn on your library under Google Scholar's **Settings → Library links**, then copy the address of its link on any search result: everything before the `?` is the base. Other templates follow the same pattern: an OpenAthens redirector is `https://go.openathens.net/redirector/<your domain>?url={doi_url}`, and an SFX or Alma resolver takes `?{openurl}` after its base address.

Which OpenURL form to use depends on the resolver. Most accept both. OCLC's resolver looks up the DOI itself when it gets `{openurl}`, which fills in missing details.

## Upload a PDF you downloaded

When an access link works for you but not for the server, download the PDF yourself and hand it to the server through an upload link. The PDF travels over HTTP straight to the server, so it never passes through the conversation.

1. The agent calls `create_upload_link` with the paper's identifier. It gets a one-time `url`.
2. You, or the agent, send the file as the body of a `PUT` to that URL.
3. The agent calls `fetch_and_convert` with the same identifier. The server finds the uploaded PDF in its cache and returns the paged Markdown.

Without an identifier, the link response carries a `pdf_path` instead, and `convert_pdf_to_markdown` converts that file without any paper metadata. When `fetch_and_convert` can't get a PDF, its response names `create_upload_link` under `upload`.

An uploaded PDF joins the shared cache, so later requests for the same paper get it too. If it turns out to be the wrong document, call `create_upload_link` with `replace` set to true. That removes the stored PDF and its converted Markdown at once, before any new upload.

Upload links exist only on an HTTP deployment with `SCHOLAR_MCP_BASE_URL` set. Under stdio, put the file on the server's disk and call `convert_pdf_to_markdown` with its path. [Transfer links](../deploy/transfer-links.md) covers what the operator configures.

## Limitations

- **Paywalled papers**: alternative resolution only finds openly available versions. A paywalled paper needs a manual download, which reaches the server through an [upload link](#upload-a-pdf-you-downloaded) or a file path for `convert_pdf_to_markdown`. [Access links](#access-links-for-licensed-papers) point you to your library's copy, and `fetch_pdf_by_url` takes a direct link you find.
- **Conversion quality varies**: OCR quality depends on the PDF source. Scanned papers produce lower-quality results than born-digital PDFs.
- **docling-serve polling**: Conversion is asynchronous internally. The server polls docling-serve for completion with a timeout of ~10 minutes (200 polls at 3-second intervals). This happens inside the background job, so the MCP client is not blocked.

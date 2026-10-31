<!-- DOMAIN-README-BADGES-START -->
<!-- An optional project logo or header line above the title; kept across copier update. -->
<!-- DOMAIN-README-BADGES-END -->

# Scholar MCP

<!-- mcp-name: io.github.pvliesdonk/scholar-mcp -->

[![CI](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=pvliesdonk_scholar-mcp&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=pvliesdonk_scholar-mcp) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=pvliesdonk_scholar-mcp&metric=coverage)](https://sonarcloud.io/summary/new_code?id=pvliesdonk_scholar-mcp) [![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=pvliesdonk_scholar-mcp&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=pvliesdonk_scholar-mcp) [![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=pvliesdonk_scholar-mcp&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=pvliesdonk_scholar-mcp) [![PyPI](https://img.shields.io/pypi/v/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/) [![Python](https://img.shields.io/pypi/pyversions/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/) [![License](https://img.shields.io/github/license/pvliesdonk/scholar-mcp)](LICENSE) [![Docker](https://img.shields.io/github/v/release/pvliesdonk/scholar-mcp?label=ghcr.io&logo=docker)](https://github.com/pvliesdonk/scholar-mcp/pkgs/container/scholar-mcp) [![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/scholar-mcp/) [![llms.txt](https://img.shields.io/badge/llms.txt-available-brightgreen)](https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt) [![Template](https://img.shields.io/badge/dynamic/yaml?url=https://raw.githubusercontent.com/pvliesdonk/scholar-mcp/main/.copier-answers.yml&query=%24._commit&label=template)](https://github.com/pvliesdonk/fastmcp-server-template)

Scholarly papers, patents, books, standards and PDF conversion

**[Documentation](https://pvliesdonk.github.io/scholar-mcp/)** | **[Config wizard](https://pvliesdonk.github.io/scholar-mcp/latest/reference/configuration-generator/)** | **[PyPI](https://pypi.org/project/pvliesdonk-scholar-mcp/)** | **[Docker](https://github.com/pvliesdonk/scholar-mcp/pkgs/container/scholar-mcp)**

<!-- DOMAIN-README-PITCH-START -->

29 tools, organised by scholarly source type.

### Source domains

- **Papers**: full-text search with year/venue/field/citation filters; single-paper lookup by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID; author profile and name search; forward citations, backward references, BFS graph traversal, shortest-path bridge discovery; recommendations from positive/negative examples; BibTeX/CSL-JSON/RIS citation generation with OpenAlex venue enrichment.
- **Patents**: search across 100+ patent offices via EPO OPS with CPC/applicant/inventor/jurisdiction filters; bibliographic, claims, description, family, legal, and citations sections; NPL-to-paper resolution via Semantic Scholar and paper-to-patent citation discovery. EPO credentials are optional; other domains work without them.
- **Books**: Open Library search by title/author/keywords, no API key required; lookup by ISBN-10/13 or by Open Library work/edition ID; subject-based recommendations sorted by popularity; Google Books excerpts and preview links; WorldCat permalinks for library discovery; cover image caching. Papers with an ISBN in `externalIds` are automatically enriched with publisher, edition, cover URL, and subject data from Open Library.
- **Standards**: identifier resolution, search, and metadata retrieval for NIST, IETF, W3C, and ETSI standards, with optional full-text fetch and Markdown conversion via docling. Tier 2 ISO, IEC, IEEE, Common Criteria (CC), and CEN/CENELEC metadata (including ISO/IEC/IEEE joint standards and the CC ↔ ISO/IEC 15408 cross-link) is synced locally via `sync-standards`. ISO, IEC, IEEE have a live-fetch fallback for unsynced identifiers; CC and CEN have no live API and require a sync first. Citations matching standards patterns (RFC, ISO, NIST SP, IEEE, EN, CC) are automatically enriched with structured `standard_metadata` including identifier, title, body, status, and full-text URL when available (see [docs/guides/standards.md](docs/guides/standards.md)).

### Cross-cutting

- **Enrichment pipeline**: phased enrichment from multiple sources: OpenAlex (OA status, affiliations, funders, concepts), CrossRef (publisher, page ranges, container titles), Google Books (preview links, excerpts), and Open Library (book metadata). Runs automatically on paper and book results.
- **PDF conversion**: download open-access PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures; automatic fallback to ArXiv, PubMed Central, and Unpaywall when Semantic Scholar has no OA link; direct URL download for PDFs found elsewhere; converted text is paged so large documents fit in MCP responses.
- **Intelligent caching**: SQLite-backed cache with per-table TTLs (30 days for papers/authors, 7 days for citations/references) and identifier aliasing.
- **Authentication**: bearer token, OIDC (OAuth 2.1), or both simultaneously (multi-auth).
- **Multi-transport**: stdio (Claude Desktop), HTTP (streamable-http), and SSE transports.
- **Linux packages**: `.deb` and `.rpm` packages with systemd service and security hardening.

### Coverage by domain

Per-domain depth is uneven. Papers currently have the richest tool surface (citation graph, recommendations, cross-referencing to all three other domains); standards are the leanest. That reflects public data availability, not a value hierarchy: writing a paper typically needs all four source types for citations and prior art. Parity work is tracked in [GitHub issues](https://github.com/pvliesdonk/scholar-mcp/issues) and [milestones](https://github.com/pvliesdonk/scholar-mcp/milestones); the roadmap shows intent, not a completeness commitment.
<!-- DOMAIN-README-PITCH-END -->

## Does it fit?

What the server can reach, what it changes and who gets in is set out in the [security model](docs/security-model.md); the block below says who it serves and where it stops.

<!-- DOMAIN-README-FIT-START -->

With this server mounted in an MCP client (Claude, etc.), you can:

- **Survey a field**: "Find the 20 most-cited papers on graph neural networks from 2020 to 2024 and draft a literature review outline." Composes `search_papers` + `get_citations` + `enrich_paper`.
- **Trace a citation path**: "What's the shortest citation path from 'Attention is All You Need' to 'RLHF for dialogue agents'?" Uses `find_bridge_papers` + `get_citation_graph`.
- **Cross-reference prior art**: "For this patent family, list academic papers it cites and any books or standards that show up in the description." Composes `get_patent` + `batch_resolve` + standards/book enrichment.
- **Generate a bibliography**: "Emit BibTeX for these 30 DOIs with OpenAlex venue data." Uses `generate_citations`.
- **Look up a standard**: "What's the latest status of RFC 9000, and fetch the Markdown full text." Uses `resolve_standard_identifier` + `get_standard`.
<!-- DOMAIN-README-FIT-END -->

## Quick start

Pick the client you use. Each line installs the released version; the [Get started](docs/get-started/index.md) tutorials carry on from there.

**Claude Desktop.** Download the `.mcpb` bundle from the [releases page](https://github.com/pvliesdonk/scholar-mcp/releases) and open it with Claude Desktop (or **Settings** › **Extensions** › **Advanced settings** › **Install Extension…**). Claude Desktop asks for the required settings itself. [Tutorial](docs/get-started/claude-desktop.md).

**Claude Code.** Two commands inside Claude Code; the second asks for a scope. [Tutorial](docs/get-started/claude-code.md).

```text
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

**A client that runs a command** (stdio). To register it in Claude Code, see the [Claude Code](docs/get-started/claude-code.md) tutorial.

```bash
uv tool install "pvliesdonk-scholar-mcp"
scholar-mcp serve
```

**A server for remote clients** (streamable HTTP). [A remote server](docs/get-started/http-client.md) connects the clients.

```bash
docker run --rm -p 8000:8000 --env-file .env ghcr.io/pvliesdonk/scholar-mcp:latest
```

A `compose.yml` ships at the repository root and runs as-is: copy `.env.example` to `.env`, then `docker compose up -d`. [Deploy](docs/deploy/index.md) covers authentication, OIDC, a reverse proxy and system packages (`.deb`/`.rpm` on the releases page). The server answers `/health` and `/health/ready` outside the MCP mount, and its `get_server_info` tool reports the running version.

<!-- DOMAIN-README-EXTRAS-START -->

- **`[all]`**: every production feature in one extra; the Linux packages and the Claude Desktop bundle install it.
- **`[debug]`**: adds the remote debugger (`debugpy`); see [Remote debugging](docs/deployment/docker.md#remote-debugging).

The base package already carries FastMCP through `fastmcp-pvl-core`, so `pip install pvliesdonk-scholar-mcp` is enough to run `scholar-mcp serve`. The older `[mcp]` extra is kept so existing install commands keep working; it adds nothing beyond the base package.
<!-- DOMAIN-README-EXTRAS-END -->

## Configuration

Everything is configured through environment variables with the `SCHOLAR_MCP_` prefix. The ones most installs set:

<!-- GENERATED-ENV-TABLE-DOMAIN-START — generated by scripts/gen_config_surface.py; do not edit -->
| Variable | Default | Required | Description |
|---|---|---|---|
| `SCHOLAR_MCP_READ_ONLY` | `true` | No | When true, write-tagged tools (PDF download and conversion cache writes) are hidden. Set false to enable them. |
| `SCHOLAR_MCP_S2_API_KEY` | (none) | No | Semantic Scholar API key. Optional but strongly recommended: a key has an introductory 1 req/s allowance; anonymous users share capacity and may be throttled. Request one at https://www.semanticscholar.org/product/api#api-key-form. |
| `SCHOLAR_MCP_DOCLING_URL` | (none) | No | Base URL of a running docling-serve instance for PDF conversion (such as http://localhost:5001). When unset, PDF conversion tools return an error. |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | No | Directory for the SQLite cache database (cache.db) and downloaded PDFs (pdfs/, md/). |
| `SCHOLAR_MCP_CONTACT_EMAIL` | (none) | No | Contact email for the OpenAlex polite pool (improves rate limits). Also enables Unpaywall lookups as a PDF fallback source. |
<!-- GENERATED-ENV-TABLE-DOMAIN-END -->

Every variable the server reads, the shared ones included, is in the [configuration reference](docs/reference/configuration.md); `.env.example` lists the same surface in copy-paste form, and the [config wizard](https://pvliesdonk.github.io/scholar-mcp/latest/reference/configuration-generator/) writes one for your deployment.

## Documentation

- [Security model](docs/security-model.md): what the server can reach, what it changes and who gets in.
- [Get started](docs/get-started/index.md): a first success with your client.
- [Deploy](docs/deploy/index.md): Docker, authentication, OIDC, reverse proxy.
- [Use](docs/use/index.md): the features, for real tasks.
- [Reference](docs/reference/configuration.md): configuration, [tools](docs/reference/tools/index.md), resources, prompts, command line.
- [Upgrade](docs/upgrade/index.md): release channels, and what an upgrade changes for your clients and your data.
- [Contribute](docs/contribute/index.md): local development, secrets, where a fix belongs; `CONTRIBUTING.md` and `SECURITY.md` at the root.

## Design decisions

<!-- DOMAIN-README-DESIGN-START -->

- **Library-first, MCP-optional.** The core domain logic (S2/EPO/Open Library/standards clients, enrichment pipeline, cache) is importable without FastMCP; the MCP server is a thin async wrapper. Enables reuse in scripts, notebooks, and other servers.
- **Sync domain code, async MCP layer.** Backend clients are synchronous; MCP tools call them via `asyncio.to_thread()`. Simpler client code, explicit offloading at the transport boundary.
- **SQLite cache with per-table TTLs and identifier aliases.** Papers / authors last 30 days, citations / references 7 days. DOI ↔ S2 ID ↔ arXiv ID aliasing survives across cache clears so repeated enrichment hits the same row.
- **Read-only by default.** Write-tagged tools (PDF download/convert, patent PDF) are hidden unless `SCHOLAR_MCP_READ_ONLY=false`. Safer default for first-run.
- **Slow work becomes a background job.** Every tool whose work can run long uses the `fastmcp-pvl-core` jobs layer. A call that beats `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` returns its result directly; a slower one returns a handle to poll with `get_job_result`. S2-backed tools also return a reasoned handle as soon as Semantic Scholar throttles them. The work continues from where it paused, and a cache hit still answers directly.
- **EPO throttling is waited out, not queued.** The traffic light is consulted before every request and cached for a minute, so a retry sooner than that would re-read the cache rather than ask again. Each backoff outlasts the cache; an exhausted daily quota is reported immediately instead, since it will not clear today.
- **Tier 2 standards sync out-of-band.** ISO/IEC/IEEE/CC/CEN catalogues come from community Relaton dumps via `scholar-mcp sync-standards`, not live at runtime, which avoids paywalled-HTML scraping and keeps tool calls fast.
<!-- DOMAIN-README-DESIGN-END -->

## Links

- [Documentation](https://pvliesdonk.github.io/scholar-mcp/) and its [llms.txt](https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt)
- [FastMCP](https://gofastmcp.com) and [fastmcp-pvl-core](https://pypi.org/project/fastmcp-pvl-core/), which this server is built on
- [fastmcp-server-template](https://github.com/pvliesdonk/fastmcp-server-template), which generated this repository

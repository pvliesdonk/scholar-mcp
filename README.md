<<<<<<< before updating
# scholar-mcp
=======
<!-- DOMAIN-START -->
<!-- Add an optional project logo or project-specific header here. Kept across copier update. -->
<!-- DOMAIN-END -->

# Scholar MCP
>>>>>>> after updating

<!-- mcp-name: io.github.pvliesdonk/scholar-mcp -->

[![CI](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/scholar-mcp/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/pvliesdonk/scholar-mcp/graph/badge.svg)](https://codecov.io/gh/pvliesdonk/scholar-mcp) [![PyPI](https://img.shields.io/pypi/v/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/) [![Python](https://img.shields.io/pypi/pyversions/pvliesdonk-scholar-mcp)](https://pypi.org/project/pvliesdonk-scholar-mcp/) [![License](https://img.shields.io/github/license/pvliesdonk/scholar-mcp)](LICENSE) [![Docker](https://img.shields.io/github/v/release/pvliesdonk/scholar-mcp?label=ghcr.io&logo=docker)](https://github.com/pvliesdonk/scholar-mcp/pkgs/container/scholar-mcp) [![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/scholar-mcp/) [![llms.txt](https://img.shields.io/badge/llms.txt-available-brightgreen)](https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt) [![Template](https://img.shields.io/badge/dynamic/yaml?url=https://raw.githubusercontent.com/pvliesdonk/scholar-mcp/main/.copier-answers.yml&query=%24._commit&label=template)](https://github.com/pvliesdonk/fastmcp-server-template)

A [FastMCP](https://github.com/jlowin/fastmcp) server for the scholarly citation landscape (**papers**, **patents**, **books**, and **standards**), giving LLMs a unified way to search, cross-reference, and retrieve prior art across all four source types via [Semantic Scholar](https://www.semanticscholar.org/), [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops), [Open Library](https://openlibrary.org/), and standards bodies (NIST, IETF, W3C, ETSI), with [OpenAlex](https://openalex.org/) enrichment and optional [docling-serve](https://github.com/DS4SD/docling-serve) PDF/full-text conversion.

**[Documentation](https://pvliesdonk.github.io/scholar-mcp/)** | **[Config wizard](https://pvliesdonk.github.io/scholar-mcp/latest/configuration-generator/)** | **[PyPI](https://pypi.org/project/pvliesdonk-scholar-mcp/)** | **[Docker](https://github.com/pvliesdonk/scholar-mcp/pkgs/container/scholar-mcp)**

## Features

<!-- DOMAIN-START -->

### Source domains

- **Papers**: full-text search with year/venue/field/citation filters; single-paper lookup by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID; author profile and name search; forward citations, backward references, BFS graph traversal, shortest-path bridge discovery; recommendations from positive/negative examples; BibTeX/CSL-JSON/RIS citation generation with OpenAlex venue enrichment.
- **Patents**: search across 100+ patent offices via EPO OPS with CPC/applicant/inventor/jurisdiction filters; bibliographic, claims, description, family, legal, and citations sections; NPL-to-paper resolution via Semantic Scholar and paper-to-patent citation discovery. EPO credentials are optional; other domains work without them.
- **Books**: Open Library search by title/author/keywords, no API key required; lookup by ISBN-10/13 or by Open Library work/edition ID; subject-based recommendations sorted by popularity; Google Books excerpts and preview links; WorldCat permalinks for library discovery; cover image caching. Papers with an ISBN in `externalIds` are automatically enriched with publisher, edition, cover URL, and subject data from Open Library.
- **Standards**: identifier resolution, search, and metadata retrieval for NIST, IETF, W3C, and ETSI standards, with optional full-text fetch and Markdown conversion via docling. Tier 2 ISO, IEC, IEEE, Common Criteria (CC), and CEN/CENELEC metadata (including ISO/IEC/IEEE joint standards and the CC ↔ ISO/IEC 15408 cross-link) is synced locally via `sync-standards`. ISO, IEC, IEEE have a live-fetch fallback for unsynced identifiers; CC and CEN have no live API and require a sync first. Citations matching standards patterns (RFC, ISO, NIST SP, IEEE, EN, CC) are automatically enriched with structured `standard_metadata` including identifier, title, body, status, and full-text URL when available (see [docs/guides/standards.md](docs/guides/standards.md)).

### Cross-cutting

- **Enrichment pipeline**: phased enrichment from multiple sources: OpenAlex (OA status, affiliations, funders, concepts), CrossRef (publisher, page ranges, container titles), Google Books (preview links, excerpts), and Open Library (book metadata). Runs automatically on paper and book results.
- **PDF conversion**: download open-access PDFs and convert to Markdown via [docling-serve](https://github.com/DS4SD/docling-serve), with optional VLM enrichment for formulas and figures; automatic fallback to ArXiv, PubMed Central, and Unpaywall when Semantic Scholar has no OA link; direct URL download for PDFs found elsewhere.
- **Intelligent caching**: SQLite-backed cache with per-table TTLs (30 days for papers/authors, 7 days for citations/references) and identifier aliasing.
- **Authentication**: bearer token, OIDC (OAuth 2.1), or both simultaneously (multi-auth).
- **Multi-transport**: stdio (Claude Desktop), HTTP (streamable-http), and SSE transports.
- **Linux packages**: `.deb` and `.rpm` packages with systemd service and security hardening.

### Coverage by domain

Per-domain depth is uneven. Papers currently have the richest tool surface (citation graph, recommendations, cross-referencing to all three other domains); standards are the leanest. That reflects public data availability, not a value hierarchy: writing a paper typically needs all four source types for citations and prior art. Parity work is tracked in [GitHub issues](https://github.com/pvliesdonk/scholar-mcp/issues) and [milestones](https://github.com/pvliesdonk/scholar-mcp/milestones); the roadmap shows intent, not a completeness commitment.
<!-- DOMAIN-END -->

## What you can do with it

<!-- DOMAIN-START -->

With this server mounted in an MCP client (Claude, etc.), you can:

- **Survey a field**: "Find the 20 most-cited papers on graph neural networks from 2020 to 2024 and draft a literature review outline." Composes `search_papers` + `get_citations` + `enrich_paper`.
- **Trace a citation path**: "What's the shortest citation path from 'Attention is All You Need' to 'RLHF for dialogue agents'?" Uses `find_bridge_papers` + `get_citation_graph`.
- **Cross-reference prior art**: "For this patent family, list academic papers it cites and any books or standards that show up in the description." Composes `get_patent` + `batch_resolve` + standards/book enrichment.
- **Generate a bibliography**: "Emit BibTeX for these 30 DOIs with OpenAlex venue data." Uses `generate_citations`.
- **Look up a standard**: "What's the latest status of RFC 9000, and fetch the Markdown full text." Uses `resolve_standard_identifier` + `get_standard`.
<!-- DOMAIN-END -->

<!-- ===== TEMPLATE-OWNED SECTIONS BELOW — DO NOT EDIT; CHANGES WILL BE OVERWRITTEN ON COPIER UPDATE ===== -->

## Installation

### From PyPI

```bash
pip install pvliesdonk-scholar-mcp
```

If you add optional extras via the `PROJECT-EXTRAS-START` / `PROJECT-EXTRAS-END` sentinels in `pyproject.toml`, document them below:

<!-- DOMAIN-START -->

Scholar-mcp ships two optional-dependency groups:

- **`[mcp]`**: installs FastMCP; required to run `scholar-mcp serve` and expose tools over stdio/HTTP.
- **`[all]`**: currently identical to `[mcp]`; reserved for future optional backends.

For MCP-server usage:

```bash
pip install 'pvliesdonk-scholar-mcp[mcp]'
# or, without installing into the environment:
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

Installing the bare `pvliesdonk-scholar-mcp` package is enough for library use (`from scholar_mcp import ...`) but the `scholar-mcp serve` CLI requires `[mcp]`.
<!-- DOMAIN-END -->

### From source

```bash
git clone https://github.com/pvliesdonk/scholar-mcp.git
cd scholar-mcp
uv sync --all-extras --all-groups
```

### Docker

```bash
docker pull ghcr.io/pvliesdonk/scholar-mcp:latest
```

To run the newest merged code instead of the newest release, use the rolling `edge` tag. It is rebuilt on every merge to `main` and carries no version identity. See [Image tags](docs/deployment/docker.md#image-tags) for the full tag list.

```bash
docker pull ghcr.io/pvliesdonk/scholar-mcp:edge
```

A `compose.yml` ships at the repo root as a starting point. Copy `.env.example` to `.env`, edit, and `docker compose up -d`.

To attach a remote Python debugger (development only; the protocol is unauthenticated), see [Remote debugging](docs/deployment/docker.md#remote-debugging).

### Linux packages (.deb / .rpm)

Download `.deb` or `.rpm` packages from the [GitHub Releases](https://github.com/pvliesdonk/scholar-mcp/releases) page. Both install a hardened systemd unit; env configuration is sourced from `/etc/scholar-mcp/env` (copy from the shipped `/etc/scholar-mcp/env.example`).

### Claude Desktop (.mcpb bundle)

Download the `.mcpb` bundle from the [GitHub Releases](https://github.com/pvliesdonk/scholar-mcp/releases) page and double-click to install, or run:

```bash
mcpb install scholar-mcp-<version>.mcpb
```

Claude Desktop prompts for required env vars via a GUI wizard, with no manual JSON editing needed.

For manual Claude Desktop configuration and setup options, see [Claude Desktop deployment](docs/deployment/claude-desktop.md).

## Release channels

Artifacts ship on three channels. Each row lists exactly what that channel publishes.

| Channel | Version identity | Artifacts |
|---|---|---|
| `edge` (rolling) | None; the commit is the identity | Docker image `:edge` rebuilt on every merge to `main`; `.mcpb` bundle as the `mcpb-bundle-edge` workflow artifact; Claude Code plugin `.zip` as the `plugin-zip-edge` artifact; rolling `unstable` docs version. It leaves no git tag, GitHub release, or PyPI entry behind. |
| Pre-release | `vX.Y.Z-rc.N`, computed and reviewed in its release pull request | PyPI (as the pre-release `X.Y.ZrcN`); GitHub release with wheels, `sdist`, `.deb`/`.rpm` packages, `.mcpb` bundle, plugin `.zip`, and SBOM attached; Docker image under its immutable `vX.Y.Z-rc.N` tag plus the ordering-aware rolling `rc` tag. Skips the plugin marketplace, the MCP registry, and the docs deploy. |
| Stable | `vX.Y.Z` | Everything: PyPI, Docker (version tag plus ordering-aware `latest` / `vX` / `vX.Y`), `.deb`/`.rpm`, GitHub release assets (wheels, `sdist`, `.mcpb` bundle, plugin `.zip`, SBOM), plugin marketplace and MCP registry entries (when the release is the newest stable), versioned docs with an ordering-aware `latest` alias. |

Pre-releases reach PyPI so that a candidate's `.mcpb` bundle installs: the bundle points at PyPI rather than carrying the code. Ordinary installers never see them, because a PEP 440 resolver skips pre-releases unless the requirement pins one or you pass `--pre`. Ask for a candidate by name with `pip install pvliesdonk-scholar-mcp==X.Y.ZrcN`. PyPI spells it in the PEP 440 canonical form, while tags use SemVer. Rolling pointers are ordering-aware, so a patch release cut from an old `release/X.Y` branch never moves `latest`-style tags back to older content, and a candidate for an already-released version never moves `rc`. See [Release process](docs/deployment/release-process.md) for the full model.

## Quick start

```bash
scholar-mcp serve                                # stdio transport
scholar-mcp serve --transport http --port 8000   # streamable HTTP
```

For library usage (embedding the domain logic without the MCP transport), import from the `scholar_mcp` package directly. Backend clients live under `src/scholar_mcp/_s2_client.py`, `_epo_client.py`, `_openlibrary_client.py`, and `_standards_client.py`.

### Server info

The server registers a built-in `get_server_info` tool (via `fastmcp_pvl_core.register_server_info_tool`) so operators can confirm the deployed version with a single MCP call. The default response carries `server_name`, `server_version`, and `core_version`. Servers that talk to a remote upstream wire upstream version reporting inside the `DOMAIN-UPSTREAM-START` / `DOMAIN-UPSTREAM-END` sentinel in `src/scholar_mcp/server.py`; see [`tool-registration`](.agents/skills/tool-registration/SKILL.md#server-info-tool-get_server_info) for the wiring pattern.

## Configuration

The most common environment variables, shared across all
`fastmcp-pvl-core`-based services:

<!-- GENERATED-ENV-TABLE-CORE-START — generated by scripts/gen_config_surface.py; do not edit -->
| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_KV_STORE_URL` | `file:///data/state` | Persistent-state backend URL shared by every pvl-core subsystem that needs state. `memory://` is in-process and lost on restart; `file:///path` persists on one server; `redis://`, `dynamodb://` and `mongodb://` each need their matching extra. When unset, defaults to `file:///data/state` (the volume family Docker images mount), or to `memory://` (with a warning) on a host where that directory is not usable. |
| `FASTMCP_LOG_LEVEL` | `INFO` | Log level for FastMCP internals and app loggers (DEBUG / INFO / WARNING / ERROR / CRITICAL). The -v CLI flag overrides to DEBUG. |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set false for plain or structured JSON log output. |
<!-- GENERATED-ENV-TABLE-CORE-END -->

This table and the one under [Domain configuration](#domain-configuration)
are curated subsets. The complete generated reference, with every variable
the server reads, is the [configuration reference](docs/configuration.md);
`.env.example` lists the same surface in copy-paste form.

## Authorization (opt-in)

This server inherits opt-in per-subject authorization from `fastmcp-pvl-core`. The default posture is **off**: every authenticated caller can use every tool, resource, and prompt. Turn it on by pointing `SCHOLAR_MCP_ACL_PATH` at a TOML ACL file; the middleware is installed only when the path is set, and individual tools opt in by declaring `meta={"required_scope": "<scope>"}` at registration. A tool without `required_scope` is unrestricted regardless of caller.

Wire it in by uncommenting the `acl_path` field in `src/scholar_mcp/config.py` and the `AuthorizationMiddleware` stanza in `src/scholar_mcp/server.py`; both ship as commented stubs in the scaffold.

### ACL TOML schema

```toml
[subjects]
"user:alice@example.com" = ["read", "write"]
"user:admin@example.com" = ["*"]              # wildcard — any required scope passes
"service:ci-bot"         = ["read"]
"local"                  = ["*"]              # auth-disabled subject (no bearer / OIDC vars set)
```

- **Subject strings are opaque.** The `<kind>:<id>` convention is documentation only; the library treats each subject as a literal string.
- **`*` is the only library-treated special scope**: it grants every required scope. Subject-side wildcards (`*` as an ACL key) are rejected at load time.
- **Scope vocabulary is domain-defined.** Per-project or per-folder gating is encoded into the scope string itself, such as `read:project-foo` or `write:vault/personal`; `fastmcp-pvl-core` treats every scope except `*` as opaque.

### Subject ↔ bearer-token alignment

The subject string used as a *value* in the bearer-tokens TOML (`SCHOLAR_MCP_BEARER_TOKENS_FILE`) is the same string used as a *key* in the ACL TOML. Same string, opposite roles, so keep the two files consistent when adding or removing a principal. See [Mapped bearer tokens](docs/guides/authentication.md#mapped-bearer-tokens-multi-subject) in the authentication guide for the bearer-tokens TOML schema.

In single-token mode (`SCHOLAR_MCP_BEARER_TOKEN`) every authenticated caller shares one subject, the library's default (currently `"bearer-anon"`); override it with `SCHOLAR_MCP_BEARER_DEFAULT_SUBJECT`; reference *that* string as the ACL key. When no auth is configured (no `SCHOLAR_MCP_BEARER_TOKEN`, `SCHOLAR_MCP_BEARER_TOKENS_FILE`, or OIDC env vars set, which is common in stdio dev rigs but also possible on HTTP), every request resolves to the literal subject `"local"`. Reference that string as the ACL key for un-authenticated local sessions.

## Authentication

Callers authenticate via a bearer token or OIDC (mutually exclusive). See the [Authentication guide](docs/guides/authentication.md) for setup, mapped multi-subject tokens, OIDC, and troubleshooting.

## Post-scaffold checklist

After `copier copy` and `gh repo create --push`:

1. **Fill in the DOMAIN blocks** (every section marked with a `DOMAIN` sentinel comment) in this README and in `AGENTS.md`. The `GENERATED-ENV-TABLE-*` regions are not DOMAIN blocks; the config generator owns them and rewrites them on every run.
2. Configure GitHub secrets (see below).
3. Install dev + docs tooling: `uv sync --all-extras --all-groups`.
4. Install pre-commit hooks: `uv run pre-commit install`.
5. Run the gate locally: `uv run pytest -x -q && uv run ruff check --fix . && uv run ruff format . && uv run mypy src/ tests/`.
6. Push the first commit. CI should be green.

## GitHub secrets

CI workflows reference two required repository secrets and one optional Claude token. Configure them via **Settings → Secrets and variables → Actions** or with `gh secret set`:

| Secret | Used by | How to generate |
|---|---|---|
| `RELEASE_TOKEN` | `release-prepare.yml`, `release.yml`, `copier-update.yml`, `renovate.yml`, `bootstrap.yml` | Fine-grained PAT at <https://github.com/settings/personal-access-tokens/new> with `contents: write`, `pull_requests: write`, and `administration: write` (bootstrap applies the repository rulesets + auto-merge). Must belong to a repository admin: the shipped rulesets grant bypass to the admin role, and the release tag + GitHub release that knope creates after a release pull request merges rely on it (pull requests the token opens also need it so their CI runs). Scoped to this repo. |
| `CODECOV_TOKEN` | `ci.yml` | <https://codecov.io>: sign in with GitHub and add the repo. The upload token is on its settings page. |
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude.yml` | Optional. Run `claude setup-token` locally and configure this only for `@claude` or opted-in automatic review. |

```bash
gh secret set RELEASE_TOKEN
gh secret set CODECOV_TOKEN
# Optional: enables @claude and opted-in automatic review.
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

> Dependency updates are handled by **Renovate** (`renovate.yml`), which reuses
> `RELEASE_TOKEN`. It maintains `uv.lock` and auto-merges patch/minor bumps once
> the `CI Success` check is green; `bootstrap.yml` enables auto-merge and applies
> the repository rulesets (`.github/rulesets/`) on first push. See
> [Repository Protection](docs/deployment/repository-protection.md) for the
> per-branch posture and bypass model. GitHub Actions are updated in the copier
> template and arrive via `copier update`, not per-repo.

`GITHUB_TOKEN` is auto-provided; no action needed.

## Local development

The PR gate (matches CI):

```bash
uv run pytest -x -q                                  # tests
uv run ruff check --fix . && uv run ruff format .    # lint + format
uv run mypy src/ tests/                              # type-check
```

Pre-commit runs a subset of the gate on each commit; see `.pre-commit-config.yaml` for details, or [`AGENTS.md`](AGENTS.md) for the full Hard PR Acceptance Gates.

## Troubleshooting

### Moving a scaffolded project

`uv sync` creates `.venv/bin/*` scripts with absolute shebangs pointing at the venv Python. If you move the repo after scaffolding (`mv /old/path /new/path`), `uv run pytest` fails with `ModuleNotFoundError: No module named 'fastmcp'` because the stale shebang resolves to a different interpreter than the venv's site-packages.

**Fix:**

```bash
rm -rf .venv
uv sync --all-extras --all-groups
```

`uv run python -m pytest` also works as a one-shot workaround (bypasses the stale entry-script shim).

### `uv.lock` refresh after `copier update`

When `copier update` introduces new dependencies (such as a new extra added to `pyproject.toml.jinja`), the CI install step runs `uv sync --locked`, which fails against a stale lockfile. Run `uv lock` locally and commit the refreshed `uv.lock` alongside accepting the copier-update PR.

CI installs with `--locked` (and the review workflow with `--frozen`) so no job ever rewrites `uv.lock` in its own workspace: a job that re-locks hides the drift it just repaired, and a dirty workspace breaks any later `git checkout` in the same job. Lockfile drift then shows up as a red install step with a clear message, not as a silent mutation.

## Contributing

`CONTRIBUTING.md` holds the rules for issues and pull requests, and where a
fix belongs: `fastmcp-pvl-core` for library code, the template for
template-owned files, this repository for anything inside its `DOMAIN-*` /
`CONFIG-*` / `PROJECT-*` blocks. `AGENTS.md` carries the conventions and
gates; the skills under `.agents/skills/` carry the task procedures, among
them `code-review` (local self-review before a pull request),
`writing-release-notes` (release notes),
`applying-template-updates` (the weekly template update pull request) and
`authoring-issues-prs` (filing). The release procedure is in
[docs/deployment/release-process.md](docs/deployment/release-process.md);
the template update procedure in
[docs/deployment/template-updates.md](docs/deployment/template-updates.md).

## Links

- [Documentation](https://pvliesdonk.github.io/scholar-mcp/)
- [llms.txt](https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt)
- [FastMCP](https://gofastmcp.com)
- [fastmcp-pvl-core](https://pypi.org/project/fastmcp-pvl-core/)

<!-- ===== TEMPLATE-OWNED SECTIONS END ===== -->

## Domain configuration

The variables this project features as its entry points (domain variables use the `SCHOLAR_MCP_` prefix):

<!-- GENERATED-ENV-TABLE-DOMAIN-START — generated by scripts/gen_config_surface.py; do not edit -->
_No variables are featured here yet. Add `readme` to a config field's `tags` metadata to feature it; the [configuration reference](docs/configuration.md) lists every variable._
<!-- GENERATED-ENV-TABLE-DOMAIN-END -->

This is a curated subset: a field appears here when its `tags` metadata includes `readme`. Every domain variable is documented in the [configuration reference](docs/configuration.md), grouped the same way the config wizard presents them.

Domain-config fields are composed inside `src/scholar_mcp/config.py` between the `CONFIG-FIELDS-START` / `CONFIG-FIELDS-END` sentinels; env reads go through `fastmcp_pvl_core.env(_ENV_PREFIX, "SUFFIX", default)` so naming stays consistent, and field invariants go in `__post_init__` between the `CONFIG-VALIDATE-START` / `CONFIG-VALIDATE-END` sentinels. Each field's `metadata` `help`, `tags`, and `wizard` group generate the reference tables directly, so keep them accurate and complete.

Scholar-mcp pings Semantic Scholar once on startup and every 7 days
thereafter to keep the configured key from being removed for inactivity
(Semantic Scholar may remove keys unused for 60+ days). If S2 starts
rejecting the key with `403 Forbidden`, this shows up in the server logs
as `s2_key_forbidden` (on real tool calls) or `s2_keepalive_key_forbidden`
(from the background keepalive); grep for either to confirm a dead key
versus a transient upstream issue.

## Key design decisions

<!-- DOMAIN-START -->

- **Library-first, MCP-optional.** The core domain logic (S2/EPO/Open Library/standards clients, enrichment pipeline, cache) is importable without FastMCP; the MCP server is a thin async wrapper. Enables reuse in scripts, notebooks, and other servers.
- **Sync domain code, async MCP layer.** Backend clients are synchronous; MCP tools call them via `asyncio.to_thread()`. Simpler client code, explicit offloading at the transport boundary.
- **SQLite cache with per-table TTLs and identifier aliases.** Papers / authors last 30 days, citations / references 7 days. DOI ↔ S2 ID ↔ arXiv ID aliasing survives across cache clears so repeated enrichment hits the same row.
- **Read-only by default.** Write-tagged tools (PDF download/convert, patent PDF) are hidden unless `SCHOLAR_MCP_READ_ONLY=false`. Safer default for first-run.
- **Slow work becomes a background job.** Every tool whose work can run long runs through the `fastmcp-pvl-core` jobs layer, whether the slow part is a docling conversion, an EPO throttle being waited out, or a graph walk making one request per node. A call that beats `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` returns its result directly; a slower one returns a handle to poll with `get_job_result`. No tool decides in advance whether to go background, so a cache hit needs no special case.
- **EPO throttling is waited out, not queued.** The traffic light is consulted before every request and cached for a minute, so a retry sooner than that would re-read the cache rather than ask again. Each backoff outlasts the cache; an exhausted daily quota is reported immediately instead, since it will not clear today.
- **Tier 2 standards sync out-of-band.** ISO/IEC/IEEE/CC/CEN catalogues come from community Relaton dumps via `scholar-mcp sync-standards`, not live at runtime, which avoids paywalled-HTML scraping and keeps tool calls fast.
<!-- DOMAIN-END -->

## Quick Start details

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

### Claude Code plugin

```bash
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

### Syncing Tier 2 standards catalogues

Tier 2 bodies (ISO, IEC, IEEE, CC, CEN) are populated from community-curated bulk dumps rather than live-scraped at MCP-server runtime. Run the sync on first install and periodically thereafter:

```bash
scholar-mcp sync-standards            # all registered bodies
scholar-mcp sync-standards --body ISO # only ISO
scholar-mcp sync-standards --body IEEE # only IEEE
scholar-mcp sync-standards --body CC   # only Common Criteria
scholar-mcp sync-standards --body CEN # only CEN/CENELEC
scholar-mcp sync-standards --force    # re-sync even if upstream SHA is unchanged
```

Schedule via cron, launchd, or a systemd timer. Weekly is sufficient; standards change slowly. First sync can take several minutes; subsequent runs that find no upstream changes exit within seconds.

## MCP Tools

29 tools, organised by scholarly source type.

### Papers

#### Search & retrieval

| Tool | Description |
|---|---|
| `search_papers` | Full-text search with year, venue, field-of-study, and citation-count filters. Returns up to 100 results with pagination. |
| `get_paper` | Fetch full metadata for a single paper by DOI, S2 ID, arXiv ID, ACM ID, or PubMed ID. |
| `get_author` | Fetch author profile with publications, or search by name. |

#### Citation graph

| Tool | Description |
|---|---|
| `get_citations` | Forward citations (papers that cite a given paper) with optional filters. |
| `get_references` | Backward references (papers cited by a given paper). |
| `get_citation_graph` | BFS traversal from seed papers, returning nodes + edges up to configurable depth. |
| `find_bridge_papers` | Shortest citation path between two papers. |

#### Recommendations & citation generation

| Tool | Description |
|---|---|
| `recommend_papers` | Paper recommendations from 1 to 5 positive examples and optional negative examples. |
| `generate_citations` | Generate BibTeX, CSL-JSON, or RIS citations for up to 100 papers, with automatic entry type inference and optional OpenAlex venue enrichment. |
| `enrich_paper` | Augment Semantic Scholar metadata with OpenAlex fields (affiliations, funders, OA status, concepts). |

### Patents

| Tool | Description |
|---|---|
| `search_patents` | Search patents across 100+ patent offices via EPO OPS with CPC / applicant / inventor / jurisdiction / date filters. |
| `get_patent` | Fetch bibliographic / claims / description / family / legal / citations sections for a single patent by publication number. Citations include NPL-to-paper resolution via Semantic Scholar. |
| `get_citing_patents` | Find patents that cite a given academic paper (best-effort; EPO OPS citation search coverage is incomplete). |
| `fetch_patent_pdf` | Download a patent PDF via authenticated EPO OPS and optionally convert to Markdown. |

> Patent tools are hidden when `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET` are not set. `fetch_patent_pdf` is also write-tagged and hidden when `SCHOLAR_MCP_READ_ONLY=true`.

### Books

| Tool | Description |
|---|---|
| `search_books` | Search for books by title, author, ISBN, or keywords via Open Library. Returns up to 50 results. |
| `get_book` | Fetch book metadata by ISBN-10, ISBN-13, Open Library work ID, or edition ID. Optionally download and cache the cover image locally. |
| `get_book_excerpt` | Fetch a book excerpt and description from Google Books by ISBN. Shows preview availability and link. |
| `recommend_books` | Recommend books for a subject via Open Library, sorted by popularity. |

> Papers with an ISBN in their `externalIds` are automatically enriched with `book_metadata` (publisher, edition, cover URL, subjects, and more) from Open Library when fetched via `get_paper`, `get_citations`, `get_references`, or `get_citation_graph`. Book records also include `worldcat_url` (when ISBN-13 is present), `google_books_url`, and `snippet` from Google Books enrichment. Cover images can be downloaded and cached locally via `get_book`.

### Standards

| Tool | Description |
|---|---|
| `resolve_standard_identifier` | Normalise a messy citation string such as `"rfc9000"` or `"nist 800-53"` to canonical form and body. |
| `search_standards` | Search standards by identifier, title, or free text, optionally filtered to one body (`NIST`, `IETF`, `W3C`, `ETSI`). |
| `get_standard` | Retrieve a standard by canonical or fuzzy identifier, optionally fetching and converting the full text via docling. |

> Tier-1 bodies (NIST, IETF, W3C, ETSI) are supported with full metadata and optional full-text conversion. Tier-2 bodies (ISO, IEC, IEEE, CC, CEN/CENELEC) are populated locally via `scholar-mcp sync-standards`.

### Cross-source Utility

| Tool | Description |
|---|---|
| `batch_resolve` | Resolve up to 100 mixed identifiers (paper DOIs, patent numbers, ISBNs) to full metadata in one call, routing each to the right backend with OpenAlex fallback. |

### PDF Conversion (requires docling-serve)

| Tool | Description |
|---|---|
| `fetch_paper_pdf` | Download PDF for a paper (S2 open-access, then ArXiv/PMC/Unpaywall fallback). |
| `convert_pdf_to_markdown` | Convert a local PDF to Markdown via docling-serve. |
| `fetch_and_convert` | Full pipeline: fetches the PDF with fallback sources, then converts it to Markdown and returns both. |
| `fetch_pdf_by_url` | Download a PDF from any URL and optionally convert to Markdown. |

> PDF tools are write-tagged and hidden when `SCHOLAR_MCP_READ_ONLY=true` (the default). `fetch_patent_pdf` (above) and the `get_standard` full-text mode cover the patent and standards equivalents.

### Job Polling

| Tool | Description |
|---|---|
| `get_job_result` | Retrieve the outcome of a background job by ID. |

> Tools answer directly when the work is quick, including on a cache hit. A slower call returns `{"status": "working", "job_id": "...", "poll_with": "get_job_result"}`; poll with the tool the handle names until the status is terminal.

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

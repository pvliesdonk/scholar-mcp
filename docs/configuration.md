# Configuration

All settings are controlled via environment variables with the `SCHOLAR_MCP_` prefix. No configuration file is needed.

## Core

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | _(none)_ | [Semantic Scholar API key](https://www.semanticscholar.org/product/api#api-key-form). Optional, but strongly recommended: unauthenticated requests are limited to ~1 req/s while authenticated requests get ~10 req/s. |
| `SCHOLAR_MCP_READ_ONLY` | `true` | When `true`, all write-tagged tools are hidden. Set to `false` to enable PDF download and conversion. |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Directory for the SQLite cache database (`cache.db`) and downloaded PDFs (`pdfs/`, `md/`). |
| `SCHOLAR_MCP_CONTACT_EMAIL` | _(none)_ | Included in the OpenAlex `User-Agent` header for [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication#the-polite-pool) access. Also enables [Unpaywall](https://unpaywall.org/products/api) lookups as a PDF fallback source when a paper has no open-access URL in Semantic Scholar. |
| `FASTMCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. Controls all output (application and middleware). The `-v` CLI flag sets this to `DEBUG`. |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set to `false` for plain/JSON-structured output suitable for log aggregation tools (Loki, Datadog, Splunk). When `true`, output uses Rich formatting (colors, timestamps). |

## PDF Conversion

These settings are only needed if you want to use the PDF conversion tools. They require a running [docling-serve](https://github.com/DS4SD/docling-serve) instance.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_DOCLING_URL` | _(none)_ | Base URL of a running docling-serve instance (such as `http://localhost:5001`). When unset, the PDF conversion tools are still registered but will return an error. |
| `SCHOLAR_MCP_VLM_API_URL` | _(none)_ | OpenAI-compatible VLM endpoint for formula and figure enrichment during PDF conversion. |
| `SCHOLAR_MCP_VLM_API_KEY` | _(none)_ | API key for the VLM endpoint. |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name to use with the VLM endpoint. |

!!! tip "VLM enrichment"
    When both `SCHOLAR_MCP_VLM_API_URL` and `SCHOLAR_MCP_VLM_API_KEY` are set, tools can request VLM-enriched conversion that extracts LaTeX formulas and generates figure descriptions. This produces higher-quality Markdown but is slower and costs API calls.

## EPO Open Patent Services

These settings enable patent search via the [EPO Open Patent Services (OPS)](https://www.epo.org/en/searching-for-patents/data/web-services/ops) API. Both variables must be set for patent tools to be enabled; if either is missing, the `search_patents` and `get_patent` tools are automatically hidden.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | _(none)_ | EPO OPS consumer key. Optional; patent tools are hidden when unset. |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | _(none)_ | EPO OPS consumer secret. Optional; patent tools are hidden when unset. |

!!! info "Graceful degradation"
    When credentials are not configured, patent tools are silently omitted from the tool list. Paper search and all other tools continue to work normally without EPO credentials.

### Registering for EPO OPS access

EPO OPS provides free access to bibliographic data for 100+ patent offices. Follow these steps to obtain credentials:

1. Register at [https://developers.epo.org/user/register](https://developers.epo.org/user/register). Fill in your name, email, and organisation.
2. Wait for an email confirmation and click the verification link.
3. Log in to the [EPO developer portal](https://developers.epo.org/).
4. Navigate to **My Apps** in the top menu.
5. Click **Add a new App** and choose a name (such as `scholar-mcp`).
6. Select **Non-paying** as the access method (provides free access with standard rate limits).
7. Copy the generated **Consumer Key** and **Consumer Secret** to your environment:

```bash
export SCHOLAR_MCP_EPO_CONSUMER_KEY="your-consumer-key"
export SCHOLAR_MCP_EPO_CONSUMER_SECRET="your-consumer-secret"
```

Or in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scholar": {
      "command": "uvx",
      "args": ["--from", "pvliesdonk-scholar-mcp", "scholar-mcp", "serve"],
      "env": {
        "SCHOLAR_MCP_S2_API_KEY": "your-s2-key",
        "SCHOLAR_MCP_EPO_CONSUMER_KEY": "your-consumer-key",
        "SCHOLAR_MCP_EPO_CONSUMER_SECRET": "your-consumer-secret"
      }
    }
  }
}
```

## Google Books

Google Books integration is available without configuration (unauthenticated, 1000 requests/day). An API key unlocks higher rate limits.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` | _(none)_ | [Google Books API key](https://developers.google.com/books/docs/v1/using#APIKey). Optional, the enricher and `get_book_excerpt` tool work without it at reduced rate limits. |

## Server

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_SERVER_NAME` | `scholar-mcp` | MCP server display name shown to clients. |
| `SCHOLAR_MCP_INSTRUCTIONS` | *(auto-generated)* | Custom system-level instructions for LLM clients. When unset, auto-generated instructions describe available tools and the current read-only/write mode. |
| `SCHOLAR_MCP_HTTP_PATH` | `/mcp` | Mount path for HTTP transport. |

## Authentication

Authentication is optional. When no auth variables are set, the server accepts unauthenticated connections.

!!! warning
    Authentication only applies to the HTTP transport. stdio connections (such as Claude Desktop) are always unauthenticated since the client spawns the server process directly.

### Auth modes

The server supports two OIDC modes, auto-detected from environment variables:


| Mode | When selected | How it works |
|---|---|---|
| **remote** | `BASE_URL` + `OIDC_CONFIG_URL` set (no client credentials) | The external auth provider (such as Authelia behind a reverse proxy) handles the full OAuth flow; the server validates the resulting JWTs locally via JWKS. |
| **oidc-proxy** | All four OIDC vars set (`BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) | The MCP server acts as an OAuth proxy, handling the OIDC authorization flow itself. |

Auto-detection prefers `oidc-proxy` when all four vars are present. Override with `SCHOLAR_MCP_AUTH_MODE=remote` or `SCHOLAR_MCP_AUTH_MODE=oidc-proxy`.

When both bearer and OIDC auth are configured, the server uses multi-auth, either mechanism is accepted.

### Variables

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_BEARER_TOKEN` | _(none)_ | Static bearer token. When set, HTTP clients must send `Authorization: Bearer <token>`. Every authenticated caller shares one subject (see `SCHOLAR_MCP_BEARER_DEFAULT_SUBJECT`). |
| `SCHOLAR_MCP_BEARER_TOKENS_FILE` | _(none)_ | Path to a TOML file mapping bearer tokens to per-caller subjects. When set, takes precedence over `SCHOLAR_MCP_BEARER_TOKEN`. See [Mapped bearer tokens](guides/authentication.md#mapped-bearer-tokens-multi-subject) in the authentication guide. |
| `SCHOLAR_MCP_BEARER_DEFAULT_SUBJECT` | `bearer-anon` | Single-token-mode subject string. Used as the ACL key when wiring opt-in authorization. |
| `SCHOLAR_MCP_AUTH_MODE` | *(auto)* | Force auth mode: `remote` or `oidc-proxy`. When unset, auto-detected from which OIDC env vars are present. |
| `SCHOLAR_MCP_BASE_URL` | _(none)_ | Public base URL of this server (such as `https://mcp.example.com`). Required for both OIDC modes. |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | _(none)_ | OIDC discovery endpoint URL (such as `https://auth.example.com/.well-known/openid-configuration`). |
| `SCHOLAR_MCP_OIDC_CLIENT_ID` | _(none)_ | OIDC client ID registered with your identity provider. Only needed for `oidc-proxy` mode. |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | _(none)_ | OIDC client secret. Only needed for `oidc-proxy` mode. |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` | *(ephemeral)* | JWT signing key for OIDC proxy sessions. **Required on Linux/Docker** for `oidc-proxy` mode; the ephemeral default invalidates all sessions on restart. Generate with: `openssl rand -hex 32`. |
| `SCHOLAR_MCP_OIDC_AUDIENCE` | _(none)_ | Expected JWT audience claim. When set, the token's `aud` must match. Used by both modes. |
| `SCHOLAR_MCP_OIDC_REQUIRED_SCOPES` | `openid` | Comma-separated required scopes (such as `openid,profile`). Used by both modes. |
| `SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false` | (`oidc-proxy` only) Set `true` to verify the upstream `access_token` as a JWT instead of the `id_token`. Use when your provider issues JWT access tokens. |
| `SCHOLAR_MCP_ACL_PATH` | _(none)_ | (scaffold) Path to a TOML ACL file enabling opt-in per-subject authorization. Requires uncommenting the matching scaffold in `src/scholar_mcp/config.py` and `src/scholar_mcp/server.py`; see [Authorization (opt-in)](https://github.com/pvliesdonk/scholar-mcp#authorization-opt-in) in the README. |

See [Authentication guide](guides/authentication.md) for setup instructions and [OIDC deployment](deployment/oidc.md) for provider-specific configuration.

## Cache TTLs

Cache expiry is not configurable via environment variables. The built-in TTLs are:

| Table | TTL | Description |
|---|---|---|
| `papers` | 30 days | Paper metadata |
| `authors` | 30 days | Author profiles |
| `citations` | 7 days | Citation lists (paper IDs) |
| `refs` | 7 days | Reference lists (paper IDs) |
| `openalex` | 30 days | OpenAlex enrichment data |
| `crossref` | 30 days | CrossRef metadata (publisher, page ranges, container titles) |
| `google_books` | 30 days | Google Books volume data (preview links, descriptions) |
| `id_aliases` | _(none)_ | Identifier-to-S2-ID mappings (never expires) |

Use the CLI to manage the cache:

```bash
scholar-mcp cache stats          # Show row counts and DB size
scholar-mcp cache clear          # Clear all (preserves id_aliases)
scholar-mcp cache clear --older-than 7   # Clear entries older than 7 days
```

## Rate Limiting

Rate limiting is automatic and not configurable:

- **With API key**: ~0.1 s between Semantic Scholar requests
- **Without API key**: ~1.1 s between requests
- **Retry**: automatic exponential backoff on HTTP 429 (up to 3 retries)

## Remote debugging

Optional development-only listener. Requires the `[debug]` extra (Docker images: built with `--build-arg DEBUG=true`; pip / uv installs: `pip install 'pvliesdonk-scholar-mcp[debug]'`). When `debugpy` isn't importable the helper logs a `WARNING` and continues, there's no hard failure.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_DEBUG_PORT` | _(none)_ | TCP port for the `debugpy` listener (such as `5678`). Unset = listener disabled. |
| `SCHOLAR_MCP_DEBUG_WAIT` | `false` | Block startup until the IDE attaches. Useful for debugging early startup code paths. |

See [Docker deployment → Remote debugging](deployment/docker.md#remote-debugging) for the IDE-attach walkthrough.

## Tool visibility

Operators can trim which tools this instance exposes. Each variable takes a
comma-separated list of explicit tool names:

- `SCHOLAR_MCP_TOOLS_ALLOW`: expose *only* the listed tools.
- `SCHOLAR_MCP_TOOLS_DENY`: hide the listed tools.

Hidden tools disappear from `tools/list` and are rejected on `tools/call`;
resources and prompts are unaffected. Setting both variables, or setting one
to a value with no names in it, is a startup error. A name matching no
registered tool is ignored, but an allowlist that matches nothing logs a
startup `WARNING` since the instance then exposes zero tools. See
`fastmcp-pvl-core`'s README for the full semantics.

## Background tasks

Every Scholar MCP instance wires a background-task backend at startup, so
a tool registered with `task=True` works with no extra setup. One variable
picks the backend:

- `SCHOLAR_MCP_TASKS_URL`: `memory://` runs tasks in-process and loses
  them on restart; `redis://...` is durable and shared across processes.

Unset, a `redis://` `SCHOLAR_MCP_KV_STORE_URL` is reused for tasks as
well, so a single URL configures every stateful subsystem. With neither set,
the backend falls back to `memory://`, which the server logs at startup when
running over HTTP. The queue name comes from the `SCHOLAR_MCP` prefix, so
two servers sharing one Redis do not share a queue.

Worker tuning stays on the native `FASTMCP_DOCKET_*` variables
(`FASTMCP_DOCKET_CONCURRENCY` and friends, listed in `.env.example`). Set the
backend through `SCHOLAR_MCP_TASKS_URL` rather than
`FASTMCP_DOCKET_URL`: the former wins when both are set, and the server warns
about the disagreement.

<!-- DOMAIN-CONFIG-VARS-START -->
<!-- Project-specific config notes; kept across copier update. Scholar's
     domain config is documented in the per-domain sections above (Core, PDF
     Conversion, EPO, Google Books, Server, Authentication, Cache TTLs, Rate
     Limiting). -->

### Long-running tools and background jobs

PDF downloads and docling conversions can take longer than a client is willing
to wait, so they are registered as dual-mode tools. What a caller gets back
depends only on how long the call takes:

- Finishes within `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` (25 seconds by default):
  the result, directly.
- Takes longer: a job handle, `{"status": "working", "job_id": "...",
  "poll_with": "get_job_result", ...}`. The work continues in the background
  and the caller redeems it with the `get_job_result` tool.
- Speaks the MCP task protocol: the call runs as a native background task and
  the queue `SCHOLAR_MCP_TASKS_URL` configures does the work.

Three variables tune this:

- `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S`: how long a call may run in the foreground
  before it is promoted. Keep it below the strictest client request timeout in
  play, so the server answers before the client hangs up.
- `SCHOLAR_MCP_JOBS_RESULT_TTL_S`: how long a job record is kept for polling.
  Measured from when the record is created, and settling a job never extends
  it, so callers should collect results promptly.
- `SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT`: the cap on live job records per calling
  subject. Over stdio every caller is the same subject, so there the cap bounds
  the whole server.

Job records live in the store `SCHOLAR_MCP_KV_STORE_URL` names, and are scoped
to the calling subject, so one caller can never poll a job belonging to
another. A job runs on the serving process and does not survive a restart of
it. Its record then reports `working` until the TTL removes it, rather than
inventing a result.
Durable execution across a restart is the native task path's job, which means a
`redis://` backend.

### Migrating from `list_tasks` / `get_task_result`

Earlier versions carried a second, private queue behind `list_tasks` and
`get_task_result` that `SCHOLAR_MCP_TASKS_URL` did not configure, and that kept
nothing across a restart. It is gone, and with it the
`{"queued": true, "task_id": "..."}` payload.

Poll `get_job_result` with the `job_id` from a job handle instead. The handle's
`poll_with` field names the tool, so a client that follows it needs no change.
`list_tasks` has no replacement, because job lookup is by id.
<!-- DOMAIN-CONFIG-VARS-END -->

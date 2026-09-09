# Configuration

Scholar MCP reads all configuration from environment variables. Domain variables carry the `SCHOLAR_MCP_` prefix; a few third-party variables (`FASTMCP_*`, `PUID`/`PGID`) keep their upstream names.

This page is the complete reference: every variable the server reads appears in exactly one table below. The tables come from the same source as `.env.example`, the packaged env files, and the [configuration generator](https://pvliesdonk.github.io/scholar-mcp/unstable/configuration-generator/index.md), so the four cannot disagree. The README carries a hand-picked subset of these variables as its quick entry point.

## Server

Transport, identity, and tool visibility. `SCHOLAR_MCP_SERVER_NAME` and `SCHOLAR_MCP_INSTRUCTIONS_EXTRA` let an operator rename an instance or append deployment notes to the generated MCP instructions without touching code; the legacy `SCHOLAR_MCP_INSTRUCTIONS` replaces the generated text wholesale and logs a deprecation warning at startup.

`SCHOLAR_MCP_TOOLS_ALLOW` and `SCHOLAR_MCP_TOOLS_DENY` trim which tools an instance exposes. Hidden tools disappear from `tools/list` and are rejected on `tools/call`; resources and prompts are unaffected. Setting both variables, or setting one to a value with no names in it, is a startup error. A name matching no registered tool is ignored, but an allowlist that matches nothing logs a startup warning, since the instance then exposes zero tools. See `fastmcp-pvl-core`'s README for the full semantics.

| Variable                         | Default     | Description                                                                                                                                                                                                                                                 |
| -------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_TRANSPORT`          | `stdio`     | Transport the server speaks: `stdio` for local Claude Desktop/Code, `http` or `sse` for a network server.                                                                                                                                                   |
| `SCHOLAR_MCP_HOST`               | `127.0.0.1` | Interface the HTTP server binds to.                                                                                                                                                                                                                         |
| `SCHOLAR_MCP_PORT`               | `8000`      | TCP port for the HTTP server.                                                                                                                                                                                                                               |
| `SCHOLAR_MCP_BASE_URL`           | (none)      | Public base URL of the deployed server (`https://mcp.example.com`). Required for OIDC. Also the fallback source of the MCP Apps domain when `app_domain` is unset.                                                                                          |
| `SCHOLAR_MCP_TOOLS_ALLOW`        | (none)      | Comma-separated explicit tool names this instance exposes; every other tool is hidden from listings and cannot be invoked. Names matching no registered tool are inert. Mutually exclusive with `tools_deny`. Takes effect through `apply_tool_visibility`. |
| `SCHOLAR_MCP_TOOLS_DENY`         | (none)      | Comma-separated explicit tool names hidden from this instance (absent from listings, cannot be invoked). Names matching no registered tool are inert. Mutually exclusive with `tools_allow`. Takes effect through `apply_tool_visibility`.                  |
| `SCHOLAR_MCP_SERVER_NAME`        | (none)      | Rename this server instance; defaults to the project name.                                                                                                                                                                                                  |
| `SCHOLAR_MCP_INSTRUCTIONS_EXTRA` | (none)      | Operator context appended to the generated MCP instructions.                                                                                                                                                                                                |
| `SCHOLAR_MCP_INSTRUCTIONS`       | (none)      | Legacy: replaces the entire generated MCP instructions text (deprecated; prefer the \_EXTRA variant).                                                                                                                                                       |
| `SCHOLAR_MCP_HTTP_PATH`          | `/mcp`      | Mount path for the MCP endpoint.                                                                                                                                                                                                                            |

## Authentication

Callers authenticate with a bearer token or OIDC; the two are mutually exclusive, and `SCHOLAR_MCP_AUTH_MODE` is normally inferred from which credentials are set. The Required column below means "required to enable OIDC": with none of these set, the server starts and serves unauthenticated. See the [authentication guide](https://pvliesdonk.github.io/scholar-mcp/unstable/guides/authentication/index.md) for setup, mapped multi-subject tokens, and troubleshooting.

| Variable                               | Default                 | Required | Description                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------- | ----------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_BEARER_TOKEN`             | (none)                  | No       | Single shared bearer token; enables bearer auth unless `bearer_tokens_file` is set, which takes precedence.                                                                                                                                                                                                                                                                   |
| `SCHOLAR_MCP_OIDC_CONFIG_URL`          | (none)                  | **Yes**  | OIDC discovery document URL (`https://auth.example.com/.well-known/openid-configuration`).                                                                                                                                                                                                                                                                                    |
| `SCHOLAR_MCP_OIDC_CLIENT_ID`           | (none)                  | **Yes**  | OIDC client identifier registered with the provider.                                                                                                                                                                                                                                                                                                                          |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET`       | (none)                  | **Yes**  | OIDC client secret registered with the provider.                                                                                                                                                                                                                                                                                                                              |
| `SCHOLAR_MCP_OIDC_AUDIENCE`            | (none)                  | No       | Expected `aud` claim; tokens issued for another audience are rejected.                                                                                                                                                                                                                                                                                                        |
| `SCHOLAR_MCP_OIDC_REQUIRED_SCOPES`     | `openid`                | No       | Scopes a caller must present, space- or comma-separated. Defaults to `openid` in oidc-proxy mode.                                                                                                                                                                                                                                                                             |
| `SCHOLAR_MCP_OIDC_ADVERTISED_SCOPES`   | `openid offline_access` | No       | Scopes advertised to MCP clients in protected-resource metadata, space- or comma-separated. Overrides the default `openid offline_access`; `oidc_required_scopes` is always added on top. Set this when the registered client is not permitted `offline_access`, or to have clients request extra claim scopes (such as `groups`) without also requiring them in every token. |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY`     | `derived`               | No       | Signing key for issued tokens; used in oidc-proxy mode only. When unset, the key is derived deterministically from `oidc_client_secret`, so tokens survive a restart. Rotating that secret then invalidates every issued token. Set this explicitly to decouple token validity from secret rotation. Generate with `openssl rand -hex 32`.                                    |
| `SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false`                 | No       | Validate the access token instead of the id token.                                                                                                                                                                                                                                                                                                                            |
| `SCHOLAR_MCP_AUTH_MODE`                | (none)                  | No       | Explicit auth-mode override, accepting `remote` or `oidc-proxy` (case- and whitespace-insensitive). When unset the mode is auto-detected from which auth variables are set; the override exists because having all four OIDC variables set is ambiguous between those two modes. Other values are ignored with a warning.                                                     |
| `SCHOLAR_MCP_BEARER_TOKENS_FILE`       | (none)                  | No       | Path to a TOML file mapping bearer tokens to subjects; overrides the single-token `bearer_token` mode.                                                                                                                                                                                                                                                                        |
| `SCHOLAR_MCP_BEARER_DEFAULT_SUBJECT`   | `bearer-anon`           | No       | Subject assigned to the single-token bearer mode; ignored when `bearer_tokens_file` is set, since mapped mode carries per-token subjects.                                                                                                                                                                                                                                     |

## Persistence

One URL configures every stateful subsystem. A `redis://` `SCHOLAR_MCP_KV_STORE_URL` is also reused for background tasks when `SCHOLAR_MCP_TASKS_URL` is unset, so a single URL covers both.

| Variable                      | Default              | Description                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_KV_STORE_URL`    | `file:///data/state` | Persistent-state backend URL shared by every pvl-core subsystem that needs state. `memory://` is in-process and lost on restart; `file:///path` persists on one server; `redis://`, `dynamodb://` and `mongodb://` each need their matching extra. When unset, defaults to `file:///data/state` (the volume family Docker images mount), or to `memory://` (with a warning) on a host where that directory is not usable. |
| `SCHOLAR_MCP_EVENT_STORE_URL` | (none)               | Legacy state-backend override, used by `build_event_store` and `build_kv_store` only when `kv_store_url` is unset. It then backs every namespace, not just HTTP resumability. Prefer `kv_store_url` for new deployments.                                                                                                                                                                                                  |
| `SCHOLAR_MCP_TASKS_URL`       | (none)               | Background-task (Docket) backend URL: `memory://` is in-process and lost on restart; `redis://` is durable and multi-process. When unset, a `redis://` `kv_store_url` is reused for tasks too; otherwise fastmcp's `memory://` default applies. Only applies when task-enabled tools exist. Applied via `configure_task_backend`.                                                                                         |

## Background tasks

Every Scholar MCP instance wires a background-task backend at startup, so a tool registered with `task=True` works with no extra setup. `SCHOLAR_MCP_TASKS_URL` (under Persistence above) picks the backend: `memory://` runs tasks in-process and loses them on restart; `redis://...` is durable and shared across processes. With neither it nor a `redis://` KV store set, the backend falls back to `memory://`, which the server logs at startup when running over HTTP. The queue name comes from the `SCHOLAR_MCP` prefix, so two servers sharing one Redis do not share a queue.

Worker tuning stays on the native `FASTMCP_DOCKET_*` variables below. Set the backend through `SCHOLAR_MCP_TASKS_URL` rather than `FASTMCP_DOCKET_URL`: the former wins when both are set, and the server warns about the disagreement.

| Variable                                | Default | Description                                                                              |
| --------------------------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `FASTMCP_DOCKET_CONCURRENCY`            | `10`    | Maximum background tasks this worker runs at once.                                       |
| `FASTMCP_DOCKET_WORKER_NAME`            | (none)  | Identifies this worker in the queue; defaults to a generated name.                       |
| `FASTMCP_DOCKET_REDELIVERY_TIMEOUT`     | `300`   | Seconds before a task claimed by a worker that never finished is redelivered to another. |
| `FASTMCP_DOCKET_RECONNECTION_DELAY`     | `5`     | Seconds to wait before reconnecting after the queue connection drops.                    |
| `FASTMCP_DOCKET_MINIMUM_CHECK_INTERVAL` | `0.05`  | Seconds between queue polls; lower cuts latency and raises idle load.                    |

## MCP Apps

| Variable                 | Default | Description                                                                                  |
| ------------------------ | ------- | -------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_APP_DOMAIN` | (none)  | MCP Apps iframe domain, used for CSP sandboxing. Overrides the host derived from `base_url`. |

## Logging

| Variable                      | Default | Description                                                                                                                      |
| ----------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `FASTMCP_LOG_LEVEL`           | `INFO`  | Log level for FastMCP internals and app loggers (DEBUG / INFO / WARNING / ERROR / CRITICAL). The -v CLI flag overrides to DEBUG. |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true`  | Set false for plain or structured JSON log output.                                                                               |

## Container runtime

Read by the container entrypoint (Docker / Compose), not by the server process.

| Variable | Default | Description                                                                                                  |
| -------- | ------- | ------------------------------------------------------------------------------------------------------------ |
| `PUID`   | `1000`  | Run the server process as this UID; the container entrypoint reassigns ownership of writable paths to match. |
| `PGID`   | `1000`  | Run the server process as this GID; pair with PUID to match the owner of a mounted volume.                   |

## Remote debugger

Development only; the image must be built with `--build-arg DEBUG=true`, and the protocol is unauthenticated. See [remote debugging](https://pvliesdonk.github.io/scholar-mcp/unstable/deployment/docker/#remote-debugging).

| Variable                 | Default | Description                                                                 |
| ------------------------ | ------- | --------------------------------------------------------------------------- |
| `SCHOLAR_MCP_DEBUG_PORT` | `5678`  | debugpy listen port; the image must be built with `--build-arg DEBUG=true`. |
| `SCHOLAR_MCP_DEBUG_WAIT` | `false` | Block startup until a debugger attaches.                                    |

## Domain variables

### Patents: obtaining EPO OPS credentials

Both `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET` must be set for the patent tools to appear. With either missing they are omitted from the tool list rather than failing at call time, and every other tool works unaffected.

EPO OPS provides free access to bibliographic data for 100+ patent offices. Follow these steps to obtain credentials:

1. Register at <https://developers.epo.org/user/register>. Fill in your name, email, and organisation.
1. Wait for an email confirmation and click the verification link.
1. Log in to the [EPO developer portal](https://developers.epo.org/).
1. Navigate to **My Apps** in the top menu.
1. Click **Add a new App** and choose a name (such as `scholar-mcp`).
1. Select **Non-paying** as the access method (provides free access with standard rate limits).
1. Copy the generated **Consumer Key** and **Consumer Secret** to your environment:

```
export SCHOLAR_MCP_EPO_CONSUMER_KEY="your-consumer-key"
export SCHOLAR_MCP_EPO_CONSUMER_SECRET="your-consumer-secret"
```

Or in `claude_desktop_config.json`:

```
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

### Cache TTLs

Cache expiry is not configurable via environment variables. The built-in TTLs are:

| Table          | TTL      | Description                                                  |
| -------------- | -------- | ------------------------------------------------------------ |
| `papers`       | 30 days  | Paper metadata                                               |
| `authors`      | 30 days  | Author profiles                                              |
| `citations`    | 7 days   | Citation lists (paper IDs)                                   |
| `refs`         | 7 days   | Reference lists (paper IDs)                                  |
| `openalex`     | 30 days  | OpenAlex enrichment data                                     |
| `crossref`     | 30 days  | CrossRef metadata (publisher, page ranges, container titles) |
| `google_books` | 30 days  | Google Books volume data (preview links, descriptions)       |
| `id_aliases`   | *(none)* | Identifier-to-S2-ID mappings (never expires)                 |

Use the CLI to manage the cache:

```
scholar-mcp cache stats          # Show row counts and DB size
scholar-mcp cache clear          # Clear all (preserves id_aliases)
scholar-mcp cache clear --older-than 7   # Clear entries older than 7 days
```

### Rate limiting

Rate limiting is automatic and not configurable:

- **With API key**: ~0.1 s between Semantic Scholar requests
- **Without API key**: ~1.1 s between requests
- **Retry**: automatic exponential backoff on HTTP 429 (up to 3 retries)

### Long-running tools and `get_job_result`

Every tool whose work can run long runs as a background job when it is slow. The exceptions are the pure cache and index reads, which cannot: they answer directly whatever the upstream is doing. A call that finishes within `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` returns its result directly. A slower one is promoted to a background job, and the caller gets a handle instead:

```
{"status": "working", "job_id": "...", "poll_with": "get_job_result",
 "retry_after_s": 5.0, "message": "..."}
```

Calling `get_job_result` with that `job_id` returns `working` until the work settles, then `completed` with a `result` object, or `failed` with an `error`. A cache hit answers directly and creates no job at all.

| Variable                           | Default | Meaning                                                                                         |
| ---------------------------------- | ------- | ----------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` | `25`    | Foreground window before promotion. Keep it below the strictest client request timeout in play. |
| `SCHOLAR_MCP_JOBS_RESULT_TTL_S`    | `3600`  | Job-record retention, measured from creation. Settling a job never extends it.                  |
| `SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT` | `256`   | Live-job cap per calling subject.                                                               |

Two operational notes:

- **Job records live in the KV backend**, so `SCHOLAR_MCP_KV_STORE_URL` covers them along with every other stateful subsystem. That is a different variable from `SCHOLAR_MCP_TASKS_URL`, which selects the native SEP-1686 Docket backend described under [Background tasks](#background-tasks).
- **A restart does not resume promoted work.** The job stops running with the process, while its record survives, so a poll after a restart reports `working` with a growing `running_for_s` until the retention period removes the record. That is deliberate, because a result is never invented. It does mean a job still reported as `working` long past its expected duration may be orphaned rather than slow. For work that must survive a restart, use the native task path with a `redis://` backend.

If you restrict the tool surface with `SCHOLAR_MCP_TOOLS_ALLOW`, **include `get_job_result`**. The allowlist matches on tool name, so leaving it out makes every job handle unresolvable.

Upgrading from a release that had `get_task_result` and `list_tasks`: those tools no longer exist, and an allowlist naming them keeps working because an unknown name is ignored rather than rejected. Nothing errors, so add `get_job_result` yourself. Without it the server hands out job handles that nothing exposed can poll.

### EPO throttling

The patent tools wait out an amber or red EPO traffic light rather than failing on it. Each wait is longer than the 60-second lifetime of the cached light, because a shorter one would re-read the same cached colour instead of asking EPO again. Two retries follow the first attempt, so a throttled call can spend roughly three minutes waiting. That is well past `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S`, so such a call is handed back as a job to poll rather than holding the connection open.

A black light means the daily quota is spent. That does not clear until tomorrow, so it is reported at once with `"retryable": false` instead of costing the caller the full wait for the same answer.

| Variable                    | Default             | Required | Description                                                                                                                                                                             |
| --------------------------- | ------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_READ_ONLY`     | `true`              | No       | When true, write-tagged tools (PDF download and conversion cache writes) are hidden. Set false to enable them.                                                                          |
| `SCHOLAR_MCP_S2_API_KEY`    | (none)              | No       | Semantic Scholar API key. Optional but strongly recommended: unauthenticated requests are limited to ~1 req/s. Request one at https://www.semanticscholar.org/product/api#api-key-form. |
| `SCHOLAR_MCP_CACHE_DIR`     | `/data/scholar-mcp` | No       | Directory for the SQLite cache database (cache.db) and downloaded PDFs (pdfs/, md/).                                                                                                    |
| `SCHOLAR_MCP_CONTACT_EMAIL` | (none)              | No       | Contact email for the OpenAlex polite pool (improves rate limits). Also enables Unpaywall lookups as a PDF fallback source.                                                             |

### Standards

| Variable               | Default | Required | Description                                                                                                                                      |
| ---------------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SCHOLAR_GITHUB_TOKEN` | (none)  | No       | GitHub token used to raise rate limits when fetching standards documents from GitHub. Optional; unauthenticated requests work at reduced limits. |

### PDF conversion

| Variable                  | Default  | Required | Description                                                                                                                                        |
| ------------------------- | -------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_DOCLING_URL` | (none)   | No       | Base URL of a running docling-serve instance for PDF conversion (such as http://localhost:5001). When unset, PDF conversion tools return an error. |
| `SCHOLAR_MCP_VLM_API_URL` | (none)   | No       | OpenAI-compatible VLM endpoint for formula and figure enrichment during PDF conversion.                                                            |
| `SCHOLAR_MCP_VLM_API_KEY` | (none)   | No       | API key for the VLM endpoint.                                                                                                                      |
| `SCHOLAR_MCP_VLM_MODEL`   | `gpt-4o` | No       | Model name to use with the VLM endpoint.                                                                                                           |

### Patents (EPO OPS)

| Variable                          | Default | Required | Description                                                                                                                                |
| --------------------------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `SCHOLAR_MCP_EPO_CONSUMER_KEY`    | (none)  | No       | EPO Open Patent Services consumer key. Optional; patent tools are hidden when unset. Register at https://developers.epo.org/user/register. |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | (none)  | No       | EPO Open Patent Services consumer secret. Optional; patent tools are hidden when unset.                                                    |

### Books

| Variable                           | Default | Required | Description                                                                             |
| ---------------------------------- | ------- | -------- | --------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` | (none)  | No       | Google Books API key. Optional; book tools work unauthenticated at reduced rate limits. |

### Jobs

| Variable                           | Default  | Required | Description                                                                                                                                |
| ---------------------------------- | -------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` | `25.0`   | No       | Seconds a long-running tool call may run in the foreground before it is promoted to a background job and a job handle is returned instead. |
| `SCHOLAR_MCP_JOBS_RESULT_TTL_S`    | `3600.0` | No       | Seconds a background-job record (working or finished) is retained for polling before it expires from the store.                            |
| `SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT` | `256`    | No       | Maximum live background jobs per calling subject; further promotions are rejected until older records expire.                              |

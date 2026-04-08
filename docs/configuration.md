# Configuration

All settings are controlled via environment variables with the `SCHOLAR_MCP_` prefix. No configuration file is needed.

## Core

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | -- | [Semantic Scholar API key](https://www.semanticscholar.org/product/api#api-key-form). Optional, but strongly recommended: unauthenticated requests are limited to ~1 req/s while authenticated requests get ~10 req/s. |
| `SCHOLAR_MCP_READ_ONLY` | `true` | When `true`, all write-tagged tools are hidden. Set to `false` to enable PDF download and conversion. |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Directory for the SQLite cache database (`cache.db`) and downloaded PDFs (`pdfs/`, `md/`). |
| `SCHOLAR_MCP_CONTACT_EMAIL` | -- | Included in the OpenAlex `User-Agent` header for [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication#the-polite-pool) access. Also enables [Unpaywall](https://unpaywall.org/products/api) lookups as a PDF fallback source when a paper has no open-access URL in Semantic Scholar. |
| `FASTMCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. Controls all output (application and middleware). The `-v` CLI flag sets this to `DEBUG`. |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set to `false` for plain/JSON-structured output suitable for log aggregation tools (Loki, Datadog, Splunk). When `true`, output uses Rich formatting (colors, timestamps). |

## PDF Conversion

These settings are only needed if you want to use the PDF conversion tools. They require a running [docling-serve](https://github.com/DS4SD/docling-serve) instance.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_DOCLING_URL` | -- | Base URL of a running docling-serve instance (e.g. `http://localhost:5001`). When unset, the PDF conversion tools are still registered but will return an error. |
| `SCHOLAR_MCP_VLM_API_URL` | -- | OpenAI-compatible VLM endpoint for formula and figure enrichment during PDF conversion. |
| `SCHOLAR_MCP_VLM_API_KEY` | -- | API key for the VLM endpoint. |
| `SCHOLAR_MCP_VLM_MODEL` | `gpt-4o` | Model name to use with the VLM endpoint. |

!!! tip "VLM enrichment"
    When both `SCHOLAR_MCP_VLM_API_URL` and `SCHOLAR_MCP_VLM_API_KEY` are set, tools can request VLM-enriched conversion that extracts LaTeX formulas and generates figure descriptions. This produces higher-quality Markdown but is slower and costs API calls.

## EPO Open Patent Services

These settings enable patent search via the [EPO Open Patent Services (OPS)](https://www.epo.org/en/searching-for-patents/data/web-services/ops) API. Both variables must be set for patent tools to be enabled; if either is missing, the `search_patents` and `get_patent` tools are automatically hidden.

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_EPO_CONSUMER_KEY` | -- | EPO OPS consumer key. Optional -- patent tools are hidden when unset. |
| `SCHOLAR_MCP_EPO_CONSUMER_SECRET` | -- | EPO OPS consumer secret. Optional -- patent tools are hidden when unset. |

!!! info "Graceful degradation"
    When credentials are not configured, patent tools are silently omitted from the tool list. Paper search and all other tools continue to work normally without EPO credentials.

### Registering for EPO OPS access

EPO OPS provides free access to bibliographic data for 100+ patent offices. Follow these steps to obtain credentials:

1. Register at [https://developers.epo.org/user/register](https://developers.epo.org/user/register) -- fill in your name, email, and organisation.
2. Wait for an email confirmation and click the verification link.
3. Log in to the [EPO developer portal](https://developers.epo.org/).
4. Navigate to **My Apps** in the top menu.
5. Click **Add a new App** and choose a name (e.g. `scholar-mcp`).
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

## Server

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_SERVER_NAME` | `scholar-mcp` | MCP server display name shown to clients. |
| `SCHOLAR_MCP_INSTRUCTIONS` | *(auto-generated)* | Custom system-level instructions for LLM clients. When unset, auto-generated instructions describe available tools and the current read-only/write mode. |
| `SCHOLAR_MCP_HTTP_PATH` | `/mcp` | Mount path for HTTP transport. |

## Authentication

Authentication is optional. When no auth variables are set, the server accepts unauthenticated connections.

!!! warning
    Authentication only applies to the HTTP transport. stdio connections (e.g. Claude Desktop) are always unauthenticated since the client spawns the server process directly.

### Auth modes

The server supports two OIDC modes, auto-detected from environment variables:

| Mode | When selected | How it works |
|---|---|---|
| **remote** | `BASE_URL` + `OIDC_CONFIG_URL` set (no client credentials) | Validates JWTs locally via JWKS. The external auth provider (e.g. Authelia behind a reverse proxy) handles the full OAuth flow. |
| **oidc-proxy** | All four OIDC vars set (`BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) | The MCP server acts as an OAuth proxy, handling the OIDC authorization flow itself. |

Auto-detection prefers `oidc-proxy` when all four vars are present. Override with `SCHOLAR_MCP_AUTH_MODE=remote` or `SCHOLAR_MCP_AUTH_MODE=oidc-proxy`.

When both bearer and OIDC auth are configured, the server uses multi-auth — either mechanism is accepted.

### Variables

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_BEARER_TOKEN` | -- | Static bearer token. When set, HTTP clients must send `Authorization: Bearer <token>`. |
| `SCHOLAR_MCP_AUTH_MODE` | *(auto)* | Force auth mode: `remote` or `oidc-proxy`. When unset, auto-detected from which OIDC env vars are present. |
| `SCHOLAR_MCP_BASE_URL` | -- | Public base URL of this server (e.g. `https://mcp.example.com`). Required for both OIDC modes. |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | -- | OIDC discovery endpoint URL (e.g. `https://auth.example.com/.well-known/openid-configuration`). |
| `SCHOLAR_MCP_OIDC_CLIENT_ID` | -- | OIDC client ID registered with your identity provider. Only needed for `oidc-proxy` mode. |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | -- | OIDC client secret. Only needed for `oidc-proxy` mode. |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` | *(ephemeral)* | JWT signing key for OIDC proxy sessions. **Required on Linux/Docker** for `oidc-proxy` mode -- the ephemeral default invalidates all sessions on restart. Generate with: `openssl rand -hex 32`. |
| `SCHOLAR_MCP_OIDC_AUDIENCE` | -- | Expected JWT audience claim. When set, the token's `aud` must match. Used by both modes. |
| `SCHOLAR_MCP_OIDC_REQUIRED_SCOPES` | `openid` | Comma-separated required scopes (e.g. `openid,profile`). Used by both modes. |
| `SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false` | (`oidc-proxy` only) Set `true` to verify the upstream `access_token` as a JWT instead of the `id_token`. Use when your provider issues JWT access tokens. |

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
| `id_aliases` | -- | Identifier-to-S2-ID mappings (never expires) |

Use the CLI to manage the cache:

```bash
scholar-mcp cache stats          # Show row counts and DB size
scholar-mcp cache clear          # Clear all (preserves id_aliases)
scholar-mcp cache clear --older-than 7   # Clear entries older than 7 days
```

## Rate Limiting

Rate limiting is automatic and not configurable:

- **With API key**: ~0.1s between Semantic Scholar requests
- **Without API key**: ~1.1s between requests
- **Retry**: automatic exponential backoff on HTTP 429 (up to 3 retries)

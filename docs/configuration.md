# Configuration

All settings are controlled via environment variables with the `SCHOLAR_MCP_` prefix. No configuration file is needed.

## Core

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | -- | [Semantic Scholar API key](https://www.semanticscholar.org/product/api#api-key-form). Optional, but strongly recommended: unauthenticated requests are limited to ~1 req/s while authenticated requests get ~10 req/s. |
| `SCHOLAR_MCP_READ_ONLY` | `true` | When `true`, all write-tagged tools are hidden. Set to `false` to enable PDF download and conversion. |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Directory for the SQLite cache database (`cache.db`) and downloaded PDFs (`pdfs/`, `md/`). |
| `SCHOLAR_MCP_CONTACT_EMAIL` | -- | Included in the OpenAlex `User-Agent` header. Setting this gives you access to the [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication#the-polite-pool) with higher rate limits. |
| `SCHOLAR_MCP_LOG_LEVEL` | `INFO` | Python logging level: `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |

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

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_BEARER_TOKEN` | -- | Static bearer token. When set, HTTP clients must send `Authorization: Bearer <token>`. |
| `SCHOLAR_MCP_BASE_URL` | -- | Public base URL of this server, required for OIDC callback routing (e.g. `https://mcp.example.com`). |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | -- | OIDC discovery endpoint URL (e.g. `https://auth.example.com/.well-known/openid-configuration`). |
| `SCHOLAR_MCP_OIDC_CLIENT_ID` | -- | OIDC client ID registered with your identity provider. |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | -- | OIDC client secret. |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` | *(ephemeral)* | JWT signing key for OIDC sessions. **Required on Linux/Docker** -- the ephemeral default invalidates all sessions on restart. Generate with: `openssl rand -hex 32`. |
| `SCHOLAR_MCP_OIDC_AUDIENCE` | -- | Expected JWT audience claim. When set, the token's `aud` must match. Useful for multi-tenant deployments. |
| `SCHOLAR_MCP_OIDC_REQUIRED_SCOPES` | `openid` | Comma-separated required scopes (e.g. `openid,profile`). Token must include all listed scopes. |
| `SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false` | Set `true` to verify the upstream `access_token` as a JWT instead of the `id_token`. Use when your provider issues JWT access tokens and you need audience-claim validation on that token. |

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

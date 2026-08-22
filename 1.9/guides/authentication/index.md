# Authentication

This guide covers how to protect your MCP server with authentication. Choose the mode that fits your deployment.

Transport requirement

Authentication only works with HTTP transport (`--transport http` or `sse`). It has no effect with `--transport stdio`.

## Auth modes

The server supports five authentication modes:

| Mode             | When to use                                                                              | Configuration                                                                                       |
| ---------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Multi-auth**   | Mixed clients, such as Claude web (OIDC) + Claude Code (bearer token) on the same server | Set `SCHOLAR_MCP_BEARER_TOKEN` + OIDC vars (either remote or oidc-proxy)                            |
| **Remote**       | Behind a reverse proxy that handles OAuth (such as Traefik + Authelia)                   | Set `SCHOLAR_MCP_BASE_URL` + `SCHOLAR_MCP_OIDC_CONFIG_URL` only                                     |
| **OIDC proxy**   | Production with user identity, SSO, multi-user access, server handles OAuth directly     | Set all four OIDC variables (`BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) |
| **Bearer token** | Simple deployments behind a VPN, Docker compose stacks, development                      | Set `SCHOLAR_MCP_BEARER_TOKEN` only                                                                 |
| **No auth**      | Local stdio usage, trusted networks                                                      | Default (nothing to configure)                                                                      |

The OIDC mode is auto-detected from environment variables: `oidc-proxy` when all four OIDC vars are present, `remote` when only `BASE_URL` + `OIDC_CONFIG_URL` are set. Override with `SCHOLAR_MCP_AUTH_MODE=remote` or `SCHOLAR_MCP_AUTH_MODE=oidc-proxy`.

When both bearer token and OIDC (either mode) are configured, the server accepts **either** credential: a valid bearer token or a valid OIDC session. This is useful when different clients require different authentication flows against the same server instance.

______________________________________________________________________

## Bearer token

The simplest way to protect your server. A single static token shared between server and clients.

### Setup

1. Generate a random token:

   ```
   openssl rand -hex 32
   ```

1. Set the environment variable:

   ```
   SCHOLAR_MCP_BEARER_TOKEN=your-generated-token
   ```

1. Start the server with HTTP transport:

   ```
   scholar-mcp serve --transport http --port 8000
   ```

### Client usage

Clients must include the token in every request:

```
Authorization: Bearer your-generated-token
```

### When to use bearer token

- Deployments behind a VPN or firewall
- Docker compose stacks where services communicate internally
- Development and testing environments
- Any scenario where full OIDC is overkill

### Mapped bearer tokens (multi-subject)

The bearer-token mode above shares one subject across every authenticated caller. By default this is the library's `bearer-anon`; override with `SCHOLAR_MCP_BEARER_DEFAULT_SUBJECT`. For audit logs and authorization that distinguish callers, switch to mapped-token mode by pointing `SCHOLAR_MCP_BEARER_TOKENS_FILE` at a TOML file:

```
# tokens.toml
[tokens]
"ghp_alice_xxxxxxxx" = "user:alice@example.com"
"sk_ci_yyyyyyyy"     = "service:ci-bot"
```

Each token resolves to a distinct subject string for downstream attribution. Subject strings are opaque: the `<kind>:<id>` convention (`user:`, `service:`, `token:`) is documentation only. When `BEARER_TOKENS_FILE` is set it overrides `BEARER_TOKEN` (a `WARNING` is logged if both are present). A missing or malformed file aborts startup with `ConfigurationError` rather than silently denying every request.

For the per-tool authorization that consumes these subjects, see the **Authorization (opt-in)** section of the project [README](https://github.com/pvliesdonk/scholar-mcp#authorization-opt-in).

______________________________________________________________________

## Remote auth

Use this when your server sits behind a reverse proxy (such as Traefik + Authelia) that handles the full OAuth/OIDC flow. The MCP server validates JWTs locally using the OIDC provider's JWKS endpoint, no client credentials needed.

### How it works

```
Client → Reverse proxy (Authelia) → scholar-mcp (JWT validation only)
```

1. Client connects to the server
1. The reverse proxy's auth middleware (Authelia) handles the OAuth flow
1. Authelia issues a JWT and forwards the request with the token
1. Scholar-mcp validates the JWT locally via the provider's JWKS keys

### Required variables

| Variable                      | Description                                                                                   |
| ----------------------------- | --------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_BASE_URL`        | Public base URL (such as `https://mcp.example.com`)                                           |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | OIDC discovery endpoint (such as `https://auth.example.com/.well-known/openid-configuration`) |

### Optional variables

| Variable                           | Default  | Description                     |
| ---------------------------------- | -------- | ------------------------------- |
| `SCHOLAR_MCP_OIDC_AUDIENCE`        | *(none)* | Expected JWT audience claim     |
| `SCHOLAR_MCP_OIDC_REQUIRED_SCOPES` | `openid` | Comma-separated required scopes |

### When to use remote auth

- Deployments behind Traefik + Authelia, Caddy + Authentik, or similar reverse-proxy auth stacks
- When the OIDC provider issues opaque access tokens (such as Authelia), the proxy handles the token exchange
- When you don't want to register the MCP server as an OIDC client

______________________________________________________________________

## OIDC proxy

Full OAuth 2.1 authentication using an external identity provider. The MCP server itself acts as an OAuth proxy, supports user login flows, SSO, and multi-user access control without an external auth reverse proxy.

### How it works

The server proxies OIDC itself, with no external auth sidecar to deploy:

```
Client → scholar-mcp (OIDCProxy) → OIDC Provider
```

1. Client connects to the server
1. Server redirects to the OIDC provider for login
1. Provider authenticates the user and returns a code
1. Server exchanges the code for tokens
1. Subsequent requests include the JWT

### Required variables

| Variable                         | Description                                                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SCHOLAR_MCP_BASE_URL`           | Public base URL of the deployed server (`https://mcp.example.com`). Required for OIDC. Also the fallback source of the MCP Apps domain when `app_domain` is unset. |
| `SCHOLAR_MCP_OIDC_CONFIG_URL`    | OIDC discovery document URL (`https://auth.example.com/.well-known/openid-configuration`).                                                                         |
| `SCHOLAR_MCP_OIDC_CLIENT_ID`     | OIDC client identifier registered with the provider.                                                                                                               |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | OIDC client secret registered with the provider.                                                                                                                   |

### Optional variables

| Variable                               | Default                 | Description                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_OIDC_AUDIENCE`            | (none)                  | Expected `aud` claim; tokens issued for another audience are rejected.                                                                                                                                                                                                                                                                                                        |
| `SCHOLAR_MCP_OIDC_REQUIRED_SCOPES`     | `openid`                | Scopes a caller must present, space- or comma-separated. Defaults to `openid` in oidc-proxy mode.                                                                                                                                                                                                                                                                             |
| `SCHOLAR_MCP_OIDC_ADVERTISED_SCOPES`   | `openid offline_access` | Scopes advertised to MCP clients in protected-resource metadata, space- or comma-separated. Overrides the default `openid offline_access`; `oidc_required_scopes` is always added on top. Set this when the registered client is not permitted `offline_access`, or to have clients request extra claim scopes (such as `groups`) without also requiring them in every token. |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY`     | `derived`               | Signing key for issued JSON Web Tokens; used in oidc-proxy mode only. When unset, the key is derived deterministically from `oidc_client_secret`, so tokens survive a restart. Rotating that secret invalidates every issued token. Set this explicitly to decouple token validity from secret rotation. Generate with `openssl rand -hex 32`.                                |
| `SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false`                 | Validate the access token instead of the id token.                                                                                                                                                                                                                                                                                                                            |

JWT signing key and secret rotation

When `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` is unset, FastMCP derives the signing key from the OIDC client secret, so the key stays the same across restarts. Rotating the client secret changes the derived key and invalidates every token issued under the old one. Set an explicit key to decouple token validity from client-secret rotation:

```
openssl rand -hex 32
```

Long-running sessions

Current MCP clients do not reliably refresh tokens; see [Known Limitations](#known-limitations-mcp-oauth-token-refresh). Configure **all** token lifetimes (access, id, refresh) on your identity provider to cover a full workday (8 hours or more). For simpler deployments, bearer token auth is unaffected by these limitations.

For the full OIDC reference (env vars, Docker Compose, subpath deployments, architecture):

- [OIDC Authentication reference](https://pvliesdonk.github.io/scholar-mcp/1.9/deployment/oidc/index.md)

______________________________________________________________________

## Troubleshooting

### "invalid client" error

The `client_id` and/or `redirect_uris` in your OIDC provider config don't match the values in your `.env` file. Verify both sides match exactly.

### Tokens invalidated after a client-secret rotation

You're missing `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY`. Without it, FastMCP derives the signing key from the OIDC client secret, so rotating that secret changes the derived key and invalidates every token issued under the old one. Generate and set a stable key to decouple token validity from secret rotation:

```
openssl rand -hex 32
```

### Auth has no effect

FastMCP's stdio transport doesn't enforce auth on incoming messages (stdio messages have no `Authorization` header), but auth provider construction still runs at startup regardless of transport, and the server logs a `WARNING: auth_configured_but_stdio_skips_enforcement` line when this happens so you don't mis-read startup logs as proof of enforcement.

Per-mode behaviour on `--transport stdio`:

- **bearer-single / bearer-mapped**: the verifier is built but never consulted. Safe to set, just inert.
- **`remote` mode** (`SCHOLAR_MCP_BASE_URL` + `SCHOLAR_MCP_OIDC_CONFIG_URL`, no client id/secret): OIDC discovery fires against the configured URL inside pvl-core's `build_remote_auth`. Discovery failure raises `ConfigurationError: OIDC discovery failed at …` and the server refuses to start (pvl-core ≥ 2.0 fail-loud).
- **`oidc-proxy` mode** (all four OIDC env vars set: `BASE_URL` + `OIDC_CONFIG_URL` + `OIDC_CLIENT_ID` + `OIDC_CLIENT_SECRET`): discovery fires inside FastMCP's `OIDCProxy.__init__` and currently propagates raw `httpx.HTTPError` / `pydantic.ValidationError` rather than `ConfigurationError` (asymmetry between pvl-core layers; tracked upstream). The CLI does not currently catch these, operators see the raw traceback.
- **`multi` mode** (bearer + OIDC together): inherits the OIDC failure mode of whichever sub-mode applies (`remote` or `oidc-proxy`) per above.

Recommendation: leave OIDC env vars unset on stdio deployments. Switch to `--transport http` to actually exercise auth.

### Bearer token not working

- Verify the env var is set and non-empty (whitespace-only values are ignored)
- Check that clients send `Authorization: Bearer <token>` (not `Basic` or other schemes)
- If OIDC is also configured, multi-auth is active: both bearer and OIDC are accepted simultaneously

### OIDC redirect fails

- Verify `BASE_URL` matches your public URL exactly (including any subpath prefix)
- For subpath deployments, see the [subpath deployment guide](https://pvliesdonk.github.io/scholar-mcp/1.9/deployment/oidc/#subpath-deployments); `BASE_URL` must include the prefix, `HTTP_PATH` must not
- Check that `redirect_uris` in your provider config includes your callback URL (such as `https://mcp.example.com/auth/callback`)

### Session drops after token expiry

**Symptom:** the MCP client works for a period (often ~1 hour), then starts returning 401 errors or stops responding. Restarting the client fixes it temporarily.

**Root cause:** this is almost always a token lifetime issue, not a server bug. Check three things:

1. **id_token lifetime** (most common): When using `verify_id_token` mode (the default for Authelia), the server re-validates the upstream `id_token` on every request. If your provider's `id_token` lifetime is shorter than the `access_token` lifetime, the session dies at the `id_token` expiry, even though the access token is still valid. Authelia defaults `id_token` to 1 hour. **Fix: set `id_token` lifetime to match `access_token`** in your provider config.
1. **access_token lifetime**: If both `id_token` and `access_token` are set correctly but sessions still drop, check that the provider's `expires_in` response matches your configured lifetime.
1. **No refresh token**: See [Known Limitations](#known-limitations-mcp-oauth-token-refresh) below; current MCP clients cannot refresh tokens, so sessions are limited to the token lifetime.

**Workaround:** configure **all** token lifetimes on your identity provider to cover a full workday:

```
# Authelia example
lifespans:
  custom:
    mcp_long_lived:
      access_token: '8h'
      id_token: '8h'        # must match access_token for verify_id_token mode
      refresh_token: '30d'
```

### Opaque access tokens (Authelia)

Authelia issues opaque (non-JWT) access tokens. This is handled automatically: the server verifies the `id_token` instead. No extra configuration needed.

______________________________________________________________________

## Known Limitations: MCP OAuth token refresh

Ecosystem-wide issue

The limitations below affect **all** OAuth-protected MCP servers, not just this one. They are caused by issues in the MCP client implementations (Claude Code, Claude.ai, Claude Desktop) and the MCP Python SDK. Check the linked tracking issues for current status.

### The problem

MCP clients cannot maintain sessions beyond the token lifetime because token refresh does not work. When tokens expire, the session drops and requires manual re-authentication. This affects every provider: Authelia, Keycloak, Google, and others.

### Why refresh doesn't work

Three independent issues prevent token refresh:

| Layer              | Issue                                                                                                                          | Impact                                                                                                                                                                                                                                                                    |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Claude Code**    | Stores refresh tokens but never uses them ([claude-code#21333](https://github.com/anthropics/claude-code/issues/21333))        | Refresh tokens are obtained and saved but never sent back to refresh expired access tokens                                                                                                                                                                                |
| **Claude Code**    | Does not ask for `offline_access` on its own ([claude-code#7744](https://github.com/anthropics/claude-code/issues/7744))       | Most OIDC providers issue no refresh token without this scope. The server advertises `openid offline_access` in its protected-resource metadata, so a client that requests the advertised set gets a refresh-capable grant; one that ignores the metadata still does not. |
| **MCP Python SDK** | Token refresh deadlocks inside SSE streams ([python-sdk#1326](https://github.com/modelcontextprotocol/python-sdk/issues/1326)) | Even with a valid refresh token, the SDK hangs when attempting refresh during an active stream                                                                                                                                                                            |

The server-side refresh architecture (FastMCP's `OAuthProxy.exchange_refresh_token()`) is correctly implemented and would work, but it requires the client to initiate the refresh, which none of the current clients do reliably.

### What works today

**Bearer token auth** is unaffected by all of the above. If your deployment allows it (such as Claude Code with env vars, or API clients), bearer tokens are the simplest and most reliable option.

**Long token lifetimes** are the only viable workaround for OIDC. Set all three lifetimes (access, id, refresh) to cover your typical session duration:

- `access_token: '8h'`: covers a workday
- `id_token: '8h'`: **must match access_token** when using `verify_id_token` mode (critical for Authelia)
- `refresh_token: '30d'`: ready for when clients support refresh
- Permit `offline_access` for the registered client; the server advertises it by default, so a client that honours the advertised scopes requests it. Where the client may not hold that scope, narrow what the server advertises with `SCHOLAR_MCP_OIDC_ADVERTISED_SCOPES` rather than letting the authorization request fail

### Tracking

These upstream issues are actively tracked:

- [anthropics/claude-code#21333](https://github.com/anthropics/claude-code/issues/21333): refresh tokens stored but never used
- [anthropics/claude-code#7744](https://github.com/anthropics/claude-code/issues/7744): `offline_access` scope never requested
- [modelcontextprotocol/python-sdk#1326](https://github.com/modelcontextprotocol/python-sdk/issues/1326): SSE refresh deadlock

When these are resolved, OIDC sessions should persist indefinitely via automatic token refresh with no changes needed server-side.

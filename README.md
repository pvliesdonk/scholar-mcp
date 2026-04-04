# fastmcp-server-template

> **This is a template repository.** Click "Use this template" to create your own MCP server, then follow [TEMPLATE.md](TEMPLATE.md) to customise it.

A production-ready [FastMCP](https://gofastmcp.com) server scaffold with batteries included:

- **Auth** — bearer token, OIDC, and multi-auth (both simultaneously)
- **Read-only mode** — write tools hidden via `mcp.disable(tags={"write"})`
- **CI** — test matrix (Python 3.11–3.14), ruff, mypy, pip-audit, gitleaks, CodeQL
- **Release pipeline** — semantic-release → PyPI + Docker (GHCR), SBOM attestation
- **Docker** — multi-arch, `gosu` privilege dropping, configurable PUID/PGID
- **Docs** — MkDocs Material + GitHub Pages

## Quick start

```bash
# Install and run (stdio transport)
pip install fastmcp-server-template[mcp]
mcp-server serve

# Or with HTTP transport
mcp-server serve --transport http --port 8000
```

## Configuration

All configuration is via environment variables prefixed with `MCP_SERVER_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_READ_ONLY` | `true` | Disable write tools |
| `MCP_SERVER_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MCP_SERVER_SERVER_NAME` | `mcp-server` | Server name shown to clients |
| `MCP_SERVER_INSTRUCTIONS` | (dynamic) | System instructions for LLM context |
| `MCP_SERVER_HTTP_PATH` | `/mcp` | Mount path for HTTP transport |

## Authentication

The server supports four auth modes:

1. **Multi-auth** — both bearer token and OIDC configured; either credential accepted
2. **Bearer token** — set `MCP_SERVER_BEARER_TOKEN` to a secret string
3. **OIDC** — full OAuth 2.1 flow via `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `BASE_URL`
4. **No auth** — server accepts all connections (default)

**Auth requires `--transport http` (or `sse`).** It has no effect with `--transport stdio`.

| Variable | Description |
|----------|-------------|
| `MCP_SERVER_BEARER_TOKEN` | Static bearer token |
| `MCP_SERVER_BASE_URL` | Public base URL — required for OIDC (e.g. `https://mcp.example.com`) |
| `MCP_SERVER_OIDC_CONFIG_URL` | OIDC discovery endpoint |
| `MCP_SERVER_OIDC_CLIENT_ID` | OIDC client ID |
| `MCP_SERVER_OIDC_CLIENT_SECRET` | OIDC client secret |
| `MCP_SERVER_OIDC_JWT_SIGNING_KEY` | JWT signing key — **required on Linux/Docker** to survive restarts |

See [Authentication guide](docs/guides/authentication.md) for full setup details.

## Docker

```bash
docker compose up -d
```

See [Docker deployment](docs/deployment/docker.md) for volumes, UID/GID, and Traefik setup.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## Using this template

See [TEMPLATE.md](TEMPLATE.md) for the step-by-step customisation guide, including the `rename.sh` bootstrap script.

## Keeping derived repos in sync

See [SYNC.md](SYNC.md) for the infrastructure vs domain boundary definition and the cherry-pick workflow for propagating non-domain changes between this template and derived repositories.

## License

MIT

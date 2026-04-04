# scholar-mcp

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
pip install scholar-mcp[mcp]
scholar-mcp serve

# Or with HTTP transport
scholar-mcp serve --transport http --port 8000
```

## Configuration

All configuration is via environment variables prefixed with `SCHOLAR_MCP_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHOLAR_MCP_READ_ONLY` | `true` | Disable write tools |
| `SCHOLAR_MCP_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SCHOLAR_MCP_SERVER_NAME` | `scholar-mcp` | Server name shown to clients |
| `SCHOLAR_MCP_INSTRUCTIONS` | (dynamic) | System instructions for LLM context |
| `SCHOLAR_MCP_HTTP_PATH` | `/mcp` | Mount path for HTTP transport |

## Authentication

The server supports four auth modes:

1. **Multi-auth** — both bearer token and OIDC configured; either credential accepted
2. **Bearer token** — set `SCHOLAR_MCP_BEARER_TOKEN` to a secret string
3. **OIDC** — full OAuth 2.1 flow via `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `BASE_URL`
4. **No auth** — server accepts all connections (default)

**Auth requires `--transport http` (or `sse`).** It has no effect with `--transport stdio`.

| Variable | Description |
|----------|-------------|
| `SCHOLAR_MCP_BEARER_TOKEN` | Static bearer token |
| `SCHOLAR_MCP_BASE_URL` | Public base URL — required for OIDC (e.g. `https://mcp.example.com`) |
| `SCHOLAR_MCP_OIDC_CONFIG_URL` | OIDC discovery endpoint |
| `SCHOLAR_MCP_OIDC_CLIENT_ID` | OIDC client ID |
| `SCHOLAR_MCP_OIDC_CLIENT_SECRET` | OIDC client secret |
| `SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY` | JWT signing key — **required on Linux/Docker** to survive restarts |

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

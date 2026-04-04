# Docker Deployment

## Quick start

```bash
docker compose up -d
```

The server listens on port 8000 with HTTP transport by default.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_READ_ONLY` | `true` | Disable write tools |
| `MCP_SERVER_BEARER_TOKEN` | — | Enable bearer token auth |
| `MCP_SERVER_LOG_LEVEL` | `INFO` | Log level |
| `MCP_SERVER_SERVER_NAME` | `mcp-server` | Server name shown to clients |
| `MCP_SERVER_INSTRUCTIONS` | (dynamic) | System instructions for LLM context |

For OIDC auth variables, see [Authentication](../guides/authentication.md).

## Volumes

| Path | Purpose |
|------|---------|
| `/data/service` | Your service data (bind-mount or named volume) |
| `/data/state` | State files (FastMCP OIDC state, etc.) |

## UID/GID

Set `PUID` and `PGID` in your `.env` file to match the owner of bind-mounted
directories (default 1000/1000).

# Docker Deployment

## Quick start

```bash
docker run -v scholar-mcp-data:/data/scholar-mcp \
           ghcr.io/pvliesdonk/scholar-mcp:latest
```

The server listens on port 8000 with HTTP transport by default. Add `-e SCHOLAR_MCP_S2_API_KEY=your-key` for higher rate limits (see below).

## Docker Compose

### Basic setup

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp

volumes:
  scholar-mcp-data:
```

### With docling-serve (PDF conversion)

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"
      SCHOLAR_MCP_READ_ONLY: "false"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
      SCHOLAR_MCP_CONTACT_EMAIL: "${SCHOLAR_MCP_CONTACT_EMAIL:-}"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped

volumes:
  scholar-mcp-data:
```

### With Traefik reverse proxy

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    env_file: .env
    volumes:
      - scholar-mcp-data:/data/scholar-mcp
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.scholar-mcp.rule=Host(`scholar-mcp.yourdomain.com`)"
      - "traefik.http.routers.scholar-mcp.tls.certresolver=letsencrypt"
      - "traefik.http.services.scholar-mcp.loadbalancer.server.port=8000"
    networks:
      - traefik

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped
    networks:
      - traefik

volumes:
  scholar-mcp-data:

networks:
  traefik:
    external: true
```

## Environment variables

See [Configuration](../configuration.md) for the full reference. Key variables for Docker:

| Variable | Default | Description |
|---|---|---|
| `SCHOLAR_MCP_S2_API_KEY` | -- | Semantic Scholar API key (optional; ~1 req/s without, ~10 req/s with) |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Cache and PDF storage directory |
| `SCHOLAR_MCP_READ_ONLY` | `true` | Set `false` to enable PDF tools |
| `SCHOLAR_MCP_DOCLING_URL` | -- | docling-serve URL (e.g. `http://docling-serve:5001`) |
| `SCHOLAR_MCP_BEARER_TOKEN` | -- | Bearer token for HTTP auth |
| `FASTMCP_LOG_LEVEL` | `INFO` | Logging level (use `-v` or set to `DEBUG` for verbose output) |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set `false` for structured JSON logging with aggregators |

For OIDC authentication, see [OIDC deployment](oidc.md).

## Volumes

| Container path | Purpose |
|---|---|
| `/data/scholar-mcp` | SQLite cache database, downloaded PDFs, converted Markdown |
| `/data/state` | FastMCP OIDC state (only needed with OIDC auth) |

Use named volumes (shown above) for persistence. Bind mounts also work:

```yaml
volumes:
  - ./data/scholar-mcp:/data/scholar-mcp
```

## UID/GID

The image runs as a non-root user with UID/GID 1000 by default. To match your host user for bind mounts, set build args:

```yaml
services:
  scholar-mcp:
    build:
      context: .
      args:
        APP_UID: 1000
        APP_GID: 1000
```

## Image tags

| Tag | Description |
|---|---|
| `latest` | Latest release |
| `v1.0.1` | Specific version |
| `v1.0` | Latest patch in 1.0.x |
| `v1` | Latest minor in 1.x |

Multi-arch: `linux/amd64` and `linux/arm64`.

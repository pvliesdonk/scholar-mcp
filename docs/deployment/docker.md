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
| `SCHOLAR_MCP_S2_API_KEY` | n/a | Semantic Scholar API key (optional; ~1 req/s without, ~10 req/s with) |
| `SCHOLAR_MCP_CACHE_DIR` | `/data/scholar-mcp` | Cache and PDF storage directory |
| `SCHOLAR_MCP_READ_ONLY` | `true` | Set `false` to enable PDF tools |
| `SCHOLAR_MCP_DOCLING_URL` | n/a | docling-serve URL (e.g. `http://docling-serve:5001`) |
| `SCHOLAR_MCP_BEARER_TOKEN` | n/a | Bearer token for HTTP auth |
| `FASTMCP_LOG_LEVEL` | `INFO` | Logging level (use `-v` or set to `DEBUG` for verbose output) |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set `false` for structured JSON logging with aggregators |
| `SCHOLAR_MCP_INSTRUCTIONS` | (computed at startup) | System instructions for LLM context |
| `SCHOLAR_MCP_DEBUG_PORT` | n/a | Remote-debugger TCP port (see [Remote debugging](#remote-debugging); requires `--build-arg DEBUG=true` image) |
| `SCHOLAR_MCP_DEBUG_WAIT` | `false` | Block startup until IDE attaches (see [Remote debugging](#remote-debugging)) |

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

## Remote debugging

Production images ship without `debugpy` to keep the image lean. To attach a remote Python debugger from VS Code or PyCharm:

1. **Build with the debug extra:**

    ```bash
    docker build --build-arg DEBUG=true -t scholar-mcp:debug .
    ```

    This installs the `[debug]` optional-dependency group (which pulls `debugpy` transitively from `fastmcp-pvl-core`). Default builds (`DEBUG=false`) skip it.

2. **Run with the debug env vars set and the port mapped:**

    ```bash
    docker run --rm \
      -e SCHOLAR_MCP_DEBUG_PORT=5678 \
      -e SCHOLAR_MCP_DEBUG_WAIT=true \
      -p 127.0.0.1:5678:5678 \
      -p 8000:8000 \
      scholar-mcp:debug
    ```

    | Env var | Effect |
    |---------|--------|
    | `SCHOLAR_MCP_DEBUG_PORT` | TCP port the debugger listens on (any value parsing to ``0`` disables; non-numeric or out-of-range values log a WARNING and the listener stays off) |
    | `SCHOLAR_MCP_DEBUG_WAIT` | When truthy (``1``/``true``/``yes``/``on``), block startup until the IDE attaches. Default is non-blocking. |

3. **Attach from VS Code**, adding a launch config:

    ```json
    {
      "name": "Attach to scholar-mcp",
      "type": "debugpy",
      "request": "attach",
      "connect": { "host": "localhost", "port": 5678 }
    }
    ```

    PyCharm uses *Run → Edit Configurations → Python Debug Server* with the same host/port.

!!! danger "Never publish the debug port on a public network"
    The debug listener binds `0.0.0.0` inside the container so the IDE can reach it from the host, but **debugpy's DAP protocol is unauthenticated**: any peer that can reach the port has arbitrary code execution as the server process. Always bind the port mapping to localhost (`-p 127.0.0.1:5678:5678`) or tunnel via `kubectl port-forward` / SSH. Production images should be built with default `DEBUG=false`.

When the helper is invoked but `debugpy` isn't installed (say, someone sets `DEBUG_PORT` on a non-debug image), it logs a WARNING and continues; this is the safe failure mode.


<!-- DOMAIN-DOCKER-EXTRA-START -->
<!-- Project-specific notes for Docker deployment go here; kept across copier
     update. (E.g. "the /data/uploads volume must be writable by UID Y",
     "container needs cap_add: SYS_PTRACE for debugging tools".) -->
<!-- DOMAIN-DOCKER-EXTRA-END -->

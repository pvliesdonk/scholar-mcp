# Docker Deployment

## Quick start

```
cp .env.example .env
docker compose up -d
```

The server listens on port 8000 with HTTP transport, published on the host as `8000:8000`. No reverse proxy, TLS terminator, or external network is assumed.

Copying `.env.example` first is the step to keep. Every variable in it arrives commented out, so the server starts on its defaults and the copy changes no behaviour by itself. It is the file you edit next, and `compose.yml` names it.

Apply a later edit with `docker compose up -d`, which recreates the container with the new values. `docker compose restart` does not pick them up: an env file is read when a container is created, so a restarted container keeps the values it was created with and the edit is ignored without any message.

## Docker Compose

`compose.yml` is a working deployment, not an illustration. It is re-rendered on every `copier update`, so fixes and new defaults reach it; edit it inside the sentinel blocks described below and your changes survive.

### Where configuration goes

The split matters, because two files can set the same variable:

- **`.env` holds the server's configuration.** `compose.yml` reads it with `env_file:`. `.env.example` is generated from the server's own config surface and lists every variable with its default and a one-line description, so it is both the checklist and the place to edit. [Configuration](https://pvliesdonk.github.io/scholar-mcp/unstable/configuration/index.md) carries the full reference.
- **`compose.yml`'s `environment:` block holds only what the file itself determines.** Currently that is `FASTMCP_HOME`, which points at the state volume the file mounts. Values here override `.env`, so a knob set in both places takes the value from `compose.yml`, which is rarely what an operator editing `.env` expects.

The `env_file:` entry is marked `required: false`, so a checkout with no `.env` still starts on defaults. That form needs Compose 2.24.0 or newer; on an older engine, either upgrade or replace the entry with plain `env_file: .env` and make sure the file exists.

### Ports

The image pins its own listener: `CMD` passes `--host 0.0.0.0 --port 8000`, so `SCHOLAR_MCP_HOST` and `SCHOLAR_MCP_PORT` in a `.env` do not move it. To serve on a different host port, change the left-hand side of the mapping (`"9000:8000"`) rather than the server's port.

### Domain content and `copier update`

Four sentinel blocks mark the parts of `compose.yml` a project owns. Content inside them survives a template update; content outside them does not, and will conflict.

| Block                         | For                                                     |
| ----------------------------- | ------------------------------------------------------- |
| `DOMAIN-COMPOSE-VOLUMES`      | Extra mounts on the service                             |
| `DOMAIN-COMPOSE-ENVIRONMENT`  | Extra environment this file determines                  |
| `DOMAIN-COMPOSE-SERVICES`     | Sidecars, such as a task backend or a cache             |
| `DOMAIN-COMPOSE-VOLUME-NAMES` | Top-level declarations for any named volume added above |

A named volume needs an entry in two of those: the mount in `DOMAIN-COMPOSE-VOLUMES`, and its declaration in `DOMAIN-COMPOSE-VOLUME-NAMES`. A bind mount needs only the first.

### Behind a reverse proxy

Proxy configuration is deployment-specific, so `compose.yml` ships none. Add it in a second file rather than by editing `compose.yml`, which is template-owned and re-rendered: save this as `compose.override.yml`, which Compose loads automatically alongside `compose.yml`.

```
services:
  scholar-mcp:
    # `!reset` drops the published port: the proxy reaches the container over
    # the shared network, so nothing needs to be on the host. Plain merging
    # appends to sequences, so without this the port stays published.
    ports: !reset []
    networks:
      - traefik
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.scholar-mcp.rule=Host(`mcp.example.com`)"
      - "traefik.http.routers.scholar-mcp.tls.certresolver=letsencrypt"
      - "traefik.http.services.scholar-mcp.loadbalancer.server.port=8000"

networks:
  traefik:
    external: true
```

`!reset` needs Compose 2.24.4 or newer. On an older engine, drop that line and remove the port mapping from `compose.yml` directly, accepting that the edit conflicts on the next template update.

Check the result before starting anything, since a merge that silently kept the port mapping looks identical until the port clashes:

```
docker compose config
```

Substitute your own hostname for `mcp.example.com`. Set `SCHOLAR_MCP_BASE_URL` to the public URL as well: the server needs it to advertise its own address, and it is required once OIDC is enabled. Do not reach for `SCHOLAR_MCP_HOST` here. That variable is the interface the server binds to, which is not the name the proxy routes.

The network must already exist and be the one the proxy watches. For the same overlay with OIDC, see [OIDC](https://pvliesdonk.github.io/scholar-mcp/unstable/deployment/oidc/index.md).

### Building the image yourself

`compose.yml` pulls a published image rather than building one, so `docker compose up -d` never rebuilds from a stale checkout. To run your own build, build and tag it first:

```
docker build -t ghcr.io/pvliesdonk/scholar-mcp:dev .
```

then point the `image:` line at that tag.

### Health

The service declares a health check that opens a TCP connection to port 8000 inside the container, so `docker compose ps` reports `healthy` once the server is listening. It does not assert that the server is working, because there is no health route to probe. Read it as evidence that the process is up, not that the deployment is good.

## Image tags

| Tag          | Contents                                                     | Updated by                                           |
| ------------ | ------------------------------------------------------------ | ---------------------------------------------------- |
| `latest`     | Newest stable release                                        | Each stable release that is newest across all series |
| `vX.Y.Z`     | That exact release (pre-releases included, as `vX.Y.Z-rc.N`) | Never (immutable)                                    |
| `vX.Y`, `vX` | Newest stable release in that series                         | Each stable release that is newest in its series     |
| `rc`         | Newest release candidate                                     | Each pre-release still ahead of `latest`             |
| `edge`       | Newest commit on `main`                                      | Every merge to `main`                                |

Rolling tags are ordering-aware: a patch release cut from an old `release/X.Y` branch after a newer stable has shipped updates its own series tags but never `latest`. The same rule governs `rc`: a candidate only moves the tag while its version is still ahead of the newest stable, so a candidate for an already-released version never pulls `rc` behind `latest`.

The three rolling tags answer different questions. Use `latest` to run released code, `rc` to test the candidate for the next release, and `edge` to run the newest merged commit. Note that `rc` is not cleared when its release ships: it keeps pointing at the last candidate until the next one is cut, so `latest` is the tag to follow in production. To find the commit behind an `edge` image, read its `org.opencontainers.image.revision` label:

```
docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
  ghcr.io/pvliesdonk/scholar-mcp:edge
```

## Environment variables

See [Configuration](https://pvliesdonk.github.io/scholar-mcp/unstable/configuration/index.md) for the full reference. Key variables for Docker:

| Variable                           | Default               | Description                                                                                                   |
| ---------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------- |
| `SCHOLAR_MCP_S2_API_KEY`           | n/a                   | Semantic Scholar API key (optional; ~1 req/s without, ~10 req/s with)                                         |
| `SCHOLAR_MCP_CACHE_DIR`            | `/data/scholar-mcp`   | Cache and PDF storage directory                                                                               |
| `SCHOLAR_MCP_READ_ONLY`            | `true`                | Set `false` to enable PDF tools                                                                               |
| `SCHOLAR_MCP_DOCLING_URL`          | n/a                   | docling-serve URL (such as `http://docling-serve:5001`)                                                       |
| `SCHOLAR_MCP_BEARER_TOKEN`         | n/a                   | Bearer token for HTTP auth                                                                                    |
| `FASTMCP_LOG_LEVEL`                | `INFO`                | Logging level (use `-v` or set to `DEBUG` for verbose output)                                                 |
| `FASTMCP_ENABLE_RICH_LOGGING`      | `true`                | Set `false` for structured JSON logging with aggregators                                                      |
| `SCHOLAR_MCP_INSTANCE_DESCRIPTION` | n/a                   | Routing context that distinguishes this deployment                                                            |
| `SCHOLAR_MCP_INSTRUCTIONS_EXTRA`   | n/a                   | Deployment-specific behavioral policy added to the generated MCP instructions                                 |
| `SCHOLAR_MCP_INSTRUCTIONS`         | (computed at startup) | Legacy full replacement of the generated instructions (deprecated)                                            |
| `SCHOLAR_MCP_DEBUG_PORT`           | n/a                   | Remote-debugger TCP port (see [Remote debugging](#remote-debugging); requires `--build-arg DEBUG=true` image) |
| `SCHOLAR_MCP_DEBUG_WAIT`           | `false`               | Block startup until IDE attaches (see [Remote debugging](#remote-debugging))                                  |

For OIDC authentication, see [OIDC deployment](https://pvliesdonk.github.io/scholar-mcp/unstable/deployment/oidc/index.md).

Running behind a reverse proxy on a path prefix (`https://mcp.example.com/myservice/mcp`) rather than its own hostname needs two routing rules, one of which sits outside the prefix: see [Subpath Deployments](https://pvliesdonk.github.io/scholar-mcp/unstable/deployment/oidc/#subpath-deployments).

## Volumes

| Container path      | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| `/data/scholar-mcp` | SQLite cache database, downloaded PDFs, converted Markdown |
| `/data/state`       | FastMCP OIDC state (only needed with OIDC auth)            |

Use named volumes (shown above) for persistence. Bind mounts also work:

```
volumes:
  - ./data/scholar-mcp:/data/scholar-mcp
```

## UID/GID

The image runs as a non-root user with UID/GID 1000 by default. To match your host user for bind mounts, set build args:

```
services:
  scholar-mcp:
    build:
      context: .
      args:
        APP_UID: 1000
        APP_GID: 1000
```

## Remote debugging

Production images ship without `debugpy` to keep the image lean. To attach a remote Python debugger from VS Code or PyCharm:

1. **Build with the debug extra:**

   ```
   docker build --build-arg DEBUG=true -t scholar-mcp:debug .
   ```

   This installs the `[debug]` optional-dependency group (which pulls `debugpy` transitively from `fastmcp-pvl-core`). Default builds (`DEBUG=false`) skip it.

1. **Run with the debug env vars set and the port mapped:**

   ```
   docker run --rm \
     -e SCHOLAR_MCP_DEBUG_PORT=5678 \
     -e SCHOLAR_MCP_DEBUG_WAIT=true \
     -p 127.0.0.1:5678:5678 \
     -p 8000:8000 \
     scholar-mcp:debug
   ```

   | Env var                  | Effect                                                                                                                                            |
   | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `SCHOLAR_MCP_DEBUG_PORT` | TCP port the debugger listens on (any value parsing to `0` disables; non-numeric or out-of-range values log a WARNING and the listener stays off) |
   | `SCHOLAR_MCP_DEBUG_WAIT` | When truthy (`1`/`true`/`yes`/`on`), block startup until the IDE attaches. Default is non-blocking.                                               |

1. **Attach from VS Code**, adding a launch config:

   ```
   {
     "name": "Attach to scholar-mcp",
     "type": "debugpy",
     "request": "attach",
     "connect": { "host": "localhost", "port": 5678 }
   }
   ```

   PyCharm uses *Run → Edit Configurations → Python Debug Server* with the same host/port.

Never publish the debug port on a public network

The debug listener binds `0.0.0.0` inside the container so the IDE can reach it from the host, but **debugpy's DAP protocol is unauthenticated**: any peer that can reach the port has arbitrary code execution as the server process. Always bind the port mapping to localhost (`-p 127.0.0.1:5678:5678`) or tunnel via `kubectl port-forward` / SSH. Production images should be built with default `DEBUG=false`.

When the helper is invoked but `debugpy` isn't installed (say, someone sets `DEBUG_PORT` on a non-debug image), it logs a WARNING and continues; this is the safe failure mode.

## The cache volume

`compose.yml` mounts a third named volume, `cache-data`, at `/data/scholar-mcp`. That path is the default of `SCHOLAR_MCP_CACHE_DIR`, which holds the SQLite cache database and every downloaded PDF and converted Markdown file. It is neither of the two volumes the template mounts, so without that entry the cache would sit in the container's writable layer and vanish on the next `docker compose up -d`. Point `SCHOLAR_MCP_CACHE_DIR` somewhere else and the mount has to move with it.

## Running docling-serve alongside

PDF conversion is off unless `SCHOLAR_MCP_DOCLING_URL` names a reachable [docling-serve](https://github.com/docling-project/docling-serve). The sidecar is optional, and heavy, so `compose.yml` does not ship it. Add it in `compose.override.yml`, which Compose loads automatically:

```
services:
  scholar-mcp:
    environment:
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"

  docling-serve:
    image: ghcr.io/ds4sd/docling-serve:latest
    restart: unless-stopped
```

Values in `environment:` override `.env`, so set the URL in one place, not both. Conversion also writes to the cache, which the read-only default forbids: set `SCHOLAR_MCP_READ_ONLY=false` in `.env` to expose the write-tagged tools that populate it.

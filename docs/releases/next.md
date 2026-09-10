# Next release

<!-- notes-range-end: cd380bc40f4d61498c6fec85c555c565c8d4f2da -->

<!-- RELEASE-SUMMARY NEXT START -->
Scholar MCP moves to FastMCP 4 and adopts three majors of the shared server template it is generated from. Container operators have work to do: the image now serves on a fixed port 8000, and the shipped `compose.yml` no longer carries reverse-proxy configuration. What arrives in exchange is a compose file that runs as shipped and, for the first time, keeps the cache it downloads.
<!-- RELEASE-SUMMARY NEXT END -->

## The container's port is fixed at 8000

The image's start command now pins `--port 8000`. Inside a container, `SCHOLAR_MCP_PORT` no longer reaches the server.

This is the one change that can break a working deployment quietly. The problem it settles, [as #342 put it](https://github.com/pvliesdonk/scholar-mcp/issues/342), is that "a container run with `-e SCHOLAR_MCP_PORT=9000 -p 9000:9000` serves 8000 behind a mapping to a closed port, with no error." The variable moved the server, the port mapping did not follow it, and nothing complained.

The behaviour was verified against the built image in [#360](https://github.com/pvliesdonk/scholar-mcp/pull/360):

| Container | host→8000 | host→9000 |
|---|---|---|
| default | `400` on a bare `GET /mcp`, so the port is live | not mapped |
| `-e SCHOLAR_MCP_PORT=9000` | `400` | `000`, connection refused |

With the variable set, the container still logs `Uvicorn running on http://0.0.0.0:8000`.

Express a custom port as the host side of the mapping instead, as in `-p 9000:8000`, and leave the right-hand side alone. Outside a container, on a systemd unit or a plain `scholar-mcp serve`, the variable is untouched and still works.

## A compose file that runs as shipped, and keeps its cache

`compose.yml` was an illustration. It is now a deployment, and three things follow from that.

**The cache survives a restart.** `SCHOLAR_MCP_CACHE_DIR` defaults to `/data/scholar-mcp`, and the compose file mounted neither that path nor anything containing it. The SQLite cache database and every downloaded PDF and converted Markdown file lived in the container's writable layer, so `docker compose up -d` discarded them. A `cache-data` volume now mounts that path ([#360](https://github.com/pvliesdonk/scholar-mcp/pull/360)). Nothing regresses, since the data was already being lost, but a deployment that followed the old documented example with a `scholar-mcp-data` volume will find the new one empty on first start.

**The reverse-proxy configuration is gone, deliberately.** The file used to ship Traefik labels that never worked: it declared no `networks:` stanza, so the service sat on the compose project's default network and the proxy had no route to it. Proxy setup is now an overlay you supply, and `docs/deployment/docker.md` carries a Traefik `compose.override.yml` to copy. That overlay needs one line most people would omit, `ports: !reset []`, because Compose appends to sequences rather than replacing them. Without it the service joins the proxy network and keeps publishing 8000 as well.

**Port 8000 is published on the host,** where previously nothing was. A health check is new too. Every 30 seconds it opens a TCP connection to port 8000 inside the container, which is evidence that the process is listening and nothing more. No health route exists to probe, so it says nothing about whether the deployment is good.

Two version floors come with this. The `env_file` entry is marked `required: false`, so a checkout with no `.env` still starts on defaults; that form needs Compose 2.24.0 or newer. The `!reset` in the proxy overlay needs 2.24.4.

`build: .` is gone as well. The file pulls the published image, so `docker compose up -d` can no longer rebuild from a stale checkout.

## Instructions the model reads now match the deployment

The text an MCP client receives on connect was one flat paragraph. It is now composed from contributions that each carry a role, rendered in a fixed order: identity, then operator routing, then instance facts, policy, capabilities, workflows, and a documentation pointer ([pvl-core#301](https://github.com/pvliesdonk/fastmcp-pvl-core/pull/301), adopted in [#359](https://github.com/pvliesdonk/scholar-mcp/pull/359)).

Two consequences are visible to anyone running the server.

A read-only instance no longer reads about tools it cannot call. The paragraph describing the cache-populating tools is registered with `requires_tools`, naming `fetch_paper_pdf`, `convert_pdf_to_markdown`, `fetch_and_convert` and `fetch_pdf_by_url`. When `SCHOLAR_MCP_READ_ONLY` hides those tools, the paragraph is dropped with them.

The old text also ended with a sentence addressed to operators, asking them to set `SCHOLAR_MCP_INSTRUCTIONS`, that was delivered to the language model instead. The model could act on none of it. That sentence is gone.

Two new optional variables replace it, splitting what used to be a single override:

| Variable | For |
|---|---|
| `SCHOLAR_MCP_INSTANCE_DESCRIPTION` | Routing context: what distinguishes this deployment's material or responsibility |
| `SCHOLAR_MCP_INSTRUCTIONS_EXTRA` | Behavioural policy specific to this deployment |

Both default to empty, and neither is required. `SCHOLAR_MCP_INSTRUCTIONS` still replaces the generated text outright, so nothing an operator set before needs changing, but it now logs a deprecation warning naming the two additive variables it suppresses.

## One generated configuration reference

`docs/configuration.md` was a hand-written table that had drifted from the code it described. Every row is now generated from the field metadata in `config.py`, and a completeness check fails the build when a variable lands in no section, so the two cannot separate again ([#340](https://github.com/pvliesdonk/scholar-mcp/issues/340), [#358](https://github.com/pvliesdonk/scholar-mcp/pull/358)). The README keeps a curated five-row table of the variables worth meeting first (`SCHOLAR_MCP_READ_ONLY`, `SCHOLAR_MCP_S2_API_KEY`, `SCHOLAR_MCP_DOCLING_URL`, `SCHOLAR_MCP_CACHE_DIR` and `SCHOLAR_MCP_CONTACT_EMAIL`) and points at the reference for the rest. The EPO OPS registration walkthrough, the cache TTLs and the rate-limiting prose moved onto that page.

The same field metadata drives two install surfaces. Five credentials that were not previously flagged are now marked as secrets in `server.json`, so the MCP registry's install screen masks them. They are `SCHOLAR_MCP_S2_API_KEY`, `SCHOLAR_MCP_VLM_API_KEY`, `SCHOLAR_MCP_EPO_CONSUMER_SECRET`, `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY` and `SCHOLAR_GITHUB_TOKEN`.

The guided-setup wizard also gained a fix it had been missing since its output became generated. A field whose value is a file path now emits the `-v` mount alongside the `-e` variable. For this server that is `SCHOLAR_MCP_BEARER_TOKENS_FILE`, whose generated `docker run` previously named a path the container could not read ([template#569](https://github.com/pvliesdonk/fastmcp-server-template/pull/569)).

## FastMCP 4, and which clients get a job handle

The floor moves to FastMCP 4 and `fastmcp-pvl-core` 7, with MCP SDK 2. Long-running tools keep their two paths, and which path a client takes now depends on what that client negotiates.

A client that does not advertise the SEP-2663 tasks extension, which is most MCP clients today, is unaffected. A tool whose work outlives `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` still hands back a job handle to poll with `get_job_result`.

A client that does advertise it now gets native background-task execution instead, with the task backend owning the lifecycle. FastMCP's own `Client` advertises the extension by default, so proxies, scripts and test harnesses built on it take the native path and block for the tool's full duration rather than receiving a handle ([#360](https://github.com/pvliesdonk/scholar-mcp/pull/360)).

No tool was added, removed or renamed, and no documented tool behaviour changed.

## Upgrading

The public import surface is unchanged, `requires-python` stays at 3.11, no environment variable was removed, and no default changed. The systemd unit and `packaging/env.example` are untouched, so a package or `pip` install needs only the last two steps below.

For a container deployment, in order:

1. **Check your Compose version.** `docker compose version` must report 2.24.0 or newer, or 2.24.4 if you will use the proxy overlay. On an older engine, replace the `env_file:` block with plain `env_file: .env` and make sure the file exists.
2. **Remove `SCHOLAR_MCP_PORT` from any `.env` a container reads.** It is ignored there now.
3. **Re-express a custom port as the host side of the mapping,** as `-p 9000:8000` or `ports: - "9000:8000"`. Never change the right-hand side.
4. **Recreate your reverse-proxy routing yourself.** Copy the overlay from [Docker deployment](../deployment/docker.md) into `compose.override.yml`, keep the `ports: !reset []` line, and check the result with `docker compose config` before starting anything.
5. **If `SCHOLAR_MCP_HOST` held a public hostname** for the old Traefik router rule, put that hostname in your overlay's `Host(...)` rule and set `SCHOLAR_MCP_BASE_URL` to the public URL. Reset `SCHOLAR_MCP_HOST` to a bind address or drop the line: it is the interface the server binds to, and a name that does not resolve locally now fails startup.
6. **If you built from `compose.yml`,** build and tag explicitly with `docker build -t ghcr.io/pvliesdonk/scholar-mcp:dev .`, then point `image:` at that tag.
7. **Move any hand edits to `compose.yml`** into the `DOMAIN-COMPOSE-VOLUMES`, `-ENVIRONMENT`, `-SERVICES` and `-VOLUME-NAMES` blocks, where they survive future template updates. A named volume needs two entries: the mount, and its top-level declaration.
8. **Apply changes with `docker compose up -d`, not `docker compose restart`.** An environment file is read when a container is created, so a restarted container keeps the values it was created with and the edit is ignored without any message.

For every deployment:

9. **Python consumers** should relax any pin below `fastmcp-pvl-core` 7 or FastMCP 4. Installing alongside FastMCP 3, or `fastmcp-pvl-core` 4 through 6, no longer resolves.
10. **If you track `.env`,** two optional variables were added and none removed. Nothing must be set.

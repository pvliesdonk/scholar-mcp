# MCP File Exchange

Scholar MCP participates in the **MCP File Exchange** convention
— a lightweight, spec-defined way for co-deployed MCP servers to pass
files to each other by reference instead of by base64-in-context.

The full specification lives in `fastmcp-pvl-core`'s docs:
[`docs/specs/file-exchange.md`](https://github.com/pvliesdonk/fastmcp-pvl-core/blob/main/docs/specs/file-exchange.md).
This page is the project-side guide: **what's wired by default, which
env vars to set, and how to publish, consume, or accept agent-uploaded
`FileRef` objects from your tool bodies.**

## What's wired by default

`make_server()` calls `register_file_exchange()` once during startup.
That single call:

1. Mounts an `/artifacts/{token}` HTTP route (HTTP transport only).
2. Advertises the `experimental.file_exchange` capability on the MCP
   `initialize` response.
3. Registers two MCP tools when the surrounding env permits:
    - `create_download_link` — producer-side; mints time-limited HTTP
      URLs for `FileRef`s this server has published.
    - `fetch_file` — consumer-side; resolves a `FileRef` (via
      `exchange://` or `https://`) and hands the bytes to your sink.

By default the feature is **on** for HTTP/SSE deployments and **off**
for stdio. See [Configuration → MCP File Exchange](../configuration.md#mcp-file-exchange)
for the env-var matrix.

The **upload direction** is opt-in and not wired by default — see
[Uploading files](#uploading-files-receiver) below for the
`register_file_exchange_upload(...)` pattern.

## The two patterns

### Augmented response (recommended)

The tool returns its normal output plus a `file_ref` field. Existing
clients ignore the field and keep working; file-exchange-aware
clients can use it.

```python
from fastmcp_pvl_core import FileRefPreview

result = await handle.publish(
    source=image_bytes,
    mime_type="image/png",
    preview=FileRefPreview(description=prompt, dimensions=(width, height)),
)
return {
    "image_id": image_id,
    "prompt": prompt,
    "dimensions": {"width": width, "height": height},
    "file_ref": result.to_dict(),
}
```

### Reference-only

The tool returns just the `FileRef` — appropriate when the file is
large and you do not want to spend tokens on inline data:

```python
file_ref = await handle.publish(source=pdf_path, mime_type="application/pdf")
return file_ref.to_dict()
```

## Producing files (`handle.publish`)

`register_file_exchange` returns a `FileExchangeHandle`. Capture it
in `make_server()` and stash it where your tool bodies can reach it.
The simplest pattern is a module-level singleton in `server.py` —
this stays well-typed under `mypy --strict` (the alternative,
attaching to the `FastMCP` instance, fails `attr-defined` because
`FastMCP` does not declare a `file_exchange` field):

```python
# server.py
from fastmcp_pvl_core import FileExchangeHandle, register_file_exchange

_file_exchange: FileExchangeHandle | None = None


def get_file_exchange() -> FileExchangeHandle:
    """Return the registered handle. Raises if make_server has not run."""
    if _file_exchange is None:
        raise RuntimeError("file exchange is not initialised — call make_server first")
    return _file_exchange


def make_server(*, transport: str = "stdio", ...) -> FastMCP:
    global _file_exchange
    ...
    _file_exchange = register_file_exchange(
        mcp,
        namespace="scholar-mcp",
        env_prefix=_ENV_PREFIX,
        transport="auto",
        produces=("image/png", "image/webp"),
    )
    return mcp
```

Then in a tool body:

```python
from fastmcp_pvl_core import FileRefPreview

from scholar_mcp.server import get_file_exchange


@mcp.tool
async def render(prompt: str) -> dict[str, Any]:
    image_bytes = await _render(prompt)
    file_ref = await get_file_exchange().publish(
        source=image_bytes,
        mime_type="image/png",
        preview=FileRefPreview(description=prompt),
    )
    return {"prompt": prompt, "file_ref": file_ref.to_dict()}
```

`publish()` returns a `FileRef`. Call `.to_dict()` (or let your
return type adapter serialise it) before sending it back through MCP.

## Consuming files (`consumer_sink`)

Pass a `consumer_sink` to enable the `fetch_file` tool. The sink
receives the resolved bytes and a `FetchContext`, and returns a
`FetchResult`:

```python
from fastmcp_pvl_core import FetchContext, FetchResult

async def _store_in_vault(data: bytes, ctx: FetchContext) -> FetchResult:
    path = await _vault.write(data, mime_type=ctx.mime_type, name=ctx.suggested_filename)
    return FetchResult(stored_at=str(path), bytes_written=len(data))

# Consume-only servers do not need to capture the handle — the facade
# wires `fetch_file` itself; the handle is only required to call
# `.publish()` from a tool body (see "Producing files" above).
register_file_exchange(
    mcp,
    namespace="scholar-mcp",
    env_prefix=_ENV_PREFIX,
    transport="auto",
    consumes=("image/*", "application/pdf"),
    consumer_sink=_store_in_vault,
)
```

`consumes=` is advertised in the capability declaration; the LLM and
peer servers use it to pick a destination for `fetch_file` calls.

## Uploading files (`receiver=`)

The download direction is producer-driven: this server `publish()`es
a file, and a peer (or LLM tool) fetches it. The **upload direction**
is the inverse — an agent or peer pushes bytes into this server, and
a **receiver** in your code commits them.

Wire it by uncommenting the `register_file_exchange_upload(...)`
block in `src/scholar_mcp/server.py` (inside the
`DOMAIN-FILE-EXCHANGE-START / END` sentinel) and supplying a
`receiver`:

```python
from typing import Any

from fastmcp_pvl_core import UploadRecord, register_file_exchange_upload


# _vault is illustrative — replace with your domain's storage helper.
def _upload_receiver(record: UploadRecord, body: bytes) -> dict[str, Any]:
    # record.target_id, record.extra, record.max_bytes available.
    path = _vault.write(record.target_id, body)
    return {"path": str(path), "size_bytes": len(body)}

register_file_exchange_upload(
    mcp,
    namespace="scholar-mcp",
    env_prefix=_ENV_PREFIX,
    receiver=_upload_receiver,
)
```

Once registered, an LLM-visible `create_upload_link` tool appears.
The agent calls it with a `target_id` (and optional `extra`,
`ttl_seconds`, `max_bytes`); the helper mints a one-time HTTPS
`POST /<namespace>/uploads/{token}` URL and returns it. The agent
POSTs the bytes; the route hands them to your receiver.

### Pre-link validation

To reject bad `target_id`s **before** the token is minted — so an LLM
sees a clean tool error rather than wastes a round-trip — supply
`pre_link_validator`:

```python
def _validate_upload_target(target_id: str, extra: dict[str, Any] | None) -> None:
    if not target_id.startswith("inbox/"):
        raise ValueError(f"target_id must begin with 'inbox/': {target_id}")

register_file_exchange_upload(
    mcp,
    namespace="scholar-mcp",
    env_prefix=_ENV_PREFIX,
    receiver=_upload_receiver,
    pre_link_validator=_validate_upload_target,
)
```

Raising `ValueError` surfaces the message verbatim to the caller.
Other exceptions also propagate but are logged at ERROR with a
`non-ValueError` marker so operators distinguish bugs from
caller-input errors. Sync validators run in `asyncio.to_thread`
automatically; `async def` validators run on the loop.

### Receiver error contract

The receiver runs **after** route-level checks pass. Oversized bodies
(over `UPLOAD_MAX_BYTES`) return `413` and expired or already-consumed
tokens return `404` before the receiver is invoked. Once the receiver
runs, exceptions translate to status codes as follows:

| Exception | Response | When to use |
|-----------|----------|-------------|
| `ValueError` | `400` Bad Request | Request body fails domain validation. |
| `FileExistsError` | `409` Conflict | `target_id` collides with existing data. |
| Anything else | `500` Internal Server Error | Server-side bug. Traceback is logged. |

For `400` and `409`, the exception's `str(exc)` becomes the response
body — frame those messages as caller-facing diagnostics. The `500`
path returns a generic body and logs the traceback server-side. A
returned `dict[str, Any]` produces `200` and is JSON-encoded into the
response; non-dict returns are treated as receiver bugs (`500` with a
WARNING log). Sync receivers run in `asyncio.to_thread` (blocking I/O
does not stall the loop); `async def` receivers run on the loop.

Tokens are **one-time** — every non-2xx response burns the link;
retries call `create_upload_link` again. For uploads too large to
buffer, use `stream_receiver=` (`AsyncIterator[bytes]` shape; **`async
def` only** — sync stream receivers cannot iterate the body).
Documented in the upstream `fastmcp-pvl-core` README — the template
scaffolds the buffered shape only.

See [Configuration → MCP File Exchange](../configuration.md#mcp-file-exchange)
for the env-var matrix.

## Co-deploying two servers (docker-compose)

The `exchange://` transfer method requires both servers to share a
volume mounted at `MCP_EXCHANGE_DIR`. Example:

```yaml
services:
  image-mcp:
    image: ghcr.io/example/image-mcp:latest
    environment:
      IMAGE_MCP_TRANSPORT: http
      IMAGE_MCP_BASE_URL: https://mcp.example.com/image
      MCP_EXCHANGE_DIR: /var/lib/mcp-exchange
    volumes:
      - mcp-exchange:/var/lib/mcp-exchange

  vault-mcp:
    image: ghcr.io/example/vault-mcp:latest
    environment:
      VAULT_MCP_TRANSPORT: http
      VAULT_MCP_BASE_URL: https://mcp.example.com/vault
      MCP_EXCHANGE_DIR: /var/lib/mcp-exchange
    volumes:
      - mcp-exchange:/var/lib/mcp-exchange

volumes:
  mcp-exchange:
```

Both containers see the same `.exchange-id` file, so they agree on
the exchange group automatically. When `image-mcp` publishes a file,
`vault-mcp` can fetch it via the `exchange://` URI without an HTTP
round-trip — the bytes never leave the shared volume.

When the servers are deployed apart (no shared volume), the spec's
`http` transfer method handles it: peers call `create_download_link`
on the producer, get a time-limited HTTPS URL, and pull the bytes
across the network.

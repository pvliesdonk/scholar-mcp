# Service lifecycle and the template shape

## Decision

`server.py`, `cli.py` and `_server_deps.py` are the template's files. Outside
their sentinel blocks they stay identical to the render of the pinned template
version; scholar's code lives only inside `DOMAIN-WIRING`, `DOMAIN-UPSTREAM` and
`DOMAIN-COMMANDS`, and in the seeded modules the template expects to exist
(`domain.py`, `tools.py`, `resources.py`, `prompts.py`).

## The service

`domain.Service` owns every upstream client, the SQLite cache, the standards
client, the enrichment pipeline and the Semantic Scholar keepalive task. The
template's `server_lifespan` constructs it with no arguments, awaits
`start()`, yields it under the `"service"` key, and awaits `stop()` on
shutdown. Tools resolve it with `Depends(get_service)`.

The keepalive and S2 request pacing depend on the external behaviour recorded
in [the Semantic Scholar API reference](reference/semantic-scholar-api.md).
The Google Books enrichment client depends on
[the Google Books volume-search reference](reference/google-books-api.md).

`start()` builds each resource inside a `contextlib.AsyncExitStack` and
registers that resource's cleanup immediately after constructing it, then
detaches the stack with `pop_all()` as its last statement. A failure part-way
through startup therefore unwinds everything built so far (#230); `stop()`
closes the detached stack in reverse order, and a second `stop()` is a no-op.

Tests that need a service without a lifespan construct `Service(config)` and
assign its collaborators directly (`tests/conftest.py`, `service` fixture).

## Consequences of the template shape

- `register_tools(mcp)` builds `Jobs` from the environment, so a
  `ProjectConfig` passed to `make_server` governs the task backend but not the
  jobs subsystem. The upstream request for a config passthrough is
  pvliesdonk/fastmcp-server-template#534.
- The CLI's `serve` is the template's: a `ConfigurationError` at startup
  surfaces as a traceback rather than a one-line message.
- `scholar_mcp.server.build_event_store` is pvl-core's helper, re-exported
  under the same name: its signature is `(env_prefix, config)`, not this
  project's former zero-argument wrapper. That wrapper and the
  `_resolve_auth_mode` / `_build_*_auth` compat shims are gone, so a
  downstream caller of the old shapes breaks. This is why the adoption ships
  as a breaking release rather than carrying a compatibility layer the
  template does not have.
- The packaged systemd unit sets no bind host and `packaging/env.example` is
  fully commented; `docs/deployment/systemd.md` tells the operator to set
  `SCHOLAR_MCP_CACHE_DIR` and `SCHOLAR_MCP_HOST` in `/etc/scholar-mcp/env`.

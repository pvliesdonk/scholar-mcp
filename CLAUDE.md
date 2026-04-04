# fastmcp-server-template

FastMCP server scaffold. See [TEMPLATE.md](TEMPLATE.md) for customisation guide.

## Project Structure

```
src/fastmcp_server_template/
  mcp_server.py        -- FastMCP server factory + auth wiring (don't modify)
  config.py            -- env var loading; add domain config fields here
  cli.py               -- CLI entry point (serve command)
  _server_deps.py      -- lifespan + Depends() DI; replace placeholder service
  _server_tools.py     -- MCP tools; replace example tools with domain tools
  _server_resources.py -- MCP resources; add domain resources here
  _server_prompts.py   -- MCP prompts; add domain prompts here
```

## Conventions

- Python 3.11+
- `uv` for package management, `ruff` for linting/formatting (line length 88)
- `hatchling` build backend
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Google-style docstrings on all public functions
- `logging.getLogger(__name__)` throughout, no `print()`
- Type hints everywhere

## Key Patterns

- Library is sync; MCP layer uses `asyncio.to_thread()` for blocking calls
- Write tools tagged `tags={"write"}`, hidden via `mcp.disable(tags={"write"})` in read-only mode
- Auth: `_build_bearer_auth()` + `_build_oidc_auth()` called in `create_server()`; MultiAuth when both set
- `_ENV_PREFIX` in `config.py` controls all env var names — change once, affects everything

# scholar-mcp

FastMCP server scaffold. See [TEMPLATE.md](TEMPLATE.md) for customisation guide.

## Project Structure

```
src/scholar_mcp/
  mcp_server.py        -- FastMCP server factory + auth wiring (don't modify)
  config.py            -- env var loading; add domain config fields here
  cli.py               -- CLI entry point (serve command)
  _server_deps.py      -- lifespan + Depends() DI; ServiceBundle holds all services
  _server_tools.py     -- MCP tools; dispatches to category modules
  _server_resources.py -- MCP resources; add domain resources here
  _server_prompts.py   -- MCP prompts; add domain prompts here
  _task_queue.py       -- In-memory task queue for background async operations
  _rate_limiter.py     -- Rate limiter, retry, try-once + RateLimitedError
```

## Conventions

- Python 3.11+
- `uv` for package management, `ruff` for linting/formatting (line length 88)
- `hatchling` build backend
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Google-style docstrings on all public functions
- `logging.getLogger(__name__)` throughout, no `print()`
- Type hints everywhere

## Documentation

- `README.md` and `docs/**` must be kept up to date with any user-facing changes (new tools, config options, CLI flags, deployment changes, etc.)
- Update docs in the same PR as the code change

## Key Patterns

- Library is sync; MCP layer uses `asyncio.to_thread()` for blocking calls
- Write tools tagged `tags={"write"}`, hidden via `mcp.disable(tags={"write"})` in read-only mode
- All tools have MCP annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint`)
- Auth: `_build_bearer_auth()` + `_build_oidc_auth()` called in `create_server()`; MultiAuth when both set
- `_ENV_PREFIX` in `config.py` controls all env var names — change once, affects everything
- **Async task queue**: S2 tools try once (`retry=False`); on 429 `RateLimitedError`, queue with retries for background execution. PDF tools always queue (unless cache hit). `TaskQueue` lives in `ServiceBundle.tasks`.
- **Tool queueing pattern**: extract tool logic into `async def _execute(*, retry=True) -> str`, try with `retry=False`, catch `RateLimitedError` and `bundle.tasks.submit(_execute(retry=True))`

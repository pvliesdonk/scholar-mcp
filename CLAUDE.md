# scholar-mcp

FastMCP server scaffold. See [TEMPLATE.md](TEMPLATE.md) for customisation guide.

## Project Structure

```
src/scholar_mcp/
  server.py            -- FastMCP server factory (make_server) + auth wiring
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
- `logging.getLogger(__name__)` throughout, no `print()` — see **Logging Standard** below
- Type hints everywhere

## Documentation

- `README.md` and `docs/**` must be kept up to date with any user-facing changes (new tools, config options, CLI flags, deployment changes, etc.)
- Update docs in the same PR as the code change

## Hard PR Acceptance Gates

Every PR must pass **all** of the following before merge. Do not open or push a PR until these are green locally:

1. **CI passes** — `uv run pytest -x -q` all tests pass
2. **Lint passes** — run in this exact order: `uv run ruff check --fix .` then `uv run ruff format .` then verify with `uv run ruff format --check .`. Always run format *after* check --fix because check --fix can leave files needing reformatting.
3. **Type-check passes** — `uv run mypy src/` reports no errors
4. **Patch coverage ≥ 80%** — Codecov measures only lines added/changed in the PR diff. Run `uv run pytest --cov=<changed_module> --cov-report=term-missing` and verify new code is exercised. Add tests for every uncovered branch before pushing.
5. **Docs updated** — `README.md` and `docs/**` reflect any user-facing changes in the same commit. Includes `.claude-plugin/plugin/README.md` and `docs/guides/claude-code-plugin.md` when plugin-related.
6. **Manifest version lockstep** — `server.json`, `.claude-plugin/plugin/.claude-plugin/plugin.json`, and `.claude-plugin/plugin/.mcp.json` must carry the same version. The release workflow bumps all three atomically.

## GitHub Review Types

GitHub has two distinct review mechanisms — **both must be read and addressed**:

- **Inline review comments** (`get_review_comments`): attached to specific lines of the diff. Appear in the "Files changed" tab. Use `get_review_comments` to fetch these.
- **PR-level comments** (`get_comments`): posted on the Conversation tab, not tied to a line. Review summary posts, bot analysis, and blocking issues are often posted here. Use `get_comments` to fetch these.

Always fetch both before declaring a review round complete.

## Key Patterns

- Library is sync; MCP layer uses `asyncio.to_thread()` for blocking calls
- Write tools tagged `tags={"write"}`, hidden via `mcp.disable(tags={"write"})` in read-only mode
- All tools have MCP annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint`)
- Auth: `_build_bearer_auth()` + `_build_oidc_auth()` called in `make_server()`; MultiAuth when both set
- `_ENV_PREFIX` in `config.py` controls all env var names — change once, affects everything
- **Async task queue**: S2 tools try once (`retry=False`); on 429 `RateLimitedError`, queue with retries for background execution. PDF tools always queue (unless cache hit). `TaskQueue` lives in `ServiceBundle.tasks`.
- **Tool queueing pattern**: extract tool logic into `async def _execute(*, retry=True) -> str`, try with `retry=False`, catch `RateLimitedError` and `bundle.tasks.submit(_execute(retry=True))`

## Logging Standard

### Framework
- Standard library `logging` throughout. Every module: `logger = logging.getLogger(__name__)`.
- No `print()` for operational output. No third-party logging libraries.
- FastMCP middleware handles tool invocation, timing, and error logging automatically.
- All logging goes through FastMCP's `configure_logging()` for uniform output. `FASTMCP_LOG_LEVEL` is the single log level control; the `-v` CLI flag sets it to `DEBUG`. `FASTMCP_ENABLE_RICH_LOGGING=false` switches to plain/JSON output.

### Log Levels
| Level | Use for |
|-------|---------|
| `DEBUG` | Detailed internals: cache hits, parameter values, enrichment attempts, rate-limit queueing |
| `INFO` | Significant operations: service startup, configuration decisions (tool calls logged by middleware) |
| `WARNING` | Degraded but continuing: API errors with fallback, missing optional config, unexpected data |
| `ERROR` | Failures affecting the primary result. Use `logger.error(..., exc_info=True)` when traceback is needed |

### Exception Handling
- All exceptions must be caught and handled. No bare `except:`. Always specify the exception type.
- Expected errors (HTTP 4xx, rate limits, missing data): catch, log, return user-facing error string.
- Optional enrichment failures (OpenAlex, Unpaywall): catch, log at `DEBUG` with `exc_info=True`, continue.
- Primary result errors: catch, log at `WARNING` or `ERROR`, return error string.
- `ErrorHandlingMiddleware` is a safety net. If it catches something, that's a bug to fix.

### Message Format
- Pseudo-structured: `logger.info("event_name key=%s", value)`
- Event name as first token (snake_case), then key=value pairs via `%s` formatting.
- Never use f-strings in log calls (defeats lazy evaluation).

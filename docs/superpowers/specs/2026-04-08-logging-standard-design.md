# Logging Standard Design

## Problem

The codebase lacks centralized tool invocation logging, has no documented logging
standard, and the documentation understates current practices. While the code is
already consistent (stdlib `logging`, `getLogger(__name__)` in all 24 modules, no
bare `except:`), there is no specification governing log levels, exception handling
policy, or message format. Tool calls are not logged at the server layer.

## Decision: Use FastMCP Built-in Middleware

FastMCP 3.2+ provides `LoggingMiddleware`, `StructuredLoggingMiddleware`,
`TimingMiddleware`, and `ErrorHandlingMiddleware`. These cover tool invocation
logging, timing, and error capture without custom code. No third-party logging
library (structlog, loguru) is needed.

## Middleware Stack

Added to `create_server()` in `mcp_server.py`, after constructing the `FastMCP`
instance and before `register_tools()`:

```python
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.server.middleware.logging import (
    LoggingMiddleware,
    StructuredLoggingMiddleware,
)

# 1. Error handling first — catches everything downstream
mcp.add_middleware(ErrorHandlingMiddleware(
    include_traceback=True,
    transform_errors=True,
))

# 2. Timing — records duration of each operation
mcp.add_middleware(TimingMiddleware())

# 3. Logging last — sees the final state after other middleware
if config.log_format == "json":
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=True,
        max_payload_length=500,
    ))
else:
    mcp.add_middleware(LoggingMiddleware(
        include_payloads=True,
        max_payload_length=500,
    ))
```

Execution order: ErrorHandling runs first on the way in (catches all errors),
Logging runs last on the way in / first on the way out (logs final state).

## New Configuration

| Env var | Values | Default | Purpose |
|---------|--------|---------|---------|
| `SCHOLAR_MCP_LOG_FORMAT` | `console`, `json` | `console` | Selects human-readable or structured JSON logging middleware |

Added to `ServerConfig` in `config.py` as `log_format: str = "console"`.

The existing `SCHOLAR_MCP_LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR, default INFO)
continues to control log verbosity.

## Logging Standard

### Framework

- Standard library `logging` throughout. Every module: `logger = logging.getLogger(__name__)`.
- No `print()` for operational output. No third-party logging libraries.

### Log Levels

| Level | Use for |
|-------|---------|
| `DEBUG` | Detailed internals: cache hits, parameter values, enrichment attempts, intermediate state |
| `INFO` | Significant operations: tool invocations (handled by middleware), service startup, configuration decisions |
| `WARNING` | Degraded but continuing: API errors with fallback, missing optional config, unexpected data |
| `ERROR` | Failures affecting the primary result: unrecoverable API errors, missing required config. Use `logger.error(..., exc_info=True)` when the traceback is needed. |

`logger.exception()` is reserved for the `ErrorHandlingMiddleware` safety net.
Module code that catches and handles an error uses `logger.error(..., exc_info=True)`
when it wants the traceback in logs.

### Exception Handling Policy

- All exceptions must be caught and handled explicitly. No bare `except:`. Always
  specify the exception type.
- Expected errors (HTTP 4xx, rate limits, missing data): catch, log at appropriate
  level, return a user-facing error string.
- Optional enrichment failures (OpenAlex author data, Unpaywall lookups): catch,
  log at `DEBUG` with `exc_info=True`, continue without the enrichment.
- Errors affecting the primary tool result: catch, log at `WARNING` or `ERROR`,
  return error string to client.
- The `ErrorHandlingMiddleware` is a safety net, not a substitute for proper
  handling. If it fires on a code path, that is a bug to fix.

### Message Format

- Pseudo-structured style: `logger.info("event_name key=%s", value)`
- Event name as first token (snake_case), then key=value pairs via `%s` formatting.
- Never use f-strings in log calls (defeats lazy evaluation).

## Existing Code Audit

### Already correct (no changes needed)

- All 24 modules use `logging.getLogger(__name__)`
- No bare `except:` clauses
- No `print()` for operational output
- Message format follows `event_name key=%s` style

### Fixes needed

- Add `DEBUG`-level logging to `RateLimitedError` catch blocks that silently queue
  tasks: `logger.debug("rate_limited_queued tool=%s", tool_name)`.
- Verify each `debug`-level exception catch is correctly categorized (optional
  enrichment vs primary result). Promote to `WARNING` where the exception affects
  the primary result.

## File Changes

| File | Change |
|------|--------|
| `config.py` | Add `log_format: str` field, load from `SCHOLAR_MCP_LOG_FORMAT` |
| `mcp_server.py` | Add middleware stack after `FastMCP()` construction |
| `cli.py` | Pass `log_format` through to server creation |
| `CLAUDE.md` | Add logging standard section (levels, exceptions, format) |
| `README.md` | Document `SCHOLAR_MCP_LOG_FORMAT` env var |
| `docs/configuration.md` | Document `SCHOLAR_MCP_LOG_FORMAT` alongside existing vars |
| `_tools_*.py` (selective) | Add missing `DEBUG` logs on rate-limit queueing |

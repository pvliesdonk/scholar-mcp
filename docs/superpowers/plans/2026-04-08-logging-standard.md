# Logging Standard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FastMCP middleware for tool-call/timing/error logging, add `SCHOLAR_MCP_LOG_FORMAT` env var, add debug logging to rate-limit queueing, and document the logging standard in CLAUDE.md and user docs.

**Architecture:** Wire FastMCP's built-in `ErrorHandlingMiddleware`, `TimingMiddleware`, and `LoggingMiddleware`/`StructuredLoggingMiddleware` into `create_server()`. Add a `log_format` config field to switch between human-readable and JSON output. Document the logging standard (levels, exception handling, message format) in CLAUDE.md.

**Tech Stack:** FastMCP 3.2+ middleware (`fastmcp.server.middleware.logging`, `.timing`, `.error_handling`), stdlib `logging`, pytest

---

### Task 1: Add `log_format` to ServerConfig

**Files:**
- Modify: `src/scholar_mcp/config.py:13-47` (ServerConfig dataclass)
- Modify: `src/scholar_mcp/config.py:65-93` (load_config)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config.py`:

```python
def test_log_format_default(monkeypatch):
    monkeypatch.delenv("SCHOLAR_MCP_LOG_FORMAT", raising=False)
    cfg = load_config()
    assert cfg.log_format == "console"


def test_log_format_json(monkeypatch):
    monkeypatch.setenv("SCHOLAR_MCP_LOG_FORMAT", "json")
    cfg = load_config()
    assert cfg.log_format == "json"


def test_log_format_console_explicit(monkeypatch):
    monkeypatch.setenv("SCHOLAR_MCP_LOG_FORMAT", "console")
    cfg = load_config()
    assert cfg.log_format == "console"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py::test_log_format_default tests/test_config.py::test_log_format_json tests/test_config.py::test_log_format_console_explicit -v`
Expected: FAIL with `AttributeError: ... has no attribute 'log_format'`

- [ ] **Step 3: Add `log_format` field to ServerConfig**

In `src/scholar_mcp/config.py`, add to the `ServerConfig` dataclass (after `epo_consumer_secret`):

```python
    log_format: str = "console"
```

Update the docstring to include:

```python
        log_format: Logging output format. ``"console"`` for human-readable,
            ``"json"`` for structured JSON (e.g. for log aggregators).
```

In `load_config()`, add to the return statement (after `epo_consumer_secret`):

```python
        log_format=os.environ.get(f"{p}_LOG_FORMAT", "console").lower(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/config.py tests/test_config.py
git commit -m "feat: add SCHOLAR_MCP_LOG_FORMAT config field"
```

---

### Task 2: Wire middleware into create_server()

**Files:**
- Modify: `src/scholar_mcp/mcp_server.py:1-28` (imports)
- Modify: `src/scholar_mcp/mcp_server.py:424-433` (after FastMCP construction)
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_mcp_server.py`:

```python
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import (
    LoggingMiddleware,
    StructuredLoggingMiddleware,
)
from fastmcp.server.middleware.timing import TimingMiddleware


class TestMiddlewareStack:
    """Tests for logging/timing/error middleware wiring."""

    def test_default_middleware_stack(self) -> None:
        """Default config wires ErrorHandling + Timing + LoggingMiddleware."""
        server = create_server()
        types = [type(m) for m in server._middleware]
        assert ErrorHandlingMiddleware in types
        assert TimingMiddleware in types
        assert LoggingMiddleware in types
        assert StructuredLoggingMiddleware not in types

    def test_json_format_uses_structured_logging(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOG_FORMAT=json wires StructuredLoggingMiddleware."""
        monkeypatch.setenv("SCHOLAR_MCP_LOG_FORMAT", "json")
        server = create_server()
        types = [type(m) for m in server._middleware]
        assert StructuredLoggingMiddleware in types
        assert LoggingMiddleware not in types

    def test_middleware_order(self) -> None:
        """ErrorHandling is first, Timing second, Logging third."""
        server = create_server()
        types = [type(m) for m in server._middleware]
        err_idx = types.index(ErrorHandlingMiddleware)
        time_idx = types.index(TimingMiddleware)
        log_idx = types.index(LoggingMiddleware)
        assert err_idx < time_idx < log_idx
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_server.py::TestMiddlewareStack -v`
Expected: FAIL — `_middleware` is empty or attribute doesn't exist

- [ ] **Step 3: Add middleware wiring to create_server()**

In `src/scholar_mcp/mcp_server.py`, add imports after the existing `from fastmcp import FastMCP` line:

```python
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import (
    LoggingMiddleware,
    StructuredLoggingMiddleware,
)
from fastmcp.server.middleware.timing import TimingMiddleware
```

In `create_server()`, add after `mcp = FastMCP(...)` (line 429) and before `register_tools(...)` (line 431):

```python
    # --- Middleware: error handling, timing, logging ---
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=True,
        transform_errors=True,
    ))
    mcp.add_middleware(TimingMiddleware())
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: all pass (including existing tests)

- [ ] **Step 5: Run lint + type check**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: wire FastMCP logging, timing, and error middleware"
```

---

### Task 3: Add debug logging to rate-limit queueing

Every `except RateLimitedError` block that queues a task should log at DEBUG level. There are 16 such blocks across 8 files. The pattern is identical in each: add a `logger.debug(...)` line between the `except` and the `bundle.tasks.submit(...)`.

**Files:**
- Modify: `src/scholar_mcp/_tools_search.py` (lines 108, 168, 227, 249)
- Modify: `src/scholar_mcp/_tools_graph.py` (lines 194, 251, 504, 618)
- Modify: `src/scholar_mcp/_tools_pdf.py` (line 118)
- Modify: `src/scholar_mcp/_tools_citation.py` (line 149)
- Modify: `src/scholar_mcp/_tools_books.py` (lines 139, 181)
- Modify: `src/scholar_mcp/_tools_patent.py` (lines 231, 326, 394)
- Modify: `src/scholar_mcp/_tools_recommendations.py` (line 81)
- Modify: `src/scholar_mcp/_tools_standards.py` (line 254)
- Modify: `src/scholar_mcp/_tools_utility.py` (lines 204, 288)
- Test: `tests/test_tools_search.py` (one representative test is sufficient)

- [ ] **Step 1: Write failing test**

Pick `search_papers` as the representative case. Add to `tests/test_tools_search.py` (or create a focused test file if no rate-limit queueing tests exist):

```python
import logging

def test_rate_limit_queueing_logs_debug(
    monkeypatch, caplog, bundle_with_mock_s2
):
    """RateLimitedError catch logs tool name at DEBUG before queueing."""
    # This test depends on the existing test fixtures that mock S2Client
    # to raise RateLimitedError. Adapt to existing fixture names.
    with caplog.at_level(logging.DEBUG):
        # Trigger a rate-limited tool call
        ...  # use existing test pattern for rate-limit path
    assert any("rate_limited_queued" in r.message for r in caplog.records)
```

Note: adapt this test to the existing test fixtures in the file. The key assertion is that a `rate_limited_queued` message appears at DEBUG level.

- [ ] **Step 2: Run test to verify it fails**

Run the test — expected: FAIL (no `rate_limited_queued` log message)

- [ ] **Step 3: Add debug logging to all RateLimitedError catch blocks**

In each file, after the `except RateLimitedError:` (or `except (RateLimitedError, EpoRateLimitedError):`) line, add:

```python
            logger.debug("rate_limited_queued tool=%s", "<tool_name>")
```

Where `<tool_name>` matches the `tool=` string passed to `bundle.tasks.submit()`. For example, in `_tools_search.py` line 108:

```python
        except RateLimitedError:
            logger.debug("rate_limited_queued tool=%s", "search_papers")
            task_id = bundle.tasks.submit(_execute(retry=True), tool="search_papers")
```

Apply to all 16+ catch blocks:

| File | Line | Tool name |
|------|------|-----------|
| `_tools_search.py` | 108 | `search_papers` |
| `_tools_search.py` | 168 | `get_paper` |
| `_tools_search.py` | 227 | `get_author` |
| `_tools_search.py` | 249 | `get_author` |
| `_tools_graph.py` | 194 | `get_citations` |
| `_tools_graph.py` | 251 | `get_references` |
| `_tools_graph.py` | 504 | `get_citation_graph` |
| `_tools_graph.py` | 618 | `find_bridge_papers` |
| `_tools_pdf.py` | 118 | `fetch_paper_pdf` |
| `_tools_citation.py` | 149 | `generate_citations` |
| `_tools_books.py` | 139 | `search_books` |
| `_tools_books.py` | 181 | `get_book` |
| `_tools_patent.py` | 231 | `search_patents` |
| `_tools_patent.py` | 326 | `get_patent` |
| `_tools_patent.py` | 394 | `get_citing_patents` |
| `_tools_recommendations.py` | 81 | `recommend_papers` |
| `_tools_standards.py` | 254 | `get_standard` |
| `_tools_utility.py` | 204 | `batch_resolve` |
| `_tools_utility.py` | 288 | `enrich_paper` |

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools_search.py -v -k rate_limit`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_tools_search.py src/scholar_mcp/_tools_graph.py \
  src/scholar_mcp/_tools_pdf.py src/scholar_mcp/_tools_citation.py \
  src/scholar_mcp/_tools_books.py src/scholar_mcp/_tools_patent.py \
  src/scholar_mcp/_tools_recommendations.py src/scholar_mcp/_tools_standards.py \
  src/scholar_mcp/_tools_utility.py tests/
git commit -m "feat: add debug logging to rate-limit queueing in all tools"
```

---

### Task 4: Update CLAUDE.md with logging standard

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add logging standard section to CLAUDE.md**

Replace the existing line `- `logging.getLogger(__name__)` throughout, no `print()`` in the Conventions section with a reference, and add a new top-level section after "Key Patterns":

```markdown
## Logging Standard

### Framework
- Standard library `logging` throughout. Every module: `logger = logging.getLogger(__name__)`.
- No `print()` for operational output. No third-party logging libraries.
- FastMCP middleware handles tool invocation, timing, and error logging automatically.

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
```

Keep the `- `logging.getLogger(__name__)` throughout, no `print()`` line in Conventions but add: `See **Logging Standard** below for full details.`

- [ ] **Step 2: Verify CLAUDE.md is valid markdown**

Read the file back and check formatting.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add logging standard to CLAUDE.md"
```

---

### Task 5: Update README.md and docs/ with LOG_FORMAT

**Files:**
- Modify: `README.md:110` (config table)
- Modify: `docs/configuration.md:13` (config table)
- Modify: `docs/deployment/docker.md:98` (config table)

- [ ] **Step 1: Add `SCHOLAR_MCP_LOG_FORMAT` to README.md**

In the config table in `README.md`, after the `SCHOLAR_MCP_LOG_LEVEL` row (line 110), add:

```markdown
| `SCHOLAR_MCP_LOG_FORMAT` | `console` | Log output format: `console` (human-readable) or `json` (structured, for log aggregators) |
```

- [ ] **Step 2: Add `SCHOLAR_MCP_LOG_FORMAT` to docs/configuration.md**

After the `SCHOLAR_MCP_LOG_LEVEL` row (line 13), add:

```markdown
| `SCHOLAR_MCP_LOG_FORMAT` | `console` | Log output format. `console` produces human-readable output; `json` produces structured JSON lines for log aggregation tools (Loki, Datadog, Splunk). |
```

- [ ] **Step 3: Add `SCHOLAR_MCP_LOG_FORMAT` to docs/deployment/docker.md**

After the `SCHOLAR_MCP_LOG_LEVEL` row (line 98), add:

```markdown
| `SCHOLAR_MCP_LOG_FORMAT` | `console` | `json` for structured logging with aggregators |
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/configuration.md docs/deployment/docker.md
git commit -m "docs: document SCHOLAR_MCP_LOG_FORMAT env var"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -x -q
```

Expected: all pass

- [ ] **Step 2: Run lint**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
```

Expected: clean

- [ ] **Step 3: Run type check**

```bash
uv run mypy src/
```

Expected: no errors

- [ ] **Step 4: Check patch coverage**

```bash
uv run pytest --cov=scholar_mcp.config --cov=scholar_mcp.mcp_server --cov-report=term-missing
```

Expected: new lines covered (log_format field, middleware wiring, debug log lines)

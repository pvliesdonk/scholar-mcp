# EPO OPS Per-Service Throttle & LLM Retry Guidance

**Date:** 2026-04-08
**Status:** Approved

## Problem

The EPO OPS API returns an `X-Throttling-Control` header with both an overall color and a per-service breakdown:

```
busy (images=green:100, inpadoc=green:45, other=green:1000, retrieval=green:100, search=green:15)
```

Currently `_check_throttle` reads only the overall color. A response with `overall=busy` but `search=green` causes all searches to be queued unnecessarily.

When a patent tool does queue due to rate limiting, two further problems arise:

1. The task result on failure contains the raw exception string `EpoRateLimitedError: EPO rate limited: search=yellow`. LLMs trained on EPO OPS documentation recognise this and may start reasoning about the traffic light system themselves — retrying too aggressively, alarming the user, or otherwise behaving in ways the server already handles correctly.
2. Patent tools have no entry in `_DURATION_HINTS`, so `get_task_result` gives no hint about expected wait time — just a bare `elapsed_seconds` with no context.

## Goals

1. Check the relevant **per-service color** instead of the overall color.
2. Prevent wasted API calls via a **pre-flight cache check** when a service is known to be throttled.
3. **Sanitise rate-limit error strings** surfaced through `get_task_result` so LLMs see a generic, actionable message rather than EPO-specific terminology.
4. Add **patent tool duration hints** to `get_task_result` so LLMs understand progress is happening.
5. Update **tool descriptions** so LLMs know to just attempt calls — throttling is fully server-side.

## Non-Goals

- No new `check_epo_quota` tool.
- No change to the task queue retry logic.
- No change to S2 or other non-EPO rate limiting.
- No EPO-specific retry timing exposed to LLMs (color, `retry_after_seconds`, etc.).

---

## Design

### 1. Throttle Header Parsing — `_parse_throttle_header`

New module-level function in `_epo_client.py`:

```python
def _parse_throttle_header(header: str) -> dict[str, str]:
    """Parse X-Throttling-Control into {service: color, '_overall': color}.

    Example input: "busy (images=green:100, search=yellow:2, retrieval=green:50)"
    Example output: {"_overall": "busy", "images": "green", "search": "yellow", "retrieval": "green"}
    """
```

Uses a regex to extract `name=color:count` pairs from the parenthesised section. The `_overall` key always holds the first token. Missing header defaults to `{"_overall": "green"}`.

### 2. Per-Service Throttle Check — `_check_throttle(response, service)`

`_check_throttle` gains a `service: str` parameter (default `"_overall"`). After parsing the header it looks up `throttle.get(service, throttle["_overall"])` for the effective color. Behaviour is otherwise unchanged:

- `black` → `RuntimeError("EPO daily quota exhausted. Please try again tomorrow.")`
- not in `{"green", "idle"}` → `EpoRateLimitedError`

Every call to `_check_throttle` also writes the freshly-parsed throttle dict to the instance-level cache (see §3).

Service mappings:

| Method(s) | EPO service |
|---|---|
| `search()` | `"search"` |
| `get_biblio()`, `get_claims()`, `get_description()`, `get_citations()` | `"retrieval"` |
| `get_family()`, `get_legal()` | `"inpadoc"` |

### 3. Pre-Flight Cache Check

`EpoClient` gains two instance attributes initialised in `__init__`:

```python
self._throttle_cache: dict[str, str] = {}   # service → color
self._throttle_cache_ts: float = 0.0         # time.monotonic() of last update
```

New helper `_is_service_throttled(service: str) -> bool`:

- Returns `False` if `time.monotonic() - _throttle_cache_ts > 60` (stale — let the call through)
- Returns `True` if `_throttle_cache.get(service, "green") not in {"green", "idle"}`

Each public `EpoClient` method calls `_is_service_throttled` **before** acquiring the lock or making any network call. If throttled, raises `EpoRateLimitedError` immediately using the cached color.

Effect: after the first throttled response, subsequent concurrent calls (serialised behind the `asyncio.Lock`) short-circuit without touching EPO for up to 60 seconds.

### 4. `EpoRateLimitedError` — `service` Attribute

```python
class EpoRateLimitedError(RateLimitedError):
    def __init__(self, color: str, *, service: str = "_overall") -> None:
        self.color = color
        self.service = service
        super().__init__(f"EPO rate limited: {service}={color}")
```

`service` is keyword-only to preserve the existing positional `color` signature used in tests.

### 5. Sanitised Error Strings in `get_task_result`

`get_task_result` in `_tools_tasks.py` currently returns `task.error` verbatim. Two substring checks (no import needed) replace EPO-specific strings with concrete, actionable messages:

| Condition | `error` returned | `retryable` |
|---|---|---|
| `"daily quota"` in `task.error` | `"The service has reached its daily quota. Try again tomorrow."` | `false` |
| `"RateLimitedError"` in `task.error` | `"The service was busy and could not complete the request. Try calling the tool again in about 60 seconds."` | `true` |
| anything else | `task.error` unchanged | *(omitted)* |

Checks run in that order so the daily-quota case is caught before the generic rate-limit case.

This keeps EPO-specific terminology out of LLM responses entirely. The `retryable` flag gives the LLM a clear, implementation-agnostic signal without requiring it to interpret error strings.

### 6. Patent Tool Duration Hints

Add entries to `_DURATION_HINTS` in `_tools_tasks.py`:

```python
"search_patents": "Patent searches usually complete in 5-15 seconds.",
"get_patent": "Patent data retrieval usually completes in 5-20 seconds.",
"get_citing_patents": "Citing patent lookup usually completes in 10-30 seconds.",
```

These appear in `get_task_result` responses while a patent task is `pending` or `running`, alongside `elapsed_seconds`.

### 7. Tool Description Updates

The `search_patents`, `get_patent`, and `get_citing_patents` docstrings gain a note in their `Returns:` section:

> If the EPO service is busy, the request is automatically retried once and a `{"queued": true, "task_id": "..."}` response is returned. Use `get_task_result` to retrieve the result. If the retry also fails, `get_task_result` returns `status: failed` — call the tool again after about 60 seconds. Do not attempt to manage or reason about EPO throttle states directly.

---

## Files Changed

| File | Changes |
|---|---|
| `src/scholar_mcp/_epo_client.py` | `_parse_throttle_header`, `_check_throttle(service)`, throttle cache, pre-flight check, `EpoRateLimitedError.service` |
| `src/scholar_mcp/_tools_patent.py` | Updated docstrings on three tools |
| `src/scholar_mcp/_tools_tasks.py` | Patent entries in `_DURATION_HINTS`; sanitise rate-limit errors in `get_task_result` |
| `tests/test_epo_client.py` | Header parsing, per-service check, cache pre-flight, cache TTL |
| `tests/test_tools_patent.py` | Queued response shape (no `rate_limited` block) |
| `tests/test_tools_tasks.py` | Sanitised error string, `retryable` flag, patent hints |

---

## Testing

- `_parse_throttle_header`: full header, no sub-services, missing header (defaults green), all known colors.
- Per-service check: `overall=busy, search=green` does not raise; `overall=green, search=yellow` raises `EpoRateLimitedError(service="search")`.
- Pre-flight cache: after a throttled response, second call raises without touching the mock EPO client.
- Cache TTL: after > 60 s (mocked `time.monotonic`), call goes through normally.
- Sanitised error: `task.error` containing `"daily quota"` → daily quota message + `retryable: false`; containing `"RateLimitedError"` → 60-second retry message + `retryable: true`; other errors unchanged.
- Patent hints: `get_task_result` for a pending `search_patents` task includes `hint` and `elapsed_seconds`.
- Existing throttle tests (`green`, `yellow`, `red`, `black`, `idle`) continue to pass.

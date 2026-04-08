# EPO OPS Per-Service Throttle & LLM Retry Guidance

**Date:** 2026-04-08
**Status:** Approved

## Problem

The EPO OPS API returns an `X-Throttling-Control` header with both an overall color and a per-service breakdown:

```
busy (images=green:100, inpadoc=green:45, other=green:1000, retrieval=green:100, search=green:15)
```

Currently `_check_throttle` reads only the overall color. A response with `overall=busy` but `search=green` causes all searches to be queued unnecessarily. Additionally, when a tool does queue due to rate limiting, the LLM client receives only `{"queued": true, "task_id": "..."}` with no guidance on when to retry — leading to immediate re-attempts that burn further quota.

## Goals

1. Check the relevant **per-service color** instead of the overall color.
2. Prevent wasted API calls when a service is known to be throttled (pre-flight cache check).
3. Tell LLM clients **when to retry** in the queued response.
4. Update tool **descriptions** so LLMs know to just attempt calls — throttling is handled server-side.

## Non-Goals

- No new `check_epo_quota` tool (not needed given transparent queueing).
- No change to the task queue retry logic.
- No change to S2 or other non-EPO rate limiting.

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

Uses a regex to extract `name=color:count` pairs from the parenthesised section. The `_overall` key always holds the first token.

### 2. Per-Service Throttle Check — `_check_throttle(response, service)`

`_check_throttle` gains a `service: str` parameter (default `"_overall"`). After parsing the header, it looks up `throttle.get(service, throttle["_overall"])` for the effective color. Behavior is otherwise unchanged:

- `black` → `RuntimeError` (daily quota exhausted, not retryable)
- not in `{"green", "idle"}` → `EpoRateLimitedError`

Every call to `_check_throttle` also updates the instance-level throttle cache (see §3).

Service mappings across `EpoClient` methods:

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

Every `_check_throttle` call writes the freshly-parsed throttle dict to `_throttle_cache` and updates `_throttle_cache_ts`.

New helper `_is_service_throttled(service: str) -> bool`:

- Returns `False` if `time.monotonic() - _throttle_cache_ts > 60` (cache stale — let the call through)
- Returns `True` if `_throttle_cache.get(service, "green") not in {"green", "idle"}`

Each public `EpoClient` method checks `_is_service_throttled` before acquiring the lock or making any network call. If throttled, it raises `EpoRateLimitedError` immediately with the cached color.

This means: after the first throttled response, subsequent calls (including concurrent ones serialised behind the `asyncio.Lock`) short-circuit without touching EPO, until the 60-second TTL expires.

### 4. `EpoRateLimitedError` — `service` Attribute

```python
class EpoRateLimitedError(RateLimitedError):
    def __init__(self, color: str, *, service: str = "_overall") -> None:
        self.color = color
        self.service = service
        super().__init__(f"EPO rate limited: {service}={color}")
```

The `service` attribute is keyword-only to preserve the existing positional `color` signature used in tests.

### 5. Queued Response — Retry Guidance

Color → `retry_after_seconds` mapping (module-level constant in `_tools_patent.py`):

```python
_RETRY_AFTER: dict[str, int | None] = {
    "yellow": 30,
    "red": 120,
    "black": None,   # daily quota; message explains
}
```

When a tool catches `EpoRateLimitedError` and queues the task, the response becomes:

```json
{
  "queued": true,
  "task_id": "<id>",
  "tool": "search_patents",
  "rate_limited": {
    "service": "search",
    "color": "yellow",
    "retry_after_seconds": 30,
    "message": "EPO search quota is limited. Request queued for retry. Check task status or retry the search in ~30 s."
  }
}
```

For `black` (daily quota exhausted), `retry_after_seconds` is `null` and the message says "EPO daily quota exhausted. Try again tomorrow."

### 6. Tool Description Updates

The `search_patents`, `get_patent`, and `get_citing_patents` docstrings gain a standard note in their `Returns:` section:

> Rate limiting is handled automatically. If the EPO quota is limited, the request is queued and `{"queued": true, "task_id": "..."}` is returned along with retry guidance. There is no need to pre-check quota — just attempt the call.

---

## Files Changed

| File | Changes |
|---|---|
| `src/scholar_mcp/_epo_client.py` | `_parse_throttle_header`, `_check_throttle(service)`, throttle cache, pre-flight check, `EpoRateLimitedError.service` |
| `src/scholar_mcp/_tools_patent.py` | `_RETRY_AFTER` constant, richer queued response, updated docstrings |
| `tests/test_epo_client.py` | Tests for header parsing, per-service check, cache pre-flight, idle color |
| `tests/test_tools_patent.py` | Tests for `_RETRY_AFTER` mapping, queued response shape |

---

## Testing

- `_parse_throttle_header`: unit tests covering full header, header with no sub-services, missing header (defaults to green), each known color.
- Per-service check: `overall=busy, search=green` does not raise; `overall=green, search=yellow` raises `EpoRateLimitedError` with `service="search"`.
- Pre-flight cache: after a throttled response, a second call raises without hitting the mock client.
- Cache TTL: after > 60 s (mocked), the call goes through normally.
- Queued response shape: `rate_limited` block present and correct for `yellow`, `red`, `black`.
- Existing throttle tests (`green`, `yellow`, `red`, `black`, `idle`) continue to pass.

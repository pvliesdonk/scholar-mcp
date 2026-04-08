# EPO Per-Service Throttle & LLM Retry Guidance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix EPO OPS throttle checking to use per-service quota colors, add a pre-flight cache to prevent wasted API calls, and replace raw exception strings in task results with clear, actionable messages for LLM clients.

**Architecture:** Three coordinated changes: (1) `_epo_client.py` gains a header parser, per-service throttle check, and a 60-second instance-level cache that short-circuits pre-throttled calls; (2) `_tools_tasks.py` sanitises rate-limit errors and adds patent tool duration hints; (3) patent tool docstrings gain a standard note explaining transparent queueing. No new tools; no changes to task queue retry logic.

**Tech Stack:** Python 3.12, `asyncio`, `epo_ops` (sync library wrapped in `asyncio.to_thread`), `fastmcp`, `pytest-asyncio`

**Spec:** `docs/superpowers/specs/2026-04-08-epo-throttle-design.md`

---

## File Map

| File | Role |
|---|---|
| `src/scholar_mcp/_epo_client.py` | `_parse_throttle_header`, cache attrs, `_is_service_throttled`, updated `_check_throttle(service)`, updated `EpoRateLimitedError`, pre-flight in every public method |
| `src/scholar_mcp/_tools_tasks.py` | Sanitised error in `get_task_result`, patent entries in `_DURATION_HINTS` |
| `src/scholar_mcp/_tools_patent.py` | Docstring note on three tools |
| `tests/test_epo_client.py` | All new throttle tests |
| `tests/test_tools_tasks.py` | Rate-limit error sanitisation tests, patent hint tests |

---

## Task 1: `_parse_throttle_header` — module-level header parser

**Files:**
- Modify: `src/scholar_mcp/_epo_client.py` (add function before `EpoRateLimitedError`)
- Test: `tests/test_epo_client.py`

- [ ] **Write failing tests**

Add to `tests/test_epo_client.py` after the existing imports — import the new function alongside `EpoClient`:

```python
from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError, _parse_throttle_header
```

Add these test functions after the existing `_mock_response` helper:

```python
# ---------------------------------------------------------------------------
# _parse_throttle_header unit tests
# ---------------------------------------------------------------------------


def test_parse_throttle_header_full() -> None:
    """Full header extracts overall color and all per-service colors."""
    result = _parse_throttle_header(
        "busy (images=green:100, search=yellow:2, retrieval=green:50, inpadoc=green:45, other=green:1000)"
    )
    assert result["_overall"] == "busy"
    assert result["search"] == "yellow"
    assert result["retrieval"] == "green"
    assert result["images"] == "green"
    assert result["inpadoc"] == "green"


def test_parse_throttle_header_simple_color_only() -> None:
    """Header with no sub-services returns only _overall."""
    result = _parse_throttle_header("green")
    assert result["_overall"] == "green"
    assert "search" not in result


def test_parse_throttle_header_idle() -> None:
    """idle color is parsed correctly for overall and sub-services."""
    result = _parse_throttle_header("idle (search=idle:30, retrieval=idle:200)")
    assert result["_overall"] == "idle"
    assert result["search"] == "idle"


def test_parse_throttle_header_normalises_to_lowercase() -> None:
    """Colors are always returned as lowercase."""
    result = _parse_throttle_header("Green (Search=Yellow:2)")
    assert result["_overall"] == "green"
    assert result["search"] == "yellow"
```

- [ ] **Run tests to verify they fail**

```
uv run pytest tests/test_epo_client.py::test_parse_throttle_header_full -v
```

Expected: `ImportError: cannot import name '_parse_throttle_header'`

- [ ] **Implement `_parse_throttle_header`**

Add `import re` and `import time` to the existing imports in `_epo_client.py`, then insert this function immediately before the `EpoRateLimitedError` class:

```python
def _parse_throttle_header(header: str) -> dict[str, str]:
    """Parse an EPO ``X-Throttling-Control`` header into a service→color mapping.

    Args:
        header: Raw header value, e.g.
            ``"busy (images=green:100, search=yellow:2, retrieval=green:50)"``.

    Returns:
        Dict with ``"_overall"`` holding the top-level color, plus one entry
        per named service.  All values are lowercase.  Missing header should
        be represented by calling this with ``"green"``.
    """
    parts = header.strip().split(None, 1)
    result: dict[str, str] = {"_overall": parts[0].lower() if parts else "green"}
    if len(parts) > 1:
        for match in re.finditer(r"(\w+)=(\w+):\d+", parts[1]):
            result[match.group(1).lower()] = match.group(2).lower()
    return result
```

- [ ] **Run tests to verify they pass**

```
uv run pytest tests/test_epo_client.py::test_parse_throttle_header_full tests/test_epo_client.py::test_parse_throttle_header_simple_color_only tests/test_epo_client.py::test_parse_throttle_header_idle tests/test_epo_client.py::test_parse_throttle_header_normalises_to_lowercase -v
```

Expected: 4 passed

- [ ] **Commit**

```bash
git add src/scholar_mcp/_epo_client.py tests/test_epo_client.py
git commit -m "feat: add _parse_throttle_header for EPO per-service throttle parsing"
```

---

## Task 2: Update `_mock_response` + `_check_throttle` to use per-service color

The `_mock_response` test helper currently builds a header with only the `search` sub-service. Expand it to include all four services so that per-service checks work correctly in all existing and new tests. Then update `_check_throttle` to use the parsed per-service color.

**Files:**
- Modify: `tests/test_epo_client.py` (`_mock_response` helper + two new tests)
- Modify: `src/scholar_mcp/_epo_client.py` (`_check_throttle` signature and body)

- [ ] **Write failing tests**

Add these two tests to `tests/test_epo_client.py` in the throttle section (after `test_green_throttle_does_not_raise`):

```python
async def test_search_checks_search_service_not_overall(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """overall=busy but search=green must NOT raise — per-service check."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML,
        throttle="busy (images=green:100, retrieval=green:200, search=green:15, inpadoc=green:45, other=green:1000)",
    )
    result = await epo_client.search("ti=Test")
    assert result["total_count"] == 1


async def test_search_raises_on_search_service_yellow_despite_overall_green(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """search=yellow must raise EpoRateLimitedError even when overall=green."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML,
        throttle="green (images=green:100, retrieval=green:200, search=yellow:2, inpadoc=green:45, other=green:1000)",
    )
    with pytest.raises(EpoRateLimitedError):
        await epo_client.search("ti=Test")
```

- [ ] **Run tests to verify they fail**

```
uv run pytest tests/test_epo_client.py::test_search_checks_search_service_not_overall tests/test_epo_client.py::test_search_raises_on_search_service_yellow_despite_overall_green -v
```

Expected: both FAIL (first one raises unexpectedly, second one does not raise)

- [ ] **Update `_mock_response` helper**

Replace the existing `_mock_response` function in `tests/test_epo_client.py`:

```python
def _mock_response(
    content: bytes,
    status_code: int = 200,
    throttle: str = "green",
) -> MagicMock:
    """Create a fake requests.Response for use with mocked epo_ops methods.

    Args:
        content: Raw response body bytes.
        status_code: HTTP status code.
        throttle: Either a simple color word (``"green"``, ``"yellow"``, etc.)
            which is expanded into a full header with all four services set to
            that color, or a complete ``X-Throttling-Control`` header string
            (detected by the presence of ``"("``).

    Returns:
        MagicMock configured to behave like a requests.Response.
    """
    resp = MagicMock(spec=requests.Response)
    resp.content = content
    resp.status_code = status_code
    if "(" in throttle:
        header = throttle
    else:
        header = (
            f"{throttle} ("
            f"search={throttle}:30, "
            f"retrieval={throttle}:200, "
            f"inpadoc={throttle}:45, "
            f"other={throttle}:1000)"
        )
    resp.headers = {"X-Throttling-Control": header}
    resp.raise_for_status = MagicMock()
    return resp
```

- [ ] **Update `_check_throttle` in `_epo_client.py`**

Replace the existing `_check_throttle` method body:

```python
def _check_throttle(self, response: Any, service: str = "_overall") -> None:
    """Inspect the throttle header and raise if the relevant service is not green.

    Parses the full ``X-Throttling-Control`` header and checks the color for
    *service* specifically, falling back to the overall color when the service
    is not listed.  Updates the instance throttle cache on every call.

    Args:
        response: A ``requests.Response``-like object with a ``headers`` dict.
        service: EPO service name to check — ``"search"``, ``"retrieval"``,
            ``"inpadoc"``, or ``"_overall"`` (default).

    Raises:
        RuntimeError: When color is ``"black"`` (daily quota exhausted).
        EpoRateLimitedError: When color is not green or idle.
    """
    header = response.headers.get("X-Throttling-Control", "green")
    throttle = _parse_throttle_header(header)
    self._throttle_cache = throttle
    self._throttle_cache_ts = time.monotonic()

    color = throttle.get(service, throttle.get("_overall", "green"))
    if color == "black":
        raise RuntimeError("EPO daily quota exhausted. Please try again tomorrow.")
    if color not in ("green", "idle"):
        logger.warning("epo_throttle service=%s color=%s", service, color)
        raise EpoRateLimitedError(color, service=service)
```

Also add `import time` and `import re` at the top of `_epo_client.py` (alongside the existing imports).

- [ ] **Run all throttle tests**

```
uv run pytest tests/test_epo_client.py -k "throttle" -v
```

Expected: all pass (existing tests still pass because the expanded `_mock_response` sets all services to the same color, so per-service == overall)

- [ ] **Commit**

```bash
git add src/scholar_mcp/_epo_client.py tests/test_epo_client.py
git commit -m "feat: check per-service EPO throttle color instead of overall"
```

---

## Task 3: `EpoRateLimitedError.service` + throttle cache + pre-flight on `search()`

**Files:**
- Modify: `src/scholar_mcp/_epo_client.py`
- Test: `tests/test_epo_client.py`

- [ ] **Write failing tests**

Add to `tests/test_epo_client.py`:

```python
def test_epo_rate_limited_error_stores_service() -> None:
    """EpoRateLimitedError stores the service name."""
    exc = EpoRateLimitedError("yellow", service="search")
    assert exc.service == "search"
    assert exc.color == "yellow"


def test_epo_rate_limited_error_default_service() -> None:
    """EpoRateLimitedError defaults service to '_overall'."""
    exc = EpoRateLimitedError("red")
    assert exc.service == "_overall"


async def test_search_preflight_uses_cache_to_skip_api(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """After a throttled response, subsequent search() calls raise without hitting the API."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="yellow"
    )
    with pytest.raises(EpoRateLimitedError):
        await epo_client.search("ti=First")

    mock_ops_client.published_data_search.reset_mock()

    with pytest.raises(EpoRateLimitedError):
        await epo_client.search("ti=Second")

    mock_ops_client.published_data_search.assert_not_called()


async def test_search_preflight_bypasses_expired_cache(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """After the 60-second TTL, the next call goes through to the API."""
    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="yellow"
    )
    with pytest.raises(EpoRateLimitedError):
        await epo_client.search("ti=Test")

    # Manually expire the cache
    epo_client._throttle_cache_ts = 0.0

    mock_ops_client.published_data_search.return_value = _mock_response(
        _SEARCH_XML, throttle="green"
    )
    result = await epo_client.search("ti=Test")
    assert result["total_count"] == 1
    mock_ops_client.published_data_search.assert_called()
```

- [ ] **Run tests to verify they fail**

```
uv run pytest tests/test_epo_client.py::test_epo_rate_limited_error_stores_service tests/test_epo_client.py::test_search_preflight_uses_cache_to_skip_api -v
```

Expected: FAIL — `EpoRateLimitedError` has no `service` param, `_throttle_cache` does not exist

- [ ] **Update `EpoRateLimitedError`**

Replace the existing class definition:

```python
class EpoRateLimitedError(RateLimitedError):
    """Raised when the EPO traffic light is yellow, red, or black for a service."""

    def __init__(self, color: str, *, service: str = "_overall") -> None:
        self.color = color
        self.service = service
        super().__init__(f"EPO rate limited: {service}={color}")
```

- [ ] **Add throttle cache attrs to `EpoClient.__init__`**

In `EpoClient.__init__`, after `self._lock = asyncio.Lock()`:

```python
self._throttle_cache: dict[str, str] = {}
self._throttle_cache_ts: float = 0.0
```

- [ ] **Add `_is_service_throttled` helper**

Add this method to `EpoClient` immediately after `_check_throttle`:

```python
def _is_service_throttled(self, service: str) -> bool:
    """Return True if a recent throttled response indicates *service* is not green.

    The cache expires after 60 seconds to allow automatic recovery.

    Args:
        service: EPO service name — ``"search"``, ``"retrieval"``, or
            ``"inpadoc"``.

    Returns:
        ``True`` when the cached color for *service* is non-green and the
        cache is less than 60 seconds old.  ``False`` when the cache is stale
        or the service is green/idle.
    """
    if time.monotonic() - self._throttle_cache_ts > 60:
        return False
    color = self._throttle_cache.get(
        service, self._throttle_cache.get("_overall", "green")
    )
    return color not in ("green", "idle")
```

- [ ] **Add pre-flight to `search()` and pass `service="search"` to `_check_throttle`**

Replace the `search()` method body:

```python
async def search(
    self,
    cql_query: str,
    range_begin: int = 1,
    range_end: int = 25,
) -> dict[str, Any]:
    """Search EPO published data using a CQL query.

    Args:
        cql_query: CQL (Contextual Query Language) search expression.
        range_begin: First result number in the requested range (1-based).
        range_end: Last result number in the requested range (inclusive).

    Returns:
        Parsed search results dict with keys ``total_count`` and
        ``references`` (see :func:`parse_search_xml`).

    Raises:
        EpoRateLimitedError: When the EPO search quota is not green.
    """
    if self._is_service_throttled("search"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "search", self._throttle_cache.get("_overall", "unknown")
            ),
            service="search",
        )
    try:
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data_search,
                cql_query,
                range_begin=range_begin,
                range_end=range_end,
            )
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.debug("epo_search_no_results cql=%s", cql_query)
            return {"total_count": 0, "references": []}
        raise
    self._check_throttle(response, service="search")
    return parse_search_xml(response.content)
```

- [ ] **Run tests**

```
uv run pytest tests/test_epo_client.py -v
```

Expected: all pass

- [ ] **Commit**

```bash
git add src/scholar_mcp/_epo_client.py tests/test_epo_client.py
git commit -m "feat: add throttle cache and pre-flight check to EpoClient.search()"
```

---

## Task 4: Pre-flight + per-service check for all remaining EpoClient methods

Wire `_is_service_throttled` and the correct `service` arg into `get_biblio`, `get_claims`, `get_description`, `get_citations` (all `"retrieval"`) and `get_family`, `get_legal` (both `"inpadoc"`).

**Files:**
- Modify: `src/scholar_mcp/_epo_client.py`
- Test: `tests/test_epo_client.py`

- [ ] **Write failing tests**

```python
async def test_get_biblio_preflight_uses_cache(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """After retrieval=yellow response, get_biblio raises without hitting the API."""
    mock_ops_client.published_data.return_value = _mock_response(
        _BIBLIO_XML, throttle="yellow"
    )
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(EpoRateLimitedError):
        await epo_client.get_biblio(doc)

    mock_ops_client.published_data.reset_mock()

    with pytest.raises(EpoRateLimitedError):
        await epo_client.get_biblio(doc)

    mock_ops_client.published_data.assert_not_called()


async def test_get_family_preflight_uses_cache(
    epo_client: EpoClient,
    mock_ops_client: MagicMock,
) -> None:
    """After inpadoc=yellow response, get_family raises without hitting the API."""
    mock_ops_client.family.return_value = _mock_response(
        _FAMILY_RESPONSE_XML, throttle="yellow"
    )
    doc = DocdbNumber(country="EP", number="1234567", kind="A1")
    with pytest.raises(EpoRateLimitedError):
        await epo_client.get_family(doc)

    mock_ops_client.family.reset_mock()

    with pytest.raises(EpoRateLimitedError):
        await epo_client.get_family(doc)

    mock_ops_client.family.assert_not_called()
```

- [ ] **Run tests to verify they fail**

```
uv run pytest tests/test_epo_client.py::test_get_biblio_preflight_uses_cache tests/test_epo_client.py::test_get_family_preflight_uses_cache -v
```

Expected: FAIL — no pre-flight yet in those methods

- [ ] **Add pre-flight + per-service to retrieval methods**

Replace each method body. Pattern for `"retrieval"` methods (`get_biblio`, `get_claims`, `get_description`, `get_citations`):

```python
async def get_biblio(self, doc: DocdbNumber) -> dict[str, Any]:
    """Fetch bibliographic data for a single patent.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        Parsed bibliographic metadata dict (see :func:`parse_biblio_xml`).

    Raises:
        EpoRateLimitedError: When the EPO retrieval quota is not green.
    """
    if self._is_service_throttled("retrieval"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "retrieval", self._throttle_cache.get("_overall", "unknown")
            ),
            service="retrieval",
        )
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="biblio",
        )
    self._check_throttle(response, service="retrieval")
    return parse_biblio_xml(response.content)


async def get_claims(self, doc: DocdbNumber) -> str:
    """Fetch claims text for a patent.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        Claims text as a single string (see :func:`parse_claims_xml`).

    Raises:
        EpoRateLimitedError: When the EPO retrieval quota is not green.
    """
    if self._is_service_throttled("retrieval"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "retrieval", self._throttle_cache.get("_overall", "unknown")
            ),
            service="retrieval",
        )
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="claims",
        )
    self._check_throttle(response, service="retrieval")
    return parse_claims_xml(response.content)


async def get_description(self, doc: DocdbNumber) -> str:
    """Fetch description text for a patent.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        Description text as a single string (see :func:`parse_description_xml`).

    Raises:
        EpoRateLimitedError: When the EPO retrieval quota is not green.
    """
    if self._is_service_throttled("retrieval"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "retrieval", self._throttle_cache.get("_overall", "unknown")
            ),
            service="retrieval",
        )
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="description",
        )
    self._check_throttle(response, service="retrieval")
    return parse_description_xml(response.content)


async def get_citations(self, doc: DocdbNumber) -> dict[str, list[dict[str, Any]]]:
    """Fetch cited references (patent and NPL) for a patent.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        Dict with ``patent_refs`` and ``npl_refs`` lists
        (see :func:`parse_citations_from_biblio`).

    Raises:
        EpoRateLimitedError: When the EPO retrieval quota is not green.
    """
    if self._is_service_throttled("retrieval"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "retrieval", self._throttle_cache.get("_overall", "unknown")
            ),
            service="retrieval",
        )
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="biblio",
        )
    self._check_throttle(response, service="retrieval")
    return parse_citations_from_biblio(response.content)
```

- [ ] **Add pre-flight + per-service to inpadoc methods**

```python
async def get_family(self, doc: DocdbNumber) -> list[dict[str, str]]:
    """Fetch patent family members.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        List of family member dicts (see :func:`parse_family_xml`).

    Raises:
        EpoRateLimitedError: When the EPO inpadoc quota is not green.
    """
    if self._is_service_throttled("inpadoc"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "inpadoc", self._throttle_cache.get("_overall", "unknown")
            ),
            service="inpadoc",
        )
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.family,
            "publication",
            inp,
        )
    self._check_throttle(response, service="inpadoc")
    return parse_family_xml(response.content)


async def get_legal(self, doc: DocdbNumber) -> list[dict[str, str]]:
    """Fetch legal status events for a patent.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        List of legal event dicts (see :func:`parse_legal_xml`).

    Raises:
        EpoRateLimitedError: When the EPO inpadoc quota is not green.
    """
    if self._is_service_throttled("inpadoc"):
        raise EpoRateLimitedError(
            self._throttle_cache.get(
                "inpadoc", self._throttle_cache.get("_overall", "unknown")
            ),
            service="inpadoc",
        )
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.legal,
            "publication",
            inp,
        )
    self._check_throttle(response, service="inpadoc")
    return parse_legal_xml(response.content)
```

- [ ] **Run all epo client tests**

```
uv run pytest tests/test_epo_client.py -v
```

Expected: all pass

- [ ] **Commit**

```bash
git add src/scholar_mcp/_epo_client.py tests/test_epo_client.py
git commit -m "feat: add per-service throttle check and pre-flight cache to all EpoClient methods"
```

---

## Task 5: Sanitise rate-limit errors + patent duration hints in `get_task_result`

**Files:**
- Modify: `src/scholar_mcp/_tools_tasks.py`
- Test: `tests/test_tools_tasks.py`

- [ ] **Write failing tests**

Add to `tests/test_tools_tasks.py`:

```python
async def test_get_task_result_rate_limit_error_is_sanitised(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """Rate-limit errors are replaced with a generic 60-second retry message."""

    async def _rate_limited_coro() -> str:
        raise Exception("EpoRateLimitedError: EPO rate limited: search=yellow")

    task_id = bundle.tasks.submit(_rate_limited_coro())
    for _ in range(40):
        task = bundle.tasks.get(task_id)
        if task and task.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] == "failed"
    assert data["retryable"] is True
    assert "60 seconds" in data["error"]
    assert "RateLimitedError" not in data["error"]
    assert "yellow" not in data["error"]


async def test_get_task_result_daily_quota_error_is_sanitised(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """Daily quota errors are replaced with a 'try tomorrow' message."""

    async def _quota_coro() -> str:
        raise Exception("RuntimeError: EPO daily quota exhausted. Please try again tomorrow.")

    task_id = bundle.tasks.submit(_quota_coro())
    for _ in range(40):
        task = bundle.tasks.get(task_id)
        if task and task.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] == "failed"
    assert data["retryable"] is False
    assert "tomorrow" in data["error"]
    assert "daily quota" not in data["error"].lower()


async def test_get_task_result_other_errors_pass_through(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """Non-rate-limit errors are returned unchanged (regression guard)."""

    async def _failing_coro() -> str:
        raise ValueError("unexpected database error")

    task_id = bundle.tasks.submit(_failing_coro())
    for _ in range(40):
        task = bundle.tasks.get(task_id)
        if task and task.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] == "failed"
    assert "unexpected database error" in data["error"]
    assert "retryable" not in data


async def test_get_task_result_patent_search_hint(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_task_result includes a hint for queued search_patents tasks."""

    async def _slow_coro() -> str:
        await asyncio.sleep(10)
        return "{}"

    task_id = bundle.tasks.submit(_slow_coro(), tool="search_patents")

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] in ("pending", "running")
    assert "hint" in data
    assert "5-15 seconds" in data["hint"]


async def test_get_task_result_get_patent_hint(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_task_result includes a hint for queued get_patent tasks."""

    async def _slow_coro() -> str:
        await asyncio.sleep(10)
        return "{}"

    task_id = bundle.tasks.submit(_slow_coro(), tool="get_patent")

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert "hint" in data
    assert "5-20 seconds" in data["hint"]
```

- [ ] **Run tests to verify they fail**

```
uv run pytest tests/test_tools_tasks.py::test_get_task_result_rate_limit_error_is_sanitised tests/test_tools_tasks.py::test_get_task_result_patent_search_hint -v
```

Expected: FAIL

- [ ] **Update `_DURATION_HINTS` in `_tools_tasks.py`**

Replace the existing `_DURATION_HINTS` dict:

```python
_DURATION_HINTS: dict[str, str] = {
    "fetch_paper_pdf": "PDF download usually completes in 10-30 seconds.",
    "convert_pdf_to_markdown": (
        "PDF conversion typically takes 1-5 minutes depending on page count."
    ),
    "fetch_and_convert": (
        "Full pipeline (download + conversion) typically takes 1-5 minutes."
    ),
    "search_patents": "Patent searches usually complete in 5-15 seconds.",
    "get_patent": "Patent data retrieval usually completes in 5-20 seconds.",
    "get_citing_patents": "Citing patent lookup usually completes in 10-30 seconds.",
}
```

- [ ] **Update the `failed` branch in `get_task_result`**

Replace this section in `get_task_result`:

```python
        if task.status == "completed":
            response["result"] = task.result
        elif task.status == "failed":
            response["error"] = task.error
```

With:

```python
        if task.status == "completed":
            response["result"] = task.result
        elif task.status == "failed":
            error = task.error or ""
            if "daily quota" in error:
                response["error"] = (
                    "The service has reached its daily quota. Try again tomorrow."
                )
                response["retryable"] = False
            elif "RateLimitedError" in error:
                response["error"] = (
                    "The service was busy and could not complete the request. "
                    "Try calling the tool again in about 60 seconds."
                )
                response["retryable"] = True
            else:
                response["error"] = error
```

- [ ] **Run all task tool tests**

```
uv run pytest tests/test_tools_tasks.py -v
```

Expected: all pass

- [ ] **Commit**

```bash
git add src/scholar_mcp/_tools_tasks.py tests/test_tools_tasks.py
git commit -m "feat: sanitise rate-limit errors in get_task_result and add patent duration hints"
```

---

## Task 6: Update patent tool docstrings

No tests needed — docstring-only change.

**Files:**
- Modify: `src/scholar_mcp/_tools_patent.py`

- [ ] **Add standard note to `search_patents` Returns: section**

Find the `Returns:` block in `search_patents` and replace it:

```python
        Returns:
            JSON string with ``total_count`` and ``references`` list, or an
            error dict if the EPO client is not configured or the API fails.
            If the EPO service is busy, the request is automatically retried
            once and ``{"queued": true, "task_id": "..."}`` is returned. Use
            ``get_task_result`` to retrieve the result. If the retry also
            fails, ``get_task_result`` returns ``status: failed`` — call this
            tool again after about 60 seconds. Do not attempt to manage or
            reason about EPO throttle states directly.
```

- [ ] **Add same note to `get_patent` Returns: section**

```python
        Returns:
            JSON string with ``patent_number`` (normalised DOCDB format) and
            the requested section data, or an error dict on failure.
            If the EPO service is busy, the request is automatically retried
            once and ``{"queued": true, "task_id": "..."}`` is returned. Use
            ``get_task_result`` to retrieve the result. If the retry also
            fails, ``get_task_result`` returns ``status: failed`` — call this
            tool again after about 60 seconds. Do not attempt to manage or
            reason about EPO throttle states directly.
```

- [ ] **Add same note to `get_citing_patents` Returns: section**

```python
        Returns:
            JSON string with ``paper_id``, ``patents`` list (each with
            biblio data and ``match_source``), ``total_count``, and a
            ``note`` about coverage limitations.
            If the EPO service is busy, the request is automatically retried
            once and ``{"queued": true, "task_id": "..."}`` is returned. Use
            ``get_task_result`` to retrieve the result. If the retry also
            fails, ``get_task_result`` returns ``status: failed`` — call this
            tool again after about 60 seconds. Do not attempt to manage or
            reason about EPO throttle states directly.
```

- [ ] **Run full test suite to confirm nothing broken**

```
uv run pytest tests/ -q --tb=short
```

Expected: all pass

- [ ] **Commit**

```bash
git add src/scholar_mcp/_tools_patent.py
git commit -m "docs: add transparent rate-limiting note to patent tool descriptions"
```

---

## Task 7: Rebuild Docker image

- [ ] **Rebuild and restart**

```bash
cd /mnt/docker-volumes/compose.git/70-ai
docker compose up -d --build scholar-mcp
```

Expected: `Container ai-scholar-mcp Started`

- [ ] **Verify new code is live**

```bash
docker exec ai-scholar-mcp python -c "
from scholar_mcp._epo_client import _parse_throttle_header, EpoRateLimitedError
r = _parse_throttle_header('busy (search=green:15, retrieval=green:100)')
print(r)
e = EpoRateLimitedError('yellow', service='search')
print(e.service, e.color)
"
```

Expected:
```
{'_overall': 'busy', 'search': 'green', 'retrieval': 'green'}
search yellow
```

- [ ] **Commit** *(no code changes — this step just rebuilds)*

No commit needed. The image is built from already-committed source.

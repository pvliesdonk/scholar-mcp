# Standards Backends & Patent PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all three broken standards backends (NIST, W3C, ETSI) and add an authenticated EPO patent PDF tool.

**Architecture:** Each standards fix is an isolated rewrite of the relevant `_*Fetcher` class in `_standards_client.py`. NIST switches from a dead JSON endpoint to MODS XML from GitHub releases, cached to disk. W3C fixes broken response parsing and adds client-side stub caching. ETSI replaces a Cloudflare-blocked HTML scraper with the undocumented but working Joomla JSON API. Patent PDF adds a new tool that uses the EPO OPS two-step image/PDF retrieval plus URL interception in `fetch_pdf_by_url`.

**Tech Stack:** Python stdlib `xml.etree.ElementTree` (MODS parsing), `httpx` (all HTTP), `json` (disk cache), existing `epo_ops.Client` (patent PDF), existing `RateLimiter`, FastMCP DI patterns.

---

## Context for subagent workers

**Codebase location:** `/mnt/code/scholar-mcp`

**Key files:**
- `src/scholar_mcp/_standards_client.py` — all four standards fetchers + `StandardsClient` orchestrator
- `src/scholar_mcp/_server_deps.py:130-131` — `StandardsClient` constructed here; add `cache_dir` param
- `src/scholar_mcp/_epo_client.py` — EPO OPS async wrapper; add `get_pdf()` here
- `src/scholar_mcp/_tools_patent.py` — patent MCP tools; add `fetch_patent_pdf` here
- `src/scholar_mcp/_tools_pdf.py:442` — `fetch_pdf_by_url`; add URL interception here
- `tests/test_standards_client.py` — all standards tests
- `tests/test_tools_patent.py` — patent tool tests
- `tests/test_tools_pdf.py` — PDF tool tests

**Run tests:** `uv run pytest -x -q`
**Lint+format:** `uv run ruff check --fix . && uv run ruff format .`
**Type check:** `uv run mypy src/`

**StandardsClient constructor signature (current):**
```python
def __init__(self, http: httpx.AsyncClient) -> None:
```
After Task 1 it becomes:
```python
def __init__(self, http: httpx.AsyncClient, *, cache_dir: Path | None = None) -> None:
```

**`StandardRecord` is a `TypedDict`** with these keys (all optional except `identifier`):
`identifier`, `aliases`, `title`, `body`, `number`, `revision`, `status`, `published_date`,
`withdrawn_date`, `superseded_by`, `supersedes`, `scope`, `committee`, `url`,
`full_text_url`, `full_text_available`, `price`, `related`.

**Test patterns to follow:**
- Use `respx` for HTTP mocking (decorator `@pytest.mark.respx(base_url=...)` or `respx_mock` fixture)
- Fetchers are tested directly (no FastMCP needed): `_NISTFetcher(http, RateLimiter(delay=0.0))`
- All async tests use `pytest-anyio` via `asyncio` mode (configured in pyproject.toml)

---

## Task 1: NIST — Replace dead JSON endpoint with MODS XML (disk-cached)

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` — rewrite `_NISTFetcher` + `_normalize_nist`, add `cache_dir` to `StandardsClient`
- Modify: `src/scholar_mcp/_server_deps.py` — pass `cache_dir=config.cache_dir` to `StandardsClient`
- Modify: `tests/test_standards_client.py` — replace NIST tests for new implementation

**Background:** The old endpoint `https://csrc.nist.gov/CSRC/media/Publications/search-results-json-file/json` returns 404. The replacement is the NIST-Tech-Pubs GitHub releases MODS XML: `https://github.com/usnistgov/NIST-Tech-Pubs/releases/download/Jan2026/allrecords-MODS.xml` (80MB, namespace `http://www.loc.gov/mods/v3`). We discover the latest release via the GitHub API, download once, parse to a list of records, save as JSON to `{cache_dir}/nist_catalogue.json`. On subsequent startups, load from disk if <90 days old.

**MODS XML structure (one `<mods>` record for SP 800-53 Rev. 5):**
```xml
<mods version="3.7">
  <titleInfo><title>Security and Privacy Controls...</title></titleInfo>
  <abstract displayLabel="Abstract">...</abstract>
  <originInfo eventType="publisher"><dateIssued>2020-09.</dateIssued></originInfo>
  <location>
    <url displayLabel="electronic resource" usage="primary display">
      https://doi.org/10.6028/NIST.SP.800-53r5
    </url>
  </location>
  <relatedItem type="series">
    <titleInfo>
      <title>NIST special publication; NIST special pub; NIST SP</title>
      <partNumber>800-53r5</partNumber>
    </titleInfo>
  </relatedItem>
  <identifier type="doi">10.6028/NIST.SP.800-53r5</identifier>
</mods>
```
`partNumber` encodes both number and revision: `800-53r5` → number=`800-53`, rev=`5`.
Other series titles: "NISTIR; NIST IR; NIST interagency report" → NISTIR, "FIPS" → FIPS.

- [ ] **Step 1: Write failing tests for new _NISTFetcher**

In `tests/test_standards_client.py`, replace all existing NIST tests (search for `# NIST fetcher tests` section and everything under it until `# W3C fetcher tests`) with:

```python
# ---------------------------------------------------------------------------
# NIST fetcher tests (MODS XML backend)
# ---------------------------------------------------------------------------

GITHUB_RELEASES_URL = "https://api.github.com"
GITHUB_RELEASES_CDN = "https://objects.githubusercontent.com"  # redirect target

SAMPLE_GITHUB_RELEASE = {
    "tag_name": "Jan2026",
    "assets": [
        {
            "name": "allrecords-MODS.xml",
            "browser_download_url": "https://github.com/usnistgov/NIST-Tech-Pubs/releases/download/Jan2026/allrecords-MODS.xml",
        }
    ],
}

SAMPLE_MODS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<modsCollection xmlns="http://www.loc.gov/mods/v3">
  <mods version="3.7">
    <titleInfo>
      <title>Security and Privacy Controls for Information Systems and Organizations</title>
    </titleInfo>
    <abstract displayLabel="Abstract">A catalog of security and privacy controls.</abstract>
    <originInfo eventType="publisher">
      <dateIssued>2020-09.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.SP.800-53r5</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>NIST special publication; NIST special pub; NIST SP</title>
        <partNumber>800-53r5</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.SP.800-53r5</identifier>
  </mods>
  <mods version="3.7">
    <titleInfo>
      <title>Minimum Security Requirements for Federal Information and Information Systems</title>
    </titleInfo>
    <originInfo eventType="publisher">
      <dateIssued>2006-03.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.FIPS.200</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>Federal information processing standards publication; FIPS</title>
        <partNumber>200</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.FIPS.200</identifier>
  </mods>
  <mods version="3.7">
    <titleInfo>
      <title>Cybersecurity Framework Version 2.0</title>
    </titleInfo>
    <originInfo eventType="publisher">
      <dateIssued>2024-02.</dateIssued>
    </originInfo>
    <location>
      <url displayLabel="electronic resource" usage="primary display">https://doi.org/10.6028/NIST.CSWP.29</url>
    </location>
    <relatedItem type="series">
      <titleInfo>
        <title>NIST cybersecurity white paper; NIST CSWP</title>
        <partNumber>29</partNumber>
      </titleInfo>
    </relatedItem>
    <identifier type="doi">10.6028/NIST.CSWP.29</identifier>
  </mods>
</modsCollection>
"""


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_search_sp(respx_mock: respx.MockRouter, tmp_path) -> None:
    """search() finds SP 800-53 from MODS XML."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "NIST SP 800-53 Rev. 5"
    assert results[0]["body"] == "NIST"
    assert results[0]["number"] == "800-53"
    assert results[0]["revision"] == "Rev. 5"
    assert results[0]["full_text_available"] is True


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_search_fips(respx_mock: respx.MockRouter, tmp_path) -> None:
    """search() finds FIPS 200."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("FIPS 200", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "FIPS 200"
    assert results[0]["body"] == "NIST"


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get(respx_mock: respx.MockRouter, tmp_path) -> None:
    """get() returns exact match."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 800-53 Rev. 5")
    await http.aclose()
    assert record is not None
    assert record["title"].startswith("Security and Privacy")
    assert record["scope"] is not None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_get_not_found(respx_mock: respx.MockRouter, tmp_path) -> None:
    """get() returns None for unknown identifier."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        return_value=httpx.Response(200, content=SAMPLE_MODS_XML)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    record = await fetcher.get("NIST SP 999-99")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_disk_cache_used_on_second_call(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """Second fetcher instance loads from disk cache, no network call."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=SAMPLE_MODS_XML)

    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(200, json=SAMPLE_GITHUB_RELEASE)
    )
    respx_mock.get(re.compile(r".*allrecords-MODS\.xml.*")).mock(
        side_effect=side_effect
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)

    # First fetcher: downloads XML, saves to disk
    fetcher1 = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    await fetcher1.search("800-53", limit=1)
    assert call_count == 1

    # Second fetcher: should load from disk, not download again
    fetcher2 = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    await fetcher2.search("800-53", limit=1)
    await http.aclose()
    assert call_count == 1  # no new download


@pytest.mark.respx(base_url=GITHUB_RELEASES_URL)
async def test_nist_github_api_failure_returns_empty(
    respx_mock: respx.MockRouter, tmp_path
) -> None:
    """GitHub API failure logs warning and returns empty list."""
    respx_mock.get("/repos/usnistgov/NIST-Tech-Pubs/releases/latest").mock(
        return_value=httpx.Response(503)
    )
    http = httpx.AsyncClient(base_url=GITHUB_RELEASES_URL)
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert results == []
```

Also add `import re` to the imports at the top of `tests/test_standards_client.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_standards_client.py::test_nist_search_sp -xvs 2>&1 | tail -15
```
Expected: FAIL with `TypeError` or `AssertionError` — `_NISTFetcher` still uses old JSON endpoint.

- [ ] **Step 3: Implement new `_NISTFetcher` in `_standards_client.py`**

Replace the `_NIST_BASE` and `_NIST_PUBLICATIONS_JSON` constants and the entire `_NISTFetcher` class and `_normalize_nist` function. Also add `cache_dir` parameter to `StandardsClient.__init__` and update `_NISTFetcher` instantiation inside it.

Add these imports at the top of `_standards_client.py` (after existing imports):
```python
import json
import time
from pathlib import Path
from xml.etree import ElementTree as ET
```

Replace the NIST constants:
```python
_NIST_GITHUB_API = "https://api.github.com"
_NIST_MODS_RELEASE_URL = (
    f"{_NIST_GITHUB_API}/repos/usnistgov/NIST-Tech-Pubs/releases/latest"
)
_NIST_MODS_ASSET_NAME = "allrecords-MODS.xml"
_NIST_MODS_NS = "http://www.loc.gov/mods/v3"
_NIST_CACHE_MAX_AGE_DAYS = 90
```

Replace `_NISTFetcher` class:
```python
class _NISTFetcher:
    """Fetches NIST publication metadata from NIST-Tech-Pubs MODS XML releases.

    Downloads the MODS XML catalogue from the latest GitHub release of
    https://github.com/usnistgov/NIST-Tech-Pubs on first use, parses it,
    and caches parsed records to disk as JSON. Subsequent calls within 90 days
    load from disk without network I/O.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter.
        cache_dir: Directory for persistent JSON cache. If None, no disk
            caching is used (data is re-downloaded every process restart).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        cache_dir: Path | None = None,
    ) -> None:
        self._http = http
        self._limiter = limiter
        self._cache_dir = cache_dir
        self._catalogue: list[dict] | None = None  # type: ignore[type-arg]
        self._lock = asyncio.Lock()

    def _cache_path(self) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / "nist_catalogue.json"

    def _load_from_disk(self) -> list[dict] | None:  # type: ignore[type-arg]
        """Load cached catalogue from disk if it exists and is fresh."""
        path = self._cache_path()
        if path is None or not path.exists():
            return None
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if age_days > _NIST_CACHE_MAX_AGE_DAYS:
            logger.info(
                "nist_catalogue_stale age_days=%.0f threshold=%d — re-downloading",
                age_days,
                _NIST_CACHE_MAX_AGE_DAYS,
            )
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("nist_catalogue_disk_load_failed err=%s", exc)
            return None

    def _save_to_disk(self, records: list[dict]) -> None:  # type: ignore[type-arg]
        path = self._cache_path()
        if path is None:
            return
        try:
            path.write_text(json.dumps(records), encoding="utf-8")
            logger.info("nist_catalogue_cached path=%s count=%d", path, len(records))
        except OSError as exc:
            logger.warning("nist_catalogue_disk_save_failed err=%s", exc)

    async def _fetch_mods_url(self) -> str | None:
        """Get the download URL for the latest MODS XML asset from GitHub releases."""
        await self._limiter.acquire()
        resp = await self._http.get(
            _NIST_MODS_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            logger.warning(
                "nist_github_api_error status=%d url=%s",
                resp.status_code,
                str(resp.url),
            )
            return None
        data = resp.json()
        for asset in data.get("assets", []):
            if asset.get("name") == _NIST_MODS_ASSET_NAME:
                return asset["browser_download_url"]
        logger.warning("nist_mods_asset_not_found release=%s", data.get("tag_name"))
        return None

    async def _fetch_all(self) -> list[dict]:  # type: ignore[type-arg]
        """Return parsed NIST catalogue, using disk cache when available."""
        if self._catalogue is not None:
            return self._catalogue
        async with self._lock:
            if self._catalogue is not None:
                return self._catalogue
            cached = self._load_from_disk()
            if cached is not None:
                self._catalogue = cached
                logger.debug("nist_catalogue_loaded_from_disk count=%d", len(cached))
                return self._catalogue

            mods_url = await self._fetch_mods_url()
            if mods_url is None:
                return []

            await self._limiter.acquire()
            resp = await self._http.get(mods_url, follow_redirects=True)
            if resp.status_code != 200:
                logger.warning(
                    "nist_mods_download_error status=%d", resp.status_code
                )
                return []
            records = _parse_nist_mods(resp.content)
            logger.info("nist_catalogue_parsed count=%d", len(records))
            self._save_to_disk(records)
            self._catalogue = records
        return self._catalogue

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search NIST publications by keyword in identifier or title.

        Args:
            query: Search string (e.g. "800-53", "FIPS 140").
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        all_pubs = await self._fetch_all()
        q = query.lower()
        matches = [
            p
            for p in all_pubs
            if q in (p.get("identifier") or "").lower()
            or q in (p.get("title") or "").lower()
            or q in (p.get("number") or "").lower()
        ]
        return matches[:limit]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single NIST publication by canonical identifier.

        Args:
            identifier: Canonical NIST identifier (e.g. "NIST SP 800-53 Rev. 5").

        Returns:
            Populated StandardRecord or None if not found.
        """
        all_pubs = await self._fetch_all()
        id_lower = identifier.lower()
        for pub in all_pubs:
            pub_id = (pub.get("identifier") or "").lower()
            if pub_id == id_lower or id_lower in pub_id or pub_id in id_lower:
                return pub  # type: ignore[return-value]
        return None
```

Replace `_normalize_nist` with `_parse_nist_mods`:
```python
def _parse_nist_mods(xml_bytes: bytes) -> list[StandardRecord]:
    """Parse a NIST-Tech-Pubs MODS XML file into a list of StandardRecords.

    Only records belonging to recognised NIST series (SP, FIPS, NISTIR) are
    returned. Other series (internal reports, white papers without a series
    label) are skipped.

    Args:
        xml_bytes: Raw bytes of allrecords-MODS.xml.

    Returns:
        List of populated StandardRecord dicts.
    """
    ns = f"{{{_NIST_MODS_NS}}}"
    records: list[StandardRecord] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("nist_mods_parse_error err=%s", exc)
        return []

    for mods in root.findall(f"{ns}mods"):
        record = _normalize_nist_mods(mods, ns)
        if record is not None:
            records.append(record)
    return records


def _normalize_nist_mods(
    mods: "ET.Element", ns: str
) -> StandardRecord | None:
    """Normalise a single <mods> element to a StandardRecord.

    Args:
        mods: A ``<mods>`` XML element.
        ns: Namespace prefix string, e.g. ``"{http://www.loc.gov/mods/v3}"``.

    Returns:
        Populated StandardRecord or None if the record is not a recognised
        NIST series publication.
    """
    # Series metadata
    series_el = None
    for ri in mods.findall(f"{ns}relatedItem"):
        if ri.get("type") == "series":
            series_el = ri
            break
    if series_el is None:
        return None

    series_title_el = series_el.find(f"{ns}titleInfo/{ns}title")
    part_el = series_el.find(f"{ns}titleInfo/{ns}partNumber")
    series_title = (
        (series_title_el.text or "").lower() if series_title_el is not None else ""
    )
    part_number = (
        part_el.text.strip() if part_el is not None and part_el.text else ""
    )

    if "special publication" in series_title or "nist sp" in series_title:
        body_prefix = "NIST SP"
    elif "nistir" in series_title or "interagency" in series_title or "internal report" in series_title:
        body_prefix = "NISTIR"
    elif "fips" in series_title:
        body_prefix = "FIPS"
    else:
        return None  # skip unrecognised series

    # partNumber → number + optional revision (e.g. "800-53r5" → "800-53", "5")
    m = re.match(r"^(.*?)r(\d+)$", part_number)
    if m:
        number = m.group(1)
        revision = m.group(2)
    else:
        number = part_number
        revision = None

    # Canonical identifier
    if body_prefix == "NIST SP":
        canonical = f"NIST SP {number}"
        if revision:
            canonical += f" Rev. {revision}"
    elif body_prefix == "NISTIR":
        canonical = f"NISTIR {number.upper()}"
    else:
        canonical = f"FIPS {number}"

    # Title
    title_el = mods.find(f"{ns}titleInfo/{ns}title")
    subtitle_el = mods.find(f"{ns}titleInfo/{ns}subTitle")
    title = (title_el.text or "").strip() if title_el is not None else ""
    if subtitle_el is not None and subtitle_el.text:
        title = f"{title}: {subtitle_el.text.strip()}"

    # Abstract
    abstract_el = mods.find(f"{ns}abstract")
    scope = (
        abstract_el.text.strip()
        if abstract_el is not None and abstract_el.text
        else None
    )

    # URL (primary display location)
    url = ""
    for url_el in mods.findall(f"{ns}location/{ns}url"):
        if url_el.get("usage") == "primary display":
            url = (url_el.text or "").strip()
            break
    if not url:
        url_el = mods.find(f"{ns}location/{ns}url")
        if url_el is not None:
            url = (url_el.text or "").strip()

    # Publication date (strip trailing dot)
    pub_date = None
    for date_el in mods.iter(f"{ns}dateIssued"):
        if date_el.text:
            pub_date = date_el.text.strip().rstrip(".")
            break

    return StandardRecord(
        identifier=canonical,
        aliases=[],
        title=title,
        body="NIST",
        number=number,
        revision=f"Rev. {revision}" if revision else None,
        status="published",
        published_date=pub_date,
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=scope,
        committee=None,
        url=url,
        full_text_url=url or None,
        full_text_available=bool(url),
        price=None,
        related=[],
    )
```

Update `StandardsClient.__init__` to accept and pass `cache_dir`:
```python
def __init__(
    self, http: httpx.AsyncClient, *, cache_dir: Path | None = None
) -> None:
    self._http = http
    self._fetchers: dict[
        str, _IETFFetcher | _NISTFetcher | _W3CFetcher | _ETSIFetcher
    ] = {
        "IETF": _IETFFetcher(http, RateLimiter(delay=0.5)),
        "NIST": _NISTFetcher(http, RateLimiter(delay=1.0), cache_dir=cache_dir),
        "W3C": _W3CFetcher(http, RateLimiter(delay=0.5)),
        "ETSI": _ETSIFetcher(http, RateLimiter(delay=1.0)),
    }
```

- [ ] **Step 4: Update `_server_deps.py` to pass `cache_dir`**

In `src/scholar_mcp/_server_deps.py`, change line 131:
```python
# Before:
standards = StandardsClient(standards_http)
# After:
standards = StandardsClient(standards_http, cache_dir=config.cache_dir)
```

- [ ] **Step 5: Run the new NIST tests**

```bash
uv run pytest tests/test_standards_client.py -k "nist" -xvs 2>&1 | tail -20
```
Expected: All 6 new NIST tests PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
uv run pytest -x -q 2>&1 | tail -10
```
Expected: All tests pass (old NIST tests that mocked the dead JSON endpoint are replaced).

- [ ] **Step 7: Lint, format, type-check**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/ 2>&1 | tail -5
```
Expected: No errors. If mypy complains about `ET.Element` type, add `from xml.etree.ElementTree import Element as ETElement` and use it in the signature.

- [ ] **Step 8: Commit**

```bash
git add src/scholar_mcp/_standards_client.py src/scholar_mcp/_server_deps.py tests/test_standards_client.py
git commit -m "fix: replace dead NIST JSON endpoint with MODS XML from GitHub releases (#100)"
```

---

## Task 2: W3C — Fix broken response parsing and add stub caching

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` — rewrite `_W3CFetcher.search()`, add `_stubs` cache
- Modify: `tests/test_standards_client.py` — update W3C tests

**Background:** The W3C API at `https://api.w3.org/specifications` returns specs under `_links.specifications` (not `results` or `_embedded.specifications` as the current code expects). Each stub is `{"href": "...", "title": "..."}` only — no shortname or status. The `q=` param is **ignored** — it always returns all 1682 specs. Strategy: fetch all pages of stubs once, cache `{shortname, title}` in memory, filter client-side for `search()`, fetch full spec for top matches.

**W3C API actual response:**
```json
{
  "page": 1, "limit": 100, "pages": 17, "total": 1682,
  "_links": {
    "specifications": [
      {"href": "https://api.w3.org/specifications/WCAG21", "title": "Web Content..."}
    ]
  }
}
```
Shortname is the last path segment of `href`.

**Individual spec response (already works for `get()`):**
```json
{
  "shortname": "WCAG21",
  "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
  "description": "...",
  "series-version": "2.1",
  "_links": {
    "latest-version": {"href": "https://www.w3.org/TR/WCAG21/"},
    "latest-status": ...
  }
}
```
Note: `latest-status` is in `_links` as a sub-key, NOT at top level. Top level has `"latest-version"` as a URL string. Check both.

- [ ] **Step 1: Write failing tests for fixed W3C fetcher**

In `tests/test_standards_client.py`, replace the W3C test section (from `# W3C fetcher tests` to `# ETSI fetcher tests`) with:

```python
# ---------------------------------------------------------------------------
# W3C fetcher tests
# ---------------------------------------------------------------------------

W3C_API_BASE = "https://api.w3.org"

SAMPLE_W3C_SPEC = {
    "shortname": "WCAG21",
    "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
    "description": "Covers a wide range of recommendations for making Web content more accessible.",
    "series-version": "2.1",
    "latest-version": "https://www.w3.org/TR/WCAG21/",
    "latest-status": "Recommendation",
    "published": "2018-06-05",
    "_links": {
        "self": {"href": "https://api.w3.org/specifications/WCAG21"},
        "latest-version": {"href": "https://www.w3.org/TR/WCAG21/", "title": "Recommendation"},
    },
}

# Paginated stubs: 3 items across 2 pages for simplicity
SAMPLE_W3C_PAGE1 = {
    "page": 1, "limit": 2, "pages": 2, "total": 3,
    "_links": {
        "specifications": [
            {"href": "https://api.w3.org/specifications/WCAG21", "title": "Web Content Accessibility Guidelines (WCAG) 2.1"},
            {"href": "https://api.w3.org/specifications/html", "title": "HTML Standard"},
        ]
    },
}

SAMPLE_W3C_PAGE2 = {
    "page": 2, "limit": 2, "pages": 2, "total": 3,
    "_links": {
        "specifications": [
            {"href": "https://api.w3.org/specifications/webauthn-2", "title": "Web Authentication Level 2"},
        ]
    },
}


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_finds_wcag(respx_mock: respx.MockRouter) -> None:
    """search() finds WCAG by title match and returns full spec."""
    respx_mock.get("/specifications").mock(
        side_effect=lambda req: (
            httpx.Response(200, json=SAMPLE_W3C_PAGE1)
            if req.url.params.get("page") in (None, "1", "")
            else httpx.Response(200, json=SAMPLE_W3C_PAGE2)
        )
    )
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("WCAG", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "W3C"
    assert "WCAG" in results[0]["title"]
    assert results[0]["full_text_available"] is True


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_stubs_cached_on_second_call(
    respx_mock: respx.MockRouter,
) -> None:
    """Stubs are fetched only once; second search reuses in-memory cache."""
    page_call_count = 0

    def page_side_effect(req):
        nonlocal page_call_count
        page_call_count += 1
        return httpx.Response(200, json=SAMPLE_W3C_PAGE1)

    respx_mock.get("/specifications").mock(side_effect=page_side_effect)
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    await fetcher.search("WCAG", limit=1)
    await fetcher.search("WCAG", limit=1)
    await http.aclose()
    # stubs pages fetched only once
    assert page_call_count == 1


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get(respx_mock: respx.MockRouter) -> None:
    """get() fetches individual spec by shortname."""
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("WCAG 2.1")
    await http.aclose()
    assert record is not None
    assert record["body"] == "W3C"
    assert record["full_text_available"] is True
    assert record["full_text_url"] is not None
    assert "w3.org" in record["full_text_url"]


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_not_found(respx_mock: respx.MockRouter) -> None:
    """get() returns None for unknown identifier."""
    respx_mock.get("/specifications/UNKNOWNSPEC999").mock(
        return_value=httpx.Response(404)
    )
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("UNKNOWN SPEC 99.9")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search_non200_returns_empty(respx_mock: respx.MockRouter) -> None:
    """search() returns [] if stubs page returns non-200."""
    respx_mock.get("/specifications").mock(return_value=httpx.Response(503))
    http = httpx.AsyncClient(base_url=W3C_API_BASE)
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("WCAG", limit=5)
    await http.aclose()
    assert results == []
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run pytest tests/test_standards_client.py::test_w3c_search_finds_wcag -xvs 2>&1 | tail -10
```
Expected: FAIL.

- [ ] **Step 3: Rewrite `_W3CFetcher` in `_standards_client.py`**

Replace the entire `_W3CFetcher` class (keep `_W3C_API`, `_W3C_TR`, `_W3C_SHORTNAME_MAP` constants and `_normalize_w3c` function):

```python
class _W3CFetcher:
    """Fetches W3C specification metadata from the W3C API.

    On first search, downloads all specification stubs (paginated, ~1682 total)
    and caches them in memory as ``{shortname, title}`` pairs. Subsequent
    searches filter in-memory without network I/O.  Individual spec fetches
    via ``get()`` always hit the API directly.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~0.5s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter
        self._stubs: list[dict[str, str]] | None = None  # [{shortname, title}]
        self._lock = asyncio.Lock()

    def _to_shortname(self, identifier: str) -> str:
        """Convert a human-readable W3C identifier to an API shortname.

        Args:
            identifier: Human-readable identifier like "WCAG 2.1".

        Returns:
            API shortname like "WCAG21".
        """
        if identifier in _W3C_SHORTNAME_MAP:
            return _W3C_SHORTNAME_MAP[identifier]
        return re.sub(r"[\s.]", "", identifier)

    async def _ensure_stubs(self) -> list[dict[str, str]]:
        """Download all spec stubs (paginated) and cache in memory.

        Returns:
            List of ``{shortname, title}`` dicts.
        """
        if self._stubs is not None:
            return self._stubs
        async with self._lock:
            if self._stubs is not None:
                return self._stubs
            stubs: list[dict[str, str]] = []
            page = 1
            while True:
                await self._limiter.acquire()
                resp = await self._http.get(
                    f"{_W3C_API}/specifications",
                    params={"page": page, "limit": 100},
                )
                if resp.status_code != 200:
                    logger.warning(
                        "w3c_stubs_error status=%d page=%d", resp.status_code, page
                    )
                    break
                data = resp.json()
                page_specs = (
                    data.get("_links", {}).get("specifications") or []
                )
                for spec in page_specs:
                    href = spec.get("href", "")
                    shortname = href.rstrip("/").rsplit("/", 1)[-1]
                    title = spec.get("title", "")
                    if shortname:
                        stubs.append({"shortname": shortname, "title": title})
                pages = data.get("pages", 1)
                if page >= pages:
                    break
                page += 1
            self._stubs = stubs
            logger.info("w3c_stubs_cached count=%d", len(stubs))
        return self._stubs

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single W3C specification by identifier.

        Args:
            identifier: Human-readable identifier (e.g. "WCAG 2.1").

        Returns:
            Populated StandardRecord or None if not found.
        """
        shortname = self._to_shortname(identifier)
        await self._limiter.acquire()
        resp = await self._http.get(f"{_W3C_API}/specifications/{shortname}")
        if resp.status_code != 200:
            logger.warning(
                "w3c_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return None
        return _normalize_w3c(resp.json())

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search W3C specifications by keyword against cached stubs.

        Downloads all stubs on first call (paginated). Filters by title
        client-side, then fetches full spec objects for the top matches.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        stubs = await self._ensure_stubs()
        if not stubs:
            return []
        q = query.lower()
        matches = [
            s for s in stubs
            if q in s["title"].lower() or q in s["shortname"].lower()
        ][:limit]

        results: list[StandardRecord] = []
        for stub in matches:
            await self._limiter.acquire()
            resp = await self._http.get(
                f"{_W3C_API}/specifications/{stub['shortname']}"
            )
            if resp.status_code == 200:
                results.append(_normalize_w3c(resp.json()))
            else:
                logger.debug(
                    "w3c_spec_fetch_failed shortname=%s status=%d",
                    stub["shortname"],
                    resp.status_code,
                )
        return results
```

- [ ] **Step 4: Run W3C tests**

```bash
uv run pytest tests/test_standards_client.py -k "w3c" -xvs 2>&1 | tail -20
```
Expected: All 5 W3C tests pass.

- [ ] **Step 5: Lint, format, type-check, full suite**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/ && uv run pytest -x -q 2>&1 | tail -5
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py
git commit -m "fix: rewrite W3C fetcher to use _links.specifications and client-side search (#101)"
```

---

## Task 3: ETSI — Replace Cloudflare-blocked HTML scraper with JSON API

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` — rewrite `_ETSIFetcher`
- Modify: `tests/test_standards_client.py` — replace ETSI scraper tests with JSON API tests

**Background:** `https://www.etsi.org/standards-search/` is behind Cloudflare and returns 403 or challenge pages from a server. The real data source is a Joomla component endpoint that the search page's JavaScript uses:

```
GET https://www.etsi.org/?option=com_standardssearch&view=data&format=json
    &page=1&search=303+645&title=1&etsiNumber=1&content=1&version=0
    &published=1&onApproval=1&withdrawn=0&historical=0
    &isCurrent=1&superseded=0&startDate=1988-01-15&sort=1
```

**JSON response structure:**
```json
[
  {
    "RowNum": "1",
    "total_count": "2458",
    "wki_id": "69970",
    "TITLE": "CYBER; Cyber Security for Consumer Internet of Things: Baseline Requirements",
    "WKI_REFERENCE": "REN/CYBER-00127",
    "EDSpathname": "etsi_en/303600_303699/303645/03.01.03_60/",
    "EDSPDFfilename": "en_303645v030103p.pdf",
    "ETSI_DELIVERABLE": "ETSI EN 303 645 V3.1.3 (2024-09)",
    "STATUS_CODE": "12",
    "ACTION_TYPE": "PU",
    "IsCurrent": "0",
    "superseded": "0",
    "Scope": "Transposition of TS 103 645...",
    "TB": "Cyber Security",
    "Keywords": "Cybersecurity,IoT,privacy"
  }
]
```

PDF URL = `https://www.etsi.org/deliver/{EDSpathname}{EDSPDFfilename}`
`ACTION_TYPE`: "PU" → published, "WD" → withdrawn, else → draft.

- [ ] **Step 1: Write failing tests for new ETSI JSON API fetcher**

Replace the ETSI test section in `tests/test_standards_client.py` (from `# ETSI fetcher tests` to `# StandardsClient integration tests`) with:

```python
# ---------------------------------------------------------------------------
# ETSI fetcher tests (Joomla JSON API backend)
# ---------------------------------------------------------------------------

ETSI_BASE = "https://www.etsi.org"

SAMPLE_ETSI_JSON = [
    {
        "RowNum": "1",
        "total_count": "2",
        "wki_id": "69970",
        "TITLE": "CYBER; Cyber Security for Consumer Internet of Things: Baseline Requirements",
        "WKI_REFERENCE": "REN/CYBER-00127",
        "EDSpathname": "etsi_en/303600_303699/303645/03.01.03_60/",
        "EDSPDFfilename": "en_303645v030103p.pdf",
        "EDSARCfilename": "",
        "ETSI_DELIVERABLE": "ETSI EN 303 645 V3.1.3 (2024-09)",
        "STATUS_CODE": "12",
        "ACTION_TYPE": "PU",
        "IsCurrent": "0",
        "superseded": "0",
        "ReviewDate": None,
        "new_versions": "",
        "Scope": "Transposition of TS 103 645 v3.1.1 into an updated version.",
        "TB": "Cyber Security",
        "Keywords": "Cybersecurity,IoT,privacy",
    },
    {
        "RowNum": "2",
        "total_count": "2",
        "wki_id": "73702",
        "TITLE": "Cyber Security (CYBER); Guide to Cyber Security for Consumer IoT",
        "WKI_REFERENCE": "RTR/CYBER-00142",
        "EDSpathname": "etsi_tr/103600_103699/103621/02.01.01_60/",
        "EDSPDFfilename": "tr_103621v020101p.pdf",
        "EDSARCfilename": "",
        "ETSI_DELIVERABLE": "ETSI TR 103 621 V2.1.1 (2025-07)",
        "STATUS_CODE": "12",
        "ACTION_TYPE": "PU",
        "IsCurrent": "0",
        "superseded": "0",
        "ReviewDate": None,
        "new_versions": "",
        "Scope": None,
        "TB": "Cyber Security",
        "Keywords": "Cybersecurity,IoT",
    },
]

_ETSI_API_PATH = "/"  # Joomla root
_ETSI_API_PARAMS = {
    "option": "com_standardssearch",
    "view": "data",
    "format": "json",
}


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search(respx_mock: respx.MockRouter) -> None:
    """search() calls Joomla JSON API and returns parsed records."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "ETSI"
    assert "303 645" in results[0]["identifier"]
    assert results[0]["full_text_available"] is True
    assert "etsi.org/deliver" in (results[0]["full_text_url"] or "")


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_non200_returns_empty(respx_mock: respx.MockRouter) -> None:
    """search() returns [] on non-200."""
    respx_mock.get("/").mock(return_value=httpx.Response(403))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert results == []


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get(respx_mock: respx.MockRouter) -> None:
    """get() returns first result matching identifier."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 303 645")
    await http.aclose()
    assert record is not None
    assert record["body"] == "ETSI"
    assert record["full_text_available"] is True


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get_not_found(respx_mock: respx.MockRouter) -> None:
    """get() returns None when no match."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=[]))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 999 999")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_normalize_pdf_url(respx_mock: respx.MockRouter) -> None:
    """PDF URL constructed from EDSpathname + EDSPDFfilename."""
    respx_mock.get("/").mock(return_value=httpx.Response(200, json=SAMPLE_ETSI_JSON))
    http = httpx.AsyncClient(base_url=ETSI_BASE)
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=1)
    await http.aclose()
    expected_pdf = "https://www.etsi.org/deliver/etsi_en/303600_303699/303645/03.01.03_60/en_303645v030103p.pdf"
    assert results[0]["full_text_url"] == expected_pdf
    assert results[0]["url"] == expected_pdf
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run pytest tests/test_standards_client.py::test_etsi_search -xvs 2>&1 | tail -10
```
Expected: FAIL.

- [ ] **Step 3: Rewrite `_ETSIFetcher` in `_standards_client.py`**

Replace the `_ETSI_BASE`, `_ETSI_SEARCH` constants, the entire `_ETSIFetcher` class, and remove the BeautifulSoup import from ETSI (it was only used in `_scrape_catalogue`). Keep `_ETSI_RE` regex as it's used in `resolve_identifier_local`.

New constants:
```python
_ETSI_BASE = "https://www.etsi.org"
_ETSI_JOOMLA_PARAMS: dict[str, str | int] = {
    "option": "com_standardssearch",
    "view": "data",
    "format": "json",
    "version": "0",      # major versions only
    "published": "1",
    "onApproval": "1",
    "withdrawn": "0",
    "historical": "0",
    "isCurrent": "1",
    "superseded": "0",
    "startDate": "1988-01-15",
    "sort": "1",
    "title": "1",
    "etsiNumber": "1",
    "content": "1",
}
```

New `_ETSIFetcher`:
```python
class _ETSIFetcher:
    """Fetches ETSI standard metadata via the ETSI website Joomla JSON endpoint.

    Calls ``https://www.etsi.org/?option=com_standardssearch&view=data&format=json``
    which is the server-side AJAX endpoint backing the ETSI standards search page.
    This endpoint is not behind Cloudflare bot protection.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~1s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search ETSI standards by keyword.

        Args:
            query: Search string (e.g. "303 645", "IoT security").
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        await self._limiter.acquire()
        params = {**_ETSI_JOOMLA_PARAMS, "search": query, "page": 1}
        resp = await self._http.get(f"{_ETSI_BASE}/", params=params)
        if resp.status_code != 200:
            logger.warning(
                "etsi_api_error status=%d url=%s", resp.status_code, str(resp.url)
            )
            return []
        items: list[dict] = resp.json()  # type: ignore[type-arg]
        if not isinstance(items, list):
            logger.warning("etsi_api_unexpected_response type=%s", type(items).__name__)
            return []
        return [_normalize_etsi(item) for item in items[:limit]]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single ETSI standard by canonical identifier.

        Args:
            identifier: Canonical identifier (e.g. "ETSI EN 303 645").

        Returns:
            Populated StandardRecord or None if not found.
        """
        results = await self.search(identifier, limit=1)
        return results[0] if results else None
```

New `_normalize_etsi`:
```python
def _normalize_etsi(item: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a single ETSI Joomla API result item to a StandardRecord.

    Args:
        item: A single dict from the Joomla JSON API response array.

    Returns:
        Populated StandardRecord.
    """
    deliverable = item.get("ETSI_DELIVERABLE", "")
    title = item.get("TITLE", "")
    pathname = item.get("EDSpathname", "")
    pdffile = item.get("EDSPDFfilename", "")
    scope = item.get("Scope") or None
    keywords = item.get("Keywords") or None
    tb = item.get("TB") or None

    # Canonical identifier: "ETSI EN 303 645" from "ETSI EN 303 645 V3.1.3 (2024-09)"
    m = re.match(r"(ETSI\s+\w+\s+\d+\s+\d+)", deliverable)
    canonical = m.group(1) if m else deliverable.split(" V")[0].strip()

    # Version from deliverable string
    vm = re.search(r"V([\d.]+)\s+\((\d{4}-\d{2})\)", deliverable)
    version = vm.group(1) if vm else None
    pub_date = vm.group(2) if vm else None

    action_type = (item.get("ACTION_TYPE") or "").upper()
    if action_type == "PU":
        status = "published"
    elif action_type == "WD":
        status = "withdrawn"
    else:
        status = "published"

    pdf_url: str | None = None
    if pathname and pdffile:
        pdf_url = f"{_ETSI_BASE}/deliver/{pathname}{pdffile}"

    return StandardRecord(
        identifier=canonical,
        aliases=[deliverable] if deliverable != canonical else [],
        title=title,
        body="ETSI",
        number=re.sub(r"^ETSI\s+\w+\s+", "", canonical),
        revision=version,
        status=status,
        published_date=pub_date,
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=scope,
        committee=tb,
        url=pdf_url or f"{_ETSI_BASE}/standards",
        full_text_url=pdf_url,
        full_text_available=pdf_url is not None,
        price=None,
        related=[],
    )
```

Remove the `from bs4 import BeautifulSoup` import in `_ETSIFetcher._scrape_catalogue` since that method no longer exists.

- [ ] **Step 4: Run ETSI tests**

```bash
uv run pytest tests/test_standards_client.py -k "etsi" -xvs 2>&1 | tail -20
```
Expected: All 5 ETSI tests pass.

- [ ] **Step 5: Full suite, lint, type-check**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/ && uv run pytest -x -q 2>&1 | tail -5
```
Expected: All pass. Note: if `beautifulsoup4` was only used in `_ETSIFetcher`, mypy and tests will still pass since the import was inside the method. The dependency can remain in `pyproject.toml` — do NOT remove it (other code may use it).

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py
git commit -m "fix: replace ETSI HTML scraper with Joomla JSON API endpoint (#102)"
```

---

## Task 4: Patent PDF — Authenticated EPO download + URL interception

**Files:**
- Modify: `src/scholar_mcp/_epo_client.py` — add `get_pdf()` method
- Modify: `src/scholar_mcp/_tools_patent.py` — add `fetch_patent_pdf` tool
- Modify: `src/scholar_mcp/_tools_pdf.py` — add URL interception in `fetch_pdf_by_url`
- Modify: `tests/test_tools_patent.py` — add `fetch_patent_pdf` tests
- Modify: `tests/test_tools_pdf.py` — add URL interception test

**Background:**

EPO OPS PDF retrieval is a two-step process:
1. `client.published_data("publication", inp, endpoint="images")` → XML with image inquiry, contains a `link` attribute path like `published-data/images/EP.3491801.B1.20200101/pdf/`
2. `client.image(path=link_path, range=1, document_format="application/pdf")` → PDF bytes (first page only per call, but for whole-document PDFs `range=1` gets the full document)

The `python-epo-ops-client` library's `image()` call strips the base path prefix before making the request. The path comes from the inquiry XML `link` attribute.

`fetch_pdf_by_url` should intercept URLs matching `ops.epo.org` and return a helpful error redirecting to `fetch_patent_pdf`.

**EPO image inquiry XML structure (abbreviated):**
```xml
<ops:world-patent-data>
  <ops:document-inquiry ...>
    <ops:inquiry-result>
      <ops:document-instance desc="Drawing" ...>
        <ops:document-format .../>
      </ops:document-instance>
      <ops:document-instance desc="FullDocument" link="published-data/images/EP.3491801.B1.20200101/pdf/" number-of-pages="15">
        <ops:document-format desc="application/pdf"/>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>
```

- [ ] **Step 1: Write failing tests**

**In `tests/test_tools_patent.py`**, add at the end:

```python
# ---------------------------------------------------------------------------
# fetch_patent_pdf tests
# ---------------------------------------------------------------------------

def _make_image_inquiry_xml(link: str, pages: int = 5) -> bytes:
    """Build a minimal EPO image inquiry XML response."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns:exch="http://www.epo.org/exchange">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance desc="FullDocument" link="{link}" number-of-pages="{pages}">
        <ops:document-format desc="application/pdf"/>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>
""".encode()


def test_fetch_patent_pdf_no_epo_client(mcp: FastMCP) -> None:
    """Returns error when EPO is not configured."""
    import asyncio
    from fastmcp.client import Client

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "error" in data
    assert "epo" in data["error"].lower() or "configured" in data["error"].lower()


def test_fetch_patent_pdf_invalid_number(mcp_with_epo: FastMCP) -> None:
    """Returns error for unparseable patent number."""
    import asyncio
    from fastmcp.client import Client

    async def run():
        async with Client(mcp_with_epo) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "NOTAPATENT"}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "error" in data


def test_fetch_patent_pdf_queued(mcp_with_epo: FastMCP, bundle: ServiceBundle, tmp_path) -> None:
    """fetch_patent_pdf queues task and returns queued response."""
    import asyncio
    from fastmcp.client import Client
    from unittest.mock import MagicMock

    link_path = "published-data/images/EP.3491801.B1.20200101/pdf/"
    inquiry_xml = _make_image_inquiry_xml(link_path)

    mock_inquiry_resp = MagicMock()
    mock_inquiry_resp.content = inquiry_xml

    mock_pdf_resp = MagicMock()
    mock_pdf_resp.content = b"%PDF-1.4 fake pdf content"

    bundle.config = bundle.config.__class__(
        **{**bundle.config.__dict__, "cache_dir": tmp_path}
    )

    call_count = 0

    async def mock_get_pdf(doc):
        nonlocal call_count
        call_count += 1
        return b"%PDF-1.4 fake pdf content"

    bundle.epo.get_pdf = mock_get_pdf

    async def run():
        async with Client(mcp_with_epo) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    # Should return queued immediately (PDF tools always queue)
    assert data.get("queued") is True or "pdf_path" in data
    assert data.get("tool") == "fetch_patent_pdf" or "pdf_path" in data
```

Note: the `mcp_with_epo` fixture should already exist in `test_tools_patent.py`. If it doesn't, check the conftest or existing patent tests — there's typically a `bundle` fixture with EPO configured. Look at how `test_get_patent_returns_biblio` sets up its mock.

**In `tests/test_tools_pdf.py`**, add at the end:

```python
def test_fetch_pdf_by_url_intercepts_epo_url(mcp: FastMCP) -> None:
    """fetch_pdf_by_url returns helpful error for EPO OPS URLs."""
    import asyncio
    from fastmcp.client import Client

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "fetch_pdf_by_url",
                {"url": "https://ops.epo.org/rest-services/published-data/publication/epodoc/EP3491801B1/fulltext/pdf"},
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "error" in data
    assert "fetch_patent_pdf" in str(data).lower() or "epo" in str(data).lower()
```

- [ ] **Step 2: Verify tests fail**

```bash
uv run pytest tests/test_tools_patent.py::test_fetch_patent_pdf_no_epo_client tests/test_tools_pdf.py::test_fetch_pdf_by_url_intercepts_epo_url -xvs 2>&1 | tail -15
```
Expected: FAIL with `ToolError` or similar (tool doesn't exist yet).

- [ ] **Step 3: Add `get_pdf()` to `EpoClient`**

In `src/scholar_mcp/_epo_client.py`, add after `get_citations()`:

```python
async def get_pdf(self, doc: DocdbNumber) -> bytes:
    """Download full-document PDF for a patent via EPO OPS image service.

    Two-step process: first fetches the image inquiry to get the PDF link
    path, then downloads the PDF using that path.

    Args:
        doc: Patent number in DOCDB format.

    Returns:
        Raw PDF bytes.

    Raises:
        EpoRateLimitedError: When the EPO traffic light is not green.
        ValueError: If no PDF is available for this patent.
    """
    if self._is_service_throttled("retrieval"):
        cached = self._throttle_cache
        color = cached.get("retrieval", cached.get("_overall", "red"))
        if color == "black":
            raise RuntimeError(
                "EPO daily quota exhausted. Please try again tomorrow."
            )
        raise EpoRateLimitedError(color, service="retrieval")

    inp = self._to_docdb_input(doc)

    # Step 1: image inquiry to get the PDF link path
    async with self._lock:
        inquiry_resp = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="images",
        )
    self._check_throttle(inquiry_resp, service="retrieval")

    pdf_link = _parse_pdf_link(inquiry_resp.content)
    if pdf_link is None:
        raise ValueError(
            f"No PDF available for patent {doc.country}{doc.number}{doc.kind or ''}"
        )

    # Step 2: download the PDF
    if self._is_service_throttled("retrieval"):
        cached = self._throttle_cache
        color = cached.get("retrieval", cached.get("_overall", "red"))
        raise EpoRateLimitedError(color, service="retrieval")

    async with self._lock:
        pdf_resp = await asyncio.to_thread(
            self._client.image,
            pdf_link,
            range=1,
            document_format="application/pdf",
        )
    self._check_throttle(pdf_resp, service="retrieval")
    return pdf_resp.content
```

Also add the `_parse_pdf_link` helper (module-level, before `EpoClient`):

```python
def _parse_pdf_link(inquiry_xml: bytes) -> str | None:
    """Extract the FullDocument PDF link path from an EPO image inquiry response.

    Args:
        inquiry_xml: Raw XML bytes from ``published_data(..., endpoint='images')``.

    Returns:
        The ``link`` attribute value for the FullDocument PDF instance, or
        ``None`` if no PDF is available.
    """
    try:
        from lxml import etree

        root = etree.fromstring(inquiry_xml)
        ns = {
            "ops": "http://ops.epo.org",
        }
        for el in root.xpath(
            "//ops:document-instance[@desc='FullDocument']", namespaces=ns
        ):
            for fmt in el:
                if fmt.get("desc") == "application/pdf":
                    return el.get("link")
        return None
    except Exception as exc:
        logger.warning("epo_pdf_link_parse_failed err=%s", exc)
        return None
```

- [ ] **Step 4: Add `fetch_patent_pdf` tool to `_tools_patent.py`**

In `src/scholar_mcp/_tools_patent.py`, add the new tool after `get_patent` (before `register_patent_tools` closes). The tool follows the same pattern as `fetch_pdf_by_url` — always queues since PDF download is slow:

```python
    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        tags={"write"},
    )
    async def fetch_patent_pdf(
        patent_number: str,
        use_vlm: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Download a patent PDF via authenticated EPO OPS and convert to Markdown.

        Downloads the full-document PDF for a patent using the authenticated
        EPO Open Patent Services session, saves it locally, and if docling is
        configured converts it to Markdown.

        Not all patents have full text available via OPS — WO and older EP
        patents sometimes lack PDFs. Returns an error in that case.

        Args:
            patent_number: Patent number in any format (EP, WO, US, etc.),
                e.g. "EP3491801B1", "EP 3491801 B1", "US10123456B2".
            use_vlm: Use VLM enrichment for formulas and figures (requires
                VLM to be configured).

        Returns:
            JSON with ``pdf_path`` and optionally ``markdown`` / ``md_path``,
            or ``{"queued": true, "task_id": "...", "tool": "fetch_patent_pdf"}``
            while the download is in progress.
        """
        import hashlib
        import re
        from pathlib import Path

        if bundle.epo is None:
            return json.dumps(
                {
                    "error": "epo_not_configured",
                    "detail": "EPO OPS credentials are not set. Configure EPO_CONSUMER_KEY and EPO_CONSUMER_SECRET.",
                }
            )

        doc = normalize(patent_number)
        if doc is None:
            return json.dumps(
                {
                    "error": "invalid_patent_number",
                    "detail": f"Could not parse patent number: {patent_number!r}",
                }
            )

        stem = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
        url_hash = hashlib.sha256(patent_number.encode()).hexdigest()[:8]
        stem = f"patent_{stem}_{url_hash}"

        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{stem}.pdf"

        async def _execute() -> str:
            # Download if not cached
            if not pdf_path.exists():
                try:
                    pdf_bytes = await bundle.epo.get_pdf(doc)  # type: ignore[union-attr]
                except ValueError as exc:
                    return json.dumps(
                        {"error": "pdf_not_available", "detail": str(exc)}
                    )
                except (EpoRateLimitedError, RuntimeError) as exc:
                    raise
                await _asyncio.to_thread(pdf_path.write_bytes, pdf_bytes)
                logger.info(
                    "patent_pdf_downloaded path=%s bytes=%d",
                    pdf_path,
                    len(pdf_bytes),
                )

            result: dict[str, object] = {"pdf_path": str(pdf_path)}

            # Convert with docling if available
            if bundle.docling is None:
                return json.dumps(result)

            vlm_suffix = "_vlm" if use_vlm and bundle.docling.vlm_available else ""
            md_dir = bundle.config.cache_dir / "md"
            md_dir.mkdir(parents=True, exist_ok=True)
            md_path = md_dir / f"{stem}{vlm_suffix}.md"

            if md_path.exists():
                markdown = await _asyncio.to_thread(md_path.read_text, encoding="utf-8")
            else:
                try:
                    pdf_bytes_for_conv = await _asyncio.to_thread(pdf_path.read_bytes)
                    markdown = await bundle.docling.convert(
                        pdf_bytes_for_conv, pdf_path.name, use_vlm=use_vlm
                    )
                except Exception:
                    logger.exception("docling_convert_failed path=%s", pdf_path)
                    return json.dumps(result)
                await _asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

            result["markdown"] = markdown
            result["md_path"] = str(md_path)
            result["vlm_used"] = use_vlm and bundle.docling.vlm_available
            skip_reason = bundle.docling.vlm_skip_reason(use_vlm)
            if skip_reason:
                result["vlm_skip_reason"] = skip_reason
            return json.dumps(result)

        task_id = bundle.tasks.submit(
            _execute(), ttl=3600.0, tool="fetch_patent_pdf"
        )
        return json.dumps(
            {"queued": True, "task_id": task_id, "tool": "fetch_patent_pdf"}
        )
```

Add `"fetch_patent_pdf"` to the task TTL registry in `src/scholar_mcp/_tools_tasks.py`:
```python
# In the _TOOL_TTLS dict or equivalent — check the file for the pattern
"fetch_patent_pdf": (3600.0, "Patent PDF download and conversion"),
```

Check `_tools_tasks.py` for the actual pattern and add accordingly.

- [ ] **Step 5: Add URL interception in `fetch_pdf_by_url`**

In `src/scholar_mcp/_tools_pdf.py`, at the start of `fetch_pdf_by_url` (after the docstring, before the `if filename:` block), add:

```python
        # Intercept authenticated service URLs that need special handling
        _EPO_OPS_PATTERN = "ops.epo.org"
        if _EPO_OPS_PATTERN in url:
            return json.dumps({
                "error": "use_fetch_patent_pdf",
                "detail": (
                    "EPO OPS URLs require authenticated access. "
                    "Use the fetch_patent_pdf tool instead, passing the patent number "
                    "(e.g. fetch_patent_pdf('EP3491801B1'))."
                ),
            })
```

- [ ] **Step 6: Run patent PDF tests**

```bash
uv run pytest tests/test_tools_patent.py::test_fetch_patent_pdf_no_epo_client tests/test_tools_pdf.py::test_fetch_pdf_by_url_intercepts_epo_url -xvs 2>&1 | tail -20
```
Expected: Both pass.

- [ ] **Step 7: Full suite, lint, type-check**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/ && uv run pytest -x -q 2>&1 | tail -5
```
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add src/scholar_mcp/_epo_client.py src/scholar_mcp/_tools_patent.py src/scholar_mcp/_tools_pdf.py src/scholar_mcp/_tools_tasks.py tests/test_tools_patent.py tests/test_tools_pdf.py
git commit -m "feat: add fetch_patent_pdf tool with authenticated EPO download + URL interception (#103)"
```

---

## Final steps

- [ ] **Update docs**: Add `fetch_patent_pdf` to `README.md` patent tools section. Update `docs/configuration.md` if any new env vars were added (none for this feature set).

- [ ] **Open PR** targeting `main`.

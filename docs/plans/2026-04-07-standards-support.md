# Standards Support (v0.8.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tier 1 standards lookup (NIST, IETF, W3C, ETSI) to scholar-mcp via a unified `StandardsClient`, with three new MCP tools and optional full-text conversion via docling.

**Architecture:** A single `_standards_client.py` houses the identifier resolver, four source fetchers, and `StandardsClient` (which routes between them). `ServiceBundle` gains one `standards: StandardsClient` field. Three tools (`search_standards`, `get_standard`, `resolve_standard_identifier`) live in `_tools_standards.py` and follow the same cache-first/try-once/queue pattern as books and patents.

**Tech Stack:** Python 3.11+, httpx, aiosqlite, respx (tests), FastMCP, BeautifulSoup4 (ETSI scraping)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/scholar_mcp/_record_types.py` | Modify | Add `StandardRecord` TypedDict |
| `src/scholar_mcp/_cache.py` | Modify | Add 4 standards tables + 8 cache methods |
| `src/scholar_mcp/_protocols.py` | Modify | Add standards methods to `CacheProtocol` |
| `src/scholar_mcp/_standards_client.py` | Create | Resolver, 4 source fetchers, `StandardsClient` |
| `src/scholar_mcp/_tools_standards.py` | Create | `register_standards_tools` + 3 tools |
| `src/scholar_mcp/_server_deps.py` | Modify | Add `standards: StandardsClient` to `ServiceBundle` + lifespan |
| `src/scholar_mcp/_server_tools.py` | Modify | Call `register_standards_tools` |
| `tests/conftest.py` | Modify | Add `standards` to `ServiceBundle` fixture |
| `tests/test_cache_standards.py` | Create | Cache round-trip tests |
| `tests/test_standards_client.py` | Create | Resolver + fetcher unit tests |
| `tests/test_tools_standards.py` | Create | Tool integration tests |
| `docs/tools/index.md` | Modify | Document three new tools |

---

### Task 1: StandardRecord + cache schema + protocol

**Files:**
- Modify: `src/scholar_mcp/_record_types.py`
- Modify: `src/scholar_mcp/_cache.py`
- Modify: `src/scholar_mcp/_protocols.py`
- Create: `tests/test_cache_standards.py`

- [ ] **Step 1: Write failing cache tests**

```python
# tests/test_cache_standards.py
"""Tests for standards cache tables."""

from __future__ import annotations

from scholar_mcp._cache import ScholarCache

SAMPLE_STANDARD: dict = {
    "identifier": "RFC 9000",
    "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
    "body": "IETF",
    "number": "9000",
    "status": "published",
    "full_text_available": True,
    "url": "https://www.rfc-editor.org/rfc/rfc9000",
}


async def test_get_standard_miss(cache: ScholarCache) -> None:
    result = await cache.get_standard("RFC 9000")
    assert result is None


async def test_set_and_get_standard(cache: ScholarCache) -> None:
    await cache.set_standard("RFC 9000", SAMPLE_STANDARD)
    result = await cache.get_standard("RFC 9000")
    assert result is not None
    assert result["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"


async def test_get_standard_alias_miss(cache: ScholarCache) -> None:
    result = await cache.get_standard_alias("rfc9000")
    assert result is None


async def test_set_and_get_standard_alias(cache: ScholarCache) -> None:
    await cache.set_standard_alias("rfc9000", "RFC 9000")
    result = await cache.get_standard_alias("rfc9000")
    assert result == "RFC 9000"


async def test_get_standards_search_miss(cache: ScholarCache) -> None:
    result = await cache.get_standards_search("quic transport")
    assert result is None


async def test_set_and_get_standards_search(cache: ScholarCache) -> None:
    await cache.set_standards_search("quic transport", [SAMPLE_STANDARD])
    result = await cache.get_standards_search("quic transport")
    assert result is not None
    assert len(result) == 1
    assert result[0]["identifier"] == "RFC 9000"


async def test_get_standards_index_miss(cache: ScholarCache) -> None:
    result = await cache.get_standards_index("ETSI")
    assert result is None


async def test_set_and_get_standards_index(cache: ScholarCache) -> None:
    stubs = [{"identifier": "ETSI EN 303 645", "title": "IoT Cyber Security", "url": "https://etsi.org"}]
    await cache.set_standards_index("ETSI", stubs)
    result = await cache.get_standards_index("ETSI")
    assert result is not None
    assert result[0]["identifier"] == "ETSI EN 303 645"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_cache_standards.py -v
```
Expected: `AttributeError: 'ScholarCache' object has no attribute 'get_standard'`

- [ ] **Step 3: Add `StandardRecord` to `_record_types.py`**

At the bottom of `src/scholar_mcp/_record_types.py`, after `BookRecord`:

```python
class StandardRecord(TypedDict, total=False):
    """Typed representation of a normalised standards record.

    All fields use ``total=False`` because records are JSON-serialised
    and may have absent fields from partial API responses or cache.
    """

    identifier: str           # canonical: "NIST SP 800-53 Rev. 5", "RFC 9000"
    aliases: list[str]        # alt forms seen in citations
    title: str
    body: str                 # "NIST" | "IETF" | "W3C" | "ETSI"
    number: str               # "800-53", "9000", "2.1"
    revision: str | None      # "Rev. 5", "2022", "3rd edition"
    status: str               # "published" | "withdrawn" | "superseded" | "draft"
    published_date: str | None
    withdrawn_date: str | None
    superseded_by: str | None
    supersedes: list[str]
    scope: str | None         # abstract / scope statement
    committee: str | None
    url: str                  # canonical catalogue URL
    full_text_url: str | None # direct PDF/HTML link if freely available
    full_text_available: bool # True for all Tier 1 sources
    price: str | None         # None for Tier 1; populated for Tier 2
    related: list[str]        # related standard identifiers
```

- [ ] **Step 4: Add standards tables + TTLs to `_cache.py`**

Add TTL constants after the existing `_BOOK_SUBJECT_TTL` line:

```python
_STANDARD_TTL = 90 * 86400        # 90 days — standards rarely change
_STANDARD_ALIAS_TTL = 90 * 86400  # 90 days
_STANDARD_SEARCH_TTL = 7 * 86400  # 7 days
_STANDARD_INDEX_TTL = 7 * 86400   # 7 days — re-scrape weekly
```

Add to `_SCHEMA` string (append before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS standards (
    identifier TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_cached ON standards(cached_at);

CREATE TABLE IF NOT EXISTS standards_aliases (
    raw_id     TEXT PRIMARY KEY,
    canonical  TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_aliases_cached ON standards_aliases(cached_at);

CREATE TABLE IF NOT EXISTS standards_search (
    query_hash TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_search_cached ON standards_search(cached_at);

CREATE TABLE IF NOT EXISTS standards_index (
    body      TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_index_cached ON standards_index(cached_at);
```

Add all four tables to `_TTL_TABLES`:

```python
_TTL_TABLES = (
    "papers",
    "citations",
    "refs",
    "authors",
    "openalex",
    "patents",
    "patent_claims",
    "patent_descriptions",
    "patent_families",
    "patent_legal",
    "patent_citations",
    "patent_search",
    "books_isbn",
    "books_openlibrary",
    "books_search",
    "books_subject",
    "standards",
    "standards_aliases",
    "standards_search",
    "standards_index",
)
```

Add eight cache methods to `ScholarCache` (after the books section):

```python
# ------------------------------------------------------------------
# Standards
# ------------------------------------------------------------------

async def get_standard(self, identifier: str) -> dict[str, Any] | None:
    """Return cached standard record or None if missing/stale.

    Args:
        identifier: Canonical standard identifier.

    Returns:
        StandardRecord dict or None.
    """
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM standards WHERE identifier = ?", (identifier,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or time.time() - row[1] > _STANDARD_TTL:
        return None
    return json.loads(row[0])  # type: ignore[no-any-return]

async def set_standard(self, identifier: str, data: dict[str, Any]) -> None:
    """Cache a standard record.

    Args:
        identifier: Canonical standard identifier.
        data: StandardRecord dict.
    """
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO standards (identifier, data, cached_at) VALUES (?, ?, ?)",
        (identifier, json.dumps(data), time.time()),
    )
    await db.commit()

async def get_standard_alias(self, raw: str) -> str | None:
    """Return canonical identifier for a raw alias string, or None.

    Args:
        raw: Raw alias string (e.g. ``"rfc9000"``).

    Returns:
        Canonical identifier string or None.
    """
    db = _require_open(self._db)
    async with db.execute(
        "SELECT canonical, cached_at FROM standards_aliases WHERE raw_id = ?", (raw,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or time.time() - row[1] > _STANDARD_ALIAS_TTL:
        return None
    return row[0]  # type: ignore[no-any-return]

async def set_standard_alias(self, raw: str, canonical: str) -> None:
    """Cache a raw-to-canonical alias mapping.

    Args:
        raw: Raw alias string.
        canonical: Canonical identifier.
    """
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO standards_aliases (raw_id, canonical, cached_at) VALUES (?, ?, ?)",
        (raw, canonical, time.time()),
    )
    await db.commit()

async def get_standards_search(self, query: str) -> list[dict[str, Any]] | None:
    """Return cached standards search results or None if missing/stale.

    Args:
        query: Search query string; SHA-256 hash used as cache key.

    Returns:
        List of StandardRecord dicts or None.
    """
    db = _require_open(self._db)
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    async with db.execute(
        "SELECT data, cached_at FROM standards_search WHERE query_hash = ?",
        (query_hash,),
    ) as cur:
        row = await cur.fetchone()
    if row is None or time.time() - row[1] > _STANDARD_SEARCH_TTL:
        return None
    return json.loads(row[0])  # type: ignore[no-any-return]

async def set_standards_search(self, query: str, data: list[dict[str, Any]]) -> None:
    """Cache standards search results.

    Args:
        query: Search query string.
        data: List of StandardRecord dicts.
    """
    db = _require_open(self._db)
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    await db.execute(
        "INSERT OR REPLACE INTO standards_search (query_hash, data, cached_at) VALUES (?, ?, ?)",
        (query_hash, json.dumps(data), time.time()),
    )
    await db.commit()

async def get_standards_index(self, body: str) -> list[dict[str, Any]] | None:
    """Return cached standards catalogue index for a body, or None if stale.

    Args:
        body: Standards body name (e.g. ``"ETSI"``).

    Returns:
        List of stub dicts (identifier, title, url) or None.
    """
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM standards_index WHERE body = ?", (body,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or time.time() - row[1] > _STANDARD_INDEX_TTL:
        return None
    return json.loads(row[0])  # type: ignore[no-any-return]

async def set_standards_index(self, body: str, data: list[dict[str, Any]]) -> None:
    """Cache a standards catalogue index for a body.

    Args:
        body: Standards body name.
        data: List of stub dicts (identifier, title, url).
    """
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO standards_index (body, data, cached_at) VALUES (?, ?, ?)",
        (body, json.dumps(data), time.time()),
    )
    await db.commit()
```

- [ ] **Step 5: Add standards methods to `CacheProtocol` in `_protocols.py`**

After the Book methods block, add:

```python
    # Standards methods
    async def get_standard(self, identifier: str) -> dict[str, Any] | None: ...
    async def set_standard(self, identifier: str, data: dict[str, Any]) -> None: ...
    async def get_standard_alias(self, raw: str) -> str | None: ...
    async def set_standard_alias(self, raw: str, canonical: str) -> None: ...
    async def get_standards_search(self, query: str) -> list[dict[str, Any]] | None: ...
    async def set_standards_search(self, query: str, data: list[dict[str, Any]]) -> None: ...
    async def get_standards_index(self, body: str) -> list[dict[str, Any]] | None: ...
    async def set_standards_index(self, body: str, data: list[dict[str, Any]]) -> None: ...
```

Also add `StandardRecord` import to `_protocols.py` — actually it is not needed for the protocol methods (they use `dict[str, Any]`). Keep `_protocols.py` imports as-is.

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_cache_standards.py -v
```
Expected: all 8 tests PASS

- [ ] **Step 7: Run full test suite to confirm no regressions**

```
pytest --tb=short -q
```
Expected: all existing tests still PASS

- [ ] **Step 8: Commit**

```bash
git add src/scholar_mcp/_record_types.py src/scholar_mcp/_cache.py src/scholar_mcp/_protocols.py tests/test_cache_standards.py
git commit -m "feat: add StandardRecord TypedDict and standards cache tables"
```

---

### Task 2: Identifier resolver (local regex, no network)

**Files:**
- Create: `src/scholar_mcp/_standards_client.py` (skeleton + resolver only)
- Create: `tests/test_standards_client.py` (resolver tests only)

- [ ] **Step 1: Write failing resolver tests**

```python
# tests/test_standards_client.py
"""Tests for StandardsClient, source fetchers, and identifier resolver."""

from __future__ import annotations

import pytest

from scholar_mcp._standards_client import _resolve_identifier_local


# --- Resolver: IETF ---

def test_resolve_rfc_with_space() -> None:
    result = _resolve_identifier_local("RFC 9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_no_space() -> None:
    result = _resolve_identifier_local("rfc9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_hyphen() -> None:
    result = _resolve_identifier_local("rfc-9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_tls() -> None:
    result = _resolve_identifier_local("RFC 8446")
    assert result == ("RFC 8446", "IETF")


# --- Resolver: NIST SP ---

def test_resolve_nist_sp_full() -> None:
    result = _resolve_identifier_local("NIST SP 800-53 Rev. 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_abbreviated_rev() -> None:
    result = _resolve_identifier_local("SP800-53r5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_space_rev() -> None:
    result = _resolve_identifier_local("nist 800-53 rev 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_no_rev() -> None:
    result = _resolve_identifier_local("NIST SP 800-53")
    assert result == ("NIST SP 800-53", "NIST")


def test_resolve_nist_fips() -> None:
    result = _resolve_identifier_local("FIPS 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nist_fips_no_space() -> None:
    result = _resolve_identifier_local("FIPS140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir() -> None:
    result = _resolve_identifier_local("NISTIR 8259A")
    assert result == ("NISTIR 8259A", "NIST")


# --- Resolver: W3C ---

def test_resolve_wcag_with_prefix() -> None:
    result = _resolve_identifier_local("W3C WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_prefix() -> None:
    result = _resolve_identifier_local("WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_space() -> None:
    result = _resolve_identifier_local("WCAG2.1")
    assert result == ("WCAG 2.1", "W3C")


# --- Resolver: ETSI ---

def test_resolve_etsi_en_with_spaces() -> None:
    result = _resolve_identifier_local("ETSI EN 303 645")
    assert result == ("ETSI EN 303 645", "ETSI")


def test_resolve_etsi_en_no_spaces() -> None:
    result = _resolve_identifier_local("etsi en 303645")
    assert result == ("ETSI EN 303 645", "ETSI")


# --- Resolver: unrecognised ---

def test_resolve_unknown_returns_none() -> None:
    result = _resolve_identifier_local("some random text")
    assert result is None


def test_resolve_iec_series_returns_none() -> None:
    # IEC 62443 is Tier 2 — not handled by local Tier 1 resolver
    result = _resolve_identifier_local("62443")
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_standards_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'scholar_mcp._standards_client'`

- [ ] **Step 3: Create `_standards_client.py` with resolver only**

```python
# src/scholar_mcp/_standards_client.py
"""Standards lookup client: identifier resolver, source fetchers, StandardsClient."""

from __future__ import annotations

import re
import logging
from typing import TYPE_CHECKING

import httpx

from ._rate_limiter import RateLimiter
from ._record_types import StandardRecord

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns for local identifier resolution
# ---------------------------------------------------------------------------

# IETF RFC: "RFC 9000", "rfc9000", "rfc-9000", "RFC9000"
_IETF_RFC_RE = re.compile(r"(?i)\brfc[-\s]?(\d+)\b")

# NIST SP with optional revision: "SP 800-53 Rev. 5", "SP800-53r5", "NIST SP 800-53 Rev 5"
_NIST_SP_REV_RE = re.compile(
    r"(?i)\b(?:nist\s+)?sp\s*(\d{3,4}(?:-\d+)?[A-Z]?)\s*r(?:ev\.?\s*)?(\d)\b"
)
# NIST SP without revision: "NIST SP 800-53", "SP800-53", "nist 800-53"
_NIST_SP_RE = re.compile(
    r"(?i)\b(?:nist\s+)?sp\s*(\d{3,4}(?:-\d+)?[A-Z]?)\b"
)
# NIST SP shorthand: "nist 800-53 rev 5" (number only after "nist")
_NIST_NUM_REV_RE = re.compile(
    r"(?i)\bnist\s+(\d{3,4}(?:-\d+)?)\s+r(?:ev\.?\s*)?(\d)\b"
)
_NIST_NUM_RE = re.compile(r"(?i)\bnist\s+(\d{3,4}(?:-\d+)?)\b")
# NIST FIPS: "FIPS 140-3", "FIPS140-3"
_NIST_FIPS_RE = re.compile(r"(?i)\bfips\s*(\d{2,3}(?:-\d+)?)\b")
# NIST IR: "NISTIR 8259A"
_NIST_IR_RE = re.compile(r"(?i)\bnistir\s+(\d{4}[A-Z]?)\b")

# W3C: "WCAG 2.1", "WCAG2.1", "W3C WCAG 2.1", "WebAuthn Level 2"
_W3C_WCAG_RE = re.compile(r"(?i)\bwcag\s*(\d+\.\d+)\b")
_W3C_WEBAUTHN_RE = re.compile(r"(?i)\bwebauthn\s+level\s+(\d+)\b")

# ETSI: "ETSI EN 303 645", "etsi en 303645", "ETSI TS 102 165"
_ETSI_RE = re.compile(r"(?i)\b(?:etsi\s+)?(EN|TS|TR|ES|EG)\s*(\d{3})\s*[\s-]?\s*(\d{3})\b")


def _resolve_identifier_local(raw: str) -> tuple[str, str] | None:
    """Attempt to resolve *raw* to (canonical_identifier, body) using only regex.

    Returns ``None`` when no Tier 1 pattern matches.

    Args:
        raw: Raw citation string from a paper reference.

    Returns:
        Tuple of (canonical_identifier, body) or None.
    """
    s = raw.strip()

    # IETF RFC (check before NIST to avoid "RFC" matching NIST patterns)
    m = _IETF_RFC_RE.search(s)
    if m:
        return f"RFC {int(m.group(1))}", "IETF"

    # NIST FIPS
    m = _NIST_FIPS_RE.search(s)
    if m:
        return f"FIPS {m.group(1)}", "NIST"

    # NIST IR
    m = _NIST_IR_RE.search(s)
    if m:
        return f"NISTIR {m.group(1).upper()}", "NIST"

    # NIST SP with revision (must check before without-revision to capture rev)
    m = _NIST_SP_REV_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)} Rev. {m.group(2)}", "NIST"

    # NIST SP without revision
    m = _NIST_SP_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)}", "NIST"

    # NIST shorthand with revision: "nist 800-53 rev 5"
    m = _NIST_NUM_REV_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)} Rev. {m.group(2)}", "NIST"

    # NIST shorthand without revision: "nist 800-53"
    m = _NIST_NUM_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)}", "NIST"

    # W3C WCAG
    m = _W3C_WCAG_RE.search(s)
    if m:
        return f"WCAG {m.group(1)}", "W3C"

    # W3C WebAuthn
    m = _W3C_WEBAUTHN_RE.search(s)
    if m:
        return f"WebAuthn Level {m.group(1)}", "W3C"

    # ETSI
    m = _ETSI_RE.search(s)
    if m:
        return f"ETSI {m.group(1).upper()} {m.group(2)} {m.group(3)}", "ETSI"

    return None
```

- [ ] **Step 4: Run resolver tests to verify they pass**

```
pytest tests/test_standards_client.py -v
```
Expected: all resolver tests PASS

- [ ] **Step 5: Run full test suite**

```
pytest --tb=short -q
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py
git commit -m "feat: add standards identifier resolver with Tier 1 regex patterns"
```

---

### Task 3: IETF source fetcher

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` (add `_IETFFetcher`)
- Modify: `tests/test_standards_client.py` (add IETF fetcher tests)

- [ ] **Step 1: Write failing IETF fetcher tests**

Append to `tests/test_standards_client.py`:

```python
import httpx
import respx

from scholar_mcp._standards_client import _IETFFetcher
from scholar_mcp._rate_limiter import RateLimiter

IETF_BASE = "https://datatracker.ietf.org"
RFC_EDITOR_BASE = "https://www.rfc-editor.org"

SAMPLE_RFC9000_DOC = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "abstract": "This document defines QUIC.",
            "std_level": "proposed_standard",
            "pub_date": "2021-05-01",
            "resource_uri": "/api/v1/doc/document/rfc9000/",
        }
    ],
    "meta": {"total_count": 1},
}

SAMPLE_RFC9000_SEARCH = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "std_level": "proposed_standard",
            "pub_date": "2021-05-01",
            "resource_uri": "/api/v1/doc/document/rfc9000/",
        }
    ],
    "meta": {"total_count": 1},
}


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_rfc(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_DOC)
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 9000")
    await http.aclose()
    assert record is not None
    assert record["identifier"] == "RFC 9000"
    assert record["body"] == "IETF"
    assert record["number"] == "9000"
    assert record["full_text_available"] is True
    assert "rfc-editor.org" in record["full_text_url"]


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_get_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json={"objects": [], "meta": {"total_count": 0}})
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("RFC 99999")
    await http.aclose()
    assert record is None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_ietf_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _IETFFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("QUIC transport", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "RFC 9000"
```

- [ ] **Step 2: Run tests to confirm failure**

```
pytest tests/test_standards_client.py::test_ietf_get_rfc -v
```
Expected: `ImportError` or `AttributeError` — `_IETFFetcher` not defined yet

- [ ] **Step 3: Add `_IETFFetcher` to `_standards_client.py`**

After the resolver function, add:

```python
# ---------------------------------------------------------------------------
# IETF source fetcher
# ---------------------------------------------------------------------------

_IETF_DATATRACKER = "https://datatracker.ietf.org"
_RFC_EDITOR_BASE = "https://www.rfc-editor.org"
_IETF_DELAY = 0.5  # ~120 req/min politeness


class _IETFFetcher:
    """Fetches RFC metadata from the IETF Datatracker REST API.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~0.5s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single RFC by identifier (e.g. "RFC 9000").

        Args:
            identifier: Canonical RFC identifier.

        Returns:
            Populated StandardRecord or None if not found.
        """
        m = re.match(r"(?i)rfc\s*(\d+)", identifier)
        if not m:
            return None
        n = int(m.group(1))
        await self._limiter.wait()
        resp = await self._http.get(
            f"{_IETF_DATATRACKER}/api/v1/doc/document/",
            params={"name": f"rfc{n:04d}", "format": "json"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        objects = data.get("objects") or []
        if not objects:
            return None
        return _normalize_ietf(objects[0])

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search RFCs by title keyword.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        await self._limiter.wait()
        resp = await self._http.get(
            f"{_IETF_DATATRACKER}/api/v1/doc/document/",
            params={
                "type": "rfc",
                "title__icontains": query,
                "format": "json",
                "limit": limit,
            },
        )
        if resp.status_code != 200:
            return []
        objects = (resp.json().get("objects") or [])[:limit]
        return [_normalize_ietf(obj) for obj in objects]


def _normalize_ietf(obj: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a Datatracker document object to a StandardRecord.

    Args:
        obj: Raw Datatracker ``/api/v1/doc/document/`` object.

    Returns:
        Populated StandardRecord.
    """
    name = obj.get("name", "")  # e.g. "rfc9000"
    n = re.sub(r"[^\d]", "", name)
    identifier = f"RFC {int(n)}" if n else name.upper()
    return StandardRecord(
        identifier=identifier,
        aliases=[name, name.upper().replace("RFC", "RFC ")],
        title=obj.get("title", ""),
        body="IETF",
        number=n,
        revision=None,
        status=_map_ietf_status(obj.get("std_level", "")),
        published_date=obj.get("pub_date"),
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=obj.get("abstract"),
        committee=obj.get("group", {}).get("acronym") if isinstance(obj.get("group"), dict) else None,
        url=f"{_RFC_EDITOR_BASE}/info/rfc{n}",
        full_text_url=f"{_RFC_EDITOR_BASE}/rfc/rfc{n}.html",
        full_text_available=True,
        price=None,
        related=[],
    )


def _map_ietf_status(std_level: str) -> str:
    """Map IETF std_level to a human-readable status string.

    Args:
        std_level: Datatracker std_level value.

    Returns:
        Status string: "published", "draft", or "informational".
    """
    mapping = {
        "proposed_standard": "published",
        "draft_standard": "published",
        "internet_standard": "published",
        "informational": "published",
        "experimental": "published",
        "best_current_practice": "published",
        "historic": "withdrawn",
        "unknown": "draft",
        "": "published",
    }
    return mapping.get(std_level.lower(), "published")
```

- [ ] **Step 4: Run IETF fetcher tests**

```
pytest tests/test_standards_client.py -k "ietf" -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py
git commit -m "feat: add IETF RFC source fetcher"
```

---

### Task 4: NIST source fetcher

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` (add `_NISTFetcher`)
- Modify: `tests/test_standards_client.py` (add NIST tests)

- [ ] **Step 1: Write failing NIST fetcher tests**

Append to `tests/test_standards_client.py`:

```python
from scholar_mcp._standards_client import _NISTFetcher

NIST_BASE = "https://csrc.nist.gov"

SAMPLE_NIST_SEARCH = [
    {
        "docIdentifier": "SP 800-53 Rev. 5",
        "title": "Security and Privacy Controls for Information Systems and Organizations",
        "abstract": "This publication provides a catalog of security and privacy controls.",
        "status": "Final",
        "publicationDate": "2020-09-23",
        "doiUrl": "https://doi.org/10.6028/NIST.SP.800-53r5",
        "doi": "10.6028/NIST.SP.800-53r5",
        "pdfUrl": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf",
        "series": "Special Publication (SP)",
        "number": "800-53",
        "revisionNumber": "5",
        "family": "",
    }
]


@pytest.mark.respx(base_url=NIST_BASE)
async def test_nist_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/CSRC/media/Publications/search-results-json-file/json").mock(
        return_value=httpx.Response(200, json=SAMPLE_NIST_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("800-53", limit=5)
    await http.aclose()
    assert len(results) == 1
    assert results[0]["identifier"] == "NIST SP 800-53 Rev. 5"
    assert results[0]["body"] == "NIST"
    assert results[0]["full_text_available"] is True


@pytest.mark.respx(base_url=NIST_BASE)
async def test_nist_get(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/CSRC/media/Publications/search-results-json-file/json").mock(
        return_value=httpx.Response(200, json=SAMPLE_NIST_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("NIST SP 800-53 Rev. 5")
    await http.aclose()
    assert record is not None
    assert record["number"] == "800-53"
    assert record["revision"] == "Rev. 5"
    assert "nvlpubs.nist.gov" in record["full_text_url"]


@pytest.mark.respx(base_url=NIST_BASE)
async def test_nist_get_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/CSRC/media/Publications/search-results-json-file/json").mock(
        return_value=httpx.Response(200, json=[])
    )
    http = httpx.AsyncClient()
    fetcher = _NISTFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("NIST SP 999-99")
    await http.aclose()
    assert record is None
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_standards_client.py -k "nist" -v
```
Expected: `ImportError` — `_NISTFetcher` not defined

- [ ] **Step 3: Add `_NISTFetcher` to `_standards_client.py`**

After `_IETFFetcher`:

```python
# ---------------------------------------------------------------------------
# NIST source fetcher
# ---------------------------------------------------------------------------

_NIST_BASE = "https://csrc.nist.gov"
_NIST_PUBLICATIONS_JSON = "/CSRC/media/Publications/search-results-json-file/json"
_NIST_DELAY = 1.0  # 1 req/s politeness


class _NISTFetcher:
    """Fetches NIST CSRC publication metadata.

    Uses the NIST CSRC publications JSON endpoint as a searchable catalogue.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~1s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    async def _fetch_all(self) -> list[dict]:  # type: ignore[type-arg]
        """Fetch the full NIST publications JSON catalogue.

        Returns:
            Raw list of publication objects from CSRC.
        """
        await self._limiter.wait()
        resp = await self._http.get(f"{_NIST_BASE}{_NIST_PUBLICATIONS_JSON}")
        if resp.status_code != 200:
            return []
        data = resp.json()
        # The endpoint may return a list directly or a wrapped object
        if isinstance(data, list):
            return data
        return data.get("response", data.get("publications", []))

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
            p for p in all_pubs
            if q in (p.get("docIdentifier") or "").lower()
            or q in (p.get("title") or "").lower()
            or q in (p.get("number") or "").lower()
        ]
        return [_normalize_nist(p) for p in matches[:limit]]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single NIST publication by canonical identifier.

        Searches the catalogue and returns the first exact or close match.

        Args:
            identifier: Canonical NIST identifier (e.g. "NIST SP 800-53 Rev. 5").

        Returns:
            Populated StandardRecord or None if not found.
        """
        all_pubs = await self._fetch_all()
        id_lower = identifier.lower()
        for pub in all_pubs:
            doc_id = (pub.get("docIdentifier") or "").lower()
            if doc_id == id_lower or doc_id in id_lower or id_lower in doc_id:
                return _normalize_nist(pub)
        return None


def _normalize_nist(pub: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a NIST CSRC publication object to a StandardRecord.

    Args:
        pub: Raw publication object from the CSRC JSON feed.

    Returns:
        Populated StandardRecord.
    """
    doc_id = pub.get("docIdentifier", "")
    series = pub.get("series", "")
    number = pub.get("number", "")
    rev = pub.get("revisionNumber", "")

    # Build canonical identifier
    if "SP" in series or "Special Publication" in series:
        canonical = f"NIST SP {number}"
        if rev:
            canonical += f" Rev. {rev}"
    elif "FIPS" in series:
        canonical = f"FIPS {number}"
    elif "NISTIR" in series or "Interagency" in series:
        canonical = f"NISTIR {number}"
    else:
        canonical = doc_id or f"NIST {number}"

    pdf_url: str | None = pub.get("pdfUrl") or pub.get("doiUrl")
    status_raw = (pub.get("status") or "").lower()
    status = "published" if "final" in status_raw else "draft" if "draft" in status_raw else "published"

    return StandardRecord(
        identifier=canonical,
        aliases=[doc_id] if doc_id and doc_id != canonical else [],
        title=pub.get("title", ""),
        body="NIST",
        number=number,
        revision=f"Rev. {rev}" if rev else None,
        status=status,
        published_date=pub.get("publicationDate"),
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=pub.get("abstract"),
        committee=None,
        url=pub.get("doiUrl") or f"{_NIST_BASE}/publications/detail/{number}",
        full_text_url=pdf_url,
        full_text_available=pdf_url is not None,
        price=None,
        related=[],
    )
```

- [ ] **Step 4: Run NIST tests**

```
pytest tests/test_standards_client.py -k "nist" -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py
git commit -m "feat: add NIST CSRC source fetcher"
```

---

### Task 5: W3C source fetcher

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` (add `_W3CFetcher`)
- Modify: `tests/test_standards_client.py` (add W3C tests)

- [ ] **Step 1: Write failing W3C tests**

Append to `tests/test_standards_client.py`:

```python
from scholar_mcp._standards_client import _W3CFetcher

W3C_API_BASE = "https://api.w3.org"

SAMPLE_W3C_SPEC = {
    "shortname": "WCAG21",
    "title": "Web Content Accessibility Guidelines (WCAG) 2.1",
    "description": "Covers a wide range of recommendations for making Web content more accessible.",
    "status": "Recommendation",
    "_links": {
        "self": {"href": "https://api.w3.org/specifications/WCAG21"},
        "latest-version": {"href": "https://www.w3.org/TR/WCAG21/"},
    },
    "latest-version": "https://www.w3.org/TR/WCAG21/",
    "latest-status": "Recommendation",
    "published": "2018-06-05",
}

SAMPLE_W3C_SEARCH = {
    "results": [SAMPLE_W3C_SPEC],
    "pages": 1,
    "total": 1,
}


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/specifications").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SEARCH)
    )
    http = httpx.AsyncClient()
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("WCAG 2.1", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "W3C"
    assert "WCAG" in results[0]["title"]


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/specifications/WCAG21").mock(
        return_value=httpx.Response(200, json=SAMPLE_W3C_SPEC)
    )
    http = httpx.AsyncClient()
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("WCAG 2.1")
    await http.aclose()
    assert record is not None
    assert record["body"] == "W3C"
    assert record["full_text_available"] is True
    assert "w3.org/TR" in record["full_text_url"]


@pytest.mark.respx(base_url=W3C_API_BASE)
async def test_w3c_get_not_found(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/specifications/UNKNOWNSPEC").mock(
        return_value=httpx.Response(404)
    )
    http = httpx.AsyncClient()
    fetcher = _W3CFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("UNKNOWN SPEC 99.9")
    await http.aclose()
    assert record is None
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_standards_client.py -k "w3c" -v
```
Expected: `ImportError` — `_W3CFetcher` not defined

- [ ] **Step 3: Add `_W3CFetcher` to `_standards_client.py`**

```python
# ---------------------------------------------------------------------------
# W3C source fetcher
# ---------------------------------------------------------------------------

_W3C_API = "https://api.w3.org"
_W3C_TR = "https://www.w3.org/TR"
_W3C_DELAY = 0.5

# Map common W3C spec names to their shortname for the API
_W3C_SHORTNAME_MAP: dict[str, str] = {
    "WCAG 2.1": "WCAG21",
    "WCAG 2.2": "WCAG22",
    "WCAG 2.0": "WCAG20",
    "WCAG 3.0": "wcag-3.0",
    "WebAuthn Level 1": "webauthn-1",
    "WebAuthn Level 2": "webauthn-2",
    "HTML5": "html5",
    "HTML Living Standard": "html",
}


class _W3CFetcher:
    """Fetches W3C specification metadata from the W3C API.

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~0.5s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter

    def _to_shortname(self, identifier: str) -> str:
        """Convert a human-readable W3C identifier to an API shortname.

        Args:
            identifier: Human-readable identifier like "WCAG 2.1".

        Returns:
            API shortname like "WCAG21".
        """
        if identifier in _W3C_SHORTNAME_MAP:
            return _W3C_SHORTNAME_MAP[identifier]
        # Fallback: strip spaces and dots
        return re.sub(r"[\s.]", "", identifier)

    async def get(self, identifier: str) -> StandardRecord | None:
        """Fetch a single W3C specification by identifier.

        Args:
            identifier: Human-readable identifier (e.g. "WCAG 2.1").

        Returns:
            Populated StandardRecord or None if not found.
        """
        shortname = self._to_shortname(identifier)
        await self._limiter.wait()
        resp = await self._http.get(f"{_W3C_API}/specifications/{shortname}")
        if resp.status_code != 200:
            return None
        return _normalize_w3c(resp.json())

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search W3C specifications by keyword.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        await self._limiter.wait()
        resp = await self._http.get(
            f"{_W3C_API}/specifications",
            params={"q": query, "limit": limit},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        specs = (data.get("results") or data.get("_embedded", {}).get("specifications", []))[:limit]
        return [_normalize_w3c(s) for s in specs]


def _normalize_w3c(spec: dict) -> StandardRecord:  # type: ignore[type-arg]
    """Normalise a W3C API specification object to a StandardRecord.

    Args:
        spec: Raw W3C API specification object.

    Returns:
        Populated StandardRecord.
    """
    title = spec.get("title", "")
    shortname = spec.get("shortname", "")
    latest_url = spec.get("latest-version") or (
        (spec.get("_links") or {}).get("latest-version", {}).get("href", "")
    )
    if not latest_url:
        latest_url = f"{_W3C_TR}/{shortname}/"

    status_raw = (spec.get("latest-status") or spec.get("status") or "").lower()
    if "recommendation" in status_raw:
        status = "published"
    elif "draft" in status_raw or "working" in status_raw:
        status = "draft"
    elif "retired" in status_raw or "superseded" in status_raw:
        status = "superseded"
    else:
        status = "published"

    return StandardRecord(
        identifier=title,
        aliases=[shortname],
        title=title,
        body="W3C",
        number=shortname,
        revision=None,
        status=status,
        published_date=spec.get("published"),
        withdrawn_date=None,
        superseded_by=None,
        supersedes=[],
        scope=spec.get("description"),
        committee=None,
        url=f"{_W3C_API}/specifications/{shortname}",
        full_text_url=latest_url or None,
        full_text_available=bool(latest_url),
        price=None,
        related=[],
    )
```

- [ ] **Step 4: Run W3C tests**

```
pytest tests/test_standards_client.py -k "w3c" -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py
git commit -m "feat: add W3C specification source fetcher"
```

---

### Task 6: ETSI source fetcher + catalogue index

ETSI has no public API; this fetcher scrapes the ETSI standards search page to build a local index, then searches that index for subsequent queries. Requires `beautifulsoup4`.

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` (add `_ETSIFetcher`)
- Modify: `tests/test_standards_client.py` (add ETSI tests)

- [ ] **Step 1: Add `beautifulsoup4` dependency**

```bash
uv add beautifulsoup4
```

- [ ] **Step 2: Write failing ETSI tests**

Append to `tests/test_standards_client.py`:

```python
from scholar_mcp._standards_client import _ETSIFetcher

ETSI_BASE = "https://www.etsi.org"

SAMPLE_ETSI_HTML = """
<html><body>
<table class="table">
<tr>
  <td><a href="/deliver/etsi_en/303600_303699/303645/02.01.01_60/en_303645v020101p.pdf">ETSI EN 303 645</a></td>
  <td>Cyber Security for Consumer Internet of Things: Baseline Requirements</td>
  <td>V2.1.1 (2020-06)</td>
  <td>2020-06-30</td>
</tr>
</table>
</body></html>
"""


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_index_built_on_first_search(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/standards-search/").mock(
        return_value=httpx.Response(200, text=SAMPLE_ETSI_HTML)
    )
    http = httpx.AsyncClient()
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    results = await fetcher.search("303 645", limit=5)
    await http.aclose()
    assert len(results) >= 1
    assert results[0]["body"] == "ETSI"
    assert "303 645" in results[0]["identifier"]


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_search_cached_index_skips_network(respx_mock: respx.MockRouter) -> None:
    """Second search with warm index should not call ETSI network."""
    call_count = 0

    def side_effect(request):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, text=SAMPLE_ETSI_HTML)

    respx_mock.get("/standards-search/").mock(side_effect=side_effect)
    http = httpx.AsyncClient()
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    await fetcher.search("303 645", limit=5)
    await fetcher.search("303 645", limit=5)  # second call — should use in-memory index
    await http.aclose()
    assert call_count == 1  # network called only once


@pytest.mark.respx(base_url=ETSI_BASE)
async def test_etsi_get(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/standards-search/").mock(
        return_value=httpx.Response(200, text=SAMPLE_ETSI_HTML)
    )
    http = httpx.AsyncClient()
    fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
    record = await fetcher.get("ETSI EN 303 645")
    await http.aclose()
    assert record is not None
    assert record["body"] == "ETSI"
    assert record["full_text_available"] is True
```

- [ ] **Step 3: Run to confirm failure**

```
pytest tests/test_standards_client.py -k "etsi" -v
```
Expected: `ImportError` — `_ETSIFetcher` not defined

- [ ] **Step 4: Add `_ETSIFetcher` to `_standards_client.py`**

```python
# ---------------------------------------------------------------------------
# ETSI source fetcher (catalogue index + scraping)
# ---------------------------------------------------------------------------

_ETSI_BASE = "https://www.etsi.org"
_ETSI_SEARCH = "/standards-search/"
_ETSI_DELAY = 2.0  # conservative: 1 req/2s


class _ETSIFetcher:
    """Fetches ETSI standard metadata by scraping the ETSI standards search page.

    On first call, builds an in-memory index from the catalogue page (a few
    seconds). Subsequent calls search the in-memory index without network I/O.
    The index is rebuilt when ``_index`` is None (e.g. after process restart).

    Args:
        http: Shared httpx async client.
        limiter: Rate limiter enforcing ~2s between requests.
    """

    def __init__(self, http: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._http = http
        self._limiter = limiter
        self._index: list[StandardRecord] | None = None

    async def _ensure_index(self) -> list[StandardRecord]:
        """Return in-memory index, building it from the ETSI catalogue if needed.

        Returns:
            List of stub StandardRecord dicts covering the ETSI catalogue.
        """
        if self._index is not None:
            return self._index
        self._index = await self._scrape_catalogue()
        return self._index

    async def _scrape_catalogue(self) -> list[StandardRecord]:
        """Scrape the ETSI standards search page to build a catalogue index.

        Returns:
            List of StandardRecord stubs (identifier, title, url).
        """
        from bs4 import BeautifulSoup

        await self._limiter.wait()
        resp = await self._http.get(f"{_ETSI_BASE}{_ETSI_SEARCH}")
        if resp.status_code != 200:
            logger.warning("etsi_catalogue_scrape_failed status=%d", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        records: list[StandardRecord] = []

        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = cells[0].find("a")
            if not link:
                continue
            raw_id = link.get_text(strip=True)
            title = cells[1].get_text(strip=True)
            href = link.get("href", "")
            pdf_url = f"{_ETSI_BASE}{href}" if href.startswith("/") else href
            m = _ETSI_RE.search(raw_id)
            if not m:
                continue
            canonical = f"ETSI {m.group(1).upper()} {m.group(2)} {m.group(3)}"
            records.append(StandardRecord(
                identifier=canonical,
                aliases=[raw_id] if raw_id != canonical else [],
                title=title,
                body="ETSI",
                number=f"{m.group(2)} {m.group(3)}",
                revision=None,
                status="published",
                published_date=cells[3].get_text(strip=True) if len(cells) > 3 else None,
                withdrawn_date=None,
                superseded_by=None,
                supersedes=[],
                scope=None,
                committee=None,
                url=f"{_ETSI_BASE}{_ETSI_SEARCH}",
                full_text_url=pdf_url if pdf_url.endswith(".pdf") else None,
                full_text_available=pdf_url.endswith(".pdf"),
                price=None,
                related=[],
            ))

        logger.info("etsi_catalogue_indexed count=%d", len(records))
        return records

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:
        """Search the ETSI catalogue index by keyword.

        Builds the index on first call (inline scrape). Subsequent calls use
        the in-memory cache.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            List of matching StandardRecord dicts.
        """
        index = await self._ensure_index()
        q = query.lower().replace(" ", "").replace("-", "")
        matches = [
            r for r in index
            if q in (r.get("identifier") or "").lower().replace(" ", "").replace("-", "")
            or q in (r.get("title") or "").lower()
        ]
        return matches[:limit]

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

- [ ] **Step 5: Run ETSI tests**

```
pytest tests/test_standards_client.py -k "etsi" -v
```
Expected: 3 tests PASS

- [ ] **Step 6: Run all standards client tests**

```
pytest tests/test_standards_client.py -v
```
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/scholar_mcp/_standards_client.py tests/test_standards_client.py pyproject.toml uv.lock
git commit -m "feat: add ETSI source fetcher with in-memory catalogue index"
```

---

### Task 7: StandardsClient + ServiceBundle wiring

**Files:**
- Modify: `src/scholar_mcp/_standards_client.py` (add `StandardsClient`)
- Modify: `src/scholar_mcp/_server_deps.py` (add `standards` field)
- Modify: `src/scholar_mcp/_server_tools.py` (add `register_standards_tools` call)
- Modify: `tests/conftest.py` (add `standards` to `ServiceBundle` fixture)
- Modify: `tests/test_standards_client.py` (add `StandardsClient` integration tests)

- [ ] **Step 1: Write failing StandardsClient tests**

Append to `tests/test_standards_client.py`:

```python
from scholar_mcp._standards_client import StandardsClient


@pytest.mark.respx(base_url=IETF_BASE)
async def test_standards_client_resolve_ietf_local(respx_mock: respx.MockRouter) -> None:
    """Local resolution needs no network call."""
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    results = await client.resolve("rfc9000")
    await http.aclose()
    # Local regex resolves without network; returns list with one item
    assert len(results) == 1
    assert results[0]["identifier"] == "RFC 9000"
    assert results[0]["body"] == "IETF"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_standards_client_search_body_filter(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC9000_SEARCH)
    )
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    results = await client.search("QUIC", body="IETF", limit=5)
    await http.aclose()
    assert all(r["body"] == "IETF" for r in results)
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_standards_client.py -k "standards_client" -v
```
Expected: `ImportError` — `StandardsClient` not defined

- [ ] **Step 3: Add `StandardsClient` to `_standards_client.py`**

```python
# ---------------------------------------------------------------------------
# StandardsClient — public orchestrator
# ---------------------------------------------------------------------------

_STANDARDS_DELAY = 0.5  # shared default for API-backed fetchers


class StandardsClient:
    """Unified client for Tier 1 standards sources.

    Routes search and lookup requests to the appropriate source fetcher
    (IETF, NIST, W3C, ETSI) based on the body parameter or identifier prefix.

    All four source fetchers share a single ``httpx.AsyncClient``. ETSI
    maintains an in-memory catalogue index to avoid per-query scraping.

    Args:
        http: Shared httpx async client (created externally, closed externally).
    """

    def __init__(self, http: httpx.AsyncClient) -> None:
        ietf_limiter = RateLimiter(delay=_IETF_DELAY)
        nist_limiter = RateLimiter(delay=_NIST_DELAY)
        w3c_limiter = RateLimiter(delay=_W3C_DELAY)
        etsi_limiter = RateLimiter(delay=_ETSI_DELAY)
        self._http = http
        self._fetchers: dict[str, _IETFFetcher | _NISTFetcher | _W3CFetcher | _ETSIFetcher] = {
            "IETF": _IETFFetcher(http, ietf_limiter),
            "NIST": _NISTFetcher(http, nist_limiter),
            "W3C": _W3CFetcher(http, w3c_limiter),
            "ETSI": _ETSIFetcher(http, etsi_limiter),
        }

    async def search(
        self,
        query: str,
        *,
        body: str | None = None,
        limit: int = 10,
    ) -> list[StandardRecord]:
        """Search standards by query string, optionally filtered to one body.

        Args:
            query: Identifier, title, or free text.
            body: Optional body filter: "NIST", "IETF", "W3C", or "ETSI".
            limit: Maximum results.

        Returns:
            List of StandardRecord dicts.
        """
        if body is not None:
            fetcher = self._fetchers.get(body.upper())
            if fetcher is None:
                return []
            return await fetcher.search(query, limit=limit)

        # Search all sources concurrently and merge
        import asyncio
        results_per_body = await asyncio.gather(
            *(f.search(query, limit=limit) for f in self._fetchers.values()),
            return_exceptions=True,
        )
        merged: list[StandardRecord] = []
        for r in results_per_body:
            if isinstance(r, list):
                merged.extend(r)
        return merged[:limit]

    async def get(self, identifier: str) -> StandardRecord | None:
        """Resolve and fetch a single standard by identifier.

        Attempts local regex resolution first; if unambiguous, routes to the
        matching source fetcher. Falls back to searching all fetchers.

        Args:
            identifier: Canonical or fuzzy identifier.

        Returns:
            Populated StandardRecord or None.
        """
        resolved = _resolve_identifier_local(identifier)
        if resolved is not None:
            canonical, body = resolved
            fetcher = self._fetchers.get(body)
            if fetcher:
                return await fetcher.get(canonical)

        # No local resolution — try each fetcher
        for fetcher in self._fetchers.values():
            result = await fetcher.get(identifier)
            if result is not None:
                return result
        return None

    async def resolve(self, raw: str) -> list[StandardRecord]:
        """Resolve a raw citation string to one or more StandardRecords.

        Returns a single-item list when unambiguous, multiple items when
        the raw string matches multiple standards, or an empty list when
        unresolvable.

        Args:
            raw: Raw citation string.

        Returns:
            List of matching StandardRecord dicts.
        """
        resolved = _resolve_identifier_local(raw)
        if resolved is not None:
            canonical, body = resolved
            # For unambiguous local resolution, build a minimal record
            # without a network call
            fetcher = self._fetchers.get(body)
            if fetcher:
                record = await fetcher.get(canonical)
                if record is not None:
                    return [record]
            # Return a stub if fetcher fails
            return [StandardRecord(identifier=canonical, body=body, title="", full_text_available=False)]

        # No local resolution — fall back to API search across all bodies
        results = await self.search(raw, limit=5)
        return results

    async def aclose(self) -> None:
        """Close the underlying HTTP client.

        Args: None
        """
        await self._http.aclose()
```

- [ ] **Step 4: Run StandardsClient tests**

```
pytest tests/test_standards_client.py -k "standards_client" -v
```
Expected: 2 tests PASS

- [ ] **Step 5: Update `_server_deps.py` — add `standards` to `ServiceBundle` and lifespan**

In `ServiceBundle` dataclass, after `tasks: TaskQueue`:

```python
    standards: StandardsClient
```

Add import at the top of `_server_deps.py`:

```python
from ._standards_client import StandardsClient
```

In `make_service_lifespan`, after creating `tasks = TaskQueue()`, add:

```python
    standards_http = httpx.AsyncClient(timeout=30.0)
    standards = StandardsClient(standards_http)
```

Update `bundle = ServiceBundle(...)` to include `standards=standards`.

In the `finally` block, after `await s2.aclose()`, add:

```python
        await standards.aclose()
```

- [ ] **Step 6: Update `_server_tools.py` — add `register_standards_tools` call**

```python
    from ._tools_standards import register_standards_tools

    register_standards_tools(mcp)
```

(Add after the `register_book_tools(mcp)` call.)

- [ ] **Step 7: Update `tests/conftest.py` — add `standards` to ServiceBundle fixture**

Add import:
```python
from scholar_mcp._standards_client import StandardsClient
```

In the `bundle` fixture, add `standards_http` and `standards`:

```python
    standards_http = httpx.AsyncClient(timeout=10.0)
    standards = StandardsClient(standards_http)
    yield ServiceBundle(
        s2=s2,
        openalex=openalex,
        docling=None,
        epo=None,
        openlibrary=openlibrary,
        cache=cache,
        config=test_config,
        tasks=TaskQueue(),
        standards=standards,
    )
    await openlibrary_http.aclose()
    await openalex_http.aclose()
    await s2.aclose()
    await standards_http.aclose()
```

- [ ] **Step 8: Create empty `_tools_standards.py`** (so `_server_tools.py` import doesn't break)

```python
# src/scholar_mcp/_tools_standards.py
"""Standards search, lookup, and identifier resolution MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP


def register_standards_tools(mcp: FastMCP) -> None:
    """Register standards tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """
```

- [ ] **Step 9: Run full test suite**

```
pytest --tb=short -q
```
Expected: all tests PASS (no regressions from ServiceBundle change)

- [ ] **Step 10: Commit**

```bash
git add src/scholar_mcp/_standards_client.py src/scholar_mcp/_server_deps.py src/scholar_mcp/_server_tools.py src/scholar_mcp/_tools_standards.py tests/conftest.py tests/test_standards_client.py
git commit -m "feat: add StandardsClient and wire into ServiceBundle"
```

---

### Task 8: `resolve_standard_identifier` tool

**Files:**
- Modify: `src/scholar_mcp/_tools_standards.py`
- Create: `tests/test_tools_standards.py`

- [ ] **Step 1: Write failing tool tests**

```python
# tests/test_tools_standards.py
"""Tests for standards MCP tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_standards import register_standards_tools

IETF_BASE = "https://datatracker.ietf.org"

SAMPLE_RFC_DOC = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "abstract": "This document defines QUIC.",
            "std_level": "proposed_standard",
            "pub_date": "2021-05-01",
        }
    ],
    "meta": {"total_count": 1},
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_standards_tools(app)
    return app


@pytest.mark.respx(base_url=IETF_BASE)
async def test_resolve_unambiguous(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    """resolve_standard_identifier returns canonical + record for known RFC."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("resolve_standard_identifier", {"raw": "rfc9000"})
    data = json.loads(result.content[0].text)
    assert data["canonical"] == "RFC 9000"
    assert data["body"] == "IETF"
    assert data["record"] is not None
    assert data["record"]["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"


async def test_resolve_unknown_returns_null(mcp: FastMCP) -> None:
    """resolve_standard_identifier returns nulls for unknown input."""
    async with Client(mcp) as client:
        result = await client.call_tool("resolve_standard_identifier", {"raw": "totally unknown xyz"})
    data = json.loads(result.content[0].text)
    assert data["canonical"] is None
    assert data["body"] is None
    assert data["record"] is None


async def test_resolve_uses_alias_cache(mcp: FastMCP, bundle: ServiceBundle) -> None:
    """resolve_standard_identifier uses alias cache on repeated calls."""
    # Pre-populate alias cache
    await bundle.cache.set_standard_alias("rfc9000", "RFC 9000")
    await bundle.cache.set_standard(
        "RFC 9000",
        {"identifier": "RFC 9000", "title": "QUIC", "body": "IETF", "full_text_available": True, "url": "https://rfc-editor.org/info/rfc9000"},
    )
    async with Client(mcp) as client:
        result = await client.call_tool("resolve_standard_identifier", {"raw": "rfc9000"})
    data = json.loads(result.content[0].text)
    assert data["canonical"] == "RFC 9000"
    assert data["record"]["title"] == "QUIC"
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_tools_standards.py -v
```
Expected: tools exist in empty stub — tests fail with `ToolNotFoundError`

- [ ] **Step 3: Implement `resolve_standard_identifier` in `_tools_standards.py`**

```python
# src/scholar_mcp/_tools_standards.py
"""Standards search, lookup, and identifier resolution MCP tools."""

from __future__ import annotations

import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle
from ._standards_client import _resolve_identifier_local

logger = logging.getLogger(__name__)


def register_standards_tools(mcp: FastMCP) -> None:
    """Register standards tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def resolve_standard_identifier(
        raw: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Normalise a messy standard citation string to its canonical form.

        Tries local regex first (fast, no network). Falls back to querying
        source APIs when local patterns don't match. Returns all candidates
        when the input is ambiguous.

        Examples:
            resolve_standard_identifier("rfc9000")
            resolve_standard_identifier("nist 800-53")
            resolve_standard_identifier("WCAG2.1")

        Args:
            raw: Raw citation string as it appears in a paper reference.

        Returns:
            JSON with ``canonical``, ``body``, and ``record`` when unambiguous;
            ``{"ambiguous": true, "candidates": [...]}`` when multiple matches;
            ``{"canonical": null, "body": null, "record": null}`` when unresolvable.
        """
        raw = raw.strip()

        # 1. Check alias cache first
        cached_canonical = await bundle.cache.get_standard_alias(raw)
        if cached_canonical is not None:
            cached_record = await bundle.cache.get_standard(cached_canonical)
            if cached_record is not None:
                return json.dumps(
                    {"canonical": cached_canonical, "body": cached_record.get("body"), "record": cached_record}
                )

        # 2. Try local regex
        resolved = _resolve_identifier_local(raw)
        if resolved is not None:
            canonical, body = resolved
            # Fetch full record from source
            record = await bundle.standards.get(canonical)
            if record is not None:
                await bundle.cache.set_standard_alias(raw, canonical)
                await bundle.cache.set_standard(canonical, record)
                return json.dumps({"canonical": canonical, "body": body, "record": record})
            # Return with stub record when fetch fails
            return json.dumps({"canonical": canonical, "body": body, "record": None})

        # 3. API fallback — search all sources
        candidates = await bundle.standards.resolve(raw)
        if not candidates:
            return json.dumps({"canonical": None, "body": None, "record": None})
        if len(candidates) == 1:
            record = candidates[0]
            canonical = record.get("identifier", "")
            body = record.get("body", "")
            await bundle.cache.set_standard_alias(raw, canonical)
            await bundle.cache.set_standard(canonical, record)
            return json.dumps({"canonical": canonical, "body": body, "record": record})

        return json.dumps({"ambiguous": True, "candidates": candidates})
```

- [ ] **Step 4: Run `resolve_standard_identifier` tests**

```
pytest tests/test_tools_standards.py -k "resolve" -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_tools_standards.py tests/test_tools_standards.py
git commit -m "feat: add resolve_standard_identifier tool"
```

---

### Task 9: `search_standards` tool

**Files:**
- Modify: `src/scholar_mcp/_tools_standards.py`
- Modify: `tests/test_tools_standards.py`

- [ ] **Step 1: Write failing `search_standards` tests**

Append to `tests/test_tools_standards.py`:

```python
@pytest.mark.respx(base_url=IETF_BASE)
async def test_search_standards_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_standards", {"query": "QUIC transport", "body": "IETF"}
        )
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["body"] == "IETF"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_search_standards_caches_results(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        await client.call_tool("search_standards", {"query": "cache test", "body": "IETF"})

    cached = await bundle.cache.get_standards_search("q=cache test:body=IETF:limit=10")
    assert cached is not None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_search_standards_cache_hit_skips_network(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """Second search for same query uses cache, not API."""
    call_count = 0

    def side_effect(request):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=SAMPLE_RFC_DOC)

    respx_mock.get("/api/v1/doc/document/").mock(side_effect=side_effect)
    async with Client(mcp) as client:
        await client.call_tool("search_standards", {"query": "QUIC", "body": "IETF"})
        await client.call_tool("search_standards", {"query": "QUIC", "body": "IETF"})
    assert call_count == 1
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_tools_standards.py -k "search_standards" -v
```
Expected: `ToolNotFoundError: search_standards`

- [ ] **Step 3: Implement `search_standards` in `_tools_standards.py`**

Add inside `register_standards_tools`, after `resolve_standard_identifier`:

```python
    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_standards(
        query: str,
        body: str | None = None,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search technical standards by identifier, title, or free text.

        Searches NIST, IETF, W3C, and ETSI. Use ``body`` to restrict to one
        source body.

        Examples:
            search_standards("TLS 1.3")
            search_standards("800-53", body="NIST")
            search_standards("accessibility", body="W3C", limit=5)
            search_standards("IoT security", body="ETSI")

        Args:
            query: Identifier, title, or free text.
            body: Optional filter — "NIST", "IETF", "W3C", or "ETSI".
            limit: Maximum results (max 50).

        Returns:
            JSON list of StandardRecord dicts.
        """
        limit = max(1, min(limit, 50))
        cache_key = f"q={query}:body={body}:limit={limit}"

        cached = await bundle.cache.get_standards_search(cache_key)
        if cached is not None:
            logger.debug("standards_search_cache_hit key=%s", cache_key[:80])
            return json.dumps(cached)

        results = await bundle.standards.search(query, body=body, limit=limit)
        await bundle.cache.set_standards_search(cache_key, results)
        return json.dumps(results)
```

- [ ] **Step 4: Run `search_standards` tests**

```
pytest tests/test_tools_standards.py -k "search_standards" -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_tools_standards.py tests/test_tools_standards.py
git commit -m "feat: add search_standards tool"
```

---

### Task 10: `get_standard` tool (metadata only)

**Files:**
- Modify: `src/scholar_mcp/_tools_standards.py`
- Modify: `tests/test_tools_standards.py`

- [ ] **Step 1: Write failing `get_standard` tests (metadata only)**

Append to `tests/test_tools_standards.py`:

```python
@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_by_fuzzy_id(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "rfc9000"})
    data = json.loads(result.content[0].text)
    assert data["identifier"] == "RFC 9000"
    assert data["body"] == "IETF"
    assert data["full_text_available"] is True


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_caches_result(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        await client.call_tool("get_standard", {"identifier": "RFC 9000"})

    cached = await bundle.cache.get_standard("RFC 9000")
    assert cached is not None
    assert cached["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json={"objects": [], "meta": {"total_count": 0}})
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "RFC 99999"})
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_get_standard_cache_hit_skips_network(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard returns cached record without a network call."""
    cached_record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", cached_record)
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "RFC 9000"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "QUIC"
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_tools_standards.py -k "get_standard" -v
```
Expected: `ToolNotFoundError: get_standard`

- [ ] **Step 3: Implement `get_standard` (metadata only) in `_tools_standards.py`**

Add inside `register_standards_tools`, after `search_standards`:

```python
    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_standard(
        identifier: str,
        fetch_full_text: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Retrieve a standard by identifier (canonical or fuzzy).

        Resolves fuzzy inputs (e.g. "rfc9000", "nist 800-53") to their
        canonical form before fetching. With ``fetch_full_text=True`` and
        docling configured, downloads and converts the full text.

        Examples:
            get_standard("RFC 9000")
            get_standard("NIST SP 800-53 Rev. 5")
            get_standard("rfc9000")
            get_standard("WCAG 2.1", fetch_full_text=True)

        Args:
            identifier: Canonical or fuzzy standard identifier.
            fetch_full_text: If True and docling is configured, download and
                convert the full text PDF/HTML via docling.

        Returns:
            JSON StandardRecord, or ``{"error": "not_found"}`` if unresolvable.
        """
        identifier = identifier.strip()

        # 1. Resolve identifier to canonical form
        resolved = _resolve_identifier_local(identifier)
        canonical = resolved[0] if resolved else identifier

        # 2. Check cache
        cached = await bundle.cache.get_standard(canonical)
        if cached is not None:
            logger.debug("standard_cache_hit identifier=%s", canonical)
            if fetch_full_text:
                return await _handle_full_text(cached, bundle)
            return json.dumps(cached)

        # 3. Fetch from source
        record = await bundle.standards.get(canonical)
        if record is None:
            return json.dumps({"error": "not_found", "identifier": identifier})

        # 4. Cache result
        await bundle.cache.set_standard(canonical, record)
        if resolved:
            await bundle.cache.set_standard_alias(identifier, canonical)

        if fetch_full_text:
            return await _handle_full_text(record, bundle)
        return json.dumps(record)
```

Also add the `_handle_full_text` helper (stub for now — full implementation in Task 11):

```python
async def _handle_full_text(record: dict, bundle: ServiceBundle) -> str:  # type: ignore[type-arg]
    """Return record JSON (full-text fetch deferred to Task 11).

    Args:
        record: StandardRecord dict.
        bundle: Service bundle.

    Returns:
        JSON StandardRecord.
    """
    return json.dumps(record)
```

- [ ] **Step 4: Run `get_standard` tests**

```
pytest tests/test_tools_standards.py -k "get_standard" -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Run full test suite**

```
pytest --tb=short -q
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_tools_standards.py tests/test_tools_standards.py
git commit -m "feat: add get_standard tool (metadata)"
```

---

### Task 11: Full-text via docling in `get_standard`

**Files:**
- Modify: `src/scholar_mcp/_tools_standards.py` (implement `_handle_full_text`)
- Modify: `tests/test_tools_standards.py` (add docling tests)

- [ ] **Step 1: Write failing full-text tests**

Append to `tests/test_tools_standards.py`:

```python
from unittest.mock import AsyncMock, MagicMock

from scholar_mcp._docling_client import DoclingClient


async def test_get_standard_fetch_full_text_queues_task(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard with fetch_full_text=True and docling configured queues a task."""
    mock_docling = MagicMock(spec=DoclingClient)
    mock_docling.convert = AsyncMock(return_value={"markdown": "# RFC 9000\n..."})

    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)

    # Patch docling into bundle
    bundle.docling = mock_docling  # type: ignore[assignment]

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
        )
    data = json.loads(result.content[0].text)
    # Should return task ID (queued) or inline result — either is acceptable
    assert "identifier" in data or "task_id" in data or "queued" in data


async def test_get_standard_fetch_full_text_no_docling(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard with fetch_full_text=True but no docling returns record only."""
    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)
    # bundle.docling is None by default in test fixture

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
        )
    data = json.loads(result.content[0].text)
    assert data["identifier"] == "RFC 9000"
    assert "full_text_url" in data  # URL included so user can fetch manually
```

- [ ] **Step 2: Run to confirm current behaviour (stub passes no-docling, queued may fail)**

```
pytest tests/test_tools_standards.py -k "full_text" -v
```

- [ ] **Step 3: Implement `_handle_full_text` properly**

Replace the stub `_handle_full_text` with:

```python
async def _handle_full_text(record: dict, bundle: ServiceBundle) -> str:  # type: ignore[type-arg]
    """Download and convert full text via docling if available.

    If docling is not configured or no full_text_url is available, returns
    the record as-is (the caller can use full_text_url to fetch manually).

    Args:
        record: StandardRecord dict.
        bundle: Service bundle with optional docling client and task queue.

    Returns:
        JSON StandardRecord, possibly with ``full_text`` field populated,
        or ``{"queued": true, "task_id": "..."}`` if conversion was queued.
    """
    from ._rate_limiter import RateLimitedError

    if not record.get("full_text_available") or not record.get("full_text_url"):
        return json.dumps(record)

    if bundle.docling is None:
        logger.debug("full_text_requested_but_docling_not_configured id=%s", record.get("identifier"))
        return json.dumps(record)

    url = record["full_text_url"]

    async def _convert(*, retry: bool = True) -> str:
        result = await bundle.docling.convert(url)
        enriched = {**record, "full_text": result.get("markdown", "")}
        return json.dumps(enriched)

    try:
        return await _convert(retry=False)
    except RateLimitedError:
        task_id = bundle.tasks.submit(
            _convert(retry=True), tool="get_standard"
        )
        return json.dumps({"queued": True, "task_id": task_id, "tool": "get_standard"})
    except Exception as exc:
        logger.warning("full_text_conversion_failed id=%s err=%s", record.get("identifier"), exc)
        return json.dumps(record)
```

- [ ] **Step 4: Run full-text tests**

```
pytest tests/test_tools_standards.py -k "full_text" -v
```
Expected: 2 tests PASS

- [ ] **Step 5: Run all tool tests**

```
pytest tests/test_tools_standards.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Run full test suite**

```
pytest --tb=short -q
```
Expected: all tests PASS

- [ ] **Step 7: Run type checks and linter**

```bash
uv run mypy src/scholar_mcp/_standards_client.py src/scholar_mcp/_tools_standards.py src/scholar_mcp/_server_deps.py src/scholar_mcp/_record_types.py src/scholar_mcp/_cache.py src/scholar_mcp/_protocols.py
uv run ruff check src/scholar_mcp/_standards_client.py src/scholar_mcp/_tools_standards.py
uv run ruff format src/scholar_mcp/_standards_client.py src/scholar_mcp/_tools_standards.py
```

Fix any reported issues before committing.

- [ ] **Step 8: Commit**

```bash
git add src/scholar_mcp/_tools_standards.py tests/test_tools_standards.py
git commit -m "feat: add full-text docling conversion to get_standard"
```

---

### Task 12: Docs, GitHub milestone, and deferred issues

**Files:**
- Modify: `docs/tools/index.md`

- [ ] **Step 1: Update `docs/tools/index.md`**

Add a Standards section documenting the three new tools. Follow the existing format in the file. Add:

```markdown
## Standards

Scholar MCP supports Tier 1 standards bodies (NIST, IETF, W3C, ETSI) with full metadata and
optional full-text conversion. Tier 2 paywalled bodies (ISO, IEC, IEEE) are planned for v0.9.0.

### `search_standards`

Search standards by identifier, title, or free text.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | — | Identifier, title, or free text |
| `body` | string | null | Filter to one body: `NIST`, `IETF`, `W3C`, `ETSI` |
| `limit` | integer | 10 | Max results (max 50) |

### `get_standard`

Retrieve a standard by identifier (canonical or fuzzy). Optionally fetches and converts
full text via docling.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `identifier` | string | — | Canonical or fuzzy identifier |
| `fetch_full_text` | boolean | false | Fetch and convert full text via docling |

### `resolve_standard_identifier`

Normalise a messy citation string to its canonical form and body.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `raw` | string | — | Messy citation string (e.g. `"rfc9000"`, `"nist 800-53"`) |
```

- [ ] **Step 2: Create v0.8.0 milestone on GitHub**

```bash
gh api repos/pvliesdonk/scholar-mcp/milestones \
  --method POST \
  -f title="v0.8.0" \
  -f description="Standards support — NIST, IETF, W3C, ETSI Tier 1 fetchers, unified StandardsClient, three new tools, full-text via docling"
```

- [ ] **Step 3: File deferred Tier 2 issues**

```bash
gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: ISO/IEC standards metadata lookup (Tier 2)" \
  --label "enhancement" \
  --body "Scrape iso.org catalogue for metadata. Returns StandardRecord with full_text_available=False and price populated. No paywall bypass. Identifier forms: ISO/IEC 27001:2022, ISO 9001:2015. Part of Tier 2 standards support (paywalled metadata only). Depends on v0.8.0 StandardsClient framework."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: IEC standards metadata lookup (Tier 2)" \
  --label "enhancement" \
  --body "Scrape webstore.iec.ch for IEC and ISO/IEC co-published standards metadata. Deduplicates with ISO on joint standards by identifier. Covers IEC 62443 series (industrial/product security). Returns StandardRecord with full_text_available=False. Depends on v0.8.0 StandardsClient framework."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: IEEE standards metadata lookup (Tier 2)" \
  --label "enhancement" \
  --body "Browse standards.ieee.org catalogue for IEEE Std metadata. Full text paywalled unless IEEE Xplore institutional access is available (see F7 for authenticated path). Identifier forms: IEEE 802.11-2020, IEEE Std 1588-2019. Depends on v0.8.0 StandardsClient framework."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: CEN/CENELEC standards metadata lookup (Tier 2)" \
  --label "enhancement" \
  --body "Browse standards.cencenelec.eu for European Norms not already covered by ETSI. Full text paywalled via national mirrors. Most relevant for harmonised standards under EU regulation (CRA, RED). Low priority. Depends on v0.8.0 StandardsClient framework."
```

- [ ] **Step 4: File Tier 3 issue**

```bash
gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: Common Criteria portal integration (Tier 3)" \
  --label "enhancement" \
  --body "Add commoncriteriaportal.org as a Tier 3 source. Freely available PDFs. Cross-link CC:2022 and ISO/IEC 15408 identifiers so lookups by either form resolve to the same record. Covers CC documents, Protection Profiles, and certified product list. Depends on v0.8.0 StandardsClient framework."
```

- [ ] **Step 5: File enrichment integration issue**

```bash
gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: standards auto-enrichment in get_paper / get_references / get_citations" \
  --label "enhancement" \
  --body "When a citation string in S2 results matches standards-like patterns (ISO, IEC, NIST SP, RFC, IEEE Std, ETSI) but S2 returned sparse or no metadata, auto-call resolve_standard_identifier and attach result as standard_metadata field on the citation. Must be non-blocking and cached. Depends on v0.8.0 StandardsClient framework."
```

- [ ] **Step 6: File F1–F9 follow-up issues**

```bash
gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: national standards mirrors alias resolution (NEN, DIN, BSI, AFNOR)" \
  --label "enhancement" \
  --body "F1: Extend alias resolution to handle national identifier forms such as NEN-EN-ISO/IEC 27001, DIN EN ISO 27001, BS EN ISO 27001. Maps national identifiers to the corresponding ISO/IEC canonical form. Depends on Tier 2 ISO support."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: Public.Resource.Org standards access" \
  --label "enhancement" \
  --body "F2: Add law.resource.org as a source for standards incorporated by reference into US law. Coverage is spotty but legally open. Useful for US regulatory contexts (building codes, safety standards). Depends on v0.8.0 StandardsClient framework."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: OASIS, OMG, 3GPP, ITU-T Tier 1 sources" \
  --label "enhancement" \
  --body "F3: Add freely-published Tier 1 sources: OASIS (SAML, STIX, TAXII) at oasis-open.org; OMG (UML, SysML, BPMN) at omg.org; 3GPP at 3gpp.org; ITU-T Recommendations at itu.int/rec/T-REC. All have clean enough catalogue pages. Deferred to avoid scope creep in v0.8.0. Depends on v0.8.0 StandardsClient framework."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: BibLaTeX @techreport / @manual citation output for standards (F4)" \
  --label "enhancement" \
  --body "F4: Ensure generate_citations produces correct BibLaTeX output for StandardRecord. Typically @techreport (NIST, IETF) or @manual (ISO, W3C). Different bodies have different citation conventions — may need per-body templates. Depends on v0.8.0 StandardsClient framework and the existing generate_citations feature."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: regulatory framework to standards cross-linking" \
  --label "enhancement" \
  --body "F5: Map regulations to the standards they reference (CRA → harmonised standards list, NIS2 → ISO 27001, etc.). Expose a get_regulation_standards tool returning all standards referenced by a given regulation. High value for product security work. Requires maintained mapping data. Depends on v0.8.0."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: standards lifecycle tracking — detect withdrawn/superseded citations" \
  --label "enhancement" \
  --body "F6: Alert when a cited standard is withdrawn or superseded. Useful for literature reviews: 'this 2015 paper cites ISO/IEC 27001:2013, now superseded by 27001:2022'. Requires periodic catalogue refresh and a diff mechanism. Depends on v0.8.0 StandardsClient and cache."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: IEEE Xplore institutional access for full-text standards" \
  --label "enhancement" \
  --body "F7: If institutional access is available (e.g. TNO IEEE Xplore), add authenticated API access to IEEE standards full text. Would promote IEEE from Tier 2 to Tier 1 for authenticated users. Requires API key and auth handling. Depends on Tier 2 IEEE metadata support."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: Perinorm commercial metadata aggregator integration" \
  --label "enhancement" \
  --body "F8: Perinorm is a commercial cross-body catalogue. Only worth pursuing if TNO has a subscription. Would provide the most comprehensive cross-body catalogue in one place. Low priority. Depends on v0.8.0."

gh issue create \
  --repo pvliesdonk/scholar-mcp \
  --title "feat: standards recommendation given a paper or topic" \
  --label "enhancement" \
  --body "F9: Given a paper or topic, suggest relevant standards. Analogous to recommend_papers but for standards. Could leverage ICS classification (ISO) and NIST CSF mapping. Depends on v0.8.0 StandardsClient and Tier 2 metadata for ICS classification."
```

- [ ] **Step 7: Assign all new deferred issues to appropriate milestones**

Tier 2 and Tier 3 issues → v0.9.0 (create if it doesn't exist):

```bash
MILESTONE_ID=$(gh api repos/pvliesdonk/scholar-mcp/milestones --jq '.[] | select(.title=="v0.9.0") | .number')
if [ -z "$MILESTONE_ID" ]; then
  MILESTONE_ID=$(gh api repos/pvliesdonk/scholar-mcp/milestones --method POST -f title="v0.9.0" -f description="Standards Tier 2 — ISO, IEC, IEEE, CEN/CENELEC metadata; Common Criteria; enrichment integration" --jq '.number')
fi
echo "v0.9.0 milestone: $MILESTONE_ID"
```

Then assign each issue to v0.9.0 or Future using:
```bash
gh issue edit <number> --milestone "v0.9.0"  # Tier 2, Tier 3, enrichment integration
gh issue edit <number> --milestone "Future"  # F1–F9 follow-ups
```

- [ ] **Step 8: Commit docs**

```bash
git add docs/tools/index.md
git commit -m "docs: document standards tools (search_standards, get_standard, resolve_standard_identifier)"
```

- [ ] **Step 9: Run final full test suite**

```bash
pytest --tb=short -q
uv run ruff check src/scholar_mcp/
uv run mypy src/scholar_mcp/ --ignore-missing-imports
```
Expected: all tests PASS, no lint errors, no mypy errors

---

## Summary

12 tasks, all TDD. Commit after each task.

| Task | Commits |
|------|---------|
| 1 | StandardRecord + cache |
| 2 | Identifier resolver |
| 3 | IETF fetcher |
| 4 | NIST fetcher |
| 5 | W3C fetcher |
| 6 | ETSI fetcher + index |
| 7 | StandardsClient + ServiceBundle wiring |
| 8 | `resolve_standard_identifier` tool |
| 9 | `search_standards` tool |
| 10 | `get_standard` (metadata) |
| 11 | Full-text via docling |
| 12 | Docs + milestone + 14 deferred issues |

# Standards Sync Infrastructure Implementation Plan (PR 1 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the foundation for v0.9.0 Tier 2 standards: a `scholar-mcp sync-standards` CLI subcommand, a cache schema capable of distinguishing synced records from live-fetched records, a `standards_sync_runs` table with a `get_sync_status` MCP tool to report freshness, and an extensible loader dispatcher with zero loaders registered yet.

**Architecture:** New `_standards_sync.py` module defines a `Loader` protocol, `SyncReport` dataclass, and `run_sync()` dispatcher. SQLite schema migrates `standards` to carry `source` + `synced_at` columns, adds a `standards_sync_runs` table. `ScholarCache.set_standard()` gains optional `source` / `synced_at` parameters; when `synced_at` is provided the record bypasses the 90-day TTL on reads. CLI subcommand calls the dispatcher with body filter + force flag, prints per-body summary, exits with 0/1/3 for success/hard-fail/partial-fail.

**Tech Stack:** Python 3.11+, `aiosqlite`, `click`, `pytest` (`asyncio` mode), `FastMCP` (for the new MCP tool), `ruff`, `mypy`.

**Scope (this PR only):**
- No loaders for ISO / IEC / IEEE / CEN / CC (those ship in PRs 2–4).
- No enricher (PR 5).
- Every public surface this PR adds must be exercised by tests.

---

## File Structure

**Create:**
- `src/scholar_mcp/_standards_sync.py` — `SyncReport`, `Loader` protocol, `run_sync()` dispatcher, `_format_report()` helper
- `tests/test_standards_sync.py` — dispatcher + report tests using stub loaders
- `tests/test_cli_sync_standards.py` — CLI subcommand tests via `CliRunner`

**Modify:**
- `src/scholar_mcp/_cache.py` — bump `_STANDARD_SEARCH_TTL` and `_STANDARD_INDEX_TTL` from 7d to 30d; add `source`/`synced_at` columns via a new `schema_version=2` migration; new `standards_sync_runs` table; update `set_standard` signature; update `get_standard` to skip TTL for synced records; add `set_sync_run`, `get_sync_run`, `list_sync_runs`
- `src/scholar_mcp/_protocols.py` — extend `CacheProtocol` with the three new sync-run methods
- `src/scholar_mcp/cli.py` — register a new `sync-standards` subcommand group
- `src/scholar_mcp/_tools_standards.py` — register a new `get_sync_status` MCP tool
- `tests/test_cache_standards.py` — add round-trip tests for the new columns, TTL bypass for synced records, and sync-run methods
- `README.md` — add a "Standards sync" subsection under Features and mention `scholar-mcp sync-standards` in Quick Start
- `docs/tools/index.md` — document `get_sync_status`
- `server.json`, `.claude-plugin/plugin/.claude-plugin/plugin.json`, `.claude-plugin/plugin/.mcp.json` — bump patch version in lockstep

---

## Task 1: Bump TTL constants for search and index caches

**Files:**
- Modify: `src/scholar_mcp/_cache.py:84-85`
- Test: `tests/test_cache_standards.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cache_standards.py`:

```python
from scholar_mcp import _cache as _cache_mod


def test_standard_search_ttl_is_30_days() -> None:
    assert _cache_mod._STANDARD_SEARCH_TTL == 30 * 86400


def test_standard_index_ttl_is_30_days() -> None:
    assert _cache_mod._STANDARD_INDEX_TTL == 30 * 86400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache_standards.py -v -k "ttl_is_30"`
Expected: FAIL — current values are `7 * 86400`.

- [ ] **Step 3: Bump the constants**

Replace `src/scholar_mcp/_cache.py:84-85` from:

```python
_STANDARD_SEARCH_TTL = 7 * 86400  # 7 days
_STANDARD_INDEX_TTL = 7 * 86400  # 7 days — re-scrape weekly
```

to:

```python
_STANDARD_SEARCH_TTL = 30 * 86400  # 30 days — standards are effectively append-only
_STANDARD_INDEX_TTL = 30 * 86400  # 30 days — re-scrape monthly
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cache_standards.py -v -k "ttl_is_30"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cache_standards.py src/scholar_mcp/_cache.py
git commit -m "feat(standards): bump search/index TTL to 30 days"
```

---

## Task 2: Add `source` and `synced_at` columns to `standards` table via schema migration

**Files:**
- Modify: `src/scholar_mcp/_cache.py` (schema block, `open()` method)
- Test: `tests/test_cache_standards.py`

Rationale: existing `_SCHEMA` uses `CREATE TABLE IF NOT EXISTS` only; altering an existing user's DB requires a migration guarded by `schema_version`. The `schema_version` table already exists with version `1`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cache_standards.py`:

```python
import aiosqlite


async def test_standards_table_has_source_column(cache: ScholarCache) -> None:
    async with aiosqlite.connect(cache._db_path) as db:  # type: ignore[attr-defined]
        async with db.execute("PRAGMA table_info(standards)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
    assert "source" in cols
    assert "synced_at" in cols


async def test_schema_version_is_2(cache: ScholarCache) -> None:
    async with aiosqlite.connect(cache._db_path) as db:  # type: ignore[attr-defined]
        async with db.execute(
            "SELECT MAX(version) FROM schema_version"
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cache_standards.py -v -k "source_column or schema_version_is_2"`
Expected: FAIL — columns don't exist, version is 1.

- [ ] **Step 3: Update schema and add migration**

In `src/scholar_mcp/_cache.py`, replace `INSERT OR IGNORE INTO schema_version VALUES (1);` (line ~89) with:

```python
INSERT OR IGNORE INTO schema_version VALUES (2);
```

Then replace the `standards` table definition (lines ~222-227) from:

```python
CREATE TABLE IF NOT EXISTS standards (
    identifier TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_standards_cached ON standards(cached_at);
```

to:

```python
CREATE TABLE IF NOT EXISTS standards (
    identifier TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL NOT NULL,
    source     TEXT,
    synced_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_standards_cached ON standards(cached_at);
CREATE INDEX IF NOT EXISTS idx_standards_source ON standards(source);
```

Add this migration script constant near `_SCHEMA` (above the `_TTL_TABLES` tuple):

```python
# Idempotent migrations for existing cache DBs. Each MUST tolerate
# re-execution — use CREATE IF NOT EXISTS and check PRAGMA before ALTER.
_MIGRATIONS = """
-- v2: add source and synced_at to standards for sync/live distinction
"""


async def _apply_migrations(db: aiosqlite.Connection) -> None:
    """Apply column migrations not covered by CREATE TABLE IF NOT EXISTS.

    Idempotent — safe to run on fresh or already-migrated DBs.
    """
    async with db.execute("PRAGMA table_info(standards)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "source" not in cols:
        await db.execute("ALTER TABLE standards ADD COLUMN source TEXT")
    if "synced_at" not in cols:
        await db.execute("ALTER TABLE standards ADD COLUMN synced_at REAL")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_standards_source ON standards(source)"
    )
    await db.execute(
        "INSERT OR IGNORE INTO schema_version VALUES (2)"
    )
    await db.commit()
```

Call it from `open()`. Locate the method at around line 305 and change:

```python
async def open(self) -> None:
    """Open database connection and apply schema."""
    self._db_path.parent.mkdir(parents=True, exist_ok=True)
    self._db = await aiosqlite.connect(self._db_path)
    await self._db.executescript(_SCHEMA)
    await self._db.commit()
    logger.info("cache_opened path=%s", self._db_path)
```

to:

```python
async def open(self) -> None:
    """Open database connection and apply schema."""
    self._db_path.parent.mkdir(parents=True, exist_ok=True)
    self._db = await aiosqlite.connect(self._db_path)
    await self._db.executescript(_SCHEMA)
    await _apply_migrations(self._db)
    await self._db.commit()
    logger.info("cache_opened path=%s", self._db_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cache_standards.py -v`
Expected: PASS for the two new tests plus all existing standards cache tests.

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_cache.py tests/test_cache_standards.py
git commit -m "feat(standards): add source/synced_at columns and v2 migration"
```

---

## Task 3: Teach `set_standard` / `get_standard` about synced records

**Files:**
- Modify: `src/scholar_mcp/_cache.py` (around lines 1015-1045, the existing `get_standard` / `set_standard`)
- Test: `tests/test_cache_standards.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cache_standards.py`:

```python
async def test_set_standard_with_source_stores_both_columns(
    cache: ScholarCache,
) -> None:
    await cache.set_standard("RFC 9000", SAMPLE_STANDARD, source="IETF")
    async with aiosqlite.connect(cache._db_path) as db:  # type: ignore[attr-defined]
        async with db.execute(
            "SELECT source, synced_at FROM standards WHERE identifier = ?",
            ("RFC 9000",),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "IETF"
    assert row[1] is None  # live-fetched, no synced_at


async def test_set_standard_synced_marks_synced_at(cache: ScholarCache) -> None:
    before = time.time()
    await cache.set_standard(
        "ISO 9001:2015", SAMPLE_STANDARD, source="ISO", synced=True
    )
    async with aiosqlite.connect(cache._db_path) as db:  # type: ignore[attr-defined]
        async with db.execute(
            "SELECT synced_at FROM standards WHERE identifier = ?",
            ("ISO 9001:2015",),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[0] >= before


async def test_get_standard_synced_ignores_ttl(cache: ScholarCache) -> None:
    """Synced records must never TTL-expire."""
    await cache.set_standard(
        "ISO 27001:2022", SAMPLE_STANDARD, source="ISO", synced=True
    )
    # Backdate cached_at beyond the 90-day TTL
    async with aiosqlite.connect(cache._db_path) as db:  # type: ignore[attr-defined]
        long_ago = time.time() - (180 * 86400)
        await db.execute(
            "UPDATE standards SET cached_at = ? WHERE identifier = ?",
            (long_ago, "ISO 27001:2022"),
        )
        await db.commit()
    result = await cache.get_standard("ISO 27001:2022")
    assert result is not None
    assert result["identifier"] == "RFC 9000"  # fixture body — we only care it returned


async def test_get_standard_live_respects_ttl(cache: ScholarCache) -> None:
    """Live-fetched records (no synced_at) still TTL-expire."""
    await cache.set_standard("RFC 1234", SAMPLE_STANDARD, source="IETF")
    async with aiosqlite.connect(cache._db_path) as db:  # type: ignore[attr-defined]
        long_ago = time.time() - (180 * 86400)
        await db.execute(
            "UPDATE standards SET cached_at = ? WHERE identifier = ?",
            (long_ago, "RFC 1234"),
        )
        await db.commit()
    result = await cache.get_standard("RFC 1234")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cache_standards.py -v -k "source or synced or live_respects"`
Expected: FAIL — `set_standard` does not yet accept `source` / `synced` kwargs; `get_standard` does not yet check `synced_at`.

- [ ] **Step 3: Update `set_standard` and `get_standard`**

Replace the existing `get_standard` method (around line 1015) with:

```python
async def get_standard(self, identifier: str) -> StandardRecord | None:
    """Return cached standard record or None if missing.

    Synced records (``synced_at IS NOT NULL``) bypass TTL — they're
    refreshed only by a subsequent sync. Live-fetched records expire
    after ``_STANDARD_TTL`` seconds.

    Args:
        identifier: Canonical standard identifier.

    Returns:
        StandardRecord dict or None.
    """
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at, synced_at FROM standards WHERE identifier = ?",
        (identifier,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    synced_at = row[2]
    if synced_at is None and time.time() - row[1] > _STANDARD_TTL:
        return None
    return json.loads(row[0])  # type: ignore[no-any-return]
```

Replace the existing `set_standard` method (around line 1033) with:

```python
async def set_standard(
    self,
    identifier: str,
    data: StandardRecord,
    *,
    source: str | None = None,
    synced: bool = False,
) -> None:
    """Cache a standard record.

    Args:
        identifier: Canonical standard identifier.
        data: StandardRecord dict.
        source: Populating body — one of "IETF", "NIST", "W3C", "ETSI",
            "ISO", "IEC", "IEEE", "CEN", "CENELEC", "CC". ``None`` for
            legacy call sites that have not been updated yet.
        synced: When True, marks ``synced_at=now``. Synced records never
            TTL-expire. Live-fetched callers must leave this False.
    """
    db = _require_open(self._db)
    now = time.time()
    synced_at = now if synced else None
    await db.execute(
        "INSERT OR REPLACE INTO standards "
        "(identifier, data, cached_at, source, synced_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (identifier, json.dumps(data), now, source, synced_at),
    )
    await db.commit()
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cache_standards.py -v`
Expected: PASS for all existing tests plus the four new ones.

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_cache.py tests/test_cache_standards.py
git commit -m "feat(standards): set_standard source/synced kwargs, synced bypasses TTL"
```

---

## Task 4: Add `standards_sync_runs` table and `ScholarCache` methods

**Files:**
- Modify: `src/scholar_mcp/_cache.py` (schema block, add three new methods)
- Modify: `src/scholar_mcp/_protocols.py` (extend `CacheProtocol`)
- Test: `tests/test_cache_standards.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cache_standards.py`:

```python
async def test_sync_run_roundtrip(cache: ScholarCache) -> None:
    await cache.set_sync_run(
        body="ISO",
        upstream_ref="abc123",
        added=42,
        updated=3,
        unchanged=100,
        withdrawn=1,
        errors=[],
        started_at=1_000_000.0,
        finished_at=1_000_060.0,
    )
    row = await cache.get_sync_run("ISO")
    assert row is not None
    assert row["body"] == "ISO"
    assert row["upstream_ref"] == "abc123"
    assert row["added"] == 42
    assert row["updated"] == 3
    assert row["unchanged"] == 100
    assert row["withdrawn"] == 1
    assert row["errors"] == []
    assert row["started_at"] == 1_000_000.0
    assert row["finished_at"] == 1_000_060.0


async def test_sync_run_replaces_on_second_write(cache: ScholarCache) -> None:
    await cache.set_sync_run(
        body="IEC", upstream_ref="v1", added=1, updated=0,
        unchanged=0, withdrawn=0, errors=[],
        started_at=1.0, finished_at=2.0,
    )
    await cache.set_sync_run(
        body="IEC", upstream_ref="v2", added=5, updated=2,
        unchanged=10, withdrawn=0, errors=["one failure"],
        started_at=3.0, finished_at=4.0,
    )
    row = await cache.get_sync_run("IEC")
    assert row is not None
    assert row["upstream_ref"] == "v2"
    assert row["added"] == 5
    assert row["errors"] == ["one failure"]


async def test_sync_run_missing_returns_none(cache: ScholarCache) -> None:
    assert await cache.get_sync_run("IEEE") is None


async def test_list_sync_runs(cache: ScholarCache) -> None:
    await cache.set_sync_run(
        body="ISO", upstream_ref="a", added=0, updated=0,
        unchanged=0, withdrawn=0, errors=[],
        started_at=1.0, finished_at=2.0,
    )
    await cache.set_sync_run(
        body="IEC", upstream_ref="b", added=0, updated=0,
        unchanged=0, withdrawn=0, errors=[],
        started_at=3.0, finished_at=4.0,
    )
    rows = await cache.list_sync_runs()
    bodies = {r["body"] for r in rows}
    assert bodies == {"ISO", "IEC"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cache_standards.py -v -k "sync_run"`
Expected: FAIL — `set_sync_run` / `get_sync_run` / `list_sync_runs` don't exist.

- [ ] **Step 3: Add the table to `_SCHEMA`**

In `src/scholar_mcp/_cache.py`, append inside `_SCHEMA` (before the closing `"""`, after the `standards_index` block around line 248):

```sql

CREATE TABLE IF NOT EXISTS standards_sync_runs (
    body          TEXT PRIMARY KEY,
    upstream_ref  TEXT,
    added         INTEGER NOT NULL,
    updated       INTEGER NOT NULL,
    unchanged     INTEGER NOT NULL,
    withdrawn     INTEGER NOT NULL,
    errors        TEXT NOT NULL,
    started_at    REAL NOT NULL,
    finished_at   REAL NOT NULL
);
```

- [ ] **Step 4: Add the three methods**

Append to the `ScholarCache` class (after `set_standards_index`, at end of file):

```python
# ------------------------------------------------------------------
# Standards sync runs
# ------------------------------------------------------------------

async def set_sync_run(
    self,
    *,
    body: str,
    upstream_ref: str | None,
    added: int,
    updated: int,
    unchanged: int,
    withdrawn: int,
    errors: list[str],
    started_at: float,
    finished_at: float,
) -> None:
    """Record (or replace) the latest sync run for *body*.

    Args:
        body: Standards body key (e.g. ``"ISO"``).
        upstream_ref: Commit SHA, ``Last-Modified``, or similar marker
            indicating what upstream version was synced.
        added: Number of new records.
        updated: Number of records that changed.
        unchanged: Number of records unchanged since last sync.
        withdrawn: Number of records marked withdrawn.
        errors: Non-fatal error strings encountered this run.
        started_at: Unix timestamp (seconds) when the run started.
        finished_at: Unix timestamp (seconds) when the run finished.
    """
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO standards_sync_runs ("
        "body, upstream_ref, added, updated, unchanged, "
        "withdrawn, errors, started_at, finished_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            body,
            upstream_ref,
            added,
            updated,
            unchanged,
            withdrawn,
            json.dumps(errors),
            started_at,
            finished_at,
        ),
    )
    await db.commit()


async def get_sync_run(self, body: str) -> dict[str, Any] | None:
    """Return the last sync run record for *body*, or None.

    Args:
        body: Standards body key.

    Returns:
        Dict with keys ``body``, ``upstream_ref``, ``added``,
        ``updated``, ``unchanged``, ``withdrawn``, ``errors``,
        ``started_at``, ``finished_at``.
    """
    db = _require_open(self._db)
    async with db.execute(
        "SELECT body, upstream_ref, added, updated, unchanged, "
        "withdrawn, errors, started_at, finished_at "
        "FROM standards_sync_runs WHERE body = ?",
        (body,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "body": row[0],
        "upstream_ref": row[1],
        "added": row[2],
        "updated": row[3],
        "unchanged": row[4],
        "withdrawn": row[5],
        "errors": json.loads(row[6]),
        "started_at": row[7],
        "finished_at": row[8],
    }


async def list_sync_runs(self) -> list[dict[str, Any]]:
    """Return every recorded sync run, one per body.

    Returns:
        List of dicts with the same shape as :meth:`get_sync_run`.
    """
    db = _require_open(self._db)
    async with db.execute(
        "SELECT body, upstream_ref, added, updated, unchanged, "
        "withdrawn, errors, started_at, finished_at "
        "FROM standards_sync_runs ORDER BY body"
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "body": r[0],
            "upstream_ref": r[1],
            "added": r[2],
            "updated": r[3],
            "unchanged": r[4],
            "withdrawn": r[5],
            "errors": json.loads(r[6]),
            "started_at": r[7],
            "finished_at": r[8],
        }
        for r in rows
    ]
```

- [ ] **Step 5: Extend `CacheProtocol`**

In `src/scholar_mcp/_protocols.py`, append after the last standards method (line ~92):

```python
# Standards sync-run methods
async def set_sync_run(
    self,
    *,
    body: str,
    upstream_ref: str | None,
    added: int,
    updated: int,
    unchanged: int,
    withdrawn: int,
    errors: list[str],
    started_at: float,
    finished_at: float,
) -> None: ...
async def get_sync_run(self, body: str) -> dict[str, Any] | None: ...
async def list_sync_runs(self) -> list[dict[str, Any]]: ...
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_cache_standards.py -v -k "sync_run"`
Expected: PASS for all four new tests.

- [ ] **Step 7: Type-check**

Run: `uv run mypy src/`
Expected: no errors. `ScholarCache` must still satisfy `CacheProtocol`.

- [ ] **Step 8: Commit**

```bash
git add src/scholar_mcp/_cache.py src/scholar_mcp/_protocols.py tests/test_cache_standards.py
git commit -m "feat(standards): add standards_sync_runs table and cache methods"
```

---

## Task 5: `SyncReport` dataclass and `Loader` protocol in `_standards_sync.py`

**Files:**
- Create: `src/scholar_mcp/_standards_sync.py`
- Create: `tests/test_standards_sync.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_standards_sync.py` with:

```python
"""Tests for the standards sync dispatcher."""

from __future__ import annotations

from typing import Any

import pytest

from scholar_mcp._cache import ScholarCache
from scholar_mcp._standards_sync import Loader, SyncReport


def test_sync_report_is_dataclass() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(SyncReport)


def test_sync_report_construction_with_defaults() -> None:
    report = SyncReport(
        body="ISO",
        added=0,
        updated=0,
        unchanged=0,
        withdrawn=0,
        errors=[],
        upstream_ref="abc",
        started_at=0.0,
        finished_at=1.0,
    )
    assert report.body == "ISO"
    assert report.errors == []


async def test_loader_protocol_accepts_conforming_class(
    cache: ScholarCache,
) -> None:
    class _Stub:
        body = "STUB"

        async def sync(
            self, cache: Any, *, force: bool = False
        ) -> SyncReport:
            return SyncReport(
                body="STUB",
                added=1,
                updated=0,
                unchanged=0,
                withdrawn=0,
                errors=[],
                upstream_ref=None,
                started_at=0.0,
                finished_at=0.0,
            )

    loader: Loader = _Stub()  # must satisfy the structural type
    report = await loader.sync(cache)
    assert report.added == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_standards_sync.py -v`
Expected: FAIL — `_standards_sync` module does not exist (ImportError).

- [ ] **Step 3: Create `_standards_sync.py`**

Create `src/scholar_mcp/_standards_sync.py`:

```python
"""Standards sync dispatcher — loader protocol, report type, run driver.

This module is intentionally loader-agnostic. It defines the contract
that each body-specific loader must implement and the top-level
:func:`run_sync` function that the CLI calls.

Loaders ship in subsequent PRs: Relaton-backed ISO / IEC / IEEE in PR 2
and PR 3, CSV-backed Common Criteria and Formex-XML CEN/CENELEC in PR 4.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ._protocols import CacheProtocol

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    """Outcome of one body's sync run.

    Attributes:
        body: Standards body key (e.g. ``"ISO"``, ``"IEC"``).
        added: Number of records newly inserted.
        updated: Number of records whose content changed.
        unchanged: Number of records unchanged since last sync.
        withdrawn: Number of records marked ``status="withdrawn"``
            because they disappeared from the upstream dump.
        errors: Non-fatal error strings encountered during the run.
            Fatal errors should raise instead.
        upstream_ref: Commit SHA, ``Last-Modified`` header, or similar
            marker identifying the upstream version that was synced.
            ``None`` if the loader has no such concept.
        started_at: Unix timestamp (seconds) when the run began.
        finished_at: Unix timestamp (seconds) when the run finished.
    """

    body: str
    added: int
    updated: int
    unchanged: int
    withdrawn: int
    errors: list[str] = field(default_factory=list)
    upstream_ref: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0


@runtime_checkable
class Loader(Protocol):
    """Structural type for per-body sync loaders.

    Each loader is responsible for exactly one upstream data source
    (Relaton YAML, CC CSV, EUR-Lex Formex XML, …). Multiple loaders may
    share an implementation module when they share a data format — see
    ``_sync_relaton.py`` in PR 2 for the multi-body pattern.

    Attributes:
        body: Standards body key. Also used as the ``standards.source``
            column value for every record written.
    """

    body: str

    async def sync(
        self, cache: CacheProtocol, *, force: bool = False
    ) -> SyncReport:
        """Pull upstream data into *cache* and return a SyncReport.

        Implementations SHOULD:

        * Check upstream freshness cheaply (commit SHA,
          ``If-Modified-Since``) and return an ``unchanged`` report
          when nothing has changed, unless ``force=True``.
        * Write records via ``cache.set_standard(..., source=body,
          synced=True)`` so they bypass TTL expiry.
        * Mark removed identifiers with ``status="withdrawn"`` rather
          than deleting them.
        * Accumulate non-fatal errors into the report; re-raise fatal
          ones.
        """
        ...


async def run_sync(
    loaders: list[Loader],
    cache: CacheProtocol,
    *,
    force: bool = False,
) -> list[SyncReport]:
    """Run every loader concurrently; persist each report; return them.

    Loaders execute in parallel via :mod:`asyncio`. A failure in one
    loader does not abort the others — its report carries the error.

    Args:
        loaders: Loaders to run. Empty list is valid (returns ``[]``).
        cache: Open :class:`ScholarCache` (or any ``CacheProtocol``).
        force: Passed through to each loader's ``sync()``.

    Returns:
        One :class:`SyncReport` per loader, in the same order as
        *loaders*.
    """
    if not loaders:
        logger.info("sync_no_loaders_registered")
        return []

    async def _run_one(loader: Loader) -> SyncReport:
        started = time.time()
        try:
            report = await loader.sync(cache, force=force)
        except Exception as exc:  # noqa: BLE001 — loader boundary
            logger.error(
                "sync_loader_crashed body=%s err=%s",
                loader.body,
                exc,
                exc_info=True,
            )
            return SyncReport(
                body=loader.body,
                added=0,
                updated=0,
                unchanged=0,
                withdrawn=0,
                errors=[f"{type(exc).__name__}: {exc}"],
                upstream_ref=None,
                started_at=started,
                finished_at=time.time(),
            )
        # Persist a row per body for get_sync_status.
        await cache.set_sync_run(
            body=report.body,
            upstream_ref=report.upstream_ref,
            added=report.added,
            updated=report.updated,
            unchanged=report.unchanged,
            withdrawn=report.withdrawn,
            errors=report.errors,
            started_at=report.started_at or started,
            finished_at=report.finished_at or time.time(),
        )
        return report

    return await asyncio.gather(*(_run_one(loader) for loader in loaders))


def format_reports(reports: list[SyncReport]) -> str:
    """Render *reports* as a human-readable multi-line string.

    Args:
        reports: One report per body.

    Returns:
        One line per body plus a final summary line. Empty *reports*
        returns a single "no loaders registered" line.
    """
    if not reports:
        return "no loaders registered"
    lines = []
    total_added = total_updated = total_withdrawn = total_errors = 0
    for r in reports:
        lines.append(
            f"{r.body} added={r.added} updated={r.updated} "
            f"unchanged={r.unchanged} withdrawn={r.withdrawn} "
            f"errors={len(r.errors)}"
        )
        total_added += r.added
        total_updated += r.updated
        total_withdrawn += r.withdrawn
        total_errors += len(r.errors)
    lines.append(
        f"total added={total_added} updated={total_updated} "
        f"withdrawn={total_withdrawn} errors={total_errors}"
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_standards_sync.py -v`
Expected: PASS for the three tests.

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_standards_sync.py tests/test_standards_sync.py
git commit -m "feat(standards): add SyncReport type and Loader protocol"
```

---

## Task 6: Dispatcher tests for `run_sync` and `format_reports`

**Files:**
- Modify: `tests/test_standards_sync.py`

Covers the dispatcher behaviour: concurrent loader execution, persistence to `standards_sync_runs`, error isolation, empty-loader-list, report formatting.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_standards_sync.py`:

```python
import dataclasses

from scholar_mcp._standards_sync import format_reports, run_sync


def _report(body: str, **kw: Any) -> SyncReport:
    defaults: dict[str, Any] = {
        "body": body,
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "withdrawn": 0,
        "errors": [],
        "upstream_ref": None,
        "started_at": 0.0,
        "finished_at": 0.0,
    }
    defaults.update(kw)
    return SyncReport(**defaults)


class _FakeLoader:
    def __init__(self, body: str, report: SyncReport | None = None,
                 raises: Exception | None = None) -> None:
        self.body = body
        self._report = report or _report(body, added=1, upstream_ref="ref-" + body)
        self._raises = raises
        self.calls = 0

    async def sync(
        self, cache: Any, *, force: bool = False
    ) -> SyncReport:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return dataclasses.replace(self._report)


async def test_run_sync_empty_returns_empty(cache: ScholarCache) -> None:
    assert await run_sync([], cache) == []


async def test_run_sync_persists_each_report(cache: ScholarCache) -> None:
    loaders = [_FakeLoader("ISO"), _FakeLoader("IEC")]
    reports = await run_sync(loaders, cache)
    assert {r.body for r in reports} == {"ISO", "IEC"}
    assert await cache.get_sync_run("ISO") is not None
    assert await cache.get_sync_run("IEC") is not None


async def test_run_sync_isolates_loader_failure(cache: ScholarCache) -> None:
    good = _FakeLoader("ISO")
    bad = _FakeLoader("IEC", raises=RuntimeError("upstream is down"))
    reports = await run_sync([good, bad], cache)
    assert len(reports) == 2
    bad_report = next(r for r in reports if r.body == "IEC")
    assert "RuntimeError" in bad_report.errors[0]
    good_report = next(r for r in reports if r.body == "ISO")
    assert good_report.errors == []


async def test_run_sync_force_propagates(cache: ScholarCache) -> None:
    class _ForceSensitive:
        body = "FS"

        def __init__(self) -> None:
            self.force_seen: bool | None = None

        async def sync(
            self, cache: Any, *, force: bool = False
        ) -> SyncReport:
            self.force_seen = force
            return _report("FS")

    fs = _ForceSensitive()
    await run_sync([fs], cache, force=True)
    assert fs.force_seen is True


def test_format_reports_empty() -> None:
    assert format_reports([]) == "no loaders registered"


def test_format_reports_renders_lines() -> None:
    out = format_reports(
        [
            _report("ISO", added=10, updated=2, unchanged=500, withdrawn=0),
            _report("IEC", added=5, errors=["bad yaml"]),
        ]
    )
    assert "ISO added=10 updated=2 unchanged=500 withdrawn=0 errors=0" in out
    assert "IEC added=5 updated=0 unchanged=0 withdrawn=0 errors=1" in out
    assert "total added=15 updated=2 withdrawn=0 errors=1" in out
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `uv run pytest tests/test_standards_sync.py -v`
Expected: PASS — the dispatcher from Task 5 already implements all of this. (This task is test-first coverage; if any test fails, the implementation in Task 5 is incomplete — fix it in `_standards_sync.py` before continuing.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_standards_sync.py
git commit -m "test(standards): dispatcher persistence, error isolation, force flag"
```

---

## Task 7: CLI `sync-standards` subcommand

**Files:**
- Modify: `src/scholar_mcp/cli.py`
- Create: `tests/test_cli_sync_standards.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_sync_standards.py`:

```python
"""Tests for the scholar-mcp sync-standards CLI subcommand."""

from __future__ import annotations

import asyncio
from pathlib import Path

from click.testing import CliRunner

from scholar_mcp.cli import cli


async def _init_db(path: Path) -> None:
    from scholar_mcp._cache import ScholarCache

    c = ScholarCache(path)
    await c.open()
    await c.close()


def test_sync_standards_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--help"])
    assert result.exit_code == 0
    assert "--body" in result.output
    assert "--force" in result.output


def test_sync_standards_no_loaders_registered(tmp_path: Path) -> None:
    """Zero loaders registered → exits 0 with a clear message."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["sync-standards", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "no loaders registered" in result.output


def test_sync_standards_unknown_body(tmp_path: Path) -> None:
    """Invalid --body value exits 2 (click's usage error)."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["sync-standards", "--body", "XYZ", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert "XYZ" in result.output or "Invalid value" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_sync_standards.py -v`
Expected: FAIL — `sync-standards` subcommand doesn't exist.

- [ ] **Step 3: Register the subcommand**

Append to `src/scholar_mcp/cli.py` (after the `cache_clear` command, before `def main()`):

```python
_SYNC_BODIES = ("ISO", "IEC", "IEEE", "CEN", "CC", "all")


@cli.command("sync-standards")
@click.option(
    "--body",
    type=click.Choice(_SYNC_BODIES, case_sensitive=False),
    default="all",
    show_default=True,
    help="Body to sync. 'all' runs every registered loader.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Bypass upstream-freshness checks and re-sync unconditionally.",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override cache directory.",
)
def sync_standards(body: str, force: bool, cache_dir: Path | None) -> None:
    """Sync Tier 2 standards catalogue data into the local cache.

    Safe to schedule under cron / launchd / systemd timers.

    Exit codes:
        0 — no changes OR synced with updates
        1 — hard failure (no body synced)
        3 — partial failure (some bodies succeeded, some did not)
    """
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._standards_sync import Loader, format_reports, run_sync
    from scholar_mcp.config import load_config

    async def _run() -> int:
        config = load_config()
        db_path = (cache_dir or config.cache_dir) / "cache.db"
        c = ScholarCache(db_path)
        await c.open()
        try:
            loaders = _select_loaders(body)
            reports = await run_sync(loaders, c, force=force)
        finally:
            await c.close()

        click.echo(format_reports(reports))

        if not loaders:
            return 0
        failures = [r for r in reports if r.errors]
        successes = [r for r in reports if not r.errors]
        if failures and not successes:
            return 1
        if failures and successes:
            return 3
        return 0

    exit_code = asyncio.run(_run())
    raise SystemExit(exit_code)


def _select_loaders(body: str) -> list[Loader]:  # type: ignore[name-defined]
    """Return loaders matching *body* ('all' returns every registered).

    Zero loaders are registered in PR 1 — this is a placeholder that
    later PRs (ISO/IEC in PR 2, IEEE in PR 3, CEN+CC in PR 4) replace
    with real registration.
    """
    from scholar_mcp._standards_sync import Loader

    registered: list[Loader] = []
    if body.upper() == "ALL":
        return registered
    return [loader for loader in registered if loader.body == body.upper()]
```

Also add at the top of `cli.py` (imports section) — keep the `TYPE_CHECKING` guard minimal:

```python
# No new top-level imports required; sync-standards uses local imports
# to avoid loading FastMCP/HTTPX when the user runs `cache stats`.
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cli_sync_standards.py -v`
Expected: PASS for all three tests.

- [ ] **Step 5: Run the existing CLI tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS — no regression.

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/cli.py tests/test_cli_sync_standards.py
git commit -m "feat(cli): add scholar-mcp sync-standards subcommand"
```

---

## Task 8: `get_sync_status` MCP tool

**Files:**
- Modify: `src/scholar_mcp/_tools_standards.py`
- Test: `tests/test_tools_standards.py`

- [ ] **Step 1: Inspect existing tool registration pattern**

Read `src/scholar_mcp/_tools_standards.py:20-35` to see how `resolve_standard_identifier` is registered. Match the same annotations and `Depends(get_bundle)` pattern.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_tools_standards.py`:

```python
import json as _json
import time as _time


async def test_get_sync_status_empty(mcp_tool_caller: Any) -> None:
    """No sync rows yet → returns an empty list under 'runs'."""
    result = await mcp_tool_caller("get_sync_status", {})
    payload = _json.loads(result)
    assert payload == {"runs": []}


async def test_get_sync_status_reports_runs(
    mcp_tool_caller: Any, bundle: Any
) -> None:
    await bundle.cache.set_sync_run(
        body="ISO",
        upstream_ref="abc123",
        added=10,
        updated=0,
        unchanged=50_000,
        withdrawn=0,
        errors=[],
        started_at=_time.time() - 5,
        finished_at=_time.time(),
    )
    result = await mcp_tool_caller("get_sync_status", {})
    payload = _json.loads(result)
    assert len(payload["runs"]) == 1
    row = payload["runs"][0]
    assert row["body"] == "ISO"
    assert row["added"] == 10
    assert row["errors"] == []
```

Note: `mcp_tool_caller` and `bundle` are fixtures already defined in `tests/test_tools_standards.py` (or `conftest.py`). If they are not, scan `tests/test_tools_standards.py` for the fixture setup pattern and reuse it. If the file currently exercises tools via direct function calls (no MCP tool invocation), replace `mcp_tool_caller("get_sync_status", {})` with a direct call to the decorated function and adjust the assertion accordingly.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_standards.py -v -k "get_sync_status"`
Expected: FAIL — tool not registered.

- [ ] **Step 4: Register the tool**

In `src/scholar_mcp/_tools_standards.py`, append inside `register_standards_tools(mcp)` (after the `get_standard` tool at line 205):

```python

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def get_sync_status(
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Report the last sync run for each standards body.

        One row per body. ``started_at`` / ``finished_at`` are Unix
        timestamps (seconds). ``errors`` is a list of non-fatal error
        strings from the most recent run (empty on success).

        Returns:
            JSON ``{"runs": [{body, upstream_ref, added, updated,
            unchanged, withdrawn, errors, started_at, finished_at}, ...]}``.
            Empty ``runs`` list when no sync has been run yet.
        """
        runs = await bundle.cache.list_sync_runs()
        return json.dumps({"runs": runs})
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_tools_standards.py -v -k "get_sync_status"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_tools_standards.py tests/test_tools_standards.py
git commit -m "feat(standards): add get_sync_status MCP tool"
```

---

## Task 9: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `docs/tools/index.md`

- [ ] **Step 1: Update `README.md`**

Open `README.md`. Find the Quick Start section (look for `scholar-mcp serve` or similar). Add after the existing invocation example:

```markdown

### Syncing Tier 2 standards catalogues

Tier 2 bodies (ISO, IEC, IEEE, CEN/CENELEC, Common Criteria) are populated
from community-curated bulk dumps rather than live-scraped at MCP-server
runtime. Run the sync on first install and periodically thereafter:

```bash
scholar-mcp sync-standards            # all bodies
scholar-mcp sync-standards --body ISO # single body
scholar-mcp sync-standards --force    # bypass incremental checks
```

Schedule via cron / launchd / systemd timer — weekly is sufficient;
standards change slowly. First sync can take several minutes; subsequent
runs that find no upstream changes exit within seconds.
```

(Only the CLI surface is live in PR 1; no body actually produces records until PR 2 merges. This doc update explains intent and is safe to ship.)

- [ ] **Step 2: Update `docs/tools/index.md`**

Open `docs/tools/index.md`. Find the standards tools section (search for `resolve_standard_identifier` or `search_standards`). Append:

```markdown
### `get_sync_status`

Reports the last run of each Tier 2 standards sync. Returns one record per
body — see `scholar-mcp sync-standards` in the CLI docs.

**Returns:** `{"runs": [{"body", "upstream_ref", "added", "updated", "unchanged", "withdrawn", "errors", "started_at", "finished_at"}]}`.
An empty `runs` list means no sync has been run yet.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/tools/index.md
git commit -m "docs(standards): document sync-standards CLI and get_sync_status tool"
```

---

## Task 10: Manifest version lockstep

**Files:**
- Modify: `server.json`
- Modify: `.claude-plugin/plugin/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/plugin/.mcp.json`

Per CLAUDE.md hard gate #6, the three manifests must carry the same version.

- [ ] **Step 1: Read current version**

Run: `uv run python -c "import json; print(json.load(open('server.json'))['version'])"`
Record the result (e.g. `0.6.4`).

- [ ] **Step 2: Bump patch version**

If current is `X.Y.Z`, new version is `X.Y.(Z+1)`. Edit all three files:

`server.json` — update the `"version"` field.
`.claude-plugin/plugin/.claude-plugin/plugin.json` — update `"version"`.
`.claude-plugin/plugin/.mcp.json` — update `"version"`.

Use string replace; versions must match character-for-character across files.

- [ ] **Step 3: Verify the three files agree**

Run:

```bash
uv run python -c "
import json
a = json.load(open('server.json'))['version']
b = json.load(open('.claude-plugin/plugin/.claude-plugin/plugin.json'))['version']
c = json.load(open('.claude-plugin/plugin/.mcp.json'))['version']
assert a == b == c, (a, b, c)
print('version lockstep ok:', a)
"
```

Expected: `version lockstep ok: X.Y.Z`.

- [ ] **Step 4: Commit**

```bash
git add server.json .claude-plugin/plugin/.claude-plugin/plugin.json .claude-plugin/plugin/.mcp.json
git commit -m "chore: bump version for sync infrastructure PR"
```

---

## Task 11: Final quality gate before opening the PR

- [ ] **Step 1: Run lint (fix pass)**

Run: `uv run ruff check --fix .`
Expected: either "All checks passed!" or fixes applied (review with `git diff`).

- [ ] **Step 2: Run format**

Run: `uv run ruff format .`
Expected: no changes or only reformat of recently-touched files.

- [ ] **Step 3: Verify format is idempotent**

Run: `uv run ruff format --check .`
Expected: "N files already formatted".

- [ ] **Step 4: Run type-check**

Run: `uv run mypy src/`
Expected: "Success: no issues found in N source files".

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -x -q`
Expected: all tests pass. `-x` stops on first failure so you can address regressions immediately.

- [ ] **Step 6: Verify patch coverage**

Identify modules changed in this PR:

```bash
git diff --name-only main -- src/scholar_mcp/ | grep -v __pycache__
```

Run coverage against them:

```bash
uv run pytest --cov=scholar_mcp._standards_sync \
              --cov=scholar_mcp._cache \
              --cov=scholar_mcp.cli \
              --cov=scholar_mcp._tools_standards \
              --cov-report=term-missing \
              tests/test_standards_sync.py \
              tests/test_cache_standards.py \
              tests/test_cli_sync_standards.py \
              tests/test_cli.py \
              tests/test_tools_standards.py \
              tests/test_cache.py
```

Expected: each changed module at ≥80% on lines added in this PR. If any line introduced this PR is uncovered, add a test for it before moving on.

- [ ] **Step 7: If any fixes were needed, commit them**

```bash
git status
# If diffs exist:
git add -u
git commit -m "chore: lint/format/coverage fixes for sync infrastructure"
```

- [ ] **Step 8: Final commit summary**

```bash
git log main..HEAD --oneline
```

Expected: a clean list of task commits matching the sequence above.

---

## Self-review checklist

Before handing off:

- [ ] Spec sections covered: CLI surface (Task 7), `standards.source`/`synced_at` (Tasks 2-3), `standards_sync_runs` (Task 4), `Loader` protocol + `SyncReport` (Task 5), dispatcher (Tasks 5-6), `get_sync_status` (Task 8), TTL bumps (Task 1), docs (Task 9), manifest lockstep (Task 10), quality gate (Task 11). All present.
- [ ] No placeholders — every step has exact code / exact commands.
- [ ] Type consistency — `Loader.body`, `SyncReport.body`, `cache.set_sync_run(body=...)`, `_tools_standards.get_sync_status()` all use `body: str` and the same key set throughout.
- [ ] Zero loaders registered is the intended end-state of PR 1. `_select_loaders("all")` returning `[]` is tested explicitly in Task 7.

Out of scope for this PR (deferred to PRs 2-5):

- `_sync_relaton.py` (ISO, IEC, IEEE) — PR 2 + PR 3.
- `_sync_cc.py`, `_sync_cen.py` — PR 4.
- `_enricher_standards.py` and `_record_types.py` extensions — PR 5.
- Regex extensions in `_standards_client.py` for ISO / IEC / IEEE / CEN / CC — PR 2 (with ISO + IEC) and PR 3 (IEEE) and PR 4 (CEN + CC).

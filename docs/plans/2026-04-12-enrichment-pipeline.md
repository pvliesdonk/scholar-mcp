# v0.6.0 Enrichment Pipeline & Data Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a phased enrichment pipeline and integrate CrossRef, Google Books, WorldCat permalink, cover caching, and chapter-level resolution into the scholar-mcp server.

**Architecture:** An `Enricher` protocol with phased execution groups (phase 0 = primary metadata, phase 1 = secondary sources). Existing OpenAlex and Open Library enrichment migrated onto the pipeline, then CrossRef and Google Books added as new enrichers. Chapter parsing, cover caching, and WorldCat permalinks are standalone features built on top.

**Tech Stack:** Python 3.11+, FastMCP, httpx, aiosqlite, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-04-12-enrichment-pipeline-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/scholar_mcp/_enrichment.py` | `Enricher` protocol + `EnrichmentPipeline` class |
| `src/scholar_mcp/_crossref_client.py` | CrossRef API client (httpx wrapper) |
| `src/scholar_mcp/_google_books_client.py` | Google Books API client (httpx wrapper) |
| `src/scholar_mcp/_chapter_parser.py` | Citation string chapter/page pattern extraction |
| `tests/test_enrichment.py` | Pipeline + enricher tests |
| `tests/test_crossref_client.py` | CrossRef client unit tests |
| `tests/test_google_books_client.py` | Google Books client unit tests |
| `tests/test_chapter_parser.py` | Chapter parser unit tests |

### Modified files

| File | Changes |
|------|---------|
| `src/scholar_mcp/_record_types.py` | Add `BookChapterRecord`; add `worldcat_url`, `snippet`, `cover_path` fields to `BookRecord` |
| `src/scholar_mcp/_protocols.py` | Add `crossref` and `google_books` cache methods |
| `src/scholar_mcp/_cache.py` | Add `crossref` and `google_books` tables, TTLs, and cache methods |
| `src/scholar_mcp/config.py` | Add `google_books_api_key` field |
| `src/scholar_mcp/_server_deps.py` | Add `CrossRefClient`, `GoogleBooksClient`, `EnrichmentPipeline` to `ServiceBundle` |
| `src/scholar_mcp/_book_enrichment.py` | Refactor into `OpenLibraryEnricher` class |
| `src/scholar_mcp/_tools_citation.py` | Extract `OpenAlexEnricher`; replace ad-hoc enrichment with pipeline call |
| `src/scholar_mcp/_tools_search.py` | Replace `enrich_books()` calls with pipeline |
| `src/scholar_mcp/_tools_graph.py` | Replace `enrich_books()` calls with pipeline |
| `src/scholar_mcp/_tools_books.py` | Add `download_cover`/`cover_size` params to `get_book`; add `get_book_excerpt` tool |
| `src/scholar_mcp/_tools_utility.py` | Chapter-aware `batch_resolve` |
| `src/scholar_mcp/_tools_patent.py` | Chapter-aware NPL citation resolution |
| `src/scholar_mcp/_openlibrary_client.py` | Populate `worldcat_url` in `normalize_book()` |
| `tests/conftest.py` | Add new clients + pipeline to `bundle` fixture |

---

## Task 1: Enricher Protocol and EnrichmentPipeline (#62 core)

**Files:**
- Create: `src/scholar_mcp/_enrichment.py`
- Test: `tests/test_enrichment.py`

- [ ] **Step 1: Write failing tests for the Enricher protocol and pipeline**

```python
# tests/test_enrichment.py
"""Tests for the enrichment pipeline."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from scholar_mcp._enrichment import EnrichmentPipeline, Enricher


class StubEnricher:
    """Enricher stub for testing."""

    def __init__(
        self,
        name: str,
        phase: int = 0,
        tags: frozenset[str] = frozenset({"papers"}),
        *,
        predicate: bool = True,
    ) -> None:
        self.name = name
        self.phase = phase
        self.tags = tags
        self._predicate = predicate
        self.calls: list[dict[str, Any]] = []

    def can_enrich(self, record: dict[str, Any]) -> bool:
        return self._predicate

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        self.calls.append(record)
        record[f"enriched_by_{self.name}"] = True


class FailingEnricher(StubEnricher):
    """Enricher that raises on enrich()."""

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        raise RuntimeError("enrichment failed")


def test_stub_satisfies_enricher_protocol() -> None:
    e = StubEnricher("test")
    assert isinstance(e, Enricher)


@pytest.mark.anyio
async def test_pipeline_runs_single_enricher() -> None:
    e = StubEnricher("alpha")
    pipeline = EnrichmentPipeline([e])
    records = [{"title": "A paper"}]
    await pipeline.enrich(records, bundle=None)
    assert records[0]["enriched_by_alpha"] is True
    assert len(e.calls) == 1


@pytest.mark.anyio
async def test_pipeline_skips_when_can_enrich_false() -> None:
    e = StubEnricher("alpha", predicate=False)
    pipeline = EnrichmentPipeline([e])
    records = [{"title": "A paper"}]
    await pipeline.enrich(records, bundle=None)
    assert "enriched_by_alpha" not in records[0]
    assert len(e.calls) == 0


@pytest.mark.anyio
async def test_pipeline_filters_by_tags() -> None:
    papers_e = StubEnricher("papers_e", tags=frozenset({"papers"}))
    books_e = StubEnricher("books_e", tags=frozenset({"books"}))
    pipeline = EnrichmentPipeline([papers_e, books_e])
    records = [{"title": "A paper"}]
    await pipeline.enrich(records, bundle=None, tags=frozenset({"books"}))
    assert "enriched_by_papers_e" not in records[0]
    assert records[0]["enriched_by_books_e"] is True


@pytest.mark.anyio
async def test_pipeline_respects_phase_order() -> None:
    order: list[str] = []

    class OrderTracker(StubEnricher):
        async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
            order.append(self.name)
            await asyncio.sleep(0.01)  # simulate async work

    phase0 = OrderTracker("phase0", phase=0)
    phase1 = OrderTracker("phase1", phase=1)
    # Register in reverse order to verify phase sorting
    pipeline = EnrichmentPipeline([phase1, phase0])
    await pipeline.enrich([{"title": "test"}], bundle=None)
    assert order == ["phase0", "phase1"]


@pytest.mark.anyio
async def test_pipeline_error_does_not_propagate() -> None:
    failing = FailingEnricher("bad")
    good = StubEnricher("good")
    pipeline = EnrichmentPipeline([failing, good])
    records = [{"title": "test"}]
    await pipeline.enrich(records, bundle=None)
    # good enricher still ran despite failing enricher
    assert records[0]["enriched_by_good"] is True


@pytest.mark.anyio
async def test_pipeline_multiple_records() -> None:
    e = StubEnricher("alpha")
    pipeline = EnrichmentPipeline([e])
    records = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    await pipeline.enrich(records, bundle=None)
    assert all(r.get("enriched_by_alpha") for r in records)
    assert len(e.calls) == 3


@pytest.mark.anyio
async def test_pipeline_concurrency_bounded() -> None:
    max_concurrent = 0
    current = 0

    class ConcurrencyTracker(StubEnricher):
        async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
            nonlocal max_concurrent, current
            current += 1
            if current > max_concurrent:
                max_concurrent = current
            await asyncio.sleep(0.02)
            current -= 1

    e = ConcurrencyTracker("tracker")
    pipeline = EnrichmentPipeline([e])
    records = [{"id": i} for i in range(10)]
    await pipeline.enrich(records, bundle=None, concurrency=3)
    assert max_concurrent <= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enrichment.py -x -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scholar_mcp._enrichment'`

- [ ] **Step 3: Implement the Enricher protocol and EnrichmentPipeline**

```python
# src/scholar_mcp/_enrichment.py
"""Enrichment pipeline: phased, tag-filtered, concurrent enrichment."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Enricher(Protocol):
    """Protocol for pluggable record enrichers.

    Attributes:
        name: Short identifier for logging (e.g. ``"openalex"``).
        phase: Execution order group. Lower phases run first.
        tags: Record-type tags this enricher applies to
            (e.g. ``frozenset({"papers"})``).
    """

    name: str
    phase: int
    tags: frozenset[str]

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Fast predicate — no I/O. Check if this enricher applies.

        Args:
            record: Record dict to inspect.

        Returns:
            True if this enricher should run on the record.
        """
        ...

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Mutate record in-place with enriched data.

        Best-effort: implementations should not raise.

        Args:
            record: Record dict to enrich (mutated in-place).
            bundle: ServiceBundle for API/cache access.
        """
        ...


class EnrichmentPipeline:
    """Run enrichers on records in phase order with bounded concurrency.

    Enrichers are grouped by phase number and executed concurrently within
    each phase. Phase groups run sequentially (phase 0 completes before
    phase 1 starts). Errors in individual enrichers are caught and logged.

    Args:
        enrichers: List of enricher instances.
    """

    def __init__(self, enrichers: list[Enricher]) -> None:
        self._phases: dict[int, list[Enricher]] = defaultdict(list)
        for e in enrichers:
            self._phases[e.phase].append(e)

    async def enrich(
        self,
        records: list[dict[str, Any]],
        bundle: Any,
        *,
        tags: frozenset[str] | None = None,
        concurrency: int = 5,
    ) -> None:
        """Run matching enrichers on all records, phase by phase.

        Args:
            records: List of record dicts to enrich (mutated in-place).
            bundle: ServiceBundle for API/cache access.
            tags: If provided, only run enrichers whose tags intersect.
            concurrency: Max concurrent enrich() calls per phase.
        """
        sem = asyncio.Semaphore(concurrency)

        for phase_num in sorted(self._phases):
            enrichers = self._phases[phase_num]
            if tags is not None:
                enrichers = [e for e in enrichers if e.tags & tags]
            if not enrichers:
                continue

            tasks: list[asyncio.Task[None]] = []
            for enricher in enrichers:
                for record in records:
                    if enricher.can_enrich(record):
                        tasks.append(
                            asyncio.create_task(
                                self._run_one(enricher, record, bundle, sem)
                            )
                        )
            if tasks:
                await asyncio.gather(*tasks)

    @staticmethod
    async def _run_one(
        enricher: Enricher,
        record: dict[str, Any],
        bundle: Any,
        sem: asyncio.Semaphore,
    ) -> None:
        """Run a single enricher on a single record, with error trapping.

        Args:
            enricher: The enricher to run.
            record: Record to enrich.
            bundle: ServiceBundle for API/cache access.
            sem: Concurrency-bounding semaphore.
        """
        async with sem:
            try:
                await enricher.enrich(record, bundle)
            except Exception:
                logger.debug(
                    "enricher_failed name=%s", enricher.name, exc_info=True
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enrichment.py -x -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix src/scholar_mcp/_enrichment.py tests/test_enrichment.py
uv run ruff format src/scholar_mcp/_enrichment.py tests/test_enrichment.py
git add src/scholar_mcp/_enrichment.py tests/test_enrichment.py
git commit -m "feat: add Enricher protocol and EnrichmentPipeline (#62)"
```

---

## Task 2: OpenAlexEnricher — Extract from _tools_citation.py (#62 migration)

**Files:**
- Create: `src/scholar_mcp/_enricher_openalex.py`
- Test: `tests/test_enricher_openalex.py`

- [ ] **Step 1: Write failing tests for OpenAlexEnricher**

```python
# tests/test_enricher_openalex.py
"""Tests for OpenAlexEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from scholar_mcp._enricher_openalex import OpenAlexEnricher
from scholar_mcp._enrichment import Enricher


def test_satisfies_enricher_protocol() -> None:
    e = OpenAlexEnricher()
    assert isinstance(e, Enricher)
    assert e.name == "openalex"
    assert e.phase == 0
    assert e.tags == frozenset({"papers"})


def test_can_enrich_true_when_doi_and_no_venue() -> None:
    e = OpenAlexEnricher()
    record = {"externalIds": {"DOI": "10.1234/test"}, "venue": ""}
    assert e.can_enrich(record) is True


def test_can_enrich_false_when_venue_present() -> None:
    e = OpenAlexEnricher()
    record = {"externalIds": {"DOI": "10.1234/test"}, "venue": "Nature"}
    assert e.can_enrich(record) is False


def test_can_enrich_false_when_no_doi() -> None:
    e = OpenAlexEnricher()
    record = {"externalIds": {}, "venue": ""}
    assert e.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_fills_venue_from_cache() -> None:
    e = OpenAlexEnricher()
    record: dict[str, Any] = {"externalIds": {"DOI": "10.1234/test"}, "venue": ""}
    bundle = AsyncMock()
    bundle.cache.get_openalex.return_value = {
        "primary_location": {"source": {"display_name": "Nature"}}
    }
    await e.enrich(record, bundle)
    assert record["venue"] == "Nature"
    bundle.openalex.get_by_doi.assert_not_called()


@pytest.mark.anyio
async def test_enrich_fills_venue_from_api() -> None:
    e = OpenAlexEnricher()
    record: dict[str, Any] = {"externalIds": {"DOI": "10.1234/test"}, "venue": ""}
    bundle = AsyncMock()
    bundle.cache.get_openalex.return_value = None
    bundle.openalex.get_by_doi.return_value = {
        "primary_location": {"source": {"display_name": "Science"}}
    }
    await e.enrich(record, bundle)
    assert record["venue"] == "Science"
    bundle.cache.set_openalex.assert_awaited_once()


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    e = OpenAlexEnricher()
    record: dict[str, Any] = {"externalIds": {"DOI": "10.1234/test"}, "venue": ""}
    bundle = AsyncMock()
    bundle.cache.get_openalex.side_effect = RuntimeError("network fail")
    await e.enrich(record, bundle)
    assert record.get("venue") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enricher_openalex.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement OpenAlexEnricher**

```python
# src/scholar_mcp/_enricher_openalex.py
"""OpenAlex enricher — fills missing venue metadata via DOI lookup."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OpenAlexEnricher:
    """Enricher that populates paper venue from OpenAlex.

    Phase 0 (primary). Tags: papers.
    """

    name: str = "openalex"
    phase: int = 0
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """True when record has a DOI but no venue."""
        if record.get("venue"):
            return False
        doi = (record.get("externalIds") or {}).get("DOI")
        return bool(doi)

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill venue from OpenAlex cache or API.

        Args:
            record: Paper dict (mutated in-place).
            bundle: ServiceBundle with openalex client and cache.
        """
        doi = (record.get("externalIds") or {}).get("DOI")
        if not doi:
            return
        try:
            cached = await bundle.cache.get_openalex(doi)
            oa_data = (
                cached
                if cached is not None
                else await bundle.openalex.get_by_doi(doi)
            )
            if oa_data is None:
                return
            if cached is None:
                await bundle.cache.set_openalex(doi, oa_data)
            loc = oa_data.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name")
            if venue:
                record["venue"] = venue
        except Exception:
            logger.debug("openalex_enrich_failed doi=%s", doi, exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enricher_openalex.py -x -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix src/scholar_mcp/_enricher_openalex.py tests/test_enricher_openalex.py
uv run ruff format src/scholar_mcp/_enricher_openalex.py tests/test_enricher_openalex.py
git add src/scholar_mcp/_enricher_openalex.py tests/test_enricher_openalex.py
git commit -m "feat: extract OpenAlexEnricher from inline citation logic (#62)"
```

---

## Task 3: OpenLibraryEnricher — Refactor _book_enrichment.py (#62 migration)

**Files:**
- Create: `src/scholar_mcp/_enricher_openlibrary.py`
- Test: `tests/test_enricher_openlibrary.py`
- Modify: `src/scholar_mcp/_book_enrichment.py` (keep helper functions, remove `enrich_books`)

The existing helpers (`_resolve_author_keys`, `_extract_author_keys`,
`enrich_authors_from_work`, `_needs_book_enrichment`, `_extract_isbn`,
`_enrich_one`, `_to_enrichment_dict`) stay in `_book_enrichment.py` since
they're also used by `_tools_books.py` resolvers. The enricher wraps them.

- [ ] **Step 1: Write failing tests for OpenLibraryEnricher**

```python
# tests/test_enricher_openlibrary.py
"""Tests for OpenLibraryEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from scholar_mcp._enricher_openlibrary import OpenLibraryEnricher
from scholar_mcp._enrichment import Enricher


def test_satisfies_enricher_protocol() -> None:
    e = OpenLibraryEnricher()
    assert isinstance(e, Enricher)
    assert e.name == "openlibrary"
    assert e.phase == 1
    assert e.tags == frozenset({"papers"})


def test_can_enrich_true_when_isbn_present() -> None:
    e = OpenLibraryEnricher()
    record = {"externalIds": {"ISBN": "9780262035613"}}
    assert e.can_enrich(record) is True


def test_can_enrich_false_when_no_isbn() -> None:
    e = OpenLibraryEnricher()
    record = {"externalIds": {"DOI": "10.1234/test"}}
    assert e.can_enrich(record) is False


def test_can_enrich_false_when_no_external_ids() -> None:
    e = OpenLibraryEnricher()
    record = {"title": "A paper"}
    assert e.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_uses_cache() -> None:
    e = OpenLibraryEnricher()
    record: dict[str, Any] = {"externalIds": {"ISBN": "9780262035613"}}
    bundle = AsyncMock()
    bundle.cache.get_book_by_isbn.return_value = {
        "title": "Deep Learning",
        "publisher": "MIT Press",
        "isbn_13": "9780262035613",
    }
    await e.enrich(record, bundle)
    assert record["book_metadata"]["publisher"] == "MIT Press"
    bundle.openlibrary.get_by_isbn.assert_not_called()


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    e = OpenLibraryEnricher()
    record: dict[str, Any] = {"externalIds": {"ISBN": "9780262035613"}}
    bundle = AsyncMock()
    bundle.cache.get_book_by_isbn.side_effect = RuntimeError("db error")
    await e.enrich(record, bundle)
    # Should not raise; record unchanged
    assert "book_metadata" not in record
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enricher_openlibrary.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement OpenLibraryEnricher**

```python
# src/scholar_mcp/_enricher_openlibrary.py
"""Open Library enricher — adds book metadata to papers with ISBNs."""

from __future__ import annotations

import logging
from typing import Any

from ._book_enrichment import _enrich_one
from ._rate_limiter import RateLimitedError

logger = logging.getLogger(__name__)


class OpenLibraryEnricher:
    """Enricher that populates paper book_metadata from Open Library.

    Phase 1 (secondary). Tags: papers. Runs after phase 0 so that
    OpenAlex may have already populated externalIds with an ISBN.
    """

    name: str = "openlibrary"
    phase: int = 1
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """True when record has an ISBN in externalIds."""
        ext = record.get("externalIds") or {}
        return bool(ext.get("ISBN"))

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill book_metadata from Open Library cache or API.

        Args:
            record: Paper dict (mutated in-place).
            bundle: ServiceBundle with openlibrary client and cache.
        """
        try:
            await _enrich_one(record, bundle)
        except RateLimitedError:
            logger.debug(
                "openlibrary_rate_limited paper=%s", record.get("paperId")
            )
        except Exception:
            logger.debug(
                "openlibrary_enrich_failed paper=%s",
                record.get("paperId"),
                exc_info=True,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enricher_openlibrary.py -x -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix src/scholar_mcp/_enricher_openlibrary.py tests/test_enricher_openlibrary.py
uv run ruff format src/scholar_mcp/_enricher_openlibrary.py tests/test_enricher_openlibrary.py
git add src/scholar_mcp/_enricher_openlibrary.py tests/test_enricher_openlibrary.py
git commit -m "feat: extract OpenLibraryEnricher from book_enrichment (#62)"
```

---

## Task 4: Wire Pipeline into ServiceBundle and Update Call Sites (#62 integration)

**Files:**
- Modify: `src/scholar_mcp/_server_deps.py:37-59` (ServiceBundle), `src/scholar_mcp/_server_deps.py:62-155` (lifespan)
- Modify: `src/scholar_mcp/_tools_search.py` (replace `enrich_books` calls)
- Modify: `src/scholar_mcp/_tools_graph.py` (replace `enrich_books` calls)
- Modify: `src/scholar_mcp/_tools_citation.py:28-55` (remove `_enrich_paper`, use pipeline)
- Modify: `tests/conftest.py` (add pipeline to bundle fixture)

- [ ] **Step 1: Add `enrichment` to ServiceBundle**

In `src/scholar_mcp/_server_deps.py`, add the import and field:

Add to imports (after line 24):
```python
from ._enrichment import EnrichmentPipeline
```

Add to `ServiceBundle` dataclass (after line 59, before the closing of the class):
```python
    enrichment: EnrichmentPipeline
```

- [ ] **Step 2: Create the pipeline in lifespan**

In `src/scholar_mcp/_server_deps.py`, add enricher imports (after the `EnrichmentPipeline` import):
```python
from ._enricher_openalex import OpenAlexEnricher
from ._enricher_openlibrary import OpenLibraryEnricher
```

After the `standards` client creation (after line 131) and before the `bundle = ServiceBundle(` line, add:
```python
    enrichment = EnrichmentPipeline([
        OpenAlexEnricher(),
        OpenLibraryEnricher(),
    ])
```

Add `enrichment=enrichment` to the `ServiceBundle(...)` constructor call.

- [ ] **Step 3: Update conftest.py bundle fixture**

In `tests/conftest.py`, add imports:
```python
from scholar_mcp._enrichment import EnrichmentPipeline
from scholar_mcp._enricher_openalex import OpenAlexEnricher
from scholar_mcp._enricher_openlibrary import OpenLibraryEnricher
```

Add to the `ServiceBundle(...)` call in the `bundle` fixture:
```python
        enrichment=EnrichmentPipeline([
            OpenAlexEnricher(),
            OpenLibraryEnricher(),
        ]),
```

- [ ] **Step 4: Replace `enrich_books()` calls in `_tools_search.py`**

In `src/scholar_mcp/_tools_search.py`:
- Remove line 13: `from ._book_enrichment import enrich_books`
- Replace each `await enrich_books([data], bundle)` with:
  `await bundle.enrichment.enrich([data], bundle, tags=frozenset({"papers"}))`
- Replace each `await enrich_books([fetched], bundle)` with:
  `await bundle.enrichment.enrich([fetched], bundle, tags=frozenset({"papers"}))`

- [ ] **Step 5: Replace `enrich_books()` calls in `_tools_graph.py`**

In `src/scholar_mcp/_tools_graph.py`:
- Remove line 14: `from ._book_enrichment import enrich_books`
- Replace each `await enrich_books(papers, bundle)` / `await enrich_books(citing_papers, bundle)` / `await enrich_books(node_list, bundle)` with:
  `await bundle.enrichment.enrich(<list_var>, bundle, tags=frozenset({"papers"}))`

- [ ] **Step 6: Replace inline `_enrich_paper()` in `_tools_citation.py`**

In `src/scholar_mcp/_tools_citation.py`:
- Remove the `_enrich_paper` function (lines 28-55)
- Replace the call at line 132 (`await _enrich_paper(p, bundle)`) with:
  `await bundle.enrichment.enrich([p], bundle, tags=frozenset({"papers"}))`

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass. The pipeline now runs both enrichers in the same order as before.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_server_deps.py src/scholar_mcp/_tools_search.py \
  src/scholar_mcp/_tools_graph.py src/scholar_mcp/_tools_citation.py \
  tests/conftest.py
git commit -m "refactor: wire EnrichmentPipeline into ServiceBundle, replace ad-hoc enrichment (#62)"
```

---

## Task 5: CrossRef Client and Cache (#67 infrastructure)

**Files:**
- Create: `src/scholar_mcp/_crossref_client.py`
- Test: `tests/test_crossref_client.py`
- Modify: `src/scholar_mcp/_protocols.py:60-70` (add crossref methods after book methods)
- Modify: `src/scholar_mcp/_cache.py` (add TTL, schema table, cache methods)

- [ ] **Step 1: Write failing tests for CrossRefClient**

```python
# tests/test_crossref_client.py
"""Tests for CrossRefClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from scholar_mcp._crossref_client import CrossRefClient


@pytest.fixture
def client() -> CrossRefClient:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    return CrossRefClient(mock_http)


@pytest.mark.anyio
async def test_get_by_doi_returns_data(client: CrossRefClient) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "status": "ok",
        "message": {
            "DOI": "10.1234/test",
            "type": "journal-article",
            "title": ["Test Article"],
            "publisher": "Test Publisher",
        },
    }
    response.raise_for_status = MagicMock()
    client._client.get = AsyncMock(return_value=response)
    result = await client.get_by_doi("10.1234/test")
    assert result is not None
    assert result["DOI"] == "10.1234/test"
    assert result["publisher"] == "Test Publisher"


@pytest.mark.anyio
async def test_get_by_doi_returns_none_on_404(client: CrossRefClient) -> None:
    response = MagicMock()
    response.status_code = 404
    client._client.get = AsyncMock(return_value=response)
    result = await client.get_by_doi("10.1234/missing")
    assert result is None


@pytest.mark.anyio
async def test_get_by_doi_returns_none_on_error(client: CrossRefClient) -> None:
    response = MagicMock()
    response.status_code = 500
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=response)
    )
    client._client.get = AsyncMock(return_value=response)
    result = await client.get_by_doi("10.1234/broken")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_crossref_client.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CrossRefClient**

```python
# src/scholar_mcp/_crossref_client.py
"""CrossRef API client for metadata enrichment."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CrossRefClient:
    """Async client for the CrossRef REST API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at CrossRef.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch CrossRef work metadata by DOI.

        Args:
            doi: DOI string (e.g. ``10.1234/test``).

        Returns:
            CrossRef work message dict, or None if not found.
        """
        url = f"/works/{doi}"
        try:
            r = await self._client.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            return data.get("message")  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("crossref_error doi=%s status=%s", doi, r.status_code)
            return None

    async def search_chapters(self, title: str) -> list[dict[str, Any]]:
        """Search CrossRef for book-chapter records by title.

        Args:
            title: Bibliographic title to search for.

        Returns:
            List of CrossRef work message dicts.
        """
        try:
            r = await self._client.get(
                "/works",
                params={
                    "query.bibliographic": title,
                    "filter": "type:book-chapter",
                    "rows": 5,
                },
            )
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("items", [])  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("crossref_search_error title=%s", title[:80])
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_crossref_client.py -x -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Add CrossRef cache protocol methods**

In `src/scholar_mcp/_protocols.py`, add after the book methods block (after line 70):

```python
    # CrossRef methods
    async def get_crossref(self, doi: str) -> dict[str, Any] | None: ...
    async def set_crossref(self, doi: str, data: dict[str, Any]) -> None: ...
```

- [ ] **Step 6: Add CrossRef cache schema, TTL, and implementation**

In `src/scholar_mcp/_cache.py`:

Add TTL constant after line 82 (after `_STANDARD_INDEX_TTL`):
```python
_CROSSREF_TTL = 30 * 86400  # 30 days
```

Add table to `_SCHEMA` (before the closing `"""`):
```sql
CREATE TABLE IF NOT EXISTS crossref (
    doi       TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crossref_cached ON crossref(cached_at);
```

Add cache methods after the book methods section (after `set_book_subject`):
```python
    async def get_crossref(self, doi: str) -> dict[str, Any] | None:
        """Return cached CrossRef data by DOI or None if missing/stale.

        Args:
            doi: DOI string.

        Returns:
            CrossRef metadata dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM crossref WHERE doi = ?", (doi,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _CROSSREF_TTL:
            return None
        return json.loads(row[0])

    async def set_crossref(self, doi: str, data: dict[str, Any]) -> None:
        """Cache CrossRef data by DOI.

        Args:
            doi: DOI string.
            data: CrossRef metadata dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO crossref (doi, data, cached_at) VALUES (?, ?, ?)",
            (doi, json.dumps(data), time.time()),
        )
        await db.commit()
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass, including `test_protocols.py` (protocol conformance).

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_crossref_client.py tests/test_crossref_client.py \
  src/scholar_mcp/_protocols.py src/scholar_mcp/_cache.py
git commit -m "feat: add CrossRef client and cache layer (#67)"
```

---

## Task 6: CrossRefEnricher (#67 enricher)

**Files:**
- Create: `src/scholar_mcp/_enricher_crossref.py`
- Test: `tests/test_enricher_crossref.py`
- Modify: `src/scholar_mcp/_server_deps.py` (add CrossRefClient to bundle, register enricher)
- Modify: `tests/conftest.py` (add CrossRefClient + enricher to fixture)

- [ ] **Step 1: Write failing tests for CrossRefEnricher**

```python
# tests/test_enricher_crossref.py
"""Tests for CrossRefEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from scholar_mcp._enricher_crossref import CrossRefEnricher
from scholar_mcp._enrichment import Enricher


def test_satisfies_enricher_protocol() -> None:
    e = CrossRefEnricher()
    assert isinstance(e, Enricher)
    assert e.name == "crossref"
    assert e.phase == 0
    assert e.tags == frozenset({"papers"})


def test_can_enrich_true_when_doi_and_sparse_metadata() -> None:
    e = CrossRefEnricher()
    record = {"externalIds": {"DOI": "10.1234/test"}}
    assert e.can_enrich(record) is True


def test_can_enrich_false_when_no_doi() -> None:
    e = CrossRefEnricher()
    record = {"externalIds": {}}
    assert e.can_enrich(record) is False


def test_can_enrich_false_when_crossref_already_present() -> None:
    e = CrossRefEnricher()
    record = {
        "externalIds": {"DOI": "10.1234/test"},
        "crossref_metadata": {"publisher": "ACM"},
    }
    assert e.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_fills_crossref_metadata_from_cache() -> None:
    e = CrossRefEnricher()
    record: dict[str, Any] = {"externalIds": {"DOI": "10.1234/test"}}
    bundle = AsyncMock()
    bundle.cache.get_crossref.return_value = {
        "publisher": "ACM",
        "type": "journal-article",
    }
    await e.enrich(record, bundle)
    assert record["crossref_metadata"]["publisher"] == "ACM"
    bundle.crossref.get_by_doi.assert_not_called()


@pytest.mark.anyio
async def test_enrich_fills_crossref_metadata_from_api() -> None:
    e = CrossRefEnricher()
    record: dict[str, Any] = {"externalIds": {"DOI": "10.1234/test"}}
    bundle = AsyncMock()
    bundle.cache.get_crossref.return_value = None
    bundle.crossref.get_by_doi.return_value = {
        "publisher": "Springer",
        "type": "book-chapter",
        "container-title": ["Handbook of X"],
        "page": "45-67",
    }
    await e.enrich(record, bundle)
    assert record["crossref_metadata"]["publisher"] == "Springer"
    assert record["crossref_metadata"]["type"] == "book-chapter"
    bundle.cache.set_crossref.assert_awaited_once()


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    e = CrossRefEnricher()
    record: dict[str, Any] = {"externalIds": {"DOI": "10.1234/test"}}
    bundle = AsyncMock()
    bundle.cache.get_crossref.side_effect = RuntimeError("db fail")
    await e.enrich(record, bundle)
    assert "crossref_metadata" not in record
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enricher_crossref.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CrossRefEnricher**

```python
# src/scholar_mcp/_enricher_crossref.py
"""CrossRef enricher — fills sparse paper metadata via DOI lookup."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CrossRefEnricher:
    """Enricher that populates crossref_metadata from CrossRef API.

    Phase 0 (primary). Tags: papers. Predicate: record has DOI and no
    existing crossref_metadata.
    """

    name: str = "crossref"
    phase: int = 0
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """True when record has a DOI and no crossref_metadata."""
        if record.get("crossref_metadata"):
            return False
        doi = (record.get("externalIds") or {}).get("DOI")
        return bool(doi)

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill crossref_metadata from cache or CrossRef API.

        Args:
            record: Paper dict (mutated in-place).
            bundle: ServiceBundle with crossref client and cache.
        """
        doi = (record.get("externalIds") or {}).get("DOI")
        if not doi:
            return
        try:
            cached = await bundle.cache.get_crossref(doi)
            cr_data = (
                cached
                if cached is not None
                else await bundle.crossref.get_by_doi(doi)
            )
            if cr_data is None:
                return
            if cached is None:
                await bundle.cache.set_crossref(doi, cr_data)
            record["crossref_metadata"] = cr_data
        except Exception:
            logger.debug("crossref_enrich_failed doi=%s", doi, exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enricher_crossref.py -x -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Wire CrossRefClient into ServiceBundle**

In `src/scholar_mcp/_server_deps.py`:

Add import:
```python
from ._crossref_client import CrossRefClient
from ._enricher_crossref import CrossRefEnricher
```

Add to `ServiceBundle` dataclass:
```python
    crossref: CrossRefClient
```

In `make_service_lifespan()`, after the `openlibrary` setup and before `docling`, add:
```python
    crossref_http = httpx.AsyncClient(
        base_url="https://api.crossref.org",
        headers={"User-Agent": ua},
        timeout=30.0,
    )
    crossref = CrossRefClient(crossref_http)
```

Add `crossref=crossref` to the `ServiceBundle(...)` constructor.

Add `CrossRefEnricher()` to the `EnrichmentPipeline([...])` list.

In the `finally` block, add cleanup:
```python
        await crossref_http.aclose()
```

- [ ] **Step 6: Update conftest.py**

Add to imports:
```python
from scholar_mcp._crossref_client import CrossRefClient
from scholar_mcp._enricher_crossref import CrossRefEnricher
```

In the `bundle` fixture, create and add:
```python
    crossref_http = httpx.AsyncClient(
        base_url="https://api.crossref.org", timeout=10.0
    )
    crossref = CrossRefClient(crossref_http)
```

Add `crossref=crossref` to `ServiceBundle(...)`.

Add `CrossRefEnricher()` to the `EnrichmentPipeline([...])`.

Add cleanup: `await crossref_http.aclose()`.

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_enricher_crossref.py tests/test_enricher_crossref.py \
  src/scholar_mcp/_server_deps.py tests/conftest.py
git commit -m "feat: add CrossRefEnricher with DOI-based metadata lookup (#67)"
```

---

## Task 7: Google Books Client, Cache, and Config (#61 infrastructure)

**Files:**
- Create: `src/scholar_mcp/_google_books_client.py`
- Test: `tests/test_google_books_client.py`
- Modify: `src/scholar_mcp/config.py:12-47` (add `google_books_api_key`)
- Modify: `src/scholar_mcp/_protocols.py` (add google_books methods)
- Modify: `src/scholar_mcp/_cache.py` (add table, TTL, methods)

- [ ] **Step 1: Write failing tests for GoogleBooksClient**

```python
# tests/test_google_books_client.py
"""Tests for GoogleBooksClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from scholar_mcp._google_books_client import GoogleBooksClient


@pytest.fixture
def client() -> GoogleBooksClient:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    return GoogleBooksClient(mock_http)


@pytest.mark.anyio
async def test_search_by_isbn_returns_volume(client: GoogleBooksClient) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "totalItems": 1,
        "items": [
            {
                "id": "vol123",
                "volumeInfo": {
                    "title": "Deep Learning",
                    "previewLink": "https://books.google.com/books?id=vol123",
                },
                "searchInfo": {"textSnippet": "A comprehensive intro..."},
            }
        ],
    }
    response.raise_for_status = MagicMock()
    client._client.get = AsyncMock(return_value=response)
    result = await client.search_by_isbn("9780262035613")
    assert result is not None
    assert result["id"] == "vol123"


@pytest.mark.anyio
async def test_search_by_isbn_returns_none_when_empty(
    client: GoogleBooksClient,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"totalItems": 0, "items": []}
    response.raise_for_status = MagicMock()
    client._client.get = AsyncMock(return_value=response)
    result = await client.search_by_isbn("0000000000000")
    assert result is None


@pytest.mark.anyio
async def test_get_volume_returns_data(client: GoogleBooksClient) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "id": "vol123",
        "volumeInfo": {"title": "Deep Learning", "description": "A book."},
        "accessInfo": {"viewability": "PARTIAL"},
    }
    response.raise_for_status = MagicMock()
    client._client.get = AsyncMock(return_value=response)
    result = await client.get_volume("vol123")
    assert result is not None
    assert result["accessInfo"]["viewability"] == "PARTIAL"


@pytest.mark.anyio
async def test_get_volume_returns_none_on_404(client: GoogleBooksClient) -> None:
    response = MagicMock()
    response.status_code = 404
    client._client.get = AsyncMock(return_value=response)
    result = await client.get_volume("missing")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_google_books_client.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GoogleBooksClient**

```python
# src/scholar_mcp/_google_books_client.py
"""Google Books API client for book enrichment and excerpt retrieval."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GoogleBooksClient:
    """Async client for the Google Books API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at Google Books.
        api_key: Optional API key for higher rate limits.
    """

    def __init__(
        self, http_client: httpx.AsyncClient, *, api_key: str | None = None
    ) -> None:
        self._client = http_client
        self._api_key = api_key

    def _params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build query params, adding API key if configured.

        Args:
            extra: Additional query parameters.

        Returns:
            Merged parameter dict.
        """
        params: dict[str, str] = {}
        if self._api_key:
            params["key"] = self._api_key
        if extra:
            params.update(extra)
        return params

    async def search_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        """Search Google Books by ISBN and return the first matching volume.

        Args:
            isbn: ISBN-10 or ISBN-13 string.

        Returns:
            Google Books volume dict, or None if no match.
        """
        try:
            r = await self._client.get(
                "/volumes", params=self._params({"q": f"isbn:{isbn}"})
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("items") or []
            return items[0] if items else None  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("google_books_search_error isbn=%s", isbn)
            return None

    async def get_volume(self, volume_id: str) -> dict[str, Any] | None:
        """Fetch a Google Books volume by ID.

        Args:
            volume_id: Google Books volume ID.

        Returns:
            Volume dict, or None if not found.
        """
        try:
            r = await self._client.get(
                f"/volumes/{volume_id}", params=self._params()
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning(
                "google_books_volume_error id=%s status=%s",
                volume_id,
                r.status_code,
            )
            return None
```

- [ ] **Step 4: Run client tests**

Run: `uv run pytest tests/test_google_books_client.py -x -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Add `google_books_api_key` to config**

In `src/scholar_mcp/config.py`:

Add to `ServerConfig` docstring (after `epo_consumer_secret` doc):
```
        google_books_api_key: Google Books API key (optional, higher rate limits).
```

Add field to `ServerConfig` (after line 40, before `epo_configured` property):
```python
    google_books_api_key: str | None = None
```

Add to `load_config()` return statement (after `epo_consumer_secret` line):
```python
        google_books_api_key=_str("GOOGLE_BOOKS_API_KEY"),
```

- [ ] **Step 6: Add Google Books cache protocol, schema, and implementation**

In `src/scholar_mcp/_protocols.py`, add after the CrossRef methods:
```python
    # Google Books methods
    async def get_google_books(self, isbn: str) -> dict[str, Any] | None: ...
    async def set_google_books(self, isbn: str, data: dict[str, Any]) -> None: ...
```

In `src/scholar_mcp/_cache.py`:

Add TTL after `_CROSSREF_TTL`:
```python
_GOOGLE_BOOKS_TTL = 30 * 86400  # 30 days
```

Add table to `_SCHEMA`:
```sql
CREATE TABLE IF NOT EXISTS google_books (
    isbn      TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_google_books_cached ON google_books(cached_at);
```

Add cache methods after the CrossRef methods:
```python
    async def get_google_books(self, isbn: str) -> dict[str, Any] | None:
        """Return cached Google Books data by ISBN or None if missing/stale.

        Args:
            isbn: ISBN-13 string.

        Returns:
            Google Books volume dict or None.
        """
        db = _require_open(self._db)
        async with db.execute(
            "SELECT data, cached_at FROM google_books WHERE isbn = ?", (isbn,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _GOOGLE_BOOKS_TTL:
            return None
        return json.loads(row[0])

    async def set_google_books(self, isbn: str, data: dict[str, Any]) -> None:
        """Cache Google Books data by ISBN.

        Args:
            isbn: ISBN-13 string.
            data: Google Books volume dict.
        """
        db = _require_open(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO google_books (isbn, data, cached_at) VALUES (?, ?, ?)",
            (isbn, json.dumps(data), time.time()),
        )
        await db.commit()
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_google_books_client.py tests/test_google_books_client.py \
  src/scholar_mcp/config.py src/scholar_mcp/_protocols.py src/scholar_mcp/_cache.py
git commit -m "feat: add Google Books client, cache, and config (#61)"
```

---

## Task 8: GoogleBooksEnricher and get_book_excerpt Tool (#61 enricher + tool)

**Files:**
- Create: `src/scholar_mcp/_enricher_google_books.py`
- Test: `tests/test_enricher_google_books.py`
- Modify: `src/scholar_mcp/_server_deps.py` (add GoogleBooksClient, register enricher)
- Modify: `src/scholar_mcp/_tools_books.py` (add `get_book_excerpt` tool)
- Modify: `tests/conftest.py` (add GoogleBooksClient + enricher)

- [ ] **Step 1: Write failing tests for GoogleBooksEnricher**

```python
# tests/test_enricher_google_books.py
"""Tests for GoogleBooksEnricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from scholar_mcp._enricher_google_books import GoogleBooksEnricher
from scholar_mcp._enrichment import Enricher


def test_satisfies_enricher_protocol() -> None:
    e = GoogleBooksEnricher()
    assert isinstance(e, Enricher)
    assert e.name == "google_books"
    assert e.phase == 1
    assert e.tags == frozenset({"books"})


def test_can_enrich_true_when_isbn13() -> None:
    e = GoogleBooksEnricher()
    assert e.can_enrich({"isbn_13": "9780262035613"}) is True


def test_can_enrich_true_when_isbn10() -> None:
    e = GoogleBooksEnricher()
    assert e.can_enrich({"isbn_10": "0262035618"}) is True


def test_can_enrich_false_when_no_isbn() -> None:
    e = GoogleBooksEnricher()
    assert e.can_enrich({"title": "Some Book"}) is False


def test_can_enrich_false_when_already_enriched() -> None:
    e = GoogleBooksEnricher()
    record = {"isbn_13": "9780262035613", "google_books_url": "https://..."}
    assert e.can_enrich(record) is False


@pytest.mark.anyio
async def test_enrich_fills_google_books_url() -> None:
    e = GoogleBooksEnricher()
    record: dict[str, Any] = {"isbn_13": "9780262035613"}
    bundle = AsyncMock()
    bundle.cache.get_google_books.return_value = None
    bundle.google_books.search_by_isbn.return_value = {
        "id": "vol123",
        "volumeInfo": {
            "previewLink": "https://books.google.com/books?id=vol123",
        },
        "searchInfo": {"textSnippet": "A comprehensive intro..."},
    }
    await e.enrich(record, bundle)
    assert record["google_books_url"] == "https://books.google.com/books?id=vol123"
    assert record["snippet"] == "A comprehensive intro..."
    bundle.cache.set_google_books.assert_awaited_once()


@pytest.mark.anyio
async def test_enrich_uses_cache() -> None:
    e = GoogleBooksEnricher()
    record: dict[str, Any] = {"isbn_13": "9780262035613"}
    bundle = AsyncMock()
    bundle.cache.get_google_books.return_value = {
        "id": "vol123",
        "volumeInfo": {
            "previewLink": "https://books.google.com/books?id=vol123",
        },
    }
    await e.enrich(record, bundle)
    assert record["google_books_url"] == "https://books.google.com/books?id=vol123"
    bundle.google_books.search_by_isbn.assert_not_called()


@pytest.mark.anyio
async def test_enrich_handles_error_silently() -> None:
    e = GoogleBooksEnricher()
    record: dict[str, Any] = {"isbn_13": "9780262035613"}
    bundle = AsyncMock()
    bundle.cache.get_google_books.side_effect = RuntimeError("fail")
    await e.enrich(record, bundle)
    assert "google_books_url" not in record
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enricher_google_books.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GoogleBooksEnricher**

```python
# src/scholar_mcp/_enricher_google_books.py
"""Google Books enricher — populates preview URL and snippet on book records."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GoogleBooksEnricher:
    """Enricher that populates google_books_url and snippet from Google Books.

    Phase 1 (secondary). Tags: books. Needs ISBN, which may come from
    CrossRef (phase 0).
    """

    name: str = "google_books"
    phase: int = 1
    tags: frozenset[str] = frozenset({"books"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """True when record has an ISBN and no google_books_url yet."""
        if record.get("google_books_url"):
            return False
        return bool(record.get("isbn_13") or record.get("isbn_10"))

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill google_books_url and snippet from cache or API.

        Args:
            record: Book record dict (mutated in-place).
            bundle: ServiceBundle with google_books client and cache.
        """
        isbn = record.get("isbn_13") or record.get("isbn_10")
        if not isbn:
            return
        try:
            cached = await bundle.cache.get_google_books(isbn)
            gb_data = (
                cached
                if cached is not None
                else await bundle.google_books.search_by_isbn(isbn)
            )
            if gb_data is None:
                return
            if cached is None:
                await bundle.cache.set_google_books(isbn, gb_data)
            vol_info = gb_data.get("volumeInfo") or {}
            preview = vol_info.get("previewLink")
            if preview:
                record["google_books_url"] = preview
            snippet = (gb_data.get("searchInfo") or {}).get("textSnippet")
            if snippet:
                record["snippet"] = snippet
        except Exception:
            logger.debug(
                "google_books_enrich_failed isbn=%s", isbn, exc_info=True
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enricher_google_books.py -x -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Wire GoogleBooksClient into ServiceBundle**

In `src/scholar_mcp/_server_deps.py`:

Add imports:
```python
from ._google_books_client import GoogleBooksClient
from ._enricher_google_books import GoogleBooksEnricher
```

Add `_GOOGLE_BOOKS_BASE` constant:
```python
_GOOGLE_BOOKS_BASE = "https://www.googleapis.com/books/v1"
_GOOGLE_BOOKS_DELAY = 0.5
```

Add to `ServiceBundle`:
```python
    google_books: GoogleBooksClient
```

In `make_service_lifespan()`, after the crossref client setup:
```python
    google_books_http = httpx.AsyncClient(
        base_url=_GOOGLE_BOOKS_BASE, headers={"User-Agent": ua}, timeout=30.0
    )
    google_books = GoogleBooksClient(
        google_books_http, api_key=config.google_books_api_key
    )
```

Add `google_books=google_books` to `ServiceBundle(...)`.

Add `GoogleBooksEnricher()` to the `EnrichmentPipeline([...])` list.

In `finally`, add: `await google_books_http.aclose()`.

- [ ] **Step 6: Add `get_book_excerpt` tool to `_tools_books.py`**

Add the new tool inside `register_book_tools()`, after the existing tools:

```python
    @mcp.tool(
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_book_excerpt(
        isbn: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Get a book excerpt and preview info from Google Books.

        Returns the publisher description, text snippet, and a link to
        the Google Books preview page.

        Args:
            isbn: ISBN-10 or ISBN-13.

        Returns:
            JSON with excerpt, description, preview availability, and link.
        """
        volume = await bundle.google_books.search_by_isbn(isbn)
        if volume is None:
            return json.dumps({"error": "not_found", "isbn": isbn})

        vol_info = volume.get("volumeInfo") or {}
        access_info = volume.get("accessInfo") or {}
        search_info = volume.get("searchInfo") or {}
        viewability = access_info.get("viewability", "NO_PAGES")
        preview_available = viewability in ("PARTIAL", "ALL_PAGES")

        return json.dumps({
            "excerpt": search_info.get("textSnippet"),
            "description": vol_info.get("description"),
            "source": "google_books",
            "preview_available": preview_available,
            "preview_link": vol_info.get("previewLink"),
        })
```

- [ ] **Step 7: Update conftest.py**

Add imports and create GoogleBooksClient in the `bundle` fixture (same pattern as CrossRef). Add `google_books=google_books` to `ServiceBundle(...)` and `GoogleBooksEnricher()` to the pipeline. Add cleanup.

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 9: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_enricher_google_books.py tests/test_enricher_google_books.py \
  src/scholar_mcp/_server_deps.py src/scholar_mcp/_tools_books.py tests/conftest.py
git commit -m "feat: add GoogleBooksEnricher and get_book_excerpt tool (#61)"
```

---

## Task 9: BookRecord Fields and WorldCat Permalink (#66, partial #68)

**Files:**
- Modify: `src/scholar_mcp/_record_types.py:8-30` (add fields)
- Modify: `src/scholar_mcp/_openlibrary_client.py:298-375` (populate `worldcat_url` in `normalize_book`)
- Modify: `tests/test_record_types.py` (update test data)
- Modify: `tests/test_openlibrary_client.py` (assert `worldcat_url`)

- [ ] **Step 1: Add new fields to BookRecord**

In `src/scholar_mcp/_record_types.py`, add after `description` (line 29):
```python
    worldcat_url: str | None
    snippet: str | None
    cover_path: str | None
```

- [ ] **Step 2: Update test_record_types.py**

In `tests/test_record_types.py`, add the new fields to the valid data test to confirm they're accepted.

- [ ] **Step 3: Populate worldcat_url in normalize_book**

In `src/scholar_mcp/_openlibrary_client.py`, in `normalize_book()`:

For the `source == "search"` branch, after the ISBN extraction, add:
```python
        isbn_13 = ...  # existing extraction
        "worldcat_url": f"https://www.worldcat.org/isbn/{isbn_13}" if isbn_13 else None,
```

For the `source == "edition"` branch, same pattern:
```python
        "worldcat_url": f"https://www.worldcat.org/isbn/{isbn_13}" if isbn_13 else None,
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_record_types.py tests/test_openlibrary_client.py -x -v`
Expected: PASS (new fields accepted; worldcat_url populated)

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_record_types.py src/scholar_mcp/_openlibrary_client.py \
  tests/test_record_types.py tests/test_openlibrary_client.py
git commit -m "feat: add worldcat_url permalink and new BookRecord fields (#66)"
```

---

## Task 10: Cover Image Caching on get_book (#68)

**Files:**
- Modify: `src/scholar_mcp/_tools_books.py:146-185` (add params to `get_book`)
- Test: `tests/test_tools_books.py` (add cover download tests)

- [ ] **Step 1: Write failing test for cover download**

Add to `tests/test_tools_books.py`:

```python
@pytest.mark.anyio
async def test_get_book_download_cover(bundle, tmp_path, monkeypatch):
    """get_book with download_cover=True saves cover to disk."""
    # Mock the book resolution to return a record with cover_url and isbn
    isbn = "9780262035613"
    book_record = {
        "title": "Deep Learning",
        "isbn_13": isbn,
        "cover_url": f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",
    }
    # Patch cache to return the book
    bundle.cache.get_book_by_isbn = AsyncMock(return_value=book_record)
    bundle.config = ServerConfig(cache_dir=tmp_path, read_only=False)

    # Mock httpx download of cover image
    cover_bytes = b"\xff\xd8\xff\xe0fake-jpeg-data"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = cover_bytes
    mock_response.raise_for_status = MagicMock()

    with patch("scholar_mcp._tools_books.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        # Call get_book with download_cover=True
        # (exact invocation depends on tool registration pattern —
        #  test through the internal helper or via FastMCP test client)
```

The exact test wiring depends on how existing `test_tools_books.py` invokes tools. Follow the established pattern in that file.

- [ ] **Step 2: Add `download_cover` and `cover_size` params to `get_book`**

In `src/scholar_mcp/_tools_books.py`, modify the `get_book` function signature to add:
```python
    async def get_book(
        identifier: str,
        include_editions: bool = False,
        download_cover: bool = False,
        cover_size: str = "M",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
```

After the existing book resolution logic, before `return json.dumps(result)`, add:
```python
        if download_cover and result.get("cover_url") and result.get("isbn_13"):
            if bundle.config.read_only:
                result["cover_error"] = "read_only_mode"
            else:
                isbn = result["isbn_13"]
                size = cover_size.upper() if cover_size.upper() in ("S", "M", "L") else "M"
                covers_dir = bundle.config.cache_dir / "covers"
                covers_dir.mkdir(parents=True, exist_ok=True)
                local_path = covers_dir / f"{isbn}_{size}.jpg"
                if local_path.exists():
                    result["cover_path"] = str(local_path)
                else:
                    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as http:
                            resp = await http.get(url)
                            resp.raise_for_status()
                            local_path.write_bytes(resp.content)
                            result["cover_path"] = str(local_path)
                    except Exception:
                        logger.debug("cover_download_failed isbn=%s", isbn, exc_info=True)
```

Add `import httpx` to the top of the file if not already present.

- [ ] **Step 3: Update the docstring for `get_book`**

Add documentation for the new parameters in the docstring.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_tools_books.py -x -v`
Expected: All tests pass (new and existing).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_tools_books.py tests/test_tools_books.py
git commit -m "feat: add cover image caching to get_book (#68)"
```

---

## Task 11: BookChapterRecord and Chapter Parser (#64 core)

**Files:**
- Modify: `src/scholar_mcp/_record_types.py` (add `BookChapterRecord`)
- Create: `src/scholar_mcp/_chapter_parser.py`
- Test: `tests/test_chapter_parser.py`

- [ ] **Step 1: Write failing tests for the chapter parser**

```python
# tests/test_chapter_parser.py
"""Tests for chapter citation string parser."""

from __future__ import annotations

import pytest

from scholar_mcp._chapter_parser import ChapterHint, parse_chapter_hint


def test_chapter_number_pattern() -> None:
    hint = parse_chapter_hint("See Chapter 3 in Goodfellow et al., Deep Learning")
    assert hint.chapter_number == 3


def test_ch_abbreviation() -> None:
    hint = parse_chapter_hint("Ch. 12, Advanced Topics")
    assert hint.chapter_number == 12


def test_chap_abbreviation() -> None:
    hint = parse_chapter_hint("Chap. 5, Risk Management")
    assert hint.chapter_number == 5


def test_page_range_pp() -> None:
    hint = parse_chapter_hint("Goodfellow et al., 2016, pp. 45-67")
    assert hint.page_start == 45
    assert hint.page_end == 67


def test_single_page() -> None:
    hint = parse_chapter_hint("Smith, 2020, p. 123")
    assert hint.page_start == 123
    assert hint.page_end is None


def test_pages_keyword() -> None:
    hint = parse_chapter_hint("Jones, 2018, pages 100–150")
    assert hint.page_start == 100
    assert hint.page_end == 150


def test_in_book_title() -> None:
    hint = parse_chapter_hint("Smith, 'Neural Networks', In: Handbook of AI, 2020")
    assert hint.parent_title == "Handbook of AI"


def test_isbn_extraction() -> None:
    hint = parse_chapter_hint(
        "Deep Learning, MIT Press, 2016, ISBN 978-0-262-03561-3"
    )
    assert hint.isbn == "9780262035613"


def test_isbn10_extraction() -> None:
    hint = parse_chapter_hint("Some Book, ISBN 0-262-03561-8")
    assert hint.isbn is not None


def test_no_match_returns_empty_hint() -> None:
    hint = parse_chapter_hint("Smith et al., Nature, 2020, vol. 123")
    assert hint.chapter_number is None
    assert hint.page_start is None
    assert hint.page_end is None
    assert hint.parent_title is None
    assert hint.isbn is None


def test_has_chapter_info() -> None:
    empty = parse_chapter_hint("Nothing here")
    assert empty.has_chapter_info is False
    ch = parse_chapter_hint("Chapter 3 in Some Book")
    assert ch.has_chapter_info is True
    pg = parse_chapter_hint("pp. 45-67")
    assert pg.has_chapter_info is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_chapter_parser.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add BookChapterRecord to _record_types.py**

In `src/scholar_mcp/_record_types.py`, add after `BookRecord`:
```python
class BookChapterRecord(TypedDict, total=False):
    """Chapter-level metadata within a book.

    Used when citation strings reference specific chapters or page
    ranges. ``citation_source`` indicates whether data came from
    CrossRef (structured) or regex parsing (heuristic).
    """

    chapter_title: str
    chapter_number: int
    page_start: int
    page_end: int
    parent_book: BookRecord
    citation_source: str  # "crossref" | "parsed"
```

- [ ] **Step 4: Implement the chapter parser**

```python
# src/scholar_mcp/_chapter_parser.py
"""Citation string parser for chapter and page-range patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass

# ISBN-13: starts with 978 or 979, 13 digits
_ISBN13_RE = re.compile(r"\b(97[89][\-\s]?\d[\-\s]?\d{2}[\-\s]?\d{5}[\-\s]?\d)\b")
# ISBN-10: 10 digits (last may be X)
_ISBN10_RE = re.compile(r"\b(\d[\-\s]?\d{2}[\-\s]?\d{5}[\-\s]?[\dX])\b")

_CHAPTER_RE = re.compile(r"\b(?:Chapter|Ch\.|Chap\.)\s+(\d+)", re.IGNORECASE)
_PP_RANGE_RE = re.compile(
    r"\bpp?\.\s*(\d+)\s*[-\u2013\u2014]\s*(\d+)", re.IGNORECASE
)
_PP_SINGLE_RE = re.compile(r"\bp\.\s*(\d+)\b", re.IGNORECASE)
_PAGES_RE = re.compile(
    r"\bpages?\s+(\d+)\s*[-\u2013\u2014]\s*(\d+)", re.IGNORECASE
)
_IN_TITLE_RE = re.compile(r"\bIn:\s*(.+?)(?:,\s*\d{4}|$)", re.IGNORECASE)


@dataclass
class ChapterHint:
    """Parsed chapter/page information from a citation string.

    Attributes:
        chapter_number: Chapter number, if detected.
        page_start: Start page, if detected.
        page_end: End page, if detected.
        parent_title: Parent book title from ``In:`` pattern.
        isbn: Normalized ISBN (digits only), if detected.
    """

    chapter_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    parent_title: str | None = None
    isbn: str | None = None

    @property
    def has_chapter_info(self) -> bool:
        """True if any chapter-level info was extracted."""
        return (
            self.chapter_number is not None
            or self.page_start is not None
            or self.isbn is not None
        )


def _clean_isbn(raw: str) -> str:
    """Strip hyphens and spaces from an ISBN string.

    Args:
        raw: Raw ISBN with possible hyphens/spaces.

    Returns:
        Digits-only ISBN string.
    """
    return re.sub(r"[\-\s]", "", raw)


def parse_chapter_hint(citation: str) -> ChapterHint:
    """Extract chapter, page, title, and ISBN hints from a citation string.

    Args:
        citation: Raw citation text.

    Returns:
        ChapterHint with any detected fields populated.
    """
    hint = ChapterHint()

    # Chapter number
    m = _CHAPTER_RE.search(citation)
    if m:
        hint.chapter_number = int(m.group(1))

    # Page range (pp. X-Y or pages X-Y)
    m = _PP_RANGE_RE.search(citation)
    if m:
        hint.page_start = int(m.group(1))
        hint.page_end = int(m.group(2))
    else:
        m = _PAGES_RE.search(citation)
        if m:
            hint.page_start = int(m.group(1))
            hint.page_end = int(m.group(2))
        else:
            m = _PP_SINGLE_RE.search(citation)
            if m:
                hint.page_start = int(m.group(1))

    # In: title
    m = _IN_TITLE_RE.search(citation)
    if m:
        hint.parent_title = m.group(1).strip()

    # ISBN
    m = _ISBN13_RE.search(citation)
    if m:
        hint.isbn = _clean_isbn(m.group(1))
    else:
        m = _ISBN10_RE.search(citation)
        if m:
            hint.isbn = _clean_isbn(m.group(1))

    return hint
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_chapter_parser.py -x -v`
Expected: All 13 tests PASS

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_record_types.py src/scholar_mcp/_chapter_parser.py \
  tests/test_chapter_parser.py
git commit -m "feat: add BookChapterRecord type and chapter citation parser (#64)"
```

---

## Task 12: Chapter Integration into batch_resolve and Patent NPL (#64 integration)

**Files:**
- Modify: `src/scholar_mcp/_tools_utility.py:39-209` (chapter-aware batch_resolve)
- Modify: `src/scholar_mcp/_tools_patent.py:634-695` (chapter-aware NPL)
- Test: `tests/test_tools_utility.py` (add chapter resolution test)
- Test: `tests/test_tools_patent.py` (add chapter NPL test)

- [ ] **Step 1: Write failing test for chapter-aware batch_resolve**

Add to `tests/test_tools_utility.py` (follow existing test patterns in the file):

A test that passes a citation string containing chapter/page patterns to
`batch_resolve` and asserts that the result contains `chapter_info` when
the resolved paper has `book_metadata`. The exact test wiring depends on the
existing test patterns — read the file first and follow them.

Key assertion:
```python
# When citation = "Goodfellow et al., Deep Learning, Ch. 3, pp. 45-67, ISBN 978-0-262-03561-3"
# and the paper resolves with book_metadata
# then result should include:
assert result["chapter_info"]["chapter_number"] == 3
assert result["chapter_info"]["page_start"] == 45
assert result["chapter_info"]["page_end"] == 67
assert result["chapter_info"]["citation_source"] == "parsed"
```

- [ ] **Step 2: Write failing test for chapter-aware patent NPL**

Add to `tests/test_tools_patent.py` a similar test for NPL citation
resolution containing chapter patterns.

- [ ] **Step 3: Add chapter parsing to batch_resolve**

In `src/scholar_mcp/_tools_utility.py`:

Add import:
```python
from ._chapter_parser import parse_chapter_hint
```

After S2 resolution of each identifier, if the result has `book_metadata`
or `crossref_metadata` with `type: "book-chapter"`, parse the original
identifier string for chapter hints. Build a `chapter_info` dict:

```python
# After paper resolution, before appending to results:
if paper and (paper.get("book_metadata") or
              (paper.get("crossref_metadata") or {}).get("type") == "book-chapter"):
    cr = paper.get("crossref_metadata") or {}
    if cr.get("type") == "book-chapter" and cr.get("page"):
        # CrossRef is authoritative
        pages = cr["page"].split("-")
        chapter_info = {
            "page_start": int(pages[0]) if pages[0].isdigit() else None,
            "page_end": int(pages[1]) if len(pages) > 1 and pages[1].isdigit() else None,
            "citation_source": "crossref",
        }
        if cr.get("container-title"):
            titles = cr["container-title"]
            chapter_info["chapter_title"] = titles[0] if titles else None
        paper["chapter_info"] = chapter_info
    else:
        # Fallback to regex parsing
        hint = parse_chapter_hint(identifier)
        if hint.has_chapter_info:
            paper["chapter_info"] = {
                "chapter_number": hint.chapter_number,
                "page_start": hint.page_start,
                "page_end": hint.page_end,
                "citation_source": "parsed",
            }
```

- [ ] **Step 4: Add chapter parsing to patent NPL resolution**

In `src/scholar_mcp/_tools_patent.py`:

Add import:
```python
from ._chapter_parser import parse_chapter_hint
```

In `_fetch_citations()`, after NPL references are resolved (when building
`resolved_npl` entries), for each entry that resolved to a paper, check for
chapter hints:

```python
# After resolving an NPL reference to a paper:
hint = parse_chapter_hint(npl_ref["raw"])
if hint.has_chapter_info:
    entry["chapter_info"] = {
        "chapter_number": hint.chapter_number,
        "page_start": hint.page_start,
        "page_end": hint.page_end,
        "isbn": hint.isbn,
        "citation_source": "parsed",
    }
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_tools_utility.py tests/test_tools_patent.py -x -v`
Expected: All tests pass.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix .
uv run ruff format .
git add src/scholar_mcp/_tools_utility.py src/scholar_mcp/_tools_patent.py \
  tests/test_tools_utility.py tests/test_tools_patent.py
git commit -m "feat: add chapter-level resolution to batch_resolve and patent NPL (#64)"
```

---

## Task 13: Documentation Updates

**Files:**
- Modify: `README.md`
- Modify: `docs/tools/index.md` (if exists)
- Modify: `docs/guides/` (if relevant guides exist)

- [ ] **Step 1: Read current README and docs structure**

```bash
ls docs/
```

Identify which files need updates for:
- New enrichment pipeline (developer docs)
- New config var `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY`
- New `get_book_excerpt` tool
- New `download_cover` / `cover_size` params on `get_book`
- WorldCat permalink on book records
- Chapter info on batch_resolve and patent citations
- CrossRef enrichment metadata on papers

- [ ] **Step 2: Update README.md**

Add the new config env var to the configuration table. Add `get_book_excerpt`
to the tool list. Mention enrichment pipeline in architecture section if
present.

- [ ] **Step 3: Update docs/**

Update tool documentation for `get_book` (new params), `get_book_excerpt` (new
tool), `batch_resolve` (chapter_info output), patent tools (chapter_info in NPL
citations). Update config docs for new env var.

- [ ] **Step 4: Run lint**

```bash
uv run ruff check --fix .
uv run ruff format .
```

- [ ] **Step 5: Run full test suite one final time**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 6: Run type checker**

Run: `uv run mypy src/`
Expected: No errors.

- [ ] **Step 7: Commit docs and final cleanup**

```bash
git add README.md docs/
git commit -m "docs: update docs for v0.6.0 enrichment pipeline and new features"
```

---

## Summary

| Task | Issue | Commit message |
|------|-------|---------------|
| 1 | #62 | `feat: add Enricher protocol and EnrichmentPipeline` |
| 2 | #62 | `feat: extract OpenAlexEnricher from inline citation logic` |
| 3 | #62 | `feat: extract OpenLibraryEnricher from book_enrichment` |
| 4 | #62 | `refactor: wire EnrichmentPipeline into ServiceBundle, replace ad-hoc enrichment` |
| 5 | #67 | `feat: add CrossRef client and cache layer` |
| 6 | #67 | `feat: add CrossRefEnricher with DOI-based metadata lookup` |
| 7 | #61 | `feat: add Google Books client, cache, and config` |
| 8 | #61 | `feat: add GoogleBooksEnricher and get_book_excerpt tool` |
| 9 | #66 | `feat: add worldcat_url permalink and new BookRecord fields` |
| 10 | #68 | `feat: add cover image caching to get_book` |
| 11 | #64 | `feat: add BookChapterRecord type and chapter citation parser` |
| 12 | #64 | `feat: add chapter-level resolution to batch_resolve and patent NPL` |
| 13 | all | `docs: update docs for v0.6.0 enrichment pipeline and new features` |

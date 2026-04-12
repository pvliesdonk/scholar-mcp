"""Tests for Enricher protocol and EnrichmentPipeline."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scholar_mcp._enrichment import Enricher, EnrichmentPipeline


class StubEnricher:
    """Test enricher that marks records and tracks calls."""

    def __init__(
        self,
        name: str = "stub",
        phase: int = 0,
        tags: frozenset[str] = frozenset(),
        *,
        can: bool = True,
    ) -> None:
        self.name = name
        self.phase = phase
        self.tags = tags
        self._can = can
        self.calls: list[dict[str, Any]] = []

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return the configured predicate value."""
        return self._can

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Set a marker key on the record and log the call."""
        self.calls.append(record)
        record[f"enriched_by_{self.name}"] = True


class FailingEnricher:
    """Test enricher that always raises."""

    def __init__(
        self,
        name: str = "failing",
        phase: int = 0,
        tags: frozenset[str] = frozenset(),
    ) -> None:
        self.name = name
        self.phase = phase
        self.tags = tags

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Always eligible."""
        return True

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Always raise."""
        raise RuntimeError("boom")


def test_stub_satisfies_enricher_protocol() -> None:
    """StubEnricher must satisfy the runtime-checkable Enricher protocol."""
    stub = StubEnricher()
    assert isinstance(stub, Enricher)


@pytest.mark.anyio
async def test_pipeline_runs_single_enricher() -> None:
    """A single enricher should mutate the record."""
    enricher = StubEnricher(name="alpha")
    pipeline = EnrichmentPipeline([enricher])
    records = [{"title": "Test"}]
    await pipeline.enrich(records, bundle=None)
    assert records[0]["enriched_by_alpha"] is True
    assert len(enricher.calls) == 1


@pytest.mark.anyio
async def test_pipeline_skips_when_can_enrich_false() -> None:
    """Enricher should not be called when can_enrich returns False."""
    enricher = StubEnricher(name="skip", can=False)
    pipeline = EnrichmentPipeline([enricher])
    records = [{"title": "Test"}]
    await pipeline.enrich(records, bundle=None)
    assert "enriched_by_skip" not in records[0]
    assert len(enricher.calls) == 0


@pytest.mark.anyio
async def test_pipeline_filters_by_tags() -> None:
    """Only enrichers whose tags overlap the requested tags should run."""
    e1 = StubEnricher(name="a", tags=frozenset({"openalex"}))
    e2 = StubEnricher(name="b", tags=frozenset({"crossref"}))
    pipeline = EnrichmentPipeline([e1, e2])
    records = [{"title": "Test"}]
    await pipeline.enrich(records, bundle=None, tags={"openalex"})
    assert records[0].get("enriched_by_a") is True
    assert "enriched_by_b" not in records[0]


@pytest.mark.anyio
async def test_pipeline_respects_phase_order() -> None:
    """Phase 0 enrichers run before phase 1, regardless of registration order."""
    order: list[str] = []

    class OrderTracker:
        """Enricher that logs execution order."""

        def __init__(self, name: str, phase: int) -> None:
            self.name = name
            self.phase = phase
            self.tags: frozenset[str] = frozenset()

        def can_enrich(self, record: dict[str, Any]) -> bool:
            return True

        async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
            order.append(self.name)

    # Register phase 1 first, phase 0 second
    pipeline = EnrichmentPipeline(
        [
            OrderTracker("late", phase=1),
            OrderTracker("early", phase=0),
        ]
    )
    await pipeline.enrich([{"title": "Test"}], bundle=None)
    assert order == ["early", "late"]


@pytest.mark.anyio
async def test_pipeline_error_does_not_propagate() -> None:
    """A failing enricher must not prevent subsequent enrichers from running."""
    failing = FailingEnricher(name="bad")
    good = StubEnricher(name="good")
    pipeline = EnrichmentPipeline([failing, good])
    records = [{"title": "Test"}]
    await pipeline.enrich(records, bundle=None)
    assert records[0].get("enriched_by_good") is True


@pytest.mark.anyio
async def test_pipeline_multiple_records() -> None:
    """Enricher should run on every record in the batch."""
    enricher = StubEnricher(name="batch")
    pipeline = EnrichmentPipeline([enricher])
    records = [{"id": 1}, {"id": 2}, {"id": 3}]
    await pipeline.enrich(records, bundle=None)
    assert all(r.get("enriched_by_batch") is True for r in records)
    assert len(enricher.calls) == 3


@pytest.mark.anyio
async def test_pipeline_concurrency_bounded() -> None:
    """Concurrent enrichment calls should be bounded by the semaphore."""
    peak = 0
    current = 0
    lock = asyncio.Lock()

    class SlowEnricher:
        """Enricher that sleeps briefly to test concurrency bounds."""

        def __init__(self, name: str) -> None:
            self.name = name
            self.phase = 0
            self.tags: frozenset[str] = frozenset()

        def can_enrich(self, record: dict[str, Any]) -> bool:
            return True

        async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
            nonlocal peak, current
            async with lock:
                current += 1
                if current > peak:
                    peak = current
            await asyncio.sleep(0.01)
            async with lock:
                current -= 1

    enricher = SlowEnricher(name="slow")
    pipeline = EnrichmentPipeline([enricher])
    records = [{"id": i} for i in range(10)]
    await pipeline.enrich(records, bundle=None, concurrency=3)
    assert peak <= 3

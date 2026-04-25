"""Enricher protocol and EnrichmentPipeline for batch record enrichment."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Sequence  # noqa: TC003  # used in TypeAlias (runtime)
from typing import Any, Protocol, TypeAlias, cast, runtime_checkable

from ._record_types import BookChapterRecord, BookRecord, PaperRecord, StandardRecord

logger = logging.getLogger(__name__)

#: Records the pipeline can enrich. All variants are plain dicts at
#: runtime; enrichers mutate the underlying dict in place.
EnrichableRecord: TypeAlias = (
    dict[str, Any] | PaperRecord | BookRecord | BookChapterRecord | StandardRecord
)


@runtime_checkable
class Enricher(Protocol):
    """Protocol for record enrichers.

    Enrichers are grouped by ``phase`` (lower runs first) and filtered
    by ``tags``.  Each enricher decides per-record whether it applies
    via :meth:`can_enrich`, then mutates the record in :meth:`enrich`.

    Attributes:
        name: Human-readable identifier for logging.
        phase: Execution order group (0 = first).
        tags: Labels used to select enrichers at call time.
    """

    name: str
    phase: int
    tags: frozenset[str]

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return whether this enricher should run on *record*.

        Args:
            record: The record dict to inspect.

        Returns:
            ``True`` if this enricher is applicable.
        """
        ...

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Mutate *record* in place with enriched data.

        Args:
            record: The record dict to enrich.
            bundle: Service bundle providing API clients, cache, etc.
        """
        ...


class EnrichmentPipeline:
    """Runs a sequence of :class:`Enricher` instances over record batches.

    Enrichers are grouped by phase and executed in phase order.
    Within a phase, all (enricher, record) pairs run concurrently,
    bounded by a semaphore.

    Args:
        enrichers: List of enricher instances to register.
    """

    def __init__(self, enrichers: list[Enricher]) -> None:
        self._phases: dict[int, list[Enricher]] = defaultdict(list)
        for e in enrichers:
            self._phases[e.phase].append(e)

    async def enrich(
        self,
        records: Sequence[EnrichableRecord],
        bundle: Any,
        *,
        tags: frozenset[str] | None = None,
        concurrency: int = 10,
    ) -> None:
        """Run all registered enrichers over *records*.

        Accepts a covariant :class:`Sequence` of records so callers can
        pass a ``list[BookRecord]`` (or any other supported TypedDict
        record) without casts or ``# type: ignore``.  At runtime every
        supported record type is a plain ``dict``, so the ``cast`` to
        ``dict[str, Any]`` below is safe and lets enrichers keep their
        simpler parameter type.

        Args:
            records: Sequence of record dicts to enrich in place.
            bundle: Service bundle for API clients, cache, etc.
            tags: If provided, only enrichers whose tags overlap run.
            concurrency: Maximum concurrent enrichment calls per phase.
        """
        sem = asyncio.Semaphore(concurrency)
        for phase_key in sorted(self._phases):
            enrichers = self._phases[phase_key]
            tasks: list[asyncio.Task[None]] = []
            for enricher in enrichers:
                if tags is not None and not enricher.tags & tags:
                    continue
                for record in records:
                    record_dict = cast("dict[str, Any]", record)
                    if not enricher.can_enrich(record_dict):
                        continue
                    task = asyncio.create_task(
                        self._run_one(sem, enricher, record_dict, bundle)
                    )
                    tasks.append(task)
            if tasks:
                await asyncio.gather(*tasks)

    @staticmethod
    async def _run_one(
        sem: asyncio.Semaphore,
        enricher: Enricher,
        record: dict[str, Any],
        bundle: Any,
    ) -> None:
        """Run a single enricher on a single record, guarded by *sem*.

        Exceptions are logged at DEBUG and never propagated.

        Args:
            sem: Semaphore bounding concurrency.
            enricher: The enricher to execute.
            record: The record to enrich.
            bundle: Service bundle.
        """
        async with sem:
            try:
                await enricher.enrich(record, bundle)
            except Exception:
                logger.debug(
                    "enricher_failed enricher=%s",
                    enricher.name,
                    exc_info=True,
                )

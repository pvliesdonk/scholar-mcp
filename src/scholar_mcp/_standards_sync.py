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
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
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

    async def sync(self, cache: CacheProtocol, *, force: bool = False) -> SyncReport:
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
        except Exception as exc:
            logger.error(
                "sync_loader_crashed body=%s err=%s",
                loader.body,
                exc,
                exc_info=True,
            )
            report = SyncReport(
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
        # Persist a row per body for get_sync_status — on both the
        # success and crash paths, so operators see the failure via
        # get_sync_status instead of "last successful run" or silence.
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

    return list(await asyncio.gather(*(_run_one(loader) for loader in loaders)))


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

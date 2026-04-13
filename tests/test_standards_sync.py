"""Tests for the standards sync dispatcher."""

from __future__ import annotations

from typing import Any

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

        async def sync(self, cache: Any, *, force: bool = False) -> SyncReport:
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

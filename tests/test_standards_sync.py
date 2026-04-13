"""Tests for the standards sync dispatcher."""

from __future__ import annotations

import dataclasses
from typing import Any

from scholar_mcp._cache import ScholarCache
from scholar_mcp._standards_sync import Loader, SyncReport, format_reports, run_sync


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


# ---------------------------------------------------------------------------
# Helpers for dispatcher tests
# ---------------------------------------------------------------------------


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
    def __init__(
        self,
        body: str,
        report: SyncReport | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.body = body
        self._report = report or _report(body, added=1, upstream_ref="ref-" + body)
        self._raises = raises
        self.calls = 0

    async def sync(self, cache: Any, *, force: bool = False) -> SyncReport:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return dataclasses.replace(self._report)


# ---------------------------------------------------------------------------
# Dispatcher tests — run_sync
# ---------------------------------------------------------------------------


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


async def test_run_sync_persists_row_for_crashed_loader(cache: ScholarCache) -> None:
    """A loader crash must still write a standards_sync_runs row.

    Otherwise get_sync_status shows nothing (first run) or the previous
    successful run (repeat run) — hiding the failure from operators.
    """
    bad = _FakeLoader("IEC", raises=RuntimeError("upstream is down"))
    await run_sync([bad], cache)
    row = await cache.get_sync_run("IEC")
    assert row is not None
    assert row["body"] == "IEC"
    assert row["upstream_ref"] is None
    assert row["added"] == 0
    assert row["updated"] == 0
    assert row["unchanged"] == 0
    assert row["withdrawn"] == 0
    assert len(row["errors"]) == 1
    assert "RuntimeError" in row["errors"][0]
    assert "upstream is down" in row["errors"][0]


async def test_run_sync_force_propagates(cache: ScholarCache) -> None:
    class _ForceSensitive:
        body = "FS"

        def __init__(self) -> None:
            self.force_seen: bool | None = None

        async def sync(self, cache: Any, *, force: bool = False) -> SyncReport:
            self.force_seen = force
            return _report("FS")

    fs = _ForceSensitive()
    await run_sync([fs], cache, force=True)
    assert fs.force_seen is True


# ---------------------------------------------------------------------------
# Dispatcher tests — format_reports
# ---------------------------------------------------------------------------


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
    assert "total added=15 updated=2 unchanged=500 withdrawn=0 errors=1" in out

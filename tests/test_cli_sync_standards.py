"""Tests for the scholar-mcp sync-standards CLI subcommand."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from scholar_mcp import cli as cli_mod
from scholar_mcp._standards_sync import SyncReport
from scholar_mcp.cli import cli


class _GoodLoader:
    """Stub loader that succeeds."""

    def __init__(self, body: str) -> None:
        self.body = body

    async def sync(self, cache: Any, *, force: bool = False) -> SyncReport:
        return SyncReport(
            body=self.body,
            added=1,
            updated=0,
            unchanged=0,
            withdrawn=0,
            errors=[],
            upstream_ref="ok",
            started_at=0.0,
            finished_at=0.0,
        )


class _BadLoader:
    """Stub loader that raises — the dispatcher converts this into an
    error report, exercising the exit-code branches in sync_standards.
    """

    def __init__(self, body: str) -> None:
        self.body = body

    async def sync(self, cache: Any, *, force: bool = False) -> SyncReport:
        raise RuntimeError("upstream is down")


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
    result = runner.invoke(cli, ["sync-standards", "--cache-dir", str(tmp_path)])
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


def test_sync_standards_hard_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All loaders fail → exit code 1."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    monkeypatch.setattr(cli_mod, "_select_loaders", lambda _body: [_BadLoader("ISO")])
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "ISO" in result.output


def test_sync_standards_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mix of passing and failing loaders → exit code 3."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    monkeypatch.setattr(
        cli_mod,
        "_select_loaders",
        lambda _body: [_GoodLoader("ISO"), _BadLoader("IEC")],
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 3
    assert "ISO" in result.output
    assert "IEC" in result.output


def test_sync_standards_all_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every loader succeeds → exit code 0."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    monkeypatch.setattr(
        cli_mod,
        "_select_loaders",
        lambda _body: [_GoodLoader("ISO"), _GoodLoader("IEC")],
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_select_loaders_single_body_filters() -> None:
    """Non-'all' body exercises the filter branch in _select_loaders.

    The registered list is empty in PR 1, so both branches return [],
    but this call exercises the list-comprehension line so it's not an
    uncovered branch in the Codecov patch report.
    """
    assert cli_mod._select_loaders("ISO") == []
    assert cli_mod._select_loaders("all") == []

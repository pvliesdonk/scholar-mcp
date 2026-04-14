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


def test_sync_standards_no_loaders_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero loaders registered → exits 0 with a clear message."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    monkeypatch.setattr(cli_mod, "_select_loaders", lambda _body, **_kw: [])
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

    monkeypatch.setattr(
        cli_mod, "_select_loaders", lambda _body, **_kw: [_BadLoader("ISO")]
    )
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
        lambda _body, **_kw: [_GoodLoader("ISO"), _BadLoader("IEC")],
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
        lambda _body, **_kw: [_GoodLoader("ISO"), _GoodLoader("IEC")],
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_select_loaders_single_body_filters() -> None:
    """Non-'all' body exercises the filter branch in _select_loaders.

    With ISO/IEC loaders registered, "ISO" returns exactly one loader
    and "all" returns two (ISO + IEC). "XYZ" returns empty.
    """
    import httpx

    from scholar_mcp._sync_relaton import RelatonLoader

    http = httpx.AsyncClient()
    try:
        iso_loaders = cli_mod._select_loaders("ISO", http=http, token=None)
        assert len(iso_loaders) == 1
        assert isinstance(iso_loaders[0], RelatonLoader)
        assert iso_loaders[0].body == "ISO"

        all_loaders = cli_mod._select_loaders("all", http=http, token=None)
        assert len(all_loaders) == 2
        bodies = {loader.body for loader in all_loaders}
        assert bodies == {"ISO", "IEC"}

        xyz_loaders = cli_mod._select_loaders("XYZ", http=http, token=None)
        assert xyz_loaders == []
    finally:
        asyncio.run(http.aclose())


def test_sync_standards_iso_real_loader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`sync-standards --body ISO` runs the real RelatonLoader end-to-end."""
    import gzip
    import io
    import tarfile

    import httpx
    import respx

    fixtures = Path(__file__).parent / "fixtures" / "standards" / "relaton_iso_sample"

    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for yaml_path in sorted(fixtures.glob("*.yaml")):
            data = yaml_path.read_bytes()
            info = tarfile.TarInfo(name=f"relaton-data-iso-main/data/{yaml_path.name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    tarball = buf.getvalue()

    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))

    runner = CliRunner()
    with respx.mock(assert_all_called=False) as router:
        router.get(
            "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
        ).mock(return_value=httpx.Response(200, json={"sha": "cli-sha"}))
        router.get(
            "https://api.github.com/repos/relaton/relaton-data-iso/tarball/cli-sha"
        ).mock(return_value=httpx.Response(200, content=tarball))

        result = runner.invoke(cli, ["sync-standards", "--body", "ISO"])

    assert result.exit_code == 0, result.output
    assert "ISO added=5" in result.output

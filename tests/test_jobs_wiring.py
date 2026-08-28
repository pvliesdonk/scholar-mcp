"""Guards for the pvl-core jobs wiring in `register_tools` / `make_server`.

`SCHOLAR_MCP_JOBS_*` is documented automatically -- the config-surface
generator reads `JobsConfig` from pvl-core whether or not anything wires it.
Documentation without wiring is how a feature ships inert, so these tests
assert the wiring itself: that a `Jobs` reaches the long-running tools, that
the single polling tool is registered, and -- the part a construction-only
check would miss -- that the config it is built from is the *environment's*
rather than a default-constructed stand-in.

The soft deadline is the observable that proves it. Nothing but an
env-derived `JobsConfig` shortens it, so a `register_tools` that stopped
reading the environment leaves the 25s default here and the promotion
assertion fails.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import (
    JobNotFoundError,
    Jobs,
    JobsConfig,
    ServerConfig,
    build_jobs,
)
from fastmcp_pvl_core._errors import ConfigurationError

from scholar_mcp import server as server_module
from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._server_tools import register_tools
from scholar_mcp._tools_pdf import register_pdf_tools
from scholar_mcp.config import ProjectConfig
from scholar_mcp.server import make_server


def _slow_docling_bundle(bundle: ServiceBundle) -> ServiceBundle:
    """Attach a docling client whose conversion outlives any short deadline.

    Args:
        bundle: The bundle to attach to.

    Returns:
        The same bundle, with a deliberately slow `docling`.
    """
    docling = DoclingClient(
        http_client=httpx.AsyncClient(base_url="http://docling:5001"),
        vlm_api_url=None,
        vlm_api_key=None,
        vlm_model="gpt-4o",
    )

    async def slow_convert(*args: object, **kwargs: object) -> str:
        await asyncio.sleep(0.2)
        return "# Slow"

    docling.convert = slow_convert  # type: ignore[method-assign]
    bundle.docling = docling
    return bundle


def _app(bundle: ServiceBundle) -> FastMCP:
    """Build a server whose tools are wired from the ambient environment.

    Args:
        bundle: Service bundle yielded from the app's lifespan.

    Returns:
        A :class:`FastMCP` with every domain tool registered.
    """

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_tools(app)
    return app


async def test_register_tools_registers_the_single_polling_tool(
    bundle: ServiceBundle,
) -> None:
    """`get_job_result` is registered exactly once, under pvl-core's name.

    One polling contract per server is the point of the migration: a handle
    minted by any long-running tool must resolve through this one tool.
    """
    async with Client(_app(bundle)) as client:
        names = [t.name for t in await client.list_tools()]
    assert names.count("get_job_result") == 1


async def test_soft_deadline_from_the_environment_reaches_jobs(
    bundle: ServiceBundle, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An env-set soft deadline actually governs promotion.

    This is the whole wiring assertion. With the 25s default the conversion
    below would answer inline; it only returns a handle because
    `register_tools` read `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` and passed the
    result through to `build_jobs`.
    """
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S", "0.05")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")

    async with Client(_app(_slow_docling_bundle(bundle))) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    handle = json.loads(result.content[0].text)
    assert handle["status"] == "working"
    assert handle["poll_with"] == "get_job_result"


async def test_default_deadline_answers_inline(
    bundle: ServiceBundle, tmp_path: Path
) -> None:
    """The counterpart: with the default deadline the same call is inline.

    Without this, the test above would pass just as well against a wiring
    that promoted everything unconditionally.
    """
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")

    async with Client(_app(_slow_docling_bundle(bundle))) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert "job_id" not in data
    assert "# Slow" in data["markdown"]


def test_malformed_jobs_var_fails_at_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in a `JOBS_*` var raises rather than silently taking a default.

    `JobsConfig.from_env` reads strictly. Because the `Jobs` object is built
    inside `register_tools`, that strictness surfaces at tool registration
    rather than at config load -- worth pinning so the failure point does not
    move silently.
    """
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S", "not-a-number")
    with pytest.raises(ConfigurationError, match="JOBS_SOFT_DEADLINE_S"):
        register_tools(FastMCP("test"))


def test_injected_jobs_bypasses_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit `jobs=` wins, so a bad env var is never read.

    This is the seam the tests rely on; if it regressed to reading the
    environment anyway, every test that shrinks the deadline would silently
    stop shrinking it.
    """
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S", "not-a-number")
    jobs = build_jobs(ServerConfig(kv_store_url="memory://"), JobsConfig())
    register_tools(FastMCP("test"), jobs=jobs)


async def test_make_server_exposes_the_polling_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production entry point wires jobs, not just `register_tools`."""
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path / "cache"))
    async with Client(make_server()) as client:
        names = [t.name for t in await client.list_tools()]
    assert "get_job_result" in names


async def test_job_records_are_scoped_to_the_caller(
    bundle: ServiceBundle, tmp_path: Path
) -> None:
    """A job id minted on one `Jobs` is unknown to another.

    Records are subject-scoped and per-store, so an id cannot be probed
    across servers. The bespoke queue this is replacing has no such scoping:
    `list_tasks` still returns every active task to any caller.
    """
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    short = JobsConfig(soft_deadline_s=0.05, result_ttl_s=60.0)
    mine = build_jobs(ServerConfig(kv_store_url="memory://"), short)
    theirs = build_jobs(ServerConfig(kv_store_url="memory://"), short)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": _slow_docling_bundle(bundle)}

    minting = FastMCP("minting", lifespan=lifespan)
    register_pdf_tools(minting, mine)

    async with Client(minting) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    job_id = json.loads(result.content[0].text)["job_id"]

    with pytest.raises(JobNotFoundError):
        await theirs.poll(job_id)


def test_explicit_config_reaches_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `ProjectConfig` handed to `make_server` governs jobs, not just Docket.

    `make_server` already passes its config to `configure_task_backend`. If it
    did not pass the same config through to `build_jobs`, one config object
    would configure two stateful subsystems from two different sources -- the
    exact drift #264 exists to remove. Asserting on the arguments rather than
    on promotion behaviour keeps the failure message pointed at the wiring.
    """
    captured: dict[str, object] = {}
    real_build_jobs = server_module.build_jobs

    def spy(server_config: ServerConfig, jobs_config: JobsConfig) -> Jobs:
        captured["server"] = server_config
        captured["jobs"] = jobs_config
        return real_build_jobs(server_config, jobs_config)

    monkeypatch.setattr(server_module, "build_jobs", spy)
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S", "99.0")

    config = ProjectConfig(
        server=ServerConfig(kv_store_url="memory://"),
        jobs=JobsConfig(soft_deadline_s=0.05, result_ttl_s=60.0),
        cache_dir=tmp_path / "cache",
    )
    make_server(config=config)

    assert captured, "make_server never reached build_jobs"
    # The env var above is deliberately different: reading it instead of the
    # passed config is precisely the bug this guards.
    assert captured["jobs"] is config.jobs
    assert captured["server"] is config.server


async def test_job_backed_tools_advertise_the_polling_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every tool that can return a handle says so in its advertised description.

    This is the surface the calling model actually reads. FastMCP publishes a
    docstring's summary and body but strips its `Args:` and `Returns:`
    sections, so guidance placed under `Returns:` never reaches the client --
    which is exactly how three patent tools came to advertise the old,
    removed task-queue contract while their `Returns:` text was updated.

    Asserting on the description as the client receives it, rather than on the
    docstring source, is what makes that failure visible.
    """
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "k")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "s")

    job_backed = {
        "fetch_paper_pdf",
        "convert_pdf_to_markdown",
        "fetch_and_convert",
        "fetch_pdf_by_url",
        "fetch_patent_pdf",
        "search_patents",
        "get_patent",
        "get_citing_patents",
    }

    async with Client(make_server()) as client:
        described = {t.name: (t.description or "") for t in await client.list_tools()}

    missing = sorted(job_backed - described.keys())
    assert not missing, f"expected these tools to be registered: {missing}"

    silent = sorted(
        name
        for name in job_backed
        if "get_job_result" not in described[name]
        and "job handle" not in described[name]
    )
    assert not silent, (
        "these tools can hand back a job handle but never say so in the "
        f"description the client sees: {silent}"
    )

    stale = sorted(name for name in job_backed if "get_task_result" in described[name])
    assert not stale, (
        "these tools point the caller at the legacy queue poller, which does "
        f"not know their job ids: {stale}"
    )

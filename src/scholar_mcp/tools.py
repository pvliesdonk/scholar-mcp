"""MCP tool registrations — dispatches to category modules."""

from __future__ import annotations

import weakref

from fastmcp import FastMCP
from fastmcp_pvl_core import Jobs, JobsConfig, build_jobs, register_job_tools

from ._server_deps import config_for

_JOBS_NOTE = (
    "Scholar MCP promotes slow work to a background job. PDF download and "
    "docling conversion usually take 1-5 minutes, a busy EPO traffic light "
    "is waited out, citation formatting enriches one paper after another, and "
    "graph traversal makes one rate-limited request per node. "
    "Semantic Scholar throttling defers the same work immediately and "
    "adds a reason to the handle. "
    "Those calls commonly answer with a job_id rather than a result; a cache "
    "hit answers inline, with no job."
)

# The one Jobs each server's tools share, for registrations that happen after
# register_tools (create_upload_link is wired in server.py's DOMAIN-WIRING,
# once the transport is known). Keyed weakly so a discarded test server
# releases its Jobs.
_SERVER_JOBS: weakref.WeakKeyDictionary[FastMCP, tuple[Jobs, JobsConfig]] = (
    weakref.WeakKeyDictionary()
)


def jobs_for(mcp: FastMCP) -> tuple[Jobs, JobsConfig]:
    """Return the ``Jobs`` and settings :func:`register_tools` built for *mcp*.

    Args:
        mcp: A server :func:`register_tools` has run on.

    Returns:
        The server's shared ``(jobs, jobs_config)``.

    Raises:
        RuntimeError: If :func:`register_tools` has not run on *mcp*.
    """
    try:
        return _SERVER_JOBS[mcp]
    except KeyError:
        msg = "register_tools has not run on this server; no Jobs to share"
        raise RuntimeError(msg) from None


def register_tools(
    mcp: FastMCP,
    *,
    transport: str = "stdio",
    jobs: Jobs | None = None,
    jobs_config: JobsConfig | None = None,
) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The FastMCP instance.
        transport: Active transport (unused currently, kept for compatibility).
        jobs: Shared background-job mechanics.  Built from the server's
            bound configuration when omitted, which is the production path;
            tests inject their own to shrink ``soft_deadline_s`` instead of
            sleeping for real.
            One ``Jobs`` per server is deliberate — every handle, whichever
            tool minted it, resolves through the single ``get_job_result``
            registered below.
        jobs_config: Settings used to build an injected ``jobs`` instance.
            Defaults to standard values when ``jobs`` is injected.
    """
    if jobs is None:
        # Both halves come from the one ProjectConfig make_server resolved and
        # bound (bind_config): `server` selects the KV backend the job records
        # live in, `jobs` carries the deadline, TTL and per-subject cap.
        config = config_for(mcp)
        jobs_config = jobs_config or config.jobs
        jobs = build_jobs(config.server, jobs_config)
    else:
        # Tests and embedders can inject Jobs without reading operator env.
        jobs_config = jobs_config or JobsConfig()
    _SERVER_JOBS[mcp] = (jobs, jobs_config)

    # Category modules are imported here to avoid circular imports.
    # Each module registers its tools onto `mcp` and accesses the
    # Service via Depends(get_service).
    from ._tools_search import register_search_tools

    register_search_tools(mcp, jobs, jobs_config)

    from ._tools_graph import register_graph_tools

    register_graph_tools(mcp, jobs, jobs_config)

    from ._tools_recommendations import register_recommendation_tools

    register_recommendation_tools(mcp, jobs, jobs_config)

    from ._tools_utility import register_utility_tools

    register_utility_tools(mcp, jobs, jobs_config)

    from ._tools_pdf import register_pdf_tools

    register_pdf_tools(mcp, jobs, jobs_config)

    from ._tools_citation import register_citation_tools

    register_citation_tools(mcp, jobs, jobs_config)

    from ._tools_patent import register_patent_tools

    register_patent_tools(mcp, jobs, jobs_config)

    from ._tools_books import register_book_tools

    register_book_tools(mcp, jobs)

    from ._tools_standards import register_standards_tools

    register_standards_tools(mcp, jobs)

    register_job_tools(mcp, jobs, note=_JOBS_NOTE)

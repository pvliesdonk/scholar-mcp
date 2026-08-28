"""MCP tool registrations — dispatches to category modules."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp_pvl_core import Jobs, build_jobs, register_job_tools

from .config import ProjectConfig

_JOBS_NOTE = (
    "Scholar MCP promotes slow work to a background job. PDF download and "
    "docling conversion usually take 1-5 minutes, a busy EPO traffic light "
    "is waited out, and citation formatting enriches each paper in turn. "
    "Those calls commonly answer with a job_id rather than a result; a cache "
    "hit answers inline, with no job. Tools that answer with task_id instead "
    "are polled with get_task_result, not this tool -- the response always "
    "names which one to use."
)


def register_tools(
    mcp: FastMCP,
    *,
    transport: str = "stdio",
    jobs: Jobs | None = None,
) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The FastMCP instance.
        transport: Active transport (unused currently, kept for compatibility).
        jobs: Shared background-job mechanics.  Built from the environment
            when omitted, which is the production path; tests inject their
            own to shrink ``soft_deadline_s`` instead of sleeping for real.
            One ``Jobs`` per server is deliberate — every handle, whichever
            tool minted it, resolves through the single ``get_job_result``
            registered below.
    """
    if jobs is None:
        # Both halves come from one ProjectConfig load: `server` selects the
        # KV backend the job records live in, `jobs` carries the deadline,
        # TTL and per-subject cap.
        config = ProjectConfig.from_env()
        jobs = build_jobs(config.server, config.jobs)

    # Category modules are imported here to avoid circular imports.
    # Each module registers its tools onto `mcp` and accesses the
    # ServiceBundle via Depends(get_bundle).
    from ._tools_search import register_search_tools

    register_search_tools(mcp, jobs)

    from ._tools_graph import register_graph_tools

    register_graph_tools(mcp)

    from ._tools_recommendations import register_recommendation_tools

    register_recommendation_tools(mcp, jobs)

    from ._tools_utility import register_utility_tools

    register_utility_tools(mcp)

    from ._tools_pdf import register_pdf_tools

    register_pdf_tools(mcp, jobs)

    from ._tools_tasks import register_task_tools

    register_task_tools(mcp)

    from ._tools_citation import register_citation_tools

    register_citation_tools(mcp, jobs)

    from ._tools_patent import register_patent_tools

    register_patent_tools(mcp, jobs)

    from ._tools_books import register_book_tools

    register_book_tools(mcp, jobs)

    from ._tools_standards import register_standards_tools

    register_standards_tools(mcp)

    register_job_tools(mcp, jobs, note=_JOBS_NOTE)

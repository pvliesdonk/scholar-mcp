"""MCP tool registrations — dispatches to category modules."""

from __future__ import annotations

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, *, transport: str = "stdio") -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The FastMCP instance.
        transport: Active transport (unused currently, kept for compatibility).
    """
    # Category modules are imported here to avoid circular imports.
    # Each module registers its tools onto `mcp` and accesses the
    # ServiceBundle via Depends(get_bundle).
    from ._tools_search import register_search_tools

    register_search_tools(mcp)

    from ._tools_graph import register_graph_tools

    register_graph_tools(mcp)

    from ._tools_recommendations import register_recommendation_tools

    register_recommendation_tools(mcp)

    from ._tools_utility import register_utility_tools

    register_utility_tools(mcp)

    from ._tools_pdf import register_pdf_tools

    register_pdf_tools(mcp)

    from ._tools_tasks import register_task_tools

    register_task_tools(mcp)

    from ._tools_citation import register_citation_tools

    register_citation_tools(mcp)

    from ._tools_patent import register_patent_tools

    register_patent_tools(mcp)

    from ._tools_books import register_book_tools

    register_book_tools(mcp)

    from ._tools_standards import register_standards_tools

    register_standards_tools(mcp)

"""Shared dependency injection and lifespan for the MCP server.

Provides :func:`get_service` and :func:`make_service_lifespan` which are
imported by the tool, resource, and prompt registration modules.

TODO: Replace ``MyService`` / the placeholder dict with your actual business
object (database connection, API client, in-memory index, etc.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.lifespan import lifespan

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastmcp_server_template.config import ServerConfig

logger = logging.getLogger(__name__)


def make_service_lifespan(config: ServerConfig) -> Any:
    """Create a lifespan function that closes over a pre-loaded config.

    Args:
        config: A fully-loaded :class:`~fastmcp_server_template.config.ServerConfig`
            instance produced by a single :func:`load_config` call in
            :func:`~fastmcp_server_template.mcp_server.create_server`.

    Returns:
        A FastMCP lifespan coroutine that initialises the service object and
        yields ``{"service": service, "config": config}`` to the lifespan
        context.
    """

    @lifespan
    async def _service_lifespan(
        server: FastMCP,  # noqa: ARG001
    ) -> AsyncIterator[dict[str, Any]]:
        """Initialise the service at server startup, tear down on shutdown."""
        logger.info("Service starting up (read_only=%s)", config.read_only)

        # TODO: Replace this placeholder with your real service initialisation.
        # Examples:
        #   service = MyDatabase(config.data_dir)
        #   await service.connect()
        #   service = MyApiClient(api_key=config.api_key)
        service: dict[str, Any] = {"ready": True}

        try:
            yield {"service": service, "config": config}
        finally:
            # TODO: Add teardown logic here.
            # Examples:
            #   await service.close()
            #   service.flush()
            logger.info("Service shut down")

    return _service_lifespan


def get_service(ctx: Context = CurrentContext()) -> Any:
    """Resolve the service object from lifespan context.

    Used as a ``Depends()`` default in tool/resource/prompt signatures.

    Raises:
        RuntimeError: If the server lifespan has not run.
    """
    service: Any = ctx.lifespan_context.get("service")
    if service is None:
        msg = "Service not initialised — server lifespan has not run"
        raise RuntimeError(msg)
    return service

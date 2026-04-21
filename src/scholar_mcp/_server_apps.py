"""MCP Apps scaffolding for Scholar MCP.

Ships as an inert placeholder: ``register_apps`` is a no-op unless the
``SCHOLAR_MCP_APP_DOMAIN`` or ``SCHOLAR_MCP_BASE_URL`` env
vars are set.  Adopt MCP Apps by copying MV's ``_server_apps.py`` as a
reference once you need a real UI resource.
"""

from __future__ import annotations

import logging
import os

from fastmcp import FastMCP

from scholar_mcp.config import _ENV_PREFIX

logger = logging.getLogger(__name__)


def register_apps(_mcp: FastMCP) -> None:
    """Register MCP Apps resources on *mcp*.

    This scaffold intentionally registers nothing; check the env var
    and log that the scaffold is inactive.  Real projects replace the
    body with resource + tool registrations following MV's pattern.
    """
    app_domain = (
        os.environ.get(f"{_ENV_PREFIX}_APP_DOMAIN", "").strip()
        or os.environ.get(f"{_ENV_PREFIX}_BASE_URL", "").strip()
    )
    if app_domain:
        logger.info(
            "MCP Apps scaffold present but not wired — app_domain=%s", app_domain
        )
    else:
        logger.debug("MCP Apps scaffold inactive (no app_domain configured)")

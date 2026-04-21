"""Project configuration for scholar-mcp.

Composes ``fastmcp_pvl_core.ServerConfig`` for transport/auth/event-store
fields; adds Scholar domain fields below.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from fastmcp_pvl_core import ServerConfig, env, parse_bool

logger = logging.getLogger(__name__)

_ENV_PREFIX = "SCHOLAR_MCP"


@dataclass
class ProjectConfig:
    """Scholar-mcp configuration loaded from environment variables.

    The ``server`` field carries generic FastMCP server config (transport,
    auth, event store).  Domain fields (API keys, cache dir, etc.) live
    directly on this dataclass.
    """

    # CONFIG-FIELDS-START — scholar domain fields; kept across copier update
    server: ServerConfig = field(default_factory=ServerConfig)
    server_name: str | None = None
    read_only: bool = True
    s2_api_key: str | None = None
    docling_url: str | None = None
    vlm_api_url: str | None = None
    vlm_api_key: str | None = None
    vlm_model: str = "gpt-4o"
    cache_dir: Path = field(default_factory=lambda: Path("/data/scholar-mcp"))
    contact_email: str | None = None
    epo_consumer_key: str | None = None
    epo_consumer_secret: str | None = None
    google_books_api_key: str | None = None
    github_token: str | None = None
    # CONFIG-FIELDS-END

    @property
    def epo_configured(self) -> bool:
        """True when both EPO OPS credentials are set."""
        return (
            self.epo_consumer_key is not None and self.epo_consumer_secret is not None
        )


def load_config() -> ProjectConfig:
    """Load configuration from environment variables.

    Reads all generic ``ServerConfig`` env vars (BASE_URL, BEARER_TOKEN,
    OIDC_*, EVENT_STORE_URL, etc.) plus scholar's domain fields — see
    ``fastmcp_pvl_core.ServerConfig.from_env`` for the generic set.
    """
    server = ServerConfig.from_env(env_prefix=_ENV_PREFIX)

    # CONFIG-FROM-ENV-START — scholar domain reads; kept across copier update
    server_name = env(_ENV_PREFIX, "SERVER_NAME")
    read_only = parse_bool(env(_ENV_PREFIX, "READ_ONLY", "true"))

    cache_dir = Path(env(_ENV_PREFIX, "CACHE_DIR") or "/data/scholar-mcp")

    # SCHOLAR_GITHUB_TOKEN (not SCHOLAR_MCP_GITHUB_TOKEN) — conventional
    # GitHub-tooling env name users expect.
    github_token = os.environ.get("SCHOLAR_GITHUB_TOKEN") or None

    config = ProjectConfig(
        server=server,
        server_name=server_name,
        read_only=read_only,
        s2_api_key=env(_ENV_PREFIX, "S2_API_KEY"),
        docling_url=env(_ENV_PREFIX, "DOCLING_URL"),
        vlm_api_url=env(_ENV_PREFIX, "VLM_API_URL"),
        vlm_api_key=env(_ENV_PREFIX, "VLM_API_KEY"),
        vlm_model=env(_ENV_PREFIX, "VLM_MODEL", "gpt-4o"),
        cache_dir=cache_dir,
        contact_email=env(_ENV_PREFIX, "CONTACT_EMAIL"),
        epo_consumer_key=env(_ENV_PREFIX, "EPO_CONSUMER_KEY"),
        epo_consumer_secret=env(_ENV_PREFIX, "EPO_CONSUMER_SECRET"),
        google_books_api_key=env(_ENV_PREFIX, "GOOGLE_BOOKS_API_KEY"),
        github_token=github_token,
    )
    # CONFIG-FROM-ENV-END

    logger.debug(
        "load_config: read_only=%s cache_dir=%s", config.read_only, config.cache_dir
    )
    return config

"""Configuration loading from environment variables.

All environment variables share the ``MCP_SERVER_`` prefix (controlled by
:data:`_ENV_PREFIX`).  Add your domain-specific configuration fields to
:class:`ServerConfig` and read them in :func:`load_config`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Change this to match your service.  All env vars will be prefixed with it.
# e.g. _ENV_PREFIX = "WEATHER_MCP" → WEATHER_MCP_READ_ONLY, WEATHER_MCP_PORT …
# ---------------------------------------------------------------------------
_ENV_PREFIX = "MCP_SERVER"


def get_log_level() -> int:
    """Return the configured log level from ``MCP_SERVER_LOG_LEVEL``.

    Accepts standard Python level names (``DEBUG``, ``INFO``, ``WARNING``,
    ``ERROR``).  Falls back to :data:`logging.INFO` when the variable is
    unset or contains an unrecognised value.

    Returns:
        An ``int`` log level constant from the :mod:`logging` module.
    """
    raw = os.environ.get(f"{_ENV_PREFIX}_LOG_LEVEL", "").strip().upper()
    if not raw:
        return logging.INFO
    level = logging.getLevelNamesMapping().get(raw)
    if level is None:
        logger.warning("Unrecognised LOG_LEVEL=%r — falling back to INFO", raw)
        return logging.INFO
    return level


def _env(name: str, default: str | None = None) -> str | None:
    """Return the value of ``{_ENV_PREFIX}_{name}`` from the environment.

    Args:
        name: Suffix after the prefix (e.g. ``"READ_ONLY"``).
        default: Fallback when the variable is unset.

    Returns:
        The environment variable value, or *default*.
    """
    return os.environ.get(f"{_ENV_PREFIX}_{name}", default)


def _parse_bool(value: str) -> bool:
    """Parse a boolean from an environment variable string.

    Treats ``"true"``, ``"1"``, and ``"yes"`` (case-insensitive) as ``True``.

    Args:
        value: Raw environment variable string.

    Returns:
        ``True`` for truthy strings, ``False`` otherwise.
    """
    return value.strip().lower() in ("true", "1", "yes")


@dataclass
class ServerConfig:
    """Server configuration loaded from environment variables.

    Add your domain-specific fields here.  Use :func:`load_config` to
    populate them from environment variables at startup.

    Attributes:
        read_only: When ``True`` (default), write-tagged tools are hidden via
            ``mcp.disable(tags={"write"})``.

    Example::

        # TODO: replace with your domain fields, e.g.:
        # data_dir: Path = Path("/data")
        # max_results: int = 50
    """

    read_only: bool = True


def load_config() -> ServerConfig:
    """Load configuration from environment variables.

    Currently reads:

    - ``MCP_SERVER_READ_ONLY``: disable write tools; default ``true``.

    TODO: Add your domain-specific env vars here and populate the
    corresponding :class:`ServerConfig` fields.

    Returns:
        A populated :class:`ServerConfig` instance.

    Example::

        config = load_config()
        # config.read_only == True by default
    """
    raw_read_only = _env("READ_ONLY")
    read_only = _parse_bool(raw_read_only) if raw_read_only is not None else True
    logger.debug("load_config: read_only=%s (raw=%r)", read_only, raw_read_only)

    return ServerConfig(read_only=read_only)

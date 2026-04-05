"""Environment-based configuration for Scholar MCP Server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_PREFIX = "SCHOLAR_MCP"


@dataclass
class ServerConfig:
    """All configuration loaded from environment variables.

    Attributes:
        read_only: When True, write-tagged tools are hidden.
        s2_api_key: Semantic Scholar API key (enables higher rate limits).
        docling_url: Base URL of docling-serve instance. PDF tools return
            ``docling_not_configured`` if unset.
        vlm_api_url: OpenAI-compatible endpoint for VLM enrichment.
        vlm_api_key: API key for the VLM endpoint.
        vlm_model: Model name passed to the VLM endpoint.
        cache_dir: Directory for SQLite DB and downloaded PDFs.
        contact_email: Email address included in the OpenAlex User-Agent header
            for the polite pool. Set ``SCHOLAR_MCP_CONTACT_EMAIL`` to opt in.
        epo_consumer_key: EPO OPS API consumer key.
        epo_consumer_secret: EPO OPS API consumer secret.
    """

    read_only: bool = True
    s2_api_key: str | None = None
    docling_url: str | None = None
    vlm_api_url: str | None = None
    vlm_api_key: str | None = None
    vlm_model: str = "gpt-4o"
    cache_dir: Path = Path("/data/scholar-mcp")
    contact_email: str | None = None
    epo_consumer_key: str | None = None
    epo_consumer_secret: str | None = None

    @property
    def epo_configured(self) -> bool:
        """True when both EPO OPS credentials are set."""
        return (
            self.epo_consumer_key is not None and self.epo_consumer_secret is not None
        )


def get_log_level() -> int:
    """Return the configured log level from the environment.

    Reads ``SCHOLAR_MCP_LOG_LEVEL`` (e.g. ``DEBUG``, ``INFO``).
    Defaults to ``INFO``.

    Returns:
        Integer log level constant from :mod:`logging`.
    """
    import logging

    raw = os.environ.get(f"{_ENV_PREFIX}_LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def load_config() -> ServerConfig:
    """Load :class:`ServerConfig` from environment variables.

    Returns:
        Populated :class:`ServerConfig` instance.
    """
    p = _ENV_PREFIX

    def _bool(key: str, default: bool) -> bool:
        val = os.environ.get(f"{p}_{key}")
        if val is None:
            return default
        return val.lower() not in ("0", "false", "no", "off", "n")

    def _str(key: str) -> str | None:
        return os.environ.get(f"{p}_{key}") or None

    return ServerConfig(
        read_only=_bool("READ_ONLY", True),
        s2_api_key=_str("S2_API_KEY"),
        docling_url=_str("DOCLING_URL"),
        vlm_api_url=_str("VLM_API_URL"),
        vlm_api_key=_str("VLM_API_KEY"),
        vlm_model=os.environ.get(f"{p}_VLM_MODEL", "gpt-4o"),
        cache_dir=Path(os.environ.get(f"{p}_CACHE_DIR", "/data/scholar-mcp")),
        contact_email=_str("CONTACT_EMAIL"),
        epo_consumer_key=_str("EPO_CONSUMER_KEY"),
        epo_consumer_secret=_str("EPO_CONSUMER_SECRET"),
    )

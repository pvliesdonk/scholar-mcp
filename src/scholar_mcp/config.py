"""Configuration for Scholar MCP.

Composes :class:`fastmcp_pvl_core.ServerConfig` via the domain
:class:`ProjectConfig` dataclass — never inherits.

Add domain-specific fields between the CONFIG-FIELDS sentinels, populate
them in ``from_env`` between the CONFIG-FROM-ENV sentinels, and enforce
their invariants in ``__post_init__`` between the CONFIG-VALIDATE
sentinels; copier update preserves all three blocks across template
updates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from fastmcp_pvl_core import (
    JobsConfig,
    ServerConfig,
    env,
    parse_bool,
)

_ENV_PREFIX = "SCHOLAR_MCP"


@dataclass(frozen=True)
class ProjectConfig:
    """Domain config for Scholar MCP.  Compose — don't inherit."""

    server: ServerConfig = field(default_factory=ServerConfig)

    # CONFIG-FIELDS-START — add domain fields below; kept across copier update
    # Composed, not inherited — same rule as `server` above.  It lives inside
    # the domain block because the template does not wire jobs; scholar does
    # (see `_server_tools.register_tools`).  Holding it here is also what
    # puts the SCHOLAR_MCP_JOBS_* vars in front of the config-surface
    # generator: `server_config_surface()` covers ServerConfig only.
    jobs: JobsConfig = field(default_factory=JobsConfig)
    read_only: bool = field(
        default=True,
        metadata={
            "help": (
                "When true, write-tagged tools (PDF download and conversion "
                "cache writes) are hidden. Set false to enable them."
            ),
            "tags": ("mode",),
        },
    )
    s2_api_key: str | None = field(
        default=None,
        metadata={
            "help": (
                "Semantic Scholar API key. Optional but strongly recommended: "
                "unauthenticated requests are limited to ~1 req/s. Request one "
                "at https://www.semanticscholar.org/product/api#api-key-form."
            ),
            "tags": ("s2",),
        },
    )
    docling_url: str | None = field(
        default=None,
        metadata={
            "help": (
                "Base URL of a running docling-serve instance for PDF "
                "conversion (e.g. http://localhost:5001). When unset, PDF "
                "conversion tools return an error."
            ),
            "tags": ("pdf",),
        },
    )
    vlm_api_url: str | None = field(
        default=None,
        metadata={
            "help": (
                "OpenAI-compatible VLM endpoint for formula and figure "
                "enrichment during PDF conversion."
            ),
            "tags": ("pdf",),
        },
    )
    vlm_api_key: str | None = field(
        default=None,
        metadata={
            "help": "API key for the VLM endpoint.",
            "tags": ("pdf",),
        },
    )
    vlm_model: str = field(
        default="gpt-4o",
        metadata={
            "help": "Model name to use with the VLM endpoint.",
            "tags": ("pdf",),
        },
    )
    cache_dir: Path = field(
        default=Path("/data/scholar-mcp"),
        metadata={
            "help": (
                "Directory for the SQLite cache database (cache.db) and "
                "downloaded PDFs (pdfs/, md/)."
            ),
            "tags": ("cache",),
        },
    )
    contact_email: str | None = field(
        default=None,
        metadata={
            "help": (
                "Contact email for the OpenAlex polite pool (improves rate "
                "limits). Also enables Unpaywall lookups as a PDF fallback "
                "source."
            ),
            "tags": ("enrichment",),
        },
    )
    epo_consumer_key: str | None = field(
        default=None,
        metadata={
            "help": (
                "EPO Open Patent Services consumer key. Optional; patent "
                "tools are hidden when unset. Register at "
                "https://developers.epo.org/user/register."
            ),
            "tags": ("patents",),
        },
    )
    epo_consumer_secret: str | None = field(
        default=None,
        metadata={
            "help": (
                "EPO Open Patent Services consumer secret. Optional; patent "
                "tools are hidden when unset."
            ),
            "tags": ("patents",),
        },
    )
    google_books_api_key: str | None = field(
        default=None,
        metadata={
            "help": (
                "Google Books API key. Optional; book tools work "
                "unauthenticated at reduced rate limits."
            ),
            "tags": ("books",),
        },
    )
    # Populated from SCHOLAR_GITHUB_TOKEN (not SCHOLAR_MCP_GITHUB_TOKEN) — the
    # conventional GitHub-tooling env name users expect. The non-prefixed read
    # is invisible to the domain env-var scan, so the var is declared in
    # config-presentation.domain.yml instead of via field metadata.
    github_token: str | None = None
    # Opt-in per-subject authorization: uncomment to enable. See pvl-core's
    # README "Authorization" section + scholar's README "Authorization
    # (opt-in)" section for the wire-in story. Also requires uncommenting
    # the matching AuthorizationMiddleware stanza in ``server.py`` and the
    # env-load in ``from_env`` below.
    # acl_path: Path | None = None

    @property
    def epo_configured(self) -> bool:
        """True when both EPO OPS credentials are set."""
        return (
            self.epo_consumer_key is not None and self.epo_consumer_secret is not None
        )

    # CONFIG-FIELDS-END

    def __post_init__(self) -> None:
        """Validate composed domain fields.  Raise ``ValueError`` when invalid.

        Runs on EVERY construction path — ``from_env`` and a direct
        ``ProjectConfig(field=...)`` alike.  That is what makes this the right
        home for a field invariant: ``env_float`` / ``env_int`` bounds check
        only the *env-sourced* value, never the default, so a direct
        construction slips past them.  They also cannot express an exclusive
        bound (their ``minimum`` / ``maximum`` are inclusive, so "must be > 0"
        lets ``0`` through) or a cross-field rule (A requires B,
        mutually-exclusive pairs).  All three belong here.

        The dataclass is ``frozen=True``: read fields freely, but plain
        assignment raises.  To *normalise* rather than merely check, use
        ``object.__setattr__(self, "name", value)``.
        """
        # CONFIG-VALIDATE-START — validate domain fields below; kept across copier update
        # (no domain invariants yet — scholar's fields are all independently
        #  optional; add cross-field rules here when one appears)
        # CONFIG-VALIDATE-END

    @classmethod
    def from_env(cls) -> ProjectConfig:
        """Load :class:`ProjectConfig` from ``SCHOLAR_MCP_*`` env vars."""
        return cls(
            server=ServerConfig.from_env(_ENV_PREFIX),
            # CONFIG-FROM-ENV-START — populate domain fields below; kept across copier update
            jobs=JobsConfig.from_env(_ENV_PREFIX),
            read_only=parse_bool(env(_ENV_PREFIX, "READ_ONLY", "true")),
            s2_api_key=env(_ENV_PREFIX, "S2_API_KEY"),
            docling_url=env(_ENV_PREFIX, "DOCLING_URL"),
            vlm_api_url=env(_ENV_PREFIX, "VLM_API_URL"),
            vlm_api_key=env(_ENV_PREFIX, "VLM_API_KEY"),
            vlm_model=env(_ENV_PREFIX, "VLM_MODEL", "gpt-4o") or "gpt-4o",
            cache_dir=Path(
                env(_ENV_PREFIX, "CACHE_DIR", "/data/scholar-mcp")
                or "/data/scholar-mcp"
            ),
            contact_email=env(_ENV_PREFIX, "CONTACT_EMAIL"),
            epo_consumer_key=env(_ENV_PREFIX, "EPO_CONSUMER_KEY"),
            epo_consumer_secret=env(_ENV_PREFIX, "EPO_CONSUMER_SECRET"),
            google_books_api_key=env(_ENV_PREFIX, "GOOGLE_BOOKS_API_KEY"),
            # SCHOLAR_GITHUB_TOKEN — see the github_token field comment above.
            github_token=os.environ.get("SCHOLAR_GITHUB_TOKEN") or None,
            # Opt-in authorization (see CONFIG-FIELDS-START comment above):
            # acl_path=Path(_p) if (_p := env(_ENV_PREFIX, "ACL_PATH")) else None,
            # CONFIG-FROM-ENV-END
        )

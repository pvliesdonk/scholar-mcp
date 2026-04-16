"""Standards enricher for the EnrichmentPipeline.

Attaches ``standard_metadata`` (a :class:`StandardRecord` dict) to S2
citation records whose title is predominantly a standards identifier.
Uses :func:`resolve_identifier_local` for detection and
``bundle.standards.get()`` for resolution.

Design reference: ``docs/specs/2026-04-16-pr5-standards-enrichment-design.md``.
"""

from __future__ import annotations

import logging
from typing import Any

from ._standards_client import resolve_identifier_local

logger = logging.getLogger(__name__)


class StandardsEnricher:
    """Auto-enriches citation records that ARE standards references.

    Plugs into the :class:`EnrichmentPipeline` at phase 0 alongside
    CrossRef and OpenAlex. The trigger heuristic requires the resolved
    identifier to cover >50% of the citation title, preventing false
    positives on papers that merely mention a standard.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (0 = first).
        tags: Labels used to filter enricher selection.
    """

    name: str = "standards"
    phase: int = 0
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True when the citation title is predominantly a standard.

        Checks:
        1. No existing ``standard_metadata`` (skip re-enrichment).
        2. Title is non-empty.
        3. ``resolve_identifier_local`` matches.
        4. Canonical identifier covers >50% of the title text.

        Args:
            record: The paper/citation record dict to inspect.

        Returns:
            ``True`` if this citation should be enriched with standards
            metadata.
        """
        if record.get("standard_metadata"):
            return False
        title = record.get("title")
        if not title or not isinstance(title, str):
            return False
        title = title.strip()
        if not title:
            return False
        match = resolve_identifier_local(title)
        if match is None:
            return False
        canonical, _body = match
        return len(canonical) > 0.5 * len(title)

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Resolve the standards identifier and attach metadata.

        Calls ``bundle.standards.get(canonical_identifier)``. If the
        standard is found (cache hit or live-fetch success), sets
        ``record["standard_metadata"]`` to the ``StandardRecord`` dict.
        If not found, does nothing — no error, no stub.

        Args:
            record: The paper/citation record dict to enrich in place.
            bundle: Service bundle providing ``standards`` client.
        """
        title = record.get("title")
        if not title or not isinstance(title, str):
            return
        match = resolve_identifier_local(title.strip())
        if match is None:
            return
        canonical, _body = match
        # Same >50% coverage guard as can_enrich() — makes enrich()
        # safe to call directly without the pipeline's can_enrich gate.
        if len(canonical) <= 0.5 * len(title.strip()):
            return
        logger.debug(
            "standards_enrich_attempt identifier=%s title=%s",
            canonical,
            title[:60],
        )
        try:
            standard = await bundle.standards.get(canonical)
            if standard is not None:
                record["standard_metadata"] = standard
                logger.debug(
                    "standards_enrich_hit identifier=%s body=%s",
                    canonical,
                    standard.get("body", "?"),
                )
        except Exception:
            logger.debug(
                "standards_enrich_failed identifier=%s",
                canonical,
                exc_info=True,
            )

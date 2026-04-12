"""OpenAlex venue enricher for paper records."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OpenAlexEnricher:
    """Enriches paper records with venue data from OpenAlex.

    Looks up the paper's DOI in OpenAlex and fills the ``venue``
    field from the primary location's source display name.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (0 = first).
        tags: Labels used to filter enricher selection.
    """

    name: str = "openalex"
    phase: int = 0
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True when record has a DOI but no venue.

        Args:
            record: The paper record dict to inspect.

        Returns:
            ``True`` if the record has a DOI and venue is empty or missing.
        """
        doi = (record.get("externalIds") or {}).get("DOI")
        if not doi:
            return False
        return not record.get("venue")

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill venue from OpenAlex, using cache when available.

        Extracts the DOI from ``record["externalIds"]["DOI"]``, checks
        the cache, falls back to the OpenAlex API, and sets
        ``record["venue"]`` from the primary location source name.

        All errors are caught and logged at DEBUG level so enrichment
        failures never propagate.

        Args:
            record: The paper record dict to enrich in place.
            bundle: Service bundle providing cache and OpenAlex client.
        """
        doi = (record.get("externalIds") or {}).get("DOI")
        if not doi:
            return
        try:
            cached = await bundle.cache.get_openalex(doi)
            oa_data = (
                cached if cached is not None else await bundle.openalex.get_by_doi(doi)
            )
            if oa_data is None:
                return
            if cached is None:
                await bundle.cache.set_openalex(doi, oa_data)
            loc = oa_data.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name")
            if venue:
                record["venue"] = venue
        except Exception:
            logger.debug("openalex_enrich_failed doi=%s", doi, exc_info=True)

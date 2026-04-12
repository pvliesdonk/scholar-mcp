"""CrossRef enricher for paper records."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CrossRefEnricher:
    """Enriches paper records with metadata from CrossRef.

    Looks up the paper's DOI in CrossRef and stores the full
    metadata response as ``crossref_metadata`` on the record.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (0 = first).
        tags: Labels used to filter enricher selection.
    """

    name: str = "crossref"
    phase: int = 0
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True when record has a DOI but no crossref_metadata.

        Args:
            record: The paper record dict to inspect.

        Returns:
            ``True`` if the record has a DOI and crossref_metadata is
            absent or falsy.
        """
        if record.get("crossref_metadata"):
            return False
        doi = (record.get("externalIds") or {}).get("DOI")
        return bool(doi)

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill crossref_metadata from CrossRef, using cache when available.

        Extracts the DOI from ``record["externalIds"]["DOI"]``, checks
        the cache, falls back to the CrossRef API, and sets
        ``record["crossref_metadata"]`` with the result.

        All errors are caught and logged at DEBUG level so enrichment
        failures never propagate.

        Args:
            record: The paper record dict to enrich in place.
            bundle: Service bundle providing cache and CrossRef client.
        """
        doi = (record.get("externalIds") or {}).get("DOI")
        if not doi:
            return
        try:
            cached = await bundle.cache.get_crossref(doi)
            cr_data = (
                cached if cached is not None else await bundle.crossref.get_by_doi(doi)
            )
            if cr_data is None:
                return
            if cached is None:
                await bundle.cache.set_crossref(doi, cr_data)
            record["crossref_metadata"] = cr_data
        except Exception:
            logger.debug("crossref_enrich_failed doi=%s", doi, exc_info=True)

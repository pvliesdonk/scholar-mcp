"""Resolve alternative PDF URLs when openAccessPdf is unavailable.

Tries multiple sources in order:
1. ArXiv — construct URL from externalIds.ArXiv
2. PubMed Central — construct URL from externalIds.PubMedCentral
3. Unpaywall — query by DOI (requires contact_email config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"


@dataclass
class ResolvedPdf:
    """A resolved PDF URL with provenance information.

    Attributes:
        url: Direct URL to the PDF.
        source: Where the URL was found (e.g. ``"arxiv"``, ``"pmc"``,
            ``"unpaywall"``).
    """

    url: str
    source: str


def _try_arxiv(paper: dict[str, Any]) -> ResolvedPdf | None:
    """Build arXiv PDF URL from externalIds.ArXiv."""
    ext = paper.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    if arxiv_id:
        return ResolvedPdf(
            url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            source="arxiv",
        )
    return None


def _try_pmc(paper: dict[str, Any]) -> ResolvedPdf | None:
    """Build PMC PDF URL from externalIds.PubMedCentral."""
    ext = paper.get("externalIds") or {}
    pmc_id = ext.get("PubMedCentral")
    if pmc_id:
        return ResolvedPdf(
            url=(f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"),
            source="pmc",
        )
    return None


async def _try_unpaywall(paper: dict[str, Any], email: str) -> ResolvedPdf | None:
    """Query Unpaywall API for an OA PDF location by DOI."""
    ext = paper.get("externalIds") or {}
    doi = ext.get("DOI")
    if not doi:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{_UNPAYWALL_BASE}/{doi}",
                params={"email": email},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf")
            if pdf_url:
                return ResolvedPdf(url=pdf_url, source="unpaywall")
    except (httpx.HTTPError, Exception):
        logger.debug("unpaywall_lookup_failed doi=%s", doi, exc_info=True)
    return None


async def resolve_alternative_pdf(
    paper: dict[str, Any],
    *,
    contact_email: str | None = None,
) -> ResolvedPdf | None:
    """Try alternative sources for a PDF URL.

    Called when ``openAccessPdf`` is absent from Semantic Scholar metadata.
    Checks ArXiv and PMC synchronously (URL construction only), then
    queries Unpaywall if a DOI and contact email are available.

    Args:
        paper: Semantic Scholar paper metadata dict (must include
            ``externalIds``).
        contact_email: Email for the Unpaywall polite pool. Unpaywall
            is skipped when not set.

    Returns:
        A :class:`ResolvedPdf` if a URL was found, else None.
    """
    # Fast, no-network checks first
    result = _try_arxiv(paper)
    if result:
        logger.info("alt_pdf_resolved source=arxiv paper=%s", paper.get("paperId"))
        return result

    result = _try_pmc(paper)
    if result:
        logger.info("alt_pdf_resolved source=pmc paper=%s", paper.get("paperId"))
        return result

    # Network call — only if email configured
    if contact_email:
        result = await _try_unpaywall(paper, contact_email)
        if result:
            logger.info(
                "alt_pdf_resolved source=unpaywall paper=%s", paper.get("paperId")
            )
            return result

    return None

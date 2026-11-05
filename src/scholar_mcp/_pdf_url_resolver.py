"""Resolve alternative PDF URLs when openAccessPdf is unavailable or fails.

Lists candidates from these sources, in order:
1. ArXiv — construct URL from externalIds.ArXiv
2. PubMed Central — construct URL from externalIds.PubMedCentral
3. Unpaywall — query by DOI (requires contact_email config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from ._record_types import PaperRecord

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


def _try_arxiv(paper: PaperRecord) -> ResolvedPdf | None:
    """Build arXiv PDF URL from externalIds.ArXiv."""
    ext = paper.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    if arxiv_id:
        return ResolvedPdf(
            url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            source="arxiv",
        )
    return None


def _try_pmc(paper: PaperRecord) -> ResolvedPdf | None:
    """Build PMC PDF URL from externalIds.PubMedCentral."""
    ext = paper.get("externalIds") or {}
    pmc_id = ext.get("PubMedCentral")
    if pmc_id:
        return ResolvedPdf(
            url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf",
            source="pmc",
        )
    return None


async def _try_unpaywall(
    paper: PaperRecord,
    email: str,
    http_client: httpx.AsyncClient | None = None,
) -> ResolvedPdf | None:
    """Query Unpaywall API for an OA PDF location by DOI.

    Args:
        paper: Paper metadata dict with ``externalIds.DOI``.
        email: Contact email for the Unpaywall polite pool.
        http_client: Optional shared httpx client for connection pooling.
            A temporary client is created if not provided.
    """
    ext = paper.get("externalIds") or {}
    doi = ext.get("DOI")
    if not doi:
        return None
    try:
        if http_client is not None:
            r = await http_client.get(
                f"{_UNPAYWALL_BASE}/{doi}",
                params={"email": email},
            )
        else:
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
    except Exception:
        logger.debug("unpaywall_lookup_failed doi=%s", doi, exc_info=True)
    return None


async def iter_alternative_pdfs(
    paper: PaperRecord,
    *,
    contact_email: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> AsyncGenerator[ResolvedPdf, None]:
    """Yield every alternative PDF URL known for a paper, in trial order.

    Used when the Semantic Scholar ``openAccessPdf`` URL is absent or did
    not yield a PDF. ArXiv and PMC URLs are built without network access;
    Unpaywall is queried only when the caller asks for the next candidate
    after those, and only if a DOI and contact email are available. A
    caller that stops at the first working PDF therefore makes no
    Unpaywall request.

    Args:
        paper: Semantic Scholar paper metadata dict (must include
            ``externalIds``).
        contact_email: Email for the Unpaywall polite pool. Unpaywall
            is skipped when not set.
        http_client: Optional shared httpx client for Unpaywall requests.

    Yields:
        Each candidate, ArXiv first, then PMC, then Unpaywall.
    """
    for candidate in (_try_arxiv(paper), _try_pmc(paper)):
        if candidate:
            logger.info(
                "alt_pdf_resolved source=%s paper=%s",
                candidate.source,
                paper.get("paperId"),
            )
            yield candidate
    if not contact_email:
        return
    unpaywall = await _try_unpaywall(paper, contact_email, http_client)
    if unpaywall:
        logger.info("alt_pdf_resolved source=unpaywall paper=%s", paper.get("paperId"))
        yield unpaywall

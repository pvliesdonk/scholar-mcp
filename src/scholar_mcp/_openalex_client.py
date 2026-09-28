"""OpenAlex API client for metadata enrichment.

External behaviour (the work object): ``docs/design/reference/openalex-works.md``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpenAlexClient:
    """Thin async client for the OpenAlex API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at OpenAlex.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch OpenAlex work metadata by DOI.

        Args:
            doi: DOI string (without ``https://doi.org/`` prefix).

        Returns:
            OpenAlex work dict or None if not found.
        """
        url = f"/works/https://doi.org/{doi}"
        try:
            r = await self._client.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]  # httpx returns Any
        except httpx.HTTPStatusError:
            logger.warning("openalex_error doi=%s status=%s", doi, r.status_code)
            return None


# URI prefixes OpenAlex puts on the external IDs it lists under ``ids``.
_ID_PREFIXES = (
    "https://doi.org/",
    "https://pubmed.ncbi.nlm.nih.gov/",
    "https://www.ncbi.nlm.nih.gov/pmc/articles/",
    "https://openalex.org/",
)

# OpenAlex ``ids`` key -> the S2 ``externalIds`` key for the same identifier.
_EXTERNAL_ID_KEYS = {
    "doi": "DOI",
    "mag": "MAG",
    "pmid": "PubMed",
    "pmcid": "PubMedCentral",
    "openalex": "OpenAlex",
}


def work_venue(work: dict[str, Any]) -> str | None:
    """Return the venue name of an OpenAlex work, or None.

    Args:
        work: An OpenAlex work object.

    Returns:
        ``primary_location.source.display_name`` when present.
    """
    source = (work.get("primary_location") or {}).get("source") or {}
    venue = source.get("display_name")
    return venue if isinstance(venue, str) and venue else None


def _strip_id(value: Any) -> str:
    text = str(value)
    for prefix in _ID_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _external_ids(work: dict[str, Any]) -> dict[str, str]:
    # ``ids.doi`` and ``ids.openalex`` repeat the top-level ``doi`` and ``id``,
    # so either place serves.
    ids = {
        "doi": work.get("doi"),
        "openalex": work.get("id"),
        **(work.get("ids") or {}),
    }
    return {
        s2_key: _strip_id(ids[oa_key])
        for oa_key, s2_key in _EXTERNAL_ID_KEYS.items()
        if ids.get(oa_key)
    }


def _abstract(work: dict[str, Any]) -> str | None:
    """Rebuild plain text from ``abstract_inverted_index`` (word -> positions)."""
    index = work.get("abstract_inverted_index")
    if not index:
        return None
    placed = sorted(
        (position, word) for word, positions in index.items() for position in positions
    )
    return " ".join(word for _, word in placed)


def _open_access_pdf(work: dict[str, Any]) -> dict[str, Any] | None:
    """Describe the best open-access PDF, S2-style, or None.

    Only ``pdf_url`` qualifies: ``openAccessPdf.url`` is followed as a PDF
    download, and OpenAlex's ``oa_url`` or ``landing_page_url`` is often an
    HTML page.
    """
    url = (work.get("best_oa_location") or {}).get("pdf_url")
    if not url:
        return None
    status = (work.get("open_access") or {}).get("oa_status")
    return {
        "url": url,
        "status": status.upper() if isinstance(status, str) else None,
        "license": None,
    }


def _reference_count(work: dict[str, Any]) -> int | None:
    count = work.get("referenced_works_count")
    if isinstance(count, int):
        return count
    referenced = work.get("referenced_works")
    return len(referenced) if isinstance(referenced, list) else None


def work_to_paper(work: dict[str, Any], fields: str) -> dict[str, Any]:
    """Map an OpenAlex work to an S2-shaped paper record.

    Keys follow the S2 Graph API names so a caller reads an OpenAlex-sourced
    record the way it reads an S2 one (#478). ``paperId`` is null because
    OpenAlex has no S2 id, and ``tldr`` and ``fieldsOfStudy`` are null because
    OpenAlex has no counterpart in S2's vocabulary.

    Args:
        work: An OpenAlex work object.
        fields: Comma-separated S2 field names to keep, as in ``FIELD_SETS``.

    Returns:
        A mapping holding exactly the requested fields.
    """
    authorships = work.get("authorships") or []
    mapped: dict[str, Any] = {
        "paperId": None,
        "title": work.get("title") or work.get("display_name"),
        "year": work.get("publication_year"),
        "venue": work_venue(work),
        "citationCount": work.get("cited_by_count"),
        "authors": [
            {"authorId": None, "name": (a.get("author") or {}).get("display_name")}
            for a in authorships
        ],
        "externalIds": _external_ids(work),
        "abstract": _abstract(work),
        "tldr": None,
        "openAccessPdf": _open_access_pdf(work),
        "fieldsOfStudy": None,
        "referenceCount": _reference_count(work),
    }
    return {name: mapped.get(name) for name in fields.split(",")}

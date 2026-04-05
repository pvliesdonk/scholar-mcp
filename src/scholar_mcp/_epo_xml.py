"""EPO OPS XML response parsers.

Parses raw XML bytes from the EPO Open Patent Services (OPS) API into plain
Python dicts. Two endpoints are supported:

- ``published-data/biblio`` — bibliographic details for a single patent
- ``published-data/search`` — search results with publication references

The parsers use ``lxml.etree`` with XPath and namespace-aware element
traversal.  All helper functions are module-private; only the two public
``parse_*`` functions are part of the module's interface.
"""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)

# XML namespaces used in EPO OPS responses.
_NS: dict[str, str] = {
    "ops": "http://ops.epo.org",
    "exch": "http://www.epo.org/exchange",
}

# Default namespace URI (used on exchange-document and most biblio elements).
_EXCH = "http://www.epo.org/exchange"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _text(el: etree._Element | None) -> str:
    """Extract stripped text content from an element.

    Args:
        el: An lxml element, or ``None``.

    Returns:
        Stripped text of the element, or an empty string when *el* is
        ``None`` or has no text content.
    """
    if el is None:
        return ""
    return (el.text or "").strip()


def _date_fmt(raw: str) -> str:
    """Convert a compact date string to ISO format.

    Args:
        raw: Date string in ``YYYYMMDD`` format.

    Returns:
        Formatted date as ``YYYY-MM-DD``, or an empty string when *raw* is
        not exactly 8 characters.
    """
    raw = raw.strip()
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return ""


def _find_docdb_id(
    parent: etree._Element,
) -> etree._Element | None:
    """Return the first ``document-id`` child with ``document-id-type="docdb"``.

    Args:
        parent: Element that contains ``document-id`` children.

    Returns:
        Matching element, or ``None`` if not found.
    """
    for el in parent.iter(f"{{{_EXCH}}}document-id"):
        if el.get("document-id-type") == "docdb":
            return el
    return None


def _parse_classification(cls_el: etree._Element) -> str:
    """Build a CPC classification string from a ``patent-classification`` element.

    Combines the section, class, subclass, main-group and subgroup into the
    canonical form ``H04L29/06``.

    Args:
        cls_el: A ``<patent-classification>`` lxml element.

    Returns:
        CPC code string, or an empty string when required sub-elements are
        missing.
    """
    def _get(tag: str) -> str:
        return _text(cls_el.find(f"{{{_EXCH}}}{tag}"))

    section = _get("section")
    cls = _get("class")
    subclass = _get("subclass")
    main_group = _get("main-group")
    subgroup = _get("subgroup")
    if not (section and cls and subclass and main_group and subgroup):
        return ""
    return f"{section}{cls}{subclass}{main_group}/{subgroup}"


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_biblio_xml(xml_bytes: bytes) -> dict[str, Any]:
    """Parse an EPO OPS biblio endpoint XML response.

    Extracts bibliographic metadata from the first ``exchange-document``
    element found in the response.  English titles and abstracts are
    preferred; the first available language is used as a fallback.

    Args:
        xml_bytes: Raw XML bytes returned by the EPO OPS
            ``published-data/biblio`` endpoint.

    Returns:
        Dictionary with the following keys:

        - ``title`` (str): Patent title, preferring English.
        - ``abstract`` (str): Abstract text, preferring English.
        - ``applicants`` (list[str]): Applicant names in document order.
        - ``inventors`` (list[str]): Inventor names in document order.
        - ``publication_number`` (str): Dotted DOCDB number
          ``CC.number.kind``.
        - ``publication_date`` (str): Publication date ``YYYY-MM-DD``.
        - ``filing_date`` (str): Application filing date ``YYYY-MM-DD``.
        - ``priority_date`` (str): Earliest priority date ``YYYY-MM-DD``.
        - ``family_id`` (str): Patent family identifier.
        - ``classifications`` (list[str]): CPC classification codes.
        - ``url`` (str): Espacenet URL for the patent.
    """
    root = etree.fromstring(xml_bytes)

    # Locate the first exchange-document element.
    exchange_doc = root.find(".//exch:exchange-documents/exch:exchange-document", _NS)
    if exchange_doc is None:
        # Fall back: search without exch prefix (default namespace handling)
        exchange_doc = root.find(f".//{{{_EXCH}}}exchange-document")
    if exchange_doc is None:
        logger.warning("No exchange-document found in biblio XML")
        return _empty_biblio()

    family_id = exchange_doc.get("family-id", "")
    country = exchange_doc.get("country", "")

    biblio = exchange_doc.find(f"{{{_EXCH}}}bibliographic-data")
    if biblio is None:
        logger.warning("No bibliographic-data found in exchange-document")
        return _empty_biblio()

    # --- Publication reference ---
    pub_ref = biblio.find(f"{{{_EXCH}}}publication-reference")
    pub_country = ""
    pub_number = ""
    pub_kind = ""
    pub_date = ""
    if pub_ref is not None:
        docdb_id = _find_docdb_id(pub_ref)
        if docdb_id is not None:
            pub_country = _text(docdb_id.find(f"{{{_EXCH}}}country"))
            pub_number = _text(docdb_id.find(f"{{{_EXCH}}}doc-number"))
            pub_kind = _text(docdb_id.find(f"{{{_EXCH}}}kind"))
            pub_date = _date_fmt(_text(docdb_id.find(f"{{{_EXCH}}}date")))

    if not pub_country:
        pub_country = country
    publication_number = f"{pub_country}.{pub_number}.{pub_kind}"

    # --- Filing date (application reference) ---
    app_ref = biblio.find(f"{{{_EXCH}}}application-reference")
    filing_date = ""
    if app_ref is not None:
        docdb_id = _find_docdb_id(app_ref)
        if docdb_id is not None:
            filing_date = _date_fmt(_text(docdb_id.find(f"{{{_EXCH}}}date")))

    # --- Priority date (earliest priority claim) ---
    priority_date = ""
    priority_claims = biblio.find(f"{{{_EXCH}}}priority-claims")
    if priority_claims is not None:
        dates: list[str] = []
        for claim in priority_claims.iter(f"{{{_EXCH}}}priority-claim"):
            docdb_id = _find_docdb_id(claim)
            if docdb_id is not None:
                raw_date = _text(docdb_id.find(f"{{{_EXCH}}}date"))
                if raw_date:
                    dates.append(raw_date)
        if dates:
            priority_date = _date_fmt(min(dates))

    # --- Parties ---
    parties = biblio.find(f"{{{_EXCH}}}parties")
    applicants: list[str] = []
    inventors: list[str] = []
    if parties is not None:
        applicants_el = parties.find(f"{{{_EXCH}}}applicants")
        if applicants_el is not None:
            for app in applicants_el.iter(f"{{{_EXCH}}}applicant"):
                name_el = app.find(f"{{{_EXCH}}}applicant-name/{{{_EXCH}}}name")
                name = _text(name_el)
                if name:
                    applicants.append(name)

        inventors_el = parties.find(f"{{{_EXCH}}}inventors")
        if inventors_el is not None:
            for inv in inventors_el.iter(f"{{{_EXCH}}}inventor"):
                name_el = inv.find(f"{{{_EXCH}}}inventor-name/{{{_EXCH}}}name")
                name = _text(name_el)
                if name:
                    inventors.append(name)

    # --- Title (prefer English) ---
    title = _pick_lang(biblio, f"{{{_EXCH}}}invention-title", text_only=True)

    # --- Abstract (prefer English) ---
    abstract = _pick_lang(biblio, f"{{{_EXCH}}}abstract", text_only=False)

    # --- Classifications ---
    classifications: list[str] = []
    patent_cls = biblio.find(f"{{{_EXCH}}}patent-classifications")
    if patent_cls is not None:
        for cls_el in patent_cls.iter(f"{{{_EXCH}}}patent-classification"):
            code = _parse_classification(cls_el)
            if code:
                classifications.append(code)

    # --- Espacenet URL ---
    # Strip dots from publication_number for URL: EP.1234567.A1 -> EP1234567A1
    url_num = pub_country + pub_number + pub_kind
    url = f"https://worldwide.espacenet.com/patent/search/family/{family_id}/publication/{url_num}"

    return {
        "title": title,
        "abstract": abstract,
        "applicants": applicants,
        "inventors": inventors,
        "publication_number": publication_number,
        "publication_date": pub_date,
        "filing_date": filing_date,
        "priority_date": priority_date,
        "family_id": family_id,
        "classifications": classifications,
        "url": url,
    }


def parse_search_xml(xml_bytes: bytes) -> dict[str, Any]:
    """Parse an EPO OPS search endpoint XML response.

    Extracts the total result count and the list of publication references
    from a ``published-data/search`` response.

    Args:
        xml_bytes: Raw XML bytes returned by the EPO OPS
            ``published-data/search`` endpoint.

    Returns:
        Dictionary with the following keys:

        - ``total_count`` (int): Total number of results reported by the API.
        - ``references`` (list[dict]): Publication references found in the
          response page.  Each entry has keys ``country``, ``number``,
          ``kind`` (all strings).
    """
    root = etree.fromstring(xml_bytes)

    biblio_search = root.find("ops:biblio-search", _NS)
    if biblio_search is None:
        logger.warning("No ops:biblio-search element found in search XML")
        return {"total_count": 0, "references": []}

    total_count = int(biblio_search.get("total-result-count", "0"))

    references: list[dict[str, str]] = []
    search_result = biblio_search.find("ops:search-result", _NS)
    if search_result is not None:
        for pub_ref in search_result.iter(f"{{{_NS['ops']}}}publication-reference"):
            docdb_id = _find_docdb_id(pub_ref)
            if docdb_id is not None:
                country = _text(docdb_id.find(f"{{{_EXCH}}}country"))
                number = _text(docdb_id.find(f"{{{_EXCH}}}doc-number"))
                kind = _text(docdb_id.find(f"{{{_EXCH}}}kind"))
                if country and number:
                    references.append(
                        {"country": country, "number": number, "kind": kind}
                    )

    return {"total_count": total_count, "references": references}


# ---------------------------------------------------------------------------
# Private helpers (continued)
# ---------------------------------------------------------------------------


def _pick_lang(
    parent: etree._Element,
    tag: str,
    *,
    text_only: bool,
) -> str:
    """Find the best language variant of a repeated element.

    Scans all direct children of *parent* matching *tag* and returns the
    text content of the English (``lang="en"``) variant when available,
    falling back to the first variant found.

    Args:
        parent: Parent element to search within.
        tag: Clark-notation tag name (e.g. ``"{ns}invention-title"``).
        text_only: When ``True``, use ``el.text``; when ``False``, collect
            all descendant text (for elements with ``<p>`` children).

    Returns:
        Best-match text content, or an empty string when no matching element
        exists.
    """

    def _extract(el: etree._Element) -> str:
        if text_only:
            return _text(el)
        # Concatenate all text nodes within the element (handles <p> wrappers).
        parts = [el.text or ""] + [
            (child.text or "") + (child.tail or "") for child in el
        ]
        return " ".join(p.strip() for p in parts if p.strip())

    first: str | None = None
    for el in parent.iterchildren(tag):
        lang = el.get("lang", "")
        text = _extract(el)
        if lang == "en":
            return text
        if first is None:
            first = text
    return first or ""


def _empty_biblio() -> dict[str, Any]:
    """Return an empty biblio dict with correct key structure.

    Returns:
        Dictionary with all expected biblio keys set to empty values.
    """
    return {
        "title": "",
        "abstract": "",
        "applicants": [],
        "inventors": [],
        "publication_number": "",
        "publication_date": "",
        "filing_date": "",
        "priority_date": "",
        "family_id": "",
        "classifications": [],
        "url": "",
    }

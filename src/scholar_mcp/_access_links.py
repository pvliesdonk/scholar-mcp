"""Build operator-configured access links for a paper.

An operator lists URL templates (an institutional OpenURL link resolver, an
inter-library-loan form, a login redirector, a publisher DOI link) and the
server fills them from a paper's metadata. The server never requests these
URLs: they are routes for the user, or for an agent browsing from the user's
network, to a paper the server could not fetch itself.

The OpenURL query strings follow OpenURL 0.1 and ANSI/NISO Z39.88-2004
(OpenURL 1.0, KEV journal format); the keys, the encoding rules and the
hybrid form are recorded with sources in
``docs/design/reference/openurl.md``. The journal details they carry (ISSN,
volume, issue, pages) come from the record's S2 and CrossRef fields, described
in ``docs/design/reference/semantic-scholar-api.md`` and
``docs/design/reference/crossref-works.md``.
"""

from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass, replace
from dataclasses import fields as dataclass_fields
from typing import TYPE_CHECKING, Any, TypedDict
from urllib.parse import quote

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

#: Placeholders a template may use.
PLACEHOLDERS: frozenset[str] = frozenset(
    {"doi", "doi_url", "openurl", "openurl_0_1", "openurl_hybrid"}
)

# OpenURL 1.0 (Z39.88-2004 §22.1, Inline transport; KEV journal matrix).
_KEV_ADMIN: tuple[tuple[str, str], ...] = (
    ("url_ver", "Z39.88-2004"),
    ("url_ctx_fmt", "info:ofi/fmt:kev:mtx:ctx"),
    ("ctx_ver", "Z39.88-2004"),
    ("ctx_enc", "info:ofi/enc:UTF-8"),
    ("rfr_id", "info:sid/pvliesdonk.github.io:scholar-mcp"),
    ("rft_val_fmt", "info:ofi/fmt:kev:mtx:journal"),
)
# OpenURL 0.1 §3: sid is VendorID ':' DatabaseID, VendorID alphanumeric.
_SID_0_1 = "scholarmcp:scholarmcp"
# Bounds the URL: Z39.88 asks resolvers to accept 2,048 bytes (App. E.1).
_MAX_LISTED_AUTHORS = 5
# A page range as S2 ("116 - 135") and CrossRef ("436-444") write it.
_PAGE_RANGE = re.compile(r"^(\S+?)\s*[-\u2013\u2014]+\s*(\S+)$")
_DOI_URL_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_TEMPLATE_KEYS = frozenset({"label", "template"})


@dataclass(frozen=True)
class AccessLinkTemplate:
    """One operator-configured link template.

    Attributes:
        label: Name shown to the user, e.g. ``"Library full text"``.
        template: ``http(s)`` URL with ``{placeholder}`` fields; see
            :data:`PLACEHOLDERS`.
    """

    label: str
    template: str


#: Used when the operator configures nothing: doi.org reaches the publisher,
#: where a licensed network's IP-based access applies. Not tied to any
#: institution. An explicit empty list turns links off.
DEFAULT_TEMPLATES: tuple[AccessLinkTemplate, ...] = (
    AccessLinkTemplate(label="Publisher (DOI)", template="https://doi.org/{doi}"),
)


class AccessLink(TypedDict):
    """A filled-in access link."""

    label: str
    url: str


@dataclass(frozen=True)
class _JournalDetails:
    """Where in its journal a paper appears, as far as the record says."""

    issn: str | None = None
    eissn: str | None = None
    volume: str | None = None
    issue: str | None = None
    spage: str | None = None
    epage: str | None = None

    def or_else(self, fallback: _JournalDetails) -> _JournalDetails:
        """Fill each field this one lacks from *fallback*."""
        filled = {
            f.name: getattr(fallback, f.name)
            for f in dataclass_fields(self)
            if getattr(self, f.name) is None
        }
        return replace(self, **filled)


@dataclass(frozen=True)
class _Citation:
    """The metadata the link formats draw on, extracted once per paper."""

    doi: str | None
    pmid: str | None
    title: str | None
    journal: str | None
    year: str | None
    authors: tuple[str, ...]
    details: _JournalDetails

    @property
    def citable(self) -> bool:
        """True when an OpenURL can identify the paper at all."""
        return bool(self.doi or self.pmid or self.title)


def parse_access_link_templates(raw: str | None) -> tuple[AccessLinkTemplate, ...]:
    """Parse the operator's access-link configuration.

    Args:
        raw: JSON text: a list of ``{"label": ..., "template": ...}``
            objects. ``None`` or blank means unconfigured; ``[]`` turns
            links off.

    Returns:
        The templates, in the configured order, or
        :data:`DEFAULT_TEMPLATES` when unconfigured.

    Raises:
        ValueError: The text is not such a list, or a template is not an
            ``http(s)`` URL using only known placeholders.
    """
    if raw is None or not raw.strip():
        return DEFAULT_TEMPLATES
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON ({exc.msg})") from None
    if not isinstance(entries, list):
        raise ValueError("expected a JSON list of {label, template} objects")
    return tuple(_parse_entry(index, entry) for index, entry in enumerate(entries))


def _parse_entry(index: int, entry: object) -> AccessLinkTemplate:
    """Validate one configuration entry."""
    where = f"entry {index}"
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object with label and template")
    extra = sorted(set(entry) - _TEMPLATE_KEYS)
    if extra:
        raise ValueError(f"{where}: unknown key(s) {', '.join(extra)}")
    label, template = entry.get("label"), entry.get("template")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{where}: label must be a non-empty string")
    if not isinstance(template, str) or not template.startswith(
        ("http://", "https://")
    ):
        raise ValueError(f"{where}: template must be an http:// or https:// URL")
    _check_placeholders(where, template)
    return AccessLinkTemplate(label=label.strip(), template=template)


def _check_placeholders(where: str, template: str) -> None:
    """Reject unknown placeholders, conversions and format specs."""
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"{where}: unbalanced brace in template ({exc})") from None
    for _literal, name, spec, conversion in fields:
        if name is None:
            continue
        if spec or conversion:
            shown = name + (f"!{conversion}" if conversion else "")
            shown += f":{spec}" if spec else ""
            raise ValueError(f"{where}: placeholder {{{shown}}} takes no options")
        if name not in PLACEHOLDERS:
            known = ", ".join(sorted(PLACEHOLDERS))
            raise ValueError(f"{where}: unknown placeholder {{{name}}}; use {known}")


def build_access_links(
    paper: Mapping[str, Any], templates: Sequence[AccessLinkTemplate]
) -> list[AccessLink]:
    """Fill each template from a paper's metadata.

    A template whose placeholders the paper cannot fill (``{doi}`` for a
    paper without a DOI) is skipped, so every returned link is complete.

    Args:
        paper: A Semantic Scholar paper record, with ``crossref_metadata``
            when enrichment added it.
        templates: The configured templates, in priority order.

    Returns:
        One labelled link per template that could be filled, in order.
    """
    if not templates:
        return []
    citation = _citation(paper)
    links: list[AccessLink] = []
    for template in templates:
        url = _render(template.template, citation)
        if url is not None:
            links.append(AccessLink(label=template.label, url=url))
    return links


def _render(template: str, citation: _Citation) -> str | None:
    """Substitute placeholders, or return None when one cannot be filled."""
    parts: list[str] = []
    for literal, name, _spec, _conversion in string.Formatter().parse(template):
        parts.append(literal)
        if name is None:
            continue
        value = _VALUES[name](citation)
        if value is None:
            return None
        parts.append(value)
    return "".join(parts)


def _citation(paper: Mapping[str, Any]) -> _Citation:
    """Extract the fields the link formats use from a paper record."""
    ids = paper.get("externalIds") or {}
    doi = ids.get("DOI")
    pmid = ids.get("PubMed")
    year = paper.get("year")
    names = [a.get("name") for a in paper.get("authors") or []]
    s2_journal = paper.get("journal") or {}
    crossref = paper.get("crossref_metadata") or {}
    journal = (
        paper.get("venue")
        or _text(s2_journal.get("name"))
        or _first_text(crossref.get("container-title"))
    )
    return _Citation(
        doi=_DOI_URL_PREFIX.sub("", doi.strip()) or None if doi else None,
        pmid=str(pmid) if pmid else None,
        title=paper.get("title") or None,
        journal=journal or None,
        year=str(year) if year else None,
        authors=tuple(n.strip() for n in names if isinstance(n, str) and n.strip()),
        details=_journal_details(paper),
    )


def _journal_details(paper: Mapping[str, Any]) -> _JournalDetails:
    """ISSN, volume, issue and pages, CrossRef first and S2 for the rest.

    CrossRef carries each value in its own field. S2 can merge volume and
    issue into one string, so its values only fill what CrossRef lacks.
    """
    details = _crossref_details(paper.get("crossref_metadata") or {}).or_else(
        _s2_details(paper)
    )
    if details.issn is not None and details.issn == details.eissn:
        details = replace(details, issn=None)
    return details


def _crossref_details(work: Mapping[str, Any]) -> _JournalDetails:
    """Journal details from a CrossRef work (``crossref_metadata``)."""
    typed = {
        entry.get("type"): _text(entry.get("value"))
        for entry in work.get("issn-type") or []
        if isinstance(entry, dict)
    }
    issn = typed.get("print")
    eissn = typed.get("electronic")
    if issn is None and eissn is None:
        issn = _first_text(work.get("ISSN"))
    spage, epage = _page_range(_text(work.get("page")))
    return _JournalDetails(
        issn=issn,
        eissn=eissn,
        volume=_text(work.get("volume")),
        issue=_text(work.get("issue")),
        spage=spage or _text(work.get("article-number")),
        epage=epage,
    )


def _s2_details(paper: Mapping[str, Any]) -> _JournalDetails:
    """Journal details from S2's ``journal`` and ``publicationVenue``."""
    journal = paper.get("journal") or {}
    venue = paper.get("publicationVenue") or {}
    volume = _text(journal.get("volume"))
    spage, epage = _page_range(_text(journal.get("pages")))
    return _JournalDetails(
        issn=_text(venue.get("issn")),
        # "116 6" is volume 116, issue 6, but only the volume is certain.
        volume=volume.split()[0] if volume else None,
        spage=spage,
        epage=epage,
    )


def _page_range(pages: str | None) -> tuple[str | None, str | None]:
    """Split ``"116 - 135"`` into start and end; a single token is the start."""
    if pages is None:
        return None, None
    match = _PAGE_RANGE.match(pages)
    if match:
        return match.group(1), match.group(2)
    return (pages, None) if len(pages.split()) == 1 else (None, None)


def _text(value: object) -> str | None:
    """A stripped non-empty string, or None."""
    if isinstance(value, int | str):
        return str(value).strip() or None
    return None


def _first_text(values: object) -> str | None:
    """The first usable string of a list, or None."""
    if isinstance(values, list):
        return next((t for t in map(_text, values) if t), None)
    return None


def _split_name(name: str) -> tuple[str, str | None]:
    """Split a display name into (last name, first names), last token last."""
    first, _, last = name.rpartition(" ")
    return last, first.strip() or None


# -- encoders ---------------------------------------------------------------


def _kev_1_0(value: str) -> str:
    """Encode a 1.0 KEV value: only ``A-Za-z0-9 . - * _`` stay (Z39.88 §13.4)."""
    return quote(value, safe="*").replace("~", "%7E")


def _kev_0_1(value: str) -> str:
    """Encode a 0.1 value: RFC 2396 unreserved marks stay (OpenURL 0.1 §0)."""
    return quote(value, safe="!*'()")


def _join(pairs: list[tuple[str, str]]) -> str:
    """Join already-encoded key/value pairs into a query string."""
    return "&".join(f"{key}={value}" for key, value in pairs)


# -- placeholder values -----------------------------------------------------


def _doi_value(citation: _Citation) -> str | None:
    """``{doi}``: the DOI, safe in a URL path or a query value."""
    return quote(citation.doi, safe="/()") if citation.doi else None


def _doi_url_value(citation: _Citation) -> str | None:
    """``{doi_url}``: the doi.org URL, fully encoded for use as a query value."""
    if not citation.doi:
        return None
    return quote(f"https://doi.org/{citation.doi}", safe="")


def _pairs_1_0(citation: _Citation) -> list[tuple[str, str]]:
    """The OpenURL 1.0 ContextObject as encoded key/value pairs."""
    pairs = [(key, _kev_1_0(value)) for key, value in _KEV_ADMIN]
    if citation.doi:
        pairs.append(("rft_id", _kev_1_0(f"info:doi/{citation.doi}")))
    if citation.pmid:
        pairs.append(("rft_id", _kev_1_0(f"info:pmid/{citation.pmid}")))
    fields = _metadata_fields(citation)
    pairs += [(f"rft.{key}", _kev_1_0(value)) for key, value in fields]
    pairs += [
        ("rft.au", _kev_1_0(name)) for name in citation.authors[:_MAX_LISTED_AUTHORS]
    ]
    return pairs


def _pairs_0_1(citation: _Citation) -> list[tuple[str, str]]:
    """The OpenURL 0.1 description as encoded key/value pairs."""
    pairs = [("sid", _SID_0_1)]
    if citation.doi:
        pairs.append(("id", "doi:" + _kev_0_1(citation.doi)))
    if citation.pmid:
        pairs.append(("id", "pmid:" + _kev_0_1(citation.pmid)))
    fields = _metadata_fields(citation)
    pairs += [(_KEY_0_1.get(key, key), _kev_0_1(value)) for key, value in fields]
    return pairs


# 1.0 journal keys that 0.1 names differently (KEV Guidelines App. A.1).
_KEY_0_1 = {"jtitle": "title"}


def _metadata_fields(citation: _Citation) -> list[tuple[str, str]]:
    """Unencoded journal-format metadata, keyed by their 1.0 names."""
    fields = [("genre", "article")]
    details = citation.details
    optional = (
        ("atitle", citation.title),
        ("jtitle", citation.journal),
        ("issn", details.issn),
        ("eissn", details.eissn),
        ("date", citation.year),
        ("volume", details.volume),
        ("issue", details.issue),
        ("spage", details.spage),
        ("epage", details.epage),
    )
    fields += [(key, value) for key, value in optional if value]
    if citation.authors:
        last, first = _split_name(citation.authors[0])
        fields.append(("aulast", last))
        if first:
            fields.append(("aufirst", first))
    return fields


def _openurl_value(citation: _Citation) -> str | None:
    """``{openurl}``: an OpenURL 1.0 query string."""
    return _join(_pairs_1_0(citation)) if citation.citable else None


def _openurl_0_1_value(citation: _Citation) -> str | None:
    """``{openurl_0_1}``: an OpenURL 0.1 query string."""
    return _join(_pairs_0_1(citation)) if citation.citable else None


def _openurl_hybrid_value(citation: _Citation) -> str | None:
    """``{openurl_hybrid}``: 1.0 keys plus the 0.1 keys (KEV Guidelines A.2)."""
    if not citation.citable:
        return None
    return _join(_pairs_1_0(citation) + _pairs_0_1(citation))


_VALUES: dict[str, Callable[[_Citation], str | None]] = {
    "doi": _doi_value,
    "doi_url": _doi_url_value,
    "openurl": _openurl_value,
    "openurl_0_1": _openurl_0_1_value,
    "openurl_hybrid": _openurl_hybrid_value,
}

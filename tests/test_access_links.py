"""Tests for operator-configured access links (``_access_links``)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl

import pytest

from scholar_mcp._access_links import (
    DEFAULT_TEMPLATES,
    AccessLinkTemplate,
    build_access_links,
    parse_access_link_templates,
)

PAPER: dict[str, Any] = {
    "paperId": "p1",
    "title": "Quasiperiodicity in dissipative systems: a renormalization group analysis",
    "venue": "Physica D: Nonlinear Phenomena",
    "year": 1982,
    "authors": [{"name": "Mitchell J. Feigenbaum"}, {"name": "Leo P. Kadanoff"}],
    "externalIds": {"DOI": "10.1016/0167-2789(82)90030-6", "PubMed": "123"},
}

RESOLVER = "https://tno.on.worldcat.org/atoztitles/link?"


def _one(template: str, paper: dict[str, Any] | None = None) -> str:
    """Render one template against a paper and return its URL."""
    links = build_access_links(
        paper if paper is not None else PAPER,
        (AccessLinkTemplate(label="L", template=template),),
    )
    assert len(links) == 1, links
    return links[0]["url"]


def _query(url: str) -> list[tuple[str, str]]:
    """Return the decoded key/value pairs of a URL's query string."""
    return parse_qsl(url.split("?", 1)[1], keep_blank_values=True)


# ---------------------------------------------------------------------------
# parse_access_link_templates
# ---------------------------------------------------------------------------


def test_parse_none_and_blank_give_the_doi_default() -> None:
    """Unset or blank configuration falls back to the single doi.org link."""
    assert parse_access_link_templates(None) == DEFAULT_TEMPLATES
    assert parse_access_link_templates("   ") == DEFAULT_TEMPLATES
    assert (
        AccessLinkTemplate(label="Publisher (DOI)", template="https://doi.org/{doi}"),
    ) == DEFAULT_TEMPLATES


def test_parse_empty_list_turns_links_off() -> None:
    """An explicit empty list is the opt-out."""
    assert parse_access_link_templates("[]") == ()


def test_parse_keeps_configured_order() -> None:
    """Templates come back in the order the operator listed them."""
    raw = json.dumps(
        [
            {"label": "Full text", "template": RESOLVER + "{openurl}"},
            {"label": "Publisher", "template": "https://doi.org/{doi}"},
        ]
    )
    assert parse_access_link_templates(raw) == (
        AccessLinkTemplate("Full text", RESOLVER + "{openurl}"),
        AccessLinkTemplate("Publisher", "https://doi.org/{doi}"),
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "JSON"),
        ('{"label": "a", "template": "https://x/{doi}"}', "list"),
        ('["https://x/{doi}"]', "object"),
        ('[{"template": "https://x/{doi}"}]', "label"),
        ('[{"label": "a"}]', "template"),
        ('[{"label": " ", "template": "https://x/{doi}"}]', "label"),
        ('[{"label": "a", "template": "ftp://x/{doi}"}]', "http"),
        ('[{"label": "a", "template": "https://x/{isbn}"}]', "isbn"),
        ('[{"label": "a", "template": "https://x/{doi!r}"}]', "{doi!r}"),
        ('[{"label": "a", "template": "https://x/{doi:>9}"}]', "{doi:>9}"),
        ('[{"label": "a", "template": "https://x/{doi"}]', "brace"),
        ('[{"label": "a", "template": "https://x/{doi}", "extra": 1}]', "extra"),
    ],
    ids=[
        "not-json",
        "not-a-list",
        "entry-not-object",
        "missing-label",
        "missing-template",
        "blank-label",
        "not-http",
        "unknown-placeholder",
        "conversion",
        "format-spec",
        "unbalanced-brace",
        "unknown-key",
    ],
)
def test_parse_rejects_malformed_configuration(raw: str, message: str) -> None:
    """Each malformed configuration is refused with a message naming the fault."""
    with pytest.raises(
        ValueError, match=message.replace("{", r"\{").replace("}", r"\}")
    ):
        parse_access_link_templates(raw)


# ---------------------------------------------------------------------------
# {doi} and {doi_url}
# ---------------------------------------------------------------------------


def test_doi_placeholder_keeps_path_slashes() -> None:
    """``{doi}`` keeps the DOI's slash and parentheses for path-style resolvers."""
    assert _one("https://resolver.example/{doi}") == (
        "https://resolver.example/10.1016/0167-2789(82)90030-6"
    )


@pytest.mark.parametrize(
    ("doi", "encoded"),
    [
        ("10.1002/(SICI)1097-4636;2-#", "10.1002/(SICI)1097-4636%3B2-%23"),
        ("10.1000/a b?c&d=e", "10.1000/a%20b%3Fc%26d%3De"),
        ("10.1000/<x>", "10.1000/%3Cx%3E"),
    ],
    ids=["semicolon-hash", "query-delimiters", "angle-brackets"],
)
def test_doi_placeholder_escapes_url_delimiters(doi: str, encoded: str) -> None:
    """Characters that would end a path or split a query are percent-encoded."""
    paper = {**PAPER, "externalIds": {"DOI": doi}}
    assert _one("https://r.example/{doi}", paper) == f"https://r.example/{encoded}"


def test_doi_url_placeholder_is_fully_encoded_for_wrapping() -> None:
    """``{doi_url}`` can sit inside another URL's query, as a redirector needs."""
    url = _one("https://go.openathens.net/redirector/example.org?url={doi_url}")
    assert url == (
        "https://go.openathens.net/redirector/example.org?url="
        "https%3A%2F%2Fdoi.org%2F10.1016%2F0167-2789%2882%2990030-6"
    )
    assert _query(url) == [("url", "https://doi.org/10.1016/0167-2789(82)90030-6")]


def test_doi_templates_are_skipped_without_a_doi() -> None:
    """A template needing a DOI yields no link for a paper without one."""
    paper = {**PAPER, "externalIds": {"PubMed": "123"}}
    templates = (
        AccessLinkTemplate("doi", "https://r.example/{doi}"),
        AccessLinkTemplate("wrapped", "https://w.example/?url={doi_url}"),
        AccessLinkTemplate("resolver", RESOLVER + "{openurl}"),
    )
    links = build_access_links(paper, templates)
    assert [link["label"] for link in links] == ["resolver"]


def test_template_without_placeholders_is_kept_verbatim() -> None:
    """A fixed URL (a library home page) is passed through unchanged."""
    assert _one("https://library.example/") == "https://library.example/"


def test_literal_braces_are_unescaped() -> None:
    """Doubled braces render as single literal braces."""
    assert _one("https://r.example/{{x}}/{doi}").startswith("https://r.example/{x}/10.")


def test_doi_given_as_url_is_normalised() -> None:
    """A DOI recorded as a doi.org URL is reduced to the bare DOI."""
    paper = {**PAPER, "externalIds": {"DOI": "https://doi.org/10.1000/xyz"}}
    assert _one("https://r.example/{doi}", paper) == "https://r.example/10.1000/xyz"


# ---------------------------------------------------------------------------
# {openurl} — OpenURL 1.0 (Z39.88-2004 KEV, journal format)
# ---------------------------------------------------------------------------


def test_openurl_1_0_carries_the_required_and_referent_keys() -> None:
    """The 1.0 query is a KEV ContextObject with a journal-format referent."""
    pairs = _query(_one(RESOLVER + "{openurl}"))
    assert pairs[0] == ("url_ver", "Z39.88-2004")
    keys = dict(pairs)
    assert keys["url_ctx_fmt"] == "info:ofi/fmt:kev:mtx:ctx"
    assert keys["ctx_ver"] == "Z39.88-2004"
    assert keys["ctx_enc"] == "info:ofi/enc:UTF-8"
    assert keys["rfr_id"] == "info:sid/pvliesdonk.github.io:scholar-mcp"
    assert keys["rft_val_fmt"] == "info:ofi/fmt:kev:mtx:journal"
    assert keys["rft.genre"] == "article"
    assert keys["rft.atitle"] == PAPER["title"]
    assert keys["rft.jtitle"] == PAPER["venue"]
    assert keys["rft.date"] == "1982"
    assert keys["rft.aulast"] == "Feigenbaum"
    assert keys["rft.aufirst"] == "Mitchell J."
    assert [v for k, v in pairs if k == "rft_id"] == [
        "info:doi/10.1016/0167-2789(82)90030-6",
        "info:pmid/123",
    ]
    assert [v for k, v in pairs if k == "rft.au"] == [
        "Mitchell J. Feigenbaum",
        "Leo P. Kadanoff",
    ]
    assert "sid" not in keys
    assert "id" not in keys


def test_openurl_1_0_escapes_everything_but_the_kev_safe_set() -> None:
    """Values keep only alphanumerics and ``. - * _`` unescaped (Z39.88 §13.4)."""
    paper = {
        "title": "a~b (c): d/e",
        "externalIds": {"DOI": "10.1/x(y)"},
    }
    raw = _one(RESOLVER + "{openurl}", paper).split("?", 1)[1]
    assert "rft.atitle=a%7Eb%20%28c%29%3A%20d%2Fe" in raw.split("&")
    assert "rft_id=info%3Adoi%2F10.1%2Fx%28y%29" in raw.split("&")


def test_openurl_1_0_encodes_non_ascii_as_utf8() -> None:
    """Non-ASCII text is percent-encoded as UTF-8 bytes."""
    paper = {"title": "Ångström", "externalIds": {"DOI": "10.1/x"}}
    raw = _one(RESOLVER + "{openurl}", paper)
    assert "rft.atitle=%C3%85ngstr%C3%B6m" in raw


def test_openurl_omits_keys_the_paper_lacks() -> None:
    """Absent metadata produces no empty keys."""
    paper = {"title": "Only a title"}
    keys = dict(_query(_one(RESOLVER + "{openurl}", paper)))
    assert keys["rft.atitle"] == "Only a title"
    for absent in ("rft_id", "rft.jtitle", "rft.date", "rft.aulast", "rft.au"):
        assert absent not in keys


def test_openurl_caps_listed_authors() -> None:
    """At most five ``rft.au`` values keep long author lists out of the URL."""
    paper = {
        "title": "Big collaboration",
        "authors": [{"name": f"Author{i} Person{i}"} for i in range(40)],
    }
    pairs = _query(_one(RESOLVER + "{openurl}", paper))
    assert len([v for k, v in pairs if k == "rft.au"]) == 5


def test_single_word_author_name_is_a_surname() -> None:
    """A one-word author name is sent as the surname with no first name."""
    paper = {"title": "t", "authors": [{"name": "Plato"}]}
    keys = dict(_query(_one(RESOLVER + "{openurl}", paper)))
    assert keys["rft.aulast"] == "Plato"
    assert "rft.aufirst" not in keys


def test_openurl_templates_are_skipped_without_identifier_or_title() -> None:
    """A paper with neither a DOI, a PMID nor a title cannot form a citation."""
    links = build_access_links(
        {"paperId": "p", "year": 2000},
        (
            AccessLinkTemplate("v1", RESOLVER + "{openurl}"),
            AccessLinkTemplate("v01", RESOLVER + "{openurl_0_1}"),
            AccessLinkTemplate("hybrid", RESOLVER + "{openurl_hybrid}"),
        ),
    )
    assert links == []


# ---------------------------------------------------------------------------
# {openurl_0_1}
# ---------------------------------------------------------------------------


def test_openurl_0_1_uses_the_0_1_keys() -> None:
    """The 0.1 query uses unprefixed keys and ``id=namespace:identifier``."""
    pairs = _query(_one(RESOLVER + "{openurl_0_1}"))
    keys = dict(pairs)
    assert keys["sid"] == "scholarmcp:scholarmcp"
    assert keys["genre"] == "article"
    assert keys["atitle"] == PAPER["title"]
    assert keys["title"] == PAPER["venue"]
    assert keys["date"] == "1982"
    assert keys["aulast"] == "Feigenbaum"
    assert keys["aufirst"] == "Mitchell J."
    assert [v for k, v in pairs if k == "id"] == [
        "doi:10.1016/0167-2789(82)90030-6",
        "pmid:123",
    ]
    assert not any(k.startswith(("rft", "url_", "ctx_", "rfr")) for k, _ in pairs)


def test_openurl_0_1_keeps_the_rfc2396_unreserved_marks() -> None:
    """0.1 leaves ``( ) ! ~ * '`` unescaped and the ``id`` namespace colon intact."""
    raw = _one(RESOLVER + "{openurl_0_1}").split("?", 1)[1].split("&")
    assert "id=doi:10.1016%2F0167-2789(82)90030-6" in raw


# ---------------------------------------------------------------------------
# {openurl_hybrid}
# ---------------------------------------------------------------------------


def test_openurl_hybrid_carries_both_versions() -> None:
    """The hybrid query is a 1.0 query plus the 0.1 keys that differ."""
    pairs = _query(_one(RESOLVER + "{openurl_hybrid}"))
    keys = dict(pairs)
    assert pairs[0] == ("url_ver", "Z39.88-2004")
    assert keys["rft.atitle"] == PAPER["title"]
    assert keys["atitle"] == PAPER["title"]
    assert keys["rfr_id"] == "info:sid/pvliesdonk.github.io:scholar-mcp"
    assert keys["sid"] == "scholarmcp:scholarmcp"
    assert "info:doi/10.1016/0167-2789(82)90030-6" in [
        v for k, v in pairs if k == "rft_id"
    ]
    assert "doi:10.1016/0167-2789(82)90030-6" in [v for k, v in pairs if k == "id"]


# ---------------------------------------------------------------------------
# build_access_links
# ---------------------------------------------------------------------------


def test_links_follow_template_order_with_labels() -> None:
    """Links come back labelled, in the configured order."""
    templates = (
        AccessLinkTemplate("Full text", RESOLVER + "{openurl}"),
        AccessLinkTemplate("Publisher", "https://doi.org/{doi}"),
    )
    links = build_access_links(PAPER, templates)
    assert [link["label"] for link in links] == ["Full text", "Publisher"]
    assert links[1]["url"] == "https://doi.org/10.1016/0167-2789(82)90030-6"


def test_no_templates_give_no_links() -> None:
    """With nothing configured there is nothing to build."""
    assert build_access_links(PAPER, ()) == []

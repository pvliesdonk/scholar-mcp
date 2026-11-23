"""CrossRef book-chapter and parent-book works for the chapter-mapping tests.

Constructed, not captured: each record reproduces a shape that
``docs/design/reference/crossref-book-chapter-fields.md`` reports from the
live sample (DOIs and titles quoted there are reused; other values are
illustrative). Every getter returns a fresh deep copy.
"""

from __future__ import annotations

import copy
from typing import Any

# Springer series chapter: two container-title elements (series first, book
# last), an ISSN, the electronic ISBN listed first, an is-part-of link as a
# full doi.org URL, no editor on the chapter.
_SPRINGER_CHAPTER: dict[str, Any] = {
    "DOI": "10.1007/978-3-031-93275-5_2",
    "type": "book-chapter",
    "title": ["Heritage Trails and Local Economies"],
    "container-title": [
        "Advances in Science, Technology &amp; Innovation",
        "Cultural Heritage-Based Sustainable Tourism Approaches",
    ],
    "ISSN": ["2522-8714", "2522-8722"],
    "ISBN": ["9783031932755", "9783031932748"],
    "isbn-type": [
        {"value": "9783031932755", "type": "electronic"},
        {"value": "9783031932748", "type": "print"},
    ],
    "author": [{"given": "Ana", "family": "Silva", "sequence": "first"}],
    "page": "15-32",
    "publisher": "Springer Nature Switzerland",
    "publisher-location": "Cham",
    "relation": {
        "is-part-of": [
            {
                "id-type": "doi",
                "id": "https://doi.org/10.1007/978-3-031-93275-5",
                "asserted-by": "object",
            }
        ]
    },
    "subtitle": [],
    "issued": {"date-parts": [[2025]]},
}

# The parent book of the Springer chapter: an edited-book carrying the
# editors the chapter record leaves out, plus a subtitle.
_SPRINGER_PARENT: dict[str, Any] = {
    "DOI": "10.1007/978-3-031-93275-5",
    "type": "edited-book",
    "title": ["Cultural Heritage-Based Sustainable Tourism Approaches"],
    "subtitle": ["Case Studies from the Mediterranean"],
    "editor": [
        {
            "given": "Maria",
            "family": "Rossi",
            "sequence": "first",
            "role": [{"vocabulary": "crossref", "role": "editor"}],
        },
        {
            "given": "Jan",
            "family": "de Vries",
            "sequence": "additional",
            "role": [{"vocabulary": "crossref", "role": "editor"}],
        },
    ],
    "ISBN": ["9783031932755", "9783031932748"],
    "isbn-type": [
        {"value": "9783031932755", "type": "electronic"},
        {"value": "9783031932748", "type": "print"},
    ],
    "publisher": "Springer Nature Switzerland",
    "edition-number": "1",
}

# Elsevier chapter: no relation.is-part-of at all, ISBN present, no
# publisher-location.
_ELSEVIER_CHAPTER: dict[str, Any] = {
    "DOI": "10.1016/b978-0-12-373947-6.00001-2",
    "type": "book-chapter",
    "title": ["Introduction"],
    "container-title": ["Encyclopedia of Applied Examples"],
    "ISBN": ["9780123739476"],
    "isbn-type": [{"value": "9780123739476", "type": "print"}],
    "page": "639-650.e3",
    "publisher": "Elsevier",
    "relation": {},
}

# Cambridge chapter: editor on the chapter itself, an escaped tag in the
# container title, a roman-numeral page range and an edition number.
_CAMBRIDGE_CHAPTER: dict[str, Any] = {
    "DOI": "10.1017/cbo9781139199100.007",
    "type": "book-chapter",
    "title": ["Preface"],
    "container-title": ["Studies in &lt;I&gt;Ancient&lt;/I&gt;  Law"],
    "editor": [{"given": "Helen", "family": "Clark", "sequence": "first"}],
    "ISBN": ["9781139199100"],
    "isbn-type": [{"value": "9781139199100", "type": "electronic"}],
    "page": "xiii-xiii",
    "publisher": "Cambridge University Press",
    "edition-number": "2",
    "relation": {
        "is-part-of": [
            {
                "id-type": "doi",
                "id": "https://doi.org/10.1017/cbo9781139199100",
                "asserted-by": "object",
            }
        ]
    },
}

# The Cambridge chapter's parent book, which also lists an editor: the
# chapter's own editor must win.
_CAMBRIDGE_PARENT: dict[str, Any] = {
    "DOI": "10.1017/cbo9781139199100",
    "type": "edited-book",
    "title": ["Studies in Ancient Law"],
    "editor": [{"given": "Someone", "family": "Else", "sequence": "first"}],
    "publisher": "Cambridge University Press",
}

# IEEE chapter: no page, no author, a single container title.
_IEEE_CHAPTER: dict[str, Any] = {
    "DOI": "10.1109/9781119000000.ch3",
    "type": "book-chapter",
    "title": ["Channel Models"],
    "container-title": ["Wireless Systems Handbook"],
    "ISBN": ["9781119000006"],
    "isbn-type": [{"value": "9781119000006", "type": "print"}],
    "publisher": "IEEE",
    "relation": {
        "is-part-of": [
            {
                "id-type": "doi",
                "id": "https://doi.org/10.1109/9781119000000",
                "asserted-by": "object",
            }
        ]
    },
}


def springer_chapter() -> dict[str, Any]:
    """Return the Springer series chapter."""
    return copy.deepcopy(_SPRINGER_CHAPTER)


def springer_parent() -> dict[str, Any]:
    """Return the Springer chapter's parent book."""
    return copy.deepcopy(_SPRINGER_PARENT)


def elsevier_chapter() -> dict[str, Any]:
    """Return the Elsevier chapter without an is-part-of link."""
    return copy.deepcopy(_ELSEVIER_CHAPTER)


def cambridge_chapter() -> dict[str, Any]:
    """Return the Cambridge chapter that carries its own editor."""
    return copy.deepcopy(_CAMBRIDGE_CHAPTER)


def cambridge_parent() -> dict[str, Any]:
    """Return the Cambridge chapter's parent book."""
    return copy.deepcopy(_CAMBRIDGE_PARENT)


def ieee_chapter() -> dict[str, Any]:
    """Return the IEEE chapter without page or author."""
    return copy.deepcopy(_IEEE_CHAPTER)

"""Patent records shared by the citation tests.

Modelled on EP3491801B1: the publication number and the applicant and
inventor spellings are the ones EPO supplies for it; the title, abstract,
dates, family id and classification are illustrative stand-ins.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scholar_mcp._record_types import PatentRecord

_EP3491801B1: PatentRecord = {
    "title": "Method and system for secure key management",
    "abstract": "A key is derived & stored.",
    "applicants": {
        "original": ["Koninklijke Philips N.V."],
        "standardised": ["KONINKLIJKE PHILIPS NV [NL]"],
    },
    "inventors": {
        "original": ["PLETEA, Daniel", "VAN LIESDONK, Peter, Petrus"],
        "standardised": ["PLETEA DANIEL"],
    },
    "publication_number": "EP.3491801.B1",
    "publication_date": "2020-09-02",
    "filing_date": "2017-07-20",
    "priority_date": "2016-07-28",
    "family_id": "56557568",
    "classifications": ["H04L9/08"],
    "url": "https://worldwide.espacenet.com/patent/search?q=pn%3DEP3491801B1",
}


def ep3491801b1() -> PatentRecord:
    """Return a fresh copy of the EP3491801B1 record.

    Returns:
        A deep copy, so a test may change it freely.
    """
    return copy.deepcopy(_EP3491801B1)

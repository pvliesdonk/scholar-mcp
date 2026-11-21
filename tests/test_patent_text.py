"""Markdown for patent claims and descriptions (#44).

The OPS shapes these cover are in docs/design/reference/epo-ops-fulltext.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scholar_mcp._epo_xml import parse_claims_xml, parse_description_xml
from scholar_mcp._patent_text import claims_markdown, description_markdown

_EPO_FIXTURES = Path(__file__).parent / "fixtures" / "epo"


def _claim_numbers(markdown: str) -> list[int]:
    return [int(m) for m in re.findall(r"(?m)^(\d+)\. ", markdown)]


@pytest.mark.parametrize(
    ("fixture", "count"),
    [("claims_ep3491801b1.xml", 10), ("claims_wo2018019652a1.xml", 14)],
)
def test_real_claim_sets_split_into_numbered_claims(fixture: str, count: int) -> None:
    """EP rejoins continued claim-texts; WO splits its single block."""
    markdown = parse_claims_xml((_EPO_FIXTURES / fixture).read_bytes())
    blocks = markdown.split("\n\n")
    assert _claim_numbers(markdown) == list(range(1, count + 1))
    assert len(blocks) == count
    assert all(re.match(r"\d+\. ", b) for b in blocks)


def test_ep_continuation_stays_with_its_claim() -> None:
    markdown = parse_claims_xml((_EPO_FIXTURES / "claims_ep3491801b1.xml").read_bytes())
    claim5 = next(b for b in markdown.split("\n\n") if b.startswith("5. "))
    assert "encrypting (608) a return message" in claim5


def test_wo_claims_numbered_mid_line_and_ocr_spaced() -> None:
    """Claims 3 and 4 start mid-line; claim 13 is OCR'd as '1 3.'."""
    markdown = parse_claims_xml(
        (_EPO_FIXTURES / "claims_wo2018019652a1.xml").read_bytes()
    )
    assert "\n\n3. Method according to claim 1 , wherein" in markdown
    assert "\n\n13. System comprising" in markdown
    assert not markdown.startswith("CLAIMS")


def test_claim_reference_is_not_a_claim_start() -> None:
    texts = ["1. A method.", "2. The method according to claim 1. Further."]
    assert claims_markdown(texts) == (
        "1. A method.\n\n2. The method according to claim 1. Further."
    )


def test_text_before_the_first_claim_is_kept() -> None:
    assert claims_markdown(["What is claimed is:", "1. A method."]) == (
        "What is claimed is:\n\n1. A method."
    )


def test_claims_without_numbers_are_kept() -> None:
    assert claims_markdown(["A method.", "A device."]) == "A method.\nA device."


def test_empty_claims() -> None:
    assert claims_markdown([]) == ""
    assert claims_markdown(["  "]) == ""


def test_real_ep_description_headings_and_numbers() -> None:
    markdown = parse_description_xml(
        (_EPO_FIXTURES / "description_ep3491801b1.xml").read_bytes()
    )
    headings = [b for b in markdown.split("\n\n") if b.startswith("## ")]
    assert headings == [
        "## TECHNICAL FIELD",
        "## BACKGROUND",
        "## SUMMARY OF THE INVENTION",
        "## BRIEF DESCRIPTION OF THE DRAWINGS",
        "## DETAILED DESCRIPTION",
    ]
    assert "\n\n[0001] Various embodiments" in markdown
    assert "  " not in markdown


@pytest.mark.parametrize(
    ("paragraph", "heading"),
    [
        ("TECHNICAL FIELD", True),
        ("BRIEF DESCRIPTION OF THE DRAWINGS", True),
        ("THE INVENTION IS DESCRIBED.", False),  # a sentence
        ("[0001] SHORT", False),  # a numbered paragraph
        ("Method and device for transmission of a video", False),  # mixed case
        ("B(t- l ) B(t)", False),
        ("OK", False),  # too few letters
        ("A" * 81, False),  # too long
    ],
)
def test_heading_detection(paragraph: str, heading: bool) -> None:
    assert description_markdown([paragraph]).startswith("## ") is heading


def test_description_squeezes_space_runs() -> None:
    assert description_markdown(["[0002]    Reference to  US 1  here.", " "]) == (
        "[0002] Reference to US 1 here."
    )

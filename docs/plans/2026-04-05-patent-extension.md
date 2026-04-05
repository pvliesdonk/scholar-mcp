# Patent Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add patent search capabilities via EPO Open Patent Services, with 3 new tools (`search_patents`, `get_patent`, `get_citing_patents`) and extended `batch_resolve`.

**Architecture:** Flat module addition following existing patterns. New `_epo_client.py` wraps `python-epo-ops-client` (sync library, called via `asyncio.to_thread()`). XML parsing in separate `_epo_xml.py`. Patent tools in `_tools_patent.py` with conditional registration when EPO credentials are configured. Cross-referencing resolves patent NPL citations to Semantic Scholar papers.

**Tech Stack:** python-epo-ops-client (EPO OAuth2 + transport), lxml (XML parsing), existing aiosqlite cache, existing FastMCP tool patterns.

**Spec:** `docs/specs/2026-04-05-patent-extension-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/scholar_mcp/_patent_numbers.py` | `DocdbNumber` dataclass, `normalize()`, `is_patent_number()` |
| `src/scholar_mcp/_epo_xml.py` | All XML parsers for EPO OPS responses |
| `src/scholar_mcp/_epo_client.py` | `EpoClient` wrapping `python-epo-ops-client` |
| `src/scholar_mcp/_tools_patent.py` | `register_patent_tools()` with `search_patents`, `get_patent`, `get_citing_patents` |
| `tests/test_patent_numbers.py` | Tests for patent number normalization |
| `tests/test_epo_xml.py` | Tests for XML parsers |
| `tests/test_epo_client.py` | Tests for EpoClient (mocked epo_ops.Client) |
| `tests/test_tools_patent.py` | Tests for patent MCP tools |

### Modified Files
| File | Change |
|------|--------|
| `pyproject.toml` | Add `python-epo-ops-client`, `lxml` to deps |
| `src/scholar_mcp/config.py` | Add `epo_consumer_key`, `epo_consumer_secret` to `ServerConfig` |
| `src/scholar_mcp/_cache.py` | Add patent tables (6 new tables) |
| `src/scholar_mcp/_server_deps.py` | Add `epo: EpoClient \| None` to `ServiceBundle`, create in lifespan |
| `src/scholar_mcp/_server_tools.py` | Import and call `register_patent_tools()` |
| `src/scholar_mcp/_tools_utility.py` | Extend `batch_resolve` with patent number support |
| `tests/conftest.py` | Add `epo=None` to bundle fixture |
| `docs/tools/index.md` | Add patent tool documentation |
| `docs/configuration.md` | Add EPO env var documentation |
| `README.md` | Add patent capabilities section |

---

## Phase 1 — Foundation

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add python-epo-ops-client and lxml to project dependencies**

In `pyproject.toml`, add to the `[project.dependencies]` list:

```toml
dependencies = [
    "httpx",
    "aiosqlite",
    "click>=8.0",
    "python-epo-ops-client>=4.2",
    "lxml>=5.0",
]
```

- [ ] **Step 2: Install and verify**

Run: `uv sync --all-extras`
Expected: packages install successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add python-epo-ops-client and lxml dependencies"
```

---

### Task 2: Patent Number Normalization

**Files:**
- Create: `src/scholar_mcp/_patent_numbers.py`
- Create: `tests/test_patent_numbers.py`

- [ ] **Step 1: Write tests for DocdbNumber, normalize(), and is_patent_number()**

```python
"""Tests for patent number normalization."""

from __future__ import annotations

import pytest

from scholar_mcp._patent_numbers import DocdbNumber, is_patent_number, normalize


class TestDocdbNumber:
    def test_docdb_property(self) -> None:
        d = DocdbNumber(country="EP", number="1234567", kind="A1")
        assert d.docdb == "EP.1234567.A1"

    def test_str(self) -> None:
        d = DocdbNumber(country="EP", number="1234567", kind="A1")
        assert str(d) == "EP.1234567.A1"

    def test_equality(self) -> None:
        a = DocdbNumber(country="EP", number="1234567", kind="A1")
        b = DocdbNumber(country="EP", number="1234567", kind="A1")
        assert a == b


class TestNormalize:
    def test_ep_no_spaces(self) -> None:
        assert normalize("EP1234567A1") == DocdbNumber("EP", "1234567", "A1")

    def test_ep_with_spaces(self) -> None:
        assert normalize("EP 1234567 A1") == DocdbNumber("EP", "1234567", "A1")

    def test_ep_no_kind(self) -> None:
        # When no kind code is provided, kind should be empty string
        result = normalize("EP1234567")
        assert result.country == "EP"
        assert result.number == "1234567"
        assert result.kind == ""

    def test_wo_with_slash(self) -> None:
        assert normalize("WO2024/123456A1") == DocdbNumber("WO", "2024123456", "A1")

    def test_wo_without_slash(self) -> None:
        assert normalize("WO2024123456") == DocdbNumber("WO", "2024123456", "")

    def test_us_with_commas(self) -> None:
        assert normalize("US11,234,567B2") == DocdbNumber("US", "11234567", "B2")

    def test_us_no_commas(self) -> None:
        assert normalize("US11234567B2") == DocdbNumber("US", "11234567", "B2")

    def test_docdb_format_passthrough(self) -> None:
        assert normalize("EP.1234567.A1") == DocdbNumber("EP", "1234567", "A1")

    def test_lowercase_country(self) -> None:
        assert normalize("ep1234567A1") == DocdbNumber("EP", "1234567", "A1")

    def test_invalid_no_country(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize("1234567")

    def test_invalid_empty(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize("")

    def test_invalid_no_digits(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize("EPABCDEF")


class TestIsPatentNumber:
    def test_ep_patent(self) -> None:
        assert is_patent_number("EP1234567A1") is True

    def test_wo_patent(self) -> None:
        assert is_patent_number("WO2024123456") is True

    def test_us_patent(self) -> None:
        assert is_patent_number("US11234567B2") is True

    def test_doi(self) -> None:
        assert is_patent_number("10.1234/abc") is False

    def test_s2_id(self) -> None:
        assert is_patent_number("abc123def456") is False

    def test_arxiv_id(self) -> None:
        assert is_patent_number("2301.12345") is False

    def test_doi_prefix(self) -> None:
        assert is_patent_number("DOI:10.1234/abc") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_patent_numbers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scholar_mcp._patent_numbers'`

- [ ] **Step 3: Implement _patent_numbers.py**

```python
"""Patent number normalization and detection.

Converts various patent number formats to DOCDB format (CC.number.kind)
for use as EPO OPS API inputs and cache keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches: optional CC, digits (with optional commas/slashes), optional kind
# Examples: EP1234567A1, EP 1234567 A1, WO2024/123456, US11,234,567B2
_PATENT_RE = re.compile(
    r"^(?P<country>[A-Za-z]{2})"  # 2-letter country code
    r"[\s.]*"  # optional separator
    r"(?P<number>[\d,/]+)"  # digits with optional commas/slashes
    r"[\s.]*"  # optional separator
    r"(?P<kind>[A-Za-z]\d{0,2})?$"  # optional kind code (e.g., A1, B2)
)

# Known patent country codes (subset — covers major offices)
_PATENT_COUNTRIES = frozenset({
    "EP", "WO", "US", "JP", "CN", "KR", "DE", "FR", "GB", "CA", "AU",
    "IN", "BR", "RU", "TW", "IL", "NZ", "SG", "HK", "AT", "BE", "CH",
    "CZ", "DK", "ES", "FI", "GR", "HU", "IE", "IT", "LU", "NL", "NO",
    "PL", "PT", "SE", "SK", "TR",
})


@dataclass(frozen=True)
class DocdbNumber:
    """A patent number in DOCDB format (country.number.kind)."""

    country: str
    number: str
    kind: str

    @property
    def docdb(self) -> str:
        """DOCDB format string: CC.number.kind."""
        if self.kind:
            return f"{self.country}.{self.number}.{self.kind}"
        return f"{self.country}.{self.number}."

    def __str__(self) -> str:
        return self.docdb


def normalize(raw: str) -> DocdbNumber:
    """Parse a patent number string into DOCDB format.

    Args:
        raw: Patent number in any common format (EP1234567A1,
            EP 1234567 A1, WO2024/123456, US11,234,567B2, etc.)

    Returns:
        DocdbNumber with normalized country, number, and kind.

    Raises:
        ValueError: If the string cannot be parsed as a patent number.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Cannot parse empty string as patent number")

    m = _PATENT_RE.match(raw)
    if m is None:
        raise ValueError(f"Cannot parse patent number: {raw!r}")

    country = m.group("country").upper()
    number = m.group("number").replace(",", "").replace("/", "")
    kind = m.group("kind") or ""

    return DocdbNumber(country=country, number=number, kind=kind)


def is_patent_number(raw: str) -> bool:
    """Heuristic check for whether a string looks like a patent number.

    Used by batch_resolve for auto-detection. Returns True if the string
    starts with a known patent country code followed by digits.

    Args:
        raw: Identifier string to check.

    Returns:
        True if the string appears to be a patent number.
    """
    raw = raw.strip()
    if len(raw) < 4:
        return False
    prefix = raw[:2].upper()
    if prefix not in _PATENT_COUNTRIES:
        return False
    # Must have a digit following the country code (after optional space/dot)
    rest = raw[2:].lstrip(" .")
    return len(rest) > 0 and rest[0].isdigit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_patent_numbers.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/scholar_mcp/_patent_numbers.py tests/test_patent_numbers.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_patent_numbers.py tests/test_patent_numbers.py
git commit -m "feat: add patent number normalization and detection"
```

---

### Task 3: EPO XML Biblio Parser

**Files:**
- Create: `src/scholar_mcp/_epo_xml.py`
- Create: `tests/test_epo_xml.py`

- [ ] **Step 1: Write tests for parse_biblio_xml**

```python
"""Tests for EPO OPS XML parsers."""

from __future__ import annotations

import pytest

from scholar_mcp._epo_xml import parse_biblio_xml

# Realistic EPO OPS biblio XML fixture
BIBLIO_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document system="ops.epo.org" country="EP" doc-number="1234567"
        kind="A1" family-id="54321">
      <bibliographic-data>
        <publication-reference>
          <document-id document-id-type="docdb">
            <country>EP</country>
            <doc-number>1234567</doc-number>
            <kind>A1</kind>
            <date>20200115</date>
          </document-id>
        </publication-reference>
        <application-reference doc-id="12345678">
          <document-id document-id-type="docdb">
            <country>EP</country>
            <doc-number>19123456</doc-number>
            <kind>A</kind>
            <date>20190501</date>
          </document-id>
        </application-reference>
        <priority-claims>
          <priority-claim sequence="1" kind="national">
            <document-id document-id-type="docdb">
              <country>US</country>
              <doc-number>16123456</doc-number>
              <date>20180601</date>
            </document-id>
          </priority-claim>
        </priority-claims>
        <parties>
          <applicants>
            <applicant data-format="docdb" sequence="1">
              <applicant-name><name>ACME CORP</name></applicant-name>
            </applicant>
          </applicants>
          <inventors>
            <inventor data-format="docdb" sequence="1">
              <inventor-name><name>SMITH, JOHN</name></inventor-name>
            </inventor>
            <inventor data-format="docdb" sequence="2">
              <inventor-name><name>DOE, JANE</name></inventor-name>
            </inventor>
          </inventors>
        </parties>
        <invention-title lang="en">Method for improved widget processing</invention-title>
        <invention-title lang="de">Verfahren zur verbesserten Widget-Verarbeitung</invention-title>
        <abstract lang="en">
          <p>A method for processing widgets with improved efficiency.</p>
        </abstract>
        <patent-classifications>
          <patent-classification>
            <classification-scheme office="EP" scheme="cpci"/>
            <section>H</section>
            <class>04</class>
            <subclass>L</subclass>
            <main-group>29</main-group>
            <subgroup>06</subgroup>
          </patent-classification>
        </patent-classifications>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""


class TestParseBiblioXml:
    def test_basic_fields(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert result["title"] == "Method for improved widget processing"
        assert result["abstract"] == "A method for processing widgets with improved efficiency."
        assert result["publication_number"] == "EP.1234567.A1"
        assert result["publication_date"] == "2020-01-15"
        assert result["family_id"] == "54321"

    def test_applicants(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert result["applicants"] == ["ACME CORP"]

    def test_inventors(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert result["inventors"] == ["SMITH, JOHN", "DOE, JANE"]

    def test_filing_date(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert result["filing_date"] == "2019-05-01"

    def test_priority_date(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert result["priority_date"] == "2018-06-01"

    def test_classifications(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert "H04L29/06" in result["classifications"]

    def test_url(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML)
        assert "EP1234567" in result["url"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_xml.py::TestParseBiblioXml -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scholar_mcp._epo_xml'`

- [ ] **Step 3: Implement parse_biblio_xml in _epo_xml.py**

```python
"""XML parsers for EPO OPS API responses.

Each parser extracts structured data from EPO's namespaced XML into
plain Python dicts. All XML handling is contained here — consumers
only see clean data.
"""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)

# EPO OPS XML namespaces
_NS = {
    "ops": "http://ops.epo.org",
    "exch": "http://www.epo.org/exchange",
}


def _text(el: etree._Element | None) -> str:
    """Extract text content from an element, or empty string if None."""
    if el is None:
        return ""
    return (el.text or "").strip()


def _date_fmt(raw: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD, or return as-is if wrong length."""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def _find_docdb_id(
    parent: etree._Element, ref_tag: str
) -> dict[str, str]:
    """Extract country, number, kind, date from a docdb document-id."""
    ref = parent.find(f"exch:{ref_tag}", _NS)
    if ref is None:
        return {}
    doc_id = ref.find("exch:document-id[@document-id-type='docdb']", _NS)
    if doc_id is None:
        return {}
    return {
        "country": _text(doc_id.find("exch:country", _NS)),
        "number": _text(doc_id.find("exch:doc-number", _NS)),
        "kind": _text(doc_id.find("exch:kind", _NS)),
        "date": _date_fmt(_text(doc_id.find("exch:date", _NS))),
    }


def parse_biblio_xml(xml_data: bytes) -> dict[str, Any]:
    """Parse EPO OPS biblio response into a patent record dict.

    Args:
        xml_data: Raw XML bytes from the published-data/biblio endpoint.

    Returns:
        Dict with keys: title, abstract, applicants, inventors,
        publication_number, publication_date, filing_date, priority_date,
        family_id, classifications, url.
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    doc = root.find(".//exch:exchange-document", _NS)
    if doc is None:
        return {"error": "no exchange-document found in response"}

    bib = doc.find("exch:bibliographic-data", _NS)
    if bib is None:
        return {"error": "no bibliographic-data found"}

    # Publication reference
    pub = _find_docdb_id(bib, "publication-reference")
    pub_number = f"{pub.get('country', '')}.{pub.get('number', '')}.{pub.get('kind', '')}"
    pub_date = pub.get("date", "")

    # Application reference (filing date)
    app = _find_docdb_id(bib, "application-reference")
    filing_date = app.get("date", "")

    # Priority date (earliest priority claim)
    priority_date = ""
    prio_claims = bib.find("exch:priority-claims", _NS)
    if prio_claims is not None:
        first_prio = prio_claims.find("exch:priority-claim", _NS)
        if first_prio is not None:
            prio_id = first_prio.find(
                "exch:document-id[@document-id-type='docdb']", _NS
            )
            if prio_id is None:
                prio_id = first_prio.find("exch:document-id", _NS)
            if prio_id is not None:
                priority_date = _date_fmt(
                    _text(prio_id.find("exch:date", _NS))
                )

    # Title (prefer English)
    title = ""
    for t_el in bib.findall("exch:invention-title", _NS):
        lang = t_el.get("lang", "")
        if lang == "en" or not title:
            title = _text(t_el)

    # Abstract (prefer English)
    abstract = ""
    for abs_el in bib.findall("exch:abstract", _NS):
        lang = abs_el.get("lang", "")
        paragraphs = [_text(p) for p in abs_el.findall("exch:p", _NS)]
        text = " ".join(p for p in paragraphs if p)
        if lang == "en" or not abstract:
            abstract = text

    # Parties
    applicants: list[str] = []
    inventors: list[str] = []
    parties = bib.find("exch:parties", _NS)
    if parties is not None:
        for app_el in parties.findall(
            "exch:applicants/exch:applicant/exch:applicant-name/exch:name",
            _NS,
        ):
            name = _text(app_el)
            if name:
                applicants.append(name)
        for inv_el in parties.findall(
            "exch:inventors/exch:inventor/exch:inventor-name/exch:name",
            _NS,
        ):
            name = _text(inv_el)
            if name:
                inventors.append(name)

    # CPC classifications
    classifications: list[str] = []
    for pc in bib.findall(
        "exch:patent-classifications/exch:patent-classification", _NS
    ):
        section = _text(pc.find("exch:section", _NS))
        cls = _text(pc.find("exch:class", _NS))
        subcls = _text(pc.find("exch:subclass", _NS))
        main_group = _text(pc.find("exch:main-group", _NS))
        subgroup = _text(pc.find("exch:subgroup", _NS))
        if section and cls and subcls:
            code = f"{section}{cls}{subcls}{main_group}/{subgroup}"
            classifications.append(code)

    # Family ID from exchange-document attributes
    family_id = doc.get("family-id", "")

    # URL to Espacenet
    country = pub.get("country", "")
    number = pub.get("number", "")
    kind = pub.get("kind", "")
    url = f"https://worldwide.espacenet.com/patent/search?q=pn%3D{country}{number}{kind}"

    return {
        "title": title,
        "abstract": abstract,
        "applicants": applicants,
        "inventors": inventors,
        "publication_number": pub_number,
        "publication_date": pub_date,
        "filing_date": filing_date,
        "priority_date": priority_date,
        "family_id": family_id,
        "classifications": classifications,
        "url": url,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_xml.py::TestParseBiblioXml -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/scholar_mcp/_epo_xml.py tests/test_epo_xml.py`

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_epo_xml.py tests/test_epo_xml.py
git commit -m "feat: add EPO XML biblio parser"
```

---

### Task 4: EPO XML Search Results Parser

**Files:**
- Modify: `src/scholar_mcp/_epo_xml.py`
- Modify: `tests/test_epo_xml.py`

- [ ] **Step 1: Add tests for parse_search_xml**

Append to `tests/test_epo_xml.py`:

```python
from scholar_mcp._epo_xml import parse_search_xml

SEARCH_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="42">
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country>
          <doc-number>1234567</doc-number>
          <kind>A1</kind>
        </document-id>
      </ops:publication-reference>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>WO</country>
          <doc-number>2024001234</doc-number>
          <kind>A1</kind>
        </document-id>
      </ops:publication-reference>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>"""

SEARCH_XML_EMPTY = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="0">
    <ops:search-result/>
  </ops:biblio-search>
</ops:world-patent-data>"""


class TestParseSearchXml:
    def test_result_count(self) -> None:
        result = parse_search_xml(SEARCH_XML)
        assert result["total_count"] == 42

    def test_references(self) -> None:
        result = parse_search_xml(SEARCH_XML)
        refs = result["references"]
        assert len(refs) == 2
        assert refs[0] == {"country": "EP", "number": "1234567", "kind": "A1"}
        assert refs[1] == {"country": "WO", "number": "2024001234", "kind": "A1"}

    def test_empty_results(self) -> None:
        result = parse_search_xml(SEARCH_XML_EMPTY)
        assert result["total_count"] == 0
        assert result["references"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_xml.py::TestParseSearchXml -v`
Expected: FAIL — `ImportError: cannot import name 'parse_search_xml'`

- [ ] **Step 3: Add parse_search_xml to _epo_xml.py**

Append to `src/scholar_mcp/_epo_xml.py`:

```python
def parse_search_xml(xml_data: bytes) -> dict[str, Any]:
    """Parse EPO OPS search response into result references.

    Args:
        xml_data: Raw XML bytes from the published-data/search endpoint.

    Returns:
        Dict with keys: total_count (int), references (list of dicts
        with country, number, kind).
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    search = root.find(".//ops:biblio-search", _NS)
    total = int(search.get("total-result-count", "0")) if search is not None else 0

    references: list[dict[str, str]] = []
    if search is not None:
        for pub_ref in search.findall(
            "ops:search-result/ops:publication-reference", _NS
        ):
            doc_id = pub_ref.find(
                "exch:document-id[@document-id-type='docdb']", _NS
            )
            if doc_id is None:
                continue
            references.append({
                "country": _text(doc_id.find("exch:country", _NS)),
                "number": _text(doc_id.find("exch:doc-number", _NS)),
                "kind": _text(doc_id.find("exch:kind", _NS)),
            })

    return {"total_count": total, "references": references}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_xml.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_epo_xml.py tests/test_epo_xml.py
git commit -m "feat: add EPO XML search results parser"
```

---

### Task 5: Configuration — EPO Environment Variables

**Files:**
- Modify: `src/scholar_mcp/config.py`
- Modify: `tests/test_config.py` (or create if not exists)

- [ ] **Step 1: Write tests for EPO config loading**

Add to the config test file:

```python
"""Tests for EPO config fields."""

import os

from scholar_mcp.config import load_config


def test_epo_keys_default_none(monkeypatch) -> None:
    """EPO keys are None when env vars not set."""
    for key in list(os.environ):
        if key.startswith("SCHOLAR_MCP_"):
            monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.epo_consumer_key is None
    assert config.epo_consumer_secret is None


def test_epo_keys_from_env(monkeypatch) -> None:
    """EPO keys loaded from environment."""
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "test-secret")
    config = load_config()
    assert config.epo_consumer_key == "test-key"
    assert config.epo_consumer_secret == "test-secret"


def test_epo_configured_both_set(monkeypatch) -> None:
    """epo_configured is True only when both key and secret are set."""
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "key")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "secret")
    config = load_config()
    assert config.epo_configured is True


def test_epo_configured_partial(monkeypatch) -> None:
    """epo_configured is False when only one credential is set."""
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "key")
    for key in list(os.environ):
        if key == "SCHOLAR_MCP_EPO_CONSUMER_SECRET":
            monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.epo_configured is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ -k "test_epo" -v`
Expected: FAIL — `AttributeError: 'ServerConfig' object has no attribute 'epo_consumer_key'`

- [ ] **Step 3: Add EPO fields to ServerConfig and load_config**

In `src/scholar_mcp/config.py`, add to `ServerConfig`:

```python
epo_consumer_key: str | None = None
epo_consumer_secret: str | None = None

@property
def epo_configured(self) -> bool:
    """True when both EPO OPS credentials are set."""
    return self.epo_consumer_key is not None and self.epo_consumer_secret is not None
```

In `load_config()`, add:

```python
epo_consumer_key=_str("EPO_CONSUMER_KEY"),
epo_consumer_secret=_str("EPO_CONSUMER_SECRET"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ -k "test_epo" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/config.py tests/
git commit -m "feat: add EPO OPS credential configuration"
```

---

### Task 6: EPO OPS Client

**Files:**
- Create: `src/scholar_mcp/_epo_client.py`
- Create: `tests/test_epo_client.py`

- [ ] **Step 1: Write tests for EpoClient**

The `EpoClient` wraps the sync `epo_ops.Client`. Tests mock the underlying library at the method level using `unittest.mock.patch`.

```python
"""Tests for the EPO OPS client wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
from scholar_mcp._epo_xml import BIBLIO_XML as _  # noqa: F401 (verify import works)
from scholar_mcp._patent_numbers import DocdbNumber

# Minimal biblio XML for client tests (parsing tested separately in test_epo_xml)
_BIBLIO_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document system="ops.epo.org" country="EP" doc-number="1234567"
        kind="A1" family-id="54321">
      <bibliographic-data>
        <publication-reference>
          <document-id document-id-type="docdb">
            <country>EP</country>
            <doc-number>1234567</doc-number>
            <kind>A1</kind>
            <date>20200115</date>
          </document-id>
        </publication-reference>
        <invention-title lang="en">Test Patent</invention-title>
        <abstract lang="en"><p>Test abstract.</p></abstract>
        <parties>
          <applicants>
            <applicant data-format="docdb" sequence="1">
              <applicant-name><name>TEST CORP</name></applicant-name>
            </applicant>
          </applicants>
          <inventors/>
        </parties>
        <patent-classifications/>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

_SEARCH_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="1">
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country>
          <doc-number>1234567</doc-number>
          <kind>A1</kind>
        </document-id>
      </ops:publication-reference>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>"""


def _mock_response(
    content: bytes,
    status_code: int = 200,
    throttle: str = "green",
) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.content = content
    resp.status_code = status_code
    resp.headers = {
        "X-Throttling-Control": f"{throttle} (search={throttle}:30)"
    }
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


@pytest.fixture
def mock_epo_ops() -> MagicMock:
    """A mocked epo_ops.Client."""
    client = MagicMock()
    client.published_data_search = MagicMock(
        return_value=_mock_response(_SEARCH_RESPONSE_XML)
    )
    client.published_data = MagicMock(
        return_value=_mock_response(_BIBLIO_RESPONSE_XML)
    )
    return client


@pytest.fixture
def epo_client(mock_epo_ops: MagicMock) -> EpoClient:
    return EpoClient(
        consumer_key="test", consumer_secret="test", _client=mock_epo_ops
    )


class TestEpoClientSearch:
    async def test_search_returns_parsed_results(
        self, epo_client: EpoClient
    ) -> None:
        result = await epo_client.search("ta=solar cell")
        assert result["total_count"] == 1
        assert len(result["references"]) == 1
        assert result["references"][0]["country"] == "EP"

    async def test_search_passes_cql_and_range(
        self, epo_client: EpoClient, mock_epo_ops: MagicMock
    ) -> None:
        await epo_client.search("ta=test", range_begin=1, range_end=10)
        mock_epo_ops.published_data_search.assert_called_once_with(
            "ta=test", range_begin=1, range_end=10
        )


class TestEpoClientGetBiblio:
    async def test_get_biblio_returns_parsed(
        self, epo_client: EpoClient
    ) -> None:
        doc = DocdbNumber("EP", "1234567", "A1")
        result = await epo_client.get_biblio(doc)
        assert result["title"] == "Test Patent"
        assert result["publication_number"] == "EP.1234567.A1"

    async def test_get_biblio_calls_published_data(
        self, epo_client: EpoClient, mock_epo_ops: MagicMock
    ) -> None:
        doc = DocdbNumber("EP", "1234567", "A1")
        await epo_client.get_biblio(doc)
        call_args = mock_epo_ops.published_data.call_args
        assert call_args.kwargs.get("endpoint") == "biblio" or \
            (len(call_args.args) >= 3 and call_args.args[2] == "biblio")


class TestEpoClientRateLimiting:
    async def test_yellow_raises_rate_limited(
        self, mock_epo_ops: MagicMock
    ) -> None:
        mock_epo_ops.published_data_search.return_value = _mock_response(
            _SEARCH_RESPONSE_XML, throttle="yellow"
        )
        client = EpoClient(
            consumer_key="test", consumer_secret="test", _client=mock_epo_ops
        )
        with pytest.raises(EpoRateLimitedError, match="yellow"):
            await client.search("ta=test")

    async def test_green_does_not_raise(
        self, epo_client: EpoClient
    ) -> None:
        # Default fixture uses green — should not raise
        result = await epo_client.search("ta=test")
        assert result["total_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scholar_mcp._epo_client'`

- [ ] **Step 3: Implement _epo_client.py**

```python
"""EPO OPS API client.

Wraps python-epo-ops-client for OAuth2 auth and HTTP transport.
Disables the library's built-in caching and throttling middleware
so the MCP server uses its own cache and task queue.

All methods are async (sync calls run via asyncio.to_thread).
All methods return parsed Python dicts — XML handling is internal.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import epo_ops
from epo_ops.models import Docdb

from scholar_mcp._epo_xml import parse_biblio_xml, parse_search_xml
from scholar_mcp._patent_numbers import DocdbNumber
from scholar_mcp._rate_limiter import RateLimitedError

logger = logging.getLogger(__name__)

# Regex to extract overall status from X-Throttling-Control header
_THROTTLE_RE = re.compile(r"^(\w+)\s")


class EpoRateLimitedError(RateLimitedError):
    """Raised when EPO traffic light is yellow, red, or black."""

    def __init__(self, color: str) -> None:
        self.color = color
        super().__init__(f"EPO rate limited: traffic light is {color}")


class EpoClient:
    """Async wrapper around python-epo-ops-client.

    Args:
        consumer_key: EPO OPS API consumer key.
        consumer_secret: EPO OPS API consumer secret.
        _client: Optional pre-built epo_ops.Client for testing.
    """

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        *,
        _client: epo_ops.Client | None = None,
    ) -> None:
        self._client = _client or epo_ops.Client(
            key=consumer_key,
            secret=consumer_secret,
            middlewares=[],  # Disable built-in caching/throttling
        )
        self._lock = asyncio.Lock()

    def _check_throttle(self, response: Any) -> None:
        """Check X-Throttling-Control header and raise if not green.

        Args:
            response: requests.Response from epo_ops.Client.

        Raises:
            EpoRateLimitedError: If traffic light is yellow, red, or black.
        """
        header = response.headers.get("X-Throttling-Control", "")
        m = _THROTTLE_RE.match(header)
        if m:
            color = m.group(1).lower()
            if color != "green":
                logger.warning("epo_throttle color=%s header=%s", color, header)
                raise EpoRateLimitedError(color)

    def _to_docdb_input(self, doc: DocdbNumber) -> Docdb:
        """Convert our DocdbNumber to epo_ops Docdb model."""
        return Docdb(
            number=doc.number,
            country_code=doc.country,
            kind_code=doc.kind or "A",
        )

    async def search(
        self,
        cql_query: str,
        range_begin: int = 1,
        range_end: int = 25,
    ) -> dict[str, Any]:
        """Search patents using CQL query.

        Args:
            cql_query: EPO CQL query string (e.g., 'ta="solar cell"').
            range_begin: Start index (1-based).
            range_end: End index.

        Returns:
            Dict with total_count and references list.

        Raises:
            EpoRateLimitedError: If EPO traffic light is not green.
        """
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data_search,
                cql_query,
                range_begin=range_begin,
                range_end=range_end,
            )
        self._check_throttle(response)
        return parse_search_xml(response.content)

    async def get_biblio(self, doc: DocdbNumber) -> dict[str, Any]:
        """Fetch bibliographic data for a patent.

        Args:
            doc: Patent number in DOCDB format.

        Returns:
            Parsed biblio dict.

        Raises:
            EpoRateLimitedError: If EPO traffic light is not green.
        """
        inp = self._to_docdb_input(doc)
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.published_data,
                "publication",
                inp,
                endpoint="biblio",
            )
        self._check_throttle(response)
        return parse_biblio_xml(response.content)

    async def aclose(self) -> None:
        """Clean up resources. No-op for sync client."""
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/scholar_mcp/_epo_client.py tests/test_epo_client.py`

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_epo_client.py tests/test_epo_client.py
git commit -m "feat: add EPO OPS client wrapper with search and biblio"
```

---

### Task 7: Cache — Patent Tables

**Files:**
- Modify: `src/scholar_mcp/_cache.py`
- Modify: `tests/test_cache.py`

- [ ] **Step 1: Write tests for patent cache operations**

Add to `tests/test_cache.py`:

```python
import time


class TestPatentCache:
    async def test_patent_roundtrip(self, cache) -> None:
        data = {"title": "Test Patent", "publication_number": "EP.1234567.A1"}
        await cache.set_patent("EP.1234567.A1", data)
        result = await cache.get_patent("EP.1234567.A1")
        assert result == data

    async def test_patent_not_found(self, cache) -> None:
        assert await cache.get_patent("EP.9999999.A1") is None

    async def test_patent_search_roundtrip(self, cache) -> None:
        data = {"total_count": 5, "references": [{"country": "EP"}]}
        await cache.set_patent_search("ta=solar", data)
        result = await cache.get_patent_search("ta=solar")
        assert result == data

    async def test_patent_claims_roundtrip(self, cache) -> None:
        await cache.set_patent_claims("EP.1234567.A1", "Claim 1: A method...")
        result = await cache.get_patent_claims("EP.1234567.A1")
        assert result == "Claim 1: A method..."

    async def test_patent_description_roundtrip(self, cache) -> None:
        await cache.set_patent_description("EP.1234567.A1", "Description text")
        result = await cache.get_patent_description("EP.1234567.A1")
        assert result == "Description text"

    async def test_patent_family_roundtrip(self, cache) -> None:
        data = [{"country": "US", "number": "11234567"}]
        await cache.set_patent_family("EP.1234567.A1", data)
        result = await cache.get_patent_family("EP.1234567.A1")
        assert result == data

    async def test_patent_legal_roundtrip(self, cache) -> None:
        data = [{"event": "grant", "date": "2020-01-15"}]
        await cache.set_patent_legal("EP.1234567.A1", data)
        result = await cache.get_patent_legal("EP.1234567.A1")
        assert result == data

    async def test_patent_stats(self, cache) -> None:
        await cache.set_patent("EP.1234567.A1", {"title": "Test"})
        stats = await cache.stats()
        assert stats["patents"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cache.py::TestPatentCache -v`
Expected: FAIL — `AttributeError: 'ScholarCache' object has no attribute 'set_patent'`

- [ ] **Step 3: Add patent tables to _cache.py**

Add these constants near the existing TTL constants:

```python
_PATENT_TTL = 90 * 86400       # 90 days
_PATENT_CLAIMS_TTL = 180 * 86400  # 180 days
_PATENT_DESC_TTL = 180 * 86400    # 180 days
_PATENT_FAMILY_TTL = 90 * 86400   # 90 days
_PATENT_LEGAL_TTL = 7 * 86400     # 7 days
_PATENT_SEARCH_TTL = 7 * 86400    # 7 days
```

Add to the `_SCHEMA` string:

```sql
CREATE TABLE IF NOT EXISTS patents (
    patent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patents_cached ON patents(cached_at);

CREATE TABLE IF NOT EXISTS patent_claims (
    patent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_claims_cached ON patent_claims(cached_at);

CREATE TABLE IF NOT EXISTS patent_descriptions (
    patent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_desc_cached ON patent_descriptions(cached_at);

CREATE TABLE IF NOT EXISTS patent_families (
    patent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_families_cached ON patent_families(cached_at);

CREATE TABLE IF NOT EXISTS patent_legal (
    patent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_legal_cached ON patent_legal(cached_at);

CREATE TABLE IF NOT EXISTS patent_search (
    query_hash TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patent_search_cached ON patent_search(cached_at);
```

Add the new table names to the `_TTL_TABLES` tuple so `stats()` and `clear()` cover them.

Add get/set methods following the existing pattern:

```python
async def get_patent(self, patent_id: str) -> dict | None:
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM patents WHERE patent_id = ?",
        (patent_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if time.time() - row[1] > _PATENT_TTL:
        return None
    return json.loads(row[0])

async def set_patent(self, patent_id: str, data: dict) -> None:
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO patents (patent_id, data, cached_at)"
        " VALUES (?, ?, ?)",
        (patent_id, json.dumps(data), time.time()),
    )
    await db.commit()

async def get_patent_claims(self, patent_id: str) -> str | None:
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM patent_claims WHERE patent_id = ?",
        (patent_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if time.time() - row[1] > _PATENT_CLAIMS_TTL:
        return None
    return row[0]  # plain text, not JSON

async def set_patent_claims(self, patent_id: str, text: str) -> None:
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO patent_claims (patent_id, data, cached_at)"
        " VALUES (?, ?, ?)",
        (patent_id, text, time.time()),
    )
    await db.commit()

async def get_patent_description(self, patent_id: str) -> str | None:
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM patent_descriptions WHERE patent_id = ?",
        (patent_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if time.time() - row[1] > _PATENT_DESC_TTL:
        return None
    return row[0]

async def set_patent_description(self, patent_id: str, text: str) -> None:
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO patent_descriptions (patent_id, data, cached_at)"
        " VALUES (?, ?, ?)",
        (patent_id, text, time.time()),
    )
    await db.commit()

async def get_patent_family(self, patent_id: str) -> list | None:
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM patent_families WHERE patent_id = ?",
        (patent_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if time.time() - row[1] > _PATENT_FAMILY_TTL:
        return None
    return json.loads(row[0])

async def set_patent_family(self, patent_id: str, data: list) -> None:
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO patent_families (patent_id, data, cached_at)"
        " VALUES (?, ?, ?)",
        (patent_id, json.dumps(data), time.time()),
    )
    await db.commit()

async def get_patent_legal(self, patent_id: str) -> list | None:
    db = _require_open(self._db)
    async with db.execute(
        "SELECT data, cached_at FROM patent_legal WHERE patent_id = ?",
        (patent_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if time.time() - row[1] > _PATENT_LEGAL_TTL:
        return None
    return json.loads(row[0])

async def set_patent_legal(self, patent_id: str, data: list) -> None:
    db = _require_open(self._db)
    await db.execute(
        "INSERT OR REPLACE INTO patent_legal (patent_id, data, cached_at)"
        " VALUES (?, ?, ?)",
        (patent_id, json.dumps(data), time.time()),
    )
    await db.commit()

async def get_patent_search(self, query: str) -> dict | None:
    db = _require_open(self._db)
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    async with db.execute(
        "SELECT data, cached_at FROM patent_search WHERE query_hash = ?",
        (query_hash,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if time.time() - row[1] > _PATENT_SEARCH_TTL:
        return None
    return json.loads(row[0])

async def set_patent_search(self, query: str, data: dict) -> None:
    db = _require_open(self._db)
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    await db.execute(
        "INSERT OR REPLACE INTO patent_search (query_hash, data, cached_at)"
        " VALUES (?, ?, ?)",
        (query_hash, json.dumps(data), time.time()),
    )
    await db.commit()
```

Add `import hashlib` at the top of the file if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cache.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_cache.py tests/test_cache.py
git commit -m "feat: add patent cache tables with per-type TTLs"
```

---

### Task 8: ServiceBundle — Add Optional EpoClient

**Files:**
- Modify: `src/scholar_mcp/_server_deps.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add `epo` field to ServiceBundle**

In `src/scholar_mcp/_server_deps.py`, add the import and field:

```python
from scholar_mcp._epo_client import EpoClient
```

Add to the `ServiceBundle` dataclass:

```python
epo: EpoClient | None
```

- [ ] **Step 2: Create EpoClient in lifespan when configured**

In `make_service_lifespan`, after the docling block and before building the bundle:

```python
# EPO OPS (optional — patent tools only available when configured)
epo: EpoClient | None = None
if config.epo_configured:
    epo = EpoClient(
        consumer_key=config.epo_consumer_key,  # type: ignore[arg-type]
        consumer_secret=config.epo_consumer_secret,  # type: ignore[arg-type]
    )
    logger.info("epo_ops status=configured")
else:
    logger.info("epo_ops status=not_configured")
```

Add `epo=epo` to the `ServiceBundle(...)` construction.

In the finally block, add cleanup:

```python
if epo is not None:
    await epo.aclose()
```

- [ ] **Step 3: Update conftest.py bundle fixture**

In `tests/conftest.py`, add `epo=None` to the `ServiceBundle(...)` construction:

```python
yield ServiceBundle(
    s2=s2,
    openalex=openalex,
    docling=None,
    epo=None,  # NEW
    cache=cache,
    config=test_config,
    tasks=TaskQueue(),
)
```

- [ ] **Step 4: Run full test suite to verify nothing breaks**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_server_deps.py tests/conftest.py
git commit -m "feat: add optional EpoClient to ServiceBundle"
```

---

### Task 9: Patent Tools — search_patents + get_patent (biblio)

**Files:**
- Create: `src/scholar_mcp/_tools_patent.py`
- Create: `tests/test_tools_patent.py`

- [ ] **Step 1: Write tests for search_patents tool**

```python
"""Tests for patent MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
from scholar_mcp._patent_numbers import DocdbNumber


@pytest.fixture
def mock_epo() -> MagicMock:
    """Mock EpoClient with async methods."""
    epo = MagicMock(spec=EpoClient)
    epo.search = AsyncMock(return_value={
        "total_count": 1,
        "references": [{"country": "EP", "number": "1234567", "kind": "A1"}],
    })
    epo.get_biblio = AsyncMock(return_value={
        "title": "Test Patent",
        "abstract": "Test abstract.",
        "applicants": ["TEST CORP"],
        "inventors": ["SMITH, JOHN"],
        "publication_number": "EP.1234567.A1",
        "publication_date": "2020-01-15",
        "filing_date": "2019-05-01",
        "priority_date": "2018-06-01",
        "family_id": "54321",
        "classifications": ["H04L29/06"],
        "url": "https://worldwide.espacenet.com/patent/search?q=pn%3DEP1234567A1",
    })
    return epo
```

The actual tool function tests depend on how FastMCP testing works. Since the existing tests call tool logic directly (the `_execute` inner function pattern), we test the tool logic similarly. The test structure depends on reading the exact tool registration pattern.

Given the existing pattern where tools are defined inside `register_*_tools()` and use `Depends(get_bundle)`, integration-test the tools by calling the inner `_execute` function or by testing the tool module functions directly.

For this plan, create testable helper functions that the tools delegate to:

```python
class TestSearchPatentsLogic:
    async def test_search_basic(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _search_patents_execute

        result_json = await _search_patents_execute(
            query="solar cell",
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert result["total_count"] == 1

    async def test_search_rate_limited(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _search_patents_execute

        mock_epo.search = AsyncMock(side_effect=EpoRateLimitedError("yellow"))
        with pytest.raises(EpoRateLimitedError):
            await _search_patents_execute(
                query="solar cell",
                epo=mock_epo,
                cache=cache,
                retry=False,
            )


class TestGetPatentLogic:
    async def test_get_biblio(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        result_json = await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["biblio"],
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert result["biblio"]["title"] == "Test Patent"

    async def test_get_patent_cached(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        # First call populates cache
        await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["biblio"],
            epo=mock_epo,
            cache=cache,
        )
        # Reset mock to verify cache hit
        mock_epo.get_biblio.reset_mock()
        result_json = await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["biblio"],
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert result["biblio"]["title"] == "Test Patent"
        mock_epo.get_biblio.assert_not_called()

    async def test_get_patent_invalid_number(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        result_json = await _get_patent_execute(
            patent_number="not-a-patent",
            sections=["biblio"],
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_patent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scholar_mcp._tools_patent'`

- [ ] **Step 3: Implement _tools_patent.py**

```python
"""Patent MCP tools.

Provides search_patents and get_patent tools. Only registered when
EPO OPS credentials are configured (bundle.epo is not None).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import Depends

from scholar_mcp._cache import ScholarCache
from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
from scholar_mcp._patent_numbers import normalize
from scholar_mcp._rate_limiter import RateLimitedError
from scholar_mcp._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def _build_cql(
    query: str,
    *,
    cpc_classification: str | None = None,
    applicant: str | None = None,
    inventor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    date_type: str = "publication",
    jurisdiction: str | None = None,
) -> str:
    """Build EPO CQL query from tool parameters.

    Args:
        query: Natural language search terms (mapped to title+abstract).
        cpc_classification: CPC code filter.
        applicant: Applicant name filter.
        inventor: Inventor name filter.
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).
        date_type: Which date field to filter (publication/filing/priority).
        jurisdiction: Country code filter.

    Returns:
        CQL query string for EPO OPS.
    """
    parts: list[str] = []
    # Main query on title + abstract
    if query:
        parts.append(f'ta="{query}"')
    if cpc_classification:
        parts.append(f'cpc="{cpc_classification}"')
    if applicant:
        parts.append(f'pa="{applicant}"')
    if inventor:
        parts.append(f'in="{inventor}"')
    if jurisdiction:
        parts.append(f'pn={jurisdiction}')

    # Date range
    date_field_map = {
        "publication": "pd",
        "filing": "ad",
        "priority": "prd",
    }
    date_field = date_field_map.get(date_type, "pd")
    if date_from and date_to:
        # EPO date format: YYYYMMDD
        df = date_from.replace("-", "")
        dt = date_to.replace("-", "")
        parts.append(f"{date_field} within {df},{dt}")
    elif date_from:
        df = date_from.replace("-", "")
        parts.append(f"{date_field} >= {df}")
    elif date_to:
        dt = date_to.replace("-", "")
        parts.append(f"{date_field} <= {dt}")

    return " AND ".join(parts) if parts else 'ta=""'


async def _search_patents_execute(
    *,
    query: str,
    epo: EpoClient,
    cache: ScholarCache,
    cpc_classification: str | None = None,
    applicant: str | None = None,
    inventor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    date_type: str = "publication",
    jurisdiction: str | None = None,
    limit: int = 10,
    offset: int = 0,
    retry: bool = True,
) -> str:
    """Execute search_patents logic. Extracted for try-once/queue pattern."""
    cql = _build_cql(
        query,
        cpc_classification=cpc_classification,
        applicant=applicant,
        inventor=inventor,
        date_from=date_from,
        date_to=date_to,
        date_type=date_type,
        jurisdiction=jurisdiction,
    )
    logger.info("patent_search cql=%s offset=%d limit=%d", cql, offset, limit)

    # Check cache
    cached = await cache.get_patent_search(cql)
    if cached is not None:
        return json.dumps(cached)

    range_begin = offset + 1
    range_end = offset + limit

    if retry:
        result = await epo.search(cql, range_begin, range_end)
    else:
        try:
            result = await epo.search(cql, range_begin, range_end)
        except EpoRateLimitedError:
            raise

    await cache.set_patent_search(cql, result)
    return json.dumps(result)


async def _get_patent_execute(
    *,
    patent_number: str,
    sections: list[str],
    epo: EpoClient,
    cache: ScholarCache,
    retry: bool = True,
) -> str:
    """Execute get_patent logic. Extracted for try-once/queue pattern."""
    try:
        doc = normalize(patent_number)
    except ValueError as e:
        return json.dumps({"error": "invalid_patent_number", "detail": str(e)})

    patent_id = doc.docdb
    result: dict[str, Any] = {"patent_number": patent_id}

    if "biblio" in sections:
        cached = await cache.get_patent(patent_id)
        if cached is not None:
            result["biblio"] = cached
        else:
            biblio = await epo.get_biblio(doc)
            await cache.set_patent(patent_id, biblio)
            result["biblio"] = biblio

    return json.dumps(result)


def register_patent_tools(mcp: FastMCP) -> None:
    """Register patent tools. Only call when bundle.epo is not None."""

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_patents(
        query: str,
        cpc_classification: str | None = None,
        applicant: str | None = None,
        inventor: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        date_type: Literal["publication", "filing", "priority"] = "publication",
        jurisdiction: str | None = None,
        limit: int = 10,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search for patents in the European Patent Office database.

        Covers European patents and global patents via INPADOC (100+ patent
        offices). Accepts natural language queries. Use CPC classification
        codes, applicant names, or date ranges to narrow results. For
        academic paper search, use search_papers instead.

        Args:
            query: Natural language search query.
            cpc_classification: CPC classification code filter (e.g., H04L29/06).
            applicant: Applicant/assignee name filter.
            inventor: Inventor name filter.
            date_from: Start date filter (YYYY-MM-DD).
            date_to: End date filter (YYYY-MM-DD).
            date_type: Which date to filter on: publication, filing, or priority.
            jurisdiction: Country code filter (e.g., EP, US, WO).
            limit: Maximum results to return (max 100).
            offset: Pagination offset.
        """
        assert bundle.epo is not None
        limit = min(limit, 100)

        async def _execute(*, retry: bool = True) -> str:
            return await _search_patents_execute(
                query=query,
                epo=bundle.epo,
                cache=bundle.cache,
                cpc_classification=cpc_classification,
                applicant=applicant,
                inventor=inventor,
                date_from=date_from,
                date_to=date_to,
                date_type=date_type,
                jurisdiction=jurisdiction,
                limit=limit,
                offset=offset,
                retry=retry,
            )

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="search_patents"
            )
            return json.dumps({
                "queued": True,
                "task_id": task_id,
                "tool": "search_patents",
            })

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_patent(
        patent_number: str,
        sections: list[
            Literal["biblio", "claims", "description", "family", "legal", "citations"]
        ] | None = None,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Get detailed information about a single patent.

        Accepts patent numbers in any format (EP, WO, US, etc.). By default
        returns bibliographic data only -- use the sections parameter to
        request additional detail (claims, description, family members,
        legal status, cited references). When sections includes 'citations',
        non-patent literature references are resolved to Semantic Scholar
        papers on a best-effort basis; unresolved references are returned
        as raw citation strings.

        Args:
            patent_number: Patent number in any format (EP1234567,
                WO2024/123456, US11234567B2, etc.).
            sections: Sections to include. Default: ["biblio"].
        """
        assert bundle.epo is not None
        if sections is None:
            sections = ["biblio"]

        async def _execute(*, retry: bool = True) -> str:
            return await _get_patent_execute(
                patent_number=patent_number,
                sections=sections,  # type: ignore[arg-type]
                epo=bundle.epo,
                cache=bundle.cache,
                retry=retry,
            )

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="get_patent"
            )
            return json.dumps({
                "queued": True,
                "task_id": task_id,
                "tool": "get_patent",
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_patent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/scholar_mcp/_tools_patent.py tests/test_tools_patent.py`

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_tools_patent.py tests/test_tools_patent.py
git commit -m "feat: add search_patents and get_patent tools (biblio only)"
```

---

### Task 10: Conditional Tool Registration

**Files:**
- Modify: `src/scholar_mcp/_server_tools.py`

- [ ] **Step 1: Add patent tool registration to _server_tools.py**

Import and call `register_patent_tools` conditionally. The registration function itself checks the bundle, but since tools are registered at import time (before the bundle is available), the conditional check happens differently.

Looking at the existing pattern: `register_tools(mcp, *, transport)` imports modules and calls `register_*_tools(mcp)`. The bundle is available at request time via `Depends(get_bundle)`.

For conditional registration, we need to defer — patent tools are always registered but use `assert bundle.epo is not None` at call time. However, the spec says tools should be **hidden** when EPO is not configured.

The cleanest approach: register patent tools into a separate `FastMCP` tag, then disable that tag when EPO is not configured. Similar to how write tools use `tags={"write"}`.

Update `_tools_patent.py` to tag all patent tools with `tags={"patent"}`.

In `mcp_server.py`'s `create_server()`, after registering tools, check config and disable:

```python
if not config.epo_configured:
    mcp.disable(tags={"patent"})
```

In `src/scholar_mcp/_server_tools.py`, add the import:

```python
from scholar_mcp._tools_patent import register_patent_tools
```

And call it:

```python
register_patent_tools(mcp)
```

- [ ] **Step 2: Add `tags={"patent"}` to both patent tools in _tools_patent.py**

Update both `@mcp.tool()` decorators:

```python
@mcp.tool(
    tags={"patent"},
    annotations={...},
)
```

- [ ] **Step 3: Add disable logic in mcp_server.py**

In `create_server()`, after the existing `mcp.disable(tags={"write"})` block, add:

```python
config = load_config()
if not config.epo_configured:
    mcp.disable(tags={"patent"})
```

Note: `load_config()` may already be called earlier in `create_server()` — reuse the existing config variable.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_server_tools.py src/scholar_mcp/_tools_patent.py src/scholar_mcp/mcp_server.py
git commit -m "feat: conditional patent tool registration via tag disabling"
```

---

### Task 11: Documentation Update (Phase 1)

**Files:**
- Modify: `docs/tools/index.md`
- Modify: `docs/configuration.md`
- Modify: `README.md`

- [ ] **Step 1: Add patent tools to docs/tools/index.md**

Add a "Patent Tools" section documenting `search_patents` and `get_patent` with their parameters, outputs, and usage examples. Include note that these tools require EPO OPS credentials.

- [ ] **Step 2: Add EPO configuration to docs/configuration.md**

Document `SCHOLAR_MCP_EPO_CONSUMER_KEY` and `SCHOLAR_MCP_EPO_CONSUMER_SECRET`. Include step-by-step EPO registration walkthrough:

1. Register at https://developers.epo.org/user/register
2. Wait for email confirmation
3. Log in, navigate to "My Apps"
4. Click "Add a new App", choose a name (e.g. "scholar-mcp")
5. Select "Non-paying" access method
6. Copy Consumer Key and Consumer Secret to env vars

- [ ] **Step 3: Update README.md**

Add patent search to the feature list and tool table. Note that EPO OPS credentials are optional.

- [ ] **Step 4: Commit**

```bash
git add docs/ README.md
git commit -m "docs: add patent tools and EPO configuration documentation"
```

---

## Phase 2 — Full Detail

### Task 12: EPO XML Claims + Description Parsers

**Files:**
- Modify: `src/scholar_mcp/_epo_xml.py`
- Modify: `tests/test_epo_xml.py`

- [ ] **Step 1: Write tests for parse_claims_xml and parse_description_xml**

```python
from scholar_mcp._epo_xml import parse_claims_xml, parse_description_xml

CLAIMS_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1">
      <claims lang="en">
        <claim>
          <claim-text>1. A method for processing widgets comprising:
            <claim-text>a) receiving input data;</claim-text>
            <claim-text>b) transforming the input data.</claim-text>
          </claim-text>
        </claim>
        <claim>
          <claim-text>2. The method of claim 1, wherein the input data is digital.</claim-text>
        </claim>
      </claims>
      <claims lang="de">
        <claim>
          <claim-text>1. Ein Verfahren zur Verarbeitung...</claim-text>
        </claim>
      </claims>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

DESCRIPTION_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1">
      <description lang="en">
        <p num="0001">FIELD OF THE INVENTION</p>
        <p num="0002">The present invention relates to widget processing.</p>
        <p num="0003">BACKGROUND</p>
        <p num="0004">Prior art widgets have limitations.</p>
      </description>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""


class TestParseClaimsXml:
    def test_english_preferred(self) -> None:
        result = parse_claims_xml(CLAIMS_XML)
        assert "processing widgets" in result
        assert "Verfahren" not in result

    def test_multiple_claims(self) -> None:
        result = parse_claims_xml(CLAIMS_XML)
        assert "1." in result
        assert "2." in result


class TestParseDescriptionXml:
    def test_paragraphs_joined(self) -> None:
        result = parse_description_xml(DESCRIPTION_XML)
        assert "FIELD OF THE INVENTION" in result
        assert "widget processing" in result

    def test_not_empty(self) -> None:
        result = parse_description_xml(DESCRIPTION_XML)
        assert len(result) > 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_xml.py -k "Claims or Description" -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement parse_claims_xml and parse_description_xml**

Add to `src/scholar_mcp/_epo_xml.py`:

```python
def parse_claims_xml(xml_data: bytes) -> str:
    """Parse EPO OPS claims response into plain text.

    Prefers English claims. Returns all claim text joined with newlines.

    Args:
        xml_data: Raw XML bytes from the published-data/claims endpoint.

    Returns:
        Claims text as a single string, or empty string if unavailable.
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    doc = root.find(".//exch:exchange-document", _NS)
    if doc is None:
        return ""

    # Prefer English claims
    claims_el = None
    for c in doc.findall("exch:claims", _NS):
        if c.get("lang", "") == "en":
            claims_el = c
            break
        if claims_el is None:
            claims_el = c  # fallback to first available

    if claims_el is None:
        return ""

    # Extract all text from claim elements, preserving structure
    parts: list[str] = []
    for claim in claims_el.findall("exch:claim", _NS):
        text = etree.tostring(claim, method="text", encoding="unicode").strip()
        if text:
            parts.append(text)

    return "\n\n".join(parts)


def parse_description_xml(xml_data: bytes) -> str:
    """Parse EPO OPS description response into plain text.

    Args:
        xml_data: Raw XML bytes from the published-data/description endpoint.

    Returns:
        Description text as a single string, or empty string if unavailable.
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    doc = root.find(".//exch:exchange-document", _NS)
    if doc is None:
        return ""

    # Prefer English description
    desc_el = None
    for d in doc.findall("exch:description", _NS):
        if d.get("lang", "") == "en":
            desc_el = d
            break
        if desc_el is None:
            desc_el = d

    if desc_el is None:
        return ""

    paragraphs: list[str] = []
    for p in desc_el.findall("exch:p", _NS):
        text = etree.tostring(p, method="text", encoding="unicode").strip()
        if text:
            paragraphs.append(text)

    return "\n\n".join(paragraphs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_xml.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_epo_xml.py tests/test_epo_xml.py
git commit -m "feat: add EPO XML claims and description parsers"
```

---

### Task 13: EPO XML Family + Legal Parsers

**Files:**
- Modify: `src/scholar_mcp/_epo_xml.py`
- Modify: `tests/test_epo_xml.py`

- [ ] **Step 1: Write tests for parse_family_xml and parse_legal_xml**

```python
from scholar_mcp._epo_xml import parse_family_xml, parse_legal_xml

FAMILY_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:patent-family>
    <ops:family-member family-id="54321">
      <publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country>
          <doc-number>1234567</doc-number>
          <kind>A1</kind>
          <date>20200115</date>
        </document-id>
      </publication-reference>
    </ops:family-member>
    <ops:family-member family-id="54321">
      <publication-reference>
        <document-id document-id-type="docdb">
          <country>US</country>
          <doc-number>11234567</doc-number>
          <kind>B2</kind>
          <date>20210301</date>
        </document-id>
      </publication-reference>
    </ops:family-member>
  </ops:patent-family>
</ops:world-patent-data>"""

LEGAL_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:register-documents>
    <ops:register-document country="EP" doc-number="1234567" kind="A1">
      <ops:legal>
        <ops:legal-event>
          <ops:event-date><ops:date>20190501</ops:date></ops:event-date>
          <ops:event-code>APPLICATION</ops:event-code>
          <ops:event-text>Application filed</ops:event-text>
        </ops:legal-event>
        <ops:legal-event>
          <ops:event-date><ops:date>20200115</ops:date></ops:event-date>
          <ops:event-code>PUBLICATION</ops:event-code>
          <ops:event-text>Publication of application</ops:event-text>
        </ops:legal-event>
      </ops:legal>
    </ops:register-document>
  </ops:register-documents>
</ops:world-patent-data>"""


class TestParseFamilyXml:
    def test_family_members(self) -> None:
        result = parse_family_xml(FAMILY_XML)
        assert len(result) == 2
        assert result[0]["country"] == "EP"
        assert result[1]["country"] == "US"

    def test_family_member_fields(self) -> None:
        result = parse_family_xml(FAMILY_XML)
        ep = result[0]
        assert ep["number"] == "1234567"
        assert ep["kind"] == "A1"
        assert ep["date"] == "2020-01-15"


class TestParseLegalXml:
    def test_legal_events(self) -> None:
        result = parse_legal_xml(LEGAL_XML)
        assert len(result) == 2

    def test_event_fields(self) -> None:
        result = parse_legal_xml(LEGAL_XML)
        assert result[0]["date"] == "2019-05-01"
        assert result[0]["code"] == "APPLICATION"
        assert "filed" in result[0]["description"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_xml.py -k "Family or Legal" -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement parse_family_xml and parse_legal_xml**

Add to `src/scholar_mcp/_epo_xml.py`:

```python
def parse_family_xml(xml_data: bytes) -> list[dict[str, str]]:
    """Parse EPO OPS family response into a list of family members.

    Args:
        xml_data: Raw XML bytes from the family endpoint.

    Returns:
        List of dicts with country, number, kind, date for each member.
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    members: list[dict[str, str]] = []

    for member in root.findall(".//ops:family-member", _NS):
        pub_ref = member.find(
            "exch:publication-reference/exch:document-id[@document-id-type='docdb']",
            _NS,
        )
        if pub_ref is None:
            continue
        members.append({
            "country": _text(pub_ref.find("exch:country", _NS)),
            "number": _text(pub_ref.find("exch:doc-number", _NS)),
            "kind": _text(pub_ref.find("exch:kind", _NS)),
            "date": _date_fmt(_text(pub_ref.find("exch:date", _NS))),
        })

    return members


def parse_legal_xml(xml_data: bytes) -> list[dict[str, str]]:
    """Parse EPO OPS legal status response into event list.

    Args:
        xml_data: Raw XML bytes from the legal endpoint.

    Returns:
        List of dicts with date, code, description for each event.
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    events: list[dict[str, str]] = []

    for event in root.findall(".//ops:legal-event", _NS):
        date_el = event.find("ops:event-date/ops:date", _NS)
        code_el = event.find("ops:event-code", _NS)
        text_el = event.find("ops:event-text", _NS)
        events.append({
            "date": _date_fmt(_text(date_el)),
            "code": _text(code_el),
            "description": _text(text_el),
        })

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_xml.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_epo_xml.py tests/test_epo_xml.py
git commit -m "feat: add EPO XML family and legal status parsers"
```

---

### Task 14: EPO Client — Remaining Methods

**Files:**
- Modify: `src/scholar_mcp/_epo_client.py`
- Modify: `tests/test_epo_client.py`

- [ ] **Step 1: Write tests for get_claims, get_description, get_family, get_legal**

Add to `tests/test_epo_client.py`:

```python
# Add XML fixtures for claims, description, family, legal
# (reuse the test XML from test_epo_xml.py or define minimal versions)

_CLAIMS_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1">
      <claims lang="en">
        <claim><claim-text>1. A method for testing.</claim-text></claim>
      </claims>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

_DESCRIPTION_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1">
      <description lang="en">
        <p num="0001">Test description.</p>
      </description>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""

_FAMILY_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:patent-family>
    <ops:family-member family-id="54321">
      <publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country><doc-number>1234567</doc-number>
          <kind>A1</kind><date>20200115</date>
        </document-id>
      </publication-reference>
    </ops:family-member>
  </ops:patent-family>
</ops:world-patent-data>"""

_LEGAL_RESPONSE_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:register-documents>
    <ops:register-document country="EP" doc-number="1234567" kind="A1">
      <ops:legal>
        <ops:legal-event>
          <ops:event-date><ops:date>20200115</ops:date></ops:event-date>
          <ops:event-code>PUB</ops:event-code>
          <ops:event-text>Published</ops:event-text>
        </ops:legal-event>
      </ops:legal>
    </ops:register-document>
  </ops:register-documents>
</ops:world-patent-data>"""


class TestEpoClientClaims:
    async def test_get_claims(self, epo_client, mock_epo_ops) -> None:
        mock_epo_ops.published_data.return_value = _mock_response(
            _CLAIMS_RESPONSE_XML
        )
        doc = DocdbNumber("EP", "1234567", "A1")
        result = await epo_client.get_claims(doc)
        assert "method for testing" in result


class TestEpoClientDescription:
    async def test_get_description(self, epo_client, mock_epo_ops) -> None:
        mock_epo_ops.published_data.return_value = _mock_response(
            _DESCRIPTION_RESPONSE_XML
        )
        doc = DocdbNumber("EP", "1234567", "A1")
        result = await epo_client.get_description(doc)
        assert "Test description" in result


class TestEpoClientFamily:
    async def test_get_family(self, epo_client, mock_epo_ops) -> None:
        mock_epo_ops.family.return_value = _mock_response(_FAMILY_RESPONSE_XML)
        doc = DocdbNumber("EP", "1234567", "A1")
        result = await epo_client.get_family(doc)
        assert len(result) == 1
        assert result[0]["country"] == "EP"


class TestEpoClientLegal:
    async def test_get_legal(self, epo_client, mock_epo_ops) -> None:
        mock_epo_ops.legal.return_value = _mock_response(_LEGAL_RESPONSE_XML)
        doc = DocdbNumber("EP", "1234567", "A1")
        result = await epo_client.get_legal(doc)
        assert len(result) == 1
        assert result[0]["code"] == "PUB"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_client.py -k "Claims or Description or Family or Legal" -v`
Expected: FAIL — `AttributeError: 'EpoClient' object has no attribute 'get_claims'`

- [ ] **Step 3: Add remaining methods to EpoClient**

Add to `src/scholar_mcp/_epo_client.py`:

```python
from scholar_mcp._epo_xml import (
    parse_biblio_xml,
    parse_claims_xml,
    parse_description_xml,
    parse_family_xml,
    parse_legal_xml,
    parse_search_xml,
)
```

Add methods to the `EpoClient` class:

```python
async def get_claims(self, doc: DocdbNumber) -> str:
    """Fetch claims text for a patent."""
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="claims",
        )
    self._check_throttle(response)
    return parse_claims_xml(response.content)

async def get_description(self, doc: DocdbNumber) -> str:
    """Fetch description text for a patent."""
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="description",
        )
    self._check_throttle(response)
    return parse_description_xml(response.content)

async def get_family(self, doc: DocdbNumber) -> list[dict[str, str]]:
    """Fetch patent family members."""
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.family,
            "publication",
            inp,
        )
    self._check_throttle(response)
    return parse_family_xml(response.content)

async def get_legal(self, doc: DocdbNumber) -> list[dict[str, str]]:
    """Fetch legal status events for a patent."""
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.legal,
            "publication",
            inp,
        )
    self._check_throttle(response)
    return parse_legal_xml(response.content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_epo_client.py tests/test_epo_client.py
git commit -m "feat: add claims, description, family, legal to EPO client"
```

---

### Task 15: get_patent — Full Sections with Concurrent Fetching

**Files:**
- Modify: `src/scholar_mcp/_tools_patent.py`
- Modify: `tests/test_tools_patent.py`

- [ ] **Step 1: Write tests for full section fetching**

Add to `tests/test_tools_patent.py`:

```python
class TestGetPatentFullSections:
    async def test_claims_section(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        mock_epo.get_claims = AsyncMock(return_value="1. A method...")
        result_json = await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["claims"],
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert result["claims"] == "1. A method..."

    async def test_multiple_sections(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        mock_epo.get_claims = AsyncMock(return_value="1. A method...")
        mock_epo.get_description = AsyncMock(return_value="Description text")
        mock_epo.get_family = AsyncMock(return_value=[{"country": "US"}])
        mock_epo.get_legal = AsyncMock(return_value=[{"code": "PUB"}])
        result_json = await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["biblio", "claims", "description", "family", "legal"],
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert "biblio" in result
        assert "claims" in result
        assert "description" in result
        assert "family" in result
        assert "legal" in result

    async def test_cached_claims_not_refetched(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        await cache.set_patent_claims("EP.1234567.A1", "Cached claims")
        mock_epo.get_claims = AsyncMock()
        result_json = await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["claims"],
            epo=mock_epo,
            cache=cache,
        )
        result = json.loads(result_json)
        assert result["claims"] == "Cached claims"
        mock_epo.get_claims.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_patent.py::TestGetPatentFullSections -v`
Expected: FAIL — claims not handled yet

- [ ] **Step 3: Extend _get_patent_execute with all sections**

Update `_get_patent_execute` in `src/scholar_mcp/_tools_patent.py`:

```python
import asyncio as _asyncio


async def _get_patent_execute(
    *,
    patent_number: str,
    sections: list[str],
    epo: EpoClient,
    cache: ScholarCache,
    retry: bool = True,
) -> str:
    """Execute get_patent logic with concurrent section fetching."""
    try:
        doc = normalize(patent_number)
    except ValueError as e:
        return json.dumps({"error": "invalid_patent_number", "detail": str(e)})

    patent_id = doc.docdb
    result: dict[str, Any] = {"patent_number": patent_id}

    # Semaphore to bound concurrent EPO requests
    sem = _asyncio.Semaphore(3)

    async def _fetch_biblio() -> None:
        cached = await cache.get_patent(patent_id)
        if cached is not None:
            result["biblio"] = cached
            return
        async with sem:
            biblio = await epo.get_biblio(doc)
        await cache.set_patent(patent_id, biblio)
        result["biblio"] = biblio

    async def _fetch_claims() -> None:
        cached = await cache.get_patent_claims(patent_id)
        if cached is not None:
            result["claims"] = cached
            return
        async with sem:
            claims = await epo.get_claims(doc)
        await cache.set_patent_claims(patent_id, claims)
        result["claims"] = claims

    async def _fetch_description() -> None:
        cached = await cache.get_patent_description(patent_id)
        if cached is not None:
            result["description"] = cached
            return
        async with sem:
            desc = await epo.get_description(doc)
        await cache.set_patent_description(patent_id, desc)
        result["description"] = desc

    async def _fetch_family() -> None:
        cached = await cache.get_patent_family(patent_id)
        if cached is not None:
            result["family"] = cached
            return
        async with sem:
            family = await epo.get_family(doc)
        await cache.set_patent_family(patent_id, family)
        result["family"] = family

    async def _fetch_legal() -> None:
        cached = await cache.get_patent_legal(patent_id)
        if cached is not None:
            result["legal"] = cached
            return
        async with sem:
            legal = await epo.get_legal(doc)
        await cache.set_patent_legal(patent_id, legal)
        result["legal"] = legal

    fetchers = []
    section_map = {
        "biblio": _fetch_biblio,
        "claims": _fetch_claims,
        "description": _fetch_description,
        "family": _fetch_family,
        "legal": _fetch_legal,
    }
    for section in sections:
        if section in section_map:
            fetchers.append(section_map[section]())

    # Run all requested sections concurrently
    await _asyncio.gather(*fetchers)

    return json.dumps(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_patent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_tools_patent.py tests/test_tools_patent.py
git commit -m "feat: add full section fetching to get_patent with concurrency"
```

---

### Task 16: Documentation Update (Phase 2)

**Files:**
- Modify: `docs/tools/index.md`

- [ ] **Step 1: Update get_patent documentation**

Add documentation for the `sections` parameter including all available sections (claims, description, family, legal) with descriptions of what each returns.

- [ ] **Step 2: Commit**

```bash
git add docs/
git commit -m "docs: add full get_patent section documentation"
```

---

## Phase 3 — Cross-Referencing

### Task 17: EPO XML — Cited References Parsing

**Files:**
- Modify: `src/scholar_mcp/_epo_xml.py`
- Modify: `tests/test_epo_xml.py`

- [ ] **Step 1: Write tests for parse_citations_from_biblio**

The biblio XML contains cited references. We need to extract them and split into patent refs and NPL (non-patent literature) refs.

```python
from scholar_mcp._epo_xml import parse_citations_from_biblio

BIBLIO_WITH_CITATIONS_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document country="EP" doc-number="1234567" kind="A1" family-id="54321">
      <bibliographic-data>
        <references-cited>
          <citation>
            <patcit>
              <document-id document-id-type="docdb">
                <country>US</country>
                <doc-number>9876543</doc-number>
                <kind>B2</kind>
              </document-id>
            </patcit>
          </citation>
          <citation>
            <nplcit>
              <text>Smith et al., "Widget Processing", Journal of Widgets, 2018, doi:10.1234/widgets.2018</text>
            </nplcit>
          </citation>
          <citation>
            <nplcit>
              <text>Doe, J., "Advanced Widgets", Conference on Widgets, 2019</text>
            </nplcit>
          </citation>
        </references-cited>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>"""


class TestParseCitationsFromBiblio:
    def test_patent_citations(self) -> None:
        result = parse_citations_from_biblio(BIBLIO_WITH_CITATIONS_XML)
        assert len(result["patent_refs"]) == 1
        assert result["patent_refs"][0]["country"] == "US"
        assert result["patent_refs"][0]["number"] == "9876543"

    def test_npl_citations(self) -> None:
        result = parse_citations_from_biblio(BIBLIO_WITH_CITATIONS_XML)
        assert len(result["npl_refs"]) == 2
        assert "Widget Processing" in result["npl_refs"][0]["raw"]

    def test_doi_extraction(self) -> None:
        result = parse_citations_from_biblio(BIBLIO_WITH_CITATIONS_XML)
        # First NPL has a DOI
        assert result["npl_refs"][0]["doi"] == "10.1234/widgets.2018"
        # Second NPL has no DOI
        assert result["npl_refs"][1]["doi"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epo_xml.py::TestParseCitationsFromBiblio -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement parse_citations_from_biblio**

Add to `src/scholar_mcp/_epo_xml.py`:

```python
_DOI_RE = re.compile(r"\bdoi:\s*(10\.\S+)", re.IGNORECASE)
```

Add `import re` at the top if not present.

```python
def parse_citations_from_biblio(xml_data: bytes) -> dict[str, list[dict[str, Any]]]:
    """Parse cited references from EPO OPS biblio response.

    Splits citations into patent references and non-patent literature (NPL).
    Extracts DOIs from NPL citation strings where possible.

    Args:
        xml_data: Raw XML bytes from the published-data/biblio endpoint.

    Returns:
        Dict with patent_refs (list of {country, number, kind}) and
        npl_refs (list of {raw, doi}).
    """
    root = etree.fromstring(xml_data)  # noqa: S320
    doc = root.find(".//exch:exchange-document", _NS)
    if doc is None:
        return {"patent_refs": [], "npl_refs": []}

    patent_refs: list[dict[str, str]] = []
    npl_refs: list[dict[str, Any]] = []

    refs_cited = doc.find(
        "exch:bibliographic-data/exch:references-cited", _NS
    )
    if refs_cited is None:
        return {"patent_refs": [], "npl_refs": []}

    for citation in refs_cited.findall("exch:citation", _NS):
        # Patent citation
        patcit = citation.find("exch:patcit", _NS)
        if patcit is not None:
            doc_id = patcit.find(
                "exch:document-id[@document-id-type='docdb']", _NS
            )
            if doc_id is not None:
                patent_refs.append({
                    "country": _text(doc_id.find("exch:country", _NS)),
                    "number": _text(doc_id.find("exch:doc-number", _NS)),
                    "kind": _text(doc_id.find("exch:kind", _NS)),
                })
            continue

        # Non-patent literature citation
        nplcit = citation.find("exch:nplcit", _NS)
        if nplcit is not None:
            text_el = nplcit.find("exch:text", _NS)
            raw = _text(text_el)
            # Try to extract DOI
            doi_match = _DOI_RE.search(raw)
            doi = doi_match.group(1).rstrip(".,;") if doi_match else None
            npl_refs.append({"raw": raw, "doi": doi})

    return {"patent_refs": patent_refs, "npl_refs": npl_refs}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epo_xml.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_epo_xml.py tests/test_epo_xml.py
git commit -m "feat: add cited references parser with DOI extraction"
```

---

### Task 18: get_patent Citations Section with NPL Resolution

**Files:**
- Modify: `src/scholar_mcp/_tools_patent.py`
- Modify: `tests/test_tools_patent.py`

- [ ] **Step 1: Write tests for citations section**

```python
class TestGetPatentCitations:
    async def test_citations_with_npl_resolution(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_patent_execute

        # Mock biblio with citations endpoint
        mock_epo.get_biblio_with_citations = AsyncMock(return_value={
            "patent_refs": [{"country": "US", "number": "9876543", "kind": "B2"}],
            "npl_refs": [
                {"raw": "Smith, doi:10.1234/test", "doi": "10.1234/test"},
                {"raw": "Unknown reference", "doi": None},
            ],
        })

        # We need a mock S2 client for NPL resolution
        mock_s2 = AsyncMock()
        mock_s2.batch_resolve = AsyncMock(return_value=[
            {"paperId": "abc123", "title": "Smith Paper"},
            None,
        ])

        result_json = await _get_patent_execute(
            patent_number="EP1234567A1",
            sections=["citations"],
            epo=mock_epo,
            cache=cache,
            s2=mock_s2,
        )
        result = json.loads(result_json)
        citations = result["citations"]
        assert len(citations["patent_refs"]) == 1
        assert len(citations["npl_refs"]) == 2
        # First NPL resolved via DOI
        assert citations["npl_refs"][0]["confidence"] == "high"
        assert citations["npl_refs"][0]["paper"]["paperId"] == "abc123"
        # Second NPL unresolved
        assert citations["npl_refs"][1]["confidence"] is None
        assert citations["npl_refs"][1]["raw"] == "Unknown reference"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_patent.py::TestGetPatentCitations -v`
Expected: FAIL

- [ ] **Step 3: Implement citations section in _get_patent_execute**

Update `_get_patent_execute` to accept an optional `s2` parameter and add a `_fetch_citations` function:

```python
from scholar_mcp._epo_xml import parse_citations_from_biblio

async def _get_patent_execute(
    *,
    patent_number: str,
    sections: list[str],
    epo: EpoClient,
    cache: ScholarCache,
    s2: Any | None = None,  # S2Client for NPL resolution
    retry: bool = True,
) -> str:
    # ... existing code ...

    async def _fetch_citations() -> None:
        # Fetch biblio with citations from EPO
        async with sem:
            biblio_response = await epo.get_biblio_with_citations(doc)

        patent_refs = biblio_response["patent_refs"]
        npl_refs = biblio_response["npl_refs"]

        # Resolve NPL refs against Semantic Scholar
        resolved_npl: list[dict[str, Any]] = []
        if s2 is not None and npl_refs:
            # Build identifiers for batch resolve
            identifiers = []
            for npl in npl_refs:
                if npl["doi"]:
                    identifiers.append(f"DOI:{npl['doi']}")
                else:
                    identifiers.append(npl["raw"][:200])  # title search fallback

            try:
                s2_results = await s2.batch_resolve(
                    identifiers, fields="standard", retry=retry
                )
            except Exception:
                logger.warning("npl_resolution_failed patent=%s", patent_id)
                s2_results = [None] * len(npl_refs)

            for npl, s2_data in zip(npl_refs, s2_results, strict=True):
                entry: dict[str, Any] = {"raw": npl["raw"]}
                if s2_data is not None:
                    entry["paper"] = s2_data
                    entry["confidence"] = "high" if npl["doi"] else "medium"
                else:
                    entry["confidence"] = None
                resolved_npl.append(entry)
        else:
            resolved_npl = [{"raw": n["raw"], "confidence": None} for n in npl_refs]

        result["citations"] = {
            "patent_refs": patent_refs,
            "npl_refs": resolved_npl,
        }

    # Add to section_map:
    section_map["citations"] = _fetch_citations
```

Also add `get_biblio_with_citations` to `EpoClient`:

```python
async def get_biblio_with_citations(self, doc: DocdbNumber) -> dict[str, Any]:
    """Fetch biblio with cited references for a patent."""
    inp = self._to_docdb_input(doc)
    async with self._lock:
        response = await asyncio.to_thread(
            self._client.published_data,
            "publication",
            inp,
            endpoint="biblio",
        )
    self._check_throttle(response)
    return parse_citations_from_biblio(response.content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_patent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Update the get_patent tool to pass bundle.s2 for NPL resolution**

In `register_patent_tools`, update the `get_patent` tool's `_execute` inner function to pass `s2=bundle.s2`:

```python
async def _execute(*, retry: bool = True) -> str:
    return await _get_patent_execute(
        patent_number=patent_number,
        sections=sections,
        epo=bundle.epo,
        cache=bundle.cache,
        s2=bundle.s2,
        retry=retry,
    )
```

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_tools_patent.py src/scholar_mcp/_epo_client.py tests/test_tools_patent.py
git commit -m "feat: add citations section to get_patent with NPL resolution"
```

---

### Task 19: get_citing_patents Tool

**Files:**
- Modify: `src/scholar_mcp/_tools_patent.py`
- Modify: `tests/test_tools_patent.py`

- [ ] **Step 1: Write tests for get_citing_patents**

```python
class TestGetCitingPatentsLogic:
    async def test_citing_from_epo(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_citing_patents_execute

        mock_epo.search = AsyncMock(return_value={
            "total_count": 1,
            "references": [{"country": "EP", "number": "9999999", "kind": "A1"}],
        })
        mock_epo.get_biblio = AsyncMock(return_value={
            "title": "Citing Patent",
            "publication_number": "EP.9999999.A1",
            "applicants": [],
            "inventors": [],
            "abstract": "",
            "publication_date": "",
            "filing_date": "",
            "priority_date": "",
            "family_id": "",
            "classifications": [],
            "url": "",
        })

        result_json = await _get_citing_patents_execute(
            paper_id="10.1234/test",
            epo=mock_epo,
            cache=cache,
            openalex=None,
            limit=10,
        )
        result = json.loads(result_json)
        assert len(result["patents"]) >= 1
        assert result["patents"][0]["match_source"] == "epo_search"

    async def test_empty_results(self, mock_epo, cache) -> None:
        from scholar_mcp._tools_patent import _get_citing_patents_execute

        mock_epo.search = AsyncMock(return_value={
            "total_count": 0,
            "references": [],
        })
        result_json = await _get_citing_patents_execute(
            paper_id="10.9999/nonexistent",
            epo=mock_epo,
            cache=cache,
            openalex=None,
            limit=10,
        )
        result = json.loads(result_json)
        assert result["patents"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_patent.py::TestGetCitingPatentsLogic -v`
Expected: FAIL — `ImportError: cannot import name '_get_citing_patents_execute'`

- [ ] **Step 3: Implement get_citing_patents**

Add to `src/scholar_mcp/_tools_patent.py`:

```python
async def _get_citing_patents_execute(
    *,
    paper_id: str,
    epo: EpoClient,
    cache: ScholarCache,
    openalex: Any | None = None,
    limit: int = 10,
    retry: bool = True,
) -> str:
    """Find patents citing a given paper. Best-effort, incomplete coverage."""
    patents: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()

    # Strategy 1: Search EPO OPS for the DOI in cited references
    # EPO CQL ct= field searches cited documents
    cql = f'ct="{paper_id}"'
    try:
        search_result = await epo.search(cql, range_begin=1, range_end=limit)
        for ref in search_result.get("references", []):
            doc = DocdbNumber(ref["country"], ref["number"], ref.get("kind", ""))
            patent_id = doc.docdb
            if patent_id in seen_numbers:
                continue
            seen_numbers.add(patent_id)
            # Fetch biblio for each result
            try:
                biblio = await epo.get_biblio(doc)
                biblio["match_source"] = "epo_search"
                patents.append(biblio)
            except Exception:
                logger.warning("citing_patent_biblio_failed patent=%s", patent_id)
    except Exception:
        logger.warning("citing_patent_epo_search_failed paper=%s", paper_id)

    # Strategy 2: Query OpenAlex for patent citations (future enhancement)
    # OpenAlex support for patent citations is limited; placeholder for now
    if openalex is not None:
        pass  # TODO: implement when OpenAlex patent citation API is available

    return json.dumps({
        "paper_id": paper_id,
        "patents": patents[:limit],
        "note": (
            "Coverage is incomplete. Results come from EPO OPS citation search "
            "and may not capture all patent-to-paper citations."
        ),
    })
```

Add the tool registration in `register_patent_tools`:

```python
@mcp.tool(
    tags={"patent"},
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
async def get_citing_patents(
    paper_id: str,
    limit: int = 10,
    bundle: ServiceBundle = Depends(get_bundle),
) -> str:
    """Find patents that cite a given academic paper.

    Coverage is incomplete -- relies on EPO OPS citation search and
    OpenAlex, which do not capture all patent-to-paper citations.
    Best results with well-known, highly-cited papers. Returns
    confirmed matches only, not an exhaustive list. Provide a DOI
    for best matching accuracy.

    Args:
        paper_id: Paper identifier (DOI preferred, also accepts S2 ID).
        limit: Maximum number of patents to return.
    """
    assert bundle.epo is not None

    async def _execute(*, retry: bool = True) -> str:
        return await _get_citing_patents_execute(
            paper_id=paper_id,
            epo=bundle.epo,
            cache=bundle.cache,
            openalex=bundle.openalex,
            limit=limit,
            retry=retry,
        )

    try:
        return await _execute(retry=False)
    except RateLimitedError:
        task_id = bundle.tasks.submit(
            _execute(retry=True), tool="get_citing_patents"
        )
        return json.dumps({
            "queued": True,
            "task_id": task_id,
            "tool": "get_citing_patents",
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_patent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_tools_patent.py tests/test_tools_patent.py
git commit -m "feat: add get_citing_patents tool with EPO search"
```

---

### Task 20: Extend batch_resolve with Patent Support

**Files:**
- Modify: `src/scholar_mcp/_tools_utility.py`
- Modify: `tests/test_tools_utility.py` (or create if not exists)

- [ ] **Step 1: Write tests for patent detection in batch_resolve**

```python
"""Tests for batch_resolve patent extension."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from scholar_mcp._patent_numbers import is_patent_number


class TestBatchResolvePatentDetection:
    def test_doi_not_patent(self) -> None:
        assert is_patent_number("10.1234/abc") is False

    def test_ep_is_patent(self) -> None:
        assert is_patent_number("EP1234567A1") is True

    def test_doi_prefix_not_patent(self) -> None:
        assert is_patent_number("DOI:10.1234/abc") is False
```

For the full batch_resolve integration test, read the existing `_tools_utility.py` to understand the current implementation, then add tests that pass patent numbers and verify they get routed to EPO:

```python
class TestBatchResolveWithPatents:
    async def test_patent_resolved_via_epo(self, bundle, mock_epo) -> None:
        """When a patent number is in the batch, it's resolved via EPO."""
        # This test requires modifying the bundle to have an epo client
        # Implementation depends on how batch_resolve accesses the bundle
        pass  # Flesh out after reading current batch_resolve implementation
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ -k "batch_resolve" -v`

- [ ] **Step 3: Extend batch_resolve in _tools_utility.py**

Read the current `batch_resolve` tool implementation first. Then modify it to:

1. Accept an optional `type` field per identifier (or as a parallel list)
2. For each identifier, check if `type == "patent"` or (type is None and `is_patent_number(raw)`)
3. Route patent identifiers to `bundle.epo.get_biblio()` instead of `bundle.s2.batch_resolve()`
4. Add `source_type: "paper" | "patent"` to each result

The exact modification depends on the current function signature. The key addition:

```python
from scholar_mcp._patent_numbers import is_patent_number, normalize

# Inside batch_resolve logic:
for i, raw in enumerate(identifiers):
    item_type = types[i] if types else None
    if item_type == "patent" or (item_type is None and is_patent_number(raw)):
        # Route to EPO
        patent_ids.append((i, raw))
    else:
        # Route to S2 as before
        paper_ids.append((i, raw))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_tools_utility.py tests/
git commit -m "feat: extend batch_resolve with patent number support"
```

---

### Task 21: Documentation Update (Phase 3)

**Files:**
- Modify: `docs/tools/index.md`
- Modify: `README.md`

- [ ] **Step 1: Add get_citing_patents documentation**

Document the tool with its limitations clearly stated. Include usage examples.

- [ ] **Step 2: Update batch_resolve documentation**

Document the new `type` parameter and auto-detection behavior.

- [ ] **Step 3: Add cross-referencing section**

Add a "Cross-Referencing Papers and Patents" section to the docs explaining the patent→paper (NPL resolution) and paper→patent (get_citing_patents) workflows, with their coverage limitations.

- [ ] **Step 4: Commit**

```bash
git add docs/ README.md
git commit -m "docs: add cross-referencing and batch_resolve patent documentation"
```

---

## Verification Checklist

After all phases are complete, verify:

- [ ] `uv run pytest tests/ -v` — all tests pass
- [ ] `uv run ruff check src/ tests/` — no lint errors
- [ ] `uv run mypy src/scholar_mcp/` — no type errors
- [ ] Server starts without EPO credentials: `SCHOLAR_MCP_EPO_CONSUMER_KEY= scholar-mcp serve --transport stdio` — patent tools hidden, paper tools work
- [ ] Server starts with EPO credentials: patent tools visible
- [ ] `search_patents` returns results for a known query
- [ ] `get_patent` returns biblio for a known patent number
- [ ] `get_patent` with all sections returns complete data
- [ ] `get_citing_patents` returns results for a well-cited paper DOI
- [ ] `batch_resolve` correctly routes patent numbers to EPO

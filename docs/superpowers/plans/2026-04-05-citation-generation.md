# Citation Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `generate_citations` MCP tool that formats Semantic Scholar paper metadata as BibTeX, CSL-JSON, or RIS citations.

**Architecture:** Three new modules — `_citation_names.py` (author name parsing), `_citation_formatter.py` (pure formatting functions for all three output formats), and `_tools_citation.py` (MCP tool registration and orchestration). The tool resolves papers via `batch_resolve`, optionally enriches via OpenAlex, then delegates to the appropriate formatter. All formatting logic is pure functions with no side effects.

**Tech Stack:** Python 3.11+, `unicodedata` (stdlib) for ASCII folding, `json` (stdlib) for CSL-JSON output. No new dependencies.

---

## File Structure

| File | Responsibility |
|------|---------------|
| Create: `src/scholar_mcp/_citation_names.py` | `AuthorName` NamedTuple + `parse_author_name()` — splits S2 author name strings into structured parts |
| Create: `src/scholar_mcp/_citation_formatter.py` | Pure formatting: `format_bibtex()`, `format_csl_json()`, `format_ris()`, plus helpers for key generation, type inference, BibTeX escaping |
| Create: `src/scholar_mcp/_tools_citation.py` | MCP tool `generate_citations` — resolves papers, enriches, dispatches to formatters |
| Modify: `src/scholar_mcp/_server_tools.py:38-41` | Add `register_citation_tools` import and call |
| Create: `tests/test_citation_names.py` | Unit tests for name parsing |
| Create: `tests/test_citation_formatter.py` | Unit tests for all three formatters + key generation + type inference + escaping |
| Create: `tests/test_tools_citation.py` | Integration tests for the MCP tool (mocked S2/OpenAlex) |
| Modify: `docs/tools/index.md` | Add `generate_citations` documentation |
| Modify: `README.md` | Add citation generation to feature list |

---

### Task 1: Author Name Parsing

**Files:**
- Create: `src/scholar_mcp/_citation_names.py`
- Create: `tests/test_citation_names.py`

- [ ] **Step 1: Write failing tests for name parsing**

```python
# tests/test_citation_names.py
"""Tests for author name parsing."""

from __future__ import annotations

import pytest

from scholar_mcp._citation_names import AuthorName, parse_author_name


@pytest.mark.parametrize(
    "name, expected",
    [
        # Simple two-part name
        ("John Smith", AuthorName(first="John", last="Smith", prefix="", suffix="")),
        # Prefix "van"
        (
            "Jan van Houten",
            AuthorName(first="Jan", last="Houten", prefix="van", suffix=""),
        ),
        # Multi-word prefix "de la"
        (
            "Maria de la Cruz",
            AuthorName(first="Maria", last="Cruz", prefix="de la", suffix=""),
        ),
        # Prefix "von"
        (
            "Klaus von Klitzing",
            AuthorName(first="Klaus", last="Klitzing", prefix="von", suffix=""),
        ),
        # Suffix "Jr."
        (
            "Robert Downey Jr.",
            AuthorName(first="Robert", last="Downey", prefix="", suffix="Jr."),
        ),
        # Suffix "III"
        (
            "William Gates III",
            AuthorName(first="William", last="Gates", prefix="", suffix="III"),
        ),
        # Hyphenated first name
        (
            "Jean-Pierre Dupont",
            AuthorName(first="Jean-Pierre", last="Dupont", prefix="", suffix=""),
        ),
        # Single-word name (fallback)
        ("Madonna", AuthorName(first="", last="Madonna", prefix="", suffix="")),
        # Prefix + suffix combo
        (
            "Jan van der Berg Jr.",
            AuthorName(first="Jan", last="Berg", prefix="van der", suffix="Jr."),
        ),
        # Empty string
        ("", AuthorName(first="", last="", prefix="", suffix="")),
        # Three-part name without prefix
        (
            "Mary Jane Watson",
            AuthorName(first="Mary Jane", last="Watson", prefix="", suffix=""),
        ),
    ],
)
def test_parse_author_name(name: str, expected: AuthorName) -> None:
    assert parse_author_name(name) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_names.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scholar_mcp._citation_names'`

- [ ] **Step 3: Implement `_citation_names.py`**

```python
# src/scholar_mcp/_citation_names.py
"""Author name parsing for citation formatting."""

from __future__ import annotations

from typing import NamedTuple

# Lowercase prefixes that appear between first name and surname.
_PREFIXES = frozenset({
    "van", "von", "de", "del", "della", "di", "du", "el", "la", "le",
    "den", "der", "het", "ten", "ter", "dos", "das", "al",
})

# Suffixes that follow the surname.
_SUFFIXES = frozenset({
    "jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v",
})


class AuthorName(NamedTuple):
    """Parsed author name components."""

    first: str
    last: str
    prefix: str
    suffix: str


def parse_author_name(name: str) -> AuthorName:
    """Parse an author name string into structured components.

    Handles prefixes (van, de, von, ...), suffixes (Jr., III, ...),
    hyphenated first names, and single-word names.

    Args:
        name: Full author name as a single string (e.g. "Jan van Houten").

    Returns:
        Parsed AuthorName with first, last, prefix, and suffix fields.
    """
    if not name or not name.strip():
        return AuthorName(first="", last="", prefix="", suffix="")

    parts = name.strip().split()

    if len(parts) == 1:
        return AuthorName(first="", last=parts[0], prefix="", suffix="")

    # Extract suffix from the end.
    suffix = ""
    if parts[-1].lower().rstrip(".") in {s.rstrip(".") for s in _SUFFIXES}:
        suffix = parts.pop()

    if len(parts) == 1:
        return AuthorName(first="", last=parts[0], prefix="", suffix=suffix)

    # The last remaining token is the surname.
    last = parts.pop()

    # Scan remaining tokens for prefix particles.
    # First token(s) are given name; contiguous lowercase prefix tokens
    # before the surname are the prefix.
    first_parts: list[str] = []
    prefix_parts: list[str] = []

    # Walk from the end of remaining parts backward to find prefix.
    i = len(parts) - 1
    while i >= 0 and parts[i].lower() in _PREFIXES:
        prefix_parts.insert(0, parts[i])
        i -= 1

    first_parts = parts[: i + 1]

    # If everything got consumed as prefix, the first prefix token is
    # actually part of the given name.
    if not first_parts and prefix_parts:
        first_parts = [prefix_parts.pop(0)]

    return AuthorName(
        first=" ".join(first_parts),
        last=last,
        prefix=" ".join(prefix_parts),
        suffix=suffix,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_names.py -v`
Expected: All 11 parametrized cases PASS

- [ ] **Step 5: Run linter**

Run: `cd /mnt/code/scholar-mcp && uv run ruff check src/scholar_mcp/_citation_names.py && uv run ruff format --check src/scholar_mcp/_citation_names.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_citation_names.py tests/test_citation_names.py
git commit -m "feat: add author name parser for citation formatting"
```

---

### Task 2: BibTeX Key Generation, Type Inference, and Escaping

**Files:**
- Create: `src/scholar_mcp/_citation_formatter.py` (initial scaffold with helpers)
- Create: `tests/test_citation_formatter.py` (initial tests for helpers)

- [ ] **Step 1: Write failing tests for key generation, type inference, and escaping**

```python
# tests/test_citation_formatter.py
"""Tests for citation formatters."""

from __future__ import annotations

import pytest

from scholar_mcp._citation_formatter import (
    escape_bibtex,
    generate_bibtex_key,
    infer_entry_type,
)


class TestGenerateBibtexKey:
    def test_simple_key(self) -> None:
        paper = {
            "authors": [{"name": "Ashish Vaswani"}],
            "year": 2017,
        }
        assert generate_bibtex_key(paper, set()) == "vaswani2017"

    def test_deduplication(self) -> None:
        paper = {
            "authors": [{"name": "John Smith"}],
            "year": 2024,
        }
        seen: set[str] = set()
        k1 = generate_bibtex_key(paper, seen)
        k2 = generate_bibtex_key(paper, seen)
        k3 = generate_bibtex_key(paper, seen)
        assert k1 == "smith2024"
        assert k2 == "smith2024a"
        assert k3 == "smith2024b"

    def test_prefix_in_name(self) -> None:
        paper = {
            "authors": [{"name": "Jan van Houten"}],
            "year": 2020,
        }
        assert generate_bibtex_key(paper, set()) == "houten2020"

    def test_no_authors(self) -> None:
        paper: dict = {"authors": [], "year": 2024}
        assert generate_bibtex_key(paper, set()) == "anon2024"

    def test_no_year(self) -> None:
        paper = {"authors": [{"name": "Smith"}], "year": None}
        assert generate_bibtex_key(paper, set()) == "smith"

    def test_unicode_folding(self) -> None:
        paper = {
            "authors": [{"name": "José García"}],
            "year": 2023,
        }
        assert generate_bibtex_key(paper, set()) == "garcia2023"


class TestInferEntryType:
    def test_conference_venue(self) -> None:
        assert infer_entry_type({"venue": "NeurIPS Proceedings"}) == "inproceedings"

    def test_workshop_venue(self) -> None:
        assert infer_entry_type({"venue": "ICML Workshop"}) == "inproceedings"

    def test_symposium_venue(self) -> None:
        assert infer_entry_type({"venue": "IEEE Symposium"}) == "inproceedings"

    def test_arxiv_preprint(self) -> None:
        paper = {"venue": "", "externalIds": {"ArXiv": "2401.00001"}}
        assert infer_entry_type(paper) == "misc"

    def test_journal_fallback(self) -> None:
        assert infer_entry_type({"venue": "Nature"}) == "article"

    def test_empty_venue_no_arxiv(self) -> None:
        assert infer_entry_type({"venue": ""}) == "article"


class TestEscapeBibtex:
    def test_special_chars(self) -> None:
        assert escape_bibtex("R&D") == r"R\&D"
        assert escape_bibtex("100%") == r"100\%"
        assert escape_bibtex("C#") == r"C\#"

    def test_unicode_accents(self) -> None:
        result = escape_bibtex("José")
        assert result == r"Jos{\'e}"

    def test_umlaut(self) -> None:
        result = escape_bibtex("Müller")
        assert result == r"M{\"u}ller"

    def test_plain_text_unchanged(self) -> None:
        assert escape_bibtex("Hello World") == "Hello World"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scholar_mcp._citation_formatter'`

- [ ] **Step 3: Implement helpers in `_citation_formatter.py`**

```python
# src/scholar_mcp/_citation_formatter.py
"""Citation formatting for BibTeX, CSL-JSON, and RIS."""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from ._citation_names import parse_author_name

# BibTeX special characters that must be escaped.
_BIBTEX_ESCAPES: dict[str, str] = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "$": r"\$",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Common Unicode → LaTeX replacements (combining diacritics approach).
_UNICODE_TO_LATEX: dict[str, str] = {
    "\u0300": "`",   # grave
    "\u0301": "'",   # acute
    "\u0302": "^",   # circumflex
    "\u0303": "~",   # tilde
    "\u0304": "=",   # macron
    "\u0308": '"',   # diaeresis / umlaut
    "\u030C": "v",   # caron
    "\u0327": "c",   # cedilla
    "\u0328": "k",   # ogonek
}

# Conference keywords for entry type inference.
_CONFERENCE_KEYWORDS = ("conference", "proceedings", "workshop", "symposium")


def escape_bibtex(text: str) -> str:
    """Escape special characters and convert Unicode to LaTeX commands.

    Args:
        text: Raw text string.

    Returns:
        BibTeX-safe string with special chars escaped and common
        Unicode accented characters converted to LaTeX commands.
    """
    # First handle Unicode → LaTeX via NFD decomposition.
    nfd = unicodedata.normalize("NFD", text)
    result: list[str] = []
    i = 0
    while i < len(nfd):
        ch = nfd[i]
        # Check if next char is a combining diacritical mark.
        if (
            i + 1 < len(nfd)
            and unicodedata.category(nfd[i + 1]) == "Mn"
            and nfd[i + 1] in _UNICODE_TO_LATEX
        ):
            accent = _UNICODE_TO_LATEX[nfd[i + 1]]
            base = ch
            # Escape the base char if needed.
            base = _BIBTEX_ESCAPES.get(base, base)
            result.append(f"{{\\{accent}{base}}}")
            i += 2
        else:
            result.append(_BIBTEX_ESCAPES.get(ch, ch))
            i += 1
    return "".join(result)


def _ascii_fold(text: str) -> str:
    """Fold Unicode to ASCII for BibTeX keys."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def generate_bibtex_key(paper: dict[str, Any], seen_keys: set[str]) -> str:
    """Generate a BibTeX citation key in authorYear style.

    Args:
        paper: Paper metadata dict with ``authors`` and ``year``.
        seen_keys: Set of already-used keys (mutated to include the new key).

    Returns:
        Unique citation key string.
    """
    authors = paper.get("authors") or []
    if authors:
        parsed = parse_author_name(authors[0].get("name", ""))
        last = _ascii_fold(parsed.last) if parsed.last else "anon"
    else:
        last = "anon"

    year = paper.get("year")
    base = f"{last}{year}" if year else last

    if base not in seen_keys:
        seen_keys.add(base)
        return base

    for suffix_ord in range(ord("a"), ord("z") + 1):
        candidate = f"{base}{chr(suffix_ord)}"
        if candidate not in seen_keys:
            seen_keys.add(candidate)
            return candidate

    # Extremely unlikely fallback.
    candidate = f"{base}_{len(seen_keys)}"
    seen_keys.add(candidate)
    return candidate


def infer_entry_type(paper: dict[str, Any]) -> str:
    """Infer BibTeX entry type from paper metadata.

    Args:
        paper: Paper metadata dict.

    Returns:
        One of ``"article"``, ``"inproceedings"``, or ``"misc"``.
    """
    venue = (paper.get("venue") or "").lower()
    if any(kw in venue for kw in _CONFERENCE_KEYWORDS):
        return "inproceedings"
    external_ids = paper.get("externalIds") or {}
    if external_ids.get("ArXiv") and not venue:
        return "misc"
    return "article"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `cd /mnt/code/scholar-mcp && uv run ruff check src/scholar_mcp/_citation_formatter.py && uv run ruff format --check src/scholar_mcp/_citation_formatter.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: add BibTeX key generation, type inference, and escaping"
```

---

### Task 3: BibTeX Formatter

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py`
- Modify: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing tests for BibTeX formatting**

Append to `tests/test_citation_formatter.py`:

```python
from scholar_mcp._citation_formatter import format_bibtex


class TestFormatBibtex:
    def test_single_article(self) -> None:
        papers = [
            {
                "paperId": "abc123",
                "title": "Attention Is All You Need",
                "year": 2017,
                "venue": "Neural Information Processing Systems",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Noam Shazeer"},
                ],
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "abstract": "The dominant sequence transduction models...",
            }
        ]
        result = format_bibtex(papers, [])
        assert "@article{vaswani2017," in result
        assert "author = {Vaswani, Ashish and Shazeer, Noam}" in result
        assert "title = {{Attention Is All You Need}}" in result
        assert "year = {2017}" in result
        assert "doi = {10.5555/3295222.3295349}" in result

    def test_conference_paper(self) -> None:
        papers = [
            {
                "title": "BERT",
                "year": 2019,
                "venue": "Conference on NLP",
                "authors": [{"name": "Jacob Devlin"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        assert "@inproceedings{devlin2019," in result
        assert "booktitle = {Conference on NLP}" in result

    def test_arxiv_preprint(self) -> None:
        papers = [
            {
                "title": "Some Preprint",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Jane Doe"}],
                "externalIds": {"ArXiv": "2401.00001"},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        assert "@misc{doe2024," in result
        assert "eprint = {2401.00001}" in result
        assert "archiveprefix = {arXiv}" in result

    def test_errors_as_comments(self) -> None:
        errors = [
            {"identifier": "DOI:10.1/missing", "reason": "not found"},
        ]
        result = format_bibtex([], errors)
        assert "% Could not resolve: DOI:10.1/missing (not found)" in result

    def test_missing_fields_omitted(self) -> None:
        papers = [
            {
                "title": "Minimal Paper",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Smith"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        assert "doi" not in result.lower().split("=")[0] if "=" in result else True
        assert "url" not in result.lower().replace("@", "").split("{")[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py::TestFormatBibtex -v`
Expected: FAIL with `ImportError: cannot import name 'format_bibtex'`

- [ ] **Step 3: Implement `format_bibtex` in `_citation_formatter.py`**

Append to `src/scholar_mcp/_citation_formatter.py`:

```python
def _format_bibtex_author(paper: dict[str, Any]) -> str:
    """Format author list for BibTeX: {Last}, First and {Last}, First."""
    authors = paper.get("authors") or []
    parts: list[str] = []
    for author in authors:
        parsed = parse_author_name(author.get("name", ""))
        if parsed.prefix:
            parts.append(f"{parsed.prefix} {parsed.last}, {parsed.first}")
        elif parsed.first:
            parts.append(f"{parsed.last}, {parsed.first}")
        else:
            parts.append(parsed.last)
        if parsed.suffix:
            parts[-1] += f", {parsed.suffix}"
    return " and ".join(parts)


def _paper_url(paper: dict[str, Any]) -> str | None:
    """Extract best URL from paper metadata."""
    oa = paper.get("openAccessPdf")
    if oa and isinstance(oa, dict) and oa.get("url"):
        return oa["url"]
    doi = (paper.get("externalIds") or {}).get("DOI")
    if doi:
        return f"https://doi.org/{doi}"
    return None


def format_bibtex(
    papers: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> str:
    """Format papers as BibTeX entries.

    Args:
        papers: List of paper metadata dicts.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        BibTeX string with all entries and error comments.
    """
    lines: list[str] = []

    for error in errors:
        ident = error.get("identifier", "unknown")
        reason = error.get("reason", "unknown error")
        lines.append(f"% Could not resolve: {ident} ({reason})")

    if errors and papers:
        lines.append("")

    seen_keys: set[str] = set()
    for paper in papers:
        entry_type = infer_entry_type(paper)
        key = generate_bibtex_key(paper, seen_keys)

        fields: list[str] = []

        author_str = _format_bibtex_author(paper)
        if author_str:
            fields.append(f"  author = {{{author_str}}}")

        title = paper.get("title")
        if title:
            fields.append(f"  title = {{{{{escape_bibtex(title)}}}}}")

        year = paper.get("year")
        if year:
            fields.append(f"  year = {{{year}}}")

        venue = paper.get("venue")
        if venue:
            if entry_type == "inproceedings":
                fields.append(f"  booktitle = {{{escape_bibtex(venue)}}}")
            else:
                fields.append(f"  journal = {{{escape_bibtex(venue)}}}")

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        if doi:
            fields.append(f"  doi = {{{doi}}}")

        url = _paper_url(paper)
        if url:
            fields.append(f"  url = {{{url}}}")

        abstract = paper.get("abstract")
        if abstract:
            fields.append(f"  abstract = {{{escape_bibtex(abstract)}}}")

        arxiv = external_ids.get("ArXiv")
        if arxiv:
            fields.append(f"  eprint = {{{arxiv}}}")
            fields.append("  archiveprefix = {arXiv}")

        entry = f"@{entry_type}{{{key},\n"
        entry += ",\n".join(fields)
        entry += ",\n}"
        lines.append(entry)

    return "\n\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `cd /mnt/code/scholar-mcp && uv run ruff check src/scholar_mcp/_citation_formatter.py && uv run ruff format --check src/scholar_mcp/_citation_formatter.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: add BibTeX citation formatter"
```

---

### Task 4: CSL-JSON Formatter

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py`
- Modify: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing tests for CSL-JSON formatting**

Append to `tests/test_citation_formatter.py`:

```python
from scholar_mcp._citation_formatter import format_csl_json


class TestFormatCslJson:
    def test_single_paper(self) -> None:
        papers = [
            {
                "title": "Attention Is All You Need",
                "year": 2017,
                "venue": "Neural Information Processing Systems",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Jan van Houten"},
                ],
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "abstract": "The dominant sequence...",
            }
        ]
        result = json.loads(format_csl_json(papers, []))
        assert len(result["citations"]) == 1
        assert result["errors"] == []
        entry = result["citations"][0]
        assert entry["title"] == "Attention Is All You Need"
        assert entry["type"] == "article-journal"
        assert entry["issued"] == {"date-parts": [[2017]]}
        assert entry["author"][0] == {"family": "Vaswani", "given": "Ashish"}
        assert entry["author"][1] == {
            "family": "Houten",
            "given": "Jan",
            "non-dropping-particle": "van",
        }

    def test_errors_in_output(self) -> None:
        errors = [{"identifier": "bad_id", "reason": "not found"}]
        result = json.loads(format_csl_json([], errors))
        assert result["citations"] == []
        assert len(result["errors"]) == 1
        assert result["errors"][0]["identifier"] == "bad_id"

    def test_missing_year(self) -> None:
        papers = [
            {
                "title": "No Year",
                "year": None,
                "venue": "",
                "authors": [{"name": "Smith"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = json.loads(format_csl_json(papers, []))
        assert "issued" not in result["citations"][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py::TestFormatCslJson -v`
Expected: FAIL with `ImportError: cannot import name 'format_csl_json'`

- [ ] **Step 3: Implement `format_csl_json` in `_citation_formatter.py`**

Append to `src/scholar_mcp/_citation_formatter.py`:

```python
_CSL_TYPE_MAP: dict[str, str] = {
    "article": "article-journal",
    "inproceedings": "paper-conference",
    "misc": "article",
}


def _csl_author(paper: dict[str, Any]) -> list[dict[str, str]]:
    """Format authors for CSL-JSON."""
    authors = paper.get("authors") or []
    result: list[dict[str, str]] = []
    for author in authors:
        parsed = parse_author_name(author.get("name", ""))
        entry: dict[str, str] = {}
        if parsed.last:
            entry["family"] = parsed.last
        if parsed.first:
            entry["given"] = parsed.first
        if parsed.prefix:
            entry["non-dropping-particle"] = parsed.prefix
        if parsed.suffix:
            entry["suffix"] = parsed.suffix
        if entry:
            result.append(entry)
    return result


def format_csl_json(
    papers: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> str:
    """Format papers as CSL-JSON.

    Args:
        papers: List of paper metadata dicts.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        JSON string with ``citations`` array and ``errors`` array.
    """
    seen_keys: set[str] = set()
    citations: list[dict[str, Any]] = []

    for paper in papers:
        entry_type = infer_entry_type(paper)
        key = generate_bibtex_key(paper, seen_keys)

        entry: dict[str, Any] = {
            "id": key,
            "type": _CSL_TYPE_MAP.get(entry_type, "article-journal"),
        }

        title = paper.get("title")
        if title:
            entry["title"] = title

        csl_authors = _csl_author(paper)
        if csl_authors:
            entry["author"] = csl_authors

        year = paper.get("year")
        if year:
            entry["issued"] = {"date-parts": [[year]]}

        venue = paper.get("venue")
        if venue:
            entry["container-title"] = venue

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        if doi:
            entry["DOI"] = doi

        url = _paper_url(paper)
        if url:
            entry["URL"] = url

        abstract = paper.get("abstract")
        if abstract:
            entry["abstract"] = abstract

        citations.append(entry)

    error_list = [
        {"identifier": e.get("identifier", "unknown"), "reason": e.get("reason", "unknown error")}
        for e in errors
    ]

    return json.dumps({"citations": citations, "errors": error_list})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `cd /mnt/code/scholar-mcp && uv run ruff check src/scholar_mcp/_citation_formatter.py && uv run ruff format --check src/scholar_mcp/_citation_formatter.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: add CSL-JSON citation formatter"
```

---

### Task 5: RIS Formatter

**Files:**
- Modify: `src/scholar_mcp/_citation_formatter.py`
- Modify: `tests/test_citation_formatter.py`

- [ ] **Step 1: Write failing tests for RIS formatting**

Append to `tests/test_citation_formatter.py`:

```python
from scholar_mcp._citation_formatter import format_ris


class TestFormatRis:
    def test_single_journal_article(self) -> None:
        papers = [
            {
                "title": "Attention Is All You Need",
                "year": 2017,
                "venue": "Nature",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Noam Shazeer"},
                ],
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "abstract": "The dominant sequence...",
            }
        ]
        result = format_ris(papers, [])
        assert "TY  - JOUR" in result
        assert "AU  - Vaswani, Ashish" in result
        assert "AU  - Shazeer, Noam" in result
        assert "TI  - Attention Is All You Need" in result
        assert "PY  - 2017///" in result
        assert "JO  - Nature" in result
        assert "DO  - 10.5555/3295222.3295349" in result
        assert "ER  -" in result

    def test_conference_paper(self) -> None:
        papers = [
            {
                "title": "BERT",
                "year": 2019,
                "venue": "Conference on NLP",
                "authors": [{"name": "Jacob Devlin"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_ris(papers, [])
        assert "TY  - CONF" in result
        assert "BT  - Conference on NLP" in result

    def test_errors_as_comments(self) -> None:
        errors = [{"identifier": "bad_id", "reason": "not found"}]
        result = format_ris([], errors)
        assert "% Could not resolve: bad_id (not found)" in result

    def test_multiple_papers_separated(self) -> None:
        papers = [
            {
                "title": "Paper 1",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Smith"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            },
            {
                "title": "Paper 2",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Jones"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            },
        ]
        result = format_ris(papers, [])
        assert result.count("ER  -") == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py::TestFormatRis -v`
Expected: FAIL with `ImportError: cannot import name 'format_ris'`

- [ ] **Step 3: Implement `format_ris` in `_citation_formatter.py`**

Append to `src/scholar_mcp/_citation_formatter.py`:

```python
_RIS_TYPE_MAP: dict[str, str] = {
    "article": "JOUR",
    "inproceedings": "CONF",
    "misc": "GEN",
}


def _ris_author_line(paper: dict[str, Any]) -> list[str]:
    """Format one AU tag per author for RIS."""
    authors = paper.get("authors") or []
    lines: list[str] = []
    for author in authors:
        parsed = parse_author_name(author.get("name", ""))
        if parsed.prefix:
            name = f"{parsed.prefix} {parsed.last}"
        else:
            name = parsed.last
        if parsed.first:
            name = f"{name}, {parsed.first}"
        if parsed.suffix:
            name = f"{name}, {parsed.suffix}"
        if name:
            lines.append(f"AU  - {name}")
    return lines


def format_ris(
    papers: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> str:
    """Format papers as RIS records.

    Args:
        papers: List of paper metadata dicts.
        errors: List of error dicts with ``identifier`` and ``reason`` keys.

    Returns:
        RIS-formatted string with all records and error comments.
    """
    blocks: list[str] = []

    for error in errors:
        ident = error.get("identifier", "unknown")
        reason = error.get("reason", "unknown error")
        blocks.append(f"% Could not resolve: {ident} ({reason})")

    for paper in papers:
        entry_type = infer_entry_type(paper)
        ris_type = _RIS_TYPE_MAP.get(entry_type, "GEN")
        lines: list[str] = [f"TY  - {ris_type}"]

        lines.extend(_ris_author_line(paper))

        title = paper.get("title")
        if title:
            lines.append(f"TI  - {title}")

        year = paper.get("year")
        if year:
            lines.append(f"PY  - {year}///")

        venue = paper.get("venue")
        if venue:
            if entry_type == "inproceedings":
                lines.append(f"BT  - {venue}")
            else:
                lines.append(f"JO  - {venue}")

        external_ids = paper.get("externalIds") or {}
        doi = external_ids.get("DOI")
        if doi:
            lines.append(f"DO  - {doi}")

        url = _paper_url(paper)
        if url:
            lines.append(f"UR  - {url}")

        abstract = paper.get("abstract")
        if abstract:
            lines.append(f"AB  - {abstract}")

        lines.append("ER  -")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_citation_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run linter**

Run: `cd /mnt/code/scholar-mcp && uv run ruff check src/scholar_mcp/_citation_formatter.py && uv run ruff format --check src/scholar_mcp/_citation_formatter.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_citation_formatter.py tests/test_citation_formatter.py
git commit -m "feat: add RIS citation formatter"
```

---

### Task 6: MCP Tool Registration and Integration

**Files:**
- Create: `src/scholar_mcp/_tools_citation.py`
- Modify: `src/scholar_mcp/_server_tools.py:38-41`
- Create: `tests/test_tools_citation.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/test_tools_citation.py
"""Tests for generate_citations MCP tool."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_citation import register_citation_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_BASE = "https://api.openalex.org"

SAMPLE_PAPER = {
    "paperId": "abc123",
    "title": "Attention Is All You Need",
    "year": 2017,
    "venue": "Neural Information Processing Systems",
    "authors": [
        {"authorId": "1", "name": "Ashish Vaswani"},
        {"authorId": "2", "name": "Noam Shazeer"},
    ],
    "externalIds": {"DOI": "10.5555/3295222.3295349", "ArXiv": "1706.03762"},
    "abstract": "The dominant sequence transduction models...",
    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
    "citationCount": 90000,
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_citation_tools(app)
    return app


async def test_generate_bibtex_single(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex"},
            )
    text = result.content[0].text
    assert "@article{vaswani2017," in text  # NeurIPS detected as article (no "proceedings" keyword)
    assert "Vaswani, Ashish and Shazeer, Noam" in text


async def test_generate_csl_json(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "csl-json"},
            )
    data = json.loads(result.content[0].text)
    assert len(data["citations"]) == 1
    assert data["citations"][0]["title"] == "Attention Is All You Need"


async def test_generate_ris(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "ris"},
            )
    text = result.content[0].text
    assert "TY  - JOUR" in text
    assert "AU  - Vaswani, Ashish" in text


async def test_partial_resolution(mcp: FastMCP) -> None:
    """Papers that fail to resolve show as errors in output."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER, None])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123", "missing_id"], "format": "bibtex"},
            )
    text = result.content[0].text
    assert "@article{vaswani2017," in text
    assert "% Could not resolve: missing_id" in text


async def test_enrich_fills_venue(mcp: FastMCP) -> None:
    """OpenAlex enrichment adds venue when S2 venue is empty."""
    paper_no_venue = {
        **SAMPLE_PAPER,
        "venue": "",
        "externalIds": {"DOI": "10.1/enrich"},
    }
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[paper_no_venue])
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "primary_location": {
                        "source": {"display_name": "Nature Machine Intelligence"}
                    }
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex", "enrich": True},
            )
    text = result.content[0].text
    assert "Nature Machine Intelligence" in text


async def test_enrich_disabled(mcp: FastMCP) -> None:
    """When enrich=False, OpenAlex is not called."""
    paper_no_venue = {**SAMPLE_PAPER, "venue": ""}
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[paper_no_venue])
        )
        # No OpenAlex mock — would error if called.
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex", "enrich": False},
            )
    text = result.content[0].text
    assert "@" in text  # still produced an entry


async def test_empty_input_error(mcp: FastMCP) -> None:
    """Empty paper_ids list returns an error."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": [], "format": "bibtex"},
        )
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_queued_on_429(bundle: ServiceBundle) -> None:
    """generate_citations returns queued response on 429."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=[SAMPLE_PAPER])

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(side_effect=_side_effect)

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_citation_tools(app)

        async with Client(app) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex"},
            )
            data = json.loads(result.content[0].text)
            assert data["queued"] is True
            assert data["tool"] == "generate_citations"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_tools_citation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scholar_mcp._tools_citation'`

- [ ] **Step 3: Implement `_tools_citation.py`**

```python
# src/scholar_mcp/_tools_citation.py
"""Citation generation MCP tool."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._citation_formatter import format_bibtex, format_csl_json, format_ris
from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

_FORMATTERS = {
    "bibtex": format_bibtex,
    "csl-json": format_csl_json,
    "ris": format_ris,
}


async def _enrich_paper(
    paper: dict[str, Any], bundle: ServiceBundle
) -> None:
    """Enrich paper in-place with OpenAlex venue data if missing.

    Args:
        paper: Paper metadata dict (mutated in-place).
        bundle: Service bundle for API access.
    """
    if paper.get("venue"):
        return
    doi = (paper.get("externalIds") or {}).get("DOI")
    if not doi:
        return
    try:
        cached = await bundle.cache.get_openalex(doi)
        oa_data = cached if cached is not None else await bundle.openalex.get_by_doi(doi)
        if oa_data is None:
            return
        if cached is None:
            await bundle.cache.set_openalex(doi, oa_data)
        loc = oa_data.get("primary_location") or {}
        source = loc.get("source") or {}
        venue = source.get("display_name")
        if venue:
            paper["venue"] = venue
    except Exception:
        logger.debug("openalex_enrich_failed doi=%s", doi, exc_info=True)


def register_citation_tools(mcp: FastMCP) -> None:
    """Register citation generation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def generate_citations(
        paper_ids: list[str],
        format: Literal["bibtex", "csl-json", "ris"] = "bibtex",
        enrich: bool = True,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Generate formatted citations for one or more papers.

        Resolves papers via Semantic Scholar, optionally enriches with
        OpenAlex metadata, and formats as BibTeX, CSL-JSON, or RIS.

        Args:
            paper_ids: List of paper identifiers (S2 IDs, DOIs, arXiv IDs,
                etc.). Maximum 100.
            format: Output format — bibtex, csl-json, or ris.
            enrich: If True, attempt OpenAlex enrichment for missing venue
                data when a DOI is available.

        Returns:
            Formatted citation string, or a queued task response on rate
            limiting.
        """
        if not paper_ids:
            return json.dumps({"error": "paper_ids must not be empty"})

        if len(paper_ids) > 100:
            return json.dumps(
                {"error": "paper_ids must contain at most 100 identifiers"}
            )

        async def _execute(*, retry: bool = True) -> str:
            try:
                s2_results = await bundle.s2.batch_resolve(
                    paper_ids, fields=FIELD_SETS["full"], retry=retry
                )
            except httpx.HTTPStatusError as exc:
                return json.dumps(
                    {
                        "error": "upstream_error",
                        "status": exc.response.status_code,
                        "detail": exc.response.text[:200],
                    }
                )

            papers: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []

            for raw_id, s2_data in zip(paper_ids, s2_results, strict=True):
                if s2_data is not None:
                    papers.append(s2_data)
                else:
                    errors.append(
                        {"identifier": raw_id, "reason": "not found"}
                    )

            if enrich:
                for paper in papers:
                    await _enrich_paper(paper, bundle)

            if not papers and errors:
                formatter = _FORMATTERS[format]
                result = formatter([], errors)
                if not result.strip():
                    return json.dumps(
                        {
                            "error": "no_papers_resolved",
                            "failed": [e["identifier"] for e in errors],
                        }
                    )
                return result

            formatter = _FORMATTERS[format]
            return formatter(papers, errors)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="generate_citations"
            )
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task_id,
                    "tool": "generate_citations",
                }
            )
```

- [ ] **Step 4: Register in `_server_tools.py`**

Add to `src/scholar_mcp/_server_tools.py` after the `register_task_tools` block (after line 40):

```python
    from ._tools_citation import register_citation_tools

    register_citation_tools(mcp)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/code/scholar-mcp && uv run pytest tests/test_tools_citation.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run full test suite**

Run: `cd /mnt/code/scholar-mcp && uv run pytest -v`
Expected: All existing tests still PASS, all new tests PASS

- [ ] **Step 7: Run linter**

Run: `cd /mnt/code/scholar-mcp && uv run ruff check src/scholar_mcp/_tools_citation.py src/scholar_mcp/_server_tools.py && uv run ruff format --check src/scholar_mcp/_tools_citation.py src/scholar_mcp/_server_tools.py`
Expected: Clean

- [ ] **Step 8: Commit**

```bash
git add src/scholar_mcp/_tools_citation.py src/scholar_mcp/_server_tools.py tests/test_tools_citation.py
git commit -m "feat: add generate_citations MCP tool"
```

---

### Task 7: Documentation

**Files:**
- Modify: `docs/tools/index.md`
- Modify: `README.md`

- [ ] **Step 1: Read current docs to understand format**

Read `docs/tools/index.md` and `README.md` to match existing documentation style.

- [ ] **Step 2: Add `generate_citations` to tool reference**

Add a new section to `docs/tools/index.md` (in the appropriate position, likely after utility tools):

```markdown
### generate_citations

Generate formatted citations for one or more papers. Resolves papers via
Semantic Scholar, optionally enriches with OpenAlex metadata, and formats
as BibTeX, CSL-JSON, or RIS.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `paper_ids` | `list[str]` | (required) | Paper identifiers (S2 IDs, DOIs, arXiv IDs, etc.). Max 100. |
| `format` | `string` | `"bibtex"` | Output format: `bibtex`, `csl-json`, or `ris`. |
| `enrich` | `boolean` | `true` | Attempt OpenAlex enrichment for missing venue data. |

**BibTeX output** includes entry type inference (`@article`, `@inproceedings`,
`@misc`), proper author formatting (`{Last}, First`), title casing
preservation, DOI, arXiv eprint fields, and special character escaping.

**CSL-JSON output** returns `{"citations": [...], "errors": [...]}` — the
citations array contains standard CSL-JSON objects compatible with Zotero,
Mendeley, Pandoc, and other CSL processors.

**RIS output** uses standard RIS tags (`TY`, `AU`, `TI`, `PY`, `JO`/`BT`,
`DO`, `UR`, `AB`, `ER`).

Papers that fail to resolve are reported inline (BibTeX/RIS: as comments,
CSL-JSON: in the errors array) rather than failing the entire request.
```

- [ ] **Step 3: Add citation generation to README features**

Add citation generation to the feature list in `README.md` (find the existing features/tools section and add a bullet).

- [ ] **Step 4: Commit**

```bash
git add docs/tools/index.md README.md
git commit -m "docs: add generate_citations tool documentation"
```

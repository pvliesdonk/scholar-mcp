---
type: Reference
title: DOIs in free-text citations
description: What a DOI looks like, and the forms it takes inside the non-patent literature citations EPO returns.
subject_version: "Crossref DOI pattern guidance (2015); EPO OPS nplcit text observed September 2026"
valid_for: "Crossref DOI syntax as published; EPO OPS 3.x citation text"
generated:
  by: process:researching-references
  at: 2026-09-28
stale_after: 2027-09-28
status: draft
sources:
  - id: crossref-regex
    title: Crossref blog, "DOIs and matching regular expressions"
    resource: https://www.crossref.org/blog/dois-and-matching-regular-expressions/
    accessed: 2026-09-28
  - id: issue-482
    title: get_patent citations for DE102025108780A1 on the deployed 3.0.0-rc.0
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/482
    accessed: 2026-09-28
---

# DOIs in free-text citations

How to find a DOI inside a citation string. Prompted by #482: every
non-patent literature (NPL) reference on DE102025108780A1 stayed unresolved,
because the extractor required a literal `doi:` and the citations wrote
`https://doi.org/…` and `DOI 10.…`.

## Scope

- Covers: the character shape of a DOI, and the markers that introduce one in
  EPO `nplcit` text.
- Does not cover: title-based matching of citations without a DOI (#59), or
  resolving a DOI once found.
- Depended on by: `src/scholar_mcp/_epo_xml.py` (`extract_doi`, used by
  `parse_citations_xml` and by `get_patent`'s NPL resolution in
  `_tools_patent.py`).

## Claims

### DOI shape

- Crossref recommends `/^10.\d{4,9}/[-._;()/:A-Z0-9]+$/i` for modern DOIs.
  Of 74.9M DOIs Crossref had seen, it matched 74.4M; most of the remainder
  are early DOIs whose suffixes are not regular-expression friendly.
  [source: crossref-regex]
  [pins: tests/test_epo_xml.py::test_extract_doi]
- Parentheses are within that character set, so a DOI can contain them, as
  in `10.1016/S0140-6736(97)11096-0`. [source: crossref-regex]
  [pins: tests/test_epo_xml.py::test_extract_doi]
- Many early John Wiley & Sons DOIs are "not expression friendly";
  `/^10.1002/[^\s]+$/i` catches 300K more. Crossref's further patterns for
  the remainder include suffixes with `<…:…>` segments.
  [source: crossref-regex] [pins: tests/test_epo_xml.py::test_extract_doi]
- A DOI scraped from text tends to carry trailing characters: even the
  recommended expression catches DOIs ending with periods, colons, semicolons,
  hyphens and underscores that belong to the surrounding text.
  [source: crossref-regex] [pins: tests/test_epo_xml.py::test_extract_doi]
- The pattern is case-insensitive. [source: crossref-regex]

### Forms in EPO citation text

- EPO NPL citations write a DOI as a resolver URL,
  `https://doi.org/10.1038/nature14539`, followed by German retrieval text
  `[abgerufen am 2018-12-17]`, and also as `DOI 10.1109/TSM.2017.2676245`
  with no colon. Both occur on DE102025108780A1, where at least 14 of 22 NPL
  references carry a DOI. [source: issue-482]
  [pins: tests/test_epo_xml.py::test_extract_doi,
  tests/test_tools_patent.py::test_get_patent_npl_resolution_reads_the_doi_from_raw_text]
- The `doi:10.…` form is what this project's tests assumed before #482.
  [unverified] No live EPO record in that form has been retained; a citation
  sample across several offices would show how common each form is.

## Where this project departs from the subject

`extract_doi` matches only a DOI introduced by a marker: `doi`, `doi:`, or a
`doi.org/` URL (`dx.doi.org` included). A bare `10.xxxx/…` with no marker is
left alone, trading the rare unmarked DOI for no false matches in page
ranges, report numbers or version strings.

The suffix is wider than Crossref's set: it runs to whitespace, a bracket, a
brace or a quote, following Crossref's `[^\s]+` fallback for early Wiley
DOIs, so a suffix with `<…>` segments is not truncated at its `<`. Trailing
`.`, `,`, `;` and `:`, and a `)` or `>` with no opening partner in the match,
are treated as sentence punctuation and dropped.

## Not covered

- A DOI whose suffix itself contains whitespace, brackets, braces or quotes
  is truncated there. [unverified] Whether any appear in patent citations.
- Percent-encoded DOIs in resolver URLs (`10.1000%2F182`), and DOIs broken
  across a line or by a hyphenation break in the citation text. [unverified]

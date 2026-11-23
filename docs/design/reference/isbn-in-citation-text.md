---
type: Reference
title: ISBNs in free-text citations
description: How an ISBN's check digit is calculated, and the forms ISBNs take inside the non-patent literature citations EPO returns.
subject_version: "ISBN Users' Manual, sixth edition (2012); EPO OPS nplcit text observed 2026-11-21"
valid_for: "ISO 2108 ISBN-13; EPO OPS 3.x citation text"
generated:
  by: process:researching-references
  at: 2026-11-21T15:00:00+01:00
stale_after: 2027-11-21T15:00:00+01:00
status: draft
sources:
  - id: isbn-manual-2012
    title: The International Standard Book Number System, ISBN Users' Manual, International Edition, Sixth Edition (London 2012)
    resource: https://www.isbn-international.org/sites/default/files/ISBN%20Manual%202012%20-corr.pdf
    accessed: 2026-11-21
  - id: issue-70
    title: "feat: patent-to-book cross-referencing via Open Library"
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/70
    accessed: 2026-11-21
---

# ISBNs in free-text citations

How to recognise a real ISBN inside a citation string. Prompted by #70, which
resolves the books a patent's non-patent literature (NPL) cites.

## Scope

- Covers: the ISBN-13 and ISBN-10 check digits, and the forms ISBNs take in
  EPO `nplcit` text.
- Does not cover: finding a book without an ISBN (title search, #59), or how
  Open Library answers an ISBN lookup.
- Depended on by: `src/scholar_mcp/_cache.py` (`checked_isbn13`), used by
  `_attach_npl_books` in `src/scholar_mcp/_npl_resolution.py` and by
  `src/scholar_mcp/_chapter_parser.py`, which extracts the ISBN and keeps
  only a candidate with a valid check digit (#737).

## Claims

### Check digits

- An ISBN-13's check digit is 10 minus the remainder of the sum of the first
  12 digits, weighted alternately 1 and 3, divided by 10, and 0 when that
  gives 10; equivalently, the weighted sum of all 13 digits is divisible by 10.
  [source: isbn-manual-2012] (Appendix 1, A1.1 "Calculating the Check Digit")
  [pins: tests/test_patent_npl_books.py::test_checked_isbn13]
- The ISBN grew from 10 to 13 digits with the fourth edition of ISO 2108, by
  adding the 3-digit GS1 prefixes 978 and 979; national agencies have issued
  only 13-digit ISBNs since 1 January 2007. [source: isbn-manual-2012]
  (Introduction; § 4 "Structure of the ISBN"; § 4.1 "Prefix element")
- A 10-digit ISBN's check digit makes the sum of its digits weighted 10 down
  to 1 divisible by 11, with `X` standing for 10, and its 13-digit form is
  `978` plus its first nine digits with a recalculated check digit.
  [unverified] The 2012 manual does not state the old rule; ISO 2108:1992 or
  an earlier edition of the manual would. Real ISBN-10s from EPO citations
  pass it. [observed: `0-7803-4455-3` on DE102025119099A1]
  [pins: tests/test_patent_npl_books.py::test_checked_isbn13]
- A number of the right length without a valid check digit is not an ISBN:
  without the check, any 10-digit number after the word "ISBN", or a 13-digit
  number starting 978, would be taken for one. Without the marker it is
  worse: a page range ("S. 81057-81105") or a Wikipedia revision id
  (`oldid=1195304739`) has the shape of an ISBN-10 and fails the check.
  [observed: DE102025118928A1, DE102025119138A1, #737]
  [pins: tests/test_patent_npl_books.py::test_checked_isbn13]
  [pins: tests/test_chapter_parser.py::TestIsbnRequiresCheckDigit::test_page_range_is_not_an_isbn]
  [pins: tests/test_chapter_parser.py::TestIsbnRequiresCheckDigit::test_revision_id_is_not_an_isbn]

### Forms in EPO citation text

- `ct=ISBN` matched 237,383 publications in OPS search on 2026-11-21, so
  book citations are common. [observed: `published_data_search('ct=ISBN')`
  through the deployed server's credentials]
- In eight DE publications from that search, ISBNs appear as
  `ISBN 978-3-947920-20-4`, `ISBN: 978-3-540-52155-6` and as ISBN-10
  `ISBN 0-7803-4455-3`, with hyphens. [observed: DE102025118518A1,
  DE102025118534A1, DE102025119099A1]
- The ISBN often names the book a cited *chapter* sits in ("Einführung in
  Expertensysteme. In: Technische Expertensysteme … Kap. 1, S. 1-44. ISBN
  978-3-540-52155-6"), or an IEEE conference proceedings volume.
  [observed: DE102025118534A1, DE102025119099A1]
- The same citations write the chapter as `Kap. 1` and the pages as `S. 1-44`
  (German `Kapitel`, `Seite`/`Seiten` are the long forms, not seen in the
  sample); journal citations use `S.` for pages too ("IEEE Access, Vol. 7,
  2019, S. 81057-81105"). The parser reads `S.` pages as it reads `pp.`.
  [observed: DE102025118534A1, DE102025118928A1; `Kapitel`, `Seite(n)` are
  [unverified] as EPO forms]
  [pins: tests/test_chapter_parser.py::TestGermanCitations::test_real_epo_citation]
- Journal references carry an ISSN instead (`ISSN 0143-8166`), eight digits
  with a hyphen. [observed: DE102025108780A1]
  [pins: tests/test_patent_npl_books.py::test_checked_isbn13]

- Open Library held four of the five ISBNs above: the Springer, Hanser and
  IEEE volumes answered 200 on `/isbn/{isbn}.json`, the RWTH Aachen
  self-published edition (`978-3-947920-20-4`) 404.
  [observed: `curl https://openlibrary.org/isbn/<isbn13>.json` on 2026-11-21]

## Where this project departs from the subject

None. A reference whose ISBN fails the check is left unresolved rather than
looked up.

## Not covered

- Open Library's coverage beyond those five; a larger sample would give a
  rate.
- ISBNs written without hyphens inside longer digit runs, or split across
  lines in the citation text.

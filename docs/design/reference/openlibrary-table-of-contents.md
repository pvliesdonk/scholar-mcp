---
type: Reference
title: Open Library tables of contents
description: Where Open Library keeps a book's table of contents, the shape of its entries, and how often academic books that hold cited chapters have one that a chapter number or page range could match.
subject_version: "Open Library API as served 2026-11-23 (Books API docs page revision of 2025-05-06)"
valid_for: "Open Library edition schema with /type/toc_item revision 2"
generated:
  by: process:researching-references
  at: 2026-11-23T21:40:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-23T21:55:00+01:00
stale_after: 2027-05-23T00:00:00+00:00
status: draft
sources:
  - id: books-api
    title: Open Library Books API (`/api/books`, `bibkeys`, `jscmd=data|details|viewapi`)
    resource: https://openlibrary.org/dev/docs/api/books
    accessed: 2026-11-23
  - id: toc-type
    title: Open Library type definition `/type/toc_item` (revision 2)
    resource: https://openlibrary.org/type/toc_item.json
    accessed: 2026-11-23
  - id: chapter-sample
    title: "Live sample: 305 distinct academic books holding a CrossRef book-chapter, looked up with /api/books?jscmd=details (per-book results in sources/openlibrary-toc/chapter-sample.tsv)"
    resource: https://openlibrary.org/api/books?bibkeys=ISBN:9780521691536&jscmd=details&format=json
    accessed: 2026-11-23
  - id: control
    title: "Positive control: Design Patterns (ISBN 9780201633610), edition /books/OL7408317M and work /works/OL6030812W"
    resource: https://openlibrary.org/isbn/9780201633610.json
    accessed: 2026-11-23
---

# Open Library tables of contents

Open Library stores a table of contents on some edition records. This page
records where it sits, what an entry looks like, and how often an academic
book that holds a cited chapter has one that a chapter number or page range
could be matched against. It answers the design question of #744 (fill a
cited chapter's title from its parent book's table of contents). It does not
cover Open Library search, covers, or rate limits.

## Scope

- Covers: the `table_of_contents` field of an edition, the `/type/toc_item`
  entry shape, whether works carry one, and coverage for academic chapter
  books.
- Does not cover: `/search.json`, author or subject records, the Read API,
  rate limits, or Internet Archive scans.
- Depended on by: nothing yet. It informs #744; `_openlibrary_client.py`
  `get_by_isbn` fetches the edition record that would carry the field.

## Sample

Two CrossRef samples gave the books. First, 200 random `book-chapter`
records (`/works?filter=type:book-chapter&sample=100`, twice), 197 of them
distinct books by ISBN set: Springer imprints 42, Elsevier 17, De Gruyter 15,
Routledge 12, Palgrave 6, Brill 6, Cambridge 6, Peter Lang 6, Oxford 4, CRC 2,
Wiley 0, and 70 smaller publishers. Wiley, CRC and Oxford were thin, so a
top-up drew 40 chapters each from prefixes 10.1002 (Wiley), 10.1201 (CRC) and
10.1093 (Oxford): 108 more distinct books, none overlapping the first set.
Each book was looked up in Open Library by every ISBN CrossRef listed for the
chapter (print and electronic) through batched `/api/books?jscmd=details`
calls; a book counts as found when any of its ISBNs resolved. The per-book
results are in
[`sources/openlibrary-toc/chapter-sample.tsv`](sources/openlibrary-toc/chapter-sample.tsv).
The random sample reflects CrossRef's chapter mix, not the books patent
examiners cite; see "Not covered". [observed: `curl` on 2026-11-23, generic
User-Agent, 25 requests in all: 7 to api.crossref.org, 18 to openlibrary.org]

## Claims

### Where the table of contents lives

- The Books API takes up to many `bibkeys` per request (`ISBN:`, `LCCN:`,
  `OCLC:`, `OLID:`) and returns one object per matched key; `jscmd=details`
  adds a `details` object that is "same as the data provided by the RESTful
  API", and the documented `jscmd=details` example shows `table_of_contents`
  inside it. [source: books-api]
- The documentation advises `jscmd=data` over `jscmd=details` as "more stable"
  but does not list `table_of_contents` among the `jscmd=data` fields.
  [source: books-api] One `jscmd=data` response for 9781437778694 did carry
  `table_of_contents` with the same entry keys, and one 80-key `jscmd=data`
  batch came back `{}` twice while the same keys answered under
  `jscmd=details`. [observed: chapter-sample] The coverage counts below use
  `jscmd=details` only.
- The table of contents is a field of the edition record: `/isbn/9780201633610.json`
  (the path `OpenLibraryClient.get_by_isbn` requests) answered 302 to
  `/books/OL7408317M.json`, which returned the same 10-entry `table_of_contents` as
  `jscmd=details`, so a lookup the server already makes would carry it at no
  extra request. [observed: control, `curl -L`]
- The work record of the same book, `/works/OL6030812W`, has no
  `table_of_contents` key (its keys: `authors`, `covers`, `created`,
  `description`, `key`, `last_modified`, `latest_revision`, `links`,
  `revision`, `subjects`, `subtitle`, `title`, `type`). [observed: control]
  That no work record carries one is [unverified]; one work was checked.

### Entry shape

- `/type/toc_item` is an embeddable type with four string properties:
  `class`, `label`, `title`, `pagenum`. [source: toc-type]
- Entries as served also carry `level` (an integer) and
  `type: {"key": "/type/toc_item"}`; `level` is not in the type definition.
  [observed: chapter-sample, control]
- All 223 entries seen (149 in the random sample, 64 in the top-up, 10 in the
  control) had `level` 0, including
  the control's numbered sections 1.1 to 1.6, so `level` does not separate
  chapters from sections. [observed: chapter-sample, control]
- Absent values come two ways: as empty strings (`"label": ""`,
  `"pagenum": ""`, every sampled entry) or as missing keys (the control's
  front-matter entries have no `label`; its last entry has no `pagenum`).
  [observed: chapter-sample, control]
- `pagenum` is a string and can be a roman numeral (`"xi"`). [observed: control]
- Some tables of contents are one entry holding the whole list as free text,
  beginning "Machine generated contents note:" (Cambridge 9780521513661,
  Elsevier 9781597497251), and one Springer entry carried HTML (`<p>`,
  `&amp;`) in its `title`. [observed: chapter-sample]
- A table of contents can stop partway: the control's ten entries end at
  section 1.6 of a 23-chapter book. [observed: control]

### Coverage for academic chapter books

| Sample | Books | Found in Open Library | Any table of contents | Entry with a numeric `label` or any `pagenum` |
| --- | ---: | ---: | ---: | ---: |
| Random `book-chapter` | 197 | 159 (81%) | 9 | 0 |
| Wiley 10.1002 (incl. AGU 10.1029) | 38 | 38 | 1 | 0 |
| CRC 10.1201 | 40 | 28 | 0 | 0 |
| Oxford 10.1093 | 29 | 26 | 4 | 0 |
| Other (prefix sample spill) | 1 | 1 | 0 | 0 |
| **All** | **305** | **252 (83%)** | **14 (4.6% of books, 5.6% of found)** | **0 (0%)** |

[observed: chapter-sample]

- No sampled book had a table-of-contents entry whose `label` is a chapter
  number (`^(chapter )?\d+(\.\d+)*\.?$`) or whose `pagenum` is non-empty. One
  entry had a non-empty `label`, a German title rather than a number (Peter
  Lang 9783820458121). [observed: chapter-sample]
- Of the 14 books with a table of contents, 9 list chapter titles in order
  with no numbers (between 5 and 89 entries). Mapping a chapter number to the
  Nth entry would be a guess: the lists include front matter such as
  "Introduction" and part headings with no marker telling them apart.
  [observed: chapter-sample]
- The remaining 5 are free text holding chapter numbers inside `title` (two
  "Machine generated contents note" blobs), volume splits ("v. 1. A-K"),
  part headings (Springer, roman numerals), or a single entry.
  [observed: chapter-sample]
- Among the 10 of 12 repository-fixture ISBNs Open Library found, one had a
  table of contents (Design Patterns, the control above), with numeric labels
  and page numbers for its first ten entries only. [observed: `curl` of
  `/api/books?jscmd=details` for the ISBNs in `tests/` and
  [CrossRef book-chapter fields](crossref-book-chapter-fields.md)]

## Where this project departs from the subject

Nothing yet: no code reads `table_of_contents`.

## Not covered

- Coverage for the books patent examiners cite, as opposed to CrossRef's
  chapter mix. A sample of `chapter_info.parent_book` ISBNs from real NPL
  citations would settle it. [unverified]
- Whether other editions of the same work (`/works/{id}/editions.json`)
  carry a table of contents when the cited edition does not. The sample
  tried every ISBN CrossRef lists for the chapter, not every edition of the
  work. [unverified]
- Whether Internet Archive scans linked from an edition (`ocaid`) expose a
  structured table of contents. Not looked at.

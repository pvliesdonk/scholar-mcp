---
type: Reference
title: Book-chapter entries in BibTeX, biblatex, CSL-JSON and RIS
description: Which entry type each citation format uses for a titled chapter in an edited book, which field carries the book title, editors, pages, place and edition, and what happens when the author is missing.
subject_version: "BibTeX 0.99b (btxdoc; plain.bst 0.99b, 2010-12-08); biblatex 3.22a (dev); CSL 1.0.2; RIS (ResearchSoft, archived 2012) and the Zotero RIS translator as of 2026-11-23"
valid_for: "BibTeX 0.99; biblatex 3.x; CSL 1.0.x; RIS as frozen by ResearchSoft"
generated:
  by: process:researching-references
  at: 2026-11-23T21:20:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-23T21:40:00+01:00
stale_after: 2027-05-23T00:00:00+00:00
status: stable
sources:
  - id: btxdoc
    title: BibTeXing (btxdoc.tex), entry types and fields
    resource: https://mirrors.ctan.org/biblio/bibtex/base/btxdoc.tex
    accessed: 2026-11-23
  - id: plain-bst
    title: plain.bst, the reference BibTeX style
    resource: https://mirrors.ctan.org/biblio/bibtex/base/plain.bst
    accessed: 2026-11-23
  - id: biblatex-manual
    title: biblatex manual source (biblatex.tex, dev branch, revision 3.22a)
    resource: https://raw.githubusercontent.com/plk/biblatex/dev/doc/latex/biblatex/biblatex.tex
    accessed: 2026-11-23
  - id: csl-spec
    title: CSL 1.0.2 specification, Appendix III (Types) and IV (Variables)
    resource: https://raw.githubusercontent.com/citation-style-language/documentation/master/specification.rst
    accessed: 2026-11-23
  - id: csl-data-schema
    title: CSL data schema csl-data.json (master)
    resource: https://github.com/citation-style-language/schema/blob/master/schemas/input/csl-data.json
    accessed: 2026-11-23
  - id: ris-reftypes
    title: RIS Format Specifications, reference types (ResearchSoft, archived 2012)
    resource: https://web.archive.org/web/2012/http://www.refman.com/support/risformat_reftypes.asp
    accessed: 2026-11-23
  - id: ris-tags
    title: RIS Format Specifications, tag definitions pages 02 and 06 (ResearchSoft, archived 2012)
    resource: https://web.archive.org/web/2012/http://www.refman.com/support/risformat_tags_06.asp
    accessed: 2026-11-23
  - id: zotero-ris
    title: Zotero RIS translator (RIS.js, master)
    resource: https://github.com/zotero/translators/blob/master/RIS.js
    accessed: 2026-11-23
  - id: pandoc-bibtex-hs
    title: pandoc src/Text/Pandoc/Citeproc/BibTeX.hs (main branch); a converter, cited as supporting evidence only
    resource: https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/Citeproc/BibTeX.hs
    accessed: 2026-11-23
---

# Book-chapter entries in BibTeX, biblatex, CSL-JSON and RIS

How the formats `generate_citations` emits represent a chapter with its own
title inside an edited book, and which field takes each part of the book.
Prompted by #593, which cites a chapter that CrossRef identified (see
[CrossRef book-chapter fields](crossref-book-chapter-fields.md)).

## Scope

- Covers: BibTeX `@incollection` and `@inbook` as `btxdoc` and `plain.bst`
  define them; biblatex `@inbook`, `@incollection`, `@suppbook`,
  `@inreference` and its rule on missing data; the CSL `chapter` type and
  the variables for the book; the RIS `CHAP` type and the tags for the book;
  how pandoc converts between them.
- Does not cover: how a style renders the entry (APA, Chicago and so on),
  `crossref` inheritance between entries, `series`, `chapter` numbers, or
  multi-volume works (`maintitle`).
- Depended on by: `src/scholar_mcp/_chapter_citation.py` and
  `infer_entry_type` in `src/scholar_mcp/_citation_formatter.py`;
  [Chapter citations](../chapter-citations.md).

## Claims

### BibTeX (classic)

- `@incollection` is "a part of a book having its own title". Required:
  `author`, `title`, `booktitle`, `publisher`, `year`. Optional: `editor`,
  `volume` or `number`, `series`, `type`, `chapter`, `pages`, `address`,
  `edition`, `month`, `note`. [source: btxdoc] (lines 566–571)
  [pins: tests/test_chapter_citation.py::TestBibtex::test_full_chapter]
- `@inbook` is "a part of a book, which may be a chapter (or section or
  whatever) and/or a range of pages". Required: `author` or `editor`,
  `title`, `chapter` and/or `pages`, `publisher`, `year`. It has no
  `booktitle`. [source: btxdoc] (lines 557–564)
- In `plain.bst`, `@inbook` formats `title` with `format.btitle`, the
  book-title formatter, and checks `chapter and pages`; so its `title` is the
  book's title, and a chapter title has no field. `@incollection` formats
  `title` as the part's title and `booktitle` through
  `format.in.ed.booktitle`, which prints "In *editors*, *booktitle*".
  [source: plain-bst] (`inbook` lines 604–636, `incollection` lines 638–662,
  `format.in.ed.booktitle` lines 415–424)
- When `editor` and `author` are both present, `editor` "gives the editor of
  the book or collection in which the reference appears". `booktitle` is the
  "title of a book, part of which is being cited". [source: btxdoc]
  (field list, lines 662–684)
- A required field that is empty makes `plain.bst` print the warning
  "empty author in *key*" and carry on; the entry is still written.
  [source: plain-bst] (`output.check`, lines 77–83)
  [pins: tests/test_chapter_citation.py::TestBibtex::test_no_author_no_editor_still_a_chapter]
- `pages` is formatted by `n.dashify`, which turns a single hyphen into an
  en dash, and by `multi.page.check`; any string is accepted.
  [source: plain-bst] (`format.pages`, lines 367–376)
  [pins: tests/test_chapter_citation.py::TestBibtex::test_nonnumeric_pages_kept_as_given]
- `edition` "should be an ordinal" with a capital first letter, such as
  "Second". [source: btxdoc] (`edition`, lines 673–677)

### biblatex

- `@incollection` is "a contribution to a collection which forms a
  self-contained unit with a distinct author and title. The `author` refers
  to the `title`, the `editor` to the `booktitle`". Required: `author`,
  `title`, `editor`, `booktitle`, `year`/`date`; optional fields include
  `publisher`, `location`, `edition`, `isbn`, `chapter`, `pages`, `doi`,
  `url`. [source: biblatex-manual] (`\typeitem{incollection}`, line 550)
- biblatex's `@inbook` has the same layout as its `@incollection` (`title`
  is the part, `booktitle` the book) but is meant for "a part of a book
  which forms a self-contained unit with its own title" in a book by one
  author, and its profile "is different from standard BibTeX".
  [source: biblatex-manual] (`\typeitem{inbook}`, line 514; section
  `bib:use:inb`, line 1519)
- `@suppbook` is for "prefaces, introductions, forewords, afterwords, etc.
  which often have a generic title only"; `@inreference` is "an article in
  a work of reference"; the standard styles treat both as aliases of
  `@inbook` and `@incollection`. [source: biblatex-manual] (lines 525, 636)
- Required fields "are not strictly required in all cases. The
  bibliography styles which come with this package can get by with as
  little as a `title` field for most entry types"; an author-year citation
  scheme still needs an author or editor. [source: biblatex-manual]
  ("Missing and Omissible Data", line 1524)
- `location` is the publisher's place; `address` is accepted as its alias.
  [source: biblatex-manual] (`location`, line 1076)
- `pages` holds "the relevant page range in that other work" when the work
  is part of another one. [source: biblatex-manual] (`pages`, line 1138)
- `@incollection` is therefore the one type whose `title` and `booktitle`
  mean the same in classic BibTeX and in biblatex; `@inbook` puts the book
  title in `title` under BibTeX and the chapter title there under biblatex.
  [source: btxdoc] [source: biblatex-manual] (derived from the claims above)
  [pins: tests/test_chapter_citation.py::TestEntryType::test_crossref_chapter_is_incollection]

### CSL-JSON

- `chapter` is "a part of a book cited separately from the book as a whole
  (e.g. a chapter in an edited book); also used for introductions,
  forewords, and similar supplemental components of a book".
  `entry-encyclopedia` is "an entry in an encyclopedia or similar reference
  work". [source: csl-spec] (Appendix III, lines 2649–2651, 2674–2675)
  [pins: tests/test_chapter_citation.py::TestCslJson::test_full_chapter]
- `container-title` is the "title of the container holding the item (e.g.
  the book title for a book chapter)"; `collection-title` is the series.
  [source: csl-spec] (Appendix IV, lines 2839–2843)
- `editor` is a name variable; `page` is the "range of pages the item ...
  covers in a container"; `publisher-place` is the "geographic location of
  the publisher"; `edition` is the "(container) edition holding the item
  (e.g. "3" when citing a chapter in the third edition of a book)"; `ISBN`
  is a standard variable. [source: csl-spec] (lines 2871, 2917, 2970,
  2995, 3072)
- CSL marks no variable as required for any type: Appendix III lists the
  types with no required variables, and the CSL data schema requires only
  `type` and `id` on an item. [source: csl-spec] (Appendix III, lines
  2615–2797) [source: csl-data-schema] (`required`, line 459)
  [pins: tests/test_chapter_citation.py::TestCslJson::test_no_author_no_editor]

### RIS

- `CHAP` is the reference type "Book chapter". [source: ris-reftypes]
- `T2` (and `BT` for types other than whole book and unpublished work) is
  "Title Secondary"; for `BOOK`, `BT` maps to the primary title instead.
  `A2`/`ED` is "Author Secondary". `SP` is the "start page number; an
  alphanumeric string" and `EP` the "ending page number"; `CY` is the "city
  of publication", `PB` the publisher, `SN` "ISSN/ISBN". [source: ris-tags]
  (pages 02 and 06)
- The archived ResearchSoft tag pages have no `ET` (edition) tag.
  [source: ris-tags]
- Zotero exports its `bookSection` type as `CHAP`, writes the book title
  as `T2`, the book editors as `A2`, the place as `CY`, the edition as
  `ET` and the ISBN as `SN`. On export it splits `pages` at the first run
  of dashes or spaces into `SP` and `EP`, and writes it whole into `SP`
  when there is none. [source: zotero-ris] (`exportTypeMap` line 89;
  `fieldMap` `T2` line 235, `A2` line 279, `ET` line 342; pages export,
  lines 2128–2140)
  [pins: tests/test_chapter_citation.py::TestRis::test_full_chapter]

### How converters map the types

- pandoc writes a CSL `chapter` as `@incollection` when it has an `editor`
  and as `@inbook` otherwise, and reads `@inbook`, `@incollection`,
  `@suppbook` and `@suppcollection` back as `chapter`, and `@inreference`
  as `entry-encyclopedia`. [source: pandoc-bibtex-hs] (lines 105–109,
  1214–1237) This is one converter's choice, not a format rule.

## Where this project departs from the subject

- A chapter is always `@incollection`, with or without editors, rather
  than pandoc's editor-based split: under classic BibTeX an `@inbook` would
  put the chapter title where the book title belongs. See
  [Chapter citations](../chapter-citations.md).
- A chapter with neither author nor editor is still written as a chapter,
  without those fields, though BibTeX lists `author` as required; see the
  same page.
- `edition` is CrossRef's `edition-number` as given (`"2"`), not BibTeX's
  capitalised ordinal. biblatex accepts an integer; classic `plain.bst`
  prints "2 edition". The `@book` path already does the same.
- RIS pages are split only when the string has exactly one hyphen, so
  `P3-660-P3-660` goes whole into `SP` where Zotero would split it.
  [pins: tests/test_chapter_citation.py::TestRis::test_ambiguous_range_goes_whole_into_sp]
- CSL `entry-encyclopedia` and biblatex `@inreference`/`@suppbook` are not
  used: nothing in the CrossRef chapter record tells an encyclopedia entry
  or a preface from a chapter.

## Not covered

- How individual CSL styles render a `chapter` without `author`; a style
  may substitute the editor or the title.
- Whether reference managers other than Zotero read `ET` from RIS.

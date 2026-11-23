---
type: Reference
title: CrossRef book-chapter fields
description: Which CrossRef REST work fields describe a book-chapter record and its parent book, how often publishers populate them, and how they differ from the journal fields.
subject_version: "Crossref REST API 4.11.0 (swagger), observed 2026-11-23"
valid_for: "Crossref REST API 4.x"
generated:
  by: process:researching-references
  at: 2026-11-23T19:30:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-23T20:10:00+01:00
stale_after: 2027-05-23T00:00:00+00:00
status: draft
sources:
  - id: swagger
    title: Crossref REST API OpenAPI (swagger) specification, `Work`, `Author` and `WorkRelation` definitions
    resource: https://api.crossref.org/swagger-docs
    accessed: 2026-11-23
  - id: markup-guide
    title: Crossref schema markup guide, books and chapters
    resource: https://www.crossref.org/documentation/schema-library/markup-guide-record-types/books-and-chapters/
    accessed: 2026-11-23
  - id: chapter-sample
    title: "Live chapter sample: /works?filter=type:book-chapter[,prefix:P]&sample=N (380 distinct records, 14 DOI prefixes targeted at 20 each plus 100 unfiltered random, 25 prefixes in the random 100)"
    resource: https://api.crossref.org/works?filter=type:book-chapter&sample=100
    accessed: 2026-11-23
  - id: parent-sample
    title: "Live parent-book records: /works/{doi} for each chapter's relation.is-part-of target (58 chapters, up to 3 per prefix, 58 resolved)"
    resource: https://api.crossref.org/works/10.1002/9780470996836
    accessed: 2026-11-23
---

# CrossRef book-chapter fields

A `book-chapter` work in the Crossref REST API describes one chapter, and
several of the fields a citation needs (parent book title, editors) sit
elsewhere than a journal article's equivalents. This page records which
fields exist, how often publishers fill them, and how the chapter links to its
book. It supports the chapter mapping (#67), the BibTeX `@incollection`
builder (#593) and the title-query fallback (#745). It does not cover the
journal fields; [CrossRef work journal fields](crossref-works.md) does.

## Scope

- Covers: `container-title`, `author`, `editor`, `ISBN`, `isbn-type`, `page`,
  `publisher`, `publisher-location`, `edition-number`, `ISSN`,
  `relation.is-part-of`, `issued` of a `book-chapter`, the same fields of its
  parent book record, and `type:book-chapter` title queries.
- Does not cover: citation lists, licences, abstracts, rate limits beyond the
  headers noted below, or other record types (`book-section`,
  `reference-entry`).
- Depended on by: `_enricher_crossref_chapter.py` (#67), which maps a
  chapter and its parent onto `chapter_info`; see
  [CrossRef book chapters](../crossref-book-chapters.md). #593 and #745 will
  read it too.

## Sample

Percentages are of the sample, not of Crossref. The targeted prefixes were
chosen to cover publishers, so the pooled counts overweight small publishers
relative to Crossref's real mix, which is Springer-heavy (43 of 100 in the
unfiltered random sample). Targeted prefixes: Wiley 10.1002, Springer
10.1007, Elsevier 10.1016, Cambridge 10.1017, Oxford 10.1093, Emerald 10.1108,
IEEE 10.1109, Brill 10.1163, CRC/Taylor & Francis 10.1201, De Gruyter 10.1515,
IGI Global 10.4018, Routledge 10.4324, IntechOpen 10.5772, MIT Press
10.7551. The parent sample added Bentham, Thieme, JSTOR, transcript, Atlantis
Press, University of Toronto Press and other small publishers.
[observed: `curl` against api.crossref.org on 2026-11-23, generic
User-Agent, no `mailto`, about 150 requests at 1 per second]

## Claims

### Field definitions

- A work's required fields are `indexed`, `publisher`, `DOI`, `type`,
  `created`, `source`, `prefix`, `member`, `deposited`, `score`, `resource`,
  `issued` and `URL`. No chapter field below is required. [source: swagger]
  (`Work`, `required`)
- `container-title`, `ISBN` and `isbn-type` are arrays (of strings, strings
  and `{type, value}` objects); `page`, `publisher`, `publisher-location`
  and `edition-number` are strings; `editor` and `author` are arrays of
  `Author` objects with `given`, `family`, `name`, `sequence`, `affiliation`
  and `role`. [source: swagger] (`Work`, `Author`)
- The schema has no chapter-number field: `volume`, `part-number` and
  `component-number` exist on `Work`, but none of the 380 chapters carried
  `volume`, `part-number`, `special-numbering` or `article-number`, and a
  `select=chapter-number` request is rejected as unavailable. [source:
  swagger] [observed: key census over the 380 records; request returning
  `select-not-available`]
- A chapter's position in its book appears only inside the DOI or title
  when at all: 18 of 380 titles start with digits, and one reads
  "CHAPTER VI". [observed: chapter-sample]

### Parent book title (`container-title`)

- `container-title` was present and non-empty on 380 of 380 chapters.
  [observed: chapter-sample]
- It has one element for 322 chapters and two for 58. In 54 of the 58 two-element
  lists the record also has `ISSN` (a book series); the other 4 name a series or
  collection without one ("Springer-Lehrbuch", "Law in Context", a letters
  edition, a conference). Springer (29), IGI Global (9) and Wiley (7) account for
  most. [observed: chapter-sample]
- With two elements the first is the series and the second the book. The last
  element equalled the parent book's `title` (or `title: subtitle`) for 58 of
  58 resolved parents. [observed: parent-sample]
- The first element is not the book title for 11 of the 58 sampled
  parents, because it is the series title: for example
  10.1007/978-3-031-93275-5_2 listed only "Advances in Science, Technology &
  Innovation" while its parent is "Cultural Heritage-Based Sustainable
  Tourism Approaches". Taking `container-title[0]` therefore mislabels
  series chapters. [observed: parent-sample]
- A chapter record whose one-element title is the series (an `ISSN` with one
  title) did not occur in the sample: all 54 records with `ISSN` had two
  titles. [observed: chapter-sample]
- Six records carry HTML entities or inline markup in `container-title`
  (`&amp;`, `<i>...</i>`; one Cambridge record has `&lt;I&gt;` in its
  title). A consumer must unescape and strip it. [observed: chapter-sample]
- The chapter record has no field for the book's subtitle; the parent's
  `subtitle` held one for at least 4 of the 58 sampled parents. [observed:
  parent-sample]

### Editors and authors

- `editor` was present on 11 of 380 chapters (3%), all Oxford, Cambridge,
  Bentham or Thieme. It was absent on every chapter from the other 12
  targeted prefixes. Parent books do carry them: 27 of 58 sampled parents had
  `editor`, and 23 of those 27 belonged to chapters with no `editor` of their
  own. [observed: chapter-sample,
  parent-sample]
- The parent's `type` does not predict whether it lists editors: the 27
  parents with `editor` were 16 `edited-book` (of 27), 6 `book` (of 10) and 5
  `monograph` (of 19), and none of the 2 `reference-book`. 3 parents had both
  `editor` and `author`, and 3 had neither. [observed: parent-sample]
- Crossref says contributors deposited at book level "will be applied to the
  chapters as well unless distinct information is supplied", and that
  distinct chapter authors or editors go at chapter level; the REST work for
  the chapter does not show the inherited book-level editors. [source:
  markup-guide] (Book metadata, Contributors; top-level book section)
  [observed: chapter-sample]
- `author` was present on 249 of 380 chapters (66%). It varied by
  publisher: 20 of 20 for IGI Global and IntechOpen, 0 of 20 for IEEE, 4 of
  20 for De Gruyter and 5 of 20 for MIT Press. Among records with neither
  `author` nor `editor` (129, 34%) are front matter, indexes, prefaces,
  encyclopedia entries and book chapters whose authorship Crossref holds
  nowhere. [observed: chapter-sample]
- Of the 19 `editor` entries in the sample 18 had `sequence: additional` and
  one `first`, all had `role: [{vocabulary: crossref, role: editor}]`, and
  no `author` array held an editor. `family` and `given` were present,
  `name` was not.
  [observed: chapter-sample]

### ISBNs

- `ISBN` was present on 374 of 380 chapters (98%). The 6 without it were
  two `10.1093/oed/` entries, one Elsevier `b978-012373947-6` record, one
  `10.3726` record whose `publisher` is "CrossRef", an Endocrine Society
  abstract and an AGU front-matter entry. [observed: chapter-sample]
- `ISBN` values are bare digits with no hyphens: 606 were 13 digits and 32
  were 10 digits. [observed: chapter-sample]
- `isbn-type` was present whenever `ISBN` was, with one `{value, type}` entry
  per ISBN and `type` either `print` or `electronic` (324 print, 314
  electronic). The two lists never differed in length. 220 chapters
  listed more than one ISBN, usually a print and an electronic ISBN of the
  same book. [observed: chapter-sample]
- The chapter's `ISBN` set equalled its parent book's for 55 of 58 pairs and
  was disjoint for the other 3: 10.1029/sc001p0025 (chapter 0875907059,
  parent 9780875907055 and 9781118667590), 10.1201/9781482295023-10 (chapter
  9780429178436, parent 9781482295023) and 10.4324/9780203366127-46 (chapter
  9780203366127, parent 9781134105144). That these are other formats of the
  same book is [unverified]; an ISBN match between chapter and parent is
  therefore sufficient but not necessary. [observed: parent-sample]
- Which ISBN is the print one has to come from `isbn-type`: the order of the
  `ISBN` array does not say, and the electronic ISBN came first for Wiley
  chapters such as 10.1002/9780470996836.ch5. [observed: chapter-sample]

### Page range

- `page` was present on 329 of 380 chapters (87%). It was absent for all 20
  IEEE and all 20 IntechOpen chapters, 5 of 20 Oxford records and 3 of 20 MIT
  Press records. [observed: chapter-sample]
- 327 of the 329 are hyphenated ranges, such as `"340-360"`. The other forms
  seen were `"542-542"`, `"xiii-xiii"`, `"ii-v"`, `"xi"`, `"ifc4"`,
  `"639-650.e3"`, `"343a-349"`, `"[i]-[viii]"` and `"P3-660-P3-660"`. A
  consumer must not assume digits. [observed: chapter-sample]
- A one-page chapter can be written as a repeated range (`"542-542"`), so a
  range does not imply more than one page. [observed: chapter-sample]
- The sample has no `article-number`, so unlike a journal article a chapter
  gives no fallback start page. [observed: chapter-sample]

### Publisher, place and edition

- `publisher` is required and was present on 380 of 380. Its string can differ
  from the imprint a reader knows (the 10.1007 chapters carried 15
  distinct strings, among them "Springer Berlin Heidelberg" (21) and
  "Springer International Publishing" (16)), and Oxford strings in the
  sample included "Oxford University PressNew York, NY", with the location
  run onto the name. The chapter's `publisher` equalled the parent's for 57 of
  58 pairs. [source: swagger] [observed: chapter-sample, parent-sample]
- `publisher-location` was present on 118 of 380 (31%): 20 of 20 Wiley and
  Springer, 10 of 20 CRC, 9 of 20 Routledge, none for Elsevier, IEEE,
  De Gruyter, Brill or IGI Global. Of 58 parents, 13 had it. [observed:
  chapter-sample, parent-sample]
- `edition-number` was present on 86 of 380 (23%), concentrated in Cambridge
  (17 of 20), CRC (19 of 20) and Routledge (19 of 20). [observed:
  chapter-sample]

### Link from chapter to book

- `relation.is-part-of` was present on 345 of 380 chapters (91%). Each entry
  is `{id-type: doi, id: "https://doi.org/<book DOI>", asserted-by:
  object}` with a full `https://doi.org/` URL, not a bare DOI. 343 distinct
  books occurred among the 345. [observed: chapter-sample]
- The link is missing for every Elsevier (10.1016) chapter in the sample (25
  of 25) and accounts for 25 of the 35 records without it; the rest were
  Oxford (4), Wiley (2), Emerald (2), and one each from 10.50505 and 10.3917.
  The Elsevier records still carry `container-title` and, for 24 of 25,
  `ISBN`. [observed: chapter-sample]
- Every `is-part-of` target of the 58 sampled resolved with
  `/works/{doi}`. Their `type` was `edited-book` (27), `monograph` (19),
  `book` (10) or `reference-book` (2); 57 of 58 had `ISBN`, all 58 had
  `publisher`. [observed: parent-sample]
- `has-part` and `is-identical-to` relations appeared on 2 and 3
  records respectively and are not a chapter-to-book link; the two
  `10.1093/oed/` entries carried `has-part` only. [observed: chapter-sample]
- Crossref does not require chapter DOIs and recommends them when chapters
  are cited; a book DOI is required. [source: markup-guide] (Book
  metadata, Book chapters)
- A chapter that has no `relation.is-part-of` has no documented route to
  its book other than `ISBN` or a title search. [unverified] Whether an
  `ISBN` filter, `/works?filter=isbn:<isbn>,type:book`, reliably returns the
  parent was not tried.

### Dates

- `issued` was present on 380 of 380, required by the schema. 148 had only
  a year in `date-parts`, and 28 `issued` entries had `[[null]]`.
  `published-print` was present on 325 (86%) and `published-online` on
  73 (19%). [source: swagger] [observed: chapter-sample]

### Single record versus list

- `/works/{doi}` returns the same fields as a list item, plus empty arrays
  such as `subtitle`, `subject`, `short-title` and `original-title` that a
  list item leaves out, so a presence check must test for non-empty.
  [observed: chapter-sample, singleton 10.1017/cbo9781139199100.007]

### Title queries for chapters without a DOI

- `/works?filter=type:book-chapter&query.bibliographic=<chapter title>`
  returned the source chapter first for 13 of 14 randomly drawn chapters
  with a title over 25 characters, against 12 first and 1 second without
  the filter (the unfiltered result mixed in journal articles,
  proceedings papers and datasets). Appending the parent `container-title`
  to the query ranked the source first for 14 of 14. The small sample
  does not show how a short or common title behaves. [observed: 3 queries
  for each of 14 chapters; 1.2 s between requests]
- The unfiltered five-result list held other types in 13 of the 14 queries,
  which is why the filter and the container title both matter.
  [observed: same run]
- The public pool answered with `x-rate-limit-limit: 1`,
  `x-rate-limit-interval: 1s` and `x-concurrency-limit: 1`.
  [observed: response headers of a list request]
- A single-work request (`/works/{doi}`) is allowed more: two DOIs and one
  chapter DOI each answered `x-rate-limit-limit: 5`,
  `x-rate-limit-interval: 1s` and `x-concurrency-limit: 1`, while a
  `/works?filter=type:book-chapter&rows=1` list request in the same run
  answered `x-rate-limit-limit: 1`. The limit is per endpoint shape; the
  concurrency limit is 1 for both. Whether a `mailto` (the polite pool)
  raises either is unverified. [observed: `curl` with a generic User-Agent
  and no `mailto`, 2026-11-23, 1.5 s between requests]

## How book-chapter fields differ from the journal fields

| Need | Journal article ([page](crossref-works.md)) | Book chapter |
| --- | --- | --- |
| Container title | `container-title[0]` is the journal | Last element is the book; first is the series when `ISSN` is present |
| Container identifier | `ISSN`, `issn-type` | `ISBN`, `isbn-type` (bare digits), or `ISSN` for the series |
| Position | `volume`, `issue`, `page` or `article-number` | `page` only, any form; no chapter number |
| Editors | not applicable | `editor`, usually absent on the chapter and present on the parent book |
| Parent link | none needed | `relation.is-part-of` (full DOI URL) when present |

## Where this project departs from the subject

- A chapter without `relation.is-part-of` gets no parent book: the ISBN
  route above stays unverified and is not followed.
- `chapter_info.editors` flattens each `Author` to one `"Given Family"`
  string (or `name`), dropping `sequence`, `affiliation` and `role`.

## Not covered

- Whether an ISBN filter finds the parent when `is-part-of` is missing (see
  above), and how a chapter with `is-part-of` pointing at an unresolved DOI
  behaves; all 58 sampled targets resolved.
- Per-publisher coverage rests on 20 chapters per prefix, so a rate such as
  "IEEE has no authors" describes that sample of 20.
- The parent sample is 58 chapters across 28 DOI prefixes, up to 3 per prefix,
  so the counts of parent `editor` and `ISBN` are indicative.
- `book-section`, `reference-entry` and `proceedings-article` records, which
  also carry book titles, were not examined.

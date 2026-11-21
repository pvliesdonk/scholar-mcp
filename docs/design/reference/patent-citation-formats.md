---
type: Reference
title: Patent entries in biblatex, CSL-JSON and RIS
description: How biblatex, CSL and RIS represent a patent, and which kind codes mark an application rather than a grant at EP, US, WO and DE.
subject_version: "biblatex 3.22a (dev, 2026-09-24); CSL 1.0.2; Zotero RIS translator and z2csl type map as of 2026-11-21; EPO, USPTO, WIPO and DPMA kind-code pages as of 2026-11-21"
valid_for: "biblatex 3.x; CSL 1.0.x; the kind-code tables of the four offices as published"
generated:
  by: process:researching-references
  at: 2026-11-21T11:00:00+01:00
stale_after: 2027-05-21T11:00:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-21T11:30:00+01:00
status: stable
sources:
  - id: biblatex-manual
    title: biblatex manual source (biblatex.tex, dev branch, release 3.22a)
    resource: https://raw.githubusercontent.com/plk/biblatex/dev/doc/latex/biblatex/biblatex.tex
    accessed: 2026-11-21
  - id: biblatex-english-lbx
    title: biblatex english.lbx localisation strings (dev branch)
    resource: https://raw.githubusercontent.com/plk/biblatex/dev/tex/latex/biblatex/lbx/english.lbx
    accessed: 2026-11-21
  - id: pandoc-bibtex-hs
    title: pandoc src/Text/Pandoc/Citeproc/BibTeX.hs (main branch)
    resource: https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/Citeproc/BibTeX.hs
    accessed: 2026-11-21
  - id: bibtex-web
    title: bibtex.web, TeX Live source
    resource: https://raw.githubusercontent.com/TeX-Live/texlive-source/trunk/texk/web2c/bibtex.web
    accessed: 2026-11-21
  - id: btxdoc
    title: BibTeXing (btxdoc.tex)
    resource: https://ctan.org/tex-archive/biblio/bibtex/base
    accessed: 2026-11-21
  - id: plain-bst
    title: plain.bst
    resource: https://ctan.org/tex-archive/biblio/bibtex/base
    accessed: 2026-11-21
  - id: csl-spec
    title: CSL 1.0.2 specification, Appendix III (Types) and IV (Variables)
    resource: https://raw.githubusercontent.com/citation-style-language/documentation/master/specification.rst
    accessed: 2026-11-21
  - id: csl-data-schema
    title: CSL data schema csl-data.json
    resource: https://github.com/citation-style-language/schema/blob/master/schemas/input/csl-data.json
    accessed: 2026-11-21
  - id: z2csl
    title: Zotero to CSL type and field map
    resource: https://aurimasv.github.io/z2csl/typeMap.xml
    accessed: 2026-11-21
  - id: csl-styles
    title: apa.csl, ieee.csl and chicago-author-date.csl (citation-style-language/styles, master)
    resource: https://github.com/citation-style-language/styles
    accessed: 2026-11-21
  - id: ris-reftypes
    title: RIS Format Specifications, reference types (ResearchSoft, archived 2012)
    resource: https://web.archive.org/web/2012/http://www.refman.com/support/risformat_reftypes.asp
    accessed: 2026-11-21
  - id: zotero-ris
    title: Zotero RIS translator (RIS.js)
    resource: https://github.com/zotero/translators/blob/master/RIS.js
    accessed: 2026-11-21
  - id: epo-kind-codes
    title: EPO European Publication Server help, kind codes
    resource: https://epo.org/en/searching-for-patents/technical/publication-server/help
    accessed: 2026-11-21
  - id: uspto-kind-codes
    title: USPTO kind codes
    resource: https://www.uspto.gov/patents/search/authority-files/uspto-kind-codes
    accessed: 2026-11-21
  - id: wipo-kind-codes
    title: WIPO PATENTSCOPE kind codes (in compliance with ST.16)
    resource: https://www.wipo.int/en/web/patentscope/data/kind_codes
    accessed: 2026-11-21
  - id: dpma-kind-codes
    title: DPMAinformativ Nr. 2, Schriftenartencodes
    resource: https://www.dpma.de/fileadmin/user_upload/Dokumente/Das_DPMA/Ver%C3%B6ffentlichungen/02_dpmainformativ_schriftenartencodes.pdf
    accessed: 2026-11-21
---

# Patent entries in biblatex, CSL-JSON and RIS

How the three citation formats `generate_citations` emits represent a patent,
and how a publication's kind code tells an application from a granted patent.
Prompted by #50.

## Scope

- Covers: the biblatex `@patent` entry and its localisation keys, what classic
  BibTeX and pandoc do with that entry, the CSL `patent` type and the variables
  styles read for it, the RIS `PAT` type and Zotero's tag map for it, and the
  application and grant kind codes of EP, US, WO and DE.
- Does not cover: citation style rules (APA, IEEE and so on) beyond which
  variables the styles read, the kind codes of other offices, or how EPO
  supplies the data (see [EPO OPS bibliographic responses](epo-ops-biblio.md)).
- Depended on by: `src/scholar_mcp/_patent_citation.py` (all of it), used by
  `src/scholar_mcp/_citation_formatter.py`; `docs/design/patent-citations.md`.

## Claims

### biblatex `@patent`

- `@patent` requires `author`, `title`, `number` and `year`/`date`; its
  optional fields are `holder`, `subtitle`, `titleaddon`, `type`, `version`,
  `location`, `note`, `month`, `addendum`, `pubstate`, `doi`, `eprint`,
  `eprintclass`, `eprinttype`, `url` and `urldate`. Generic fields such as
  `abstract` are "independent of the entry type". [source: biblatex-manual]
  (`\typeitem{patent}`, line 589; entry-type introduction, line 487)
- `number` is "the number or record token of a patent or patent request"; the
  manual sets no format for it. [source: biblatex-manual] (`number`, line 1106)
- `holder` holds "the holder(s) of a patent, if different from the author",
  and "corporate holders need to be wrapped in an additional set of braces".
  [source: biblatex-manual] (`holder`, line 991)
  [pins: tests/test_patent_citation.py::test_bibtex_holders_are_braced]
- `type` "specif[ies] the type" of the patent, and `location` indicates "the
  scope of the patent, if different from the scope implied by the type"; for
  `@patent`, `location` is a key list. [source: biblatex-manual]
  (`\typeitem{patent}`, line 589; `location`, line 1076)
- `type` is a key field: a style prints the localised string when the value
  is a known localisation key and prints the value as is otherwise.
  [source: biblatex-manual] (key fields, line 831)
- The patent keys are exactly `patent`, `patentde`, `patenteu`, `patentfr`,
  `patentuk`, `patentus`, `patreq`, `patreqde`, `patreqeu`, `patreqfr`,
  `patrequk` and `patrequs`; the manual says only a small number is defined,
  "mainly to illustrate this scheme". There is no key for WO, JP, CN or KR,
  and the British key is `uk`, not the ISO code `gb`; EP uses `eu`.
  [source: biblatex-english-lbx] (lines 549–560) [source: biblatex-manual]
  ("Patents and Patent Requests", lines 12582–12601)
- This project uses `patentde`, `patenteu`, `patentus`, their `patreq`
  counterparts, and the generic `patreq` for WO; it emits no `fr` or `uk`
  key, because no FR or GB kind code is sourced below.
  [pins: tests/test_patent_citation.py::test_bibtex_type_key]
- A corporate name in any name list is wrapped "in an extra pair of curly
  braces to prevent data parsing from treating them as personal names".
  [source: biblatex-manual] ("Corporate Authors and Editors", line 1533)
- A name written `Last, First, Second` has three comma parts, which BibTeX
  name parsing reads as `von Last, Jr, First`. [source: btxdoc]
  (lines 1068–1113) [pins: tests/test_patent_citation.py::test_person_name_joins_given_names]

### Classic BibTeX and pandoc

- Classic BibTeX warns `entry type for "<key>" isn't style-file defined` for an
  unknown type such as `@patent` and formats it with the style's
  `default.type`, which `plain.bst` defines as `misc`. [source: bibtex-web]
  (`call.type$`) [source: plain-bst] (`FUNCTION {default.type} { misc }`)
- pandoc maps biblatex `@patent` to CSL `patent`, `number` to `number`, and
  `location` to `jurisdiction` with localisation keys resolved; it resolves
  `type` as a localisation key and uses it as the CSL `genre`. It does not read `holder`, so a patent holder
  never reaches CSL through a `.bib` file. [source: pandoc-bibtex-hs]
  (`getTypeAndGenre`, lines 1192–1278; `jurisdiction'`, line 583)

### CSL `patent`

- CSL has a `patent` type, "A patent for an invention".
  [source: csl-spec] (Appendix III) [source: csl-data-schema]
- The patent-related variables are `authority`, "Issuing or judicial authority
  (e.g. "USPTO" for a patent …)", and `jurisdiction`, "Geographic scope of
  relevance (e.g. "US" for a US patent …)". `number`, `issued` and
  `submitted` are general variables. CSL has no assignee variable.
  [source: csl-spec] (Appendix IV)
- Zotero maps a patent's inventors to `author`, `patentNumber` to `number`,
  `issueDate` to `issued`, `filingDate` to `submitted`, `issuingAuthority` to
  `authority`, and `assignee` to no CSL variable. [source: z2csl]
  [pins: tests/test_patent_citation.py::test_csl_patent_entry]
- APA and Chicago author-date print a patent's identifier as `authority`
  (short form), then `genre` or the term "patent", then `number`
  ("US Patent 123,445"); Chicago also prints "filed" with `submitted`. IEEE
  prints title, `number` and `issued`. [source: csl-styles] (`identifier-patent`
  macros; the `patent` branch of `ieee.csl`)

### RIS `PAT`

- `PAT` is the RIS reference type for a patent. [source: ris-reftypes]
- The original per-type tag table could not be retrieved. [unverified] An
  archived `risformat_tags.asp` would settle it.
- Zotero's translator, whose field map is "used for exporting and importing",
  writes a patent's inventors as `AU`, `assignee` as `PB`, `patentNumber` as
  `SN`, `issueDate` as `DA` (and its year as `PY`), with `TI`, `AB` and `UR`
  as for every type. Its patent uses of `C1` (filing date) and `C2` are marked
  "not in spec". [source: zotero-ris] (`fieldMap`)
  [pins: tests/test_patent_citation.py::test_ris_patent_record]

### Application or grant: kind codes

- EP: A1 and A2 are patent applications, A3 a separate search report, A8 and
  A9 corrections of applications; B1, B2 and B3 are patent specifications
  (granted, amended, after limitation), B8 and B9 corrections of them.
  [source: epo-kind-codes]
- WO: every kind code (A1, A2, A3, A4, A8, A9) is an international
  application or a republication of one; the PCT grants no patents.
  [source: wipo-kind-codes]
- US: A1, A2 and A9 are published utility applications (from 2001), P1, P4
  and P9 plant applications; B1, B2 and B9 are utility grants, E reissues, S
  design patents, P2 and P3 plant grants, and a bare A is a utility grant
  issued before 2 January 2001. H1 is a statutory invention registration, not
  a patent. US B2 is a grant, unlike EP B2. [source: uspto-kind-codes]
- DE: A1 is an Offenlegungsschrift (application publication), A8 and A9 its
  corrections; B3 and B4 are Patentschriften (grants), B8 and B9 their
  corrections, C5 an amended Patentschrift. [source: dpma-kind-codes]
- The application or grant reading of every code above is pinned.
  [pins: tests/test_patent_citation.py::test_publication_status]
- FR and GB kind codes were not checked. [unverified] The INPI and UKIPO
  kind-code pages would settle them.

## Where this project departs from the subject

- A kind code the table above does not source, or an office outside EP, US,
  WO and DE, gets no application or grant reading. The BibTeX entry then
  carries no `type` and names the office in `location`, rather than guess
  `patent` for what may be an application.
  [pins: tests/test_patent_citation.py::test_bibtex_unknown_status_uses_location]
- CSL output drops the applicants, because CSL has no assignee variable and
  Zotero maps it to none. They stay in BibTeX `holder` and RIS `PB`.
- RIS output omits the filing date, since Zotero's `C1` use for it is marked
  "not in spec".

Both decisions are recorded in `docs/design/patent-citations.md`.

## Not covered

- Kind codes of FR, GB, JP, CN, KR and the other offices `is_patent_number`
  accepts.
- How Zotero's BibTeX translator imports `@patent`, `holder` and `type`.
- Whether an `original` EPO name for a CN, JP or KR publication is in a
  non-Latin script (see [EPO OPS bibliographic responses](epo-ops-biblio.md)).

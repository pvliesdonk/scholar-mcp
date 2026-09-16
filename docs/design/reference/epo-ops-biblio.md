---
type: Reference
title: EPO OPS bibliographic responses
description: Where OPS places the elements of a published-data biblio response, and which of them sit outside bibliographic-data.
subject_version: "OPS 3.2"
valid_for: "OPS 3.x"
generated:
  by: process:researching-references
  at: 2026-09-16
stale_after: 2027-09-16
status: draft
sources:
  - id: ops-biblio-wo
    title: Raw OPS published-data/publication/docdb/WO.2018019928.A1/biblio response (200, 18 868 bytes, fetched 2026-09-11 from inside the deployment with its own credentials), quoted verbatim in scholar-mcp#399
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/399
    accessed: 2026-09-16
  - id: ops-biblio-ep-b1
    title: Raw OPS biblio response for EP.3491801.B1, reported alongside the above in scholar-mcp#399
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/399
    accessed: 2026-09-16
---

# EPO OPS bibliographic responses

The `published-data/.../biblio` endpoint returns an `exchange-document` whose
name suggests everything about the document hangs beneath one
`bibliographic-data` element. It does not. This page records which elements sit
where, because a parser that assumes the tidy nesting silently returns an empty
string rather than failing.

## Scope

- Covers: the element *placement* of a biblio response — specifically which
  elements are children of `bibliographic-data` and which are its siblings.
- Does not cover: the meaning of the bibliographic fields, classification
  schemes, or the citation block inside `bibliographic-data`. The legal and
  image services have their own pages.
- Depended on by: `src/scholar_mcp/_epo_xml.py` (`parse_biblio_xml`).

## Claims

### Element placement

- `abstract` is a child of `exchange-document` and a **sibling** of
  `bibliographic-data`, not a child of it.
  [observed: the raw response for `WO.2018019928.A1` quoted in #399 — walking it
  with lxml, both `abstract` elements have parent `exchange-document` and
  grandparent `exchange-documents`]
  [source: ops-biblio-wo]
  [pins: tests/test_epo_xml.py::TestParseBiblioXmlEnglishPreference::test_abstract_prefers_english]
- Language variants repeat the whole element rather than nesting: the observed
  response carries `lang="en"` and `lang="fr"` siblings.
  [source: ops-biblio-wo]
  [pins: tests/test_epo_xml.py::TestParseBiblioXmlEnglishPreference::test_abstract_fallback_to_non_english]
- The abstract's text sits in one or more `<p>` children, so reading
  `element.text` alone yields nothing usable.
  [source: ops-biblio-wo]
- `invention-title` **is** a child of `bibliographic-data`. The same deployed
  build that returned `"abstract": ""` returned the correct title for the same
  document, and both lookups run through the same direct-children helper — so
  the title's placement is confirmed by the case that falsified the abstract's.
  [observed: #399, `get_patent(patent_number="WO2018019928A1")` returning
  `"title": "IDENTIFYING A NETWORK NODE TO WHICH DATA WILL BE REPLICATED"`
  alongside the empty abstract]
  [pins: tests/test_epo_xml.py::TestParseBiblioXmlEnglishPreference::test_title_prefers_english]

### Absence is meaningful

- A publication may carry no `abstract` element at all, and an empty abstract is
  then the correct answer rather than a parse failure: the `EP.3491801.B1` biblio
  response has none.
  [source: ops-biblio-ep-b1]
  [pins: tests/test_epo_xml.py::TestParseBiblioXmlMinimal::test_minimal_no_abstract]

## Where this project departs from the subject

Nowhere deliberately. `parse_biblio_xml` reads `abstract` from
`exchange-document` and everything else from `bibliographic-data`, matching the
placement recorded above.

Before #399 it read `abstract` from `bibliographic-data`, which is why every
patent record carried `"abstract": ""` — the helper it used scans direct
children only, so the element one level up was never seen. The rows already
cached with an empty abstract are dropped by a one-shot repair (#440) rather
than left to expire.

## Not covered

- Whether **any** OPS response shape nests `abstract` inside
  `bibliographic-data`. Only the two documents above were inspected, and #399
  records the same open question. The parser now looks only at
  `exchange-document`, so such a response would yield an empty abstract. A wider
  survey, or the OPS exchange schema, would settle it. [unverified]
- Placement of the elements this project does not read (`ops:pre`-style raw
  blocks, register data, the full `parties` tree beyond names). [unverified]
- **No fixture is vendored for these claims.** The session that fixed #399 had
  no EPO credentials reachable, so the evidence is the response quoted verbatim
  in #399 rather than a capture under `tests/fixtures/epo/`. This is why the page
  is `status: draft`. Re-capture the WO document when credentials are available,
  vendor it beside the legal fixture, and promote the page to `stable`.

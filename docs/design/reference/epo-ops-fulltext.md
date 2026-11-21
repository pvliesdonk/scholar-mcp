---
type: Reference
title: EPO OPS full-text claims and description
description: The shape of an OPS published-data claims or description response, as the deployed service returns it.
subject_version: "EPO OPS 3.2, observed 2026-11-21"
valid_for: "EPO OPS 3.x"
generated:
  by: process:researching-references
  at: 2026-11-21T13:00:00+01:00
stale_after: 2027-05-21T13:00:00+01:00
status: draft
sources:
  - id: issue-701
    title: get_patent claims and description are always empty
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/701
    accessed: 2026-11-21
---

# EPO OPS full-text claims and description

What `published-data/publication/docdb/claims` and `.../description` return.
Prompted by #701: the parsers were written against hand-made fixtures in the
exchange namespace and returned an empty string for every real response.

## Scope

- Covers: the envelope, namespace and language attributes of a claims or
  description response, how claims and paragraphs are split into elements,
  and which offices answered 404.
- Does not cover: the `fulltext` inquiry service, images (see
  [EPO OPS image inquiry and retrieval](epo-ops-images.md)), or full-text
  coverage beyond the four publications sampled.
- Depended on by: `src/scholar_mcp/_epo_xml.py` (`parse_claims_xml`,
  `parse_description_xml`).

All claims below were observed by fetching with `epo_ops.Client.published_data`
through the deployed server's credentials on 2026-11-21. The responses are
vendored as `tests/fixtures/epo/claims_*.xml` and `description_*.xml`.

## Claims

### Envelope and namespace

- The document sits at `ops:world-patent-data/ftxt:fulltext-documents/ftxt:fulltext-document`,
  where `ftxt` and the default namespace inside it are
  `http://www.epo.org/fulltext`; there is no `exchange-document`. The
  `fulltext-document` carries `fulltext-format="text-only"`.
  [observed: `claims_ep3491801b1.xml`, `description_wo2018019652a1.xml`]
  [pins: tests/test_epo_xml.py::TestParseClaimsXml::test_real_ep_response]
- `claims` and `description` are children of `fulltext-document`, in the
  fulltext namespace, next to a `bibliographic-data` element that holds only
  the publication reference. [observed: all four fixtures]

### Languages

- Each language is its own `claims` element with an upper-case `lang`:
  EP3491801B1 has `DE`, `FR` and `EN`, in that order; WO2018019652A1 has only
  `EN`. [observed: `claims_ep3491801b1.xml`, `claims_wo2018019652a1.xml`]
  [pins: tests/test_epo_xml.py::TestParseClaimsXml::test_english_chosen_case_insensitively]
- Both descriptions sampled have one `description lang="EN"`.
  [observed: both description fixtures]

### How claims are split

- An EP claim set is one `claim` element holding many `claim-text`
  elements. A `claim-text` usually starts with the claim number (`1. `), but
  a claim can run on into further `claim-text` elements that carry no number:
  EP3491801B1 claim 5 continues in a `claim-text` starting "encrypting (608)".
  Line breaks inside a `claim-text` are literal newlines.
  [observed: `claims_ep3491801b1.xml`]
- A WO claim set is one `claim` with a single `claim-text` holding every
  claim. It opens with a `CLAIMS` line, and the text carries OCR spacing such
  as `(1 1 , 21 , 31 )`. Claim numbers are not reliably at a line start:
  claim 1 is written `1 .`, claims 3 and 4 follow the previous claim on the
  same line (`… base partial trees. 3. Method according to claim …`), and
  claim 13 appears as `1 3.`. [observed: `claims_wo2018019652a1.xml`]
- Concatenating the text of a `claim` element with no separator glues one
  `claim-text` to the next. [observed: `etree.tostring(..., method="text")` on
  the EP fixture] [pins: tests/test_epo_xml.py::TestParseClaimsXml::test_claim_texts_stay_apart]

## Description

- A description is a flat run of `p` elements with no attributes and no
  `heading` elements. Section headings are `p` elements of their own in upper
  case ("TECHNICAL FIELD", "BACKGROUND").
  [observed: both description fixtures]
- EP paragraphs start with their number in brackets followed by a run of
  spaces (`[0001]    Various embodiments …`); WO2018019652A1's paragraphs
  carry no number. Some EP paragraphs have no number either (list items).
  [observed: `description_ep3491801b1.xml`, 119 paragraphs of which 32 have
  no number; `description_wo2018019652a1.xml`, 88 with none]

## Coverage

- US11234567B2 and EP3491801A1 answer 404 on both endpoints.
  [observed: the same fetch] Which offices and kinds OPS holds full text for
  is not recorded. [unverified] The OPS reference guide's coverage table would
  settle it.

## Where this project departs from the subject

None: the parsers read the structure as observed.

## Not covered

- Responses with more than one `fulltext-document`.
- Description languages other than English, and whether a description is ever
  split across `description` elements.

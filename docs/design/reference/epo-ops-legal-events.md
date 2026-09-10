---
type: Reference
title: EPO OPS legal-status events
description: How OPS represents INPADOC legal-status events, and why no external code dictionary is needed to read them.
subject_version: "OPS 3.2, reference guide v1.3.20"
valid_for: "OPS 3.x"
generated:
  by: process:researching-references
  at: 2026-09-10
stale_after: 2027-09-10
status: stable
verified:
  - by: process:researching-references
    at: 2026-09-10
sources:
  - id: ops-legal-xsd
    title: OPS legal-status schema (vendored at sources/epo-ops/ops_legal.xsd)
    resource: ./sources/epo-ops/ops_legal.xsd
    accessed: 2026-09-10
  - id: ops-guide
    title: Open Patent Services RESTful Web Services Reference Guide v1.3.20 (June 2024)
    resource: https://www.epo.org/en/searching-for-patents/data/web-services/ops
    accessed: 2026-09-10
---

# EPO OPS legal-status events

The legal service returns a patent's INPADOC legal-status history. The element
names look like opaque codes — `L001EP`, `L008EP`, `L500EP` — which invites the
assumption that reading them needs a dictionary EPO publishes separately. It
does not: the response is self-describing at both levels, and this page records
that so nobody goes looking for the dictionary again.

## Scope

- Covers: the response's element structure, where an event's meaning lives, and
  which fields carry dates.
- Does not cover: the meaning of individual EPO event codes such as `17Q` or
  `26N` — EPO supplies those inline, see below. Also not covered: the T12 weekly
  exchange file, a separate bulk subscription product with its own format that
  this project does not consume.
- Depended on by: `src/scholar_mcp/_epo_xml.py` (`parse_legal_xml`) and
  `src/scholar_mcp/_epo_client.py` (`get_legal`).

## Claims

### Structure

- `code` is padded to four characters (`"17Q "`, `"AK  "`), so a consumer that
  compares codes must strip it. [observed: the fixture above]
  [pins: tests/test_epo_xml.py::TestParseLegalXml::test_code_is_stripped_of_its_padding]

- The service is `GET /legal/{type}/{format}/{number}`, and it bills the
  `inpadoc` throttle bucket, not `retrieval` — see
  [throttling](epo-ops-throttling.md).
  [source: ops-guide] [pins: tests/test_epo_client.py::test_preflight_inpadoc_blocks_get_legal]
- Each event is an `ops:legal` element carrying `code`, `desc`, `infl` and
  `dateMigr` attributes; `code` and `infl` are required.
  [source: ops-legal-xsd]
- Its children are one or more `ops:pre` elements followed by a fixed sequence
  of `L001EP`…`L533EP` elements, most optional. [source: ops-legal-xsd]
- **No element named `legal-event` exists in the schema**, and none is returned.
  Neither do `event-code`, `event-date` or `event-text`.
  [source: ops-legal-xsd]
  [observed: `tests/fixtures/epo/legal_ep1000000a1.xml`, a captured 76 KB response; `legal-event` occurs 0 times, `<ops:legal ` 50 times]
  [pins: tests/test_epo_xml.py::TestParseLegalXml::test_reads_the_shape_epo_actually_sends]

### The response is self-describing

- The event's meaning is the `desc` attribute on `ops:legal` itself, in plain
  language: `FIRST EXAMINATION REPORT DESPATCHED`, `DESIGNATED CONTRACTING
  STATES`, `REFERENCE TO A NATIONAL CODE`.
  [observed: the fixture above, 50 events across 22 distinct codes]
  [pins: tests/test_epo_xml.py::TestParseLegalXml::test_event_meaning_comes_from_the_legal_element]
- Every `L###EP` child carries its own `desc` naming the field it holds —
  `Country Code`, `Filing / Published Document`, `Document Number`, `Kind Code`,
  `IPR Type`, `Gazette DATE`, `Legal Event Code 1`, `DATE last exchanged`,
  `DATE first created`. [observed: the same fixture]
- So the `L###EP` names are **field labels within** an event, not the event's
  semantics. Reading a legal event needs no external code dictionary.
  [observed: the same fixture]
- `ops:pre` repeats the event as the raw fixed-width line INPADOC delivers,
  which is redundant with the parsed fields. [observed: the same fixture]

### Dates

- Three date-bearing fields appear and **they differ within one event**:
  `L007EP` "Gazette DATE", `L018EP` "DATE last exchanged", `L019EP` "DATE first
  created". A consumer must choose deliberately; `L007EP` is the date the event
  was published in the gazette and is the one a reader means by "when did this
  happen". [observed: the same fixture]
  [pins: tests/test_epo_xml.py::TestParseLegalXml::test_date_is_the_gazette_date]
- `dateMigr` on `ops:legal` is declared `xs:string`, not a date type.
  [source: ops-legal-xsd]

## Where this project departs from the subject

Nowhere deliberately, now that #390 is fixed. `parse_legal_xml` reads
`ops:legal/@code` and `@desc` for the event and `L007EP` for the date, exactly
as recorded above.

This page was written *before* that fix, which is what the
`researching-references` skill directs: the fix followed the recorded
behaviour rather than being another guess a later reference would contradict.
Until it landed, the parser searched for `.//ops:legal-event` — an element OPS
does not send — and returned zero events from the fifty this page's fixture
contains.

## Not covered

- The full `L###EP` vocabulary. The schema declares up to `L533EP`; only
  `L001`–`L005`, `L007`, `L008`, `L018`, `L019` and `L500` appear in the one
  patent observed. What the rest carry, and which events use them, would need a
  wider survey. Each is self-describing when it does appear, so this is a
  completeness gap rather than a comprehension one. [unverified]
- Whether `infl` (`+`, `-`, or blank in the observed data) means what it appears
  to — an event's effect on the patent's force. The schema requires the
  attribute but does not document its values. Settling it needs EPO
  documentation this pass did not find. [unverified]
- `L500EP` nests a further `L501EP`…`L533EP` choice per the schema, but appeared
  empty in every observed event. [unverified]

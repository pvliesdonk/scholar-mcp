---
type: Reference
title: Relaton bibitem titles in the relaton-data repositories
description: How ISO, IEC and IEEE Relaton YAML records list a standard's title, its parts and its languages.
subject_version: "relaton-data-iso 00c4632, relaton-data-iec 43fd17a, relaton-data-ieee 3fd7035; relaton-iso README at 66a32a9"
valid_for: "relaton-bib YAML serialisation as published in September 2026"
generated:
  by: process:researching-references
  at: 2026-09-28
stale_after: 2027-03-28
status: draft
sources:
  - id: relaton-iso-readme
    title: relaton-iso README, "Get specific language"
    resource: https://github.com/relaton/relaton-iso/blob/66a32a919dccc3647b31671b9bbf407e7aa2930b/README.adoc
    accessed: 2026-09-28
  - id: iso-27002
    title: relaton-data-iso, ISO/IEC 27002:2022
    resource: https://github.com/relaton/relaton-data-iso/blob/00c463205ca500cfef59b7c5c81db39dcda3f18a/data/iso-iec-27002-2022.yaml
    accessed: 2026-09-28
  - id: iso-27001
    title: relaton-data-iso, ISO/IEC 27001:2022
    resource: https://github.com/relaton/relaton-data-iso/blob/00c463205ca500cfef59b7c5c81db39dcda3f18a/data/iso-iec-27001-2022.yaml
    accessed: 2026-09-28
  - id: iso-3166
    title: relaton-data-iso, ISO 3166-1:2020
    resource: https://github.com/relaton/relaton-data-iso/blob/00c463205ca500cfef59b7c5c81db39dcda3f18a/data/iso-3166-1-2020.yaml
    accessed: 2026-09-28
  - id: iec-cispr
    title: relaton-data-iec, CISPR 1:1961 Amendment 1
    resource: https://github.com/relaton/relaton-data-iec/blob/43fd17a0a89bd2bdee87339b3c14380f33713dc3/data/cispr-1-1961-amd1-1967.yaml
    accessed: 2026-09-28
  - id: ieee-ire
    title: relaton-data-ieee, 55 IRE 2.S1 (IEEE Std 147)
    resource: https://github.com/relaton/relaton-data-ieee/blob/3fd70352d01c1097c2f411bf339af0ef4fe59dc0/data/55-ire-2-s1-ieee-std-147.yaml
    accessed: 2026-09-28
---

# Relaton bibitem titles in the relaton-data repositories

How a Relaton YAML record lists a standard's title. Prompted by #480, where
every synced ISO record carried only its introductory element, so ISO/IEC
27001 and 27002 shared one title.

## Scope

- Covers: the `title` list of relaton-data-iso, -iec and -ieee records: entry
  types, the composed title, languages, and how `language` is serialised.
- Does not cover: identifiers (`docid`), status, links or abstracts beyond the
  one open question below.
- Depended on by: `src/scholar_mcp/_sync_relaton.py` (`_full_title`, used by
  both the sync loaders and `_relaton_live.py`).

## Claims

### Title types

- A record lists the title's parts as separately typed entries,
  `title-intro`, `title-main` and `title-part`, and beside them one `main`
  entry holding the composed full title: "Geographic information – Metadata"
  from intro "Geographic information" and main "Metadata".
  [source: relaton-iso-readme]
  [pins: tests/test_sync_relaton.py::test_full_title_prefers_the_english_main_title]
- The `title-intro` is shared across a series. ISO/IEC 27001:2022 and
  27002:2022 both have "Information security, cybersecurity and privacy
  protection" as their intro; only `main` tells them apart.
  [source: iso-27001] [source: iso-27002]
  [pins: tests/test_sync_relaton.py::test_iso_27001_and_27002_no_longer_share_a_title]
- The parts present vary. ISO 3166-1:2020 has no `title-intro`, only
  `title-main` and `title-part`, and its `main` composes those two.
  [source: iso-3166]
- IEC records use the same types. An IEC amendment carries "Amendment 1" as
  its `title-intro`, so the first entry alone names no standard.
  [source: iec-cispr]
  [pins: tests/test_sync_relaton.py::test_full_title_prefers_the_english_main_title]
- The IEEE records sampled carry a single `main` entry and no parts.
  [source: ieee-ire]
  [pins: tests/test_sync_relaton.py::test_full_title_prefers_the_english_main_title]

### Languages

- Titles repeat per language: the ISO and IEC records sampled list the
  English set first, then French. [source: iso-27002] [source: iec-cispr]
- `language` is serialised three ways: a list (`["en"]`) in relaton-data-iso,
  a bare string (`"en"`) in relaton-data-iec, and absent or null in the IEEE
  records sampled. [source: iso-27002] [source: iec-cispr] [source: ieee-ire]
  [pins: tests/test_sync_relaton.py::test_full_title_prefers_the_english_main_title]
- That English always comes first is not established; six ISO, two IEC and
  two IEEE records were read. [unverified] A scan of each repository's
  `title` lists would settle it.

## Where this project departs from the subject

`_full_title` prefers the English `main`, then any `main`, then the first
entry's text. It never composes a title from the parts itself: where `main`
is missing, the source stated no full title, so the first entry is kept as
before rather than a format the source did not use.

## Not covered

- Whether every record has a `main` entry. [unverified] A repository-wide
  count of records without one would settle it; the fallback covers them
  meanwhile.
- `_yaml_to_record` also takes the scope from `abstract[0]` by position. That
  is correct when English comes first, which the samples show but no source
  states. [unverified]

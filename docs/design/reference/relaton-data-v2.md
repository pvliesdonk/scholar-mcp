---
type: Reference
title: Relaton data dumps on the v2 branch
description: Which branch of relaton-data-iso, -iec and -ieee carries current data, and how a v2 record writes its identifiers, stage, links, dates, relations and committee.
subject_version: "relaton-data-iso dd368d8, relaton-data-iec 62f97ae, relaton-data-ieee 3d05ff3 (v2); main at 10285fc, c7029ab, 3bd8be0"
valid_for: "relaton-data v2 branches, schema_version v1.1.x, as published in November 2026"
generated:
  by: process:researching-references
  at: 2026-11-15T10:05:00+00:00
verified:
  - by: process:researching-references
    at: 2026-11-15T10:05:00+00:00
stale_after: 2027-05-15T00:00:00+00:00
status: stable
sources:
  - id: repo-api
    title: GitHub REST API, repository and commits of relaton-data-iso, -iec and -ieee (default_branch; commits on main and v2)
    resource: https://api.github.com/repos/relaton/relaton-data-iso
    accessed: 2026-11-15
  - id: iso-readme
    title: relaton-data-iso README, "Crawler"
    resource: https://github.com/relaton/relaton-data-iso/blob/dd368d8de2cb27d47ea6ff5b5874aa78cbb39e30/README.adoc
    accessed: 2026-11-15
  - id: iso-v2
    title: relaton-data-iso tarball at v2 dd368d8 (80,202 records under data/)
    resource: https://github.com/relaton/relaton-data-iso/tree/dd368d8de2cb27d47ea6ff5b5874aa78cbb39e30/data
    accessed: 2026-11-15
  - id: iec-v2
    title: relaton-data-iec tarball at v2 62f97ae (33,042 records under data/, 32,819 under data/projects/)
    resource: https://github.com/relaton/relaton-data-iec/tree/62f97ae330f2723e7395ddefe7c3c23081f4ba27/data
    accessed: 2026-11-15
  - id: ieee-v2
    title: relaton-data-ieee tarball at v2 3d05ff3 (12,635 records under data/)
    resource: https://github.com/relaton/relaton-data-ieee/tree/3d05ff31cfaaabbcc8657f256c38eb565d42dded/data
    accessed: 2026-11-15
  - id: iso-27001-2005
    title: relaton-data-iso, ISO/IEC 27001:2005, on v2 and on main
    resource: https://github.com/relaton/relaton-data-iso/blob/dd368d8de2cb27d47ea6ff5b5874aa78cbb39e30/data/iso-iec-27001-2005.yaml
    accessed: 2026-11-15
  - id: main-tarballs
    title: relaton-data-iso, -iec and -ieee tarballs at main 10285fc, c7029ab and 3bd8be0
    resource: https://github.com/relaton/relaton-data-iso/tree/10285fc356c8523838f688950687eab91bb6b220
    accessed: 2026-11-15
---

# Relaton data dumps on the v2 branch

Which branch of the Relaton data repositories carries current data, and how a
record on it is shaped. Prompted by #641: the sync and the live lookup read
`main`, which had stopped receiving data, and the parser read field names only
`main` uses.

## Scope

- Covers: the branches of relaton-data-iso, -iec and -ieee; in a `v2` record,
  the identifier list, the stage, the links, the dates, the relations and the
  committee; the filename of a record; what disappears from a dump.
- Does not cover: the title list (see
  [Relaton bibitem titles](relaton-titles.md), whose claims hold on `v2`
  except that ISO now writes `language` as a string); the `ext` fields beyond
  the status ones; the other relaton-data repositories.
- Depended on by: `src/scholar_mcp/_sync_relaton.py` (`RelatonConfig.branch`,
  `_yaml_to_record` and its helpers, `_parse_tarball_sync`,
  `RelatonLoader._remove_missing`) and `src/scholar_mcp/_relaton_live.py`
  (`_identifier_to_relaton_slug`, the raw URL).

## Claims

### Branches

- All three repositories have `v2` as their default branch.
  [source: repo-api]
- `main` no longer receives data. The last data commit ("update documents")
  on `main` is 2025-06-02 for ISO, 2026-04-30 for IEC and 2025-08-31 for IEEE.
  ISO's `main` has fix commits after that, the last on 2026-04-07. `v2` was
  updated on 2026-11-11 (ISO), 2026-11-14 (IEC) and 2026-09-28 (IEEE).
  [source: repo-api]
  [pins: tests/test_sync_relaton.py::test_loader_cold_sync_inserts_records]
- A daily crawler rebuilds ISO's `data/` from the ISO Open Data feed, skipping
  the crawl when the feed has not changed. [source: iso-readme]

### Files

- A publication lives at `data/<slug>.yaml`. The slug is the primary
  identifier lowercased, with every run of characters other than letters,
  digits and `+ & _ [ ]` turned into one hyphen: `ISO/IEC 27001:2022` is
  `iso-iec-27001-2022`, `IEEE Std 802.11-2016` is `ieee-std-802-11-2016`,
  `CISPR 11:2015+AMD1:2016 CSV` is `cispr-11-2015+amd1-2016-csv`.
  [observed: the rule against every `data/` file of the three tarballs; it
  misses 10 ISO drafts whose names carry a hash suffix and 8 IEEE records with
  bracketed nicknames, and matches all 33,042 IEC records]
  [pins: tests/test_relaton_live.py::test_identifier_to_slug_matches_v2_filenames]
- On `main`, IEC filenames used underscores (`cispr_10_1971.yaml`) and IEEE
  filenames an uppercase-underscore form (`IEEE_STD_1588-2019.yaml`). Every
  IEEE filename on `main` is absent from `v2`. [source: main-tarballs]
- IEC's `v2` also holds `data/projects/`, one record per work item: stages such
  as `30.97 MERGED` and `99.60 DELPUB`, and relations to `iec:proj:` URNs. These
  are not publications. [source: iec-v2]
  [pins: tests/test_sync_relaton.py::test_parse_tarball_sync_skips_iec_projects]
- ISO's `v2` lists drafts and projects at every stage (WD, CD, DIS, NP, PWI,
  AWI) beside the publications. [source: iso-v2]

### Identifiers

- The list is `docidentifier`, each entry holding its text under `content`
  (on `main`, `docid` with `id`). Every record has exactly one entry with
  `primary: true` that is not a trademark variant. [source: iso-v2]
  [source: iec-v2] [source: ieee-v2]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_plain_iso]
- An ISO record also lists an `iso-reference` (`ISO 9001:2015(E)`), a `URN`
  and, for 58,711 of 80,202 records, an `iso-undated` entry (`ISO 9001`) that
  every edition of the standard shares. [source: iso-v2]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_alias_skips_undated_and_non_string]
- An IEEE record lists the identifier twice as primary, once plain and once
  with `scope: trademark` (`IEEE Std 1003.1™-2024`), and usually an ISBN and a
  DOI. Published standards keep "Std" in the identifier. [source: ieee-v2]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_plain_ieee]
- A joint ISO/IEC publication carries only entries of its own repository's
  type: the ISO record of ISO/IEC 27001:2022 has no `IEC`-typed entry. The same
  held on `main`. [source: iso-v2] [source: main-tarballs]

### Stage

- ISO and IEC write `status: {stage: {content: "95"}, substage: {content: "99"}}`,
  the two halves of the harmonized stage code; two IEC records write
  `stage: {content: PUBLISHED}`. On `main` the block was `docstatus`, with
  `value` for `content`. [source: iso-v2] [source: iec-v2]
  [source: iso-27001-2005]
  [pins: tests/test_sync_relaton.py::test_harmonized_status]
- In the ISO dump, 29,715 records are at 95.99 (withdrawn); 90.93, 60.60 and
  90.92 follow. 23,934 records are below 60.60; 18,528 of them are projects
  that ended at a substage 98. [source: iso-v2]
- An IEC publication is at 60.60 or 95.99, and `ext.stagename` says why a
  95.99 edition went: `REVISED` (13,021), `REPLACED` (2,807) or `WITHDRAWN`
  (1,638). [source: iec-v2]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_status_from_v2_stage]
- IEEE writes a word in `status.stage.content` (`draft` 7,060, `approved`
  1,657, `withdrawn` 678, `superseded` 6) or no `status` at all (3,234). Every
  record has `ext.standard_status`: `Active`, `Inactive` or `Superseded`; a
  record without a stage is `Superseded` (2,099), `Inactive` (749) or `Active`
  (386). [source: ieee-v2]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_status_from_v2_stage]

### Links and dates

- Links are under `source` (on `main`, `link`), typed `src`, `obp` or `rss`
  for ISO, `src` and sometimes `obp` for IEC, `src` for IEEE.
  [source: iso-v2] [source: iec-v2] [source: ieee-v2]
- A date entry holds its value under `at` (on `main`, `value`).
  [source: iso-27001-2005]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_plain_iso]

### Relations

- Relation types are camel case: ISO uses `obsoletedBy`, `obsoletes`,
  `updates` and `updatedBy`; IEEE uses `updates`, `obsoletedBy` and
  `adoptedFrom`. Each related bibitem has one `docidentifier`, the primary one.
  [source: iso-v2] [source: ieee-v2]
  [pins: tests/test_sync_relaton.py::test_related_identifiers_ignores_other_types]
- On `v2`, ISO/IEC 27001:2005 names 2013 under `obsoletedBy`; on `main` it
  named it under `updates`. [source: iso-27001-2005]
  [pins: tests/test_sync_relaton.py::test_yaml_to_record_withdrawn_iso_edition_is_superseded]
- Every ISO `obsoletedBy` and every IEEE `obsoletedBy` target is the primary
  identifier of a record in the same dump. [observed: all 34,688 ISO and 1,350
  IEEE targets looked up in the parsed tarballs]
- ISO links an edition still current (90.92, 90.93, 60.60) to the draft of its
  revision under `obsoletedBy` (`ISO/DIS 10485`), about 4,900 times; it also
  links withdrawn editions to drafts. [source: iso-v2]
  [pins: tests/test_sync_relaton.py::test_current_edition_keeps_empty_superseded_by_despite_draft_revision]
- An IEC publication under `data/` carries no relations; the work items under
  `data/projects/` relate only through `iec:proj:` and `iec:pub:` URNs.
  [source: iec-v2]

### Committee

- The committee is a `subdivision` of the contributor whose role is `author`
  (described `committee`). ISO puts the committee designation in its
  `identifier` (`ISO/IEC JTC 1/SC 27`); IEC puts only the number there (`65`)
  and `TC 65` in the `name`; IEEE gives only a `name`. There is no
  `editorialgroup`, and on `main` the parser's `editorialgroup` read gave no
  committee either. [source: iso-v2] [source: iec-v2] [source: ieee-v2]
  [pins: tests/test_sync_relaton.py::test_committee_from_author_subdivision]

### What disappears

- A withdrawn edition stays in the dump at 95.99, so a record missing from a
  later dump was renamed or advanced from draft, not withdrawn.
  [source: iso-v2] [source: iec-v2]
  [pins: tests/test_sync_relaton.py::test_loader_removes_records_the_dump_no_longer_lists]
- Of the identifiers the sync parsed from `main`, 14.0% of ISO's, 0.5% of
  IEC's and 68.2% of IEEE's are absent from `v2`. The IEEE ones are mostly
  drafts written in a new form (`IEEE P1003.1/D-4/Cor2-2016-05` on `main`);
  ANSI/IEEE standards also lost the "Std" (`ANSI/IEEE 1000-1987`).
  [observed: identifier sets of both parses compared]
  [pins: tests/test_sync_relaton.py::test_loader_removes_renamed_identifiers_even_past_half]

## Departures

- `superseded_by` is filled only when the stage says the edition is withdrawn,
  so the draft links on current ISO editions are not read as replacements.
- An IEC edition at 95.99 marked `REVISED` or `REPLACED` reports `superseded`
  with an empty `superseded_by`, because its successor is named only by a
  project URN (#644).
- A joint publication gets the body of the repository it was synced from
  (#643).

## Not covered

- What `updates` and `updatedBy` mean across the dumps (amendment, revision);
  the parser reads neither. Relaton's model documentation would settle it.
- Whether Relaton announced the move to `v2` or a date for retiring `main`.

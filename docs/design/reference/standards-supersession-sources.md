---
type: Reference
title: Replaced-edition data for IETF, NIST and W3C
description: Where IETF, NIST and W3C publish that a document was replaced or withdrawn, in their live services and in the Relaton data dumps, and how far each source covers it.
subject_version: "datatracker API v1, CSRC pubs-export, NIST-Tech-Pubs release Oct2026, api.w3.org, relaton-data-{ietf,nist,w3c} as of 2026-11-13"
valid_for: "these services and dumps as served in November 2026"
generated:
  by: process:researching-references
  at: 2026-11-14T18:30:00+01:00
stale_after: 2027-05-14T18:30:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-14T18:30:00+01:00
status: draft
sources:
  - id: relaton-data-ietf
    title: relaton-data-ietf README and data/rfc*.yaml
    resource: https://github.com/relaton/relaton-data-ietf
    accessed: 2026-11-14
  - id: relaton-data-nist
    title: relaton-data-nist at d85f80238138ad7561ff18731cf584c26711ca4e
    resource: https://github.com/relaton/relaton-data-nist/tree/d85f80238138ad7561ff18731cf584c26711ca4e
    accessed: 2026-11-14
  - id: relaton-data-w3c
    title: relaton-data-w3c at 57329d53b3860f1d64c1a266a637eb8ad06ea3e6
    resource: https://github.com/relaton/relaton-data-w3c/tree/57329d53b3860f1d64c1a266a637eb8ad06ea3e6
    accessed: 2026-11-14
  - id: relaton-data-nist-old
    title: ietf-tools/relaton-data-nist commit history
    resource: https://github.com/ietf-tools/relaton-data-nist/commits
    accessed: 2026-11-14
  - id: relaton-nist-pubs-export
    title: relaton-nist PubsExport (lib/relaton_nist/pubs_export.rb)
    resource: https://github.com/relaton/relaton-nist/blob/main/lib/relaton_nist/pubs_export.rb
    accessed: 2026-11-14
  - id: csrc-pubs-export
    title: CSRC publications export (pubs-export.zip)
    resource: https://csrc.nist.gov/CSRC/media/feeds/metanorma/pubs-export.zip
    accessed: 2026-11-14
  - id: nist-tech-pubs
    title: usnistgov/NIST-Tech-Pubs release Oct2026, allrecords-MODS.xml
    resource: https://github.com/usnistgov/NIST-Tech-Pubs/releases/tag/Oct2026
    accessed: 2026-11-14
  - id: datatracker-api
    title: IETF datatracker API v1, doc/document and doc/relateddocument
    resource: https://datatracker.ietf.org/api/v1/doc/relateddocument/
    accessed: 2026-11-14
  - id: w3c-api
    title: W3C API, specifications and versions
    resource: https://api.w3.org/specifications/html401
    accessed: 2026-11-14
---

# Replaced-edition data for IETF, NIST and W3C

Research #120 asked whether the Relaton data dumps should replace this
project's live fetchers for the Tier 1 bodies. The question that mattered
for the `040 standards-reliability` package is narrower: where does each
body say that a document was replaced or withdrawn (#592)? This page records,
for IETF, NIST and W3C, what the live services and the Relaton dumps carry.
ETSI has its own page, [ETSI standards search data endpoint](etsi-standards-search.md).

## Scope

- Covers: supersession and withdrawal data for RFCs, NIST publications and
  W3C specifications, in the services the fetchers call today and in the
  Relaton dumps, plus each dump's freshness.
- Does not cover: titles, authors and the other bibliographic fields, the
  Relaton dumps for ISO, IEC and IEEE (already synced, see
  [Relaton bibitem titles](relaton-titles.md)), or how the project should
  model a replacement.
- Depended on by: #592 (replaced editions report `published`). No code reads
  these sources for supersession yet, so no claim here is pinned.

## Claims

### What the project's fetchers return today

- The live IETF, NIST and W3C fetchers all return records:
  `_IETFFetcher.get("RFC 2616")`, `_NISTFetcher.get("NIST SP 800-53 Rev. 4")`,
  `_NISTFetcher.get("FIPS 186-4")` and `_W3CFetcher.get("html401")`. Every one
  reports `status: "published"` and `superseded_by: None`, although RFC 2616
  is obsoleted, SP 800-53 Rev. 4 and FIPS 186-4 are withdrawn, and HTML 4.01 is
  retired. [observed: the fetchers called with a bare `httpx.AsyncClient`,
  2026-11-14]
- The W3C normaliser reads `latest-status` or `status` from the specification
  object. The API puts neither key there; the latest version's status is the
  `title` of `_links.latest-version`. So every W3C record falls through to
  `published`. [observed: `https://api.w3.org/specifications/html401` and
  read of `_normalize_w3c`, 2026-11-14] [source: w3c-api]
- The W3C record's `url` and `full_text_url` are the API's version URL
  (`https://api.w3.org/specifications/html401/versions/20180327`), not the
  document at `www.w3.org/TR/`. Its `identifier` is the title. [observed, as
  above]
- The IETF record has `published_date: None` for RFC 2616 and RFC 9110. The
  datatracker document object carries `pub_date: null` for an RFC. [observed:
  `datatracker.ietf.org/api/v1/doc/document/rfc2616/`, 2026-11-14]

### IETF

- datatracker lists the RFCs that obsolete a given RFC at
  `/api/v1/doc/relateddocument/?target__name=rfc2616&relationship=obs`. Each
  object's `source` is the obsoleting document. For RFC 2616 it returned RFC
  7230 to 7235. [observed, 2026-11-14] [source: datatracker-api]
- relaton-data-ietf carries the same fact in each record as
  `relation: - type: obsoletedBy`, and a `status.stage` that is the RFC's
  standards level (`DRAFT STANDARD`, `HISTORIC`). On four samples the
  obsoleting RFCs match datatracker exactly: RFC 2616 (7230 to 7235), RFC 793
  (9293), RFC 2246 (4346), RFC 7230 (9110, 9112). [observed:
  `data/rfc{2616,793,2246,7230}.yaml` and the datatracker query above,
  2026-11-14] [source: relaton-data-ietf]
- relaton-data-ietf is rebuilt daily (commits on 2026-11-11, 12 and 13). Its
  index lists 181,733 records, Internet-Drafts included. [observed: commit
  history and `index-v2.yaml`, 2026-11-14] [source: relaton-data-ietf]

### NIST

- The active NIST dump is `relaton/relaton-data-nist` (default branch `v2`,
  daily commits). `ietf-tools/relaton-data-nist`, the repository #120 links,
  had its last data commit on 2023-07-19. [source: relaton-data-nist]
  [source: relaton-data-nist-old]
- relaton-data-nist does not mark a final publication as withdrawn or
  replaced. Of 20,299 records, 315 carry a `status`, all `draft-public`. Its
  relations are `updates` (139), `editionOf` (34), `updatedBy` (4) and
  `obsoletes` (1). There is no `obsoletedBy`. The records for SP 800-53 Rev. 4
  and FIPS 186-4 carry no status and no relation. [observed: `grep` over a
  depth-1 clone of `data/`, 2026-11-14]
- The NIST-Tech-Pubs MODS file, which `_NISTFetcher` downloads, is no better.
  Of 20,399 records, 4 have `relatedItem type="succeeding"` and 139
  `type="preceding"`. 61 `note` lines say "Superseded by" in free text. The SP
  800-53 Rev. 4 record has only a `series` related item and no such note. [observed: `grep` over
  `allrecords-MODS.xml` from release `Oct2026`, 2026-11-14]
  [source: nist-tech-pubs]
- CSRC's publications export does carry it. Each of its 942 entries has
  `status` (`final` or `draft-public`), `substage` (`active`, `withdrawn` or
  `retired`), `superseded-by` and `supersedes` (lists of `{uri,
  docidentifier}`) and `obsoleted-date`. FIPS 186-4 is `withdrawn`, superseded
  by FIPS 186-5, obsoleted 2024-02-03. [observed: `pubs-export.json`,
  `Last-Modified` 2026-11-13, 2026-11-14] [source: csrc-pubs-export]
  relaton-nist's `main` branch has a reader for this export (`PubsExport`);
  where relaton-nist calls it was not traced. [source: relaton-nist-pubs-export]
- The export has three limits. It covers only CSRC's publications, 942
  entries against about 20,000 in MODS. It writes identifiers as `SP 800-53
  Rev. 4` and `FIPS 186-4`, without the `NIST` prefix. And it lists one entry
  per update, so `SP 800-53 Rev. 4` appears four times, three of them
  "superseded" by its own later updates (`.../r4/upd1/final`). Only the entry
  whose `superseded-by` points at a different `docidentifier` (`SP 800-53
  Rev. 5`) records the replacement. [observed, as above]

### W3C

- The W3C API marks replacement in two places. A specification's
  `_links.latest-version.title` is the latest version's status (`Retired` for
  `html401`, `Recommendation` for `WCAG20`). A replaced specification has a
  `superseded-by` link, and the replacing one a `supersedes` link: Web Forms
  2.0 is superseded by HTML5. [observed:
  `https://api.w3.org/specifications/{html401,html5,web-forms-2,WCAG20}` and
  their `superseded` and `supersedes` collections, 2026-11-14]
  [source: w3c-api]
- relaton-data-w3c holds one record per specification and one per dated
  version. Of 17,838 records, 16,140 carry a `status.stage`, the version's
  maturity (`Working Draft`, `Recommendation`, 335 `Retired`). The
  specification record (`html401.yaml`) has no status. The dated record for
  the latest version (`spsd-html401-20180327.yaml`) has `Retired`.
  [observed: depth-1 clone, 2026-11-14] [source: relaton-data-w3c]
- Its `obsoletes` (14,426) and `updatedBy` (14,410) relations link versions in
  one specification's history, such as a PR to the WD it followed. No record
  mentions "superseded", and Web Forms 2.0 has no record at all, so the
  specification-to-specification replacement the API carries is absent.
  [observed, as above]

### Licensing

- None of relaton-data-ietf, relaton-data-nist or relaton-data-w3c declares a
  licence in GitHub's metadata, and only relaton-data-ietf has a README. That
  README describes the data, not its terms. [observed: `gh api repos/...`,
  2026-11-14] [unverified] The terms for redistributing the dumps are
  unknown. Asking the Relaton maintainers would settle it.

## Where this project departs from the subject

- All three fetchers drop the replacement data their sources carry or could
  carry: IETF never asks datatracker for `obs` relations, NIST reads MODS
  rather than the CSRC export, and W3C reads status keys the API does not
  send. This is #592.

## Not covered

- How many RFCs, NIST or W3C documents disagree between dump and live
  service. Only the samples named above were compared.
- CSRC export coverage for NIST series outside CSRC (for example NBS
  circulars and NISTIRs not on CSRC).
- datatracker's other relationships (`updates`, `tobcp`, `tohist`) and how
  they bear on status.
- Rate limits for datatracker and api.w3.org under the extra requests a
  supersession lookup adds.

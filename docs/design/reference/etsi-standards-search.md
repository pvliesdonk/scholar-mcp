---
type: Reference
title: ETSI standards search data endpoint
description: Which interface serves ETSI standards metadata today, the shape of its JSON rows, and how its search, status and supersession fields behave.
subject_version: "www.etsi.org standards search (WordPress theme script.js) as served 2026-11-13"
valid_for: "the custom/standardssearch/data.php endpoint as served from November 2026"
generated:
  by: process:researching-references
  at: 2026-11-13T19:30:00+01:00
stale_after: 2027-05-13T19:30:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-13T19:30:00+01:00
status: draft
sources:
  - id: etsi-script
    title: ETSI standards search page script (wp-content/themes/etsi/standards/js/script.js)
    resource: https://www.etsi.org/wp-content/themes/etsi/standards/js/script.js
    accessed: 2026-11-13
  - id: etsi-page
    title: ETSI Standards page, search form formStandardsSearch
    resource: https://www.etsi.org/standards/
    accessed: 2026-11-13
  - id: etsi-robots
    title: www.etsi.org robots.txt
    resource: https://www.etsi.org/robots.txt
    accessed: 2026-11-13
  - id: relaton-etsi-fetcher
    title: relaton-etsi DataFetcher (lib/relaton_etsi/data_fetcher.rb)
    resource: https://github.com/relaton/relaton-etsi/blob/10aa1e34a9004a16f81e5cb0a998b2c68781ce13/lib/relaton_etsi/data_fetcher.rb
    accessed: 2026-11-13
  - id: relaton-data-etsi
    title: relaton-data-etsi repository, latest commit
    resource: https://github.com/relaton/relaton-data-etsi/commit/5a90051048e2424bca3d9a3d301c153d55c7113f
    accessed: 2026-11-13
---

# ETSI standards search data endpoint

ETSI documents no public API for its standards catalogue. The search page on
`www.etsi.org` calls a JSON endpoint of its own, and relaton-etsi calls the same
endpoint to build relaton-data-etsi. This page records that endpoint: where it
is, which parameters it takes, the shape of a row, and what its status and
supersession fields mean. ETSI publishes none of this, so almost every claim
is an observation or comes from reading the site's own client script.

## Scope

- Covers: the search endpoint, its parameters and paging, the row shape, the
  status and supersession fields, the `superseded.php` companion, the
  `/deliver/` PDF tree, and how the request filter in front of the site treats
  non-browser clients.
- Does not cover: the ETSI work programme portal (`portal.etsi.org`,
  `webapp.etsi.org`), the CSV and ZIP exports, the alert subscription, or the
  harmonised-standards filter (`harmonized=1`).
- Depended on by: `src/scholar_mcp/_standards_client.py` (`_ETSIFetcher`,
  `_normalize_etsi`). The roadmap's `040 standards-reliability` package
  depends on it too: #592 (replaced editions) and #120 (Relaton for Tier 1).

## Claims

### Where the interface is

- The search page's form (`formStandardsSearch`) submits through the
  JavaScript function `standardssearchGetData()`. That function sends a `GET`
  to `https://www.etsi.org/custom/standardssearch/data.php?format=json&page=N&…`,
  followed by every named field of the form. [source: etsi-script]
  (`standardssearchGetURI`) [source: etsi-page]
- `data.php` answers with `200 application/json`. [observed: `curl` and a bare
  `httpx.AsyncClient(timeout=30.0)` on 2026-11-13, `search=ETSI EN 303 645`]
- relaton-etsi builds relaton-data-etsi from the same `data.php` URL, with
  `includeScope=1` and every status flag on. relaton-data-etsi took a commit on
  2026-11-13, so the endpoint is in active third-party use.
  [source: relaton-etsi-fetcher] [source: relaton-data-etsi]
- The old Joomla route
  `https://www.etsi.org/?option=com_standardssearch&view=data&format=json`,
  which `_ETSIFetcher` called until #624, answers a client the filter lets through
  with `200 text/html` (a page, not data). [observed: bare httpx client,
  2026-11-13] The route no longer exists, and an HTML 200 is how a request to it
  looks today.

### The request filter

- A Cloudflare-fronted web application firewall answers `403 text/html`
  ("This transfer is blocked by a Web Application Firewall … Event Type
  signature") to curl's default `User-Agent` (`curl/8.x`). It does so on
  `data.php`, the old Joomla route and `/deliver/` alike. [observed: `curl -sS`
  with and without `-A "curl/8.11.0"`, 2026-11-13]
- The same requests succeed with `User-Agent: python-httpx/0.28.1` (what the
  standards client sends, since `domain.py` builds it without a `User-Agent`),
  with `scholar-mcp/0.1`, with a browser string, and with no `User-Agent`
  header at all. [observed: curl with each header, and the bare httpx client,
  2026-11-13] Only the user-agent strings listed here were tried.
- So there are two separate failures. A `403` is this filter. A `200` with
  HTML is the dead Joomla route. The `403` reported from the Docker host with
  `curl` in #401 fits the filter. [observed, as above] Whether the filter
  treats the deployed container's address differently was not tested.
- `robots.txt` disallows `/?s=` and `/search/` for every agent. It says
  nothing about `/custom/` or `/deliver/`. [source: etsi-robots]

### Parameters

- The form's fields, by name: `search` (free text); the checkboxes `title`,
  `etsiNumber` and `content` (which fields `search` matches); the radio
  `version` (`0` or `1`); the status checkboxes `onApproval`, `published`,
  `withdrawn`, `historical`, `isCurrent` and `superseded`; `startDate` and
  `endDate`; the hidden `harmonized=0`; and the multi-selects `keyword`, `TB`,
  `stdType`, `frequency`, `mandate`, `collection` and `sort`. The script sends an
  unchecked checkbox as `name=0` and joins several selected options with `,,`.
  [source: etsi-page] [source: etsi-script]
- These are the same names and values as `_ETSI_JOOMLA_PARAMS` (renamed
  `_ETSI_SEARCH_PARAMS` in #624). Sending that dict unchanged to `data.php`
  returns data. [observed: bare httpx client with
  `{**_ETSI_JOOMLA_PARAMS, "search": ..., "page": 1}`, 2026-11-13]
- `includeScope=1` fills each row's `Scope`. Without it, `Scope` is `null`.
  [source: relaton-etsi-fetcher] [observed: `search=EN 303 645` with and
  without `includeScope=1`, 2026-11-13]
  [pins: tests/test_standards_client.py::test_etsi_search_requests_data_endpoint]
- `content=1` also matches document content, and that changes exact lookups.
  With `content=1`, `search=ETSI EN 303 645` returned 27,442 hits and
  `search=ETSI TS 102 690-1`, a number with no ETSI deliverable, returned
  27,487 with `ETSI EN 301 908-2 V13.1.1` first. With `content=0`, the same
  searches returned 2 hits (EN 303 645 V3.1.3 first) and 0.
  [observed: bare httpx client, `_ETSI_JOOMLA_PARAMS` with `content` varied,
  2026-11-13]
  [pins: tests/test_standards_client.py::test_etsi_search_requests_data_endpoint]
- Even with `content=0`, a search for an identifier can return other
  deliverables: the second of the two hits for `ETSI EN 303 645` is
  `ETSI TS 103 929 V1.2.1`. So the first row is not necessarily the one
  asked for. [observed: `content=0`, `includeScope=1`, 2026-11-14]
  [pins: tests/test_standards_client.py::test_etsi_get_skips_rows_for_other_identifiers]
- `version=1` adds earlier versions that are not flagged `superseded` (for
  example `ETSI TS 103 929 V1.1.1` beside V1.2.1). `superseded=1` adds versions
  flagged `superseded` (for example `ETSI EN 303 645 V2.1.1`). The two flags
  are independent. [observed: `search=ETSI EN 303 645`, `content=0`, one flag
  varied from `_ETSI_JOOMLA_PARAMS`, 2026-11-13]

### Paging and empty answers

- A page holds 50 rows. Every row carries `total_count`, the size of the whole
  result set, as a string. [observed: 50 rows with `total_count` `"2482"`,
  2026-11-13] [source: relaton-etsi-fetcher] (`PAGE_SIZE = 50`)
- A search with no hits answers `200` with `[]`. So does a page past the last
  one, and so does a non-numeric `page`. [observed: `search=zzqxjvnonexistentqq`;
  `page=2` of a 4-row result; `page=abc`; 2026-11-13] An empty array therefore
  does not separate "no such standard" from a malformed request.
- The page script checks for an object with an `error` key before it reads the
  result as an array. [source: etsi-script] (`standardssearchGetData`) No
  `data.php` request produced one. [observed, 2026-11-13]

### Row shape

- A row's keys are `RowNum`, `total_count`, `wki_id`, `TITLE`, `WKI_REFERENCE`,
  `EDSpathname`, `EDSPDFfilename`, `EDSARCfilename`, `ETSI_DELIVERABLE`,
  `STATUS_CODE`, `ACTION_TYPE`, `IsCurrent`, `superseded`, `ReviewDate`,
  `new_versions`, `Scope`, `TB` and `Keywords`. Every value is a string or
  `null`. [observed: `search=EN 303 645`, 2026-11-13]
- `_normalize_etsi` reads nine of those keys: `ETSI_DELIVERABLE`, `TITLE`,
  `EDSpathname`, `EDSPDFfilename`, `ACTION_TYPE`, `STATUS_CODE`, `superseded`,
  `Scope` and `TB`; `get()` also reads `wki_id` and `total_count`.
  [observed: read of `_normalize_etsi` and `_ETSIFetcher.get`, 2026-11-15]
  [pins: tests/test_standards_client.py::test_etsi_normalize_row_fields]
- `ETSI_DELIVERABLE` carries the identifier, version and date in one string:
  `ETSI EN 303 645 V3.1.3 (2024-09)`. [observed, as above] `_normalize_etsi`
  splits it into identifier, revision and date.
  [pins: tests/test_standards_client.py::test_etsi_normalize_row_fields]
- The PDF is at `https://www.etsi.org/deliver/` + `EDSpathname` +
  `EDSPDFfilename`. [source: relaton-etsi-fetcher] [observed: the
  `/deliver/etsi_en/303600_303699/303645/` directory listing, 2026-11-13]
  [pins: tests/test_standards_client.py::test_etsi_normalize_pdf_url]
- A work item's details page is
  `https://webapp.etsi.org/workprogram/Report_WorkItem.asp?WKI_ID=` + `wki_id`.
  [source: relaton-etsi-fetcher] Not fetched.

### Status and supersession

- relaton-etsi derives the status this way: `ACTION_TYPE == "WD"` is
  withdrawn, a `STATUS_CODE` below 12 is on approval, `13` is historical, and
  anything else is published. [source: relaton-etsi-fetcher] (`derive_status`)
  This is relaton's reading. ETSI documents no codes.
- Observed values match that reading. Current publications carry `PU`/`12`.
  A search restricted to withdrawn and historical documents returned `PU`/`13`
  (47 rows) and `WD`/`50` (3 rows). [observed: `search=EN 300`, only
  `withdrawn=1` and `historical=1`, 2026-11-13]
- The fetcher's search flags (`withdrawn=0`, `historical=0`,
  `superseded=0`) leave those editions out. Until #640, `get()` used them and
  answered `None` for a deliverable whose newest edition was historical
  (`ETSI EN 300 833`), withdrawn (`ETSI EN 300 778-1`) or replaced
  (`ETSI EN 300 328-1`). [observed: `StandardsClient.get_with_failures`
  live, 2026-11-15]
- `get()` now asks with all three flags on and keeps the newest edition of the
  requested deliverable by date, then version, since ETSI's order is not by
  date. A historical or withdrawn edition reports `withdrawn`, a flagged one
  `superseded`; `search()` keeps the three flags off. [observed, as above]
  [pins: tests/test_standards_client.py::test_etsi_get_historical_deliverable_is_withdrawn, tests/test_standards_client.py::test_etsi_get_picks_the_newest_edition_over_a_replaced_one, tests/test_standards_client.py::test_etsi_search_requests_data_endpoint]
- With the three flags on, a deliverable's own editions can fill the page:
  `ETSI EN 301 908-1` returned exactly 50 rows (`total_count` 50, page 2
  empty), 10 of them its own editions. A lookup whose `total_count` exceeds
  the page is logged, not paged. [observed: pages 1 to 3, 2026-11-15]
  [pins: tests/test_standards_client.py::test_etsi_get_logs_a_lookup_longer_than_one_page]
- `superseded` is `"1"` on an edition ETSI marks as replaced. For example,
  `ETSI EN 303 645 V2.1.1` is `"1"` and V3.1.3 is `"0"`. Older versions of a
  TS without a later EN were `"0"` (`ETSI TS 102 690` V1.1.1 and V1.2.1 beside
  V2.1.1). The flag is not "a newer version exists". [observed: `content=0`,
  every status flag on, 2026-11-13]
- `superseded.php?wki_id=<id>` returns, as a row array, the editions that
  replace that work item. It returned V3.1.3 (`wki_id` 69970) for EN 303 645
  V2.1.1 (`wki_id` 57991). For an edition nothing replaces, it returned
  `{"error": "Error: An unexpected error occurred. Please try again later."}`
  with status `200`. [source: etsi-script] (the `superseded.php` call)
  [observed: `wki_id=57991` and `wki_id=69970`, 2026-11-13]
- Of nine flagged editions sampled, seven were replaced by a later edition of
  the same deliverable and two by another deliverable: EN 300 328-1 V1.3.1 and
  EN 300 328-2 V1.2.1 by EN 300 328 V1.4.1. Historical and withdrawn
  editions are not flagged, and `superseded.php` returns its error object for
  them. [observed: the flagged editions of EN 303 645, EN 301 908 and
  EN 300 328, and three historical and two withdrawn EN 300 editions,
  2026-11-15]
- `get()` calls `superseded.php` only for a newest edition that is flagged,
  and lists the other deliverables it names; the error object leaves the list
  empty and the status `superseded`, and a refused or non-JSON answer raises.
  [pins: tests/test_standards_client.py::test_etsi_get_replaced_deliverable_names_its_replacement, tests/test_standards_client.py::test_etsi_get_replaced_edition_with_no_named_replacement, tests/test_standards_client.py::test_etsi_get_raises_when_replacement_lookup_fails]
- `IsCurrent` was `"0"` on `ETSI EN 303 645 V3.1.3`, the latest edition, and
  `"1"` on `ETSI EN 300 328 V2.2.2` and `ETSI EN 301 908-2 V13.1.1`.
  [observed, 2026-11-13] Its meaning is not established. Treat it as unknown.
- `new_versions` was `""` on every row seen, superseded ones included.
  [observed, 2026-11-13] Its meaning is not established.

## Where this project departs from the subject

- `_ETSIFetcher` sends `content=0`, so a keyword search matches titles and
  numbers only, never document text. `get()` keeps only a row whose identifier equals the one
  asked for (#624, see *Parameters*).
- `_ETSIFetcher` reads an empty array as "no such standard". It cannot tell
  that from a malformed request (see *Paging and empty answers*), so its
  parameters are fixed in code rather than built from caller input, apart
  from `search`.

## Not covered

- ETSI's terms for automated access to `data.php` and `/deliver/`. Only
  `robots.txt` was read.
- Whether the request filter treats the deployed container's address or a
  sustained request rate differently. Only single requests from one
  workstation were made.
- The meaning of `IsCurrent`, `new_versions` and `ReviewDate`, and the
  `STATUS_CODE` values other than 12, 13 and 50.
- Whether `data.php` ever returns the `{"error": ...}` object that
  `superseded.php` returns.

# Patent citations

`generate_citations` formats patents as well as papers (#50). How each format
represents a patent, and which kind codes are applications, is recorded in
[Patent entries in biblatex, CSL-JSON and RIS](reference/patent-citation-formats.md).
This page records what the tool does on top of that.

## Input

Patent numbers go in the same `paper_ids` list as paper identifiers. A value
`is_patent_number` accepts is resolved through EPO biblio with the same
per-identifier handling `batch_resolve` uses (`_tools_utility._resolve_patent`).
Everything else goes to Semantic Scholar, which is not called when the list
holds only patents. A 40-character hex string is a Semantic Scholar paper id, never a patent
number: `is_patent_number` refuses it whatever its case, though `ca1…` or
`de0…` would otherwise read as an office code and a digit (#699), so it stays
with Semantic Scholar in every tool. Records come out in input
order, and unresolved
identifiers are listed in input order as comments, with the reason
(`not found` for a paper; for a patent, the code `_resolve_patent` returns:
`not_found`, `epo_not_configured`, `rate_limited`, `epo_unavailable`,
`invalid_patent_number`, `resolve_failed`). A failed patent never fails the
call. A call where nothing resolves returns `no_papers_resolved` with
`failed` as before, plus an `errors` list carrying each identifier's reason,
so a caller can tell an EPO throttle (retry later) from a bad number.

## Names

EPO supplies each party in an `original` and a standardised spelling. The
original keeps the `Last, First` comma; the standardised one is upper case
with no comma and, in epodoc form, a `[CC]` tag. The formatters therefore use
the original names and fall back to the standardised ones with the tag
removed. A name is split at its first comma; every later part is a given
name, so `VAN LIESDONK, Peter, Petrus` becomes family `VAN LIESDONK`, given
`Peter Petrus`. A name with no comma is not split: BibTeX braces it whole,
CSL writes it as `literal`, RIS writes it as is. Upper-case family names are
left as EPO wrote them; recasing them would break names like `McDONALD`.

## Formats

- BibTeX is a biblatex `@patent`: inventors in `author`, applicants in
  `holder` (each braced as a corporate name), `number` as the full
  publication number with spaces (`EP 3491801 B1`), `date` as the
  publication date. The office stays in `number` because IEEE and other
  styles print `number` with no `authority` or `type`. With no inventors, the
  applicants become the authors, braced as corporate names like `holder`,
  since biblatex requires `author`; there is then no `holder`.
- The `type` field is a biblatex key built from an explicit table, because
  the key suffixes are not ISO codes (`patenteu`). The table holds DE, EP
  and US only: biblatex also has `fr` and `uk` keys, but no FR or GB kind
  code is sourced, so they could never be chosen. EP A3 (a separately
  published search report) counts as an application publication. A known
  application gets a `patreq` key, a known grant a `patent` key. WO has no
  key of its own, so it gets `patreq` with `location = {WO}`. When the
  status is unknown (an office or kind code the reference does not source),
  there is no `type` and `location` names the office: a wrong "patent" on an
  application is worse than no type.
- CSL-JSON is type `patent` with inventors in `author`, the office code in
  `authority`, `number` (the same spaced form), `issued` (publication date) and `submitted` (filing
  date), the way Zotero maps a patent. A known application also gets
  `genre: "patent application"`, which APA and Chicago print in place of
  "Patent". The applicants are left out: CSL has no assignee variable, and
  putting them in `publisher` would print them as a publisher.
- RIS is type `PAT` with Zotero's tags: `AU` inventors, `PB` applicants,
  `SN` the full publication number, `PY` and `DA` the publication date. The
  filing date is left out because Zotero's `C1` use for it is outside the
  RIS specification.
- Citation keys are the publication number in lower case (`ep3491801b1`),
  with `_2`, `_3` and so on when the same number repeats. Papers and patents
  share one key namespace.
- The priority date is in none of the formats; none has a slot for it.

## Code

`src/scholar_mcp/_patent_citation.py` holds the patent entries;
`_citation_formatter.py` dispatches each record to it or to the paper entry
by whether the record carries `publication_number`. BibTeX escaping lives in
`_bibtex_escape.py` so both modules can use it.

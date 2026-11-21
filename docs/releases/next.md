# Next release

<!-- notes-range-end: 3775fd9dd22f6f6c2f34844f86de16de3c364b3b -->

<!-- RELEASE-SUMMARY NEXT START -->
Standards now say when they have been replaced. A withdrawn or replaced RFC,
W3C specification, ETSI deliverable, NIST publication or ISO, IEC or IEEE
edition reports `superseded` or `withdrawn`, and `superseded_by` names what
replaced it. ETSI lookups work again, `search_standards` ranks the current
edition first, NIST identifiers keep their full document number, and the CEN
harmonised-standards table matches the Official Journal. An optional
OpenAlex API key raises OpenAlex's limits. Run `sync-standards` after
upgrading. See Upgrading.
<!-- RELEASE-SUMMARY NEXT END -->

## Upgrading

If you sync ISO, IEC, IEEE or CEN, run `scholar-mcp sync-standards` after
upgrading. The sync now reads the Relaton repositories' `v2` branch, because
their `main` branch stopped receiving data
([#641](https://github.com/pvliesdonk/scholar-mcp/issues/641)). The first run
rewrites every ISO, IEC and IEEE record even if upstream has not changed, and
deletes synced identifiers that `v2` no longer lists. For CEN it deletes the
table entries that were never harmonised standards and adds the ones the
table lacked
([#678](https://github.com/pvliesdonk/scholar-mcp/pull/678)). Until that run,
lookups and searches answer from the records the previous release synced.

If you use NIST standards, the first NIST lookup after upgrading downloads the
catalogue again, and every catalogue download now also reads the CSRC
publications export from `csrc.nist.gov`. When CSRC cannot be reached, the
lookup reports an upstream error instead of answering without withdrawal data,
caches nothing, and tries again on the next call
([#654](https://github.com/pvliesdonk/scholar-mcp/pull/654)).

**Clients:** nothing beyond reconnecting. A standard's `superseded_by` is now
always a list of identifiers, where 3.2 sent a string or null. NIST SP
identifiers spell out a part, volume, version or edition
(`NIST SP 800-57 Part 1 Rev. 5`, `NIST SP 800-160 Vol. 2`), and
`search_standards` returns results in a new order.

**State:** the cache is kept. On first open the server drops standards rows it
fetched live from IETF, W3C, ETSI, NIST and the Relaton bodies, the cached
standards searches and the cached NIST SP aliases, so each is fetched again on
its next use. Synced records stay until the next `sync-standards` run replaces
them.

**Security posture:** no change to what the server exposes or accepts. It now
also reaches `csrc.nist.gov` for NIST data. An OpenAlex API key, when set, is
sent to OpenAlex only.

## Replaced and withdrawn standards

In 3.2, a standard that a later edition or document had replaced came back as
current. The tracking issue for this release put it plainly: "A caller
checking whether a cited standard is still current gets 'yes' for both"
([#592](https://github.com/pvliesdonk/scholar-mcp/issues/592)), meaning
`ISO/IEC 27001:2005` and `RFC 2616`. Every source now reads replacement and
withdrawal from where that source records it, and `get_standard` reports it
in `status` and `superseded_by`:

- **IETF.** An obsoleted RFC is `superseded` and lists the RFCs that obsolete
  it: `RFC 2616` gives `RFC 7230` to `RFC 7235`
  ([#642](https://github.com/pvliesdonk/scholar-mcp/pull/642)). A Historic RFC
  is `withdrawn`, and `published_date` is filled
  ([#634](https://github.com/pvliesdonk/scholar-mcp/pull/634)). RFCs numbered
  below 1000, such as RFC 791 and RFC 793, are found again
  ([#635](https://github.com/pvliesdonk/scholar-mcp/pull/635)).
- **W3C.** A retired specification is `superseded`, and one the W3C API says
  another replaced lists it: `web-forms-2` gives `HTML5`
  ([#632](https://github.com/pvliesdonk/scholar-mcp/pull/632),
  [#648](https://github.com/pvliesdonk/scholar-mcp/pull/648)).
- **ETSI.** Every ETSI lookup failed in 3.2, because ETSI had retired the
  route the server queried
  ([#624](https://github.com/pvliesdonk/scholar-mcp/issues/624)). Lookups now
  use the ETSI search data endpoint and match identifiers exactly
  ([#628](https://github.com/pvliesdonk/scholar-mcp/pull/628)). `get_standard`
  also finds withdrawn, historical and replaced deliverables: `ETSI EN 300
  328-1` gives `ETSI EN 300 328`
  ([#650](https://github.com/pvliesdonk/scholar-mcp/pull/650)).
- **NIST.** The status comes from the CSRC publications export:
  `NIST SP 800-53 Rev. 4` is superseded by `NIST SP 800-53 Rev. 5`, and
  `FIPS 186-4` by `FIPS 186-5`
  ([#654](https://github.com/pvliesdonk/scholar-mcp/pull/654)).
- **ISO, IEC and IEEE.** Synced records carry the stage the Relaton `v2` data
  gives, so an ISO edition is no longer always `published`, and a withdrawn
  edition that names its replacement lists it: `ISO/IEC 27001:2005` gives
  `ISO/IEC 27001:2013`
  ([#647](https://github.com/pvliesdonk/scholar-mcp/pull/647)). A revised or
  replaced IEC edition lists the editions that followed it, as
  `IEC 60335-2-91:2008` lists `IEC 62841-4-4:2020`
  ([#659](https://github.com/pvliesdonk/scholar-mcp/pull/659)).

Each name in `superseded_by` is an identifier `get_standard` accepts. An
identifier that is the key of a synced record, such as `IEEE Std 1588-2008`,
is now answered from that record before the resolver rewrites it
([#652](https://github.com/pvliesdonk/scholar-mcp/pull/652)).

Some sources still say less than others. A retired W3C specification with no
named successor, such as `html401`, has an empty list, and so does an IEC
edition the dump links to no successor. The
[standards guide](../use/standards.md) lists what each source fills.

## NIST identifiers and coverage

NIST identifiers name the publication you asked for. `NIST SP 800-63-3` used
to resolve to `NIST SP 800-63`, a different publication, and parts, volumes
and versions were dropped
([#598](https://github.com/pvliesdonk/scholar-mcp/issues/598)). The resolver
now keeps the whole document number, reads the DOI forms NIST uses
(`NIST.SP.800-53r5`) and `NIST IR 8259`, and the catalogue spells a part or
volume out the way CSRC and NIST citations do
([#670](https://github.com/pvliesdonk/scholar-mcp/pull/670)).

Publications missing from the NIST catalogue now have records too. CSRC lists
publications such as `FIPS 186-3` and the 2005 `NIST SP 800-53` that the
catalogue has no entry for, so `get_standard` used to report them not found.
Each now gets a record built from the CSRC export, with its title, date, status
and link but no abstract. FIPS 203, 204 and 205, which the catalogue holds
under a series title the server did not recognise, are found as well
([#673](https://github.com/pvliesdonk/scholar-mcp/pull/673)). The CSRC white
papers have no records yet
([#672](https://github.com/pvliesdonk/scholar-mcp/issues/672)).

## Search ranks the current edition first

`search_standards` used to return matches in storage order, so a query that
named a standard without its year could miss the current edition: `27001`
against ISO returned the 2005 edition and two corrigenda, with
`ISO/IEC 27001:2022` not among the first three
([#487](https://github.com/pvliesdonk/scholar-mcp/issues/487)). Results are
now ranked
([#661](https://github.com/pvliesdonk/scholar-mcp/pull/661),
[#676](https://github.com/pvliesdonk/scholar-mcp/pull/676)):

1. An identifier equal to the query comes first.
2. The standard's own editions come before other documents whose number
   contains the query (ISO 29001 for `9001`, a handbook such as
   `ISO/IEC 27001-HBK`), and those before documents that match only in their
   title.
3. Published editions come before drafts, then superseded, then withdrawn.
4. An edition comes before its amendments, and the newest edition first.

`resolve_standard_identifier` lists its candidates in the same order. NIST
and ETSI rank every match before `limit` applies, and the synced bodies rank
their 500 strongest candidates. IETF and W3C rank only the matches their
source returns, so a larger `limit` can bring up an edition they list further
down.

## The CEN harmonised-standards table

The table of EU harmonised standards that `sync-standards --body CEN` loads
was checked entry by entry against the decisions the Commission publishes in the Official Journal
([#678](https://github.com/pvliesdonk/scholar-mcp/pull/678)). It now names
each standard in the edition and amendment the Official Journal cites, files the EN 71 toy standards
under the Toy Safety Directive, and holds no Cyber Resilience Act entries,
because none are cited yet. A withdrawn entry carries the date its presumption
of conformity ended and the standard that replaced it. The Machinery
Directive's list ends on January 20, 2027, when the Machinery Regulation
replaces it.

## An OpenAlex API key

OpenAlex now offers API keys, and the server had no way to use one
([#619](https://github.com/pvliesdonk/scholar-mcp/issues/619)). Set
`SCHOLAR_MCP_OPENALEX_API_KEY` to send a key, as a bearer token, to OpenAlex
only. Without a key OpenAlex allows 10 requests a second and a small daily
budget, and a free key raises both
([#620](https://github.com/pvliesdonk/scholar-mcp/pull/620)). Create the key
at openalex.org and activate it from the email OpenAlex sends, because it
refuses every request made with a key that is not yet active. The
[enrichment guide](../use/enrichment.md) has the steps.

An OpenAlex refusal no longer reads as "this DOI is not in OpenAlex."
`enrich_paper` and `batch_resolve` report a throttle as `rate_limited`, which
is worth retrying, and a rejected key as `openalex_unavailable`.

## Background jobs at the cap

When a caller already holds the maximum number of background jobs, a Semantic
Scholar tool that would become one now answers with an error telling the
caller to retry later, rather than the generic fault message
([#618](https://github.com/pvliesdonk/scholar-mcp/pull/618)). The cap is
unchanged: `SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT`, 256 by default, counts every
job until its record expires
([background jobs](../use/background-jobs.md)).

## Hostile input

Several patterns that read text from callers and upstream sources took
quadratic or worse time on long malformed input. A page range of 2,000 dashes
from Semantic Scholar or CrossRef took 9 s to parse. They now run in linear
time and match the same strings as before
([#682](https://github.com/pvliesdonk/scholar-mcp/pull/682)).

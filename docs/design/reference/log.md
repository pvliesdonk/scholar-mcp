# Research log

Newest first. One entry per research pass.

## 2026-11-21

### Semantic Scholar: a batch of unknown ids

Updated [Semantic Scholar API behaviour](semantic-scholar-api.md) for #729:
an all-unknown batch answers 400 where a mixed one gets `null` entries.

### Semantic Scholar: title match

Updated [Semantic Scholar API behaviour](semantic-scholar-api.md) for #59:
what `/paper/search/match` documents and returns, the 404 on no match, the
unbounded `matchScore`, and a same-title false match observed unkeyed.

### ISBNs in free-text citations

New page [ISBNs in free-text citations](isbn-in-citation-text.md) for #70:
the ISBN-13 check digit from the 2012 Users' Manual (the ISBN-10 rule is
marked unverified), how often OPS citations carry an ISBN, the forms they
take in eight DE publications, and Open Library's hit rate on five of them.

### EPO OPS full-text claims and description

New page [EPO OPS full-text claims and description](epo-ops-fulltext.md) for
#701: observed against the deployed service, the fulltext namespace, the
upper-case `lang`, how EP and WO split claims across `claim-text`, the
heading-as-paragraph description, and the 404 for publications without full
text. The four responses are vendored as fixtures.

### Patent entries in biblatex, CSL-JSON and RIS

New page [Patent entries in biblatex, CSL-JSON and RIS](patent-citation-formats.md)
for #50: the biblatex `@patent` fields and its twelve patent keys, what
pandoc and classic BibTeX do with the entry, the CSL variables patent styles
read and Zotero's patent maps, and the application and grant kind codes of
EP, US, WO and DE. The original RIS tag table was not retrieved.

## 2026-11-20

### Relaton v2: C1 control characters in the ISO dump

Updated [Relaton data dumps on the v2 branch](relaton-data-v2.md) for #675.
New observation: which C1 characters 22 ISO files at 9b9469f hold, what
they stand for, and that each file then parses.

### Replaced-edition data: NIST records from CSRC's export

Updated [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
for #653 and #671. New observations: which export fields make a record, how
many publications only CSRC lists, the 9 that share a DOI with a MODS record
spelled another way, and the FIPS series title the parser missed.

### Replaced-edition data: NIST part and volume spellings

Updated [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
for #598. New observation: the ways MODS writes an SP part, volume, version
or edition into `partNumber`. The departures section now gives the match and
resolution counts with the catalogue spelling those out.

## 2026-11-15

### Relaton v2: how IEC links a replaced edition to its successor

Updated [Relaton data dumps on the v2 branch](relaton-data-v2.md) for #644.
IEC publications carry no relations, but name their project; the project's
`updatedBy`, `obsoletedBy` and `mergedInto` lead to the next projects and
their publications. New observations: what `hasSuccessor` points at, how many
replaced editions the chain reaches, a 30-edition check against IEC's
webstore, and why withdrawn editions are left out.

### Replaced-edition data: NIST reads CSRC's export

Updated [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
for #639. New observations: the export's URL and size, how its per-update
entries group into 553 publications and which entry is current, and how many
of its identifiers match the MODS catalogue (179 of 231 withdrawn or replaced;
7 spelled differently, 45 absent).

### ETSI: withdrawn, historical and replaced deliverables

Updated [ETSI standards search data endpoint](etsi-standards-search.md) for
#640. The fetcher's search flags left withdrawn, historical and replaced
editions out, so `get()` answered `None` for such deliverables. Seven more
`superseded.php` samples: replacement is mostly within a deliverable; EN 300
328-1 and -2 were replaced by EN 300 328. ETSI's row order is not by date.

### Replaced-edition data: W3C reads `superseded-by`

Updated [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
for #638. New observations: the `superseded-by` link is a paged collection
holding at most six replacements; the `/specifications` list omits all 41
replaced specifications, which only their own names reach. The W3C fetcher
claims now describe it following the link, and pin its tests.

### Relaton data dumps: the v2 branch

New page [Relaton data dumps on the v2 branch](relaton-data-v2.md) (#641),
from the full `v2` tarballs of relaton-data-iso, -iec and -ieee and their
`main` tarballs. All three repositories moved to `v2`; `main` stopped
receiving data (ISO's last data commit is 2025-06-02). `v2` renames the fields
the parser read (`docidentifier.content`, `status.stage.content`, `source`,
`date.at`, `obsoletedBy`), puts IEC work items under `data/projects/`, and names
every file the same lowercase-hyphen way. Added a `v2` note to
[Relaton bibitem titles](relaton-titles.md).

### Replaced-edition data: IETF reads `obs` relations

Updated [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
for #637. New observations: datatracker's `relateddocument` endpoint batches
with `target__name__in`, caps a page at 1000 rows, and rejects a filter on the
source name; no `obs` source seen was a draft. The IETF claims now describe the
fetcher reading those relations, and pin its tests.

## 2026-11-14

### Replaced-edition data, after the fetcher fixes

Updated [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
after #632, #634 and #635: the claims about the W3C status, URL and
identifier, the IETF status and publication date, and datatracker's unpadded
names now describe `main` and pin tests. Re-run live on e42339b: HTML 4.01
reports `superseded`, RFC 2246 `withdrawn`, and RFC 2616 still `published`
with no replacement (#592). Corrected the RFCs that obsolete RFC 2616 to
7230 to 7235.

### Replaced-edition data for IETF, NIST and W3C

New page [Replaced-edition data for IETF, NIST and W3C](standards-supersession-sources.md)
(#120), from depth-1 clones of relaton-data-nist and relaton-data-w3c,
samples of relaton-data-ietf, the NIST-Tech-Pubs MODS release, CSRC's
publications export, datatracker and the W3C API. Finding: the IETF dump and
datatracker both carry obsoleting RFCs; for NIST only the CSRC export marks
withdrawals and replacements; for W3C only the live API links a replaced
specification to its successor. Not settled: the dumps' licence terms.

### ETSI standards search endpoint, after the fix

Updated [ETSI standards search data endpoint](etsi-standards-search.md) for
#624, which moved `_ETSIFetcher` to `data.php` with `content=0` and
`includeScope=1`. New observation: with `content=0` a search for
`ETSI EN 303 645` still returns `ETSI TS 103 929` as its second row, so an
exact lookup has to match the identifier. The row-field and request claims now
pin tests.

## 2026-11-13

### ETSI standards search endpoint

New page [ETSI standards search data endpoint](etsi-standards-search.md)
(#454), from the search page's own `script.js`, relaton-etsi's fetcher, and
requests to the live endpoint. Finding: the data moved to
`custom/standardssearch/data.php`, with the same row shape `_normalize_etsi`
reads. A web application firewall refuses curl's default user agent, which is
separate from the dead Joomla route. Not settled: ETSI's terms for automated
access, and the meaning of `IsCurrent` and `new_versions`.

## 2026-11-12

### OpenAlex keys and limits

New page [OpenAlex API keys and limits](openalex-auth.md) (#619), from the
OpenAlex help pages on authentication, pricing, example costs and errors (all
last updated 2026-11-03). Not settled: the response to an invalid key, and
whether `mailto` still has any effect.

## 2026-11-06

### OPS party name formats

Added "Parties in several name formats" to
[EPO OPS bibliographic responses](epo-ops-biblio.md) (#483), from the OPS
v3.2 schema pages for `applicant` and `inventor` (a third-party mirror,
read verbatim) and the doubled names observed in #483. Not settled: which
formats each office sends, and whether `original` can be non-Latin.

### OPS search range limits

New page [EPO OPS published-data search range](epo-ops-search.md) (#488). The
vendored OpenAPI description gives only the default range. The 100-per-request
and 2,000-total limits come from EPO's OPS FAQ, checked verbatim against the
live page. Not settled: what OPS answers for a range past either limit.

## 2026-11-05

### OPS 404 for a nonexistent publication

Added "A publication that does not exist" to
[EPO OPS bibliographic responses](epo-ops-biblio.md) (#475), from the 404s
observed against the deployed server. No new research: the observation is
the issue's own. Not settled: whether the other published-data endpoints
answer 404 the same way.

## 2026-11-03

### CrossRef `issued` for the OpenURL date

Added `issued` to [CrossRef work journal fields](crossref-works.md) (#561).
Re-read the Crossref swagger `Work` and `DateParts` definitions. Observed that
for one republished article, CrossRef and Semantic Scholar disagree on the year.
Not settled: how CrossRef chooses `issued` when print and online dates differ.

## 2026-11-02

### Journal details for OpenURL links

New page [CrossRef work journal fields](crossref-works.md), and a "Journal
details" section on [Semantic Scholar API behaviour](semantic-scholar-api.md),
for the OpenURL journal keys (#541). Read the Crossref and S2 swagger
definitions; sampled one CrossRef work and one unkeyed S2 batch of five
papers. Found S2 returns `publicationVenue.issn` although the description
omits it, and can merge volume and issue. Not settled: how common either S2
shape is, and the other `issn-type` values. Next review: 2027-05-02.

### OpenURL 0.1 and 1.0

New page [OpenURL 0.1 and 1.0 query strings](openurl.md) for the access-link
placeholders (#539). Read the 0.1 syntax description, Z39.88-2004 (R2010), the
frozen OpenURL registry matrices, the KEV implementation guidelines, NISO
RP-21-2013 and OCLC's resolver documentation; observed an OCLC Link Resolver
with a 1.0 and a 0.1 link for the same citation. Not settled: arXiv
identifiers, and resolver handling of hybrid links. Next review: 2027-11-02.

## 2026-10-31

### Template-authored page

[Pull request size and review effectiveness](pull-request-size.md) arrived
with the fastmcp-server-template v11.5.1 update, researched upstream (passes
of 2026-10-17 and 2026-10-21) and carried here unchanged. Next review:
2027-04-17.

## 2026-09-29

### Template-authored pages

Five pages arrived with the fastmcp-server-template v11.0.2 update (#508),
researched upstream and carried here unchanged:
[GitHub and git behaviour behind integration branches](github-integration-branches.md),
[GitHub repository security settings](github-repository-security-settings.md),
[MCP model-facing text](mcp-model-facing-text.md),
[MCP tool outcomes and errors](mcp-tool-outcomes-and-errors.md) and
[Negative outcomes and faults outside MCP](negative-outcomes-and-faults.md).
Their research history is in the template's own log; each page's frontmatter
carries its review date.

## 2026-09-28

### Semantic Scholar author pages

Updated [Semantic Scholar API behaviour](semantic-scholar-api.md) for #490.
Three unkeyed requests to `/author/1695689` with different `limit` and
`offset` values returned the same 461 papers in the same order, confirming
the endpoint ignores both; the spec documents neither. The same response
reported `paperCount` 472, so the embedded list is not always complete.

### DOIs in citation text

Added [DOIs in free-text citations](doi-in-citation-text.md) for #482, where
no NPL reference on DE102025108780A1 was resolved because the extractor
required `doi:`. Sourced Crossref's recommended DOI pattern and the two EPO
forms recorded in the issue (`https://doi.org/…`, `DOI 10.…`). The DOI
Handbook's syntax pages render only through JavaScript and were not read;
early non-Crossref-shaped DOIs, percent-encoded DOIs and DOIs broken across
lines remain unverified.

### OpenAlex work objects

Added [OpenAlex work objects](openalex-works.md) for #478, where
`batch_resolve`'s DOI fallback returned the raw 15 KB work. Read the
work-object docs at openalex-docs 8cec9db and one live record
(10.1038/nature14539). The docs type `ids.mag` as an integer; the record
served a string. `referenced_works_count` is served but undocumented. The live
record's `oa_url` was a landing page with no `pdf_url`, which is why the
mapped `openAccessPdf` reads `pdf_url` only.

### Relaton titles

Added [Relaton bibitem titles](relaton-titles.md) for #480, where synced ISO
records carried only their `title-intro`. Read the relaton-iso README, which
shows `main` as the composed title beside its typed parts, and ten records
across relaton-data-iso, -iec and -ieee, pinned to the commits read. IEC
amendments have the same shape and were affected too; the IEEE records carry
`main` only. `language` is a list, a string or null depending on the
repository. Whether every record has a `main`, and whether English always
comes first (which the abstract lookup also relies on), remain unverified.

## 2026-09-25

### PDF download header

Added [PDF file header behaviour](pdf-file-header.md) as a stable reference for
#484. Checked PDF 32000-1:2008 section 7.5.2 and RFC 9110 section 8.3. The PDF
header starts with `%PDF-`; `Content-Type` describes the response media type
but does not verify the body. The implementation and tests use the header as
a download/cache check and do not claim full PDF structural validation.

### Semantic Scholar `limit` maxima

Added the per-endpoint `limit` maxima to
[Semantic Scholar API behaviour](semantic-scholar-api.md) for #476, where
`search_papers(limit=500)` came back as an opaque upstream error. Read from the
Graph and Recommendations swagger specifications: 100 for paper search, 1,000
for the citation, reference, author-search and author-papers lists, 500 for
recommendations, and no `limit` at all on `/author/{id}`. An unkeyed probe
returned 200 for `limit=100`; every over-maximum and `limit=0` attempt was
throttled with 429, so the status S2 gives an out-of-range `limit` remains
unverified.

## 2026-09-21

### Semantic Scholar and Google Books

Added [Semantic Scholar API behaviour](semantic-scholar-api.md) and
[Google Books volume search](google-books-api.md) as draft references for #389.
Checked the published API pages for the keyed S2 rate (one request per second
across endpoints), shared unauthenticated traffic, citation endpoint parameters,
Google Books ISBN search, and its volume-list response. A single anonymous
Google Books request today returned 429 with a daily `Queries` quota message;
it established neither the quota number nor the keyed error shape.

The older maintainer observations in #389, #406 and #366 are recorded with
their links and marked `[unverified]`: the issue comments preserve conclusions
but not enough raw request and response evidence to independently confirm them.
This pass made no live Semantic Scholar requests. Citation ordering, keyed
Google Books quota behavior, and whether a 429 counts as S2 key activity remain
open. Review both pages by 2027-03-21.

## 2026-09-16

### Biblio element placement, and what `L500EP` actually holds

Subject: where OPS puts `abstract` in a biblio response, and what the `L500EP`
element contains. Prompted by #399 (every patent record came back with
`"abstract": ""`) and #405 (37 `PG25` events indistinguishable apart from their
dates).

Added [EPO OPS bibliographic responses](epo-ops-biblio.md) as `status: draft`.
`abstract` is a *sibling* of `bibliographic-data`, not a child of it, so the
direct-children helper the parser used never saw it. The page is draft rather
than stable because no fixture could be vendored: the fixing session had no EPO
credentials reachable, so its evidence is the raw response quoted verbatim in
#399 rather than a capture under `tests/fixtures/epo/`. Promote it to stable
when the document can be re-captured.

Corrected a falsified claim on [legal-status events](epo-ops-legal-events.md).
The 2026-09-10 pass recorded that `L500EP` "appeared empty in every observed
event. [unverified]". It is not empty — it is a container whose child varies by
event. The fixture that pass already vendored carries `L501EP` "Ref Country
Code" on 28 of its 50 events across 19 states, and an `L525EP` "Effective DATE"
on the `17Q` event. The claim is now `[observed:]` and pinned to tests.

That makes two claims from the 2026-09-10 pass that its own vendored fixture
refutes. Both were the `[unverified]` ones, and both were falsifiable in seconds
against bytes already in the repository — an argument for spending the refute
pass on the evidence already in hand before reaching for a new source.

Next review: 2027-09-10 (unchanged).

## 2026-09-12

### GitHub planning objects

Added [GitHub planning objects](github-planning-objects.md), checked against
GitHub.com documentation and GitHub CLI 2.97.0. Covered milestone identity,
pagination, pull request membership, nullable updates, issue hierarchy and
dependencies, and documented attachment support. The refute pass retained the
cross-owner REST documentation conflict and marked unreproduced UI and search
observations explicitly. Next review: 2027-03-12.

## 2026-09-10

### Legal-status events

Subject: EPO OPS legal-status events, prompted by #388 — a decision about
whether to reproduce an EPO manual marked `DISTRIBUTION: Exchange Partners`.

**The decision dissolved on inspection.** A live `get_legal` call showed the
response is self-describing at both levels: the event's meaning is a
plain-language `desc` on `ops:legal`, and every `L###EP` child names the field
it holds. The `L###EP` tags are field labels *within* an event, not opaque event
codes needing a lookup table — which was the premise #388 rested on. The manual
documents the T12 weekly exchange file, a different product this project does
not consume, so it was never the right source.

Resolution, per the maintainer: no protected document and no transcription of
one. The index points at the public OPS page as where artefacts are obtained.

**Found while probing:** `parse_legal_xml` searches for a `legal-event` element
that exists in neither the schema nor any response, and returns zero events from
a verbatim 76 KB response containing fifty. Its tests pass because their fixtures
encode the same invented shape — the third instance of the pattern behind #371.
Filed as #390 and written up here *before* fixing, so the fix follows the
recorded behaviour rather than another assumption.

The response is checked in at `tests/fixtures/epo/legal_ep1000000a1.xml` as the
evidence for this page's observations, and as what #390 will test against.

### Images, throttling and quota

First pass. Subject: EPO Open Patent Services 3.2, prompted by four patent bugs
that each turned on undocumented-to-us behaviour — #371, #379, #384, and the
throttle-bucket question inside #381.

**Framed from the code**, not from memory: every assumption in
`_epo_client.py`'s image path and throttle handling, plus the open questions
already recorded on those issues.

**Primary sources swept:** the OPS response schema (`ops.xsd`), the OPS 3.2
OpenAPI description (`ops.yaml`), and the RESTful Web Services Reference Guide
v1.3.20. The reference client `python-epo-ops-client` was consulted while the
guide was still out of reach; its URL-prefix classifier agrees with the guide's
Table 16, but it is a secondary source and no claim here cites it.

**Observed where documentation was silent:** live inquiry and retrieval calls
for `EP3491801B1`, `EP1000000A1`, `WO2019016210A1` and `US9634864B2`; four URL
forms probed for a whole-document route; a full 21-page fetch measured and
merged. Two verbatim responses are checked in under `tests/fixtures/epo/`.

**Refuted:** the reading that §3.1.3's "images is the new name for document
(inquiry or retrieval) service" puts the inquiry in the `images` bucket. Table
16 contradicts it; the sentence names a documentation section. Recorded in the
throttling page as a trap rather than dropped, because the wrong reading is the
natural one.

**Completeness gaps** are written as `[unverified]` claims on both pages rather
than left implicit: whether OPS ever omits a required `number-of-pages`, what
`FirstPageImage` and `JapaneseAbstract` instances contain, which
`X-Rejection-Reason` values exist, and whether quota headers arrive early enough
to warn an operator.

**Found while writing:** fair-use quota exhaustion is a `403` with
`X-Rejection-Reason`, a mechanism this codebase does not recognise at all.
Filed as #384. No probe would have surfaced it without exhausting a shared
allowance.

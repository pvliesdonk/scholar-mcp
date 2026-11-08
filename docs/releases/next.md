# Next release

<!-- notes-range-end: a7b0b5e04075b2ee2c67c5ad916c9980e6be6f10 -->

<!-- RELEASE-SUMMARY NEXT START -->
The PDF download tools now refuse hosts on the server's own network, for URLs a
caller passes and URLs found in paper metadata alike, and a paper whose
Semantic Scholar link fails now falls back to arXiv, PubMed Central and
Unpaywall. Patent applicants and inventors are listed once per name format, and
`recommend_books` and `get_book_excerpt` return plain mappings. Three tool
payloads change shape and one setting is new; the upgrade steps are below.
<!-- RELEASE-SUMMARY NEXT END -->

## Upgrading

If your server downloads PDFs from a host on its own network, such as an
intranet repository, set `SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE=true`. The same
applies when the server reaches the internet only through an HTTP proxy and
cannot resolve host names itself: the new check resolves every host before the
request and refuses one it cannot resolve, so without the setting every download
fails with `download_failed`. See [PDF downloads](#pdf-downloads).

**Clients:** reconnect to pick up the changed tool surface. A client that parses
these payloads needs a change:

- `get_patent`, `batch_resolve` (its `patent` record) and `get_citing_patents`:
  `applicants` and `inventors` are objects with `original` and `standardised`
  lists, where they were flat lists of names (see [Patents](#patents)).
- `recommend_books`: the result is `{"books": [...]}`, where it was a bare list.
- `get_book_excerpt`: the structured content is the mapping itself, where it
  was a JSON string under `result`. The text content is unchanged.

**State:** the cache, downloaded PDFs and converted Markdown are kept. Cached
patent records that still hold the old flat applicant and inventor lists are
dropped once at startup, so each such patent is fetched from EPO again on its
next request.

**Security posture:** tightened. `fetch_pdf_by_url`, `fetch_paper_pdf` and
`fetch_and_convert` refuse a URL, or a redirect, whose host resolves to a
loopback, private, link-local or other non-public address.
`SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE=true` restores the previous behaviour.

## PDF downloads

### Refusing hosts on the server's own network

`fetch_pdf_by_url` downloads whatever URL its caller passes, and its caller is
a model acting on prompts the operator does not see. Until now it followed that
URL, and any redirect, to any address, so a caller could make the server request
hosts on its own network: loopback, RFC 1918 ranges and link-local addresses
such as cloud metadata endpoints
([#514](https://github.com/pvliesdonk/scholar-mcp/issues/514)). The paper
download tools had the same gap one step removed, since a candidate URL from
upstream metadata could redirect anywhere
([#573](https://github.com/pvliesdonk/scholar-mcp/issues/573)).

All three download tools now resolve each host first and download only when
every address it resolves to is a public internet address. A host with one
public and one private address is refused, because the connection may use
either. IPv6 addresses that carry an IPv4 address are judged by that IPv4
address. Redirects are followed one hop at a time, at most 10, and each hop is
checked before it is requested
([#574](https://github.com/pvliesdonk/scholar-mcp/pull/574),
[#589](https://github.com/pvliesdonk/scholar-mcp/pull/589)).

- On `fetch_pdf_by_url`, a refused URL is an error that names the URL, or the
  redirect target, and asks for a publicly reachable URL instead.
- On `fetch_paper_pdf` and `fetch_and_convert`, a refused candidate becomes a
  `download_failed` entry in `attempts`, whose `detail` names the refused URL,
  and the next source is tried.

`SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE` (default `false`) turns the check off on
all three tools ([configuration](../reference/configuration.md#pdf-conversion)).
The check runs just before each request, not at connect time, so a host whose
DNS answer changes between the two is not caught; pinning the address would
mean bypassing a configured HTTP proxy. The
[security model](../security-model.md) states this limit.

### Alternative sources when the Semantic Scholar link fails

`fetch_paper_pdf` and `fetch_and_convert` tried arXiv, PubMed Central and
Unpaywall only when Semantic Scholar listed no open-access URL. When it listed
one that served a landing page or an error, the call ended there: "The fallback
chain is gated on the absence of the S2 URL, not on its failure"
([#568](https://github.com/pvliesdonk/scholar-mcp/issues/568)).

Both tools now try the Semantic Scholar URL, then arXiv, PubMed Central and
Unpaywall, until one serves a PDF. Unpaywall is queried only after the earlier
sources failed, and still needs `SCHOLAR_MCP_CONTACT_EMAIL`. When every source
fails, the response keeps its `error`, `detail` and `pdf_source` for the last
source tried and adds `attempts`, one entry per source, so a caller can tell
"no source known" (`no_oa_pdf`) from "every known source failed"
([#570](https://github.com/pvliesdonk/scholar-mcp/pull/570)). See
[Alternative PDF sources](../use/pdf-conversion.md#alternative-pdf-sources).

## Patents

`get_patent` listed every applicant and inventor twice, once in each name
format the patent office supplied: "`WO2024235369A1` lists 12 inventors for six
people", so "A caller counting inventors, or matching a name against another
source, gets doubled or mismatched results"
([#483](https://github.com/pvliesdonk/scholar-mcp/issues/483)). `applicants` and
`inventors` are now objects with two lists, each naming every party once:
`original`, the names as the office supplied them, and `standardised`, one
standardised format. The two lists are not paired by position, because EPO does
not guarantee that entries with the same sequence number name the same party.
The shape appears wherever a patent record does: `get_patent`, `batch_resolve`
and `get_citing_patents`
([#579](https://github.com/pvliesdonk/scholar-mcp/pull/579); see the
[patent tool reference](../reference/tools/patents.md)).

`get_patent` for a number that does not exist raised a raw HTTP error naming the
EPO URL, so "there is no `error` key for a caller to branch on"
([#475](https://github.com/pvliesdonk/scholar-mcp/issues/475)). It now answers
`{"error": "patent_not_found"}`, the same answer it gave for an empty record
([#575](https://github.com/pvliesdonk/scholar-mcp/pull/575)).

`search_patents` documented `limit` as at most 100 but sent any value to EPO
([#488](https://github.com/pvliesdonk/scholar-mcp/issues/488)). It now caps
`limit` at 100, the most one EPO request returns, and its description says that
EPO serves only the first 2,000 results of a search
([#578](https://github.com/pvliesdonk/scholar-mcp/pull/578)).

## Smaller changes

`recommend_books` and `get_book_excerpt` returned "a JSON string wrapped in an
object rather than a mapping, so the caller receives double-encoded JSON"
([#370](https://github.com/pvliesdonk/scholar-mcp/issues/370)). Both now return
a mapping; `recommend_books` wraps its list as `{"books": [...]}`, like
`search_books` ([#583](https://github.com/pvliesdonk/scholar-mcp/pull/583); see
the [book tool reference](../reference/tools/books.md)).

`find_bridge_papers` returned a path paper that was not in the cache as a bare
`{"paperId": ...}`
([#485](https://github.com/pvliesdonk/scholar-mcp/issues/485)). It now fetches
the missing records in one batch request, so every path entry has the record
shape `get_paper` returns; a failed lookup marks the result `partial`
([#584](https://github.com/pvliesdonk/scholar-mcp/pull/584)).

When Semantic Scholar throttles a call, the job handle's reason now tells the
caller to keep polling, how long the result can take, that every client of the
server shares one Semantic Scholar budget, and that an unfinished job has no
answer yet rather than an empty one. The server instructions carry the shared
budget too. The motivating report found that "a \"searched, nothing found\" list
may contain searches that never finished"
([#569](https://github.com/pvliesdonk/scholar-mcp/issues/569),
[#571](https://github.com/pvliesdonk/scholar-mcp/pull/571); see
[background jobs](../use/background-jobs.md)).

`get_standard`'s description offered `nist 800-53` as an example, which returns
`not_found` because NIST publications are catalogued per revision. The example
is now `nist 800-53 rev 5`
([#481](https://github.com/pvliesdonk/scholar-mcp/issues/481),
[#586](https://github.com/pvliesdonk/scholar-mcp/pull/586)).

Concurrent book enrichment can no longer replace a cached author list with an
empty one: the write that keeps existing authors is now a single statement
([#451](https://github.com/pvliesdonk/scholar-mcp/issues/451),
[#587](https://github.com/pvliesdonk/scholar-mcp/pull/587)).

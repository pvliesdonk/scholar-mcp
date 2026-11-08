# 3.1

A paper the server cannot fetch now comes with links to it: its doi.org link by default, and the library routes an operator configures, such as a link resolver or a login redirector. `get_paper` offers the same links before any download. The Docker image moves to a new base with an init process, and `serve -v` logs at debug level again; the upgrade steps are described below.

## Upgrading

Two changes need a look if they apply to you; nothing else needs action.

**Clients:** reconnect to pick up the changed tool surface. `get_paper` records gain `access_links`, `journal` and `publicationVenue`, and a failed PDF fetch carries `access_links` and a `note` (see [MCP callers](#mcp-callers)).

**State:** the cache, downloaded PDFs and converted Markdown are kept. Paper records cached by 3.0 lack `journal` and `publicationVenue` until their 30-day entry expires; their links are built from the fields they have.

**Security posture:** the server builds access links but never requests them, so it reaches nothing new. An operator-configured link template is checked at startup and is the only new input.

### Docker image

The image now builds on `debian:trixie-slim` with Python 3.14 installed by uv, where 3.0 built on `python:3.14-slim`. It no longer has `/usr/local/bin/python` or `pip`, so a script that runs Python inside the container calls `/app/.venv/bin/python`. The change brings SQLite 3.51.3 or later, past the WAL-reset corruption bug in Debian's 3.46.1, and the Scholar MCP cache is a SQLite database. `tini` now runs as PID 1 and reaps detached child processes; Compose `init: true` and `docker run --init` keep working ([#528](https://github.com/pvliesdonk/scholar-mcp/pull/528), [template upgrade note v11.5](https://github.com/pvliesdonk/fastmcp-server-template/blob/v11.5.1/upgrading/v11.5.md), [template v11.5.1](https://github.com/pvliesdonk/fastmcp-server-template/releases/tag/v11.5.1)).

### MCP callers

`get_paper` records now carry `access_links`, a list of `{label, url}` routes to the paper. Unconfigured, it holds the paper's doi.org link; set `SCHOLAR_MCP_ACCESS_LINKS='[]'` to keep 3.0's payloads. The records also carry Semantic Scholar's `journal` and `publicationVenue` objects (see [Links to papers the server cannot fetch](#links-to-papers-the-server-cannot-fetch)).

## Links to papers the server cannot fetch

Many papers have no open-access copy, yet the user's library licenses them. The routes to such a copy (a library link resolver, an inter-library loan form, a login redirector, the publisher's page on a licensed network) run in the user's own browser session, so the server cannot use them, but it can build the links ([epic #538](https://github.com/pvliesdonk/scholar-mcp/issues/538)).

When `fetch_paper_pdf` or `fetch_and_convert` ends without a PDF (`no_oa_pdf`, `download_failed` or `not_pdf`), the response now carries `access_links`, a list of `{label, url}` routes, and a `note` telling the model to offer them to the user. `get_paper` carries the same links on every record it can fill them for, so the agent can offer them before any download ([#539](https://github.com/pvliesdonk/scholar-mcp/issues/539), [#543](https://github.com/pvliesdonk/scholar-mcp/pull/543), [#540](https://github.com/pvliesdonk/scholar-mcp/issues/540), [#545](https://github.com/pvliesdonk/scholar-mcp/pull/545)). Scholar MCP never opens these links; an agent browsing from the user's network can.

Unconfigured, the list holds one link, `Publisher (DOI)` to `https://doi.org/<DOI>`. On a network with IP-based licence access, that link often opens the full text at the publisher, and it names no institution ([#547](https://github.com/pvliesdonk/scholar-mcp/issues/547), [#549](https://github.com/pvliesdonk/scholar-mcp/pull/549)). An operator sets `SCHOLAR_MCP_ACCESS_LINKS` to a JSON list of `label` and `template` pairs to offer the library's own routes; the list replaces the default, and `[]` turns links off. A template is a URL with placeholders: `{doi}`, `{doi_url}` for wrapping in a redirector, and `{openurl}`, `{openurl_0_1}` or `{openurl_hybrid}` for an OpenURL link resolver. The server checks the list at startup and refuses to start on a malformed one. A template the paper cannot fill, such as `{doi}` without a DOI, is skipped.

The OpenURL forms carry the title, journal, year and authors, and, when the record has them, the journal's ISSN, volume, issue and pages, which lets a resolver find a paper with no DOI in the library's holdings ([#541](https://github.com/pvliesdonk/scholar-mcp/issues/541), [#552](https://github.com/pvliesdonk/scholar-mcp/pull/552)). The [PDF conversion guide](https://pvliesdonk.github.io/scholar-mcp/unstable/use/pdf-conversion/#access-links-for-licensed-papers) has a worked configuration and shows how to find a library's resolver address.

## Smaller changes

`scholar-mcp -v serve` logs at debug level again. In 3.0 the server set up logging a second time while starting, which reset the level to the environment's and dropped every debug line ([template#790](https://github.com/pvliesdonk/fastmcp-server-template/pull/790), [#528](https://github.com/pvliesdonk/scholar-mcp/pull/528)).

Each tool carries a `group:` tag, such as `group:papers`, naming its section of the [tool reference](https://pvliesdonk.github.io/scholar-mcp/unstable/reference/tools/index.md) ([#530](https://github.com/pvliesdonk/scholar-mcp/pull/530)). The documentation site is regrouped into Get started, Deploy, Use, Reference and Upgrade, and every old page address redirects to its new place ([#532](https://github.com/pvliesdonk/scholar-mcp/pull/532), [#533](https://github.com/pvliesdonk/scholar-mcp/pull/533)).

## v3.1.1

OpenURL access links now carry the year of the work the DOI names, so a library resolver gets a consistent citation. No upgrade steps are needed.

### OpenURL year

An OpenURL access link (`{openurl}`, `{openurl_0_1}` or `{openurl_hybrid}`) took its year from Semantic Scholar, which sometimes gives the year of an earlier version of the paper. For the 2017 Communications of the ACM reprint of a 2012 conference paper, the link said 2012 next to the 2017 volume and pages. A resolver that has to match a paper without a DOI by its metadata could then miss it. The link now takes the year from the paper's CrossRef record when it has one, and from Semantic Scholar otherwise ([#561](https://github.com/pvliesdonk/scholar-mcp/issues/561), [#562](https://github.com/pvliesdonk/scholar-mcp/pull/562)).

## v3.1.2

The PDF download tools now refuse hosts on the server's own network, for URLs a caller passes and URLs found in paper metadata alike, and a paper whose Semantic Scholar link fails now falls back to arXiv, PubMed Central and Unpaywall. Patent applicants and inventors are listed once per name format, and `recommend_books` and `get_book_excerpt` return plain mappings. Three tool payloads change shape and one setting is new; the upgrade steps are below.

### Upgrading

If your server downloads PDFs from a host on its own network, such as an intranet repository, set `SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE=true`. The same applies when the server reaches the internet only through an HTTP proxy and cannot resolve host names itself: the new check resolves every host before the request and refuses one it cannot resolve, so without the setting every download fails with `download_failed`. See [PDF downloads](#pdf-downloads).

**Clients:** reconnect to pick up the changed tool surface. A client that parses these payloads needs a change:

- `get_patent`, `batch_resolve` (its `patent` record) and `get_citing_patents`: `applicants` and `inventors` are objects with `original` and `standardised` lists, where they were flat lists of names (see [Patents](#patents)).
- `recommend_books`: the result is `{"books": [...]}`, where it was a bare list.
- `get_book_excerpt`: the structured content is the mapping itself, where it was a JSON string under `result`. The text content is unchanged.

**State:** the cache, downloaded PDFs and converted Markdown are kept. Cached patent records that still hold the old flat applicant and inventor lists are dropped once at startup, so each such patent is fetched from EPO again on its next request.

**Security posture:** tightened. `fetch_pdf_by_url`, `fetch_paper_pdf` and `fetch_and_convert` refuse a URL, or a redirect, whose host resolves to a loopback, private, link-local or other non-public address. `SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE=true` restores the previous behaviour.

### PDF downloads

#### Refusing hosts on the server's own network

`fetch_pdf_by_url` downloads whatever URL its caller passes, and its caller is a model acting on prompts the operator does not see. Until now it followed that URL, and any redirect, to any address, so a caller could make the server request hosts on its own network: loopback, RFC 1918 ranges and link-local addresses such as cloud metadata endpoints ([#514](https://github.com/pvliesdonk/scholar-mcp/issues/514)). The paper download tools had the same gap one step removed, since a candidate URL from upstream metadata could redirect anywhere ([#573](https://github.com/pvliesdonk/scholar-mcp/issues/573)).

All three download tools now resolve each host first and download only when every address it resolves to is a public internet address. A host with one public and one private address is refused, because the connection may use either. IPv6 addresses that carry an IPv4 address are judged by that IPv4 address. Redirects are followed one hop at a time, at most 10, and each hop is checked before it is requested ([#574](https://github.com/pvliesdonk/scholar-mcp/pull/574), [#589](https://github.com/pvliesdonk/scholar-mcp/pull/589)).

- On `fetch_pdf_by_url`, a refused URL is an error that names the URL, or the redirect target, and asks for a publicly reachable URL instead.
- On `fetch_paper_pdf` and `fetch_and_convert`, a refused candidate becomes a `download_failed` entry in `attempts`, whose `detail` names the refused URL, and the next source is tried.

`SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE` (default `false`) turns the check off on all three tools ([configuration](https://pvliesdonk.github.io/scholar-mcp/unstable/reference/configuration/#pdf-conversion)). The check runs just before each request, not at connect time, so a host whose DNS answer changes between the two is not caught; pinning the address would mean bypassing a configured HTTP proxy. The [security model](https://pvliesdonk.github.io/scholar-mcp/unstable/security-model/index.md) states this limit.

#### Alternative sources when the Semantic Scholar link fails

`fetch_paper_pdf` and `fetch_and_convert` tried arXiv, PubMed Central and Unpaywall only when Semantic Scholar listed no open-access URL. When it listed one that served a landing page or an error, the call ended there: "The fallback chain is gated on the absence of the S2 URL, not on its failure" ([#568](https://github.com/pvliesdonk/scholar-mcp/issues/568)).

Both tools now try the Semantic Scholar URL, then arXiv, PubMed Central and Unpaywall, until one serves a PDF. Unpaywall is queried only after the earlier sources failed, and still needs `SCHOLAR_MCP_CONTACT_EMAIL`. When every source fails, the response keeps its `error`, `detail` and `pdf_source` for the last source tried and adds `attempts`, one entry per source, so a caller can tell "no source known" (`no_oa_pdf`) from "every known source failed" ([#570](https://github.com/pvliesdonk/scholar-mcp/pull/570)). See [Alternative PDF sources](https://pvliesdonk.github.io/scholar-mcp/unstable/use/pdf-conversion/#alternative-pdf-sources).

### Patents

`get_patent` listed every applicant and inventor twice, once in each name format the patent office supplied: "`WO2024235369A1` lists 12 inventors for six people", so "A caller counting inventors, or matching a name against another source, gets doubled or mismatched results" ([#483](https://github.com/pvliesdonk/scholar-mcp/issues/483)). `applicants` and `inventors` are now objects with two lists, each naming every party once: `original`, the names as the office supplied them, and `standardised`, one standardised format. The two lists are not paired by position, because EPO does not guarantee that entries with the same sequence number name the same party. The shape appears wherever a patent record does: `get_patent`, `batch_resolve` and `get_citing_patents` ([#579](https://github.com/pvliesdonk/scholar-mcp/pull/579); see the [patent tool reference](https://pvliesdonk.github.io/scholar-mcp/unstable/reference/tools/patents/index.md)).

`get_patent` for a number that does not exist raised a raw HTTP error naming the EPO URL, so "there is no `error` key for a caller to branch on" ([#475](https://github.com/pvliesdonk/scholar-mcp/issues/475)). It now answers `{"error": "patent_not_found"}`, the same answer it gave for an empty record ([#575](https://github.com/pvliesdonk/scholar-mcp/pull/575)).

`search_patents` documented `limit` as at most 100 but sent any value to EPO ([#488](https://github.com/pvliesdonk/scholar-mcp/issues/488)). It now caps `limit` at 100, the most one EPO request returns, and its description says that EPO serves only the first 2,000 results of a search ([#578](https://github.com/pvliesdonk/scholar-mcp/pull/578)).

### Smaller changes

`recommend_books` and `get_book_excerpt` returned "a JSON string wrapped in an object rather than a mapping, so the caller receives double-encoded JSON" ([#370](https://github.com/pvliesdonk/scholar-mcp/issues/370)). Both now return a mapping; `recommend_books` wraps its list as `{"books": [...]}`, like `search_books` ([#583](https://github.com/pvliesdonk/scholar-mcp/pull/583); see the [book tool reference](https://pvliesdonk.github.io/scholar-mcp/unstable/reference/tools/books/index.md)).

`find_bridge_papers` returned a path paper that was not in the cache as a bare `{"paperId": ...}` ([#485](https://github.com/pvliesdonk/scholar-mcp/issues/485)). It now fetches the missing records in one batch request, so every path entry has the record shape `get_paper` returns; a failed lookup marks the result `partial` ([#584](https://github.com/pvliesdonk/scholar-mcp/pull/584)).

When Semantic Scholar throttles a call, the job handle's reason now tells the caller to keep polling, how long the result can take, that every client of the server shares one Semantic Scholar budget, and that an unfinished job has no answer yet rather than an empty one. The server instructions carry the shared budget too. The motivating report found that "a "searched, nothing found" list may contain searches that never finished" ([#569](https://github.com/pvliesdonk/scholar-mcp/issues/569), [#571](https://github.com/pvliesdonk/scholar-mcp/pull/571); see [background jobs](https://pvliesdonk.github.io/scholar-mcp/unstable/use/background-jobs/index.md)).

`get_standard`'s description offered `nist 800-53` as an example, which returns `not_found` because NIST publications are catalogued per revision. The example is now `nist 800-53 rev 5` ([#481](https://github.com/pvliesdonk/scholar-mcp/issues/481), [#586](https://github.com/pvliesdonk/scholar-mcp/pull/586)).

Concurrent book enrichment can no longer replace a cached author list with an empty one: the write that keeps existing authors is now a single statement ([#451](https://github.com/pvliesdonk/scholar-mcp/issues/451), [#587](https://github.com/pvliesdonk/scholar-mcp/pull/587)).

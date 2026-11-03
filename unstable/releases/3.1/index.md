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

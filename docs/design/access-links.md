# Access links

When Scholar MCP cannot fetch a paper's PDF, it can still say where the user
can get it: through their library's link resolver, an inter-library loan form,
a login redirector, or the publisher's page on a network with licence access.
These routes are site-specific and run in the user's browser session, so the
server cannot use them, but it can build links that very likely work for that
user. Epic [#538](https://github.com/pvliesdonk/scholar-mcp/issues/538) holds
the story; [#539](https://github.com/pvliesdonk/scholar-mcp/issues/539) is this
first slice.

## Behaviour

- The operator sets `SCHOLAR_MCP_ACCESS_LINKS` to a JSON list of
  `{"label", "template"}` objects. The list is validated at startup: each
  template must be an `http(s)` URL using only the known placeholders, with no
  format options. A malformed list is a configuration error, so a typo
  surfaces when the server starts rather than as missing links later.
- `fetch_paper_pdf` and `fetch_and_convert` add `access_links` and a `note` to
  the three outcomes where no PDF arrived: `no_oa_pdf`, `download_failed` and
  `not_pdf`. The last two usually mean a publisher answered with a paywall or a
  login page, which is exactly when a library route helps.
- Links come back in the configured order. Order is the operator's way of
  putting the route most likely to succeed first.
- A template whose placeholders the paper cannot fill is skipped, so every
  returned link is complete. With no templates configured, or none fillable,
  the payload is unchanged.
- The server never requests a configured URL. Nothing in this feature widens
  what the server reaches.

## Placeholders

| Placeholder | Needs | Encoding |
|---|---|---|
| `{doi}` | DOI | Percent-encoded except `/ ( )`, so it is safe in a path and in a query value |
| `{doi_url}` | DOI | `https://doi.org/<DOI>`, fully percent-encoded, for wrapping in a redirector's `url=` |
| `{openurl}` | DOI, PubMed ID or title | OpenURL 1.0 KEV, journal format |
| `{openurl_0_1}` | DOI, PubMed ID or title | OpenURL 0.1 |
| `{openurl_hybrid}` | DOI, PubMed ID or title | 1.0 keys followed by the 0.1 keys |

The key sets and encoding rules come from the specifications, recorded in
[OpenURL 0.1 and 1.0 query strings](reference/openurl.md). Both versions are
supported because resolvers differ: an OCLC Link Resolver enriched a 1.0
citation from its DOI but not a 0.1 one, while Google Scholar sends 0.1 to
every library it links to.

## Decisions

- **One generic template list, not a setting per product.** Ovid LinkSolver,
  SFX, Alma, OCLC and OpenAthens all reduce to "a base URL plus a citation or a
  wrapped DOI". A list of templates covers them and anything similar without
  code changes, and the operator controls order.
- **No default templates.** Every URL comes from operator configuration, so
  the shipped package points nowhere.
- **The link builder takes only what the record already has.** It reads DOI,
  PubMed ID, title, venue, year and author names. `genre` is always `article`,
  because records carry no reliable type across sources. Journal ISSN, volume,
  issue and pages are left to
  [#541](https://github.com/pvliesdonk/scholar-mcp/issues/541).
- **No arXiv identifier in OpenURL.** Neither version has a namespace that
  covers current arXiv identifiers (see the reference page); arXiv papers are
  open access and resolved earlier in the pipeline anyway.
- **The next step goes in the result, not the tool description.** The `note`
  tells the model to offer the links to the user, or to open one if it can
  browse from the user's network. The description stays a statement of the
  contract (`writing-model-facing-text`).
- **Templates are parsed per call.** The config holds the raw text; the tool
  parses it when it builds links. Parsing is cheap next to a failed download,
  and keeping config fields plain avoids imports outside the config module's
  sentinel blocks.

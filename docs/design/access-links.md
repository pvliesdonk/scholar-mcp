# Access links

When Scholar MCP cannot fetch a paper's PDF, it can still say where the user
can get it: through their library's link resolver, an inter-library loan form,
a login redirector, or the publisher's page on a network with licence access.
These routes are site-specific and run in the user's browser session, so the
server cannot use them, but it can build links that very likely work for that
user. Epic [#538](https://github.com/pvliesdonk/scholar-mcp/issues/538) holds
the story; [#539](https://github.com/pvliesdonk/scholar-mcp/issues/539) added
the links to failed PDF fetches and
[#540](https://github.com/pvliesdonk/scholar-mcp/issues/540) to `get_paper`;
[#547](https://github.com/pvliesdonk/scholar-mcp/issues/547) made a doi.org
link the default;
[#541](https://github.com/pvliesdonk/scholar-mcp/issues/541) put the journal
details into the OpenURL.

## Behaviour

- Unset, `SCHOLAR_MCP_ACCESS_LINKS` means one template,
  `{"label": "Publisher (DOI)", "template": "https://doi.org/{doi}"}`. An
  explicit `[]` turns links off.
- The operator sets `SCHOLAR_MCP_ACCESS_LINKS` to a JSON list of
  `{"label", "template"}` objects. The list is validated at startup: each
  template must be an `http(s)` URL using only the known placeholders, with no
  format options. A malformed list is a configuration error, so a typo
  surfaces when the server starts rather than as missing links later.
- `fetch_paper_pdf` and `fetch_and_convert` add `access_links` and a `note` to
  the three outcomes where no PDF arrived: `no_oa_pdf`, `download_failed` and
  `not_pdf`. The last two usually mean a publisher answered with a paywall or a
  login page, which is exactly when a library route helps.
- `get_paper` adds `access_links`, without a `note`, to every record it can
  fill a template for, whether or not the paper has an open-access PDF. A
  library route can reach the version of record when the open copy is a
  preprint, and the agent learns the route before trying a fetch.
- Links come back in the configured order. Order is the operator's way of
  putting the route most likely to succeed first.
- A template whose placeholders the paper cannot fill is skipped, so every
  returned link is complete. With links turned off, or no template
  fillable, the payload is unchanged.
- The server never requests a configured URL. Nothing in this feature widens
  what the server reaches.

## Placeholders

| Placeholder | Needs | Encoding |
|---|---|---|
| `{doi}` | DOI | Percent-encoded except `/ ( )`, so it is safe in a path and in a query value |
| `{doi_url}` | DOI | `https://doi.org/<DOI>`, fully percent-encoded, for wrapping in a redirector's `url=` |
| `{openurl}` | DOI, PubMed ID or title | OpenURL 1.0 KEV, journal format, with ISSN, volume, issue and pages when known |
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
- **One default link, and no resolver defaults.** Unconfigured, the server
  offers `https://doi.org/{doi}`: it names no institution, and on a network
  with IP-based licence access it is often the route that works, because
  the publisher sees the network. Every resolver, order-form or redirector
  URL still comes from operator configuration. A configured list replaces
  the default rather than extending it, so the operator decides whether and
  where the DOI link appears; `[]` is the opt-out.
- **The link builder takes only what the record already has.** It reads DOI,
  PubMed ID, title, venue, year and author names, plus ISSN, volume, issue
  and pages. `genre` is always `article`, because records carry no reliable
  type across sources.
- **The cached paper record carries S2's journal details.** `get_paper` and
  the PDF tools fetch the `full` field set plus `journal` and
  `publicationVenue`, which give volume, pages and ISSN. The `full` preset
  itself is unchanged, so `search_papers(fields="full")` and the batch tools
  return what they did. Records cached before this change lack the two
  fields until their 30-day entry expires; their links are built as before.
- **CrossRef first, S2 for the gaps, field by field.** CrossRef keeps volume,
  issue, pages and each ISSN with its type in separate fields. S2 has no
  issue and can merge volume and issue into one string (`"116 6"`), so only
  its first token is taken as the volume. The year follows the same rule:
  CrossRef's `issued` year dates the work the DOI names, while S2's `year`
  can be that of an earlier version, such as the conference paper a journal
  reprinted, and would contradict the volume and pages beside it
  ([#561](https://github.com/pvliesdonk/scholar-mcp/issues/561)). CrossRef metadata is on the record
  only in `get_paper`, after enrichment of a paper with a DOI; the PDF tools
  use S2's details alone. OpenAlex is not read for these details yet.
- **A page range is split into `spage` and `epage`.** A single token, such
  as an article number, is the start page. Anything else is left out rather
  than guessed at. Both OpenURL versions use the same key names for these
  details, so the 0.1 form carries them too.
- **No arXiv identifier in OpenURL.** Neither version has a namespace that
  covers current arXiv identifiers (see the reference page); arXiv papers are
  open access and resolved earlier in the pipeline anyway.
- **The next step goes in the result, not the tool description.** The `note`
  tells the model to offer the links to the user, or to open one if it can
  browse from the user's network. The description stays a statement of the
  contract (`writing-model-facing-text`).
- **Links on `get_paper` are built on read, never cached.** The tool adds
  them to its copy of the record after the cache read, so a changed template
  list applies to the next call, including for papers cached before it.
- **`batch_resolve` carries no links.** It resolves many papers at once to
  identify them; a set of URLs per paper would multiply its output for a use
  that `get_paper` covers.
- **Templates are parsed per call.** The config holds the raw text; the tool
  parses it when it builds links. Parsing a short JSON list is cheap,
  and keeping config fields plain avoids imports outside the config module's
  sentinel blocks.

## When the user fetches the PDF

An access link often works for the user and not for the server, which sits
on another network. [#546](https://github.com/pvliesdonk/scholar-mcp/issues/546)
closes that gap: the user downloads the PDF, and it reaches the server over
a one-time HTTP upload link (pvl-core's transfer subsystem), so the bytes
never pass through the agent's context. The agent's part is a link, an
upload done outside the conversation, and an ordinary conversion call.

- **`create_upload_link` mints upload links only.** It is path 2 of the
  transfer recipe: `build_transfer_links` plus one domain tool. The generic
  `create_download_link` would have nothing to serve, since conversion
  results come back in pages.
- **The upload stores, it does not convert.** docling takes minutes and the
  sink holds the body in memory inside the HTTP request, so the sink only
  checks the `%PDF-` header and writes the file. Conversion stays with
  `fetch_and_convert` (with an identifier) and `convert_pdf_to_markdown`
  (without one).
- **The target is fixed when the link is minted.** With an identifier, the
  tool resolves the paper first, so a typo fails before any upload, and the
  target is the stem `_ensure_paper_pdf` reads. Without one, the server picks
  `upload-<hex>` and returns the `pdf_path`, so the agent can proceed even
  when the user did the upload.
- **The cache is read before any download source.** `_ensure_paper_pdf`
  used to consult its cache inside the candidate loop, which never ran for a
  closed-access paper with no source. A cache hit now reports `pdf_source`
  `"cache"`.
- **Uploads join the shared cache.** The maintainer decided this
  (2026-11-09), in line with `fetch_pdf_by_url` and `convert_pdf_to_markdown`,
  which already cache what a caller supplies. There is no per-upload opt-out.
- **A wrong document is corrected with `replace`, not overwritten.** Minting
  is refused while a valid PDF is stored for the paper, and the sink answers
  `409` if one appeared since, so two links cannot race and leave stale
  Markdown behind. `replace=true` deletes the stored PDF and both Markdown
  conversions when the link is minted. If the right file never arrives, the
  wrong content is gone anyway, so there is no separate remove tool.
- **No public URL, no tool.** Upload links need `SCHOLAR_MCP_BASE_URL`. A
  server without it starts as before and logs `pdf_upload_disabled`, rather
  than refusing to start as the template recipe suggests, which would break
  existing HTTP deployments on upgrade.
- **The failure payload names the tool only when it is callable.**
  `fetch_and_convert` adds an `upload` hint when `get_tool` finds
  `create_upload_link`, which it does not for a hidden or unregistered tool.
  The hint never creates a link: most failed fetches end without an upload.
- **No inline base64 route** ([#597](https://github.com/pvliesdonk/scholar-mcp/issues/597)).
  A PDF passed as a tool argument occupies the agent's context, which is the
  cost this design exists to avoid.

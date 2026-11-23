# CrossRef book chapters

A paper whose DOI names a CrossRef `book-chapter` work gets a `chapter_info`
dict with `citation_source: "crossref"`, built from the chapter record and,
when the chapter links to it, the parent book record
([#67](https://github.com/pvliesdonk/scholar-mcp/issues/67)). The field rules
follow [CrossRef book-chapter fields](reference/crossref-book-chapter-fields.md).

## Behaviour

- `CrossRefChapterEnricher` (`_enricher_crossref_chapter.py`) runs in
  enrichment phase 1, after `CrossRefEnricher` has stored the raw work as
  `crossref_metadata`. It reads that key and never changes it, so a record
  that already carries `crossref_metadata` is mapped too.
- It applies to `papers`-tagged enrichment (`get_paper`, `get_citations`,
  `get_references`, `get_citation_graph`, and `generate_citations` with
  `enrich`) when
  `crossref_metadata.type == "book-chapter"` and the record has no
  `chapter_info` yet.
- The parent book is fetched by the DOI in `relation.is-part-of`, with the
  `https://doi.org/` prefix stripped, through the same `crossref` cache table
  every CrossRef work uses (30-day TTL). A second chapter of the same book, or
  a repeat lookup, costs no request.
- Fields, each left out when CrossRef has nothing:

  | Key | Source |
  | --- | --- |
  | `chapter_title` | chapter `title[0]` |
  | `parent_title` | the **last** `container-title` element (the first is the series when there are two), unescaped and stripped of markup; the parent's `subtitle` is appended when the title lacks it; the parent's `title` when the chapter has none |
  | `parent_doi` | `relation.is-part-of` |
  | `editors` | chapter `editor`, else the parent's, as `"Given Family"` strings (`name` for an organisation) |
  | `pages` | chapter `page`, as given (`xiii-xiii`, `639-650.e3`) |
  | `page_start`, `page_end` | set only when `pages` is one number or a range of two plain numbers |
  | `publisher`, `publisher_location`, `edition` | chapter `publisher`, `publisher-location`, `edition-number`, else the parent's |
  | `isbn` | the `print` ISBN from `isbn-type`, else the electronic one, else the `ISBN` array; chapter first, then parent; only an ISBN whose check digit passes, digits as given |

  No chapter number is mapped: CrossRef has no such field.

## Outcomes

- **No `is-part-of` link** (every Elsevier chapter in the reference sample):
  the chapter is mapped from its own record and no extra request is made.
  Following the ISBN to a parent book was considered and not built; whether
  an `isbn:` filter returns the parent is unverified on the reference page
  ([#753](https://github.com/pvliesdonk/scholar-mcp/issues/753)).
- **Parent lookup fails** (404, throttled, network error, cache error): the
  chapter is still mapped from its own record, without the book's editors or
  subtitle, and `crossref_chapter_without_parent` is logged at DEBUG. A failed
  lookup is not cached, so the next call asks again. The CrossRef client
  itself already logs `crossref_error` at WARNING for an HTTP error.
- An unexpected exception while mapping is caught by the pipeline's own
  guard (`enricher_failed` at DEBUG); the record then has no `chapter_info`.

## Decisions

- **Where it lands.** `chapter_info` on the paper record, the key and shape
  (`BookChapterRecord`) the parsed hints already use, so a consumer reads one
  shape and tells the sources apart by `citation_source`. `batch_resolve`
  keeps attaching its parsed `chapter_info` to the result entry beside
  `paper`; it runs no enrichment, so its `paper` never carries the CrossRef
  one. Alternatives: a new key such as
  `crossref_chapter` (a second shape to learn), or reshaping
  `crossref_metadata` (read by `_access_links.py`; kept as is).
- **Pages.** The raw string is always kept, because forms such as
  `xiii-xiii`, `639-650.e3` and `343a-349` occur and do not fit two
  integers; the integer keys stay for the parsed path's consumers.
- **Rate limit.** The public pool allows one request a second with one in
  flight, and the parent fetch adds one request per uncached book. The
  CrossRef client has no rate limiter today; adding one is a separate change
  ([#752](https://github.com/pvliesdonk/scholar-mcp/issues/752)).

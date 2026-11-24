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
  every CrossRef work uses (30-day TTL). A later call for a chapter of the
  same book reads the parent from the cache; two chapters of one book in the
  same batch can both miss it, because their lookups run concurrently.
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
- **Parent lookup finds nothing or fails** (404, throttled, HTTP or
  transport error, cache error, corrupt cached row): the chapter is still
  mapped from its own record, without the book's editors or subtitle, and
  `crossref_chapter_without_parent` is logged at DEBUG. A failed lookup is
  not cached, so the next call asks again. The CrossRef client logs the
  cause once: `crossref_not_found` at DEBUG for a 404,
  `crossref_rate_limited` at WARNING without a traceback for a 429, and
  `crossref_error` at WARNING with a traceback for any other HTTP,
  transport or body error.
- **Any other exception** in the parent lookup or the mapping is a bug.
  `_fetch_parent` catches only the failures listed above
  (`RateLimitedError`, `httpx.HTTPError`, `sqlite3.Error`, `ValueError`), so
  anything else reaches the pipeline's own guard (`enricher_failed` at
  DEBUG with the traceback) and the record then has no `chapter_info`.

## Decisions

- **Where it lands.** `chapter_info` on the paper record, the key and shape
  (`BookChapterRecord`) the parsed hints already use, so a consumer reads one
  shape and tells the sources apart by `citation_source`. `batch_resolve`
  keeps attaching its parsed `chapter_info` to the result entry beside
  `paper`; it runs no enrichment, so its `paper` never carries the CrossRef
  one. Alternatives: a new key such as
  `crossref_chapter` (a second shape to learn), or reshaping
  `crossref_metadata` (read by `_access_links.py`; kept as is).
- **Flat parent fields, not `parent_book`.** `BookChapterRecord` already has
  `parent_book: BookRecord`, which the NPL path fills from an ISBN lookup
  (#64). The book's editors have no `BookRecord` field, and filling a
  `BookRecord` from a CrossRef work would mix two sources' normalisations
  into one record, so the CrossRef fields stay flat next to `parent_title`.
  The alternative, a CrossRef-built `parent_book` with an added `editors`
  field, would give both paths one place for the book; #593 can decide
  which shape it reads.
- **Pages.** The raw string is always kept, because forms such as
  `xiii-xiii`, `639-650.e3` and `343a-349` occur and do not fit two
  integers; the integer keys stay for the parsed path's consumers.
- **No title query for a chapter without a DOI.** A paper reaches CrossRef
  only through its DOI. A `type:book-chapter` title query was measured
  for #745 and not built: of 37 DOI-less S2 `BookSection` papers, an equal
  title plus a shared author confirmed 2, and only `generate_citations`
  requests the `publicationTypes` that would select them
  ([reference](reference/crossref-book-chapter-fields.md#yield-for-chapters-that-reach-this-project-without-a-doi)).
- **Rate limit.** `CrossRefClient` spaces request starts with a
  `RateLimiter` of 0.2 s (`_CROSSREF_DELAY` in `domain.py`) and holds a
  lock across each request, so at most one is in flight. This matches what
  the public pool advertises for `/works/{doi}`, the only endpoint the
  client calls: 5 requests a second, concurrency 1
  ([reference](reference/crossref-book-chapter-fields.md#title-queries-for-chapters-without-a-doi);
  list queries are limited to 1 a second and would need their own
  limiter). The delay is a constant, not read from the
  `x-rate-limit-*` headers: the headers differ per endpoint shape, the
  single-work values were observed directly, and adapting to them would
  add parsing for no request the client makes today. The same pacing
  applies with a `contact_email`, since a higher polite-pool limit is
  unverified. A 429 raises `RateLimitedError`, which both CrossRef
  enrichers treat as a missing layer for this call; there is no retry, and
  the limiter's `cooldown()` is not used, because inside an S2-backed tool
  an active cooldown is reported to the job as an S2 throttle
  (`S2_RETRY_CONTEXT`) and would defer the tool for a CrossRef reason
  ([#752](https://github.com/pvliesdonk/scholar-mcp/issues/752)).

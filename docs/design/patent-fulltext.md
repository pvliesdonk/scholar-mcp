# Patent claims and description

`get_patent`'s `claims` and `description` sections come from OPS's full-text
endpoints. How those responses are shaped is recorded in
[EPO OPS full-text claims and description](reference/epo-ops-fulltext.md).

## Parsing

`parse_claims_xml` and `parse_description_xml` read the
`ftxt:fulltext-document` in the fulltext namespace and pick the English
section, matching `lang` case-insensitively, else the first one. Claims are
joined one `claim-text` per paragraph, because an EP claim set is one `claim`
element holding every `claim-text`, and joining the element's text glued one
claim onto the next. The description is joined one `p` per paragraph.

Until #701 the parsers looked for an `exchange-document` in the exchange
namespace, which OPS never sends here, so both sections were always empty.
Every row the claims and description caches held was therefore `""`; the
one-shot repairs `701_empty_patent_claims` and
`701_empty_patent_descriptions` drop them, so the next call fetches the text.

## No full text

OPS answers 404 when it holds no full text for a publication; US11234567B2
and EP3491801A1 do. The section is then `null`, not an error: the caller asked
a valid question about a real patent, and `fetch_patent_pdf` is where the
document text can come from instead. The 404 is not cached, so a call made
after EPO adds the text gets it. Any other HTTP error from these endpoints
still fails the call. A publication that does not exist is reported by the
biblio probe as `not_found`, ahead of this.

## Markdown (#44)

The callers are agents, so the text comes ready to read: an agent should not
fetch the PDF, or restructure plain text itself, just to read a claim.
`_patent_text.py` turns the parsed elements into compact Markdown and adds
nothing a reader does not use.

- **Claims:** one `N. …` block per claim, blocks separated by a blank line.
  An EP claim continued across several `claim-text` elements is rejoined; a
  WO claim set sent as one block is split at each claim number. Only the
  next number in sequence starts a claim, which skips claim references such
  as "according to claim 1." and accepts OCR spellings such as `1 3.` for 13
  and `1 .` for 1. The `CLAIMS` label a WO set opens with is dropped. Text
  before the first number is kept as its own block rather than lost.
- **Description:** a short upper-case paragraph with no paragraph number and
  no final full stop becomes a `##` heading. OPS marks no headings, so this
  is a heuristic: a bare caption such as `FIG. 1` would also qualify. Every
  other paragraph keeps its text and its number (`[0001] …`), because that
  is how patents are cited; WO paragraphs carry none and none are invented.
- **Whitespace:** runs of spaces collapse to one. OCR artefacts in the words
  themselves (`(1 1 , 21 , 31 )`) are left alone: rewriting text an agent may
  quote is worse than a stray space.

Claims and descriptions are cached as Markdown. The one-shot repairs
`44_patent_claims_as_markdown` and `44_patent_descriptions_as_markdown` drop
every row once, because a release with only the #701 fix cached plain text.

## Paging

The description is paged with the shared `page_text()` contract
([Converted document response windows](document-text-responses.md)):
`get_patent` takes `text_offset` and `max_chars`, at most 20,000 characters a
page, and the response carries the `text_*` fields and `next_offset`, all
counting description characters. The whole description stays cached, so a
later page costs no EPO request. Claims are not paged: they are short, and an
agent comparing claims needs them all at once.

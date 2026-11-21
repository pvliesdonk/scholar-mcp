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

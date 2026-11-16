# Standards search ranking

`search_standards` ranks its results so that a query naming a standard
without its revision or year finds the current edition first (#487). Every
source matches by substring. Before this, each returned its first matches in
storage or upstream order: `27001` against ISO returned the 2005 edition and
two 2013 corrigenda, and the 2022 edition was not among the first three.

`_standards_ranking.rank_standards` holds the order, most significant first:

1. An identifier equal to the query. Naming an edition exactly, replaced or
   not, returns that edition first.
2. A match in the identifier before a match in the title only.
3. Status: published, draft (and any unknown status), superseded, withdrawn.
4. The query as the whole document number before the query inside a longer
   number (`800-53` in `800-53A`) or followed by an amendment, corrigendum or
   consolidated-version suffix (anything after `/` or `+`).
5. Publication date, newest first, undated last; then identifier.

Key 2 sits above status because of what real data showed: with status first,
`27001` against the ISO dump listed ISO/IEC 27013:2021/Amd 1 and ISO/IEC
27021:2017/Amd 1, published documents that name 27001 in their titles, above
ISO/IEC 27001:2013. A caller asking for 27001 wants its editions, not the
documents that cite it.

Where the ranking applies:

- **NIST** and **ETSI** rank every match before `limit` applies: NIST's
  catalogue is in memory, and ETSI answers with every match in one response.
- **Synced bodies** (ISO, IEC, IEEE, CC, CEN): SQL orders the matches by the
  same keys, coarsely (exact identifier, identifier `LIKE`, status, date),
  and the first 500 are ranked exactly. A broad query can match tens of
  thousands of synced rows, which is why the read is bounded.
- **IETF** passes `limit` to datatracker, and **W3C** learns a specification's
  status only by fetching it, so both rank only the first `limit` matches.
- **All bodies**: `_collect_search` ranks the merged lists before cutting to
  `limit`. `resolve_standard_identifier`'s ambiguous candidates come from this
  search, so they follow the same order.

Cached search results were written in the old order, and could lack the
current edition altogether; the `487_standards_search_results` repair empties
them on upgrade. A search cached before a later sync changes records is a
separate gap (#658).

Edge: NIST names the first edition of FIPS 140 plainly, so `FIPS 140` returns
the 1982 FIPS 140 first (key 1) and FIPS 140-3 second.

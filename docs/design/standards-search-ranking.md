# Standards search ranking

`search_standards` ranks its results so that a query naming a standard
without its revision or year finds the current edition first (#487). Every
source matches by substring. Before this, each returned its first matches in
storage or upstream order: `27001` against ISO returned the 2005 edition and
two 2013 corrigenda, and the 2022 edition was not among the first three.

`_standards_ranking.rank_standards` holds the order, most significant first:

1. An identifier equal to the query. Naming an edition exactly, replaced or
   not, returns that edition first.
2. Which document the identifier names: the queried one, then another
   document whose identifier contains the query, then one that matches in
   its title only.
3. Status: published, draft (and any unknown status), superseded, withdrawn.
4. The edition before its amendments: the query as the whole document number
   before the query followed by an amendment, corrigendum or
   consolidated-version suffix (anything after `/` or `+`) or by a dash and
   digits (`140-3`, `62443-3-3`, `1588-2019`).
5. Publication date, newest first, undated last; then identifier.

Another document is the query inside a longer number (`29001` for `9001`,
`800-53A` for `800-53`, `1588c`), followed by a dash and a letter
(`27001-HBK`), or followed by a dot and more of a number (`802.11` for
`802`). A dash and digits stays with the queried document because the
bodies use it for an edition (FIPS `140-3`, NIST `800-63-4`), a part
(`62443-3-3`) and a year (IEEE `1588-2019`).

Key 2 sits above status because of what real data showed. With status
first, `27001` against the ISO dump listed ISO/IEC 27013:2021/Amd 1 and
ISO/IEC 27021:2017/Amd 1, published documents that name 27001 in their
titles, above ISO/IEC 27001:2013 (#487). With key 2 telling only identifier
from title matches, `27001` across all bodies put the handbook ISO/IEC
27001-HBK:2024 first, and `9001` against ISO put ISO 29001:2020 above ISO
9001:2015 (#674). A caller asking for 27001 wants its editions, not the
documents that contain or cite its number.

Where the ranking applies:

- **NIST** and **ETSI** rank every match before `limit` applies: NIST's
  catalogue is in memory, and ETSI answers with every match in one response.
- **Synced bodies** (ISO, IEC, IEEE, CC, CEN): SQL orders the matches by the
  same keys, coarsely (exact identifier, identifier `LIKE`, status, date),
  and the first 500 are ranked exactly. A broad query can match tens of
  thousands of synced rows, which is why the read is bounded. SQL does not
  tell the queried document from another one, so a very short query can
  leave a replaced edition outside the 500: `802` matches 2,140 synced
  identifiers, 301 of them published.
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

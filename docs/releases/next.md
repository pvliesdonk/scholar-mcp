# Next release

<!-- notes-range-end: 0784a45f301611ef62a35bdad1e05e991d33d541 -->

<!-- RELEASE-SUMMARY NEXT START -->
OpenURL access links now carry the year of the work the DOI names, so a
library resolver gets a consistent citation. No upgrade steps are needed.
<!-- RELEASE-SUMMARY NEXT END -->

## OpenURL year

An OpenURL access link (`{openurl}`, `{openurl_0_1}` or `{openurl_hybrid}`)
took its year from Semantic Scholar, which sometimes gives the year of an
earlier version of the paper. For the 2017 Communications of the ACM reprint of
a 2012 conference paper, the link said 2012 next to the 2017 volume and pages.
A resolver that has to match a paper without a DOI by its metadata could then
miss it. The link now
takes the year from the paper's CrossRef record when it has one, and from
Semantic Scholar otherwise
([#561](https://github.com/pvliesdonk/scholar-mcp/issues/561),
[#562](https://github.com/pvliesdonk/scholar-mcp/pull/562)).

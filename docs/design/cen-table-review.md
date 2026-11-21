# CEN harmonised-standards table review

`_HARMONISED_STANDARDS` in `src/scholar_mcp/_sync_cen.py` is a hand-kept
list of EU harmonised standards. The Commission changes what is cited
several times a year per act, so the table goes stale unless someone checks
it. This page is the procedure for that check. A person doing the review by
hand follows it, and `.github/workflows/cen-review.yml` gives it to Claude
Code each quarter (#594), with the table appended, to file the findings as
an issue.

The first full review (#139, 2026-11-20) found about half the table wrong:
standards never cited under the act listed, editions other than the cited
one, missing amendments, withdrawn standards still marked harmonised, and a
whole act (the Cyber Resilience Act) under which nothing was cited yet.

## What to check

For each act the table covers, and for each act it notes as having nothing
cited yet:

1. Open the Commission's harmonised-standards page for the act, under
   https://single-market-economy.ec.europa.eu/single-market/european-standards/harmonised-standards_en.
   It names the base implementing decision and every amending decision, in
   order. Note the newest one.
2. Read every decision adopted since the table was last reviewed (the date
   is in the comment above the table). Read them one by one. Do not rely on
   the consolidated text or the summary list alone: both can lag the newest
   decision. In a 2026 trial, a review that read only the consolidated text
   missed a decision adopted eleven days earlier.
3. For each table entry, establish from those decisions, and from the base
   decision for anything older:
   - whether this reference is cited under the act the entry names;
   - the exact cited reference, with its amendments;
   - whether a newer edition or amendment is cited, and the date the older
     one stops giving presumption of conformity;
   - for an entry marked withdrawn, the date presumption ended and what the
     decision names in its place.
4. Look for standards newly cited since the last review that the table
   should carry: a successor to an entry, or a widely used standard such as
   the RED cybersecurity standards EN 18031-1/-2/-3.
5. Check the acts whose lists are changing: a directive being replaced by a
   regulation (Machinery Directive 2006/42/EC by Regulation (EU) 2023/1230
   from 20.01.2027, Toy Safety Directive 2009/48/EC by Regulation (EU)
   2025/2509 from 01.08.2030), and acts with nothing cited yet (the Cyber
   Resilience Act (EU) 2024/2847, under standardisation request M/606).

## Sources

- Every claim cites a decision by number and the URL it was read at.
  Secondary sources (consultancies, vendor blogs) only point to a primary
  source.
- EUR-Lex serves decisions at
  `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:<CELEX>`,
  where a decision (EU) 2026/2479 is CELEX `32026D2479`. EUR-Lex often
  answers automated requests with HTTP 202 and an empty body, or 429.
- The Publications Office serves the same Official Journal text at
  `https://publications.europa.eu/resource/celex/<CELEX>` when the request
  asks for `application/xhtml+xml` and English. `scripts/fetch_oj.sh
  <CELEX>` makes that request.
- The Commission's summary lists (xlsx or pdf) consolidate every citation
  with its dates. They are for information only and can be months behind;
  use them to cross-check, not as the last word.
- The OJ cites ETSI standards by version only (`EN 301 893 V2.2.1`). The
  table adds the year of ETSI's published file, which the deliverables
  directory under `https://www.etsi.org/deliver/etsi_en/` lists.

## How the table records a citation

- One entry per cited reference, written as cited, with the latest cited
  amendment as a single `+A` suffix (`EN 55032:2015+A11:2020`). Corrigenda
  and earlier amendments are left out: the sync keeps one `+A` suffix and
  strips it for the stored identifier.
- An edition that is still cited until a stated date stays `harmonised`
  beside its successor, with a comment giving the date.
- A reference whose presumption has ended is `withdrawn`, with
  `withdrawn_date` and `superseded_by` naming the table entry that replaced
  it.
- A reference that was never cited under the act is removed. The sync then
  deletes its record rather than marking it withdrawn.
- `directive` names the act the reference is cited under: `EMC`, `RED`,
  `Machinery`, `MDR`, `LVD`, `Toys` or `GPSR`.

## What a review produces

A list of discrepancies, one per table entry or missing standard: what the
table says, what the cited reference is, the decision and URL that say so,
and the change to make. Anything not confirmed from a primary source is
marked unverified. When nothing differs, the review says so and names the
newest decision it read for each act.

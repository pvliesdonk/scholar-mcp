---
type: Reference
title: OpenURL 0.1 and 1.0 query strings
description: The keys, identifier forms and encoding rules of OpenURL 0.1 and ANSI/NISO Z39.88-2004 KEV links, and how resolvers treat hybrid links.
subject_version: "OpenURL 0.1 (OpenURL/1.0f, 2000-05-16); ANSI/NISO Z39.88-2004 (R2010)"
valid_for: "OpenURL 0.1 and Z39.88-2004; both frozen since the registry closed"
generated:
  by: process:researching-references
  at: 2026-11-02T14:00:00+01:00
stale_after: 2027-11-02T14:00:00+01:00
status: stable
verified:
  - by: process:researching-references
    at: 2026-11-02T16:00:00+01:00
sources:
  - id: openurl-01
    title: OpenURL Syntax Description, OpenURL/1.0f (OpenURL 0.1), OCLC Research frozen mirror
    resource: https://oclc-research.github.io/OpenURL-Frozen/docs/pdf/openurl-01.pdf
    accessed: 2026-11-02
  - id: z3988
    title: ANSI/NISO Z39.88-2004 (R2010), The OpenURL Framework for Context-Sensitive Services
    resource: https://groups.niso.org/higherlogic/ws/public/download/14833/z39_88_2004_r2010.pdf
    accessed: 2026-11-02
  - id: niso-page
    title: NISO publication page for Z39.88-2004 (R2010)
    resource: https://www.niso.org/publications/z3988-2004-r2010
    accessed: 2026-11-02
  - id: mtx-ctx
    title: KEV ContextObject Format matrix (info:ofi/fmt:kev:mtx:ctx)
    resource: https://oclc-research.github.io/OpenURL-Frozen/ContextObjectFormats/info:ofi/fmt:kev:mtx:ctx.mtx.html
    accessed: 2026-11-02
  - id: mtx-journal
    title: KEV Journal Format matrix (info:ofi/fmt:kev:mtx:journal)
    resource: https://oclc-research.github.io/OpenURL-Frozen/MetadataFormats/info:ofi/fmt:kev:mtx:journal.mtx.html
    accessed: 2026-11-02
  - id: kev-guidelines
    title: Z39.88-2004 KEV Format Implementation Guidelines, v1.7 (2004-12-09)
    resource: https://oclc-research.github.io/OpenURL-Frozen/docs/implementation_guidelines/KEV_Guidelines-20041209.pdf
    accessed: 2026-11-02
  - id: info-sid
    title: info URI registry record for info:sid/
    resource: https://oclc-research.github.io/infoURI-Frozen/info-uri.info/info:sid/reg.xml
    accessed: 2026-11-02
  - id: info-frozen
    title: '"info" URI Registry (Frozen) notice'
    resource: https://oclc-research.github.io/infoURI-Frozen/
    accessed: 2026-11-02
  - id: iota
    title: NISO RP-21-2013, Improving OpenURLs Through Analytics (IOTA)
    resource: https://groups.niso.org/higherlogic/ws/public/download/10811/RP-21-2013_IOTA.pdf
    accessed: 2026-11-02
  - id: oclc-resolver
    title: OCLC, A-Z List and OCLC Link Resolver
    resource: https://help.oclc.org/Librarian_Toolbox/OCLC_Service_Configuration/WorldCat_Discovery_and_WorldCat_Local/A_Z_List_and_OCLC_Link_Resolver
    accessed: 2026-11-02
---

# OpenURL 0.1 and 1.0 query strings

How a link resolver expects a citation to be encoded in a URL query, in the
two forms resolvers accept: OpenURL 0.1 and OpenURL 1.0 (ANSI/NISO
Z39.88-2004, Key/Encoded-Value Inline transport, journal format). The
`{openurl}`, `{openurl_0_1}` and `{openurl_hybrid}` access-link
placeholders are built from these rules.

## Scope

- Covers: the 0.1 keys, the 1.0 administrative and journal-format keys,
  identifier forms for DOI and PubMed IDs, value encoding, hybrid links,
  length limits, and what one OCLC resolver did with each form.
- Does not cover: the XML and By-Reference transports, the book and
  dissertation formats, service (`svc_`) keys, or COinS.
- Depended on by: `src/scholar_mcp/_access_links.py` (the OpenURL
  placeholders) and [the access-links design note](../access-links.md).

## Claims

### Status and where the specification lives

- Z39.88-2004 was approved by ANSI on 2005-04-15 and reaffirmed on 2010-05-13; NISO publishes it as one PDF containing Parts 1 to 4. [source: z3988] (p.1) [source: niso-page]
- The format matrices in the OpenURL registry are normative for the KEV keys. [source: z3988] (§12)
- The original registry host no longer resolves; OCLC Research hosts a frozen copy whose matrices match 2006–07 archive snapshots row for row. [observed: DNS lookup of the old host, and a row-by-row comparison of the frozen matrices with Wayback snapshots, 2026-11-02]
- The info URI registry closed to new namespaces on 2010-05-22. [source: info-frozen]
- The Z39.88 foreword renames the 2000 "OpenURL Syntax Description" to OpenURL 0.1. [source: openurl-01] (Foreword)

### OpenURL 0.1

- A query is `BASE-URL ? DESCRIPTION`, where a description has optional global identifier (`id`), metadata and local identifier (`pid`) zones. [source: openurl-01] (§1, §4)
- `sid` is `VendorID:DatabaseID`, the VendorID alphanumeric, the colon unescaped. [source: openurl-01] (§3) [pins: tests/test_access_links.py::test_openurl_0_1_uses_the_0_1_keys]
- `id` is `namespace:identifier` over four namespaces, `doi`, `pmid`, `bibcode` and `oai`; the colon stays unescaped and `id` may repeat. [source: openurl-01] (§5) [pins: tests/test_access_links.py::test_openurl_0_1_uses_the_0_1_keys]
- There is no `arxiv` namespace; the specification's own example writes an arXiv paper as `oai:arXiv:physics/0003005`. [source: openurl-01] (§5)
- Metadata keys include `genre` (`journal`, `book`, `conference`, `article`, `preprint`, `proceeding`, `bookitem`), `aulast`, `aufirst`, `auinit`, `issn`, `eissn`, `isbn`, `title` (the journal or book), `stitle`, `atitle` (the article), `volume`, `part`, `issue`, `spage`, `epage`, `pages`, `artnum` and `date` (`YYYY`, `YYYY-MM` or `YYYY-MM-DD`). Author keys describe the first author only. [source: openurl-01] (Table 1)
- Values are escape-encoded per RFC 2396: alphanumerics and `- _ . ! ~ * ' ( )` stay, everything else is `%HH`, and the examples encode `/` as `%2F`. No character set is named. [source: openurl-01] (§0, §5) [pins: tests/test_access_links.py::test_openurl_0_1_keeps_the_rfc2396_unreserved_marks]

### OpenURL 1.0 (Z39.88-2004 KEV)

- `url_ver=Z39.88-2004` is the only required transport key; a query without it is treated as 0.1. [source: z3988] (§22.1) [source: kev-guidelines] (App. A.1) [pins: tests/test_access_links.py::test_openurl_1_0_carries_the_required_and_referent_keys]
- `url_ctx_fmt=info:ofi/fmt:kev:mtx:ctx`, `ctx_ver=Z39.88-2004` and `ctx_enc` are optional; the standard text and examples write the UTF-8 encoding as `info:ofi/enc:UTF-8`, while the ctx matrix row refers to the IANA name. [source: z3988] (§13.3, Table 17) [source: mtx-ctx]
- `rft_val_fmt` must be present when any `rft.*` key is used; journal metadata uses `info:ofi/fmt:kev:mtx:journal`. [source: mtx-ctx] [source: mtx-journal]
- `rft_id` may repeat; identifiers are URIs such as `info:doi/10.1126/...` and `info:pmid/9036860`. [source: mtx-ctx] [source: z3988] (Table 26) [pins: tests/test_access_links.py::test_openurl_1_0_carries_the_required_and_referent_keys]
- `rfr_id` names the referrer as `info:sid/<domain>[:<collection>]`. [source: info-sid] [source: kev-guidelines] (§4.6)
- Journal keys: `genre` (`journal`, `issue`, `article`, `proceeding`, `conference`, `preprint`, `unknown`), `atitle`, `jtitle` (preferred over `title`, which exists for 0.1 compatibility), `stitle`, `aulast`, `aufirst`, `auinit`, `au` (repeatable, one name per value), `date`, `volume`, `issue`, `part`, `spage`, `epage`, `pages`, `artnum`, `issn`, `eissn`, `isbn`, `coden`. Every key except `au` occurs at most once. [source: mtx-journal]
- Keys may repeat and their order does not matter. [source: z3988] (§12.1, §22.2)
- Values are encoded as UTF-8, then every byte other than alphanumerics and `. - * _` becomes `%XY`; a space may be `+` or `%20`. So `: / ( ) ~` are escaped in 1.0. [source: z3988] (§13.4) [pins: tests/test_access_links.py::test_openurl_1_0_escapes_everything_but_the_kev_safe_set, tests/test_access_links.py::test_openurl_1_0_encodes_non_ascii_as_utf8]
- Resolvers must accept URLs up to 255 bytes and should accept up to 2,048. [source: z3988] (App. E.1) [pins: tests/test_access_links.py::test_openurl_caps_listed_authors]
- Keys outside the defined prefixes are foreign keys that a 1.0 resolver may ignore. [source: z3988] (§22.1)

### Hybrid links

- The KEV guidelines let a referrer send hybrid links carrying both the 1.0 keys and the 0.1 keys where the two differ, and expect resolvers to ignore the foreign keys. [source: kev-guidelines] (App. A.2) [pins: tests/test_access_links.py::test_openurl_hybrid_carries_both_versions]
- The guidelines map 0.1 to 1.0 as `sid` to `rfr_id=info:sid/...`, `id=doi:` to `rft_id=info:doi/`, a metadata key to `rft.` plus the key, and `title` to `rft.jtitle`. [source: kev-guidelines] (App. A.1)
- They say resolvers should continue to accept 0.1 links and may receive hybrids; the standard itself sets no resolver behaviour. [source: kev-guidelines] (§8)
- IOTA's core journal elements for resolution are `atitle`, `aulast`, `date`, `issn`, `issue`, `spage`, `title`/`jtitle` and `volume`. [source: iota] (Table 1)

### Resolver behaviour observed

- OCLC documents its Link Resolver as supporting both 0.1 and 1.0, and documents the request button as always shown only for 1.0. [source: oclc-resolver]
- One OCLC Link Resolver accepted a 1.0 and a 0.1 link for the same citation. Given `rft_id=info:doi/`, it filled in article title, author and ISSN itself; given `id=doi:`, it showed only the fields sent. [observed: the result pages of both links, saved from a browser on the institution's network, 2026-11-02]
- Google Scholar's library links send pure 0.1 links with `sid=google`, which breaks the `VendorID:DatabaseID` grammar, and leave `/` unescaped; the resolver accepted them. [observed: a Google Scholar library link followed in a browser, 2026-11-02]

## Where this project departs from the subject

- The 0.1 `sid` is fixed as `scholarmcp:scholarmcp` and the 1.0 `rfr_id` as `info:sid/pvliesdonk.github.io:scholar-mcp`; neither is registered. Resolvers use the referrer for statistics, not for resolution. [unverified] A resolver rejecting an unknown referrer would show it.
- `genre` is always `article`, because the paper records carry no reliable type for every source. See [the access-links design note](../access-links.md).
- `aulast` and `aufirst` come from splitting the first author's display name at its last space, so particles such as "van" land in `aufirst`.
- At most five `rft.au` values are sent, to keep the link under 2,048 bytes.

## Not covered

- arXiv identifiers: `info:arxiv/` is registered for old-style identifiers only and is not in the 1.0 core namespaces, and the 0.1 `oai:` form for arXiv is uncertain, so no arXiv identifier is sent.
- The NISO status of Z39.88 after the 2010 reaffirmation.
- Whether resolvers handle the hybrid form as well as either pure form; no resolver was tested with it.

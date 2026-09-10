# EPO OPS interface specifications

Vendored copies of the EPO specifications this project's patent integration is
written against. Internal developer reference: `docs/design/**` is excluded from
the published site (`mkdocs.yml`) and from Vale.

Refs #382.

## Why these are in the tree

Because their absence cost us a shipped bug. `_parse_pdf_link` matched the PDF
MIME type as a `desc` attribute on a direct child of `ops:document-instance`,
and the hand-written test fixtures encoded the same shape, so the suite stayed
green while `fetch_patent_pdf` returned `pdf_not_available` for every patent
(#371). `schemas/ops.xsd` declares the real content model outright:

```xml
<xs:element name="document-instance">
  <xs:sequence>
    <xs:element ref="ops:document-format-options" />   <!-- required -->
```

The shape those fixtures assumed was never valid. Reading the schema would have
been faster than the investigation that eventually found it, and cheaper than
the live API calls that confirmed it.

**Prefer these files over probing the live service.** Every OPS call spends
quota from a shared allowance.

## What each artefact answers

| File | Use it for |
|---|---|
| `ops.yaml` | The OPS 3.2 OpenAPI (Swagger 2.0) description: every operation, its parameters, and their types. |
| `schemas/ops.xsd` | Response content models — `document-instance`, `document-format-options`, `inquiry-result`, fault shapes, and the `desc` enumeration. |
| `schemas/ops_legal.xsd` | The `L###EP` legal-event element vocabulary. Load-bearing: `EpoClient.get_legal` feeds `parse_legal_xml` (`src/scholar_mcp/_epo_xml.py`). |
| `schemas/fulltextdocuments.xsd` | Description and claims sub-documents returned by the fulltext services. |
| `schemas/ccd.xsd` | Common Citation Document structure. |
| `schemas/rplus.xsd` | Register-plus data. |
| `schemas/CPCSchema.xsd`, `schemas/CPCDefinitions.xsd` | CPC classification scheme and definitions. |
| `cpc/` | CPC International sample data and the 2019 OPS release announcement. |

## Answers worth knowing about

Three findings that cost live API calls to establish, each stated plainly in
these files:

**One page per image request.** `ops.xsd`, `document-formatType-REST`:

> `application/pdf`: A single page of the document in PDF format.

And `ops.yaml` types the images `Range` parameter as a **required integer**
described as "Page number". A full patent is one request per page (#379).

**`number-of-pages` is required** on `document-instance` (`ops.xsd`). Code that
handles a missing count defensively is covering a case the schema forbids —
worth keeping anyway, since OPS is not obliged to honour its own schema, and
guessing a page count is how documents get silently truncated.

**One image-retrieval operation exists.** `ops.yaml` lists
`/published-data/images/{image-country}/{image-number}/{image-kind}/{image-type}`
and its POST twin. There is no whole-document route to find.

## What these do not cover

`X-Throttling-Control` and its per-service buckets appear in **neither** the
OpenAPI description nor the schemas. Searching the full API page for `throttl`,
`quota`, `retry-after`, `rate limit` and `fair use` returns nothing. That
material lives in EPO's separate OPS usage documentation, which is not vendored
here. The service each operation bills against is inferred from the documented
path split plus the reference client's prefix mapping — see #379.

## Provenance

Captured 2026-09-10 from the EPO Developer Portal
(`developers.epo.org/apis/ops-v32`) and the OPS schema distribution, using a
maintainer's own developer account. The portal requires a login; the OPS data
service itself does not serve these files (every conventional spec path 404s).

`ops.yaml` self-describes as *"Open API specification of OPS API. Version 1.2
only is supported by Apigee SmartDocs"*, carries `version: "3.2"`, and names its
licence as EPO's *Fair use charter*.

These are **third-party documents reproduced for reference**, not project
output. Do not edit their content. If one disagrees with observed behaviour,
the observation and the schema are both evidence — record the conflict rather
than adjusting the file. Re-capture from the portal to update.

**Not byte-identical to the originals.** The repository's `trailing-whitespace`
and `end-of-file-fixer` hooks normalised whitespace in `ops.yaml`, `ccd.xsd`,
`fulltextdocuments.xsd`, `CPCSchema.xsd` and `CPCDefinitions.xsd` on the way in.
That was verified to be whitespace-only — `diff -w` against the captured
originals is empty for all eight files, and every schema and the specification
parse cleanly. The alternative was either exempting these paths in
template-owned hook configuration, which a `copier update` would silently
revert, or storing an archive nobody can grep. Expect a whitespace diff when
re-capturing; check it with `diff -w` before assuming EPO changed something.

Unlike these, the response captures in `tests/fixtures/epo/` **are** verbatim:
they are compared against parser output, so their bytes carry meaning. They
passed the same hooks untouched.

## Deliberately not included

EPO's *User Documentation 14.11 — Worldwide legal status database (INPADOC) T12
exchange file* (v3.1, 2013), which documents the `L###EP` tag semantics that
`ops_legal.xsd` declares. It is marked `DISTRIBUTION: Exchange Partners` and
describes a subscription raw-data product, and this repository is public, so
including it is a redistribution decision for the maintainer rather than a
default. It remains the best reference for what individual legal-event tags
mean.

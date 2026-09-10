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
| `reference-guide-notes.md` | **Start here.** Cited excerpts from EPO's RESTful Web Services Reference Guide v1.3.20 — the only source that documents *behaviour* rather than *shape*: throttling, quotas, and why the image service works as it does. The 4.8 MB PDF itself is not vendored; the notes say where to get it. |
| `ops.yaml` | The OPS 3.2 OpenAPI (Swagger 2.0) description: every operation, its parameters, and their types. |
| `schemas/ops.xsd` | Response content models — `document-instance`, `document-format-options`, `inquiry-result`, fault shapes, and the `desc` enumeration. |
| `schemas/ops_legal.xsd` | The `L###EP` legal-event element vocabulary. Load-bearing: `EpoClient.get_legal` feeds `parse_legal_xml` (`src/scholar_mcp/_epo_xml.py`). |
| `schemas/fulltextdocuments.xsd` | Description and claims sub-documents returned by the fulltext services. |
| `schemas/ccd.xsd` | Common Citation Document structure. |
| `schemas/rplus.xsd` | Register-plus data. |
| `schemas/CPCSchema.xsd`, `schemas/CPCDefinitions.xsd` | CPC classification scheme and definitions. |
| `cpc/` | CPC International sample data and the 2019 OPS release announcement. |

## Answers worth knowing about

Findings that cost live API calls to establish, each stated plainly in these
files:

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

**Which throttle bucket a request bills against.** Reference guide §2.3.3,
Table 16, *"Mapping between services and throttles"*:

| Throttle | REST service URI |
|---|---|
| `search` | `/published-data/search/*` |
| `retrieval` | `/published-data/*/` |
| `inpadoc` | `/family/*` |
| `inpadoc` | `/legal/*` |
| `images` | `/published-data/images/*` |
| `images` | `/classification/cpc/media/*` |

Everything else bills `other`. The two steps of a patent PDF download bill
**different** buckets: the inquiry at
`/published-data/{type}/{format}/{number}/images` falls under the `retrieval`
catch-all, the page fetch at `/published-data/images/*` bills `images`. Every
`_check_throttle` service assignment in `_epo_client.py` was audited against
this table and matches.

**Why one request per page.** Reference guide §3.1.3, "Full document retrieval":

> In order to provide user with full document, OPS internally must do image
> inquiry and then assemble full document page by page. It's quite resource
> consumptive process and might load OPS significantly. Thus it is not possible
> to get the full document in one request but you can download it page by page.

and *"X-OPS-Range header is obligatory. It may accept only a single number (not
a range)."* The constraint is deliberate, not an accident of the parameter.

## Throttling and quota are two different mechanisms

Easy to conflate; the guide keeps them apart, and so should we.

- **`X-Throttling-Control`** is concurrency self-throttling over a rolling
  60-second window, per service, with a green/yellow/red/black light. Black
  means temporarily suspended and carries `Retry-After` in milliseconds.
- **Quota headers** — `X-IndividualQuotaPerHour-Used`,
  `X-RegisteredQuotaPerWeek-Used`, `X-RegisteredPayingQuotaPerWeek-Used` —
  track the fair-use *data* allowance. Exhausting one yields **`403` with
  `X-Rejection-Reason`**, not a black light and not a 429. The hourly quota
  refreshes on a rolling window, the weekly one at midnight UTC.

Only the traffic light is handled today. See #384.

## What these do not cover

`ops.yaml` and the schemas document *shape*, not *behaviour* — neither mentions
throttling, quotas or fair use. That is why the reference guide is the first
place to look, and why questions answered from the schemas alone kept coming
back inferred.

## Provenance

Captured 2026-09-10 from the EPO Developer Portal
(`developers.epo.org/apis/ops-v32`) and the OPS schema distribution, using a
maintainer's own developer account. The portal
requires a login; the OPS data service itself does not serve these files (every
conventional spec path 404s).

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

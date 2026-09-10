---
type: Reference
title: EPO OPS image inquiry and retrieval
description: How EPO Open Patent Services advertises and serves patent page images, and what that forces on a client that wants a whole document.
subject_version: "OPS 3.2, reference guide v1.3.20"
valid_for: "OPS 3.x"
generated:
  by: process:researching-references
  at: 2026-09-10
stale_after: 2027-09-10
status: stable
verified:
  - by: process:researching-references
    at: 2026-09-10
sources:
  - id: ops-guide
    title: Open Patent Services RESTful Web Services Reference Guide v1.3.20 (June 2024)
    resource: https://developers.epo.org/ops-v3-2/apis
    accessed: 2026-09-10
  - id: ops-xsd
    title: OPS response schema (vendored at sources/epo-ops/ops.xsd)
    resource: ./sources/epo-ops/ops.xsd
    accessed: 2026-09-10
  - id: ops-yaml
    title: OPS 3.2 OpenAPI description (vendored at sources/epo-ops/ops.yaml)
    resource: ./sources/epo-ops/ops.yaml
    accessed: 2026-09-10
---

# EPO OPS image inquiry and retrieval

Two OPS operations stand between a patent number and its PDF: an *inquiry* that
lists what images exist, and a *retrieval* that serves one. This reference
records the shape of the inquiry response and the constraint the retrieval
imposes, because getting either wrong is silent — the client returns a
plausible answer that is not the document.

Both artefacts cited here sit behind a developer-portal login, so the vendored
copies under `sources/epo-ops/` are what the next reader can actually open. The
reference guide itself is not vendored: it is 4.8 MB and the repository's
large-file hook refuses it, so its passages are quoted here instead.

## Scope

- Covers: the inquiry response content model, which instance is the document,
  how a format is advertised, and how many pages one retrieval returns.
- Does not cover: throttling and quota, which decide *whether* a request is
  allowed — see [EPO OPS throttling and fair-use quota](epo-ops-throttling.md).
  Also not covered: the fulltext, family, register, classification and CCD
  services, none of which this project calls for images.
- Depended on by: `src/scholar_mcp/_epo_client.py` (`_parse_pdf_instance`,
  `_page_count_of`, `get_pdf`, `_fetch_pdf_page`, `_merge_pdf_pages`).

## Claims

### The inquiry response

- An images inquiry is `GET /published-data/{type}/{format}/{number}/images`;
  it takes no `Range` and no format selector. [source: ops-yaml]
- The response carries one `ops:document-instance` per available image set,
  each with a required `desc` attribute drawn from the enumeration `Drawing`,
  `FirstPageClipping`, `FullDocument`, `FirstPageImage`, `JapaneseAbstract`,
  `UNKNOWN`. [source: ops-xsd]
- `ops:document-format-options` is a **required** child of
  `ops:document-instance`, and it in turn requires one or more
  `ops:document-format` elements whose text is the MIME type. The MIME type is
  never a `desc` attribute on a direct child; no such attribute exists in the
  schema. [source: ops-xsd] [pins: tests/test_epo_client.py::test_parse_pdf_link_reads_the_shape_epo_actually_sends]
- The guide's own worked example uses that nested form. [source: ops-guide]
- Live responses for `EP3491801B1`, `EP1000000A1`, `WO2019016210A1` and
  `US9634864B2` all use it, and none carries the attribute form.
  [observed: `tests/fixtures/epo/images_inquiry_*.xml`, captured from the live service on 2026-09-10]
- `number-of-pages` is a **required** attribute on `document-instance`, typed
  `xs:nonNegativeInteger`. [source: ops-xsd] [pins: tests/test_epo_client.py::test_parse_pdf_instance_rejects_a_nonsense_page_count]
- Instance order is not fixed: `EP3491801B1` returns `Drawing` before
  `FullDocument`, `WO2019016210A1` the reverse. A client must select on `desc`,
  not on position. [observed: the two captured fixtures above]
- `Drawing` and `FirstPageClipping` instances also advertise `application/pdf`,
  so matching on the format alone yields a thumbnail rather than the document.
  [observed: the same fixtures] [pins: tests/test_epo_client.py::test_parse_pdf_link_ignores_non_fulldocument_instances]

### Retrieval serves one page

- `application/pdf` from the images service *is* a single page — the schema
  documents the REST format enumeration as "application/pdf: A single page of
  the document in PDF format", and the older SOAP enumeration names the same
  value `SINGLE_PAGE_PDF`. [source: ops-xsd]
- Whole-document retrieval is deliberately not offered: "In order to provide
  user with full document, OPS internally must do image inquiry and then
  assemble full document page by page. It's quite resource consumptive process
  and might load OPS significantly. Thus it is not possible to get the full
  document in one request but you can download it page by page."
  [source: ops-guide] [pins: tests/test_epo_client.py::test_get_pdf_fetches_every_page_and_merges]
- The page selector is obligatory and singular: "X-OPS-Range header is
  obligatory. It may accept only a single number (not a range)." The OpenAPI
  description types the equivalent `Range` query parameter as a **required
  integer** described as "Page number". [source: ops-guide] [source: ops-yaml]
- Omitting it is an error, not a whole document: the request returns
  `404 SERVER.EntityNotFound`. A hyphenated value is not a range — `Range=1-5`
  returns bytes identical to `Range=5`, and `Range=all` is a `400`.
  [observed: four URL forms against the live images service for `EP3491801B1` on 2026-09-10, page counts measured with pypdf]
- The API exposes exactly one image-retrieval operation,
  `/published-data/images/{image-country}/{image-number}/{image-kind}/{image-type}`,
  plus its POST twin. There is no alternative route to look for.
  [source: ops-yaml]
- `X-OPS-Range` as an HTTP header and `Range` as a query parameter are
  equivalent. [source: ops-guide]
- An extension selects the format without an `Accept` header
  (`.../fullimage.pdf?Range=1`), and `firstpage.jpeg` returns an image no wider
  than 320 px. [source: ops-guide]

## Where this project departs from the subject

Nowhere deliberately. `get_pdf` does the page-by-page assembly EPO declines to
do, which is what the guide instructs, and merges with `pypdf`. A 21-page
patent costs 21 requests and about 19 seconds.
[observed: full fetch of `EP3491801B1` against the live service on 2026-09-10, merged to a valid 21-page 1,163,861-byte PDF]

## Not covered

- Whether OPS ever violates its own schema by omitting `number-of-pages`.
  `_page_count_of` handles the absence defensively and logs it; the schema says
  it cannot happen. Settling it would need a survey far wider than four
  patents, so the defensive branch stays. [unverified]
- What `FirstPageImage` and `JapaneseAbstract` instances contain. Both are in
  the schema's enumeration; neither appeared in any response observed. Would be
  settled by finding a patent that advertises one. [unverified]
- Whether the `link` attribute's shape is stable. The guide's examples omit the
  `published-data/images/` prefix that live responses include, so the safe rule
  is to use the `link` from the response rather than construct one; that is what
  this project does. [source: ops-guide]

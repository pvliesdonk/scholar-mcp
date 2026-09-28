---
type: Reference
title: PDF file header behaviour
description: The required PDF 1.7 file header and the role of the HTTP Content-Type field.
subject_version: "PDF 1.7 (ISO 32000-1:2008) and HTTP Semantics"
valid_for: "PDF 1.7 files and HTTP Content-Type semantics in RFC 9110"
generated:
  by: process:researching-references
  at: 2026-09-25
stale_after: 2027-09-25
status: stable
sources:
  - id: pdf-32000
    title: PDF 32000-1:2008, section 7.5.2, Adobe-hosted copy of ISO 32000-1
    resource: https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf
    accessed: 2026-09-25
  - id: rfc-9110-content-type
    title: RFC 9110, section 8.3, Content-Type
    resource: https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3
    accessed: 2026-09-25
---

# PDF file header behaviour

## Scope

- Covers: the leading header bytes used to recognize a downloaded PDF and the
  HTTP metadata that describes a response's media type.
- Does not cover: full PDF parsing, cross-reference validation, encryption,
  or whether a document can be converted successfully.
- Depended on by: `src/scholar_mcp/_tools_pdf.py` and
  `docs/design/pdf-downloads.md`.

## Claims

### PDF header

- PDF 1.7 requires the first line of a PDF file to begin with the five bytes
  `%PDF-`, followed by a version number.
  [source: pdf-32000]
  [pins: tests/test_tools_pdf.py::test_fetch_pdf_by_url_rejects_non_pdf_before_conversion,
  tests/test_tools_pdf.py::test_fetch_pdf_by_url_accepts_pdf_header_when_content_type_is_html]
- Checking those leading bytes distinguishes an HTML response from a PDF
  download, but does not establish that later objects, cross-reference data,
  or the trailer are valid. [source: pdf-32000]

### HTTP media type

- `Content-Type` identifies the media type of the representation carried in a
  message. The download code checks the response bytes independently, so a
  mislabeled header does not by itself reject a PDF or admit an HTML body.
  [source: rfc-9110-content-type]

## Where this project departs from the subject

Nowhere deliberately. Download acceptance uses the required `%PDF-` prefix as
a small content check; it is not represented as full PDF validation.

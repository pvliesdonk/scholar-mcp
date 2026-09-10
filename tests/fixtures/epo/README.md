# EPO OPS image-inquiry fixtures

`images_inquiry_*.xml` are **verbatim** responses from the EPO OPS
`published_data('publication', ..., endpoint='images')` endpoint, captured on
2026-09-10 against live credentials while fixing #371.

They are here because the hand-written fixtures they replaced did not match
what EPO returns: they put the MIME type in a `desc` attribute on a direct
child of `ops:document-instance`, where EPO nests
`ops:document-format-options/ops:document-format` and carries the MIME type as
element *text*. The parser was written against those fixtures, so the tests
passed while `fetch_patent_pdf` reported `pdf_not_available` for every patent.

**Do not edit these to make a test pass.** They are the ground truth. If a
test disagrees with them, the test or the code is wrong. Re-capture with a
live call rather than adjusting the bytes by hand.

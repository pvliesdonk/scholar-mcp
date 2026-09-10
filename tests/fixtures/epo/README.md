# EPO OPS response fixtures

Responses captured from EPO OPS against live credentials on 2026-09-10:

| File | Endpoint | Captured for |
| --- | --- | --- |
| `images_inquiry_*.xml` | `published_data(..., endpoint='images')` | #371 |
| `legal_ep1000000a1.xml` | `legal('publication', ...)` | #388, #390 |

The behaviour they evidence is written up under `docs/design/reference/`.

The image fixtures are here because the hand-written ones they replaced did not
match what EPO returns: they put the MIME type in a `desc` attribute on a direct
child of `ops:document-instance`, where EPO nests
`ops:document-format-options/ops:document-format` and carries the MIME type as
element *text*. The parser was written against those fixtures, so the tests
passed while `fetch_patent_pdf` reported `pdf_not_available` for every patent.

`legal_ep1000000a1.xml` is here for the same reason and the same bug class:
`parse_legal_xml` matches an `ops:legal-event` element OPS never sends, and
returns zero events from the fifty this file contains (#390).

**One byte differs from what EPO sent:** each file ends with a trailing
newline the payload does not have (2183 / 3012 / 76124 bytes here against
2182 / 3011 / 76123 on the wire). Two were written that way; the third was
normalised by the repository's `end-of-file-fixer` hook, which cannot be
exempted without template-owned config that a `copier update` reverts. The
XML payload above that newline is unmodified, and every parser this project
uses ignores trailing whitespace after the root element. Compare with
`diff -w`, or against `head -c -1`, before concluding EPO changed something.

**Do not edit these to make a test pass.** They are the ground truth. If a
test disagrees with them, the test or the code is wrong. Re-capture with a
live call rather than adjusting the bytes by hand.

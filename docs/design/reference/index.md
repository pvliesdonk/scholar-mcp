---
okf_version: "0.2"
type: Index
title: External behaviour references
description: How things outside this repository behave, with the evidence.
---

# External behaviour references

An [Open Knowledge Format](https://github.com/pvliesdonk/claude-plugins/tree/main/plugins/open-knowledge-format)
v0.2 bundle. Each page records how something **outside** this repository
behaves, with a marker on every claim saying how it is known and a `[pins: ...]`
link to the test that asserts this project honours it.

`docs/design/` says what this project does and why. These pages say what the
world does. Read the relevant one before changing code that talks to it — the
`researching-references` skill explains when to write or refresh a page.

## Pages

| Page | Subject | Depended on by |
| --- | --- | --- |
| [EPO OPS image inquiry and retrieval](epo-ops-images.md) | How OPS advertises and serves patent page images | `_epo_client.py`: `_parse_pdf_instance`, `get_pdf`, `_fetch_pdf_page` |
| [EPO OPS throttling and fair-use quota](epo-ops-throttling.md) | The two independent limits OPS applies, and which path bills which bucket | `_epo_client.py`: `_check_throttle`, `_is_service_throttled`, every `service=` argument |
| [EPO OPS legal-status events](epo-ops-legal-events.md) | How OPS represents INPADOC legal events, and why they need no code dictionary | `_epo_xml.py`: `parse_legal_xml`; `_epo_client.py`: `get_legal` |

## Vendored sources

`sources/epo-ops/` holds the EPO artefacts the pages cite. Obtain fresh copies
from <https://www.epo.org/en/searching-for-patents/data/web-services/ops>, which
is also where the reference guide is downloaded. They are vendored rather than
linked because the portal gates them behind a login, and a URL alone would not
let the next reader check a claim.

No EPO document carrying a restricted-distribution marking is reproduced here,
in whole or in part. Where one would have been the obvious source, the pages say
so and cite what is public instead. Only the ones this project's code depends on are
kept — the register, CCD and CPC schemas are not, and neither is the reference
guide PDF, which at 4.8 MB the repository's large-file hook refuses. Its
passages are quoted in the pages instead.

## Known gaps

- **Semantic Scholar and Google Books** have no page yet, though the same class
  of undocumented behaviour sat behind #365, #366, #368 and #369. Tracked in
  #389.

**Whitespace in the vendored files was normalised** by the repository's
`trailing-whitespace` and `end-of-file-fixer` hooks. Verified whitespace-only:
`diff -w` against the captures is empty, and each file parses. Expect a
whitespace diff when re-capturing, and check it with `diff -w` before concluding
EPO changed something.

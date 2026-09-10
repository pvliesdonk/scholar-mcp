# Research log

Newest first. One entry per research pass.

## 2026-09-10

First pass. Subject: EPO Open Patent Services 3.2, prompted by four patent bugs
that each turned on undocumented-to-us behaviour — #371, #379, #384, and the
throttle-bucket question inside #381.

**Framed from the code**, not from memory: every assumption in
`_epo_client.py`'s image path and throttle handling, plus the open questions
already recorded on those issues.

**Primary sources swept:** the OPS response schema (`ops.xsd`), the OPS 3.2
OpenAPI description (`ops.yaml`), and the RESTful Web Services Reference Guide
v1.3.20. The reference client `python-epo-ops-client` was consulted while the
guide was still out of reach; its URL-prefix classifier agrees with the guide's
Table 16, but it is a secondary source and no claim here cites it.

**Observed where documentation was silent:** live inquiry and retrieval calls
for `EP3491801B1`, `EP1000000A1`, `WO2019016210A1` and `US9634864B2`; four URL
forms probed for a whole-document route; a full 21-page fetch measured and
merged. Two verbatim responses are checked in under `tests/fixtures/epo/`.

**Refuted:** the reading that §3.1.3's "images is the new name for document
(inquiry or retrieval) service" puts the inquiry in the `images` bucket. Table
16 contradicts it; the sentence names a documentation section. Recorded in the
throttling page as a trap rather than dropped, because the wrong reading is the
natural one.

**Completeness gaps** are written as `[unverified]` claims on both pages rather
than left implicit: whether OPS ever omits a required `number-of-pages`, what
`FirstPageImage` and `JapaneseAbstract` instances contain, which
`X-Rejection-Reason` values exist, and whether quota headers arrive early enough
to warn an operator.

**Found while writing:** fair-use quota exhaustion is a `403` with
`X-Rejection-Reason`, a mechanism this codebase does not recognise at all.
Filed as #384. No probe would have surfaced it without exhausting a shared
allowance.

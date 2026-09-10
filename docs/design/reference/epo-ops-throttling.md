---
type: Reference
title: EPO OPS throttling and fair-use quota
description: The two independent limits OPS applies, how each is signalled, and which throttle bucket a given REST path bills against.
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
  - id: ops-yaml
    title: OPS 3.2 OpenAPI description (vendored at sources/epo-ops/ops.yaml)
    resource: ./sources/epo-ops/ops.yaml
    accessed: 2026-09-10
---

# EPO OPS throttling and fair-use quota

OPS applies **two independent limits**, and conflating them is the mistake this
page exists to prevent: a concurrency traffic light that says *slow down*, and a
data quota that says *come back later*. They are signalled by different headers,
recover on different clocks, and one of them is not handled by this project at
all.

## Scope

- Covers: the `X-Throttling-Control` traffic light, the path-to-bucket mapping,
  the fair-use quota headers, and how each limit is signalled when reached.
- Does not cover: what any individual request returns, or the images content
  model — see [EPO OPS image inquiry and retrieval](epo-ops-images.md).
- Depended on by: `src/scholar_mcp/_epo_client.py` (`_parse_throttle_header`,
  `_check_throttle`, `_is_service_throttled`, `_throttle_color`, and every
  `service=` argument).

## Claims

### The traffic light

- Every OPS response carries `X-Throttling-Control`, shaped
  `system-state (service-name=traffic-light-position:request-limit, ...)`, and
  it is specific to the requesting user system.
  [source: ops-guide] [pins: tests/test_epo_client.py::test_parse_throttle_header_full]
- The system state is one of `idle`, `busy`, `overloaded`, reflecting concurrent
  usage across all users. [source: ops-guide]
- A service's light is `green` (under 50% of the permitted request limit used),
  `yellow` (50–75%), `red` (over 75%), or `black` (limit exceeded, service
  temporarily suspended).
  [source: ops-guide] [pins: tests/test_epo_client.py::test_parse_throttle_header_all_colors]
- The number after the colour is the **request limit**, not the remaining
  count, measured over a rolling 60-second window. [source: ops-guide]
- The limit shrinks as the system state degrades, so the same `green` means a
  smaller allowance under load: `retrieval=green:200` when idle,
  `green:100` when busy, `green:50` when overloaded. [source: ops-guide]
- On `black`, a `Retry-After` header gives the remaining suspension time in
  milliseconds. [source: ops-guide]
- OPS instances do not share state — "At present the EPO has not implemented
  communication between OPS instances" — so headers from consecutive requests
  can disagree, and the guide directs clients to moderate "according to the
  most negative response data received". [source: ops-guide]

### Which bucket a path bills

Reference guide §2.3.3, Table 16, *"Mapping between services and throttles"*:

| Throttle | REST service URI |
| --- | --- |
| `search` | `/published-data/search/*` |
| `retrieval` | `/published-data/*/` |
| `inpadoc` | `/family/*` |
| `inpadoc` | `/legal/*` |
| `images` | `/published-data/images/*` |
| `images` | `/classification/cpc/media/*` |

- Anything not listed bills `other`. [source: ops-guide]
- The two steps of a patent PDF download therefore bill **different** buckets:
  the inquiry at `/published-data/{type}/{format}/{number}/images` matches the
  `retrieval` catch-all, while the page fetch at `/published-data/images/*`
  bills `images`.
  [source: ops-guide] [pins: tests/test_epo_client.py::test_get_pdf_second_throttle_check_raises]
- Legal-status retrieval bills `inpadoc`, not `retrieval`, because it is served
  from `/legal/*`.
  [source: ops-guide] [pins: tests/test_epo_client.py::test_preflight_inpadoc_blocks_get_legal]
- A sentence in §3.1.3 misleads on this point: "in OPS RESTful services,
  'images' is the new name for 'document (inquiry or retrieval) service' as used
  in former versions of OPS." That names the documentation section, not the
  bucket; read alone it wrongly implies the inquiry bills `images`. Table 16
  governs. [source: ops-guide]

### Quota is a separate mechanism

- Fair use is tracked by `X-IndividualQuotaPerHour-Used`,
  `X-RegisteredQuotaPerWeek-Used` and `X-RegisteredPayingQuotaPerWeek-Used`,
  returned with relevant requests. [source: ops-guide]
- The global rule is 1 Mbps, "enforced as an hourly quota equal to approx 450MB
  per hour". [source: ops-guide]
- Exhausting a quota yields **`403 Forbidden` with an `X-Rejection-Reason`
  header** naming which quota (for example `RegisteredQuotaPerWeek`), and an
  XML `<error>` body — not a black traffic light, and not a `429`.
  [source: ops-guide]
- Hourly quota refreshes on a rolling one-hour window; weekly quota is released
  each calendar week at midnight UTC. [source: ops-guide]

## Where this project departs from the subject

- **The `Retry-After` on a black light is ignored.** `EpoQuotaExhaustedError`
  is raised without reading the remaining suspension time, so a caller cannot
  know when to return. Tracked with the quota gap below.
- **Fair-use `403` is not recognised at all**, so quota exhaustion reaches the
  caller as an unspecified upstream failure rather than as "the allowance is
  spent". Tracked in #384.

## Not covered

- Which quota a given response's headers refer to when several are present, and
  whether they appear on successful responses often enough to warn an operator
  before the allowance runs out. Settling it would mean observing a deployment
  close to its limit. [unverified]
- Whether `X-Rejection-Reason` takes values beyond the guide's
  `RegisteredQuotaPerWeek` example — the other two quota headers imply at least
  `IndividualQuotaPerHour` and `RegisteredPayingQuotaPerWeek`, but the guide
  does not enumerate them. Settling it needs either an enumeration from EPO or
  an observation. [unverified]
- The behaviour of the `other` bucket's limits, which this project never
  approaches. Deliberately out of scope.

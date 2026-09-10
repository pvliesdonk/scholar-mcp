# OPS reference guide — the passages that matter

Verbatim excerpts from EPO's *Open Patent Services RESTful Web Services
Reference Guide*, v1.3.20 (June 2024), marked *"Non-confidential © 2024
European Patent Office"*. Obtain the full 154-page PDF from the EPO Developer
Portal; it is not vendored here because it is 4.8 MB and git history is forever.

**Why excerpts and not the file:** the guide is the only EPO artefact that
documents *behaviour* rather than *shape*, and four passages carry nearly all of
that value for this project. Excerpts are also greppable and diffable, which a
PDF is not.

Quotes are exact. Section and page numbers are from v1.3.20 — check them against
your copy before trusting a citation, since EPO renumbers between revisions.

## §2.3.3, p. 43 — Table 16, "Mapping between services and throttles"

| Throttle | Rest service URI |
|---|---|
| `search` | `/published-data/search/*` |
| `retrieval` | `/published-data/*/` |
| `inpadoc` | `/family/*` |
| `inpadoc` | `/legal/*` |
| `images` | `/published-data/images/*` |
| `images` | `/classification/cpc/media/*` |

> All other OPS services not included in the list above have throttle "other".

This is the authority for every `service=` argument in `_epo_client.py`. The two
steps of a patent PDF download bill **different** buckets: the inquiry at
`/published-data/{type}/{format}/{number}/images` matches the `retrieval`
catch-all, the page fetch at `/published-data/images/*` bills `images`.

**A sentence that misleads.** §3.1.3 opens:

> Note, in OPS RESTful services, "images" is the new name for "document (inquiry
> or retrieval) service" as used in former versions of OPS.

That is about what the *documentation section* is called, not about throttle
buckets. Read alone it suggests the inquiry bills `images`. Table 16 governs.

## §2.3.3, p. 42 — traffic-light semantics

> The traffic light indicator for any single service can be in one of 4
> positions:
>
> - Green – less than 50% of the permitted request limit has been used
> - Yellow – between 50% and 75% of the request limit has been used
> - Red – more than 75% of the request limit has been reached
> - Black – the limit has been exceeded and service has been temporarily
>   suspended

Header shape:

```
X-Throttling-Control: system-state (service-name=traffic-light-position:request-limit, ...)
X-Throttling-Control: idle (retrieval=green:200, search=yellow:20, inpadoc=red:30, images=green:200, other=green:1000)
```

System state is `idle`, `busy` or `overloaded`, and **the limits shrink as it
degrades** — the same green light means a smaller allowance under load. Values
are measured over a rolling 60-second window.

On black, a `Retry-After` appears giving the remaining suspension in
milliseconds. This project does not read it yet.

Instances do not share state:

> At present the EPO has not implemented communication between OPS instances.

So headers from different requests can disagree. The guide's instruction:

> you should moderate your usage of the service over a 60 second window,
> according to the **most negative** response data received.

## §2.3.3, pp. 40-41 — quota is not throttling

A separate mechanism, easily conflated with the traffic light.

Headers: `X-IndividualQuotaPerHour-Used`, `X-RegisteredQuotaPerWeek-Used`,
`X-RegisteredPayingQuotaPerWeek-Used`, and `X-Rejection-Reason` once exhausted.

> - A global 1Mbps (megabit per second) rule for all users. This is enforced as
>   an hourly quota equal to approx 450MB per hour.

Exhaustion is **a 403, not a black light and not a 429**:

```
HTTP/1.1 403 Forbidden
X-Rejection-Reason: RegisteredQuotaPerWeek

<error>
  <code>403</code>
  <message>This request has been rejected due to the violation of Fair Use policy</message>
</error>
```

> Hourly quotas will be fully refreshed within 1 hour on a rolling window basis
> ... Weekly quota will be released each calendar week at midnight UTC/GMT.

Unhandled here — see #384.

## §3.1.3, p. 72 — "Full document retrieval"

> Note: In order to provide user with full document, OPS internally must do
> image inquiry and then assemble full document page by page. It's quite
> resource consumptive process and might load OPS significantly. Thus it is not
> possible to get the full document in one request but you can download it page
> by page. To do this, use the X-OPS-Range HTTP header or Range query parameter
> to indicate the page you want to retrieve.

> X-OPS-Range header is obligatory. It may accept only a single number (not a
> range). The resulting document consists of a single page (or single image)
> with a given number as counted in a full document with all pages.

The one-request-per-page cost in `get_pdf` is the documented contract, with
EPO's reason attached: they decline to do the assembly, so the client does
(#379). `X-OPS-Range` is an accepted alternative to the `Range` query parameter;
this project uses the query parameter, via `epo_ops`.

Also documented there: an extension works instead of an `Accept` header
(`.../fullimage.pdf?Range=1`), and `firstpage.jpeg` returns an image no wider
than 320px.

## §3.1.3, pp. 68-69 — the inquiry response shape

The guide's own example uses the nested form, a third confirmation alongside
`schemas/ops.xsd` and the captures in `tests/fixtures/epo/`:

```xml
<ops:document-instance system="ops.epo.org"
    link="EP/1000000/A1/fullimage" number-of-pages="12" desc="FullDocument">
  <ops:document-format-options>
    <ops:document-format>application/pdf</ops:document-format>
    <ops:document-format>application/tiff</ops:document-format>
  </ops:document-format-options>
  <ops:document-section name="ABSTRACT" start-page="1"/>
```

Note the guide's `link` values omit the `published-data/images/` prefix that
live responses include. Use the `link` attribute from the response you actually
received rather than the guide's shorter form.

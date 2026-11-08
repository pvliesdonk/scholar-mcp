# PDF download validation

PDFs fetched by `fetch_pdf_by_url` and the shared paper download path used by
`fetch_paper_pdf` and `fetch_and_convert` are checked for the `%PDF-` header
before they are written to the cache or passed to docling.

Cache hits use the same header check and confirm that the path still names the
file that was inspected. An invalid or concurrently replaced cache entry is
not reused, and the request attempts a fresh download. A verified download is
published through a temporary file and atomic replace, so another call does
not observe partial bytes. A non-PDF response returns `not_pdf`; HTTP failures
remain `download_failed`.

The paper download path tries candidate URLs in order: the Semantic Scholar
`openAccessPdf` URL, then ArXiv, PubMed Central and Unpaywall
(`_pdf_url_resolver.iter_alternative_pdfs`). A `not_pdf` or `download_failed`
outcome moves on to the next candidate instead of ending the request, because
S2 often lists a publisher landing page (a `doi.org` link, for example) as the
open-access URL. Candidates are resolved lazily, so Unpaywall is queried only
after the sources before it failed, and a URL already tried is skipped. When
every candidate fails, the payload keeps the last attempt's `error`, `detail`
and `pdf_source` for existing callers and adds `attempts`, one record per
source, so a caller can tell "no source known" (`no_oa_pdf`) from "every known
source failed". The cache check runs once, before the first download (#568).

The `Content-Type` response header is not used as proof of file contents. The
prefix check follows PDF 1.7's required header but is not a complete structural
or integrity validation; conversion remains responsible for detecting later
PDF parsing failures. See [PDF file header behaviour](reference/pdf-file-header.md).

## Destination check

`fetch_pdf_by_url` takes its URL from the caller, so it refuses destinations
that are not public internet addresses (#514). `_url_guard.check_public_url`
accepts only `http` and `https` URLs. It resolves the host and refuses the
URL unless every address is a global unicast address. IPv4-mapped IPv6
addresses and NAT64 addresses (`64:ff9b::/96`) are judged by the IPv4
address they carry; 6to4 (`2002::/16`) is already not global. A host with one public
and one private address is refused, because the connection may use either.
Redirects are followed one hop at a time (`get_public`, at most 10 hops), and
each hop is checked before it is requested. A refusal is a `ToolError` at
INFO naming the refused URL or redirect: the caller has to pass another URL.
A host that does not resolve stays `download_failed`.

The check runs before the request, not at connect time, so DNS rebinding (an
answer that changes between the check and the connection) is not caught.
Pinning the checked address at connect time would mean connecting without
the configured HTTP proxy, which egress-restricted deployments need. The
residual risk is stated in the security model. The check also needs the
server to resolve host names itself. A deployment that reaches the internet
only through a proxy and has no DNS of its own gets `download_failed` for
every URL, because the check fails closed; it needs the opt-out below.

The paper download path (`fetch_paper_pdf`, `fetch_and_convert`) runs the
same check on every candidate URL and its redirects (#573). Its URLs come
from Semantic Scholar, arXiv, PubMed Central and Unpaywall metadata rather
than from the caller, but a hostile or compromised record, or a redirect on
a host it points at, could still lead to the server's own network. A refused
candidate is not a `ToolError`, since the caller did not choose it: it
becomes a `download_failed` attempt whose `detail` names the refused URL,
it is logged as `pdf_candidate_blocked` at INFO, and the next candidate is
tried.

`SCHOLAR_MCP_PDF_FETCH_ALLOW_PRIVATE=true` skips the check on both paths and
restores the earlier behaviour, for operators who fetch from an intranet
repository. The default is to check, because the tools' caller is a model
acting on prompts the operator does not see.

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

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

The `Content-Type` response header is not used as proof of file contents. The
prefix check follows PDF 1.7's required header but is not a complete structural
or integrity validation; conversion remains responsible for detecting later
PDF parsing failures. See [PDF file header behaviour](reference/pdf-file-header.md).

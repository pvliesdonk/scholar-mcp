# Converted document response windows

Converted documents remain whole in the server cache. MCP tools expose a
window of that text so response size does not grow with document length.

`convert_pdf_to_markdown`, `fetch_and_convert`, `fetch_pdf_by_url`,
`fetch_patent_pdf`, and `get_standard` share the `_text_window.page_text()`
contract. The default page is 20,000 characters. Integer page sizes are
clamped to that ceiling, while `max_chars=null` explicitly requests the
complete remaining text for clients that can accept it.

The original content field stays stable: `markdown` for PDF and patent tools,
and `full_text` for standards. Every response containing one of those fields
also carries:

- `text_offset`: the page's starting character;
- `text_returned_chars`: characters in this page;
- `text_total_chars`: characters in the complete cached document;
- `text_truncated`: whether the response omits any document text;
- `next_offset`: the next page's starting character, present only when more
  text follows.

Paging repeats the tool call with `text_offset=next_offset`. Each tool reads
the already converted Markdown or cached standard record, so another page
does not repeat conversion. Error and metadata-only responses contain no text
pagination fields.

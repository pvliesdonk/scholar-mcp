---
description: "Which extra sources scholar-mcp consults to fill in paper and book records, and what each adds."
kind: explanation
---

# Automatic enrichment

Paper and book results are filled in from more sources than the one that answered the call. Enrichment runs in two phases:

- **Phase 0** (primary): OpenAlex (open-access status, affiliations, funders, concepts) and CrossRef (publisher, page ranges, container titles).
- **Phase 1** (secondary): from Open Library (book metadata for papers with an ISBN) and Google Books (preview links, excerpts, snippets).

## Books cited as papers

When `get_paper`, `get_citations`, `get_references` or `get_citation_graph` returns a paper whose `externalIds.ISBN` is present and not empty, Open Library metadata is fetched and attached to the record as `book_metadata`:

| Field | Description |
|---|---|
| `publisher` | Publisher name |
| `edition` | Edition string (such as `"2nd ed."`) |
| `isbn_13` | ISBN-13 |
| `cover_url` | Cover image URL (from Open Library covers) |
| `openlibrary_work_id` | Open Library work ID (such as `OL17953442W`) |
| `description` | Work description, if available |
| `subjects` | List of subject strings |
| `page_count` | Page count, if known |
| `authors` | List of author names, resolved from Open Library work metadata |

## Other sources

CrossRef adds publisher metadata, page ranges and container titles to a paper result that has a DOI. Google Books adds `google_books_url` and `snippet` to a book record that has an ISBN.

## An OpenAlex API key

OpenAlex answers without a key, at 10 requests a second and a small daily budget. A free key raises both: 30 requests a second and a budget ten times larger. The lookups scholar-mcp makes, one work by DOI, are free of charge under either.

To use a key:

1. Create an account at [openalex.org/signup](https://openalex.org/signup).
2. Copy the key from [openalex.org/settings/api-key](https://openalex.org/settings/api-key).
3. Click the activation link OpenAlex emails you. Until then OpenAlex refuses every request made with the key.
4. Set `SCHOLAR_MCP_OPENALEX_API_KEY` to the key and restart the server.

scholar-mcp sends the key to OpenAlex only, in an `Authorization` header, so it never appears in a URL or a request log.

## When a source doesn't answer

Enrichment is best effort. If a source is unreachable or has no data, the record comes back without that layer. At most 10 enrichment requests run at once in each phase.

An OpenAlex refusal is never reported as a missing DOI. When OpenAlex throttles a lookup, `enrich_paper` and the DOI fallback in `batch_resolve` answer `rate_limited` with `retryable: true`. When it rejects the key, they answer `openalex_unavailable` with `retryable: false`, and the server logs `openalex_key_rejected` at ERROR for the operator. The usual cause is a key that is not yet activated, or one that was revoked.

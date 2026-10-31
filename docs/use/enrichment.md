---
description: "Which extra sources scholar-mcp consults to fill in paper and book records, and what each adds."
kind: explanation
---

# Automatic enrichment

Paper and book results are filled in from more sources than the one that answered the call. Enrichment runs in two phases:

- **Phase 0** (primary): OpenAlex (open-access status, affiliations, funders, concepts) and CrossRef (publisher, page ranges, container titles).
- **Phase 1** (secondary): Open Library (book metadata for papers with an ISBN) and Google Books (preview links, excerpts, snippets).

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

## When a source doesn't answer

Enrichment is best effort. If a source is unreachable or has no data, the record comes back without that layer. At most 10 enrichment requests run at once in each phase.

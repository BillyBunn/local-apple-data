# v1.27 Apple Books Metadata And Annotations

## Goal

Add a read-only Apple Books surface for locally synced Books library metadata and selected-book annotations without extracting book/chapter text, opening Books.app, fetching iCloud-only content, or mutating the library.

## Approved Surface

- CLI: `local-apple-data books search`
- CLI: `local-apple-data books get`
- CLI: `local-apple-data books annotations`
- MCP: `books_search`
- MCP: `books_get`
- MCP: `books_list_annotations`

Search reads local Apple Books metadata from `BKLibrary` and returns bounded title, author, genre, kind, progress, finished status, download status, annotation count, and opaque `books:book:v1:` handles.

Exact get returns the same selected-book metadata by opaque handle.

Annotations returns bounded highlight/note text only for one selected book handle. It may return opaque annotation handles for future exact-annotation workflows, but it does not expose raw annotation UUIDs.

## Privacy Boundary

Allowed:

- Specific title, author, or genre searches.
- Exact selected-book metadata by `books:book:v1:` handle.
- Bounded selected-book annotation text by exact book handle.
- Schema-only health checks for `ZBKLIBRARYASSET` and `ZAEANNOTATION`.

Blocked:

- Broad book-library dumps.
- Broad annotation dumps or annotation text search.
- Book/chapter/PDF/EPUB text extraction.
- Raw Apple Books asset IDs, annotation UUIDs, local file paths, store/account IDs, or database rows.
- iCloud-only book fetches or network access.
- Opening Books.app to force sync.
- Collections, series, reading sessions, or recommendations as first-tranche surfaces.
- Any Apple Books mutation.

## Verification

- Synthetic adapter tests cover search, exact book get, annotation listing, invalid handles, broad-query rejection, truncation, schema checks, and raw identifier/path redaction.
- CLI tests cover `books search`, `books get`, and `books annotations`.
- MCP list tests include `books_search`, `books_get`, and `books_list_annotations` as read-only tools.
- Runtime smoke builds synthetic Books SQLite stores and verifies opaque handles, metadata-only search, exact annotations, invalid-handle rejection, and no raw identifier leakage.
- Surface-contract, release-readiness, public-release, and redaction scans must pass before publication.

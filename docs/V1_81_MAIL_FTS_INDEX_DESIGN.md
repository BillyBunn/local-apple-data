# V1.81 Mail FTS Index Design

Status: Source read/cache-capable implementation.

This document approves an opt-in local Mail FTS index for bounded audit discovery. It writes a private local SQLite FTS5 cache, but it does not mutate Apple Mail data and does not approve background indexing, unbounded search, broad exports, Mail account/mailbox management, permanent delete, empty Trash/Junk, templates/signatures, query-result auto-apply, or any new Mail.app write verb. Later gates add outbound exact sender selection, signature/template/query-result planning, and synthetic-only mailbox/cleanup surfaces without changing this FTS gate.

## Approved Tools

- CLI build: `local-apple-data mail fts-build`
- CLI search: `local-apple-data mail fts-search`
- MCP build: `mail_build_fts_index`
- MCP search: `mail_search_fts`

## Privacy Contract

- `fts-build` requires at least one `after` or `before` date bound.
- `fts-build` requires `confirm_index=true` / `--confirm-index` because it writes a durable private cache that may contain extracted Mail subject/header/body text and optional attachment text.
- `fts-build` paginates with `cursor` / `next_cursor`; each build indexes at most the capped build page and returns `mail_fts_build_truncated` when more bounded rows remain.
- `reset` is valid only on the first build page. Continuation builds with a non-zero `cursor` must continue without `reset`; `reset` plus a continuation cursor is rejected before touching the index so prior pages are not deleted.
- The build cursor is an offset through the current bounded Mail query, not a durable Mail snapshot. If Mail changes during a multi-page build, rerun from `reset` for deterministic audit coverage.
- The default cache path is local private state; callers may override it for tests, but symlink and non-regular index, ancestor, or sidecar paths are refused and tool output never returns the path.
- Reset validates the index target, removes the private index plus WAL/SHM/journal sidecars, and rebuilds the schema from scratch so removed indexed text is not left in ordinary SQLite free pages or sidecar files. Schema-migration cleanup also uses SQLite secure-delete plus vacuum before recreating the schema.
- The cache output returns only `index_ref`, counts, booleans, `next_cursor`, and safe warning codes.
- `fts-search` also requires at least one date bound and a query that passes the minimum quality guard.
- `fts-search` supports `subject`, `from`, `to`, `cc`, `bcc`, `body`, `attachment_filename`, and `attachment_content` scopes.
- Search opens only an existing index with SQLite read-only mode. It must not create, migrate, reset, or write the index.
- Search results are revalidated against the current live Mail Envelope Index before handles are returned; deleted rows, current date-bound drift, or stale rows are skipped.
- Search stores and compares a per-message local content state hash. Rows whose local `.emlx` content changed or disappeared after indexing are skipped with `mail_fts_stale_content`.
- Search results return exact `mail:message:v2:` handles, safe metadata, matched scopes, and capped redacted snippets only.
- Snippet redaction covers email addresses, local path-like strings, raw-ID-like fields, UUID/long-hex identifiers, and common phone-number shapes.
- Output returns no full body, attachment bytes, raw MIME, full headers, full email addresses, raw account identifiers, raw row IDs, local `.emlx` paths, local attachment source paths, temporary paths, cache paths, or credentials.
- `include_attachments` indexes attachment filename/MIME metadata and bounded text/PDF content; `include_ocr` is honored only with `include_attachments`. Attachment count, safe filenames, and MIME types are stored and returned as separate metadata fields so MIME strings are not misreported as filenames.
- PDF text extraction uses local `pdftotext` when available. PDF OCR fallback uses local `ocrmypdf` only when explicitly requested. OCR attempts are capped per build.
- The build tool is annotated as a write tool only because it writes this private cache; it does not apply any Apple-data mutation and is separately allowlisted by the mutation-gate audit as a local cache write.

## Explicit Non-Goals

- No background indexing.
- No unbounded Mail search.
- No broad private-content dump.
- No query-result auto-apply. Later v1.83 query-result triage is preview-to-exact-plan only.
- No attachment bytes or broad attachment export.
- No real/non-synthetic permanent delete, empty Trash/Junk, mailbox/account management, templates/signatures, or HTML/rich-text mutation from this gate. Outbound exact sender selection later landed under `docs/V1_82_MAIL_OUTBOUND_SENDER_SELECTION_WRITE_DESIGN.md`; signatures/templates/query-result planning later landed under `docs/V1_83_MAIL_SIGNATURE_TEMPLATE_QUERY_TRIAGE_DESIGN.md`; synthetic `LAD-TEST-*` mailbox/cleanup later landed under `docs/V1_84_MAIL_SYNTHETIC_MAILBOX_CLEANUP_WRITE_DESIGN.md`.
- No Gmail connector, Gmail API, IMAP, OAuth, iCloud.com, browser sessions, keychain credentials, private APIs, or network mail path.

## Synthetic Tests Required

- Build refuses missing date bounds.
- Build refuses missing index confirmation and does not create an index.
- Build paginates with `next_cursor` instead of silently indexing only the first capped page.
- Build rejects `reset` plus a non-zero continuation cursor before deleting prior indexed pages.
- Build rejects symlink and non-regular index, ancestor, or sidecar paths.
- Build reset removes old cached text from the SQLite file and sidecars by validating, deleting the private index plus WAL/SHM/journal sidecars, and rebuilding from scratch.
- Build closes the FTS connection if schema initialization fails.
- Build indexes synthetic body, header, attachment filename, and attachment content text.
- Search refuses missing index.
- Search requires date bounds and quality-guarded queries.
- Search returns redacted bounded snippets and no full email addresses.
- Search output does not return cache paths.
- Search revalidates current live Mail rows and skips deleted/stale rows.
- Search rechecks current live date bounds after index lookup.
- Search uses a read-only index connection and does not invoke schema initialization.
- Search skips rows whose local message content state changed or disappeared after indexing.
- Attachment count, filename, and MIME-type metadata stay separated in search results.
- Search paginates safely when raw FTS matches are filtered by requested scopes or live-row checks.
- CLI forwards synthetic DB, mail root, and test index path without returning the path.
- MCP forwards bounds, flags, cursors, limits, and snippet caps.
- Runtime verifier proves build and search over synthetic Mail fixtures.
- Mutation-gate audit treats `mail_build_fts_index` as a local cache write, not an Apple-data mutation apply surface.

## Current Blockers

Real/non-synthetic mailbox/account management, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, unbounded bulk mutation, background indexing, broad attachment export, and arbitrary document extraction beyond the approved text/PDF/OCR snippet paths remain blocked until separate gates land. Later v1.82/v1.83/v1.84 gates cover outbound sender selection, signatures/templates/query-result planning, and synthetic-only mailbox/cleanup.

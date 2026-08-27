# v1.77 Mail Search Discovery Design

Status: Source read-capable implementation.

This document governs the read-only Mail discovery expansion added after the v1.76 outbound attachment tranche.

## Approved Read Tools

- CLI: `local-apple-data mail body-search`
- CLI: `local-apple-data mail attachment-search`
- CLI: `local-apple-data mail advanced-search`
- MCP: `mail_search_body`
- MCP: `mail_search_attachments`
- MCP: `mail_search_advanced`
- Exact metadata: `mail_get_metadata` may return masked sender/recipient fields, a hashed Message-ID reference, and attachment names/types when the selected local `.emlx` file is available.
- Exact content: `mail_get_content` may page content with `offset` and `next_offset`.

## Privacy Contract

- Body, attachment, and advanced discovery require at least one `after` or `before` date bound.
- Query text must pass the existing minimum quality guard; empty, wildcard-only, and one-character searches are rejected before local content scans.
- Results remain capped at 50 and discovery scans are bounded per page.
- Pagination uses an opaque cursor offset returned by the tool; raw row IDs and file paths are never accepted as cursors.
- Body discovery returns capped redacted snippets only and sets `content_returned:false`.
- Attachment discovery returns filename/MIME/size metadata plus exact `mail:attachment:v1:` handles only; it never returns attachment bytes.
- Advanced discovery supports `subject`, `from`, `to`, `cc`, `bcc`, `body`, and `attachment_filename` scopes only.
- Subject-only advanced discovery does not parse local `.emlx` files.
- Attachment discovery prefilters on header metadata; payload bytes are read only for matched attachments that need exact handles.
- Header metadata is masked by default and returns `full_email_returned:false`, `full_headers_returned:false`, and `message_id_returned:false`.
- Exact message metadata returns attachment names/types from header metadata and does not read attachment payload bytes.
- Exact full body retrieval remains gated by one selected `mail:message:v2:` handle through `mail_get_content` / `local-apple-data mail content`.
- Exact attachment export remains gated by one selected `mail:message:v2:` handle plus one selected `mail:attachment:v1:` handle.

## Explicit Non-Goals

- No durable body index or FTS cache in this v1.77 gate; an opt-in private local FTS cache later landed under `docs/V1_81_MAIL_FTS_INDEX_DESIGN.md`.
- No background indexing.
- No broad unbounded Mail content search.
- No raw MIME, full headers, full email addresses, source `.emlx` paths, mailbox URLs, raw account identifiers, or raw row IDs in output.
- Attachment content/PDF/OCR snippet search later landed under `docs/V1_79_MAIL_ATTACHMENT_CONTENT_SEARCH_DESIGN.md`.
- No live Mail mutation is introduced by this gate.

## Synthetic Tests Required

- Body search refuses missing date bounds.
- Body search finds a body-only query and returns a bounded redacted snippet.
- Attachment search finds a global attachment filename without returning bytes or paths.
- Attachment search does not read nonmatching attachment payload bytes.
- Advanced search matches masked header scopes, body scopes, and attachment filename scopes.
- Subject-only advanced search does not parse message files.
- Exact metadata returns masked headers and selected attachment names without full email/header/message-id disclosure.
- Exact metadata does not read attachment payload bytes.
- Exact content paging returns `content_offset`, `content_total_chars`, `next_offset`, and rejects negative offsets.
- CLI and MCP wrappers expose the new tools and keep bad inputs safe.
- Runtime verifier proves direct adapter behavior and MCP tool presence.

## Current Blockers

- Optional local FTS later landed under `docs/V1_81_MAIL_FTS_INDEX_DESIGN.md` as an explicit-confirmation private cache with date bounds and no cache path output.
- Background indexing, unbounded/bulk body search, broad attachment export, arbitrary document extraction beyond v1.79/v1.81 snippets, and generated document extraction remain blocked until separate gates land.

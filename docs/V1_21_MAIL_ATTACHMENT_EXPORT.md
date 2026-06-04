# v1.21 Mail Attachment Export Design

Status: implemented read/export surface.

This release adds exact-handle Apple Mail attachment metadata and local MIME attachment export. It does not add any new mutating tools.

## Approved Surface

- CLI metadata: `local-apple-data mail attachments --handle <mail:message:v2:...>`
- CLI export: `local-apple-data mail export-attachment --message-handle <mail:message:v2:...> --handle <mail:attachment:v1:...> --output-dir <dir>`
- MCP metadata: `mail_list_attachments`
- MCP export: `mail_export_attachment`

The caller must first select an exact `mail:message:v2:` handle from Mail search or metadata output. Attachment listing parses only that selected local `.emlx` MIME message and returns bounded metadata plus opaque `mail:attachment:v1:` handles. Export requires both the original message handle and the selected attachment handle, then writes bytes to a caller-selected output directory.

## Data Boundaries

- Attachment bytes are never returned inline.
- Source `.emlx` paths and source attachment paths are never returned.
- Raw MIME and full headers are never returned.
- Externalized or partial-message attachments are not fetched.
- Export writes only to the caller-selected output directory.
- Filenames are sanitized and made unique in the target directory.

## Refusals

The surface refuses:

- Raw message IDs, raw attachment IDs, old handles, mailbox refs, fabricated handles, and local source paths.
- Broad attachment exports.
- Deleted or unavailable parent messages.
- Externalized or partial-message attachments whose bytes are not in the selected local MIME message.
- Network attachment fetches.
- Attachment creation, replacement, deletion, rename, move, OCR, transcription, or other mutation.

## Verification

The implementation is covered by synthetic fixtures only:

- Attachment metadata listing by exact message handle.
- MIME attachment export by exact message and attachment handles.
- Externalized/partial attachment unavailable warning.
- Bad-handle rejection.
- CLI and MCP wrapper coverage.
- Runtime smoke keys for list/export success and legacy message-handle refusal.
- Redacted-log coverage that excludes handles, filenames, warning messages, source paths, and export paths.

## Privacy Notes

This tranche closes the local Mail attachment read/export gap without changing the default metadata-first posture. It is exact-message and exact-attachment directed: agents cannot ask for every Mail attachment, inspect source message paths, fetch missing remote resources, return raw MIME/full headers, or mutate attachment state.

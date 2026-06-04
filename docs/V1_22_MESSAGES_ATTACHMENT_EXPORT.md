# v1.22 Messages Attachment Export Design

Status: implemented read/export surface.

This release adds exact-handle Apple Messages attachment metadata and local attachment export. It does not add any new mutating tools.

## Approved Surface

- CLI metadata: `local-apple-data messages attachments --handle <messages:chat:v1:...>`
- CLI export: `local-apple-data messages export-attachment --chat-handle <messages:chat:v1:...> --handle <messages:attachment:v1:...> --output-dir <dir>`
- MCP metadata: `messages_list_attachments`
- MCP export: `messages_export_attachment`

The caller must first select an exact `messages:chat:v1:` handle from Messages search output. Attachment listing reads only attachment rows linked to that selected chat, returns bounded metadata, and emits opaque `messages:attachment:v1:` handles. Export requires both the original chat handle and the selected attachment handle, then copies the selected local attachment file to a caller-selected output directory.

## Data Boundaries

- Attachment bytes are never returned inline.
- Source media paths are never returned.
- Participant identifiers, chat GUIDs, raw row IDs, and attachment GUIDs are never returned.
- Remote or unavailable iCloud-only media is not fetched.
- Export writes only to the caller-selected output directory.
- Filenames are sanitized and made unique in the target directory.

## Refusals

The surface refuses:

- Raw chat IDs, raw attachment IDs, chat GUIDs, attachment GUIDs, old handles, fabricated handles, and local source paths.
- Broad Messages attachment exports.
- Attachments not linked to the selected chat handle.
- Source paths outside the local Messages root, symlink escapes, unsupported URL schemes, and missing local media files.
- Network or iCloud media fetches.
- Message send/edit/delete, attachment creation, replacement, deletion, rename, move, OCR, transcription, or other mutation.

## Verification

The implementation is covered by synthetic fixtures only:

- Attachment metadata listing by exact chat handle.
- Attachment export by exact chat and attachment handles.
- Missing-media unavailable warning.
- Bad-handle rejection.
- CLI and MCP wrapper coverage.
- Runtime smoke keys for list/export success and legacy attachment-handle refusal.
- Redacted-log coverage that excludes handles, filenames, warning messages, source paths, and export paths.

## Privacy Notes

This tranche closes the local Messages attachment read/export gap without changing the default metadata-first posture. It is exact-chat and exact-attachment directed: agents cannot ask for every Messages attachment, inspect source paths, fetch missing iCloud media, reveal participant identifiers, or mutate Messages state.

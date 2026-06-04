# v1.20 Notes Attachment Export Design

Status: implemented read/export surface.

This release adds exact-handle Apple Notes attachment metadata and export. It does not add any new mutating tools.

## Approved Surface

- CLI metadata: `local-apple-data notes attachments --handle <notes:note:v2:...>`
- CLI export: `local-apple-data notes export-attachment --handle <notes:attachment:v1:...> --output-dir <dir>`
- MCP metadata: `notes_list_attachments`
- MCP export: `notes_export_attachment`

The caller must first select an exact `notes:note:v2:` handle from Notes search or metadata output. Attachment listing returns bounded metadata and an opaque `notes:attachment:v1:` handle for each locally known attachment on that selected note. Export accepts only that attachment handle and writes bytes to a caller-selected output directory.

## Data Boundaries

- Attachment bytes are never returned inline.
- Source media paths are never returned.
- Remote attachment URLs are not returned and are never fetched.
- Export writes only to the caller-selected output directory.
- Export prefers the local Notes media file when available and falls back to local database BLOB data when present.
- Filenames are sanitized and made unique in the target directory.

## Refusals

The surface refuses:

- Raw note IDs, raw attachment IDs, old handles, fabricated handles, and local source paths.
- Broad attachment exports.
- Locked or deleted parent notes.
- Remote-only attachments that are not locally available.
- Network iCloud fetches.
- Attachment creation, replacement, deletion, rename, move, OCR, transcription, or other mutation.

## Verification

The implementation is covered by synthetic fixtures only:

- Attachment metadata listing by exact note handle.
- Media-file export by exact attachment handle.
- BLOB fallback export.
- Remote-only unavailable warning.
- Bad-handle rejection.
- CLI and MCP wrapper coverage.
- Runtime smoke keys for list/export success and legacy-handle refusal.
- Redacted-log coverage that excludes handles, filenames, warning messages, and export paths.

## Privacy Notes

This tranche closes the imported-note gap for locally available attachments without changing the default metadata-first posture. It is still exact-handle and user-directed: agents cannot ask for every Notes attachment, inspect source paths, fetch missing iCloud resources, or mutate attachment state.

# V1.146 iCloud Drive Non-Empty Folder Trash Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: trash_folder` as a non-mutating preview, and the existing apply tools support the matching approved exact folder Trash operation.

## Scope

This tranche broadens the v1.61 trash-folder gate from empty-only directories to exact directories that may contain children.

Allowed:

- Move one exact iCloud Drive directory selected by an opaque `icloud:file:v1:` handle to recoverable Trash.
- Preserve any existing children as part of the filesystem's atomic directory Trash move.

Still blocked:

- No child listing.
- No file content inspection.
- No permanent folder delete outside the exact selected-folder delete gate.
- No folder copy outside the exact selected-folder copy gate.
- No broad or unbounded recursive copy/delete, empty Trash, or content return.
- No raw paths, hidden-file writes, symlink/package traversal, overwrite, bulk folder operations, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback.

## Preview

Preview validates bounded input shape and returns `mutation_applied:false`.

- `trash_folder` requires one exact opaque directory handle and `expected-current-SHA-256` from `metadata_sha256`.
- Preview returns `empty_folder_required:false`, `non_empty_allowed:true`, `move_to_trash:true`, `permanent_delete:"blocked"`, `recursive_delete:"blocked"`, `recursive_content_read:"blocked"`, no child listing, no raw path, no content text, and no approval token.

## Apply

Apply requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, handle, and metadata SHA-256.
- Exact source resolution through metadata flow only.
- Directory source validation with symlink/package traversal refusal.
- Current source directory metadata SHA-256 check immediately before write.
- Recoverable Trash move through fd-relative `renameatx_np` with `RENAME_SWAP` and `RENAME_NOFOLLOW_ANY`.
- Placeholder cleanup by exact reserved directory identity.

## Read Back

Read-back is metadata-only:

- Original handle absence proof.
- `trashed:true`.
- Hash-only Trash-name proof.
- `trash_path_returned:false`.
- `empty_folder_confirmed` as a boolean.
- `non_empty_allowed:true`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

If placeholder cleanup fails after a verified Trash move, apply returns `partial` with `cleanup_unverified`, `mutation_applied:true`, and `trashed:true`. If the trashed snapshot is not verified and rollback restores the original folder, apply returns `partial` with `read_back_mismatch`, `mutation_applied:false`, and `trashed:false`.

## Synthetic Tests Required

- Preview success for non-empty-allowed trash-folder.
- Apply success for non-empty trash-folder with child preservation and no content/hash/path return.
- Apply-time non-empty race success with child preservation.
- Placeholder cleanup partial reporting with `cleanup_unverified`.
- Pre-proof read-back mismatch rollback that does not claim `mutation_applied:true` or `trashed:true`.
- Stale metadata, malformed handle, wrong kind, and missing confirmation refusals.
- CLI and MCP coverage.
- Runtime verifier coverage for direct and MCP paths.
- Redaction scan coverage proving no content text, raw paths, handles, metadata hashes, approval fingerprints, approval tokens, source names, or Trash names leak through logs.

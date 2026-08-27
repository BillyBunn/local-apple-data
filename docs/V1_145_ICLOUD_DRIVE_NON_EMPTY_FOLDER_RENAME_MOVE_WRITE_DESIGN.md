# V1.145 iCloud Drive Non-Empty Folder Rename And Move Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operations: rename_folder, move_folder` as non-mutating previews, and the existing apply tools support the matching approved exact folder rename and move operations.

## Scope

This tranche broadens the v1.60 rename-folder and v1.62 move-folder gates from empty-only directories to exact directories that may contain children.

Allowed:

- Rename one exact iCloud Drive directory selected by an opaque `icloud:file:v1:` handle.
- Move one exact iCloud Drive directory selected by an opaque `icloud:file:v1:` handle to one exact target parent directory selected by an opaque `icloud:file:v1:` handle.
- Preserve any existing children as part of the filesystem's atomic directory rename or move.

Still blocked:

- No child listing.
- No file content inspection.
- No recursive copy, delete, Trash, or content return.
- No folder copy outside the exact empty-folder copy gate.
- No folder Trash or delete outside the exact empty-folder Trash/delete gates.
- No raw paths, hidden-file writes, symlink/package traversal, overwrite, bulk folder operations, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback.

## Preview

Preview validates only bounded input shape and returns `mutation_applied:false`.

- `rename_folder` requires one exact opaque directory handle, `expected-current-SHA-256` from `metadata_sha256`, and a bounded target folder name.
- `move_folder` requires one exact opaque source directory handle, one exact opaque target parent directory handle, `expected-current-SHA-256`, and an optional bounded target folder name.
- Both previews return `empty_folder_required:false`, `non_empty_allowed:true`, no child listing, no raw path, no content text, and no approval token.

## Apply

Apply requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, handles, metadata SHA-256, and target folder name.
- Exact source and target-parent resolution through metadata flow only.
- Directory source and parent validation with symlink/package traversal refusal.
- Current source directory metadata SHA-256 check immediately before write.
- `move_folder` descendant-parent refusal so a folder cannot be moved into itself or its own subtree.
- No overwrite through fd-relative `renameatx_np` with `RENAME_EXCL` and `RENAME_NOFOLLOW_ANY`.

## Read Back

Read-back is metadata-only:

- Source/target presence proof.
- Target opaque handle, target name, kind `directory`, and `metadata_sha256`.
- `empty_folder_confirmed` as a boolean.
- `non_empty_allowed:true`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

If the directory changes during apply and the relocated snapshot cannot be verified, apply returns `partial` with `read_back_mismatch` and `mutation_applied:true`.

## Synthetic Tests Required

- Preview success for non-empty-allowed rename-folder and move-folder.
- Apply success for non-empty rename-folder with child preservation and no content/hash return.
- Apply success for non-empty move-folder with child preservation and no content/hash return.
- Move descendant-parent refusal with no source mutation.
- Apply-time directory-change partial reporting with `read_back_mismatch`.
- Stale metadata, target exists, malformed handle, wrong kind, invalid target name, and missing confirmation refusals.
- CLI and MCP coverage.
- Runtime verifier coverage for direct and MCP paths.
- Redaction scan coverage proving no content text, raw paths, handles, metadata hashes, approval fingerprints, approval tokens, source names, or target names leak through logs.

# V1.62 iCloud Drive Exact Folder Move Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: move_folder` as a non-mutating preview, and the existing apply tools support the matching approved exact folder move operation. v1.145 broadens the original empty-only guard to allow non-empty directories without child listing or content return.

## Scope

This tranche approves one narrow local filesystem operation: move one exact iCloud Drive directory selected by an opaque `icloud:file:v1:` handle to one exact target parent directory selected by an opaque `icloud:file:v1:` handle, with an optional approved target folder name. Non-empty source directories are allowed; read-back reports whether the selected directory is empty but never lists children.

This is not approval for recursive folder content traversal, folder copy outside the exact empty-folder copy gate, non-empty folder copy, permanent delete, empty Trash, package mutation, symlink traversal, binary/document content generation or editing, regular-file mutation outside exact import-file, exact replace-file, exact trash-file, exact delete-file, or metadata-only rename/copy/move gates, raw paths, broad folder operations, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback.

## Preview

`preview` never resolves local paths and never mutates files. It validates only bounded input shape:

- Exact opaque source `icloud:file:v1:` directory handle.
- Exact opaque target parent `icloud:file:v1:` directory handle.
- `expected-current-SHA-256` from the selected folder metadata's `metadata_sha256`.
- Optional new folder name, with no path separators, hidden names, or package suffixes.
- No content text.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata including `empty_folder_required:false` and `non_empty_allowed:true`, idempotency metadata, and an approval fingerprint. It does not return child listings, raw paths, approval tokens, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, source handle, target parent handle, metadata SHA-256, and optional new folder name.
- Exact source folder and target parent resolution through metadata flow only.
- Directory source and parent, no symlink or package traversal.
- Descendant-parent refusal so a folder cannot be moved into itself or its own subtree.
- Current source directory metadata SHA-256 check immediately before write.
- No overwrite through fd-relative `renameatx_np` with `RENAME_EXCL` and `RENAME_NOFOLLOW_ANY`.

If the folder already has the approved parent and name and the metadata hash still matches, apply returns `already_applied` with `mutation_applied:false`.

## Read Back

The apply response uses a `read_back` object. Read-back is metadata-only:

- `source_present:false` for successful move.
- `target_present:true` for successful move.
- Target opaque handle, target name, kind `directory`, and `metadata_sha256`.
- `empty_folder_confirmed` as a boolean.
- `non_empty_allowed:true`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing target, unexpected source presence, unreadable read-back, or metadata mismatch returns `partial` or `error` with a bounded warning code.

## Safety

- No raw local paths in normal output or logs.
- Current source directory metadata is rechecked at apply time after resolving the exact handle and before fd-relative move.
- If source directory metadata changes during apply and read-back identity cannot be fully verified against the approved snapshot, apply returns `partial` with `read_back_mismatch` instead of claiming a clean mutation.
- No child listing.
- No file content inspection.
- No permanent deletion.
- No overwrite.
- No recursive copy, delete, Trash, or content return.
- Symlink/package traversal refusal before fd-relative move.
- Stale folder metadata returns `current_metadata_changed`.
- Non-empty source directories are allowed.
- Existing destination returns `target_exists`.
- Self-parent moves return `invalid_parent_handle`.
- Descendant-parent moves return `invalid_parent_handle`.
- Hidden CLI `--root` overrides for iCloud Drive apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can replace content, rename one exact folder, move one exact folder, move one exact text file to Trash, rename, or move one exact selected file.

## Synthetic Tests Required

- Preview success for `move_folder`.
- Missing or wrong handles, parent handles, expected-current-SHA-256, content_text, and invalid target-name refusals.
- Apply success with source absence, target presence, `non_empty_allowed:true`, and metadata-only read-back.
- Stale metadata refusal with no target mutation.
- Non-empty folder success with child preservation and no content/hash return.
- Existing target refusal with no source mutation.
- Self-parent refusal with no source mutation.
- Descendant-parent refusal with no source mutation.
- Partial result when apply-time directory metadata changes cannot be verified as a clean move.
- CLI plan/apply coverage through hidden synthetic root.
- MCP preview and apply coverage.
- Runtime verifier coverage for source and MCP paths.
- Redaction scan coverage proving no content text, raw paths, handles, metadata hashes, approval fingerprints, approval tokens, source names, or target names leak through logs.

At the time of v1.145, the release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only. The later exact selected-folder permanent delete gate is governed by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`, and later bounded selected-folder copy is governed by `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`. Recursive folder content traversal, folder copy outside the exact selected-folder copy gate, unbounded recursive folder copy or delete, file permanent delete outside exact file-delete gates, folder delete outside the exact selected-folder delete gate, empty Trash, binary/document generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

# V1.61 iCloud Drive Exact Empty Folder Trash Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: trash_folder` as a non-mutating preview, and the existing apply tools support the matching approved exact empty folder Trash operation.

## Scope

This tranche approves one narrow local filesystem operation: move one exact empty iCloud Drive directory selected by an opaque `icloud:file:v1:` handle through a recoverable Trash move.

This v1.61 tranche itself is not approval for non-empty folder trash, recursive folder delete, file permanent delete, selected-folder permanent delete outside the later v1.67 gate, empty Trash, folder copy outside the exact selected-folder copy gate, folder move outside the exact folder move gate, package mutation, symlink traversal, binary/document content generation or editing, regular-file mutation outside exact import-file, exact replace-file, exact trash-file, exact delete-file, or metadata-only rename/copy/move gates, raw paths, broad folder operations, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback. Later gates broadened non-empty folder trash, selected-folder copy, and selected-folder delete.

## Preview

`preview` never resolves local paths and never mutates files. It validates only bounded input shape:

- Exact opaque `icloud:file:v1:` directory handle.
- `expected-current-SHA-256` from the selected folder metadata's `metadata_sha256`.
- No parent handle.
- No filename.
- No content text.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, and an approval fingerprint. It does not return child listings, raw paths, approval tokens, Trash paths, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, handle, and metadata SHA-256.
- Exact source folder resolution through metadata flow only.
- Directory target, no symlink or package traversal.
- Current directory metadata SHA-256 check immediately before write.
- The empty-folder check immediately before write is mandatory and repeated after exact-handle resolution.
- Recoverable Trash move using no-follow fd-relative operations and `RENAME_SWAP` plus `RENAME_NOFOLLOW_ANY`.

Apply creates a private empty directory reservation in the Trash destination, swaps the selected empty folder with that reservation, verifies the moved folder identity, verifies it remains empty, and removes only the identity-checked empty placeholder left at the original path.

## Read Back

The apply response uses a `read_back` object. Read-back is metadata-only:

- `original_present:false` for successful Trash apply.
- `trashed:true` for successful Trash apply.
- Original opaque handle and original name.
- Kind `directory`.
- `empty_folder_confirmed:true`.
- `trash_path_returned:false`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing absence proof, unreadable read-back, cleanup uncertainty, or rollback uncertainty returns `partial` or `error` with a bounded warning code.

## Safety

- No raw local paths in normal output or logs.
- No Trash path return.
- No child listing.
- No file content inspection.
- No permanent deletion; permanent delete remains blocked.
- No empty Trash.
- No recursive folder operation.
- The empty-folder check is repeated at apply time, after resolving the exact handle and before fd-relative Trash move.
- If a child appears after the empty-folder check but before/during Trash apply, apply attempts an exact identity-checked rollback to the original name. A verified rollback returns `folder_not_empty_after_apply` without leaving the approved Trash move applied; an unverified rollback returns `partial` with `rollback_failed`.
- Symlink/package traversal refusal before fd-relative Trash move.
- Stale folder metadata returns `current_metadata_changed`.
- Non-empty source returns `folder_not_empty`.
- Hidden CLI `--root` overrides for iCloud Drive apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can replace content, move one exact empty folder to Trash, rename one exact empty folder, move one exact text file to Trash, rename, or move one exact selected file.

## Synthetic Tests Required

- Preview success for `trash_folder`.
- Parent handle, filename, content text, missing SHA-256, and malformed handle refusals.
- Apply success with original absence, Trash proof, empty-folder proof, metadata-only read-back, `content_text_returned:false`, and `content_hash_returned:false`.
- Stale metadata refusal with no Trash mutation.
- Non-empty folder refusal with no Trash mutation.
- Post-empty-check race rollback when a child appears during Trash apply.
- Partial result when rollback cannot be verified.
- File-handle refusal.
- CLI preview/apply coverage.
- MCP preview and apply coverage.

## Explicit Non-Goals

- Non-empty folder Trash.
- Recursive folder delete.
- Permanent delete.
- Empty Trash.
- Folder copy or move.
- Package mutation.
- Symlink traversal.
- Raw-path mutation.
- Binary/document write.
- Broad folder operation.

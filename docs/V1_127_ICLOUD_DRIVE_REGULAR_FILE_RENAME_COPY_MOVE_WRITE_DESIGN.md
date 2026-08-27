# V1.127 iCloud Drive Regular File Rename, Copy, and Move Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: rename_file`, `operation: copy_file`, and `operation: move_file` as non-mutating previews, and the existing apply tools support the matching approved exact-file operations.

## Scope

This tranche approves narrow local filesystem operations for one non-text non-package regular iCloud Drive file selected by exact opaque `icloud:file:v1:` handle. In audit shorthand: one non-text non-package regular file.

- `operation: rename_file`: rename one regular file inside its current parent directory.
- `operation: copy_file`: copy one regular file to a non-existing target filename in the same parent or one exact selected parent folder.
- `operation: move_file`: move one regular file to one exact selected parent folder, optionally with a new filename.

This is not approval for binary/document content generation or editing, inline binary/document extraction, permanent delete, empty Trash, recursive folder content traversal, folder copy outside the exact empty-folder copy gate, non-empty folder copy, package mutation, text-file relocation outside the existing text-file gates, hidden files, raw paths, path traversal, broad folder operations, or iCloud.com/private API/browser/keychain paths.

## Preview

`preview` never resolves local paths and never mutates files. It validates only bounded input shape:

- Exact opaque `icloud:file:v1:` file handle.
- Expected file `metadata_sha256` from exact selected iCloud Drive metadata.
- New non-text non-package filename where required.
- Exact opaque parent folder handle for `move_file`, and optional exact opaque parent folder handle for `copy_file`.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, and an approval fingerprint. It returns `content_return:"blocked"` and `content_hash_return:"blocked"`. It does not return file content, content hash, raw paths, source directories, approval tokens, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, handle, expected file `metadata_sha256`, target filename, and target parent.
- Exact source file resolution through metadata flow only.
- Non-text non-package regular file, no symlink/package traversal.
- Current metadata SHA-256 check immediately before write.
- No overwrite through no-overwrite target reservation before relocation.
- Explicit symlink/package traversal refusal.

Rename and move create a no-follow exclusive placeholder at the target, then use fd-relative `renameatx_np` with `RENAME_SWAP` and `RENAME_NOFOLLOW_ANY`. Existing destinations fail before the swap. After the swap, apply verifies that the target identity matches the approved source before removing the placeholder from the source location. If post-swap proof fails, apply swaps back only after verifying both the moved file and placeholder identities; otherwise it returns `partial`. Once target proof succeeds, source-placeholder cleanup failure never triggers rollback, because rollback could move a racing source replacement into the verified target.

Copy uses fd-relative no-follow exclusive create, reads the source bytes without following symlinks, writes them to the target, verifies target identity and size, then rechecks the source metadata snapshot. If the source changed after the initial read, apply removes only the created target after verifying target identity; otherwise it returns `partial`.

All apply paths read back target metadata only. They return no inline content and no content hash.
This is metadata-only read-back and no content hash return.

## Read Back

Read-back includes:

- `source_present:false` for successful rename/move.
- `source_present:true` for successful copy.
- `target_present:true` for successful rename/copy/move.
- Target opaque handle, target filename, size, extension, and target `metadata_sha256`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing target, unexpected source presence, unreadable read-back, or wrong target kind returns `partial` with `read_back_mismatch` or `read_back_unavailable`.

## Safety

- No raw local paths in normal output or logs.
- No inline content and no returned content hash.
- No broad directory mutation.
- No permanent deletion.
- No overwrite.
- No source mutation for copy.
- Text files must use the existing text-file rename/copy/move gates.
- Package and symlink traversal refusal before and during fd-relative operations.
- Rename/move rollback on post-swap identity mismatch when rollback identities are still verifiable.
- Rename/move verified-target preservation when source-placeholder cleanup races after target proof.
- Copy post-write source metadata recheck with identity-checked target cleanup on drift.
- Stale source metadata returns `current_metadata_changed`.
- Existing destination returns `target_exists`.
- Hidden CLI `--root` overrides for iCloud Drive search/get/content/apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can create, replace, trash, delete, rename, copy, or move one exact selected item.

## Synthetic Tests Required

- Preview success for `rename_file`, `copy_file`, and `move_file`.
- Missing or wrong handles, parent handles, filenames, expected-current-SHA-256, and content_text refusals.
- Apply success for rename, copy, and move with metadata-only read_back proof.
- Stale-metadata refusal with no target mutation.
- Existing-target refusal with no source or target mutation.
- Text-file source refusal through the regular-file path.
- Symlink and package-member refusal.
- CLI hidden-root refusal for search, get, content, and apply outside the synthetic test opt-in.
- CLI plan/apply coverage.
- MCP preview and apply coverage.
- Runtime verifier coverage for source paths.
- Redaction scan coverage proving no content text, content hash, raw paths, handles, metadata hashes, approval fingerprints, or approval tokens leak through logs.

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only. Permanent delete outside the exact delete gates, empty Trash, recursive folder creation, folder copy outside the exact empty-folder copy gate, non-empty/recursive folder copy or delete, binary/document content generation, binary/document content editing, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

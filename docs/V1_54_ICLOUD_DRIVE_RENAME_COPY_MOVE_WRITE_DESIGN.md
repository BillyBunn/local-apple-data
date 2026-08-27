# V1.54 iCloud Drive Rename, Copy, and Move Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: rename_text`, `operation: copy_text`, and `operation: move_text` as non-mutating previews, and the existing apply tools support the matching approved exact-file operations.

## Scope

This tranche approves narrow local filesystem operations for one supported text-like iCloud Drive file selected by exact opaque `icloud:file:v1:` handle:

- `operation: rename_text`: rename one file inside its current parent directory.
- `operation: copy_text`: copy one file to a non-existing target filename in the same parent or one exact selected parent folder.
- `operation: move_text`: move one file to one exact selected parent folder, optionally with a new filename.

This is not approval for permanent delete, empty Trash, recursive folder content traversal, folder copy outside the exact empty-folder copy gate, non-empty folder copy, package mutation, binary/document content generation or editing, regular-file mutation outside exact import-file, exact replace-file, exact trash-file, exact delete-file, or metadata-only rename/copy/move gates, hidden files, raw paths, path traversal, broad folder operations, or iCloud.com/private API/browser/keychain paths.

## Preview

`preview` never resolves local paths and never mutates files. It validates only bounded input shape:

- Exact opaque `icloud:file:v1:` file handle.
- `expected-current-SHA-256` from exact `icloud_drive_get_content`.
- New filename where required.
- Exact opaque parent folder handle for `move_text`, and optional exact opaque parent folder handle for `copy_text`.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, and an approval fingerprint. It does not return file content, raw paths, source directories, approval tokens, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, handle, expected-current-SHA-256, target filename, and target parent.
- Exact source file resolution through metadata flow only.
- Supported text suffix, valid UTF-8, no NUL bytes, no symlink/package traversal.
- Current SHA check immediately before write.
- No overwrite through no-overwrite target reservation before relocation.
- Explicit symlink/package traversal refusal.

Rename and move create a no-follow exclusive placeholder at the target, then use fd-relative `renameatx_np` with `RENAME_SWAP` and `RENAME_NOFOLLOW_ANY`. Existing destinations fail before the swap. After the swap, apply verifies that the target identity matches the approved source and that the target SHA-256 still equals the approved current SHA-256 before removing the placeholder from the source location. If post-swap proof fails, apply swaps back only after verifying both the moved file and placeholder identities; otherwise it returns `partial`. Once target proof succeeds, source-placeholder cleanup failure never triggers rollback, because rollback could move a racing source replacement into the verified target.

Copy uses fd-relative no-follow exclusive create, writes the original source bytes, verifies target identity and SHA-256, then re-reads the source and verifies its SHA-256 still equals the approved current SHA-256. If the source changed after the initial read, apply removes only the created target after verifying target identity; otherwise it returns `partial`.

All apply paths read back the target content hash without returning `content_text`.

## Read Back

Read-back includes:

- `source_present:false` for successful rename/move.
- `source_present:true` for successful copy.
- `target_present:true` for successful rename/copy/move.
- Target opaque handle, target filename, content SHA-256, and content length.
- `content_text_returned:false`.

Missing target, unexpected source presence, unreadable read-back, or content-hash mismatch returns `partial` with `read_back_mismatch` or `read_back_unavailable`.

## Safety

- No raw local paths in normal output or logs.
- No broad directory mutation.
- No permanent deletion.
- No overwrite.
- No source mutation for copy.
- Symlink/package traversal refusal before and during fd-relative operations.
- Rename/move rollback on post-swap identity or SHA mismatch when rollback identities are still verifiable.
- Rename/move verified-target preservation when source-placeholder cleanup races after target proof.
- Copy post-write source recheck with identity-checked target cleanup on drift.
- Stale source content returns `current_content_changed`.
- Existing destination returns `target_exists`.
- Hidden CLI `--root` overrides for iCloud Drive search/get/content/apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can replace content, move to Trash, rename, or move one exact selected file.

## Synthetic Tests Required

- Preview success for `rename_text`, `copy_text`, and `move_text`.
- Missing or wrong handles, parent handles, filenames, expected-current-SHA-256, and content_text refusals.
- Apply success for rename, copy, and move with read_back proof.
- Stale-content refusal with no target mutation.
- Existing-target refusal with no source or target mutation.
- Rename/move post-swap source-content race refusal with rollback proof.
- Rename/move source-placeholder cleanup race returns `partial` while preserving the verified target.
- Copy post-target-write source-content race refusal with created-target cleanup proof.
- CLI hidden-root refusal for search, get, content, and apply outside the synthetic test opt-in.
- Unsupported binary/invalid UTF-8, symlink, and package-member refusal.
- CLI plan/apply coverage.
- MCP preview and apply coverage.
- Runtime verifier coverage for source and MCP paths.
- Redaction scan coverage proving no content text, raw paths, handles, hashes, approval fingerprints, or approval tokens leak through logs.

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, rename-text, copy-text, and move-text apply only. Permanent delete, empty Trash, recursive folder creation, folder copy outside the exact empty-folder copy gate, non-empty/recursive folder copy, binary/document generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

# V1.131 iCloud Drive Trash File Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: trash_file` as a non-mutating preview, and the existing apply tools support the matching approved exact recoverable Trash move.

## Scope

This tranche approves moving one exact existing iCloud Drive non-text non-package regular file to recoverable Trash.

- `operation: trash_file`: move one exact regular file handle to Trash while returning only metadata-proof output.

This is not approval for permanent delete, empty Trash, text-file trash outside `trash_text`, package mutation, directory trash outside `trash_folder`, broad folder trash, raw target paths, raw Trash paths, path traversal, iCloud.com/private API/browser/keychain paths, content inspection, content hash output, or regular-file mutation outside this exact trash-file gate plus the approved import-file, replace-file, and metadata-only rename/copy/move gates.

## Preview

`preview` never mutates files. It validates bounded input shape:

- Exact opaque `icloud:file:v1:` target regular-file handle.
- expected target `metadata_sha256` from recent iCloud Drive metadata.
- No parent handle, target filename, source file, or inline content text.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, and an approval fingerprint. It returns `content_return:"blocked"` and `content_hash_return:"blocked"`. It does not return the target local path, Trash path, file content, content hash, approval token, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, target handle, and expected target metadata.
- Exact target resolution through metadata flow only.
- Current target metadata SHA-256 match before Trash move.
- Non-text non-package regular target file.
- Target write through fd-relative no-follow filesystem operations.

Apply opens the target parent from the iCloud Drive root without following symlinks, creates a random reserved file in the Trash directory with exclusive create, rechecks target metadata, atomically swaps target and reserved Trash entry, verifies the moved target identity by stat metadata only, then removes the placeholder from the original parent after verifying placeholder identity.

All apply paths use exact target metadata proof, target metadata drift refusal, recoverable Trash move, original absence proof, and metadata-only read-back. They return no inline content, no content hash, no raw target path, and no Trash path: no Trash path return and no content hash return.

## Read Back

Read-back includes:

- `trashed:true`.
- `original_present:false` on successful absence proof.
- Original opaque handle and original filename.
- `kind:"file"`.
- `content_type:"regular_file"`.
- `trash_path_returned:false`.
- `content_text_returned:false`.
- `content_hash_returned:false`.
- `trash_name_sha256` hash-only proof when the Trash reservation name is available.

Missing target, unreadable read-back, stale target metadata, text-like target, package traversal, symlink traversal, non-regular target, or placeholder cleanup uncertainty returns `partial` or `error` with structured warnings and no path/hash/content disclosure.

## Safety

- No raw local paths in normal output or logs.
- No source, target, or content hash in normal output or logs.
- No inline content.
- No permanent delete.
- No text-file trash; text files must use the existing `trash_text` gate.
- Package and symlink traversal refusal before and during fd-relative operations.
- Stale target metadata returns `current_metadata_changed`.
- Text/package/symlink/non-regular targets return `unsupported_file_type` or `target_file_not_found`.
- Hidden CLI `--root` overrides for iCloud Drive search/get/content/apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can mutate one exact selected item.

## Synthetic Tests Required

- Preview success for `trash_file` without raw path or content hash disclosure.
- Apply success with metadata-only read-back proof, original absence proof, recoverable Trash presence in a synthetic root, `trash_path_returned:false`, `content_text_returned:false`, and `content_hash_returned:false`.
- Stale target-metadata refusal with no target mutation.
- Text target, symlink target, package member, and non-regular target refusals.
- CLI plan/apply coverage.
- MCP preview and apply coverage.
- Runtime verifier coverage for direct and MCP trash-file, recoverable Trash proof, stale metadata refusal, and no path/hash/content disclosure.
- Redaction scan coverage proving no content text, content hash, source path, Trash path, target path, handles, approval fingerprints, or approval tokens leak through logs.

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only. Permanent delete outside the exact delete gates, empty Trash, recursive folder creation, folder copy outside the exact empty-folder copy gate, non-empty/recursive folder copy, inline binary/document content generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

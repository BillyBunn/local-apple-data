# V1.132 iCloud Drive Delete File Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: delete_file` as a non-mutating preview, and the existing apply tools support the matching approved exact permanent unlink.

## Scope

This tranche approves permanently deleting one exact existing iCloud Drive non-text non-package regular file.

- `operation: delete_file`: permanently unlink one exact regular file handle while returning only metadata-proof output.

This is not approval for empty Trash, broad delete, text-file delete outside `delete_text`, package mutation, directory delete outside `delete_folder`, recursive delete, raw staging paths, raw target paths, path traversal, iCloud.com/private API/browser/keychain paths, content inspection, content hash output, or regular-file mutation outside this exact delete-file gate plus approved import-file, replace-file, trash-file, and metadata-only rename/copy/move gates.

## Preview

`preview` never mutates files. It validates bounded input shape:

- Exact opaque `icloud:file:v1:` target regular-file handle.
- Expected target `metadata_sha256` from recent iCloud Drive metadata.
- No parent handle, target filename, source file, or inline content text.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, and an approval fingerprint. It returns `content_return:"blocked"` and `content_hash_return:"blocked"`. It does not return the target local path, staging path, file content, content hash, approval token, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, target handle, and expected target `metadata_sha256`.
- Exact target resolution through metadata flow only.
- Current target metadata SHA-256 match before delete.
- Non-text non-package regular target file.
- Target write through fd-relative no-follow filesystem operations.

Apply opens the target parent from the iCloud Drive root without following symlinks, creates a hidden local staging directory under the configured root, atomically moves the target into a random staging name with exclusive create semantics, verifies staged identity by stat metadata only, permanently unlinks the staged file, and verifies original-handle absence.

All apply paths use exact target metadata proof, target metadata drift refusal, hidden staging identity proof, permanent unlink, original absence proof, and metadata-only read-back. They return no inline content, no content hash, no raw target path, no staging path, and no Trash path; this is no content hash return.

## Read Back

Read-back includes:

- `verified_absent:true`.
- `permanently_deleted:true`.
- `original_present:false`.
- Original opaque handle and original filename.
- `kind:"file"`.
- `content_type:"regular_file"`.
- `trash_path_returned:false`.
- `staging_path_returned:false`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing target, unreadable read-back, stale target metadata, text-like target, package traversal, symlink traversal, non-regular target, or rollback uncertainty returns `partial` or `error` with structured warnings and no path/hash/content disclosure.

## Safety

- No raw local paths in normal output or logs.
- No content hash in normal output or logs.
- No inline content.
- No Trash-empty or broad delete.
- No text-file delete; text files must use the existing `delete_text` gate.
- Package and symlink traversal refusal before and during fd-relative operations.
- Stale target metadata returns `current_metadata_changed`.
- Text/package/symlink/non-regular targets return `unsupported_file_type` or `target_file_not_found`.
- Hidden CLI `--root` overrides for iCloud Drive search/get/content/apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can mutate one exact selected item.

## Synthetic Tests Required

- Preview success for `delete_file` without raw path or content hash disclosure.
- Apply success with metadata-only read-back proof, original absence proof, permanent unlink in a synthetic root, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, and `content_hash_returned:false`.
- Stale target-metadata refusal with no target mutation.
- Text target, symlink target, package member, and non-regular target refusals.
- Rollback regression where unverified staged identity returns `partial` without falsely claiming `mutation_applied:true` or `permanently_deleted:true`.
- CLI plan/apply coverage.
- MCP preview and apply coverage.

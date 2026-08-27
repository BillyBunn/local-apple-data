# V1.68 iCloud Drive Exact Text File Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. Existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` support `operation: delete_text` as a non-mutating preview, and the existing apply tools support the matching approved exact text-file delete.

## Scope

This gate approves permanently deleting one exact supported text-file selected by an opaque `icloud:file:v1:` handle. The caller must bind `expected-current-SHA-256` from exact selected file content metadata into the plan and apply request.

This is not approval for binary or document deletion, package mutation, symlink traversal, raw paths, broad delete, empty Trash, broad or unbounded recursive folder delete, folder delete outside the v1.67 exact selected-folder delete gate, unsupported suffixes, iCloud.com, browser automation, keychain access, private APIs, or network fallback.

## Preview Contract

The preview path is non-mutating:

- Uses `operation: delete_text`.
- Requires one exact supported text-file handle.
- Requires `expected_current_sha256`.
- Rejects parent handles, filenames, target names, target parents, and content input.
- Returns `mutation_applied:false`, `apply_available:true`, an approval fingerprint, and an approval token target.
- Returns target/proposed metadata only, including `expected_file_identity_sha256`, `permanent_delete:true`, `trash_fallback:"blocked"`, `folder_delete:"blocked"`, and `content_return:"blocked"`.
- Returns no file content, raw path, staging path, Trash path, raw device/inode/timestamp fields, or content hash.

## Apply Contract

The apply path must:

- Require the matching approval token and explicit confirmation.
- Recompute the root-aware preview before mutation.
- Bind the approval fingerprint to `expected_file_identity_sha256`, a SHA-256 over exact file identity metadata. This prevents stale approval replay against a recreated same-path/same-content file without exposing raw filesystem identifiers.
- Resolve only the exact opaque file handle.
- Re-read the selected file through fd-relative no-follow checks.
- Refuse unsupported suffixes, hidden/package/symlink traversal, directories, invalid UTF-8, stale content, and missing files.
- Verify the current content hash equals the approved `expected_current_sha256`.
- Use a hidden staging rename with fd-relative no-follow operations before permanent unlink.
- Perform identity verification in staging before removal.
- Re-read staged file content and hash before unlink.
- Permanently unlink only the identity-verified staged file.
- Verify original absence after unlink.
- Report success only after absence proof.

If exact file identity changes before apply, the recomputed preview changes and apply refuses with `invalid_approval_token` before mutation. If content hash changes after token validation but before unlink, apply rolls back or refuses with `current_content_changed`. If staged unlink fails and rollback succeeds, apply returns no mutation success. If rollback cannot be verified, apply returns `partial` and must not claim `verified_absent:true` or `permanently_deleted:true`.

## Read Back

Successful read_back returns:

- `original_present:false`
- `verified_absent:true`
- `permanently_deleted:true`
- `trash_path_returned:false`
- `staging_path_returned:false`
- `content_hash_returned:false`
- `content_text_returned:false`

It may return bounded safe metadata such as original filename, original kind, and content type. It must not return raw paths, staging paths, Trash paths, content text, content hash, raw filesystem identifiers, approval tokens, approval fingerprints, or local handle internals.

Hidden staging names are random-only, never include the original filename or extension, are skipped by metadata search, and are never returned.

## Synthetic Tests Required

- Adapter preview for `delete_text` returns metadata-only delete intent.
- Apply success removes one synthetic supported text file and proves original absence.
- Stale identity/token replay and stale content hash refuse without mutation.
- Unsupported target, package, symlink, directory, and invalid UTF-8 targets fail closed.
- Staged unlink failure rolls back when possible.
- Staged unlink plus rollback failure returns `partial` without false success and leaves only a random-only staging name if rollback cannot restore.
- CLI preview/apply coverage proves no content, content hash, raw Trash path, or staging path is logged or returned.
- MCP preview and apply coverage.
- Runtime verifier exercises source and MCP `delete_text` plan/apply success plus stale identity/content refusal.

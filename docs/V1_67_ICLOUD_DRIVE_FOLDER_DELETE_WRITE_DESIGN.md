# V1.67 iCloud Drive Exact Folder Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: delete_folder` as a non-mutating preview, and the existing apply tools support the matching approved exact selected-folder permanent delete operation.

## Scope

This tranche approves one narrow local filesystem operation: permanently delete one exact bounded iCloud Drive directory tree selected by an opaque `icloud:file:v1:` handle, with the current directory `metadata_sha256` and a private bounded source-tree binding included in the plan fingerprint.

Allowed:

- Delete one exact iCloud Drive directory selected by an opaque `icloud:file:v1:` handle.
- Delete regular-file and directory descendants inside the selected folder, capped by private tree limits.
- Return metadata-only absence proof.

Still blocked:

- No child listing in plan or apply output.
- No content text or content hash return.
- No raw paths.
- No hidden entries, packages, symlinks, special files, or unsupported tree entries.
- No broad folder delete, empty Trash, unbounded recursive delete, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback.

## Preview

`preview` resolves only the exact selected folder needed to build the private safety binding. It never mutates files.

- `delete_folder` requires one exact opaque source directory handle, `expected-current-SHA-256` from the selected folder metadata's `metadata_sha256`, no parent handle, no filename, and no content text.
- Preview builds a private source-tree binding from source metadata and descendant file/directory metadata. The binding is included only in the approval fingerprint, not returned.
- Preview refuses hidden, symlink, package, special-file, too-large, missing, or unsafe source trees.
- Preview returns `mutation_applied:false`, `apply_available:true`, `empty_folder_required:false`, `non_empty_allowed:true`, `recursive_delete:"bounded_private_tree"`, `source_tree_binding:"private"`, `trash_fallback:"blocked"`, `content_return:"blocked"`, no child listing, no raw path, no content text, and no approval token.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, source handle, metadata SHA-256, and private source-tree binding.
- Exact source folder resolution through metadata flow only.
- Directory source validation with symlink/package traversal refusal.
- Current source directory metadata SHA-256 check immediately before write.
- Current source tree check against the private approval binding immediately before write.
- Hidden staging rename with fd-relative no-follow operations before permanent removal.
- Identity verification in staging before removal.
- Staged tree verification against the approved bounded tree before removal.
- Bounded permanent removal of only the staged tree.

## Read Back

The apply response uses a `read_back` object. Read-back is metadata-only:

- `original_present:false` for successful delete.
- `verified_absent:true` for successful delete.
- `permanently_deleted:true`.
- Original opaque handle, original name, and kind `directory`.
- `empty_folder_confirmed` as a boolean.
- `non_empty_allowed:true`.
- `trash_path_returned:false`.
- `staging_path_returned:false`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Unexpected original presence, unreadable read-back, staging identity mismatch, tree mismatch, failed rollback, or unverified staged-tree removal returns `partial` or `error` with a bounded warning code. Partial failures must not claim `verified_absent:true` or `permanently_deleted:true`. No raw staging path, raw source path, child listing, content text, content hash, child hash, or Trash path is returned.

## Safety

- No raw local paths in normal output or logs.
- The selected folder tree is bound privately at plan time and rechecked at apply time before staging.
- Delete moves the exact verified directory into a hidden `.local-apple-data-delete-staging` child under the configured root, verifies the staged identity and bounded tree, then permanently removes only that staged tree.
- Hidden staging names are skipped by metadata search and are never returned.
- If the source tree changes before staged deletion, apply performs identity-checked rollback to the original name. If rollback succeeds, apply returns `error` with `current_metadata_changed` and `mutation_applied:false`. If rollback cannot verify or restore the staged directory, apply returns `partial` with a bounded warning and does not claim all safety properties.
- If staged-tree removal begins and cannot be completed with bounded proof, apply returns `partial` with `delete_unverified`, `mutation_applied:true`, `verified_absent:false`, `permanently_deleted:false`, and no staging path.
- No child listing.
- No file content inspection.
- No Trash fallback.
- No unbounded recursive folder operation.
- No file permanent delete outside the exact `delete-text` and `delete-file` gates.
- Symlink/package/hidden/unsupported tree-entry refusal before fd-relative staging.
- Stale folder metadata or tree state returns `current_metadata_changed` or `invalid_approval_token`.
- Hidden CLI `--root` overrides for iCloud Drive apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can permanently delete one exact selected folder tree, replace content, rename one exact folder, move one exact folder, copy one exact selected folder, move one exact text file to Trash, rename, or move one exact selected file.

## Synthetic Tests Required

- Preview success for `delete_folder`.
- Missing or wrong handles, expected-current-SHA-256, parent handles, filename, and content_text refusals.
- Apply success with original absence, verified absence, permanently-deleted flag, empty-folder boolean, non-empty support proof, and metadata-only read-back.
- Non-empty selected-folder apply success with no child-name/content/hash/path return.
- Stale metadata/tree refusal with no mutation.
- Hidden, package, symlink, unsupported-entry, and too-large tree refusal.
- File-handle refusal.
- Apply-time tree race is rolled back with identity-checked rename and returns error when rollback succeeds.
- Rollback failure after an apply-time tree race returns partial without exposing staging paths.
- Unexpected staged tree removal failure returns `partial` with `delete_unverified`, direct hidden-staging residue proof in synthetic tests, `verified_absent:false`, `permanently_deleted:false`, and no staging path.
- Symlink targets, package components, malformed handles, fabricated handles, missing expected metadata SHA-256, and invalid expected metadata SHA-256 are refused without staging.
- CLI plan/apply coverage through hidden synthetic root.
- MCP preview and apply coverage.
- Runtime verifier coverage for source and MCP paths.
- Redaction scan coverage proving no content text, raw paths, handles, metadata hashes, approval fingerprints, approval tokens, source names, staging names, child names, or target names leak through logs.

This release broadens exact folder permanent delete from empty-only to bounded selected-folder trees on top of the earlier iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact folder copy, trash-text, rename-text, copy-text, move-text, regular-file import/replace/trash/delete, and file rename/copy/move gates. Empty Trash, unbounded recursive delete, broad folder delete, binary/document generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

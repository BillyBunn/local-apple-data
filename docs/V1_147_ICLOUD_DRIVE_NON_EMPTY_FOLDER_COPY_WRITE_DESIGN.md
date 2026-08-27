# V1.147 iCloud Drive Non-Empty Folder Copy Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: copy_folder` as a non-mutating preview, and the existing apply tools support the matching approved exact selected-folder copy operation.

## Scope

This tranche broadens the v1.63 copy-folder gate from empty-only directories to one exact bounded selected-folder tree.

Allowed:

- Copy one exact iCloud Drive directory selected by an opaque `icloud:file:v1:` handle.
- Copy regular-file and directory descendants inside the selected folder, capped by private tree limits.
- Preserve the source folder and children.

Still blocked:

- No child listing in plan or apply output.
- No content text or content hash return.
- No raw paths.
- No hidden entries, packages, symlinks, special files, or unsupported tree entries.
- No broad folder copy, overwrite, unbounded recursive delete, empty Trash, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback.

## Preview

Preview validates bounded input shape and returns `mutation_applied:false`.

- `copy_folder` requires one exact opaque source directory handle, one exact opaque target parent directory handle, `expected-current-SHA-256` from source `metadata_sha256`, and an optional bounded target folder name.
- Preview builds a private source-tree binding from source metadata and descendant file/directory metadata. The binding is included only in the approval fingerprint, not returned.
- Preview refuses hidden, symlink, package, special-file, too-large, or unsafe source trees.
- Preview returns `empty_folder_required:false`, `non_empty_allowed:true`, `recursive_copy:"bounded_private_tree"`, `source_tree_binding:"private"`, `source_mutation:"blocked"`, `content_return:"blocked"`, no child listing, no raw path, no content text, and no approval token.

## Apply

Apply requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, handles, metadata SHA-256, target folder name, and private source-tree binding.
- Exact source and target-parent resolution through metadata flow only.
- Directory source and parent validation with symlink/package traversal refusal.
- Current source directory metadata SHA-256 check immediately before write.
- Descendant-parent refusal so a folder cannot be copied into itself or its own subtree.
- No-overwrite target creation.
- Bounded recursive copy with no-follow regular-file reads and exclusive target creates.
- Post-copy source tree recheck against the private approval binding.
- Target tree verification against the entries created by this apply.

## Read Back

Read-back is metadata-only:

- Source/target presence proof.
- Target opaque handle, target name, kind `directory`, and target `metadata_sha256`.
- `empty_folder_confirmed` as a boolean.
- `non_empty_allowed:true`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

If the source tree changes during apply and the created target can be safely identified, apply removes the created target and returns `error` with `current_metadata_changed` and `mutation_applied:false`. If cleanup cannot verify that the target tree contains only entries created by this apply, apply returns `partial` with `cleanup_unverified`, `mutation_applied:true`, no target handle, and no target metadata hash.

## Synthetic Tests Required

- Preview success for non-empty-allowed copy-folder.
- Apply success for non-empty copy-folder with child preservation and no content/hash/path/child-name return.
- Stale private tree token refusal.
- Apply-time source-tree race rollback.
- Cleanup failure partial reporting with no target handle or metadata hash.
- Cleaned target verification mismatch error reporting with
  `mutation_applied:false`; cleanup-failure partial reporting remains covered
  separately.
- Swapped created-child target directory refusal before nested file copy.
- Bounded child-name scan proof that does not materialize whole `scandir`
  output with `sorted(...)`.
- Hidden, package, symlink, too-large tree, stale metadata, existing target, self-parent, descendant-parent, malformed handle, wrong kind, invalid target name, and missing confirmation refusals.
- CLI and MCP coverage.
- Runtime verifier coverage for direct and MCP non-empty copy paths.
- Redaction scan coverage proving no content text, raw paths, child names, handles, metadata hashes, approval fingerprints, approval tokens, source names, or target names leak through logs.

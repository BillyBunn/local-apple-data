# V1.63 iCloud Drive Exact Empty Folder Copy Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: copy_folder` as a non-mutating preview, and the existing apply tools support the matching approved exact empty folder copy operation.

## Scope

This tranche approves one narrow local filesystem operation: copy one exact empty iCloud Drive directory selected by an opaque `icloud:file:v1:` handle to one exact target parent directory selected by an opaque `icloud:file:v1:` handle, with an optional approved target folder name.

This v1.63 tranche itself is not approval for non-empty folder copy, unbounded recursive folder copy, folder copy outside the exact selected-folder copy gate, file permanent delete, empty Trash, folder delete outside the exact selected-folder delete gate governed by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`, package mutation, symlink traversal, binary/document content generation or editing, regular-file mutation outside exact import-file, exact replace-file, exact trash-file, exact delete-file, or metadata-only rename/copy/move gates, raw paths, broad folder operations, iCloud.com, private iCloud APIs, browser sessions, keychain credentials, or network fallback. Later `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md` broadens this to bounded selected-folder trees.

## Preview

`preview` never resolves local paths and never mutates files. It validates only bounded input shape:

- Exact opaque source `icloud:file:v1:` directory handle.
- Exact opaque target parent `icloud:file:v1:` directory handle.
- `expected-current-SHA-256` from the selected folder metadata's `metadata_sha256`.
- Optional new folder name, with no path separators, hidden names, or package suffixes.
- No content text.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, and an approval fingerprint. It does not return child listings, raw paths, approval tokens, or unrelated filenames.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, source handle, target parent handle, metadata SHA-256, and optional new folder name.
- Exact source folder and target parent resolution through metadata flow only.
- Directory source and parent, no symlink or package traversal.
- Current source directory metadata SHA-256 check immediately before write.
- Empty-folder check immediately before write.
- No overwrite through fd-relative exclusive directory create.
- Source preservation proof after write.

Self-parent copies return `invalid_parent_handle`.

## Read Back

The apply response uses a `read_back` object. Read-back is metadata-only:

- `source_present:true` for successful copy.
- `target_present:true` for successful copy.
- Target opaque handle, target name, kind `directory`, and `metadata_sha256`.
- `copied:true`.
- `empty_folder_confirmed:true`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing target, unexpected source absence, unreadable read-back, target identity mismatch, or metadata mismatch returns `partial` or `error` with a bounded warning code. Target identity mismatch does not return a target handle or target metadata for the unverified replacement.

## Safety

- No raw local paths in normal output or logs.
- The empty-folder check immediately before write is repeated at apply time, after resolving the exact handle and before fd-relative target create.
- If a child appears in the source after the empty-folder check but after target creation, apply performs identity-checked cleanup with `_safe_rmdir_created_entry`. If cleanup succeeds, apply returns `error` with `folder_not_empty_after_apply` and leaves no copied target. If cleanup cannot verify or remove the created target safely, apply returns `partial` with `cleanup_unverified` and does not claim `copied:true`.
- Final success requires a second fd-relative target identity check against the directory created by this apply. Target replacement or unreadable target identity returns `partial` instead of `ok`, sets `copied:false`, and withholds target handle and metadata for the unverified replacement.
- No child listing.
- No file content inspection.
- No source mutation.
- No permanent deletion.
- No overwrite.
- No recursive folder operation.
- Symlink/package traversal refusal before fd-relative create.
- Stale folder metadata returns `current_metadata_changed`.
- Non-empty source returns `folder_not_empty`.
- Existing destination returns `target_exists`.
- Hidden CLI `--root` overrides for iCloud Drive apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can replace content, rename one exact empty folder, move one exact empty folder, copy one exact empty folder, move one exact text file to Trash, rename, or move one exact selected file.

## Synthetic Tests Required

- Preview success for `copy_folder`.
- Missing or wrong handles, parent handles, expected-current-SHA-256, content_text, and invalid target-name refusals.
- Apply success with source presence, target presence, copied flag, empty-folder proof, and metadata-only read-back.
- Stale metadata refusal with no target mutation.
- Non-empty folder refusal with no target mutation.
- Existing target refusal with no source mutation.
- Self-parent refusal with no source mutation.
- Apply-time non-empty source race is cleaned up with identity-checked `rmdir` and returns error when cleanup succeeds.
- Cleanup failure after an apply-time non-empty source race returns partial without claiming `copied:true`.
- Partial result when target identity changes after create, without target handle or metadata.
- CLI plan/apply coverage through hidden synthetic root.
- MCP preview and apply coverage.
- Runtime verifier coverage for source and MCP paths.
- Redaction scan coverage proving no content text, raw paths, handles, metadata hashes, approval fingerprints, approval tokens, source names, or target names leak through logs.

At the time of v1.63, the release allowed iCloud Drive create-text, append-text, replace-text, create-folder, exact empty folder rename, exact empty folder Trash, exact empty folder move, exact empty folder copy, trash-text, rename-text, copy-text, and move-text apply only. The later exact selected-folder permanent delete gate is governed by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`, later non-empty exact folder rename/move is governed by `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`, and later bounded selected-folder copy is governed by `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`. Unbounded recursive folder copy/delete, file permanent delete outside exact delete-text/delete-file gates, folder delete outside the exact selected-folder delete gate, empty Trash, binary/document generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

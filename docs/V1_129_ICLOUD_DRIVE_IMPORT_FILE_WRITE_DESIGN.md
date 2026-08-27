# V1.129 iCloud Drive Import File Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: import_file` as a non-mutating preview, and the existing apply tools support the matching approved exact import.

## Scope

This tranche approves copying one caller-selected local non-text non-package regular file into one exact selected iCloud Drive folder. In audit shorthand: one local regular-file import.

- `operation: import_file`: copy one local regular file to a non-existing target filename under one exact selected iCloud Drive parent folder.

This is not approval for binary/document content generation or editing, inline binary/document extraction, URL/network import, package import, directory import, broad folder import, recursive copy, overwrite, permanent delete, empty Trash, mutation of the source file, import from inside the configured iCloud Drive root, hidden-file write, raw target paths, path traversal, iCloud.com/private API/browser/keychain paths, or regular-file mutation outside this exact import gate and the v1.127 metadata-only rename/copy/move gates.

## Preview

`preview` never mutates files. It validates bounded input shape and source safety:

- Exact opaque `icloud:file:v1:` parent directory handle.
- Caller-selected local `source_file`.
- Optional bounded non-text non-package target filename; if omitted, the source basename is used.
- Source must be a readable regular file.
- Source leaf and ancestors must not be symlinks.
- Source must not be inside the configured iCloud Drive root.
- Source and target names must not be hidden, text-like, package-like, or path traversal.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, source basename, source byte size, and an approval fingerprint. It returns `source_path_returned:false`, `source_hash_returned:false`, `content_return:"blocked"`, and `content_hash_return:"blocked"`. It does not return the raw source path, source content hash, source identity hash, target local path, file content, content hash, approval token, or unrelated filenames.

The approval fingerprint uses private source identity and content hash binding so stale source-file changes invalidate the token without exposing those values.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, parent handle, stable parent identity, source file identity/content, and target filename.
- Exact target parent resolution through metadata flow only.
- Non-text non-package regular source file, no source symlink/package traversal.
- Source outside the configured iCloud Drive root.
- No overwrite through exclusive target create.
- Target write through fd-relative no-follow filesystem operations.

Apply opens the source parent without following symlinks, opens the target parent from the iCloud Drive root without following symlinks, streams bytes into an exclusive target file, verifies target byte count and internal digest against the approved source content hash, then rechecks source identity after copy. If source identity changes during copy, apply removes only the created target after verifying target identity; otherwise it returns `partial`.

All apply paths use no-overwrite target proof, source preservation proof, and metadata-only target read-back. They return no inline content, no content hash, no raw source path, and no source hash: no source path/hash return and no content hash return.

## Read Back

Read-back includes:

- `imported:true`.
- `target_present:true`.
- Target opaque handle, target filename, size, extension, and target `metadata_sha256`.
- `source_path_returned:false`.
- `source_hash_returned:false`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing target, unreadable read-back, unexpected target kind, or changed source during copy returns `partial` or `error` with structured warnings and no path/hash/content disclosure.

## Safety

- No raw local source paths in normal output or logs.
- No source or target content hash in normal output or logs.
- No inline content.
- No overwrite.
- No source mutation.
- No import from inside the configured iCloud Drive root; use existing in-root copy/move gates instead.
- Text files must use the existing text-file create/append/replace/rename/copy/move gates.
- Package and symlink traversal refusal before and during fd-relative operations.
- Stale source token refusal (`stale source token`) returns `invalid_approval_token`.
- Source drift during copy returns `source_file_changed` with target cleanup when identity proof permits.
- Existing destination returns `target_exists`.
- Hidden CLI `--root` overrides for iCloud Drive search/get/content/apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can create, replace, trash, delete, rename, copy, move, or import one exact selected item.

## Synthetic Tests Required

- Preview success for `import_file` without raw source path or source hash disclosure.
- Missing source, source is inside the configured iCloud Drive root, text-like source, package-like source, symlink source, bad parent handle, and conflicting inputs refusals.
- Apply success with metadata-only read-back proof and source preservation.
- Stale source-token refusal with no target mutation.
- Existing-target refusal with no source or target mutation.
- CLI plan/apply coverage.
- MCP preview and apply coverage.
- Runtime verifier coverage for direct and MCP import-file, source-byte preservation, source preservation, stale-token refusal, and source path/hash non-disclosure.
- Redaction scan coverage proving no content text, content hash, source path, source hash, target path, handles, approval fingerprints, or approval tokens leak through logs.

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only. Permanent delete outside the exact delete gates, empty Trash, recursive folder creation, folder copy outside the exact empty-folder copy gate, non-empty/recursive folder copy, binary/document content generation, binary/document content editing, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

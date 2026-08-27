# V1.130 iCloud Drive Replace File Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: replace_file` as a non-mutating preview, and the existing apply tools support the matching approved exact replace.

## Scope

This tranche approves replacing one exact existing iCloud Drive non-text non-package regular file with bytes from one caller-selected local non-text non-package regular file outside the configured iCloud Drive root.

- `operation: replace_file`: replace the content of one exact regular file handle while preserving the target filename and parent folder.

This is not approval for inline binary/document content generation, URL/network import, package mutation, directory import, broad folder import, recursive copy, target rename, source mutation, import from inside the configured iCloud Drive root, hidden-file write, raw target paths, path traversal, iCloud.com/private API/browser/keychain paths, or regular-file mutation outside this exact replace-file gate plus the approved import-file and metadata-only rename/copy/move gates.

## Preview

`preview` never mutates files. It validates bounded input shape and source safety:

- Exact opaque `icloud:file:v1:` target regular-file handle.
- expected target `metadata_sha256` from recent iCloud Drive metadata.
- Caller-selected local `source_file`.
- Source must be a readable regular file.
- Source leaf and ancestors must not be symlinks.
- Source must not be inside the configured iCloud Drive root.
- Source must not be hidden, text-like, package-like, or path traversal.
- No parent handle, target filename, or inline content text.

Preview returns `mutation_applied:false`, `apply_available:true`, target metadata, idempotency metadata, source basename, source byte size, and an approval fingerprint. It returns `source_path_returned:false`, `source_hash_returned:false`, `content_return:"blocked"`, and `content_hash_return:"blocked"`. It does not return the raw source path, source content hash, source identity hash, target local path, file content, content hash, approval token, or unrelated filenames.

The approval fingerprint uses private source identity and content hash binding so stale source-file changes invalidate the token without exposing those values.

## Apply

`apply` requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply=true`.
- Recomputed plan matching operation, target handle, expected target metadata, and source file identity/content.
- Exact target resolution through metadata flow only.
- Current target metadata SHA-256 match before replacement.
- Non-text non-package regular source file, no source symlink/package traversal.
- Source outside the configured iCloud Drive root.
- source and target extensions must match.
- Target write through fd-relative no-follow filesystem operations.

Apply opens the source parent without following symlinks, opens the target parent from the iCloud Drive root without following symlinks, streams bytes into a private hidden temporary file beside the target, verifies byte count and digest against the approved source content hash, rechecks source identity, rechecks target metadata, then atomically replaces the target. It then verifies the replaced target identity and bytes.

All apply paths use exact target metadata proof, target metadata drift refusal, source preservation proof, byte replacement proof, and metadata-only target read-back. They return no inline content, no content hash, no raw source path, and no source hash: no source path/hash return and no content hash return.

## Read Back

Read-back includes:

- `replaced:true`.
- `target_present:true`.
- Target opaque handle, target filename, size, extension, and target `metadata_sha256`.
- `source_path_returned:false`.
- `source_hash_returned:false`.
- `content_text_returned:false`.
- `content_hash_returned:false`.

Missing target, unreadable read-back, unexpected target kind, changed source during copy, stale target metadata, or extension mismatch returns `partial` or `error` with structured warnings and no path/hash/content disclosure.

## Safety

- No raw local source paths in normal output or logs.
- No source or target content hash in normal output or logs.
- No inline content.
- No target rename or source mutation.
- No import from inside the configured iCloud Drive root.
- Text files must use the existing text-file create/append/replace/rename/copy/move gates.
- Package and symlink traversal refusal before and during fd-relative operations.
- stale source token returns `invalid_approval_token`.
- Stale target metadata returns `current_metadata_changed`.
- Source drift during copy returns `source_file_changed`.
- Extension mismatch returns `unsupported_file_type`.
- Hidden CLI `--root` overrides for iCloud Drive search/get/content/apply require `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`; normal CLI use cannot point the iCloud Drive surface at arbitrary roots.

MCP apply remains destructive, non-read-only, non-idempotent, and closed-world because the same static iCloud Drive apply tool can mutate one exact selected item.

## Synthetic Tests Required

- Preview success for `replace_file` without raw source path or source hash disclosure.
- Missing source, source is inside the configured iCloud Drive root, text-like source, package-like source, symlink source, bad target handle, conflicting parent/filename/content inputs, and extension-mismatch refusals.
- Apply success with metadata-only read-back proof and source preservation.
- Stale source-token refusal with no target mutation.
- Stale target-metadata refusal with no target replacement.
- CLI plan/apply coverage.
- MCP preview and apply coverage.
- Runtime verifier coverage for direct and MCP replace-file, byte replacement, source preservation, stale-token refusal, and source path/hash non-disclosure.
- Redaction scan coverage proving no content text, content hash, source path, source hash, target path, handles, approval fingerprints, or approval tokens leak through logs.

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only. Permanent delete outside the exact delete gates, empty Trash, recursive folder creation, folder copy outside the exact selected-folder copy gate, unbounded folder copy, inline binary/document content generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

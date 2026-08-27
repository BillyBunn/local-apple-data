# v1.51 iCloud Drive Replace Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: replace_text` as a non-mutating preview, and the existing apply tools support the matching approved replace operation.

This document defines the third iCloud Drive write lane: replace the entire strict UTF-8 contents of one supported text-like file selected by exact opaque `icloud:file:v1:` handle, with preview as the default behavior, expected-current-SHA-256 drift refusal on apply, same-directory temporary-file replacement, and independent read_back hash verification after apply.

## Scope

Allowed:

- Replace bounded text in one supported text-like file.
- Require an exact opaque file handle returned by iCloud Drive metadata search.
- Require the caller to fetch exact content first and provide the current normalized content SHA-256.
- Refuse to apply if the file content changed after planning.
- Write through a same-directory temporary file and `os.replace` after an immediate pre-replace content SHA recheck.
- Return read-back metadata and replacement content hash after apply.

Blocked:

- Raw local paths, hidden files, symlinks, package traversal, broad folder writes, recursive operations, and unsupported file types.
- Rename, move, copy, delete, binary/document generation, durable content caches, and partial document-format editing.
- Broad content search, arbitrary document extraction, background indexing, and network iCloud fetch.

## Tool Contract

Every iCloud Drive replace mutation keeps the same three-step shape:

- `preview`: validate inputs and return the planned replacement without touching iCloud Drive.
- `apply`: perform exactly the approved replacement after explicit user approval.
- `read_back`: verify the resulting state through the normal local iCloud Drive adapter.

The apply payload requires an approval token generated from the preview. The token binds the operation, exact file handle, expected current content SHA-256, replacement content hash, and idempotency key so an agent cannot replace with different text using a stale preview.

The read_back payload reads the changed file through the same local adapter path and returns bounded metadata plus `content_chars` and `content_sha256`. Apply returns `partial` with `read_back_mismatch` if the read-back hash does not match the approved replacement hash.

## Implemented Preview

Implemented preview tools:

- CLI: `local-apple-data icloud-drive plan --operation replace-text`
- MCP: `icloud_drive_plan_change(operation="replace_text", ...)`

Preview requirements:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Require an exact opaque `icloud:file:v1:` file handle from iCloud Drive search output.
- Require `expected_current_sha256` as a 64-character lowercase or uppercase SHA-256 hex digest.
- Require bounded non-empty `content_text`.
- Include `replace_content_sha256` in the transient preview payload.
- Mark append and delete as blocked in the preview.
- Do not resolve the handle, read iCloud Drive, replace files, or mutate iCloud Drive.
- Do not log handles, content, content hashes, filenames, raw paths, or approval fingerprints.

## Implemented Apply

Implemented apply tools:

- CLI: `local-apple-data icloud-drive apply --operation replace-text`
- MCP: `icloud_drive_apply_change(operation="replace_text", ...)`

Apply requirements:

- Return `mode: "apply"`.
- Require a matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the exact opaque file handle internally.
- Keep the resolved target under the configured iCloud Drive root.
- Reject directories, hidden files, symlinks, package traversal, binary files, invalid UTF-8, unsupported suffixes, missing targets, and unreadable files.
- Normalize current text the same way exact content retrieval does before computing the current SHA-256.
- Refuse to replace when the current SHA-256 differs from `expected_current_sha256`, except an already-applied retry where the current hash equals the approved replacement hash.
- Replace bounded UTF-8 text only after all checks pass.
- Use a same-directory temporary file and `os.replace` so the visible target switches to the approved content after writing and flushing, with no-follow reads and a final pre-replace current-SHA check.
- Read back the changed file and return the new normalized content SHA-256.
- Return `partial` with `read_back_mismatch` if read-back does not match the approved replacement hash.
- Do not log handles, content, content hashes, filenames, raw paths, approval fingerprints, or approval tokens.

## Implementation Boundary

Use the existing Python iCloud Drive adapter for this operation:

- iCloud Drive files are exposed locally through the filesystem under CloudDocs.
- Python `pathlib`, `tempfile`, no-follow `os.open` reads, and `os.replace` are sufficient for bounded UTF-8 replacement and post-replace read-back within this local filesystem lane.
- This is not a kernel-level compare-and-swap API. The implementation refuses observed current-content drift before replacement and immediately before `os.replace`, but uncooperative external writers can still race between the final check and the directory-entry replacement. Callers must re-read exact content after uncertain outcomes and avoid live use on actively edited files.
- Adding Swift would add process overhead and another failure mode without improving privacy, performance, or durability for this filesystem operation.
- Swift remains the right boundary for EventKit, Contacts, and PhotoKit operations.

## Inputs

- `operation`: `replace_text`.
- `handle`: exact opaque `icloud:file:v1:` handle for a supported text-like file returned by iCloud Drive filename search.
- `expected_current_sha256`: normalized content hash returned by exact iCloud Drive content retrieval.
- `content_text`: non-empty UTF-8 replacement text, normalized to LF line endings and capped at 12000 characters.
- `approval_token`: exact token from the matching preview.
- `confirm_apply`: explicit boolean confirmation.

All inputs are bounded. Existing file contents and replacement text are used only to compute the approval fingerprint, check current state, perform the approved replacement, and verify read-back; they are not logged.

## Gates

Before any additional apply-capable iCloud Drive operation is exposed:

- This document or a later operation-specific design doc must be updated.
- `docs/MUTATION_GATES.md`, `docs/WRITE_TOOL_ROADMAP.md`, and `docs/CAPABILITY_MATRIX.md` must name the approved operation and blocked operations.
- `scripts/audit_mutation_gates.py` must prove no extra write-like CLI/MCP tool names or iCloud Drive plan operations are exposed.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `icloud_drive_plan_change` remains read-only.
- `icloud_drive_apply_change` uses destructive non-read-only MCP annotations because the same static tool can replace existing file contents.
- Runtime smoke must prove replace plan/apply success, stale-hash refusal, read-back hash change, and destructive write annotation.
- Redaction scans must prove no content, handles, content hashes, raw paths, or approval artifacts are persisted.

## Idempotency And Partial Failure

The apply path is retry-aware:

- A retry before apply recomputes the same plan and token.
- A retry after successful replacement with the same expected current hash and same approved replacement content returns `already_applied` with `mutation_applied:false`.
- A retry after any other current-content drift refuses with `current_content_changed`, forcing the caller to re-read exact content and plan again.
- If the replace call returns an uncertain status, the caller must re-read exact content by handle and compare content hashes before retrying.
- If read-back hash verification fails, apply returns `partial` with `read_back_mismatch`.

## Warning Codes

Stable warning codes:

- `invalid_operation`
- `invalid_handle`
- `missing_required_field`
- `invalid_expected_sha256`
- `input_too_large`
- `unsupported_file_type`
- `missing_apply_confirmation`
- `invalid_approval_token`
- `icloud_drive_unavailable`
- `target_file_not_found`
- `target_outside_root`
- `read_error`
- `current_content_changed`
- `already_applied`
- `replace_error`
- `read_back_unavailable`
- `read_back_mismatch`

Warnings must use safe generic messages and no raw local paths or exception text.

## Synthetic Tests Required

Before exposure, the iCloud Drive replace implementation must add:

- Preview success tests for exact-handle replacement planning.
- Preview rejection tests for missing file handle, missing expected hash, bad hash, unexpected parent/filename, empty content, oversized content, and invalid handles.
- Apply rejection tests for missing confirmation, invalid token, missing target, unsupported file type, invalid UTF-8, package traversal, symlink targets, unreadable target, hash drift, and unavailable root.
- Apply success tests proving bounded replacement and read-back hash verification.
- Already-applied retry coverage.
- Read-back mismatch coverage.
- CLI tests for `icloud-drive plan/apply --operation replace-text`.
- MCP wrapper and annotation tests.
- Runtime verifier coverage for replace plan/apply success with exact replacement-hash proof, stale-hash refusal, and no mutation on stale apply.
- Redacted log tests proving no handle, content, hash, raw path, or approval-token persistence.
- Release-readiness and write-design gate coverage.

## Current Non-Goals

The v1.51 release allowed iCloud Drive create-text, append-text, and replace-text apply only. Later iCloud Drive create-folder is governed separately by `docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md`, trash-text is governed separately by `docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md`, file rename/copy/move is governed separately by `docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md`, folder rename by `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md`, exact folder Trash by `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md`, folder move by `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md`, exact selected-folder copy by `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md`, exact selected-folder delete by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`, and non-empty folder rename/move by `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`. File permanent delete outside exact delete-text/delete-file gates, empty Trash, unbounded recursive folder copy/delete, binary/document generation, recursive folder writes, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

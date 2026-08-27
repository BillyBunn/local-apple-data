# v1.18 iCloud Drive Append Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools now support `operation: append_text` as a non-mutating preview, and the existing apply tools now support the matching approved append operation.

This document defines the second iCloud Drive write lane: append bounded UTF-8 text to one supported text-like file selected by exact opaque `icloud:file:v1:` handle, with preview as the default behavior, expected-current-SHA-256 drift refusal on apply, same-directory temp replacement that preserves existing file bytes and adds normalized appended text, a final pre-replace SHA recheck, and independent read_back verification after apply.

## Scope

Allowed:

- Append bounded text to one supported text-like file.
- Require an exact opaque file handle returned by iCloud Drive metadata search.
- Require the caller to fetch exact content first and provide the current normalized content SHA-256.
- Refuse to apply if the file content changed after planning.
- Return read-back metadata and new content hash after apply.

Blocked:

- Raw local paths, hidden files, symlinks, package traversal, broad folder writes, recursive operations, and unsupported file types.
- Overwrite outside the exact replace-text gate, rename/copy/move outside v1.54 exact text-file gates, delete outside the exact trash-text gate, binary/document generation, and durable content caches.
- Broad content search, arbitrary document extraction, and background indexing.

## Tool Contract

Every iCloud Drive append mutation keeps the same three-step shape:

- `preview`: validate inputs and return the planned append without touching iCloud Drive.
- `apply`: perform exactly the approved append after explicit user approval.
- `read_back`: verify the resulting state through the normal local iCloud Drive adapter.

The apply payload requires an approval token generated from the preview. The token binds the operation, exact file handle, expected current content SHA-256, append content hash, and idempotency key so an agent cannot append different text with a stale preview.

The read_back payload reads the changed file through the same local adapter path and returns bounded metadata plus `content_chars` and `content_sha256`. It must not trust the write call alone.

## Implemented Preview

Implemented preview tools:

- CLI: `local-apple-data icloud-drive plan --operation append-text`
- MCP: `icloud_drive_plan_change(operation="append_text", ...)`

Preview requirements:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Require an exact opaque `icloud:file:v1:` file handle from iCloud Drive search output.
- Require `expected_current_sha256` as a 64-character lowercase or uppercase SHA-256 hex digest.
- Require bounded non-empty `content_text`.
- Include `append_content_sha256` in the transient preview payload.
- Do not resolve the handle, read iCloud Drive, append files, or mutate iCloud Drive.
- Do not log handles, content, content hashes, filenames, or approval fingerprints.

## Implemented Apply

Implemented apply tools:

- CLI: `local-apple-data icloud-drive apply --operation append-text`
- MCP: `icloud_drive_apply_change(operation="append_text", ...)`

Apply requirements:

- Return `mode: "apply"`.
- Require a matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the exact opaque file handle internally.
- Keep the resolved target under the configured iCloud Drive root.
- Reject directories, hidden files, symlinks, binary files, unsupported suffixes, missing targets, and unreadable files.
- Normalize current text the same way exact content retrieval does before computing the current SHA-256.
- Refuse to append when the current SHA-256 differs from `expected_current_sha256`.
- Write original existing bytes plus normalized appended text through a same-directory temporary file and final no-follow expected-SHA recheck so concurrent drift is refused before replacement; existing file bytes and line endings are not canonicalized by append.
- Read back the changed file and return the new normalized content SHA-256.
- Return `partial` with `read_back_mismatch` if read-back does not match the approved post-append hash.
- Do not log handles, content, content hashes, filenames, raw paths, approval fingerprints, or approval tokens.

## Implementation Boundary

Use the existing Python iCloud Drive adapter for this operation:

- iCloud Drive files are exposed locally through the filesystem under CloudDocs.
- Python filesystem APIs, no-follow reads, same-directory temp files, and `os.replace` are sufficient for bounded UTF-8 append semantics and post-append read-back.
- Adding Swift would add process overhead and another failure mode without improving privacy, performance, or durability for this filesystem operation.
- Swift remains the right boundary for EventKit, Contacts, and PhotoKit operations.

## Inputs

- `operation`: `append_text`.
- `handle`: exact opaque `icloud:file:v1:` handle for a supported text-like file returned by iCloud Drive filename search.
- `expected_current_sha256`: normalized content hash returned by exact iCloud Drive content retrieval.
- `content_text`: non-empty UTF-8 text, normalized to LF line endings and capped at 12000 characters.
- `approval_token`: exact token from the matching preview.
- `confirm_apply`: explicit boolean confirmation.

All inputs are bounded. File contents and append text are used only to compute the approval fingerprint, check current state, and append the approved text; they are not logged.

## Gates

Before any additional apply-capable iCloud Drive operation is exposed:

- This document or a later operation-specific design doc must be updated.
- `docs/MUTATION_GATES.md`, `docs/WRITE_TOOL_ROADMAP.md`, and `docs/CAPABILITY_MATRIX.md` must name the approved operation and blocked operations.
- `scripts/audit_mutation_gates.py` must still prove no extra write-like CLI/MCP tool names are exposed.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `icloud_drive_plan_change` remains read-only; `icloud_drive_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- redaction scans must prove no content, handles, content hashes, raw paths, or approval artifacts are persisted.

## Idempotency And Partial Failure

The apply path must be retry-safe:

- A retry before apply recomputes the same plan and token.
- A retry after successful append with the same expected current hash refuses with `current_content_changed`, forcing the caller to re-read exact content and plan again.
- A concurrent edit between the first current-hash check and the visible update is refused by a second no-follow current-hash check immediately before `os.replace`; the temp file is removed on refusal.
- Existing bytes are preserved during append even though current-state SHA and read-back SHA are computed from normalized text, matching exact content retrieval semantics.
- If the append call returns an uncertain status, the caller must re-read exact content by handle and compare content hashes before retrying.

Append is intentionally not made silently idempotent because that would require storing or replaying prior content. Hash drift refusal is safer and easier to audit.

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
- `append_error`
- `read_back_unavailable`
- `read_back_mismatch`

Warnings must use safe generic messages and no raw local paths or exception text.

## Synthetic Tests Required

Before exposure, the iCloud Drive append implementation must add:

- Preview success tests for exact-handle append planning.
- Preview rejection tests for missing file handle, missing expected hash, bad hash, unexpected parent/filename, empty content, oversized content, and invalid handles.
- Apply rejection tests for missing confirmation, invalid token, missing target, unsupported file type, invalid UTF-8, unreadable target, symlink/package traversal, hash drift, concurrent drift immediately before replace, and unavailable root.
- Apply success tests proving bounded append and read-back hash verification.
- Partial-read-back tests for `read_back_unavailable` and `read_back_mismatch`.
- CLI tests for `icloud-drive plan/apply --operation append-text`.
- Runtime verifier coverage for append plan/apply success and stale-hash refusal.
- Redacted log tests proving no handle, content, hash, raw path, or approval-token persistence.
- MCP annotation tests proving write tools are not marked read-only.
- Release-readiness and write-design gate coverage.

## Current Non-Goals

The v1.18 release allowed iCloud Drive create-text and append-text apply only. Later iCloud Drive replace-text is governed separately by `docs/V1_51_ICLOUD_DRIVE_REPLACE_WRITE_DESIGN.md`, create-folder is governed separately by `docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md`; create-folder-path is governed separately by `docs/V1_157_ICLOUD_DRIVE_FOLDER_PATH_CREATE_WRITE_DESIGN.md`, trash-text is governed separately by `docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md`, rename/copy/move is governed separately by `docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md`, exact folder rename by `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md` plus `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`, exact folder Trash by `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md` plus `docs/V1_146_ICLOUD_DRIVE_NON_EMPTY_FOLDER_TRASH_WRITE_DESIGN.md`, exact folder move by `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` plus `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`, exact selected-folder copy by `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md` plus `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`, and exact selected-folder delete by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`. File permanent delete outside exact delete-text/delete-file gates, empty Trash, unbounded recursive folder copy/delete, binary/document generation, recursive folder writes, raw path writes, hidden-file writes, symlink/package traversal, content replacement outside the exact replace-text gate, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

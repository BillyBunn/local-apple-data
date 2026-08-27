# v1.53 iCloud Drive Trash Write Design

Date: 2026-06-21
Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: trash_text` as a non-mutating preview, and the existing apply tools support the matching approved recoverable Trash operation.

This document defines the fifth iCloud Drive write lane: move one exact supported text-like file selected by opaque `icloud:file:v1:` handle to a recoverable Trash location, with preview as the default behavior, expected-current-SHA-256 drift refusal on apply, symlink/package traversal refusal, no folder or binary deletion, no permanent unlink, and independent read_back absence proof after apply.

## Scope

Allowed:

- One exact `icloud:file:v1:` file handle returned by iCloud Drive metadata search.
- Supported text-like suffixes already accepted by iCloud Drive content retrieval.
- `expected_current_sha256` from exact-handle content retrieval.
- Recoverable Trash move only.
- Synthetic tests using a temporary `LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT`.

Forbidden:

- Permanent delete, `unlink`, empty Trash, broad/bulk delete, recursive delete, folder delete, binary/document delete, package traversal, symlink traversal, raw path input, hidden-file writes, rename/copy/move outside v1.54 exact text-file gates, and iCloud.com/browser/private API paths.
- Returning raw Trash paths, raw source paths, file content, approval tokens, or reusable identifiers.

## Planning

- CLI: `local-apple-data icloud-drive plan --operation trash-text`
- MCP: `icloud_drive_plan_change(operation="trash_text", ...)`
- Require an exact opaque `icloud:file:v1:` handle.
- Require `expected_current_sha256`.
- Reject parent handles, filenames, and unexpected `content_text`.
- Return `mutation_applied:false`, `apply_available:true`, deterministic idempotency key, and approval fingerprint.
- Preview says `move_to_trash:true`, `permanent_delete:"blocked"`, `folder_delete:"blocked"`, and `content_return:"blocked"`.

## Apply

- CLI: `local-apple-data icloud-drive apply --operation trash-text`
- MCP: `icloud_drive_apply_change(operation="trash_text", ...)`
- Require matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Require explicit `confirm_apply:true`.
- Recompute the plan before mutation.
- Resolve the exact opaque handle internally.
- Refuse directories, binary files, unsupported suffixes, invalid UTF-8, package members, symlinks, and current-content drift.
- Re-read and recheck the normalized current SHA-256 before the Trash move.
- Move by fd-based no-follow atomic swap into a reserved recoverable Trash target: the user's macOS Trash for the default real iCloud Drive root, and a hidden synthetic Trash under test roots.
- Verify the moved file's post-swap SHA-256, swap back and fail closed on drift, then remove only the empty source reservation after proof.
- Never permanently delete the selected file.
- Read back absence through the original opaque handle after apply.
- If source-reservation cleanup fails after post-swap proof, return `partial` with `mutation_applied:true`, `read_back_mismatch`, `trashed:true`, and `original_present:true` rather than falsely reporting no mutation.

## Result Shape

Apply success returns:

- `operation: "trash_text"`
- `mutation_applied:true`
- `privacy.content_inspected:true`
- `read_back.handle`: original opaque handle
- `read_back.name`: original filename only
- `read_back.kind:"file"`
- `read_back.content_sha256`: the approved current content hash
- `read_back.original_present:false`
- `read_back.trashed:true`
- `read_back.trash_path_returned:false`

Apply output never returns file content, raw paths, Trash paths, approval tokens, or source directory names.

## Failure Modes

- `invalid_handle`
- `missing_required_field`
- `invalid_expected_sha256`
- `unexpected_create_target`
- `unexpected_content_text`
- `target_file_not_found`
- `unsupported_file_type`
- `current_content_changed`
- `read_error`
- `trash_error`
- `read_back_mismatch`

All warnings stay generic and redacted.

## MCP Annotations

`icloud_drive_plan_change` remains read-only.

`icloud_drive_apply_change` remains destructive, non-read-only, non-idempotent, and closed-world because the same static tool can replace text and move one exact text file to Trash.

## Synthetic Tests Required

- Preview success for `trash_text`.
- Missing handle and missing/invalid SHA refusal.
- Unexpected parent/filename/content-text refusal.
- Successful apply moves the exact text file to synthetic Trash, returns no raw Trash path, and proves original handle absence.
- Stale SHA refusal leaves the original file in place and creates no Trash item.
- Unsupported binary and invalid UTF-8 text-like targets are refused.
- Package-member and symlink-swap targets are refused.
- Race between preflight read and Trash move is refused by post-swap SHA verification and swap-back.
- Source-reservation cleanup failure after verified move returns partial mutation proof instead of a false no-mutation error.
- CLI plan/apply coverage for `trash-text`.
- MCP preview and apply coverage for `trash_text`.
- Runtime verifier coverage for source and installed-cache proof.

## Boundary

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact empty folder copy, trash-text, rename-text, copy-text, and move-text apply only. Rename/copy/move is governed separately by `docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md`; exact folder rename by `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md` plus `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`; exact folder Trash by `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md`; exact folder move by `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` plus `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`; and exact empty folder copy by `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md`. iCloud Drive permanent delete, empty Trash, recursive folder creation, folder copy outside the exact empty-folder copy gate, non-empty/recursive folder copy or delete, binary/document generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

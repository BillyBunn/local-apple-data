# v1.52 iCloud Drive Folder Create Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support `operation: create_folder` as a non-mutating preview, and the existing apply tools support the matching approved folder-create operation.

This document defines the fourth iCloud Drive write lane: create one child folder under an exact opaque `icloud:file:v1:` parent directory handle, with preview as the default behavior, exclusive no-follow mkdir on apply, symlink/package traversal refusal, and independent metadata read_back after apply.

## Scope

Allowed:

- Create one non-hidden folder under one exact selected iCloud Drive parent directory.
- Require an exact opaque parent folder handle returned by iCloud Drive metadata search.
- Reject raw paths, path separators, package names, hidden names, symlink traversal, and existing non-directory targets.
- Return read-back metadata for the created directory after apply.
- Treat a retry against an already-created directory with the same name as `already_applied` with `mutation_applied:false`.

Blocked:

- Raw local paths, hidden folders, symlinks, package traversal, recursive folder writes, and arbitrary directory trees.
- Rename, move, copy, delete, binary/document generation, file content writes, durable content caches, and broad content search.
- Network iCloud fetch, iCloud.com, private APIs, browser automation, or Keychain use.

## Tool Contract

Every iCloud Drive folder-create mutation keeps the same three-step shape:

- `preview`: validate inputs and return the planned folder creation without touching iCloud Drive.
- `apply`: perform exactly the approved mkdir after explicit user approval.
- `read_back`: verify the resulting directory metadata through the normal local iCloud Drive adapter.

The apply payload requires an approval token generated from the preview. The token binds the operation, exact parent handle, stable parent identity, folder name, blocked overwrite/delete semantics, and idempotency key so an agent cannot create a different folder using a stale preview or same-path recreated parent.

The read_back payload returns only metadata. It does not read file contents and must return `privacy.content_inspected:false`.

## Implemented Preview

Implemented preview tools:

- CLI: `local-apple-data icloud-drive plan --operation create-folder`
- MCP: `icloud_drive_plan_change(operation="create_folder", ...)`

Preview requirements:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Require an exact opaque `icloud:file:v1:` parent folder handle from iCloud Drive search output.
- Require a bounded folder name in the existing `filename` field.
- Reject hidden names, path separators, package suffixes, unsupported characters, and unexpected `content_text`.
- Mark content, overwrite, and delete as blocked in the preview.
- Do not resolve the handle, read iCloud Drive, create folders, or mutate iCloud Drive.
- Do not log handles, names, raw paths, approval fingerprints, or approval tokens.

## Implemented Apply

Implemented apply tools:

- CLI: `local-apple-data icloud-drive apply --operation create-folder`
- MCP: `icloud_drive_apply_change(operation="create_folder", ...)`

Apply requirements:

- Return `mode: "apply"`.
- Require a matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the exact opaque parent directory handle internally.
- Keep the resolved target under the configured iCloud Drive root.
- Reject missing parents, non-directory parents, symlink parents, package traversal, hidden/package target names, existing files, existing symlinks, and unsupported names.
- Use a parent directory fd opened without following symlinks.
- Use exclusive `mkdir` relative to that parent fd and flush the parent directory.
- Return `already_applied` with `mutation_applied:false` when the exact directory already exists.
- Read back directory metadata only; do not read file content.
- Do not log handles, names, raw paths, approval fingerprints, or approval tokens.

## Implementation Boundary

Use the existing Python iCloud Drive adapter for this operation:

- iCloud Drive directories are exposed locally through the filesystem under CloudDocs.
- Python `os.open(..., O_DIRECTORY|O_NOFOLLOW)`, `os.stat(..., follow_symlinks=False)`, and `os.mkdir(..., dir_fd=...)` are sufficient for bounded single-directory creation and metadata read-back within this local filesystem lane.
- This is not a recursive folder-tree writer. It creates exactly one child directory inside an exact parent handle.
- Adding Swift would add process overhead and another failure mode without improving privacy, performance, or durability for this filesystem operation.
- Swift remains the right boundary for EventKit, Contacts, and PhotoKit operations.

## Inputs

- `operation`: `create_folder`.
- `parent_handle`: exact opaque `icloud:file:v1:` handle for a directory returned by iCloud Drive filename search.
- `filename`: new folder name. The field name is retained for CLI/API compatibility.
- `approval_token`: exact token from the matching preview.
- `confirm_apply`: explicit boolean confirmation.

All inputs are bounded. Folder names are used only to compute the approval fingerprint, create the approved child directory, and verify read-back; they are not logged.

## Gates

Before any additional apply-capable iCloud Drive operation is exposed:

- This document or a later operation-specific design doc must be updated.
- `docs/MUTATION_GATES.md`, `docs/WRITE_TOOL_ROADMAP.md`, and `docs/CAPABILITY_MATRIX.md` must name the approved operation and blocked operations.
- `scripts/audit_mutation_gates.py` must prove no extra write-like CLI/MCP tool names or iCloud Drive plan operations are exposed.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `icloud_drive_plan_change` remains read-only.
- `icloud_drive_apply_change` uses destructive non-read-only MCP annotations because the same static tool can replace existing file contents.
- Runtime smoke must prove create-folder plan/apply success and directory metadata read-back.
- Redaction scans must prove no handles, raw paths, folder names, approval artifacts, or content are persisted.

## Idempotency And Partial Failure

The apply path is retry-aware:

- A retry before apply recomputes the same plan and token.
- A retry after successful folder creation returns `already_applied` with `mutation_applied:false` when the exact directory exists.
- A retry against an existing file, symlink, package, or other non-directory target refuses with `target_exists`.
- If apply returns an uncertain status, the caller must re-run exact metadata search/get and compare the returned directory handle before retrying.

## Warning Codes

Stable warning codes:

- `invalid_operation`
- `invalid_parent_handle`
- `unexpected_handle`
- `unexpected_content_text`
- `missing_required_field`
- `input_too_large`
- `invalid_filename`
- `unsupported_file_type`
- `missing_apply_confirmation`
- `invalid_approval_token`
- `icloud_drive_unavailable`
- `target_parent_not_found`
- `target_outside_root`
- `target_exists`
- `already_applied`
- `write_error`

Warnings must use safe generic messages and no raw local paths or exception text.

## Synthetic Tests Required

Before exposure, the iCloud Drive create-folder implementation must add:

- Preview success tests for exact-parent folder creation planning.
- Preview rejection tests for missing parent handle, file handle misuse, missing folder name, hidden name, path separators, package suffixes, unsupported characters, and unexpected content text.
- Apply rejection tests for missing confirmation, invalid token, missing parent, symlink parent, package traversal, existing file, existing symlink, unsupported target, and unavailable root.
- Apply success tests proving one directory is created and read-back reports directory metadata with no content hash.
- Already-applied retry coverage for an existing matching directory.
- CLI tests for `icloud-drive plan/apply --operation create-folder` without `--content-text`.
- MCP wrapper and annotation tests.
- Runtime verifier coverage for create-folder plan/apply success with directory read-back proof.
- Redacted log tests proving no handle, folder name, raw path, or approval-token persistence.
- Release-readiness and write-design gate coverage.

## Current Non-Goals

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, exact folder rename, exact folder Trash, exact folder move, exact selected-folder copy/delete, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only. Trash-text is governed separately by `docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md`; rename/copy/move is governed separately by `docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md`; exact folder rename by `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md` plus `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`; exact folder Trash by `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md` plus `docs/V1_146_ICLOUD_DRIVE_NON_EMPTY_FOLDER_TRASH_WRITE_DESIGN.md`; exact folder move by `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md` plus `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`; exact selected-folder copy by `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md` plus `docs/V1_147_ICLOUD_DRIVE_NON_EMPTY_FOLDER_COPY_WRITE_DESIGN.md`; and exact selected-folder delete by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`. Empty Trash, recursive folder creation, unbounded recursive folder copy/delete, binary/document generation, raw path writes, hidden-file writes, symlink/package traversal, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

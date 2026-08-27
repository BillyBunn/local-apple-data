# v1.34 Notes Replace Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data notes plan` and `notes_plan_change` tools now support `operation: replace_text` as a non-mutating preview, and the existing apply tools now support the matching approved replace operation.

This document defines the third Notes write lane: replace the full plaintext body of one note selected by exact opaque `notes:note:v2:` handle, with preview as the default behavior, expected-current-SHA-256 drift refusal on apply, and independent read_back verification after apply.

## Scope

Allowed:

- Replace bounded plaintext for one unlocked, non-deleted, non-shared Apple Note.
- Require an exact opaque Notes handle returned by Notes metadata search output.
- Require the caller to fetch exact content first and provide the current normalized plaintext SHA-256.
- Refuse to apply if note plaintext changed after planning.
- Return exact-content read-back metadata, bounded text, and new content hash after apply.

Blocked:

- Delete, move-to-trash, Recently Deleted management, folder/account targeting, locked-note mutation, shared-note mutation, rich-text editing, checklist state, attachment mutation, raw Notes identifiers, raw local database paths, broad note exports, durable content caches, and background indexing.
- Private Notes store writes, iCloud.com, browser sessions, keychain credentials, and private iCloud web APIs.

## Tool Contract

Every Notes replace mutation keeps the same three-step shape:

- `preview`: validate inputs and return the planned replacement without touching Notes.app or reading Notes data.
- `apply`: perform exactly the approved replacement after explicit user approval.
- `read_back`: verify the resulting state through the normal exact Notes content adapter.

The apply payload requires an approval token generated from the preview. The token binds the operation, exact note handle, expected current content SHA-256, replacement body hash, and idempotency key so an agent cannot replace with different text or a stale preview.

The read_back payload returns the changed note through the existing Notes exact-content shape, using opaque `notes:note:v2:` handles, bounded plaintext, and `content_sha256`. It must not trust the AppleScript write call alone.

## Implemented Preview

Implemented preview tools:

- CLI: `local-apple-data notes plan --operation replace-text`
- MCP: `notes_plan_change(operation="replace_text", ...)`

Preview requirements:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Require an exact opaque `notes:note:v2:` handle from Notes metadata search output.
- Require `expected_current_sha256` as a 64-character lowercase or uppercase SHA-256 hex digest.
- Require bounded non-empty `body_text`.
- Include `replacement_body_sha256` in the transient preview payload.
- Do not call Notes.app, resolve the handle, read note content, replace notes, or mutate Notes data.
- Do not log handles, content, content hashes, titles, approval fingerprints, or approval tokens.

## Implemented Apply

Implemented apply tools:

- CLI: `local-apple-data notes apply --operation replace-text`
- MCP: `notes_apply_change(operation="replace_text", ...)`

Apply requirements:

- Return `mode: "apply"`.
- Require a matching `notes-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the exact opaque Notes handle internally through the local SQLite metadata mapping.
- Reject missing, locked, deleted, shared, or unresolvable notes.
- Read current Notes `body` through Notes.app automation and normalize plaintext the same way exact content retrieval does before computing current SHA-256.
- Refuse to replace when the current SHA-256 differs from `expected_current_sha256`.
- Re-check the exact current HTML body inside the write script before setting the replacement body.
- Generate escaped HTML from bounded plaintext only after all checks pass.
- Read back the changed note through the exact-content adapter and require normalized plaintext to match the approved replacement text.
- Do not log handles, content, content hashes, titles, raw IDs, raw paths, approval fingerprints, or approval tokens.

## Implementation Boundary

Use the existing Python Notes adapter plus Notes.app AppleScript automation:

- Apple does not expose a public Notes CRUD framework on macOS.
- The local Notes scripting dictionary exposes `note.body` as writable HTML and `note.plaintext` as read-only plaintext.
- Python already owns CLI/MCP validation, approval-token verification, exact-handle SQLite mapping, bounded content extraction, logging, redaction, and synthetic tests.
- A Swift helper would still need to drive Notes automation or private stores, so it would add process overhead without a more durable public API boundary.

## Inputs

- `operation`: `replace_text`.
- `handle`: exact opaque `notes:note:v2:` handle for an unlocked, non-deleted note returned by Notes metadata search.
- `expected_current_sha256`: normalized plaintext hash returned by exact Notes content retrieval.
- `body_text`: non-empty replacement plaintext, normalized to LF line endings and capped at 12000 characters.
- `approval_token`: exact token from the matching preview.
- `confirm_apply`: explicit boolean confirmation.

All inputs are bounded. Existing note content and replacement text are used only to compute the approval fingerprint, check current state, generate escaped replacement HTML, and verify read-back; they are not logged.

## Delete And Move-To-Trash Blocker

This tranche does not implement delete or move-to-trash. The existing Notes automation path can set `body`, but this tranche did not prove a reversible delete or Recently Deleted operation with exact-handle targeting, locked/shared refusal, and independent absence-or-trash read-back. Exact-note delete is governed separately by `docs/V1_42_NOTES_DELETE_WRITE_DESIGN.md`; move-to-trash or Recently Deleted management still requires a separate destructive design gate before exposure.

## Warning Codes

Stable warning codes:

- `invalid_operation`
- `invalid_handle`
- `unexpected_title`
- `missing_required_field`
- `invalid_expected_sha256`
- `missing_body`
- `body_too_long`
- `missing_apply_confirmation`
- `invalid_approval_token`
- `notes_store_unavailable`
- `target_note_not_found`
- `content_unavailable`
- `automation_timeout`
- `read_error`
- `current_content_changed`
- `write_error`
- `password_protected_note`
- `shared_note_mutation_blocked`
- `read_back_unavailable`
- `read_back_mismatch`

Warnings must use safe generic messages and no raw local paths, raw identifiers, exception text, handles, hashes, titles, or note content.

## Synthetic Tests Required

Before exposure, the Notes replace implementation must add:

- Preview success tests for exact-handle replace planning.
- Preview rejection tests for missing note handle, missing expected hash, bad hash, unexpected title, empty body, oversized body, and invalid handles.
- Apply rejection tests for missing confirmation, invalid token, missing target, locked/deleted target, shared-note refusal, hash drift, automation timeout, and read-back mismatch.
- Apply success tests proving bounded replace and exact-content read-back hash verification.
- CLI tests for `notes plan/apply --operation replace-text`.
- Runtime verifier coverage for replace plan/apply success and stale-hash refusal.
- Redacted log tests proving no handle, content, hash, title, raw ID, raw path, or approval-token persistence.
- MCP annotation tests proving write tools are not marked read-only.
- Release-readiness and write-design gate coverage.

## Current Non-Goals

The current release allows Notes create-note in the default folder or one exact selected folder, exact child-folder creation under one selected parent folder, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, move-to-folder, and exact-note delete apply only. Exact-folder note create is governed separately by `docs/V1_39_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`, exact child-folder create is governed separately by `docs/V1_57_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`, exact-folder rename is governed separately by `docs/V1_58_NOTES_FOLDER_RENAME_WRITE_DESIGN.md`, exact empty child-folder delete is governed separately by `docs/V1_59_NOTES_FOLDER_DELETE_WRITE_DESIGN.md`, exact-note move-to-folder is governed separately by `docs/V1_45_NOTES_MOVE_WRITE_DESIGN.md`, and exact-note delete is governed separately by `docs/V1_42_NOTES_DELETE_WRITE_DESIGN.md`. Notes note delete outside the approved exact-note delete gate, folder delete outside the approved exact empty child-folder delete gate, move outside the approved exact-note/exact-folder move-to-folder gate, folder creation outside the exact child-folder create gate, folder rename outside the exact-folder rename gate, folder/account targeting outside exact note create, child-folder create, folder-rename, and move gates, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

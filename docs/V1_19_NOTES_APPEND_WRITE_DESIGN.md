# v1.19 Notes Append Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

No new write tool names are approved or exposed by this document. The existing `local-apple-data notes plan` and `notes_plan_change` tools now support `operation: append_text` as a non-mutating preview, and the existing apply tools now support the matching approved append operation.

This document defines the second Notes write lane: append bounded plaintext to one note selected by exact opaque `notes:note:v2:` handle, with preview as the default behavior, expected-current-SHA-256 drift refusal on apply, and independent read_back verification after apply.

## Scope

Allowed:

- Append bounded plaintext to one unlocked, non-deleted, non-shared Apple Note.
- Require an exact opaque Notes handle returned by Notes metadata search output.
- Require the caller to fetch exact content first and provide the current normalized plaintext SHA-256.
- Refuse to apply if note plaintext changed after planning.
- Return exact-content read-back metadata, bounded text, and new content hash after apply.

Blocked:

- Raw Notes identifiers, raw local database paths, broad note exports, durable content caches, and background indexing.
- Overwrite, arbitrary update, delete, move, folder/account targeting, rich-text editing, checklist state, attachment mutation, locked-note mutation, shared-note mutation, Recently Deleted management, and bulk operations.
- Private Notes store writes, iCloud.com, browser sessions, keychain credentials, and private iCloud web APIs.

## Tool Contract

Every Notes append mutation keeps the same three-step shape:

- `preview`: validate inputs and return the planned append without touching Notes.app or reading Notes data.
- `apply`: perform exactly the approved append after explicit user approval.
- `read_back`: verify the resulting state through the normal exact Notes content adapter.

The apply payload requires an approval token generated from the preview. The token binds the operation, exact note handle, expected current content SHA-256, append body hash, and idempotency key so an agent cannot append different text with a stale preview.

The read_back payload returns the changed note through the existing Notes exact-content shape, using opaque `notes:note:v2:` handles, bounded plaintext, and `content_sha256`. It must not trust the AppleScript write call alone.

## Implemented Preview

Implemented preview tools:

- CLI: `local-apple-data notes plan --operation append-text`
- MCP: `notes_plan_change(operation="append_text", ...)`

Preview requirements:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Require an exact opaque `notes:note:v2:` handle from Notes metadata search output.
- Require `expected_current_sha256` as a 64-character lowercase or uppercase SHA-256 hex digest.
- Require bounded non-empty `body_text`.
- Include `append_body_sha256` in the transient preview payload.
- Do not call Notes.app, resolve the handle, read note content, append notes, or mutate Notes data.
- Do not log handles, content, content hashes, titles, approval fingerprints, or approval tokens.

## Implemented Apply

Implemented apply tools:

- CLI: `local-apple-data notes apply --operation append-text`
- MCP: `notes_apply_change(operation="append_text", ...)`

Apply requirements:

- Return `mode: "apply"`.
- Require a matching `notes-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the exact opaque Notes handle internally through the local SQLite metadata mapping.
- Reject missing, locked, deleted, shared, or unresolvable notes.
- Read current Notes `body` through Notes.app automation and normalize plaintext the same way exact content retrieval does before computing current SHA-256.
- Refuse to append when the current SHA-256 differs from `expected_current_sha256`.
- Re-check the exact current HTML body inside the write script before setting the new body.
- Append escaped HTML paragraph fragments generated from bounded plaintext only after all checks pass.
- Read back the changed note through the exact-content adapter and return the new normalized content SHA-256.
- Do not log handles, content, content hashes, titles, raw IDs, raw paths, approval fingerprints, or approval tokens.

## Implementation Boundary

Use the existing Python Notes adapter plus Notes.app AppleScript automation:

- Apple does not expose a public Notes CRUD framework on macOS.
- The local Notes scripting dictionary exposes `note.body` as writable HTML and `note.plaintext` as read-only plaintext.
- Python already owns the CLI/MCP validation, approval-token verification, exact-handle SQLite mapping, bounded content extraction, logging, redaction, and synthetic tests.
- A Swift helper would still need to drive Notes automation or private stores, so it would add process overhead without a more durable public API boundary.

## Inputs

- `operation`: `append_text`.
- `handle`: exact opaque `notes:note:v2:` handle for an unlocked, non-deleted note returned by Notes metadata search.
- `expected_current_sha256`: normalized plaintext hash returned by exact Notes content retrieval.
- `body_text`: non-empty plaintext, normalized to LF line endings and capped at 12000 characters.
- `approval_token`: exact token from the matching preview.
- `confirm_apply`: explicit boolean confirmation.

All inputs are bounded. Existing note content and append text are used only to compute the approval fingerprint, check current state, generate escaped append HTML, and verify read-back; they are not logged.

## Gates

Before any additional apply-capable Notes operation is exposed:

- This document or a later operation-specific design doc must be updated.
- `docs/MUTATION_GATES.md`, `docs/WRITE_TOOL_ROADMAP.md`, and `docs/CAPABILITY_MATRIX.md` must name the approved operation and blocked operations.
- `scripts/audit_mutation_gates.py` must still prove no extra write-like CLI/MCP tool names are exposed.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `notes_plan_change` remains read-only; `notes_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- redaction scans must prove no content, handles, content hashes, titles, raw IDs, raw paths, or approval artifacts are persisted.

## Idempotency And Partial Failure

The apply path must be retry-safe:

- A retry before apply recomputes the same plan and token.
- A retry after successful append with the same expected current hash refuses with `current_content_changed`, forcing the caller to re-read exact content and plan again.
- If Notes.app accepts the append but read-back is unavailable or mismatched, the result is partial and the caller must re-read exact content by handle before retrying.

Append is intentionally not made silently idempotent because that would require storing or replaying prior note content. Hash drift refusal is safer and easier to audit.

## Warning Codes

Stable warning codes:

- `invalid_operation`
- `invalid_handle`
- `unexpected_title`
- `unexpected_append_target`
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

Before exposure, the Notes append implementation must add:

- Preview success tests for exact-handle append planning.
- Preview rejection tests for missing note handle, missing expected hash, bad hash, unexpected title, empty body, oversized body, and invalid handles.
- Apply rejection tests for missing confirmation, invalid token, missing target, locked/deleted target, shared-note refusal, hash drift, automation timeout, and read-back mismatch.
- Apply success tests proving bounded append and exact-content read-back hash verification.
- CLI tests for `notes plan/apply --operation append-text`.
- Runtime verifier coverage for append plan/apply success and stale-hash refusal.
- Redacted log tests proving no handle, content, hash, title, raw ID, raw path, or approval-token persistence.
- MCP annotation tests proving write tools are not marked read-only.
- Release-readiness and write-design gate coverage.

## Current Non-Goals

The current release allows Notes create-note and append-text apply only. Notes arbitrary update, delete, move, folder creation, folder/account targeting, rich-text editing, checklist state, attachments, locked/shared-note mutation, Recently Deleted management, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

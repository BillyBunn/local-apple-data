# V1.42 Notes Exact Delete Write Design

Status: Apply-capable implementation.

## Scope

This document extends the approved Notes plan/apply surface with one destructive operation: delete one exact unlocked, non-shared Apple Note selected by an opaque `notes:note:v2:` handle. It does not approve Notes move outside the separate exact-note/exact-folder move-to-folder gate, folder creation outside the separate exact child-folder create gate, folder rename outside the separate exact-folder rename gate, folder deletion, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, raw Notes store writes, private iCloud APIs, or bulk operations.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

Planning tools: `local-apple-data notes plan` and `notes_plan_change`.

No new mutating tool names are approved or exposed by this document.

## Preview

For `operation:delete`, the caller must provide:

- Exact `notes:note:v2:` handle from Notes metadata search.
- `expected_current_sha256` from exact `local-apple-data notes content` / `notes_get_content`.

Preview returns `mutation_applied:false`, `apply_available:true`, and a transient approval fingerprint bound to operation, exact note handle, expected current content SHA-256, destructive delete intent, and idempotency key. Preview does not call Notes.app, read note content, delete Notes data, return body text, or expose raw identifiers.

## Apply

Apply recomputes the plan, requires the matching `notes-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply=true`.

Apply resolves the exact opaque note handle through the local Notes SQLite mapping, refuses missing/deleted/password-protected targets, derives the Notes Core Data object reference, reads the current body through Notes.app automation, computes normalized plaintext SHA-256, and refuses if the current hash differs from `expected_current_sha256`.

The generated Notes.app automation targets only `ICNote/p<note_id>`, refuses password-protected or shared notes again immediately before deletion, rechecks the exact current HTML body, then runs `delete targetNote`. It must not overwrite note bodies, delete folders, delete every note, mutate attachments, or broad-select notes.

Read-back for delete is absence proof. Success requires `get_notes_metadata(handle)` to return `not_found` after apply, producing `read_back.deleted:true` and `read_back.verified_absent:true`.

## MCP Annotation

MCP annotations are static per tool. `notes_plan_change` stays read-only. `notes_apply_change` is now annotated non-read-only, destructive, non-idempotent, and closed-world because the same static apply tool can delete one exact selected note.

## Refusals

- Missing, malformed, raw, fabricated, or legacy Notes handles.
- Missing or malformed expected current content SHA-256.
- Body text, title, or folder handle on delete planning/apply.
- Missing confirmation or mismatched approval token.
- Missing, deleted, locked/password-protected, shared, or unresolvable notes.
- Current content SHA drift before deletion.
- Read-back still finding the target note after deletion.
- Notes move outside the approved exact-note/exact-folder move-to-folder gate, Recently Deleted management, folder/account mutation outside approved exact create/move gates, rich text, checklist state, attachment mutation, raw store writes, broad deletion, and any mutation outside the exact delete gate.

## Synthetic Tests Required

- Preview success for exact-handle delete planning.
- Preview rejection for missing handle, missing expected hash, malformed hash, title/body/folder target, and invalid handles.
- Apply rejection for missing confirmation, invalid token, missing/deleted target, locked target, shared-note refusal, current-content hash drift, automation timeout/error, and absence read-back mismatch.
- Apply success proving Notes.app delete automation, no body overwrite, and exact-handle absence read-back.
- CLI tests for `notes plan/apply --operation delete`.
- Runtime verifier coverage for delete plan/apply success and stale-hash refusal.
- MCP annotation tests proving `notes_apply_change` is destructive and non-idempotent.
- Release-readiness, write-design gate, redaction, and public-release coverage.

The current release allows Notes create-note in the default folder or one exact selected folder, exact child-folder creation under one selected parent folder, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, move-to-folder, and exact-note delete apply only. Notes move outside the approved exact-note/exact-folder move-to-folder gate, folder rename outside the approved exact-folder rename gate, root/non-empty/recursive folder delete, folder move, root/default-account folder creation, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, raw store writes, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

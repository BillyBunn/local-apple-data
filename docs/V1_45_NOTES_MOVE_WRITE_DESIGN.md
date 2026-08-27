# V1.45 Notes Exact Move-To-Folder Write Design

Status: Apply-capable implementation.

## Scope

This document extends the approved Notes plan/apply surface with one bounded reorganization operation: move one exact unlocked, non-shared Apple Note selected by an opaque `notes:note:v2:` handle into one exact normal Notes folder selected by an opaque `notes:folder:v1:` handle in the same account. It does not approve broad Notes move, folder creation outside the separate exact child-folder create gate, folder rename outside the separate exact-folder rename gate, folder deletion, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, raw Notes store writes, private iCloud APIs, or bulk operations.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

Planning tools: `local-apple-data notes plan` and `notes_plan_change`.

Folder selection tools: `local-apple-data notes folders`, `local-apple-data notes folder`, `notes_search_folders`, and `notes_get_folder`.

No new mutating tool names are approved or exposed by this document.

## Preview

For `operation:move_to_folder`, the caller must provide:

- Exact `notes:note:v2:` handle from Notes metadata search.
- Exact `notes:folder:v1:` handle from Notes folder metadata search.
- `expected_current_sha256` from exact `local-apple-data notes content` / `notes_get_content`.

Preview resolves the note and target folder through local Notes SQLite metadata, refuses missing notes, deleted notes, missing folders, smart folders, source-equals-target moves, and cross-account moves, then returns `mutation_applied:false`, `apply_available:true`, and a transient approval fingerprint bound to operation, exact note handle, expected current content SHA-256, source folder handle, target folder handle, same-account target proof, and idempotency key. Preview does not call Notes.app, read note content, move Notes data, return body text, or expose raw identifiers.

## Apply

Apply recomputes the plan, requires the matching `notes-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply=true`.

Apply resolves the exact opaque note handle and exact opaque folder handle through the local Notes SQLite mapping, refuses missing/deleted/password-protected/shared targets, refuses target smart folders, refuses source-folder drift, requires the target folder to stay in the same account as the source note, derives the Notes Core Data object references, reads the current body through Notes.app automation, computes normalized plaintext SHA-256, and refuses if the current hash differs from `expected_current_sha256`.

The generated Notes.app automation targets only `ICNote/p<note_id>` and `ICFolder/p<folder_id>`, refuses password-protected or shared notes again immediately before the move, rechecks the exact current HTML body, then runs `move targetNote to targetFolder`. It must not create folders, rename folders, delete folders, delete notes, edit note bodies, mutate attachments, or broad-select notes.

Read-back for move is folder proof. Success requires the local Notes metadata read-back to show the selected note now belongs to the approved target folder, producing `read_back.target_folder_confirmed:true`, `read_back.source_folder_handle`, `read_back.target_folder_handle`, and `body_returned:false`. The apply response must not return note body text.

## MCP Annotation

MCP annotations are static per tool. `notes_plan_change` stays read-only. `notes_apply_change` remains annotated non-read-only, destructive, non-idempotent, and closed-world because the same static apply tool can move or delete one exact selected note.

## Refusals

- Missing, malformed, raw, fabricated, or legacy Notes handles.
- Missing, malformed, raw, fabricated, or legacy Notes folder handles.
- Missing or malformed expected current content SHA-256.
- Body text or title on move planning/apply.
- Missing confirmation or mismatched approval token.
- Missing, deleted, locked/password-protected, shared, or unresolvable notes.
- Missing, smart, stale, same-source, or cross-account target folders.
- Current content SHA drift before move.
- Source folder changed after planning.
- Read-back failing to confirm the selected target folder.
- Notes move outside the approved exact-note/exact-folder move-to-folder gate, Recently Deleted management, folder/account management, rich text, checklist state, attachment mutation, raw store writes, broad move, and any mutation outside the exact move gate.

## Synthetic Tests Required

- Preview success for exact-handle move-to-folder planning.
- Preview rejection for missing note handle, missing folder handle, missing expected hash, malformed hash, body/title input, invalid note handles, invalid folder handles, smart folders, same-folder target, and cross-account target.
- Apply rejection for missing confirmation, invalid token, missing/deleted target, locked target, shared-note refusal, current-content hash drift, source-folder drift, automation timeout/error, and folder read-back mismatch.
- Apply success proving Notes.app move automation, no body overwrite, and exact-folder read-back proof.
- CLI tests for `notes plan/apply --operation move-to-folder`.
- Runtime verifier coverage for move-to-folder plan/apply success and stale-hash refusal.
- MCP annotation tests proving `notes_apply_change` remains destructive and non-idempotent.
- Release-readiness, write-design gate, redaction, and public-release coverage.

The current release allows Notes create-note in the default folder or one exact selected folder, exact child-folder creation under one selected parent folder, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, move-to-folder, and exact-note delete apply only. Notes move outside the approved exact-note/exact-folder move-to-folder gate, folder rename outside the approved exact-folder rename gate, root/non-empty/recursive folder delete, folder move, root/default-account folder creation, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, raw store writes, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

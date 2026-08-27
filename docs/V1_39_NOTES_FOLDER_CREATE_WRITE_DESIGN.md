# V1.39 Notes Folder-Targeted Create Write Design

Status: Apply-capable implementation.

## Scope

This document extends the approved Notes create-note lane so a caller can create one plaintext note in one exact existing Notes folder selected by an opaque `notes:folder:v1:` handle. It does not approve Notes folder creation outside the separate exact child-folder create gate, folder rename outside the separate exact-folder rename gate, folder deletion, note move, note delete, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, or bulk operations.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

Planning tools: `local-apple-data notes plan` and `notes_plan_change`.

Folder selection tools: `local-apple-data notes folders`, `local-apple-data notes folder`, `notes_search_folders`, and `notes_get_folder`.

No new mutating tool names are approved or exposed by this document.

## Read-Only Folder Selection

`notes folders` / `notes_search_folders` search local Notes folder titles only and reject empty or broad queries. Results return bounded folder metadata, `supports_create`, visible-note count, and an opaque `notes:folder:v1:` handle. They do not return account identifiers, raw Notes database IDs, local paths, note bodies, attachment bytes, or folder content.

`notes folder` / `notes_get_folder` returns exact folder metadata only for a selected `notes:folder:v1:` handle.

## Preview

For `operation:create`, the caller may provide `folder_handle=<notes:folder:v1:...>`. The preview resolves the handle through the local Notes SQLite schema, refuses missing or smart folders, returns `mutation_applied:false`, `apply_available:true`, and binds the approval fingerprint to:

- Operation: `create`
- Target folder handle, folder title, and folder kind
- Normalized title
- Body length and body SHA-256
- Deterministic idempotency key

The preview does not call Notes.app and does not write Notes data.

## Apply

Apply recomputes the same plan, requires the matching `notes-apply:v1:<approval_fingerprint>` token, requires `confirm_apply=true`, re-resolves the exact folder handle, and refuses stale/deleted/smart folders before automation.

The Notes.app automation targets the selected folder by its CoreData folder object ID (`ICFolder/p...`) rather than by account name or raw database row in output. Read-back is mandatory. Success requires exact note content read-back and, for folder-targeted create, proof that the created note belongs to the approved folder.

## Refusals

- Raw folder IDs, account names, account identifiers, local paths, and fabricated handles.
- Smart folders as create targets.
- Note move, folder creation outside the exact child-folder create gate, folder rename outside the exact-folder rename gate, folder deletion, account management, or bulk operations.
- Rich text, checklists, attachment mutation, locked/shared-note mutation, and Recently Deleted management.

## Synthetic Tests Required

- Folder search returns `notes:folder:v1:` handles without raw identifiers or folder content.
- Exact folder detail rejects legacy/raw handles.
- Create preview binds to the selected folder handle.
- Smart-folder targets are refused.
- Apply writes through a mocked Notes.app runner to the selected `ICFolder/p...` target.
- Apply refuses stale folder handles before invoking automation.
- CLI and MCP wrapper tests cover the new folder handle path.

The current release allows Notes create-note apply in the default folder or one exact selected folder, exact child-folder creation under one selected parent folder, exact-folder rename, exact empty child-folder delete, Notes append-text apply for one exact note, Notes replace-text apply for one exact note, move-to-folder apply for one exact note and folder, and exact-note delete apply only. Exact child-folder create is governed separately by `docs/V1_57_NOTES_FOLDER_CREATE_WRITE_DESIGN.md`, exact-folder rename is governed separately by `docs/V1_58_NOTES_FOLDER_RENAME_WRITE_DESIGN.md`, exact empty child-folder delete is governed separately by `docs/V1_59_NOTES_FOLDER_DELETE_WRITE_DESIGN.md`, exact-note move-to-folder is governed separately by `docs/V1_45_NOTES_MOVE_WRITE_DESIGN.md`, and exact-note delete is governed separately by `docs/V1_42_NOTES_DELETE_WRITE_DESIGN.md`. Notes note delete outside the approved exact-note delete gate, folder delete outside the approved exact empty child-folder delete gate, move outside the approved exact-note/exact-folder move-to-folder gate, folder rename outside the approved exact-folder rename gate, root/non-empty/recursive folder delete, folder move, root/default-account folder creation, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

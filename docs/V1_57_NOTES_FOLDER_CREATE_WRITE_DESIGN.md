# V1.57 Notes Exact Child-Folder Create Write Design

Status: Apply-capable implementation.

## Scope

This document extends the approved Notes plan/apply surface with one bounded folder-management operation: create one child folder under one exact normal Notes parent folder selected by an opaque `notes:folder:v1:` handle. It does not approve default-account guessing, root-folder creation, folder rename outside the separate exact-folder rename gate, exact empty child-folder delete outside the separate delete-folder gate, root/non-empty/recursive folder delete, folder move, account management, note mutation outside the existing Notes gates, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, raw Notes store writes, private iCloud APIs, or bulk operations.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

Planning tools: `local-apple-data notes plan` and `notes_plan_change`.

Parent-folder selection tools: `local-apple-data notes folders`, `local-apple-data notes folder`, `notes_search_folders`, and `notes_get_folder`.

No new mutating tool names are approved or exposed by this document.

## Preview

For `operation:create_folder`, the caller must provide:

- New folder title.
- Exact normal parent folder handle from Notes folder metadata search.

Preview resolves the parent folder through local Notes SQLite metadata, refuses missing or smart folders, rejects note handles, expected-current SHA input, and note body text, then returns `mutation_applied:false`, `apply_available:true`, and a transient approval fingerprint bound to operation, exact parent folder handle, normalized folder title, proposed metadata-only read-back shape, and idempotency key.

Preview does not call Notes.app, read note bodies, create folders, return folder contents, expose raw folder identifiers, or infer an account target.

## Apply

Apply recomputes the plan, requires the matching `notes-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply=true`.

Apply re-resolves the exact parent folder handle through local Notes SQLite metadata, refuses stale/deleted/smart parent folders, and requires a Notes Core Data folder object reference derived from the local store mapping. If a child folder with the same title already exists under the same exact parent and account, apply returns `already_applied` without invoking Notes.app automation.

The generated Notes.app automation targets only the selected parent `ICFolder/p<folder_id>`, runs `make new folder at targetFolder`, and returns the created folder id. It must not create notes, move notes, rename folders, delete folders, delete notes, edit note bodies, mutate attachments, or broad-select folders.

Read-back is folder metadata proof only. Success requires local Notes metadata to show the new child folder belongs to the approved parent folder, producing `read_back.parent_folder_confirmed:true`, `read_back.folder_content_returned:false`, `read_back.note_content_returned:false`, and `read_back.raw_identifier_returned:false`.

## MCP Annotation

MCP annotations are static per tool. `notes_plan_change` stays read-only. `notes_apply_change` remains annotated non-read-only, destructive, non-idempotent, and closed-world because the same static apply tool can delete one exact selected note.

## Refusals

- Missing, malformed, raw, fabricated, or legacy Notes folder handles.
- Missing folder title, broad title, note body text, note handle, or expected-current SHA input.
- Missing, deleted, smart, stale, or unresolvable parent folders.
- Missing local Notes store mapping.
- Missing confirmation or mismatched approval token.
- Read-back failing to confirm the selected parent folder.
- Folder creation outside the approved exact child-folder create gate, folder rename outside the approved exact-folder rename gate, root/non-empty/recursive folder delete, folder move, root-folder/default-account creation, note mutation, account management, raw store writes, private iCloud APIs, and bulk operations.

## Synthetic Tests Required

- Preview success for exact-parent create-folder planning.
- Preview rejection for missing parent handle, smart parent folder, note target input, expected-current SHA input, and body text input.
- Apply success proving Notes.app create-folder automation, exact parent targeting, metadata-only read-back, no note creation, and no deletion.
- Apply idempotency proving an existing same-title child under the same parent avoids automation.
- Apply partial failure proving created-folder read-back must confirm the approved parent folder.
- CLI tests for `notes plan/apply --operation create-folder`.
- MCP wrapper tests proving exact parent-folder forwarding.
- Runtime verifier coverage for create-folder plan/apply success and metadata-only read-back.
- Write-design gate coverage for the design doc, runtime verifier keys, adapter tests, CLI/MCP routes, and automation script guard.

The current release allows Notes create-note in the default folder or one exact selected folder, exact child-folder creation under one selected parent folder, append-text, replace-text, move-to-folder, and exact-note delete apply only. Folder rename/delete/move, root-folder/default-account creation, account management, rich-text editing, checklist state, attachment mutation, locked/shared-note mutation, Recently Deleted management, raw store writes, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

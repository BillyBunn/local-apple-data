# v1.59 Notes Exact Empty Child-Folder Delete Write Design

Status: Apply-capable implementation.

## Scope

This gate approves exactly one new Notes mutation: delete one exact empty normal child Notes folder selected by an opaque `notes:folder:v1:` handle.

The operation name is `operation:delete_folder`, accepted by CLI alias `delete-folder` and MCP `notes_plan_change` / `notes_apply_change`.

## Source Review

`/System/Applications/Notes.app/Contents/Resources/Notes.sdef` exposes `folder` objects with nested `folder` and `note` elements, writable `name`, read-only `id`, read-only `shared`, and read-only `container` properties on lines 82-108. The SDEF includes Cocoa standard scripting commands through `/System/Library/ScriptingDefinitions/CocoaStandard.sdef`; its standard suite defines `delete` on lines 120-124 with a direct object specifier.

The implementation uses Notes.app scripting only after SQLite metadata resolves one exact folder handle. It does not use Notes UI automation, iCloud.com, private iCloud APIs, browser sessions, keychain material, or raw folder identifiers supplied by the caller.

## Inputs

- Exact normal child folder handle from Notes folder metadata search.
- `expected_current_sha256` binds the current normalized folder title.
- Matching `notes-apply:v1:<approval_fingerprint>` token.
- `confirm_apply:true`.

No note handle, note body text, new title, raw row ID, raw folder ID, account ID, default-folder guess, smart folder, root folder, shared folder, or bulk selector is accepted.

## Plan

`local-apple-data notes plan --operation delete-folder` and `notes_plan_change(operation="delete-folder")` resolve the folder through local Notes SQLite metadata and return a non-mutating preview.

Planning refuses:

- non-folder handles,
- note handles,
- smart folders,
- root folders,
- folders with non-deleted notes,
- folders with child folders,
- title/body inputs,
- fabricated, stale, or raw handles.

The preview returns metadata only: folder title, exact folder handle, expected title hash, `empty_folder_required:true`, `recursive_delete:"blocked"`, `note_delete:"blocked"`, `folder_content_returned:false`, and `note_content_returned:false`.

## Apply

Apply recomputes the plan and verifies the approval token before automation. It re-resolves the exact handle, compares `expected_current_sha256` against the current normalized folder title, refuses folders with non-deleted notes, refuses folders with child folders, and refuses root folders.

Automation targets only the selected folder `ICFolder/p<folder_id>`, checks the current folder name, checks `shared of targetFolder`, checks `count of notes of targetFolder`, checks `count of folders of targetFolder`, then runs `delete targetFolder`.

Read-back is absence proof only. Success requires `read_back.verified_absent:true`, `read_back.folder_content_returned:false`, and `read_back.note_content_returned:false`.

## Blocked

Folder move, root-folder/default-account creation, root-folder delete, recursive folder delete, non-empty folder delete, note delete through this operation, smart-folder delete, shared-folder delete, account management, Recently Deleted management, rich text, attachment mutation, and bulk operations remain blocked.

## Synthetic Tests Required

- Plan success for one exact empty child folder.
- Plan refusal for note handle, smart folder, root folder, non-empty folder, and child-folder-containing folder.
- Apply success with exact title-hash binding, scoped AppleScript, and absence read-back.
- Apply stale-title refusal before automation.
- Apply non-empty drift refusal before automation.
- Static AppleScript regression proves `delete targetFolder`, count checks, no `delete targetNote`, no note creation, no folder creation, and no move.
- CLI forwarding for `delete-folder`.
- MCP forwarding for `delete-folder`.
- Runtime verifier coverage for delete-folder plan/apply success and absence proof.

## Verification

No live Notes data is mutated by verifier or tests. All mutation proof uses synthetic SQLite fixtures and mocked Notes.app automation responses.

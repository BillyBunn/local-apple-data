# v1.158 Notes Exact Empty Child-Folder Move Write Design

Status: Apply-capable implementation.

## Scope

This gate approves exactly one new Notes mutation: move one exact empty normal child Notes folder into one exact normal destination Notes folder in the same account.

The operation name is `operation:move_folder`, accepted by CLI alias `move-folder` and MCP `notes_plan_change` / `notes_apply_change`.

## Source Review

`/System/Applications/Notes.app/Contents/Resources/Notes.sdef` exposes `folder` objects with nested `folder` and `note` elements, writable `name`, read-only `id`, read-only `shared`, and read-only `container` properties on lines 82-108. The SDEF includes Cocoa standard scripting commands through `/System/Library/ScriptingDefinitions/CocoaStandard.sdef`; its standard suite defines `move` on lines 163-168 with a direct object specifier and destination location.

The implementation uses Notes.app scripting only after SQLite metadata resolves one exact source folder handle and one exact destination folder handle. It does not use Notes UI automation, iCloud.com, private iCloud APIs, browser sessions, keychain material, or raw folder identifiers supplied by the caller.

## Inputs

- Exact normal source child folder handle from Notes folder metadata search.
- Exact normal destination folder handle from Notes folder metadata search.
- `expected_current_sha256` binds the current normalized source folder title.
- Matching `notes-apply:v1:<approval_fingerprint>` token.
- `confirm_apply:true`.

No note handle, note body text, new title, raw row ID, raw folder ID, account ID, default-folder guess, smart folder, root source folder, non-empty source folder, shared folder, recursive selector, cross-account target, or bulk selector is accepted.

## Plan

`local-apple-data notes plan --operation move-folder` and `notes_plan_change(operation="move-folder")` resolve both folders through local Notes SQLite metadata and return a non-mutating preview.

Planning refuses:

- non-folder handles,
- note handles,
- smart source or destination folders,
- root source folders,
- source folders with non-deleted notes,
- source folders with child folders,
- source and destination folders in different accounts,
- source folders already in the destination folder,
- title/body inputs,
- fabricated, stale, or raw handles.

The preview returns metadata only: source folder title, exact source folder handle, exact destination folder handle, expected source title hash, `move:"approved_exact_empty_child_folder"`, `same_account_required:true`, `empty_folder_required:true`, `recursive_move:"blocked"`, `note_move:"blocked"`, `folder_content_returned:false`, and `note_content_returned:false`.

## Apply

Apply recomputes the plan and verifies the approval token before automation. It re-resolves the exact source and destination handles, compares `expected_current_sha256` against the current normalized source folder title, refuses source folders with non-deleted notes, refuses source folders with child folders, refuses root source folders, refuses smart folders, refuses cross-account targets, and refuses already-applied/no-op moves.

Automation targets only the selected source folder `ICFolder/p<source_folder_id>` and selected destination folder `ICFolder/p<target_folder_id>`, checks the current source folder name, checks `shared of sourceFolder`, checks `shared of targetFolder`, checks `count of notes of sourceFolder`, checks `count of folders of sourceFolder`, then runs `move sourceFolder to targetFolder`.

Read-back is destination-parent proof only. Success requires `read_back.target_folder_confirmed:true`, `read_back.folder_content_returned:false`, and `read_back.note_content_returned:false`.

## Blocked

Root-folder move, non-empty folder move, recursive folder move, cross-account move, smart-folder move, shared-folder move, note move through this operation, folder copy, folder rename, folder delete, root/default-account folder creation, account management, rich text, attachment mutation, and bulk operations remain blocked.

## Synthetic Tests Required

- Plan success for one exact empty child source folder and one exact destination folder.
- Plan refusal for missing source/destination handle, smart folder, root source folder, non-empty source folder, already-in-target source folder, and missing/stale source title hash.
- Apply success with exact title-hash binding, scoped AppleScript, and destination-parent read-back.
- Apply stale-title refusal before automation.
- Apply non-empty drift refusal before automation.
- Apply prior-move/no-op refusal before automation.
- Apply read-back mismatch partial reporting.
- Static AppleScript regression proves `move sourceFolder to targetFolder`, source/destination folder IDs, source title check, empty source checks, no `move targetNote`, no delete, and no creation.
- CLI forwarding for `move-folder`.
- MCP forwarding for `move-folder`.
- Runtime verifier coverage for move-folder plan/apply success and metadata-only destination-parent proof.

## Verification

No live Notes data is mutated by verifier or tests. All mutation proof uses synthetic SQLite fixtures and mocked Notes.app automation responses.

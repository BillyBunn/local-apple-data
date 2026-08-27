# v1.58 Notes Exact Folder Rename Write Design

Date: 2026-06-22
Status: Apply-capable implementation.

## Scope

This gate approves one bounded Notes folder-management operation: rename one exact normal Notes folder selected by an opaque `notes:folder:v1:` handle.

It does not approve root/non-empty/recursive folder delete, folder move, root-folder/default-account creation, account management, smart-folder mutation, note mutation outside existing gates, raw Notes store writes, private iCloud APIs, UI scraping, rich-text changes, attachment mutation, Recently Deleted management, or bulk operations.

## Tools

- Preview: `local-apple-data notes plan --operation rename-folder` and `notes_plan_change(operation:"rename_folder")`.
- Apply: `local-apple-data notes apply --operation rename-folder` and `notes_apply_change(operation:"rename_folder")`.
- Existing read selectors: `local-apple-data notes folders`, `local-apple-data notes folder`, `notes_search_folders`, and `notes_get_folder`.
- Canonical operation string: `operation:rename_folder`.

No new mutating tool names are added. The existing Notes plan/apply gate remains the only mutation entrypoint.

## Inputs

- Exact normal folder handle from Notes folder metadata search.
- New bounded folder title.
- `expected_current_sha256` binds the current normalized folder title. Planning fills this from the selected folder when omitted; apply should pass the value returned by the plan for retry-safe approval binding.
- Matching `notes-apply:v1:<approval_fingerprint>` token.
- Explicit `confirm_apply:true`.

Rejected inputs:

- Note handles.
- Smart folders.
- Missing or fabricated folder handles.
- Empty or low-quality titles.
- Body text.
- Stale title hash unless the folder already has the approved new title.

## Preview

Preview is non-mutating. It resolves the exact folder handle through local Notes SQLite metadata, rejects smart folders, computes the current normalized title SHA-256, and returns operation `rename_folder`, target folder handle, expected-current SHA-256, new title, approval fingerprint, and idempotency key.

Preview does not return note bodies, folder contents, raw folder IDs, account identifiers, local paths, or approval tokens.

## Apply

Apply recomputes the plan, verifies the approval token and explicit confirmation, resolves the same exact normal folder, and refuses if the current normalized folder-title SHA-256 differs from the approved expected hash.

If the folder already has the approved new title, apply returns `already_applied` with `mutation_applied:false` and metadata-only read-back. Otherwise, Notes.app automation targets only the selected folder `ICFolder/p<folder_id>`, checks the current folder name again, sets `name of targetFolder` to the approved title, and returns the selected folder id.

The AppleScript must not create notes, create folders, move folders, move notes, delete anything, or target folders by title.

## Read-Back

Read-back is folder metadata proof only.

- `read_back.renamed:true`
- `read_back.folder_content_returned:false`
- `read_back.note_content_returned:false`
- The returned handle must still match the approved exact folder handle.

If automation succeeds but read-back cannot confirm the exact folder and new title, apply returns `partial` with `mutation_applied:true`.

## Privacy

Folder rename is metadata-only. It must not inspect note bodies, attachment bytes, raw rows, account identifiers, credentials, local paths, or private iCloud state. Logs may contain command names, status, warning codes, counts, and duration only; they must not persist folder titles, handles, raw paths, approval fingerprints, or approval tokens.

## Tests Required

- Plan success for exact normal folder handles.
- Plan rejection for note handles, smart folders, missing/fabricated folder handles, body text, and stale expected title hash.
- Apply success with metadata-only read-back.
- Apply stale-title refusal before automation.
- Apply already-applied retry with `mutation_applied:false`.
- AppleScript source test proving it targets only the selected folder id and uses `set name of targetFolder`.
- CLI and MCP forwarding tests for operation, folder handle, expected hash, title, approval token, and confirmation.
- Runtime verifier coverage for rename-folder plan/apply success and already-applied retry.
- Mutation/write-design/release-readiness gates updated.

## Current Limits

This gate only approves exact normal folder rename. Root/non-empty/recursive folder delete, folder move, root-folder/default-account creation, account management, smart-folder mutation, broad folder management, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

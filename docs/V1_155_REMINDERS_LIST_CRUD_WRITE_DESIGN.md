# v1.155 Reminders List CRUD Write Design

Status: Apply-capable implementation. Superseded for same-source non-empty
list migration-delete by `docs/V1_156_REMINDERS_LIST_MIGRATION_DELETE_WRITE_DESIGN.md`.

Approved read tools: `local-apple-data reminders lists`, `local-apple-data reminders list`, `reminders_search_lists`, and `reminders_get_list`.

Approved write tools: `local-apple-data reminders apply-list` and `reminders_apply_list_change`.

This gate broadens the v1.135 synthetic-only gate to ordinary exact Reminders list create, rename, and empty-list delete. It does not approve account/source management, sharing mutation, cross-source management, non-empty list delete outside the bounded same-source migrate-delete gate, or bulk list mutation.

## Scope

Candidate operations:

- Reminders list create, rename, and empty-list delete.
- Create one Reminders list in the same source as one exact selected existing list.
- Rename one exact selected empty Reminders list.
- Delete one exact selected empty Reminders list.

Required handles:

- Exact opaque `reminders:list:eventkit:v1:` source list handle.
- Exact opaque `reminders:list:eventkit:v1:` target list handle.

Out of scope:

- No account/source management, sharing mutation, cross-source management, non-empty list delete outside the bounded same-source migrate-delete gate, or bulk list mutation is approved.

## Source Review

The implementation uses public EventKit APIs from the local macOS SDK:

- `EKCalendar(for: .reminder, eventStore:)` creates a Reminders list.
- `EKCalendar.title` and `EKCalendar.source` select the approved title/source.
- `EKEventStore.saveCalendar(_:commit:)` saves create/rename changes.
- `EKEventStore.removeCalendar(_:commit:)` removes an approved empty list.
- Reminder counts use public reminder predicates and `fetchReminders(matching:)`.

No Reminders database writes, Reminders UI automation, iCloud.com, private iCloud APIs, raw EventKit identifier input, or browser/keychain path is used.

## Planning Contract

Planning is non-mutating.

Create planning requires:

- `operation:create_list`.
- Exact source list handle.
- Bounded target title.
- Source writable, non-subscribed, non-immutable, reminder-only, and not a birthday/subscribed source.
- Same-source duplicate-title refusal.
- Source safe-hash binding in the approval fingerprint.

Rename planning requires:

- `operation:rename_list`.
- Exact target list handle.
- Bounded target title.
- Target writable, non-subscribed, non-immutable, reminder-only, and empty.
- Same-source duplicate-title refusal.
- Target and source safe-hash binding in the approval fingerprint.

Delete planning requires:

- `operation:delete_list`.
- Exact target list handle.
- Target writable, non-subscribed, non-immutable, reminder-only, and empty.
- Target and source safe-hash binding in the approval fingerprint.

## Apply Contract

Apply recomputes the plan immediately before mutation, requires a matching `reminders-apply:v1:<approval_fingerprint>` token, requires `confirm_apply:true`, and re-resolves the same exact source or target handle.

The Swift EventKit helper must recheck title, source type, writable state, reminder-only entity type, and empty-list proof before mutation.

Read-back proof:

- Create returns `read_back.source_list_verified:true` only after helper proof,
  empty-list proof, and created-list source safe-hash match the approved source.
- Rename returns `read_back.empty_list_verified:true`.
- Delete returns `read_back.list_absent_verified:true`.

Failed read-back after a committed mutation returns `apply_unknown` with `mutation_applied:true`.

## Verification

Runtime verifier proves ordinary non-synthetic list titles for direct create, rename, delete, and MCP create apply through fixture-backed EventKit helper responses.

Required runtime keys include:

- `reminders_list_create_plan_status`
- `reminders_list_create_apply_status`
- `reminders_list_rename_apply_status`
- `reminders_list_delete_apply_status`
- `mcp_reminders_list_create_apply_status`

Source tests cover exact source/target handle binding, same-source duplicate refusal, create-source reminder-only refusal, empty-list proof, missing count refusal, non-empty refusal, stale-token refusal, create/read-back source proof, delete absence-proof mismatch, CLI routing, MCP wrapper routing, Swift helper typecheck, runtime verifier receipts, surface-contract audit coverage, and mutation/write-design audit coverage.

## Current Release Gate

The current release allows Reminders item create/complete/uncomplete/due-date/title/notes/priority-update/exact same-source list-move/delete and exact Reminders list create/rename/empty-delete/same-source migrate-delete only through plan/apply/read-back gates.

Account/source management, sharing, non-empty delete outside the bounded same-source migrate-delete gate, attachments, images, rich-content mutation, and bulk operations remain blocked.

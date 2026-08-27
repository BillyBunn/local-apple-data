# v1.65 Reminders List Move Write Design

Status: Apply-capable implementation.

Approved read tools: `local-apple-data reminders lists`, `local-apple-data reminders list`, `reminders_search_lists`, and `reminders_get_list`.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

This document approves exactly one Reminders list mutation: move one exact Reminder to one exact same-source target list in the same EventKit source through EventKit after plan-token and explicit-confirmation checks. It does not approve list creation, list rename, list delete, account move, cross-source move, sharing mutation, bulk move, attachment mutation, URL mutation, image mutation, or rich-content mutation.

No list creation, list rename, list delete, account move, cross-source move, sharing mutation, bulk move, attachment mutation, URL mutation, image mutation, or rich-content mutation is approved.

## Scope

Allowed:

- `local-apple-data reminders lists --query <title text>`
- `reminders_search_lists(query=...)`
- `local-apple-data reminders list --handle reminders:list:eventkit:v1:...`
- `reminders_get_list(handle=...)`
- `local-apple-data reminders plan --operation move-to-list`
- `reminders_plan_change(operation="move_to_list")`
- `local-apple-data reminders apply --operation move-to-list`
- `reminders_apply_change(operation="move_to_list")`

Required list-move inputs:

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- Exact opaque `reminders:list:eventkit:v1:` expected current list handle from the selected reminder metadata.
- Exact opaque `reminders:list:eventkit:v1:` target list handle.
- `expected_title` from a recent read-only result.
- `expected_completed` from a recent read-only result.
- `expected_list_name` from a recent read-only result.
- Matching `reminders-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply:true`.

Out of scope:

- Raw EventKit identifiers.
- Raw SQLite row IDs or legacy `reminders:reminder:v1:` handles.
- Target list selection by title, account name, raw identifier, or broad query at apply time.
- Bulk move.
- List creation, list rename, list delete, account move, cross-source move, sharing mutation, or list management.
- Reminder attachment, URL, image, or rich-content mutation.
- Any UI automation, browser/iCloud path, keychain path, external connector, or network service.

## Safety Contract

List search is metadata-only. It returns opaque `reminders:list:eventkit:v1:` handles plus list titles and does not expose raw EventKit list identifiers. Empty or broad queries are refused before EventKit access.

Exact list detail is handle-gated. `reminders_get_list` and `local-apple-data reminders list` accept only opaque list handles returned by list search and return bounded metadata only.

Plan is non-mutating. It validates the exact reminder handle, exact expected current list handle, exact target list handle, expected title, expected completion state, and expected current list name, returns `mutation_applied:false`, produces an idempotency key, and creates an approval fingerprint over the exact reminder target plus exact current and target lists.

Apply recomputes the plan, requires the matching approval token, requires explicit confirmation, resolves the reminder handle through EventKit search, resolves the expected current list handle and target list handle through EventKit list metadata, and refuses missing or stale list targets before calling the apply helper.

The Swift EventKit helper must recheck title, completion state, expected current list identifier, and current list name before any already-applied shortcut or move. It must refuse target lists whose `sourceIdentifier` differs from the reminder's current list source with `cross_account_list_move`. It must set only `reminder.calendar` for the resolved target list. It must not expose raw reminder or target-list EventKit identifiers in public output.

Read-back for list-move is target-list identity proof. A successful list-move result must include:

- `mutation_applied:true`
- `operation:"move_to_list"`
- `read_back.list_name`
- `read_back.target_list_verified:true`

If the expected current list cannot be found before apply, the operation must return `expected_list_not_found` with `mutation_applied:false`. If the target list cannot be found before apply, the operation must return `target_list_not_found` with `mutation_applied:false`.

If the helper cannot prove that the persisted reminder's post-apply list identifier matches the internally resolved target list identifier, apply must return `apply_unknown` with `mutation_applied:true` and `read_back_target_mismatch` so duplicate list titles cannot satisfy success.

## MCP Annotation

Because MCP tool annotations are static per tool and `reminders_apply_change` can delete reminders, the tool remains destructive and non-idempotent at the descriptor level. List-move itself is exact-targeted and approval-token gated, but it shares the existing Reminders apply tool.

`reminders_search_lists`, `reminders_get_list`, and `reminders_plan_change` remain read-only.

## Idempotency

List-move is not retry-safe with the original pre-move approval token after a successful move. A stale current-list expectation must be refused before any already-target shortcut, even when the old and new list titles match. A later retry requires a fresh plan bound to the reminder's then-current list handle.

There is no durable personal-content operation ledger in this release. No implementation may add one that stores reminder titles, list names, raw identifiers, notes, or account data.

## Synthetic Tests Required

Required tests:

- Search success for list metadata with opaque handles and no raw list IDs.
- Exact list detail success by opaque list handle.
- Exact list detail refusal for reminder handles, raw identifiers, or malformed handles.
- Plan success for list-move with exact reminder and target-list handles.
- Plan refusal for raw target list names or malformed list handles.
- Apply refusal before helper call when confirmation or approval token is missing.
- Apply refusal before helper call when the target list handle no longer resolves.
- Apply success using mocked EventKit helper responses and read-back target-list identity proof.
- Apply refusal for cross-account/source target lists in the Swift helper.
- Apply refusal when a stale current-list handle or title expectation would otherwise hit the already-target shortcut.
- Apply unknown result when read-back target-list identity proof is missing or false even if the visible list title matches.
- Redaction checks proving raw reminder IDs and raw list IDs do not appear in public output.
- MCP inventory tests proving the list tools are read-only and the apply tool remains destructive.
- Runtime synthetic smoke proving list search, list handle opacity, list-move plan, and list-move apply without touching live Reminders.

## Current Release Gate

This release allows only exact-handle same-source Reminder list-move through the plan/apply/read-back target-list identity proof gate above. Reminder list creation, list rename, list delete, account move, cross-source move, sharing mutation, bulk move, attachments, URLs, images, rich-content mutation, and any move path outside `reminders apply --operation move-to-list` / `reminders_apply_change(operation="move_to_list")` remain blocked.

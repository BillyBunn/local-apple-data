# v1.156 Reminders List Migration Delete Write Design

Status: Implemented in `0.1.0+codex.20260702222115`.

## Scope

This gate adds one Reminders list operation: delete one exact non-empty list
after moving every reminder in it to one exact same-source target list.

Allowed operation:

- `delete_list_with_migration`

Approved only through:

- CLI: `local-apple-data reminders plan-list --operation delete-list-with-migration ...`
- CLI: `local-apple-data reminders apply-list --operation delete-list-with-migration ...`
- MCP: `reminders_plan_list_change`
- MCP: `reminders_apply_list_change`

## Required Inputs

- `list_handle`: exact source `reminders:list:eventkit:v1:` handle from list
  metadata output.
- `target_list_handle`: exact target `reminders:list:eventkit:v1:` handle from
  list metadata output.
- Matching `approval_token` plus `confirm_apply:true` for apply.

## Safety Rules

- Source and target must be different lists.
- Source and target must be in the same EventKit source.
- Source and target must be writable, non-subscribed, non-immutable,
  reminder-only lists.
- Plan binds source safe hash, target safe hash, source reminder count, target reminder count, source/target titles, source type, and target source type.
- Apply re-resolves both exact handles and refuses drift before mutation.
- Migration is capped at 50 reminders.
- Empty sources are refused; use `delete_list` for empty-list delete.
- Cross-source migration, account/source management, sharing mutation, bulk
  list operations, attachments, images, and rich-content mutation remain blocked.

## Apply Proof

The Swift EventKit helper:

1. Fetches all reminders with `predicateForReminders(in: nil)`.
2. Checks source and target counts against the approved plan.
3. Moves each source reminder by setting `reminder.calendar = targetList` and
   saving with `store.save(reminder, commit: true)`.
4. Re-fetches reminders and verifies source count is zero and target count
   increased by the migrated count.
5. Deletes the now-empty source list with `store.removeCalendar`.
6. Verifies source list absence.

Output returns counts and boolean proof only. It returns no raw EventKit list identifiers, reminder identifiers, reminder titles, notes, URLs, attachments, or raw local paths.

Any save failure after migration starts, partial migration, or post-migration
delete failure returns `apply_unknown` with `mutation_applied:true`.

## Verification

- `uv run pytest -q tests/test_reminders_adapter.py tests/test_cli_reminders.py::test_cli_reminders_plan_and_apply_list tests/test_cli_reminders.py::test_cli_reminders_plan_list_delete_with_migration tests/test_mcp_server.py::test_mcp_reminders_list_management_wrappers_preserve_gate`
- `xcrun swiftc scripts/eventkit_helper.swift -o /tmp/local-apple-data-eventkit-helper-check`
- `uv run python scripts/verify_runtime.py --json`

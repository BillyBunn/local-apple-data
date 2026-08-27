# v1.161 Reminders Selected-List Item Metadata

## Status

Implemented in `0.1.0+codex.20260703031530`.

## Scope

Add a read-only selected-list item metadata surface:

- MCP: `reminders_list_items(handle, limit=20, include_completed=false)`
- CLI: `local-apple-data reminders list-items --json --handle <reminders:list:eventkit:v1:...> [--limit N] [--include-completed]`

## Safety Contract

- Input must be an opaque `reminders:list:eventkit:v1:` handle returned by bounded Reminders list metadata.
- The adapter resolves the handle against current EventKit list metadata without count-fetching all reminders, then the Swift helper fetches reminders only from that selected `EKCalendar`.
- Output is capped to 50 items and defaults to incomplete reminders only.
- Output returns reminder metadata and opaque reminder/list handles only.
- Output does not return reminder notes, raw EventKit identifiers, raw URLs, raw alarm detail, attachments, rich content, source/account identifiers, local paths, or inline content.
- This is read-only. It does not broaden Reminders mutation beyond existing plan/apply gates.

## Verification

Covered by:

- `tests/test_reminders_adapter.py`
- `tests/test_cli_reminders.py`
- `tests/test_mcp_server.py`
- `scripts/verify_runtime.py`
- `scripts/audit_surface_contract.py`
- `scripts/audit_mutation_gates.py`

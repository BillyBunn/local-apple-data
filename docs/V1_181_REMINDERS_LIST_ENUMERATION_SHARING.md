# v1.181 Reminders List Enumeration + Sharing Visibility

## Status

Implemented in `0.1.0+codex.20260707094952`.

## Motivation (real incident, 2026-07-07)

An agent looking for the operator's to-do list had no way to enumerate
Reminders lists: `reminders_search_lists` only matches a title substring and
requires at least two characters. Searches for "reminder"/"to do"/"inbox"
matched only "Family reminders" — a list shared with the operator's wife — so
the agent concluded it was the only list and wrote items onto it. Nothing in
list metadata indicated sharing. Moving the items out then failed repeatedly
with the generic `eventkit_apply_failed` (EventKit refuses to move share-owned
items out of a shared list), forcing the agent to guess the cause. The
explicit operator request for this tranche satisfies the read-surface
design/approval gate. No new mutation surface.

## Scope

1. Read-only enumeration of all Reminders lists:
   - MCP: `reminders_list_lists(limit=20)` (max 50)
   - CLI: `local-apple-data reminders lists --json` without `--query`
   - Same metadata shape as `reminders_search_lists` results; adds a
     `results_truncated` warning when more lists exist than the requested
     limit (the adapter requests limit+1 to detect truncation).
2. Sharing status in list metadata everywhere it is returned
   (`reminders_search_lists`, `reminders_list_lists`, `reminders_get_list`,
   selected-list and list-management read-backs):
   - `is_shared`: true/false when detection works, null when unavailable —
     never a false "not shared".
   - `sharee_count`: emitted only when EventKit exposes a positive count.
   - Detection probes private-but-stable `EKCalendar` accessors
     (`sharingStatus`, `sharees`, `sharedOwnerName`) behind `responds(to:)`
     guards in the Swift helper; EventKit has no public sharing API. All three
     accessors respond on this macOS (probed 2026-07-07).
3. Precise error for the shared-list move: when `reminders_apply_change`
   `move_to_list` is rejected by EventKit and the source list is detected as
   shared, the failure returns `shared_list_move_unsupported` recommending the
   create-on-target + guarded-delete fallback, instead of the generic
   `eventkit_apply_failed`. The `reminders_plan_change` /
   `reminders_apply_change` tool descriptions document the limitation.

## Safety Contract

- Enumeration is metadata-only: opaque `reminders:list:eventkit:v1:` handles,
  titles, capability flags, sharing flags, and safe hashes; no reminder
  contents, raw EventKit identifiers, account identifiers, or local paths.
- Sharing output is the boolean and an optional positive count only; sharee
  identities (names, emails, addresses) are never read into payloads or
  returned.
- Output caps match sibling list-metadata tools (default 20, max 50), with an
  explicit truncation warning instead of a silent cap.
- `list_safe_sha256` inputs are unchanged, so existing plan/apply approval
  fingerprints are unaffected by the new fields.
- `is_shared` is advisory read surface; it does not gate or broaden any
  mutation path. The `shared_list_move_unsupported` warning only fires after
  EventKit itself rejected the save, and only when sharing was positively
  detected (unknown state keeps the generic warning).

## Verification

Covered by:

- `tests/test_reminders_adapter.py` (enumeration, caps/truncation, degraded
  path, sharing mapping incl. unknown-state, shared vs non-shared move
  failure)
- `tests/test_cli_reminders.py` (no-query enumeration routing)
- `tests/test_mcp_server.py` (wrapper + tool inventory/annotations)
- `scripts/verify_runtime.py` (expected tools, tool_count 148)
- `scripts/audit_surface_contract.py`, `scripts/audit_mutation_gates.py`
- Live read-only validation on the operator machine: 12 lists enumerated with
  `full_access`; "PKOS" `is_shared:false`; "Family reminders"
  `is_shared:true` (via `sharingStatus`; `sharees` is empty on this account
  side, so no `sharee_count` is emitted).

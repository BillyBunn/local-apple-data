# V1.122 Calendar Selected Recurring Occurrence Calendar Move Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update surface to exact
target-calendar move. It stays local-only, EventKit-only, exact-handle gated,
occurrence-bound, approval-token gated, and metadata-only.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public writable `EKEvent.calendar` and the
existing exact `calendar:calendar:v1:` target-calendar selection gate.

This is the selected recurring occurrence target-calendar move gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- `target_calendar_handle` must be an exact `calendar:calendar:v1:` handle from
  Calendar target metadata output.
- Optional title, plain notes, timed reschedule, all-day set/clear/date-only
  reschedule, availability, event URL, structured-location, or alarm changes
  may be included only through the already approved selected occurrence gates.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with a
supported bounded recurrence payload, resolves the target calendar handle, and
binds a sibling occurrence for preservation proof.

Planning proves the event is recurring with a supported bounded recurrence payload.

The preview includes:

- `preview.proposed.selected_occurrence_calendar_move_requested:true`.
- `preview.proposed.target_calendar_handle`.
- `preview.proposed.target_calendar_verified:true`.
- `preview.proposed.target_calendar_allows_content_modifications:true`.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.
- Hash-only sibling URL, plain-location, structured-location, and alarm-state
  preservation fields.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, invalid target calendar handle, unreadable
target calendar, or unwritable target calendar returns an error preview before
mutation.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence and target calendar, re-checks recurrence
shape, occurrence/sibling identity, expected current state, target calendar
writability, and hash-only sibling URL/plain-location/structured-location/alarm
state, then sends the occurrence identity plus target calendar identifier to
the Swift EventKit helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state, assigns `event.calendar` to the
resolved target calendar, saves with `span:.thisEvent`, then reads back the
selected occurrence and adjacent occurrence at their approved times.

The Swift helper assigns `event.calendar` to the resolved target calendar.

Success requires:

- selected occurrence read-back matches the approved target calendar;
- selected occurrence read-back matches approved title/plain
  location/notes/start/end/time-zone/all-day/availability/event-URL/structured
  location and alarm state;
- adjacent occurrence remains present and recurring in the original calendar
  with URL, plain-location, structured-location, and alarm-state hash-only state
  preserved;
- helper returns `selected_occurrence_updated_verified:true`,
  `selected_occurrence_calendar_move_verified:true`, and
  `adjacent_occurrence_calendar_verified:true`;
- adapter returns `target_calendar_verified:true`,
  `selected_occurrence_calendar_move_verified:true`, and
  `adjacent_occurrence_calendar_verified:true`.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct and MCP plan/apply for selected
occurrence target-calendar move.

Fixture-backed runtime verifier proves direct and MCP plan/apply for selected occurrence target-calendar move.

Direct keys include
`calendar_recurrence_update_calendar_move_plan_status`,
`calendar_recurrence_update_calendar_move_plan_requested`,
`calendar_recurrence_update_calendar_move_apply_status`,
`calendar_recurrence_update_calendar_move_apply_target_verified`,
`calendar_recurrence_update_calendar_move_apply_selected_verified`,
`calendar_recurrence_update_calendar_move_apply_adjacent_calendar`, and
`calendar_recurrence_update_calendar_move_apply_calendar`.

MCP keys include
`mcp_calendar_recurrence_update_calendar_move_plan_status`,
`mcp_calendar_recurrence_update_calendar_move_plan_requested`,
`mcp_calendar_recurrence_update_calendar_move_apply_status`,
`mcp_calendar_recurrence_update_calendar_move_apply_target_verified`,
`mcp_calendar_recurrence_update_calendar_move_apply_selected_verified`,
`mcp_calendar_recurrence_update_calendar_move_apply_adjacent_calendar`, and
`mcp_calendar_recurrence_update_calendar_move_apply_calendar`.

Source tests cover selected occurrence target-calendar move, target-calendar
read-back proof, adjacent original-calendar preservation proof, and
write-design audit coverage.

Named regressions include
`test_plan_calendar_change_selected_occurrence_calendar_move_resolves_target`,
`test_plan_calendar_change_selected_occurrence_calendar_move_rejects_stale_target`,
`test_plan_calendar_change_selected_occurrence_calendar_move_requires_writable_target`,
`test_apply_calendar_change_moves_selected_recurring_occurrence_to_exact_calendar`
and
`test_apply_calendar_change_selected_occurrence_calendar_move_requires_adjacent_calendar_proof`.

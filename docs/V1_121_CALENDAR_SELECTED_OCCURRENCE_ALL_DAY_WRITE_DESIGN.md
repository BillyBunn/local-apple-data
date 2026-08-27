# V1.121 Calendar Selected Recurring Occurrence All-Day Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update surface to exact
all-day set/clear/date-only reschedule. It stays local-only, EventKit-only, exact-handle gated,
occurrence-bound, approval-token gated, and metadata-only.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public writable `EKEvent.isAllDay` and
existing date-only Calendar event handling.

This is the selected recurring occurrence all-day set/clear/date-only reschedule gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- All-day set uses `all_day:true` plus date-only `start_date` and `end_date`.
- Same-state all-day date-only reschedule uses `expected_all_day:true`,
  `all_day:true`, date-only expected start/end, and date-only proposed
  start/end.
- Timed clear from an all-day selected occurrence uses `all_day:false`, exact
  timestamp `start_date` and `end_date`, and explicit `time_zone`.
- Timed-to-all-day set requires `expected_time_zone` because the current
  occurrence is timed.
- Existing all-day current state is bound with `expected_all_day:true` and
  date-only expected start/end identity.
- Optional title, plain notes, availability, event URL, structured-location, or
  alarm changes may be included only through the already approved selected
  occurrence gates.
- Recurrence fields must match the expected state or be absent as required.
- Target-calendar move is governed by
  `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with a supported bounded recurrence payload, and binds a sibling occurrence for
preservation proof.

The preview includes:

- `preview.proposed.all_day:true` or `false`.
- `preview.proposed.all_day_update_requested:true` when all-day state changes.
- `preview.proposed.all_day_date_reschedule_requested:true` when an existing
  all-day selected occurrence stays all-day and moves to a new date-only range.
- `preview.proposed.date_only_input:true` for all-day set.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.
- Hash-only sibling URL, plain-location, structured-location, and alarm-state
  preservation fields.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, proposed all-day set/date-only reschedule
without date-only start/end, timed clear without explicit `time_zone`, missing
`expected_time_zone` for timed-to-all-day set, recurrence mutation, or
recurrence clearing returns an error preview before mutation.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape,
occurrence/sibling identity, expected all-day/time-zone state, date-only
all-day reschedule state when requested, and hash-only sibling
URL/plain-location/structured-location/alarm state, then sends the occurrence
identity plus proposed all-day state to the Swift EventKit helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state, applies `event.isAllDay`, saves with `span:.thisEvent`, then reads back the selected occurrence and adjacent
occurrence at their approved times.

Success requires:

- selected occurrence read-back matches the approved all-day state;
- selected occurrence read-back matches approved title/plain
  location/notes/start/end/time-zone/availability/event-URL/structured-location
  and alarm state;
- adjacent occurrence remains present and recurring with URL, plain-location,
  structured-location, and alarm-state hash-only state preserved;
- helper returns `selected_occurrence_updated_verified:true`,
  `all_day_verified:true`, and `adjacent_occurrence_verified_present:true`;
- adapter returns `all_day_verified:true` and
  `adjacent_occurrence_alarm_verified:true`.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct and MCP plan/apply for selected occurrence timed-to-all-day set, all-day-to-timed clear, and same-state all-day date-only reschedule.

Direct keys include
`calendar_recurrence_update_all_day_plan_status`,
`calendar_recurrence_update_all_day_plan_requested`,
`calendar_recurrence_update_all_day_apply_status`,
`calendar_recurrence_update_all_day_apply_verified`, and
`calendar_recurrence_update_all_day_apply_all_day`; clear keys include
`calendar_recurrence_update_all_day_clear_plan_status`,
`calendar_recurrence_update_all_day_clear_plan_requested`,
`calendar_recurrence_update_all_day_clear_apply_status`,
`calendar_recurrence_update_all_day_clear_apply_verified`, and
`calendar_recurrence_update_all_day_clear_apply_all_day`. Same-state all-day
date-only reschedule keys include
`calendar_recurrence_update_all_day_reschedule_plan_status`,
`calendar_recurrence_update_all_day_reschedule_plan_requested`,
`calendar_recurrence_update_all_day_reschedule_apply_status`,
`calendar_recurrence_update_all_day_reschedule_apply_verified`,
`calendar_recurrence_update_all_day_reschedule_apply_rescheduled`, and
`calendar_recurrence_update_all_day_reschedule_apply_all_day`.

MCP keys include
`mcp_calendar_recurrence_update_all_day_plan_status`,
`mcp_calendar_recurrence_update_all_day_apply_status`,
`mcp_calendar_recurrence_update_all_day_apply_verified`, and
`mcp_calendar_recurrence_update_all_day_apply_all_day`; clear keys include
`mcp_calendar_recurrence_update_all_day_clear_plan_status`,
`mcp_calendar_recurrence_update_all_day_clear_apply_status`,
`mcp_calendar_recurrence_update_all_day_clear_apply_verified`, and
`mcp_calendar_recurrence_update_all_day_clear_apply_all_day`. MCP same-state
all-day date-only reschedule keys include
`mcp_calendar_recurrence_update_all_day_reschedule_plan_status`,
`mcp_calendar_recurrence_update_all_day_reschedule_apply_status`,
`mcp_calendar_recurrence_update_all_day_reschedule_apply_verified`,
`mcp_calendar_recurrence_update_all_day_reschedule_apply_rescheduled`, and
`mcp_calendar_recurrence_update_all_day_reschedule_apply_all_day`.

Source tests cover selected occurrence timed-to-all-day set, all-day-to-timed
clear, same-state all-day date-only reschedule, date-only requirement refusal,
missing expected/proposed time-zone refusals, Swift helper selected occurrence
all-day read-back proof, and write-design audit coverage.

Named regressions include
`test_apply_calendar_change_updates_selected_recurring_occurrence_all_day`,
`test_apply_calendar_change_clears_selected_recurring_occurrence_all_day`,
`test_apply_calendar_change_reschedules_selected_recurring_occurrence_all_day_date_only`,
`test_plan_calendar_change_selected_recurring_occurrence_all_day_requires_date_only`,
`test_plan_calendar_change_selected_recurring_occurrence_all_day_set_requires_expected_time_zone`,
and
`test_plan_calendar_change_selected_recurring_occurrence_all_day_clear_requires_time_zone`.

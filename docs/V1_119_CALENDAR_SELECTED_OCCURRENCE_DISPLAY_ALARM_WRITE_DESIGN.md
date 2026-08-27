# V1.119 Calendar Selected Recurring Occurrence Display Alarm Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update gate to relative and
absolute display alarm set/clear. It stays local-only, EventKit-only,
exact-handle gated, occurrence-bound, approval-token gated, and metadata-only.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public `EKAlarm` relative offsets and
absolute dates only. Audio, email, geofence, and structured-location alarm
actions are handled by
`docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`.

This is the selected recurring occurrence display alarm set/clear gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- Setting relative alarms uses exact `alarm_offsets_minutes`.
- Setting absolute alarms uses exact `alarm_absolute_dates`.
- Clearing display alarms passes an explicit empty proposed display-alarm list
  with exact expected display-alarm state.
- Relative and absolute display alarms remain mutually exclusive under the
  existing Calendar alarm validation.
- Expected-state binding uses `expected_alarm_offsets_minutes` or
  `expected_alarm_absolute_dates`.
- Optional `title`, plain `notes`, timed start/end/time-zone, `availability`,
  event URL, or structured-location changes may be included only through the
  already approved selected occurrence gates.
- Proposed and expected `all_day` must both be false.
- Audio, email, geofence, and structured alarm action changes are covered by
  the v1.120 selected occurrence action-alarm gate.
- Target calendar and recurrence fields must match the expected state or be
  absent as required.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with a
supported bounded recurrence payload, and binds a sibling occurrence for
preservation proof.

The preview includes:

- `preview.target.expected_state.alarm_offsets_minutes` or
  `preview.target.expected_state.alarm_absolute_dates`.
- `preview.proposed.alarm_offsets_minutes` or
  `preview.proposed.alarm_absolute_dates`.
- `preview.proposed.display_alarm_update_requested:true`.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_location_present` and
  hash-only `adjacent_occurrence_location_safe_sha256`.
- `preview.proposed.adjacent_occurrence_structured_location_present` and
  hash-only `adjacent_occurrence_structured_location_safe_sha256`.
- `preview.proposed.adjacent_occurrence_alarm_state_present` and
  hash-only `adjacent_occurrence_alarm_state_safe_sha256`.
- Hash-only sibling URL state when present.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, all-day mutation, recurrence mutation,
recurrence clearing, or relative/absolute display-alarm mixing returns an error
preview before mutation. Target-calendar move is governed by
`docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape,
occurrence/sibling identity, expected display-alarm state, and hash-only sibling
URL/plain-location/structured-location/alarm state, then sends the
occurrence identity plus proposed display-alarm state to the Swift EventKit
helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state including display-alarm state, rejects
audio/email/geofence alarm changes, applies only approved relative or absolute
display alarms, saves with `span:.thisEvent`, then reads back the selected
occurrence and adjacent occurrence at their approved times. The adjacent
occurrence proof returns no raw sibling location, URL, or email address.

Success requires:

- selected occurrence read-back matches the approved display-alarm offsets or
  absolute dates;
- selected occurrence read-back matches approved title/plain
  location/notes/start/end/time-zone/availability/event-URL/structured-location
  state;
- adjacent occurrence remains present and recurring with URL, plain-location,
  structured-location, and alarm-state hash-only state preserved;
- helper returns `selected_occurrence_updated_verified:true` and
  `adjacent_occurrence_verified_present:true`;
- adapter returns `display_alarm_verified:true` and
  `adjacent_occurrence_alarm_verified:true`.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply for
relative display-alarm set, absolute display-alarm set, and display-alarm clear.
Direct keys include
`calendar_recurrence_update_display_alarm_plan_status`,
`calendar_recurrence_update_display_alarm_plan_requested`,
`calendar_recurrence_update_display_alarm_apply_status`,
`calendar_recurrence_update_display_alarm_apply_verified`, and
`calendar_recurrence_update_display_alarm_apply_offsets`,
`calendar_recurrence_update_absolute_display_alarm_plan_status`,
`calendar_recurrence_update_absolute_display_alarm_plan_requested`,
`calendar_recurrence_update_absolute_display_alarm_apply_status`,
`calendar_recurrence_update_absolute_display_alarm_apply_verified`,
`calendar_recurrence_update_absolute_display_alarm_apply_dates`,
`calendar_recurrence_update_display_alarm_clear_plan_status`,
`calendar_recurrence_update_display_alarm_clear_plan_requested`,
`calendar_recurrence_update_display_alarm_clear_apply_status`,
`calendar_recurrence_update_display_alarm_clear_apply_verified`, and
`calendar_recurrence_update_display_alarm_clear_apply_offsets`. MCP keys include
`mcp_calendar_recurrence_update_display_alarm_plan_status`,
`mcp_calendar_recurrence_update_display_alarm_apply_status`,
`mcp_calendar_recurrence_update_display_alarm_apply_verified`,
`mcp_calendar_recurrence_update_absolute_display_alarm_plan_status`,
`mcp_calendar_recurrence_update_absolute_display_alarm_apply_status`,
`mcp_calendar_recurrence_update_absolute_display_alarm_apply_verified`,
`mcp_calendar_recurrence_update_display_alarm_clear_plan_status`,
`mcp_calendar_recurrence_update_display_alarm_clear_apply_status`, and
`mcp_calendar_recurrence_update_display_alarm_clear_apply_verified`.

Source tests cover adapter planning/apply proof for selected occurrence relative
display-alarm set, absolute display-alarm set, display-alarm clear, sibling
alarm-state preservation, sibling alarm-state read-back mismatch as
`apply_unknown`, Swift helper source ordering, public API audit expectations,
and write-design audit coverage.

## Audit Contract Strings

Setting relative alarms uses exact `alarm_offsets_minutes`.
Setting absolute alarms uses exact `alarm_absolute_dates`.
Clearing display alarms passes an explicit empty proposed display-alarm list with exact expected display-alarm state.
Expected-state binding uses `expected_alarm_offsets_minutes` or `expected_alarm_absolute_dates`.
Planning proves the event is recurring with a supported bounded recurrence payload.
Apply proof: selected occurrence read-back matches the approved display-alarm offsets or absolute dates.
Adjacent proof: adjacent occurrence remains present and recurring with URL, plain-location, structured-location, and alarm-state hash-only state preserved.
Apply result: adapter returns `display_alarm_verified:true` and `adjacent_occurrence_alarm_verified:true`.
Verification: Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply for relative display-alarm set, absolute display-alarm set, and display-alarm clear.
Selected recurring occurrence all-day is governed by `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`; target-calendar move is governed by `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.
Still blocked: mid-series recurrence replacement.
Still blocked: attendee/invitation mutation.

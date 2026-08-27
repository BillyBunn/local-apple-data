# V1.115 Calendar Selected Recurring Occurrence Reschedule Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update gate to timed
rescheduling. It stays local-only, EventKit-only, exact-handle gated,
occurrence-bound, and approval-token gated.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence.

This is the selected recurring occurrence reschedule gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- Proposed timed `start_date`, `end_date`, and explicit `time_zone` changes are allowed with optional `title`, plain `location`, and `notes` changes.
- Any selected-occurrence start/end/time-zone change requires both an explicit
  proposed `time_zone` and an explicit `expected_time_zone`, even when the
  time zone is unchanged.
- Proposed and expected `all_day` must both be false.
- Alarm fields, URL fields, availability, target
  calendar, and recurrence fields must match the expected state or be absent as
  required. Structured-location set/clear is governed by `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with a supported bounded recurrence payload, and binds a sibling occurrence for
preservation proof.

The preview includes:

- `preview.target.expected_state.recurrence_present:true`.
- `preview.target.expected_state.recurrence`.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.start_date` / `end_date` / `time_zone`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, recurrence mutation, recurrence clearing,
all-day mutation, missing proposed/expected time-zone binding for a timed
reschedule, availability mutation, alarm mutation, and URL mutation return an
error preview before mutation. Target-calendar move is governed by
`docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape and
occurrence/sibling identity against the approved preview, and sends the
occurrence identity to the Swift EventKit helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state, applies title/plain location/notes
and timed start/end/time-zone changes, saves with `span:.thisEvent`, then reads
back the selected occurrence at the approved new time and the adjacent
occurrence at its original time.

Success requires:

- selected occurrence read-back matches approved title/plain location/notes, start/end, and time-zone state;
- original selected occurrence start/end no longer resolves after reschedule;
- adjacent occurrence remains present and recurring;
- helper returns `selected_occurrence_updated_verified:true`,
  `selected_occurrence_rescheduled_verified:true`,
  `original_occurrence_verified_absent:true`, and
  `adjacent_occurrence_verified_present:true`.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply.
Direct keys include `calendar_recurrence_update_apply_rescheduled_verified`,
`calendar_recurrence_update_apply_original_absent`,
`calendar_recurrence_update_end_only_apply_rescheduled_verified`, and
`calendar_recurrence_update_end_only_apply_original_absent`. MCP keys include
`mcp_calendar_recurrence_update_apply_rescheduled_verified`,
`mcp_calendar_recurrence_update_apply_original_absent`,
`mcp_calendar_recurrence_update_end_only_apply_rescheduled_verified`, and
`mcp_calendar_recurrence_update_end_only_apply_original_absent`.

Source tests cover adapter planning/apply proof for timed reschedule, end-only
reschedule proof, missing time-zone binding refusal, alarm mutation refusal, CLI
flag routing, MCP fail-closed behavior without occurrence identity, Swift helper
source ordering, public API audit expectations, and write-design audit coverage.

## Still Out Of Scope

- selected recurring occurrence all-day, audio/email/geofence alarm, URL, availability, or
  target-calendar mutation outside the later dedicated gates;
- mid-series recurrence replacement;
- recurrence clearing beyond first-visible `.futureEvents` clear;
- attendee/invitation mutation;
- travel time;
- non-allow-listed URL schemes;
- procedure alarms.

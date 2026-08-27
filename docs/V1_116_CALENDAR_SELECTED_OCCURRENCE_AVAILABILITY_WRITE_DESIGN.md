# V1.116 Calendar Selected Recurring Occurrence Availability Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update gate to exact
availability changes. It stays local-only, EventKit-only, exact-handle gated,
occurrence-bound, support-mask validated, and approval-token gated.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public mutable `EKEvent.availability` and
`EKCalendar.supportedEventAvailabilities`.

This is the selected recurring occurrence availability gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- Proposed `availability` must be one of `busy`, `free`, `tentative`, or `unavailable`.
- `expected_availability` is required for drift binding.
- Optional `title`, plain `location`, `notes`, or timed start/end/time-zone
  changes may be included only through the already approved selected occurrence
  scalar/timed-reschedule gates.
- Proposed and expected `all_day` must both be false.
- Alarm fields, URL fields, target calendar, and
  recurrence fields must match the expected state or be absent as required.
  Structured-location set/clear is governed by `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with a supported bounded recurrence payload, and binds a sibling occurrence for
preservation proof.

The preview includes:

- `preview.target.expected_state.availability` and `availability_name`.
- `preview.proposed.availability` and `availability_name`.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, missing `expected_availability`, unsupported
target-calendar availability support, recurrence mutation, recurrence clearing,
all-day mutation, alarm mutation, and URL mutation return an error preview before
mutation. Target-calendar move is governed by
`docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape,
occurrence/sibling identity, expected state, and target-calendar availability
support against the approved preview, and sends the occurrence identity plus
expected/proposed availability to the Swift EventKit helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state including `expected_availability`,
applies the approved `availability`, saves with `span:.thisEvent`, then reads
back the selected occurrence and adjacent occurrence at their approved times.

Success requires:

- selected occurrence read-back matches approved availability plus approved
  title/plain location/notes/start/end/time-zone state;
- adjacent occurrence remains present and recurring;
- helper returns `selected_occurrence_updated_verified:true` and
  `adjacent_occurrence_verified_present:true`;
- no reschedule absence proof is claimed unless start/end changed.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply.
Direct keys include `calendar_recurrence_update_availability_plan_status`,
`calendar_recurrence_update_availability_plan_name`,
`calendar_recurrence_update_availability_apply_status`,
`calendar_recurrence_update_availability_apply_read_back_name`, and
`calendar_recurrence_update_availability_apply_selected_verified`. MCP keys
include `mcp_calendar_recurrence_update_availability_plan_status`,
`mcp_calendar_recurrence_update_availability_plan_name`,
`mcp_calendar_recurrence_update_availability_plan_scope`,
`mcp_calendar_recurrence_update_availability_plan_expected_name`,
`mcp_calendar_recurrence_update_availability_apply_status`,
`mcp_calendar_recurrence_update_availability_apply_read_back_name`, and
`mcp_calendar_recurrence_update_availability_apply_selected_verified`.

Source tests cover adapter planning/apply proof for selected occurrence
availability changes, missing expected-availability refusal, Swift helper
source ordering, public API audit expectations, and write-design audit coverage.

## Still Out Of Scope

- selected recurring occurrence all-day, audio/email/geofence alarm, URL, or target-calendar mutation
  outside the later dedicated gates;
- mid-series recurrence replacement;
- recurrence clearing beyond first-visible `.futureEvents` clear;
- attendee/invitation mutation;
- travel time;
- non-allow-listed URL schemes;
- procedure alarms.

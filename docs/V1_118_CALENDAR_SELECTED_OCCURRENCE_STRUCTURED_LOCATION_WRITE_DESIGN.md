# V1.118 Calendar Selected Recurring Occurrence Structured Location Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update gate to bounded
structured event location set/clear. It stays local-only, EventKit-only,
exact-handle gated, occurrence-bound, approval-token gated, and metadata-only.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public mutable `EKStructuredLocation` through
`EKEvent.structuredLocation`.

This is the selected recurring occurrence structured location set/clear gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- Setting requires bounded `structured_location`.
- A set with no `expected_structured_location` binds
  `structured_location_present:false` before apply.
- Replacing requires exact `expected_structured_location` drift binding.
- Clearing requires `clear_structured_location:true`, no
  `structured_location`, empty proposed `location`, and exact
  `expected_structured_location`.
- Optional `title`, plain `notes`, timed start/end/time-zone, `availability`,
  or event URL changes may be included only through the already approved
  selected occurrence scalar/timed-reschedule/availability/event-URL gates.
- Proposed and expected `all_day` must both be false.
- Alarm fields, target calendar, and recurrence fields must match the expected
  state or be absent as required.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with
a supported bounded recurrence payload, and binds a sibling occurrence for
preservation proof.

The preview includes:

- `preview.target.expected_state.structured_location_present`.
- `preview.target.expected_state.structured_location_present_bound`.
- `preview.target.expected_state.structured_location` when replacing or
  clearing an existing structured location.
- `preview.proposed.structured_location_requested` when setting.
- `preview.proposed.structured_location_clear_requested` when clearing.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_location_present` and
  hash-only `adjacent_occurrence_location_safe_sha256`.
- `preview.proposed.adjacent_occurrence_structured_location_present` and
  hash-only `adjacent_occurrence_structured_location_safe_sha256`.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, malformed structured location,
set/clear conflict, clear without expected structured location, non-empty
proposed location during clear, recurrence mutation, recurrence clearing,
all-day mutation or alarm mutation returns an error preview before mutation.
Target-calendar move is governed by
`docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape,
occurrence/sibling identity, expected structured-location presence or exact
expected structured-location value, and hash-only sibling URL/plain-location/
structured-location state, then sends the occurrence identity plus
proposed/clear structured-location state to the Swift EventKit helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state including structured-location presence
or value, applies the approved set or clear, saves with `span:.thisEvent`, then
reads back the selected occurrence and adjacent occurrence at their approved
times. The adjacent occurrence proof returns no raw sibling location or URL.

Success requires:

- selected occurrence read-back matches the approved structured location or
  verifies structured/plain location absence;
- selected occurrence read-back matches approved title/plain
  location/notes/start/end/time-zone/availability/event-URL state;
- adjacent occurrence remains present and recurring with URL, plain-location,
  and structured-location hash-only state preserved;
- helper returns `selected_occurrence_updated_verified:true` and
  `adjacent_occurrence_verified_present:true`;
- adapter returns `structured_location_verified:true` for set or
  `structured_location_cleared_verified:true` for clear.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply for
set and clear. Direct keys include
`calendar_recurrence_update_structured_location_plan_status`,
`calendar_recurrence_update_structured_location_plan_expected_present`,
`calendar_recurrence_update_structured_location_apply_status`,
`calendar_recurrence_update_structured_location_apply_verified`,
`calendar_recurrence_update_structured_location_apply_title`,
`calendar_recurrence_update_structured_location_clear_plan_status`,
`calendar_recurrence_update_structured_location_clear_plan_requested`,
`calendar_recurrence_update_structured_location_clear_apply_status`,
`calendar_recurrence_update_structured_location_clear_apply_verified`, and
`calendar_recurrence_update_structured_location_clear_apply_present`. MCP keys
include `mcp_calendar_recurrence_update_structured_location_plan_status`,
`mcp_calendar_recurrence_update_structured_location_apply_status`,
`mcp_calendar_recurrence_update_structured_location_apply_verified`,
`mcp_calendar_recurrence_update_structured_location_clear_plan_status`,
`mcp_calendar_recurrence_update_structured_location_clear_apply_status`, and
`mcp_calendar_recurrence_update_structured_location_clear_apply_verified`.

Source tests cover adapter planning/apply proof for selected occurrence
structured-location set/clear, expected absence binding, expected structured
replacement/clear binding, stale expected absence refusal, selected occurrence
mismatch-to-`apply_unknown`, sibling location proof binding and
mismatch-to-`apply_unknown`, Swift helper source ordering, public API audit
expectations, and write-design audit coverage.

## Audit Contract Strings

Setting requires bounded `structured_location`.
A set with no `expected_structured_location` binds `structured_location_present:false` before apply.
Replacing requires exact `expected_structured_location` drift binding.
Clearing requires `clear_structured_location:true`, no `structured_location`, empty proposed `location`, and exact `expected_structured_location`.
Planning proves the event is recurring with a supported bounded recurrence payload.
Apply proof: selected occurrence read-back matches the approved structured location or verifies structured/plain location absence.
Adjacent proof: adjacent occurrence remains present and recurring with URL, plain-location, and structured-location hash-only state preserved.
Apply result: adapter returns `structured_location_verified:true` for set or `structured_location_cleared_verified:true` for clear.
Verification: Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply for set and clear.
Selected recurring occurrence all-day is governed by `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`; target-calendar move is governed by `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.
Still blocked: mid-series recurrence replacement.
Still blocked: attendee/invitation mutation.

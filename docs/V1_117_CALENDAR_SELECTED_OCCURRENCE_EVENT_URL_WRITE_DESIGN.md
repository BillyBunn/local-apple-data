# V1.117 Calendar Selected Recurring Occurrence Event URL Write Design

Status: Apply-capable implementation.

This gate extends the selected recurring occurrence update gate to exact
allow-listed event URL set/clear. It stays local-only, EventKit-only,
exact-handle gated, occurrence-bound, approval-token gated, and hash-only for
selected and adjacent-occurrence URL proof.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate
only the selected occurrence. Uses public mutable `EKCalendarItem.URL`; the
Calendar public-surface audit fails if that setter is missing.

This is the selected recurring occurrence event URL set/clear gate.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from
  Calendar metadata output.
- Setting requires exact allow-listed `event_url`.
- Clearing requires `clear_event_url:true`, no `event_url`,
  `expected_event_url_present:true`, and `expected_event_url_sha256`.
- Optional `title`, plain `location`, `notes`, timed start/end/time-zone, or
  `availability` changes may be included only through the already approved
  selected occurrence scalar/timed-reschedule/availability gates.
- Proposed and expected `all_day` must both be false.
- Alarm fields, target calendar, and recurrence
  fields must match the expected state or be absent as required.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list,
proves the handle binds start/end identity, proves the event is recurring with
a supported bounded recurrence payload, and binds a sibling occurrence plus its
hash-only URL state for preservation proof.

The preview includes:

- `preview.target.expected_state.event_url_present`.
- `preview.target.expected_state.event_url_safe_sha256` when clearing or
  binding an existing URL.
- `preview.proposed.event_url_requested`, `event_url_scheme`,
  `event_url_domain`, and `event_url_safe_sha256` when setting.
- `preview.proposed.event_url_clear_requested` when clearing.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` /
  `adjacent_occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_event_url_present`.
- `preview.proposed.adjacent_occurrence_event_url_safe_sha256` when the
  adjacent occurrence has an event URL.

Invalid scope, non-update operation, missing occurrence identity, non-recurring
target, missing adjacent occurrence, non-allow-listed URL, raw URL conflict during
clear, missing expected URL hash for clear, recurrence mutation, recurrence
clearing, all-day mutation, or alarm mutation returns an error preview before
mutation. Structured-location set/clear is governed by
`docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.
Target-calendar move is governed by
`docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation,
re-resolves the selected occurrence, re-checks recurrence shape,
occurrence/sibling identity, sibling URL state, expected state, and sends the
occurrence identity plus proposed/clear event URL state to the Swift EventKit
helper.

The Swift helper finds the selected occurrence by event identifier plus expected
start/end, validates exact expected state including URL presence/hash when
provided, validates the adjacent occurrence URL state, applies the approved URL
set or clear, saves with `span:.thisEvent`, then reads back the selected
occurrence and adjacent occurrence at their approved times.

Success requires:

- selected occurrence read-back matches the approved event URL hash or verified
  absence;
- selected occurrence read-back matches approved title/plain
  location/notes/start/end/time-zone/availability state;
- adjacent occurrence remains present, recurring, and URL-state preserved;
- helper returns `selected_occurrence_updated_verified:true` and
  `adjacent_occurrence_verified_present:true`;
- helper returns `adjacent_occurrence_event_url_verified:true`;
- adapter returns `event_url_verified:true` for set or
  `event_url_cleared_verified:true` for clear;
- no raw event URL is returned in preview or apply output.

If read-back proof is incomplete, apply returns `apply_unknown` with
`mutation_applied:true` instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply for
set and clear plus a direct existing-URL replacement smoke. Direct keys include
`calendar_recurrence_update_event_url_plan_status`,
`calendar_recurrence_update_event_url_plan_sha256`,
`calendar_recurrence_update_event_url_apply_status`,
`calendar_recurrence_update_event_url_apply_verified`,
`calendar_recurrence_update_event_url_apply_sha256`,
`calendar_recurrence_update_event_url_replace_plan_status`,
`calendar_recurrence_update_event_url_replace_plan_expected_present`,
`calendar_recurrence_update_event_url_replace_apply_status`,
`calendar_recurrence_update_event_url_replace_apply_verified`,
`calendar_recurrence_update_event_url_replace_apply_sha256`,
`calendar_recurrence_update_event_url_stale_apply_status`,
`calendar_recurrence_update_event_url_stale_mutation_applied`,
`calendar_recurrence_update_event_url_stale_warning`,
`calendar_recurrence_update_event_url_clear_plan_status`,
`calendar_recurrence_update_event_url_clear_plan_requested`,
`calendar_recurrence_update_event_url_clear_apply_status`, and
`calendar_recurrence_update_event_url_clear_apply_verified`. MCP keys include
`mcp_calendar_recurrence_update_event_url_plan_status`,
`mcp_calendar_recurrence_update_event_url_plan_scope`,
`mcp_calendar_recurrence_update_event_url_plan_sha256`,
`mcp_calendar_recurrence_update_event_url_apply_status`,
`mcp_calendar_recurrence_update_event_url_apply_verified`,
`mcp_calendar_recurrence_update_event_url_apply_sha256`,
`mcp_calendar_recurrence_update_event_url_clear_plan_status`,
`mcp_calendar_recurrence_update_event_url_clear_plan_requested`,
`mcp_calendar_recurrence_update_event_url_clear_apply_status`, and
`mcp_calendar_recurrence_update_event_url_clear_apply_verified`.

Source tests cover adapter planning/apply proof for selected occurrence event
URL set/clear/replacement, stale selected current-URL hash refusal, raw URL
non-disclosure, selected occurrence mismatch-to-`apply_unknown`, URL-present
adjacent occurrence preservation, stale adjacent occurrence URL-state refusal,
adjacent occurrence URL preservation mismatch, Swift helper source ordering,
public API audit expectations, and write-design audit coverage.

## Audit Contract Strings

Clearing requires `clear_event_url:true`, no `event_url`, `expected_event_url_present:true`, and `expected_event_url_sha256`.
Planning proves the event is recurring with a supported bounded recurrence payload.
Apply proof: selected occurrence read-back matches the approved event URL hash or verified absence.
Adjacent proof: adjacent occurrence remains present, recurring, and URL-state preserved.
Apply result: adapter returns `event_url_verified:true` for set or `event_url_cleared_verified:true` for clear.
Verification: Fixture-backed runtime verifier proves direct plan/apply, replacement, stale selected current-URL hash refusal, and MCP plan/apply for set and clear.

## Still Out Of Scope

- selected recurring occurrence all-day or target-calendar mutation outside the
  later dedicated gates;
- mid-series recurrence replacement;
- recurrence clearing beyond first-visible `.futureEvents` clear;
- attendee/invitation mutation;
- travel time;
- non-allow-listed URL schemes;
- procedure alarms.

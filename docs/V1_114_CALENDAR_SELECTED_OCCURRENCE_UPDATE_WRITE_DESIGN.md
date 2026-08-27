# V1.114 Calendar Selected Recurring Occurrence Update Write Design

Status: Apply-capable implementation.

This gate adds selected-occurrence scalar update for an existing recurring Calendar event. It stays local-only, EventKit-only, exact-handle gated, occurrence-bound, and approval-token gated.

Uses public EventKit `saveEvent:span:commit:` with `EKSpanThisEvent` to mutate only the selected occurrence.

## Approved Shape

- `recurrence_update_scope`: adapter/MCP string, currently only `this_event`.
- `--recurrence-update-scope this-event`: CLI spelling.
- Operation must be `update`.
- Target must be an exact occurrence-bound `calendar:event:v1:` handle from Calendar metadata output.
- Proposed changes are limited to `title`, plain `location`, and `notes`.
- Proposed `start_date`, `end_date`, `time_zone`, `all_day`, alarm fields, URL fields, availability, target calendar, and recurrence fields must match the expected state or be absent as required. Structured-location set/clear is governed by `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`.

## Planning Contract

Planning resolves the selected occurrence from the current EventKit event list, proves the handle binds start/end identity, proves the event is recurring with a supported bounded recurrence payload, and binds a sibling occurrence for preservation proof.

The preview includes:

- `preview.target.expected_state.recurrence_present:true`.
- `preview.target.expected_state.recurrence`.
- `preview.proposed.recurrence_update_scope:"this_event"`.
- `preview.proposed.occurrence_start_date` / `occurrence_end_date`.
- `preview.proposed.adjacent_occurrence_start_date` / `adjacent_occurrence_end_date`.

Invalid scope, non-update operation, missing occurrence identity, non-recurring target, missing adjacent occurrence, recurrence mutation, recurrence clearing, time mutation, availability mutation, alarm mutation, and URL mutation return an error preview before mutation. Target-calendar move is governed by `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`.

## Apply Contract

Apply re-plans, requires the exact approval token and explicit confirmation, re-resolves the selected occurrence, re-checks recurrence shape and occurrence/sibling identity against the approved preview, and sends the occurrence identity to the Swift EventKit helper.

The Swift helper finds the selected occurrence by event identifier plus expected start/end, validates exact expected state, applies only title/plain location/notes, saves with `span:.thisEvent`, then reads back the selected occurrence and adjacent occurrence.

Success requires:

- selected occurrence read-back matches approved title/plain location/notes;
- adjacent occurrence remains present;
- helper returns `selected_occurrence_updated_verified:true` and `adjacent_occurrence_verified_present:true`.

If read-back proof is incomplete, apply returns `apply_unknown` with mutation_applied true instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct plan/apply and MCP plan/apply. Direct keys include `calendar_recurrence_update_plan_scope`, `calendar_recurrence_update_plan_expected_frequency`, `calendar_recurrence_update_apply_scope`, `calendar_recurrence_update_apply_selected_verified`, and `calendar_recurrence_update_apply_adjacent_present`. MCP keys include `mcp_calendar_recurrence_update_apply_scope`, `mcp_calendar_recurrence_update_apply_selected_verified`, and `mcp_calendar_recurrence_update_apply_adjacent_present`.

Source tests cover adapter planning/apply proof, time-mutation refusal, CLI flag routing, MCP fail-closed behavior without occurrence identity, Swift helper source ordering, public API audit expectations, and write-design audit coverage.

## Still Out Of Scope

- selected recurring occurrence time/all-day/time-zone rescheduling;
- selected recurring occurrence alarm, URL, availability, or target-calendar mutation outside the later dedicated gates;
- mid-series recurrence replacement;
- recurrence clearing beyond first-visible `.futureEvents` clear;
- attendee/invitation mutation;
- travel time;
- non-allow-listed URL schemes;
- procedure alarms.

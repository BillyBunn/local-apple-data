# V1.174 Calendar Future Series All Day Write Design

Status: Apply-capable implementation.

This gate sets or clears the all-day state, or performs a same-state all-day date-only reschedule, for the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- All-day-only mutation using exact `all_day:true` with date-only proposed `start_date`/`end_date` for timed-to-all-day set, exact `all_day:false` with timestamp proposed `start_date`/`end_date` plus explicit proposed `time_zone` for all-day-to-timed clear, or same-state all-day date-only reschedule with `expected_all_day:true`, `all_day:true`, and date-only proposed `start_date`/`end_date` different from the expected date-only range.
- Timed-to-all-day set requires `expected_time_zone` because the current occurrence is timed.
- Because an all-day conversion changes the stored date representation, this gate always reuses the future-series original-slot machinery from `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Clear requires expected all-day state bound through `expected_all_day:true` with date-only expected start/end identity.
- No recurrence fields, `clear_recurrence`, title/notes mutation, plain-location mutation, availability mutation, event URL mutation, structured-location mutation, display/action alarm mutation, target calendar move, or procedure alarms; the proposed alarm state must equal the expected alarm state.
- Proposing the same all-day state as the expected value without a date-only all-day reschedule is rejected as a no-op.

## Plan Contract

- Requires exact current title, calendar title, start/end, notes, all-day, time-zone, event URL state, structured-location state, alarm state, and recurrence bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state, and the explicit proposed all-day set/clear/date-only reschedule state into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, scalar fields, plain-location mutation, availability mutation, event URL mutation, structured-location mutation, display/action alarm mutation, target-calendar move, or co-mutation with any other future-series update flag including timed-reschedule-only updates.
- Requires date-only proposed `start_date`/`end_date` plus `expected_time_zone` for timed-to-all-day set and explicit proposed `time_zone` for all-day-to-timed clear before mutation.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and all-day plus start/end/time-zone state matches the approved value;
- future occurrence recurrence shape still matches expected recurrence and all-day plus start/end/time-zone state matches the approved value;
- original selected and future slots are absent or hold an approved-replacement occurrence, because an all-day conversion or date-only reschedule always counts as a date change;
- previous occurrence remains present with the original expected title, plain/structured location, notes, all-day/timed state, availability, URL hash state, alarm state, and recurrence;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state, and the proposed all-day set/clear/date-only reschedule request through `future_series_all_day_update_requested`.
- Adapter apply requires all-day, selected, future, previous, and original-slot proof booleans before reporting success; all-day flips and date-only reschedules always trigger the original selected/future slot absence-or-approved-replacement proof.
- CLI accepts and forwards `--recurrence-update-scope future-events` with date-only `--start-date`/`--end-date` plus `--all-day` plus `--expected-time-zone` for set, `--time-zone` plus `--expected-all-day` for clear, and no recurrence fields.
- The Swift helper computes future-occurrence read-back slots with calendar-day arithmetic (whole-day delta over `startOfDay` values anchored to the proposed wall-clock time: midnight in the local calendar for all-day results, the proposed time zone for all-day-to-timed clears) instead of absolute TimeInterval deltas, so day shifts that cross a DST transition read back the correct slot; the pure timed reschedule gate keeps its approved v1.168 interval behavior.
- Runtime verifier proves direct and MCP future-series all-day set, clear, and date-only reschedule plan/apply paths through `calendar_future_series_all_day_*` and `mcp_calendar_future_series_all_day_*` keys including `calendar_future_series_all_day_apply_verified`, `calendar_future_series_all_day_clear_apply_verified`, and `calendar_future_series_all_day_reschedule_apply_verified`; Swift read-back verifies selected/future occurrence recurrence and all-day plus date state before returning proof booleans.
- Named regressions include `test_apply_calendar_change_updates_future_series_all_day`, `test_apply_calendar_change_clears_future_series_all_day`, `test_apply_calendar_change_reschedules_future_series_all_day_date_only`, `test_apply_calendar_change_reschedules_future_series_all_day_across_dst_boundary`, `test_apply_calendar_change_rejects_missing_future_series_all_day_proof`, `test_plan_calendar_change_update_future_series_all_day_rejects_co_mutations`, `test_plan_calendar_change_future_series_all_day_requires_date_only`, `test_plan_calendar_change_future_series_all_day_set_requires_expected_time_zone`, `test_plan_calendar_change_future_series_all_day_clear_requires_time_zone`, and `test_plan_calendar_change_future_series_all_day_flip_excludes_timed_reschedule`.

## Still Blocked

- Future-series target-calendar move is handled by `docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`.
- Future-series scalar update is handled by `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Future-series event URL set/clear is handled by `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`.
- Future-series structured-location set/clear is handled by `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`.
- Future-series display-alarm-only set/clear is handled by `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`.
- Future-series action-alarm set/clear is handled by `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

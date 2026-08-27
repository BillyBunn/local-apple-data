# V1.172 Calendar Future Series Display Alarm Write Design

Status: Apply-capable implementation.

This gate sets or clears the display alarms for the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Display-alarm-only mutation using bounded relative `alarm_offsets_minutes` or bounded absolute `alarm_absolute_dates`, or a display-alarm clear with empty proposed offsets and absolute dates.
- Clear requires non-empty expected display-alarm state through exact `expected_alarm_offsets_minutes` or `expected_alarm_absolute_dates`.
- No recurrence fields, `clear_recurrence`, title/notes mutation, plain-location mutation, timed or all-day mutation, availability mutation, event URL mutation, structured-location mutation, target calendar move, or action-alarm (sound/email/geofence) mutation.
- Proposing the same display-alarm state as the expected value is rejected as a no-op.

## Plan Contract

- Requires exact current title, calendar title, start/end, notes, all-day, time-zone, event URL state, structured-location state, alarm state, and recurrence bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, and proposed display-alarm set/clear state into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, scalar fields, plain-location mutation, timed/all-day mutation, availability mutation, event URL mutation, structured-location mutation, target-calendar move, or action-alarm co-mutation.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and display-alarm set/clear state matches the approved value;
- future occurrence recurrence shape still matches expected recurrence and display-alarm set/clear state matches the approved value;
- previous occurrence remains present with the original expected title, plain/structured location, notes, timed state, availability, URL hash state, alarm state, and recurrence;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display-alarm state, and proposed display-alarm set/clear request.
- Adapter apply requires display-alarm, selected, future, and previous proof booleans before reporting success.
- CLI accepts and forwards `--recurrence-update-scope future-events` with `--alarm-offsets-minutes` or `--alarm-absolute-dates` plus expected display-alarm state and no recurrence fields.
- Runtime verifier proves direct and MCP future-series display-alarm plan/apply paths; Swift read-back verifies selected/future occurrence recurrence and display-alarm set/clear state before returning proof booleans.

## Still Blocked

- Future-series all-day conversion or calendar move edits.
- Future-series action-alarm set/clear is handled by `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`.
- Future-series scalar update is handled by `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Future-series event URL set/clear is handled by `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`.
- Future-series structured-location set/clear is handled by `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

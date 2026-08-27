# V1.173 Calendar Future Series Action Alarm Write Design

Status: Apply-capable implementation.

This gate sets or clears the action alarms (audio sound-name alarms, email alarms, structured geofence alarms) for the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Action-alarm-only mutation using exact `alarm_sound_name` audio alarms, exact `alarm_email_address` email alarms, or exact `alarm_proximity` plus `alarm_structured_location` geofence alarms, or an action-alarm clear with empty proposed action-alarm state.
- Because EventKit saves alarms as a whole set, the proposed display trigger fields (`alarm_offsets_minutes` / `alarm_absolute_dates`) may change together with the action-alarm fields; the plan binds the complete explicit proposed trigger and action state.
- Raw `alarm_email_address` is accepted only as plan/apply input; preview, read-back, and logs carry only `alarm_email_address_sha256` and never a raw email address.
- Clear requires non-empty expected action-alarm state through exact `expected_alarm_sound_name`, `expected_alarm_email_address_sha256`, or `expected_alarm_proximity` plus `expected_alarm_structured_location`.
- No recurrence fields, `clear_recurrence`, title/notes mutation, plain-location mutation, timed or all-day mutation, availability mutation, event URL mutation, structured-location mutation, target calendar move, or procedure alarms.
- Proposing the same action-alarm state as the expected value is rejected as a no-op.

## Plan Contract

- Requires exact current title, calendar title, start/end, notes, all-day, time-zone, event URL state, structured-location state, alarm state, and recurrence bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state, and the explicit proposed trigger/action alarm set/clear state into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, scalar fields, plain-location mutation, timed/all-day mutation, availability mutation, event URL mutation, structured-location mutation, target-calendar move, or co-mutation with any other future-series update flag including display-alarm-only updates.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and action-alarm plus trigger set/clear state matches the approved value;
- future occurrence recurrence shape still matches expected recurrence and action-alarm plus trigger set/clear state matches the approved value;
- previous occurrence remains present with the original expected title, plain/structured location, notes, timed state, availability, URL hash state, alarm state, and recurrence;
- email alarm proof stays hash-only through `alarm_email_address_sha256` with no raw email output;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state, and the proposed action-alarm set/clear request.
- Adapter apply requires action-alarm, selected, future, and previous proof booleans before reporting success.
- CLI accepts and forwards `--recurrence-update-scope future-events` with `--alarm-sound-name`, `--alarm-email-address`, or `--alarm-proximity` plus `--alarm-structured-location-*` and their expected-state bindings and no recurrence fields.
- Runtime verifier proves direct and MCP future-series action-alarm plan/apply paths with audio alarms and asserts no raw email key appears in any output; Swift read-back verifies selected/future occurrence recurrence and action-alarm plus trigger set/clear state before returning proof booleans.

## Still Blocked

- Future-series calendar move edits.
- Future-series all-day set/clear/date-only reschedule is handled by `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`.
- Future-series scalar update is handled by `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Future-series event URL set/clear is handled by `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`.
- Future-series structured-location set/clear is handled by `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`.
- Future-series display-alarm-only set/clear is handled by `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

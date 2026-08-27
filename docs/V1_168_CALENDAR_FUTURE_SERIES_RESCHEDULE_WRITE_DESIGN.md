# V1.168 Calendar Future Series Reschedule Write Design

Status: Apply-capable implementation.

This gate reschedules the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, timed-event only, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Timed `start_date`, `end_date`, and/or `time_zone` changes.
- Optional title, plain `location`, and `notes` changes may ride with the same future-series save.
- No recurrence fields, `clear_recurrence`, all-day conversion, target calendar move, availability, event URL, structured location, or alarm mutation.
- Requires explicit `time_zone` and `expected_time_zone`.
- Requires at least one of start, end, or time zone to differ from expected state.

## Plan Contract

- Requires exact current title, calendar title, start/end, expected time zone, location, notes, all-day, availability, URL hash state, structured-location state, and alarm-state bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, and proposed timed fields into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, all-day conversion, target-calendar move, availability, event URL, structured-location, or alarm co-mutation.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and timed read-back matches the approved start, end, and time zone;
- future occurrence recurrence shape still matches expected recurrence and the same timed delta is present on the future occurrence;
- old selected and future slots are absent or occupied by the approved rescheduled occurrence when the start/end instants move;
- previous occurrence remains present with the original expected title, plain location, notes, timed state, and recurrence;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, explicit expected/proposed time zones, and timed fields.
- Adapter apply requires selected, future, previous, and original-slot absence-or-approved-replacement proof booleans before reporting success.
- CLI accepts and forwards `--recurrence-update-scope future-events` with timed start/end/time-zone fields and no recurrence fields.
- Runtime verifier proves direct and MCP future-series timed-reschedule plan/apply paths; Swift read-back verifies selected/future occurrence dates and time zones before returning proof booleans.

## Still Blocked

- Future-series all-day conversion, structured-location, alarm, or calendar move edits.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

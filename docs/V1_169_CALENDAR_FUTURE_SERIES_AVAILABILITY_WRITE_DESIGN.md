# V1.169 Calendar Future Series Availability Write Design

Status: Apply-capable implementation.

This gate updates the availability for the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, availability-only, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Availability-only mutation using `availability` plus `expected_availability`.
- Availability values are limited to busy, free, tentative, or unavailable, and remain gated by EventKit target-calendar support-mask validation.
- No recurrence fields, `clear_recurrence`, title/plain-location/notes mutation, timed or all-day mutation, target calendar move, event URL, structured location, or alarm mutation.
- Requires `availability` different from `expected_availability`.

## Plan Contract

- Requires exact current title, calendar title, start/end, expected availability, location, notes, all-day, time-zone, URL hash state, structured-location state, and alarm-state bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, and proposed availability into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, scalar fields, timed/all-day mutation, target-calendar move, event URL, structured-location, or alarm co-mutation.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and availability read-back matches the approved value;
- future occurrence recurrence shape still matches expected recurrence and availability read-back matches the approved value;
- previous occurrence remains present with the original expected title, plain location, notes, timed state, availability, and recurrence;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, expected availability, and proposed availability.
- Adapter apply requires availability, selected, future, and previous proof booleans before reporting success.
- CLI accepts and forwards `--recurrence-update-scope future-events` with `--availability` / `--expected-availability` and no recurrence fields.
- Runtime verifier proves direct and MCP future-series availability plan/apply paths; Swift read-back verifies selected/future occurrence recurrence and availability before returning proof booleans.

## Still Blocked

- Future-series all-day conversion, structured-location, alarm, or calendar move edits.
- Future-series scalar update is handled by `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

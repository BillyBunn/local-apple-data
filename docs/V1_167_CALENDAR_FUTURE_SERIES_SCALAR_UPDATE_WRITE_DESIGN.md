# V1.167 Calendar Future Series Scalar Update Write Design

Status: Apply-capable implementation.

This gate updates title, plain location, and/or notes for the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, scalar-only, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Title, plain `location`, and `notes` only.
- No recurrence fields, `clear_recurrence`, time/all-day/time-zone change, target calendar move, availability, event URL, structured location, or alarm mutation.
- Requires at least one of title, plain location, or notes to differ from expected state.

## Plan Contract

- Requires exact current title, calendar title, start/end, location, notes, all-day, time-zone, availability, URL hash state, structured-location state, and alarm-state bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, and proposed scalar fields into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous occurrence identity against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, target-calendar move, availability, event URL, structured-location, alarm, time, time-zone, or all-day co-mutation.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and scalar read-back matches the approved title, plain location, and notes;
- future occurrence recurrence shape still matches expected recurrence and scalar read-back matches the approved title, plain location, and notes;
- previous occurrence remains present with the original expected title, plain location, notes, and recurrence;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, and scalar fields.
- Adapter apply requires selected, future, and previous occurrence read-back booleans before reporting success.
- CLI accepts and forwards `--recurrence-update-scope future-events` with scalar title/location/notes fields and no recurrence fields.
- Runtime verifier proves direct and MCP future-series scalar plan/apply paths; Swift read-back enforces selected/future recurrence-shape matches before returning those proof booleans.

## Still Blocked

- Future-series all-day conversion, structured-location, alarm, or calendar move edits.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

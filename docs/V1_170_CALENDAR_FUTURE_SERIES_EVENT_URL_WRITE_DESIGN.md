# V1.170 Calendar Future Series Event URL Write Design

Status: Apply-capable implementation.

This gate sets or clears the event URL for the selected occurrence and all future occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, hash-only on output, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Event URL-only mutation using one allow-listed `event_url` or `clear_event_url:true`.
- URL output remains hash-only: no raw existing or applied URL is returned.
- No recurrence fields, `clear_recurrence`, title/plain-location/notes mutation, timed or all-day mutation, availability mutation, target calendar move, structured location, or alarm mutation.
- Setting the same URL as the expected current URL is rejected as a no-op.
- Clearing requires `expected_event_url_present:true` plus exact `expected_event_url_sha256`.

## Plan Contract

- Requires exact current title, calendar title, start/end, location, notes, all-day, time-zone, URL hash state, structured-location state, and alarm-state bindings already used by the Calendar update gate.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, selected occurrence identity, previous occurrence identity, future occurrence identity, and proposed URL hash or clear request into the approval fingerprint.
- Returns a normal `calendar-apply:v1:<approval_fingerprint>` token and keeps the operation non-mutating.

## Apply Contract

- Requires the matching approval token and explicit confirmation.
- Revalidates the selected occurrence and expected recurrence before mutation.
- Revalidates the previous and future occurrence identities against the selected series before mutation.
- Refuses recurrence add/replacement, recurrence clear, scalar fields, timed/all-day mutation, availability mutation, target-calendar move, structured-location, or alarm co-mutation.
- Saves with EventKit `.futureEvents`.

## Read-Back Proof

Apply must prove:

- selected occurrence recurrence shape still matches expected recurrence and URL hash or absence matches the approved value;
- future occurrence recurrence shape still matches expected recurrence and URL hash or absence matches the approved value;
- previous occurrence remains present with the original expected title, plain location, notes, timed state, availability, URL hash state, and recurrence;
- `future_series_update_read_back_mismatch` is returned instead of success when any proof fails.

## Implementation Notes

- Adapter plan binds expected recurrence, selected occurrence identity, previous occurrence identity, future occurrence identity, expected URL state, and proposed URL hash or clear request.
- Adapter apply requires event URL, selected, future, and previous proof booleans before reporting success.
- CLI accepts and forwards `--recurrence-update-scope future-events` with `--event-url` or `--clear-event-url` plus expected URL state and no recurrence fields.
- Runtime verifier proves direct and MCP future-series event URL plan/apply paths; Swift read-back verifies selected/future occurrence recurrence and URL hash or absence before returning proof booleans.

## Still Blocked

- Future-series all-day conversion, alarm, or calendar move edits.
- Future-series scalar update is handled by `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`.
- Future-series timed reschedule is handled by `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`.
- Future-series availability update is handled by `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`.
- Future-series structured-location set/clear is handled by `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`.
- Non-allow-listed event URL schemes.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.
- Custom recurrence shapes beyond approved selector-backed EventKit rules.

# v1.87 Calendar Explicit Time Zone Write Design

## Scope

Add explicit timed-event time zone support to the existing Calendar plan/apply gate.

Approved:

- `calendar plan` / `calendar_plan_change` may accept optional `time_zone` for timed create/update and optional `expected_time_zone` for exact update/delete expected-state binding.
- `calendar apply` / `calendar_apply_change` may set `EKCalendarItem.timeZone` only after a matching approval token and `confirm_apply:true`.
- Exact detail and apply read-back may return the bounded time zone identifier as metadata; title-search metadata must not include `time_zone`.

Still blocked:

- All-day `time_zone` or `expected_time_zone`.
- Time zone guessing or local-default inference.
- Date-only parsing beyond explicit all-day timestamps.
- Recurrence, attendees/invitations, travel time, email/procedure alarms, calendar account management, and default-calendar mutation. Exact absolute display alarms are governed by `docs/V1_88_CALENDAR_ABSOLUTE_ALARM_WRITE_DESIGN.md`.

## Source Review

The local macOS SDK EventKit headers expose `EKCalendarItem.timeZone` as a writable `NSTimeZone *` property. `EKCalendarItem.attendees` remains readonly. Exact absolute display alarms are governed by `docs/V1_88_CALENDAR_ABSOLUTE_ALARM_WRITE_DESIGN.md`; recurrence rules, travel time, structured/geofence alarms, email/procedure alarms, and attendee mutation require separate gates because they change mutation semantics and read-back safety.

## Gate

Planning validates `time_zone` and `expected_time_zone` with Python `zoneinfo` and accepts only IANA identifiers such as `America/Los_Angeles`. Empty values mean no explicit time zone binding. Path-like labels such as `/etc/passwd` and `../../etc/passwd` are invalid and must return bounded `invalid_time_zone` warnings, not raw exceptions.

Apply recomputes the plan fingerprint from the same inputs, requires the matching `calendar-apply:v1:` token, and only then passes the exact identifier to the Swift EventKit helper.

The Swift helper validates identifiers with `TimeZone(identifier:)`, sets `event.timeZone` only when an explicit timed-event `time_zone` is present, and checks `event.timeZone?.identifier` against `expected_time_zone` before update/delete when expected state binds it.

## Read-Back

Create/update apply and exact detail retrieval require EventKit read-back. Output may include:

- `time_zone`
- existing bounded metadata

Output must not include raw EventKit identifiers other than opaque handles, attendee identifiers, calendar account identifiers, notes text in mutation read-back, or inferred/default time zone guesses.

Calendar title search remains metadata-only and must not return `time_zone`; agents that need the explicit event time zone must use an exact `calendar:event:v1:` handle detail or apply read-back path.

## Tests

Required proof:

- Python plan validation accepts IANA identifiers and rejects non-IANA/path-like labels.
- All-day events reject `time_zone` and `expected_time_zone`.
- Calendar search omits `time_zone`; exact detail and create/update apply read-back may return it.
- MCP and CLI wrappers forward `time_zone` and `expected_time_zone`.
- Runtime verification includes direct and MCP timezone binding proof.
- Installed-cache verifier and MCP runner startup do not leave bytecode artifacts after runtime proof.

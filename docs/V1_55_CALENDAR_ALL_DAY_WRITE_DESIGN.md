# v1.55 Calendar All-Day Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar create/update/delete gate with explicit all-day event support. Calendar alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`. It does not approve recurrence, attendees, invitations, URLs, attachments, availability, travel time, calendar moves, default-calendar guessing, or bulk operations.

## Scope

Approved operation expansion:

- `create`: create one timed or all-day event in an explicit target calendar.
- `update`: update one exact timed or all-day `calendar:event:v1:` handle.
- `delete`: delete one exact timed or all-day `calendar:event:v1:` handle.

Required all-day fields:

- `all_day`: boolean flag for create/update.
- `expected_all_day`: boolean expected-state flag for update/delete.
- `start_date` and `end_date`: ISO 8601 timestamps with timezone. All-day events still require explicit start/end instants; the plugin does not infer dates, time zones, or durations.

Strict JSON booleans are required for `all_day` and `expected_all_day`; string values such as `"false"` are rejected before approval fingerprinting.

Out of scope:

- Default-calendar guessing.
- Date-only parsing or time-zone guessing.
- Recurrence, attendee, invitation, URL, attachment, travel-time, availability, or calendar/account mutation.
- Bulk Calendar mutation.

## Safety Contract

Plan stays non-mutating. It normalizes the existing title/calendar/start/end/location/notes fields, binds `all_day` or `expected_all_day` into the preview, idempotency key, and approval fingerprint, and returns `mutation_applied:false`.

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends the all-day flags to the Swift EventKit helper only after token verification.

For update/delete, the Swift helper rechecks title, calendar title, start date, end date, all-day flag, location, notes, recurrence, and attendees before mutation. For update, stale expected-state mismatch is checked before already-applied handling so a stale approval cannot be masked by a live event that already matches the proposed state. Recurring or attendee-bearing events remain unsupported. All-day events are no longer rejected solely for being all-day.

Read-back returns bounded event metadata through the existing Calendar adapter. Apply output may include the all-day boolean but must not return raw EventKit identifiers, account identifiers, framework exception text, or unrelated event content.

## Synthetic Tests Required

- Plan success for all-day create with `all_day:true`.
- Apply success for all-day create with read-back `all_day:true`.
- Apply success for all-day update with `expected_all_day:true` and proposed `all_day:true`.
- Apply success for all-day delete with `expected_all_day:true` and absence proof.
- CLI all-day plan/apply flag routing.
- MCP all-day plan/apply preview token binding without live EventKit.
- Runtime synthetic smoke proving all-day create plan/apply through the verifier.
- Write-design gate coverage for all-day source tests and runtime proof.
- Static Swift regression proving exact alarm-offset support is delegated to `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.

## Current Release Gate

This release approves only explicit all-day support inside the existing exact Calendar create/update/delete gates. Calendar recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, calendar/account management, default-calendar guessing, date-only/time-zone inference, move, and bulk operations remain blocked.

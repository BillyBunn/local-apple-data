# V1.101 Calendar Month-Day Recurrence Write Design

Status: Apply-capable implementation.

This gate extends the existing bounded Calendar recurrence create and add-to-non-recurring-event update surface with explicit month-day selection for monthly recurrence only. It stays local-only, EventKit-only, exact-target gated, and finite-bound only. It uses the public EventKit `EKRecurrenceRule` `daysOfTheMonth` initializer/read-back surface and does not add attendee, invitation, unbounded recurrence, mid-series recurrence replacement, existing-recurring-event mutation, custom yearly recurrence rules beyond yearly BYMONTH/BYMONTH+nth-BYDAY/BYYEARDAY/BYWEEK, non-allow-listed URL, or alarm-type semantics.

## Scope

- `recurrence_month_days`: adapter/MCP list or comma-separated adapter value.
- `--recurrence-month-days`: CLI comma-separated integers from -31 through -1 or 1 through 31.
- Positive values count from the start of the month. Negative values count from the end of the month. Zero is invalid.
- Supported only with `recurrence_frequency:"monthly"`.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound using either `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update. Delete recurrence scopes are unchanged.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Normalizes duplicate and unordered month-day input into ascending integer order.
- Adds `month_days:[...]` inside `preview.proposed.recurrence` only when explicit month days are requested.
- Binds month days into the approval fingerprint and idempotency key.
- Refuses month-day input for non-monthly frequencies with `invalid_recurrence`.
- Refuses zero, out-of-range, boolean, string-list, and non-integer month-day values with `invalid_recurrence`.
- Leaves existing simple recurrence payloads unchanged when no month days are requested.

## Apply Contract

Apply requires the existing exact matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- For create, applies an `EKRecurrenceRule` using EventKit's designated initializer with `daysOfTheMonth`.
- For update, still requires an exact event handle, expected current state, and `expected_recurrence_present:false`; existing recurring events remain blocked from recurrence mutation.
- Applies only to the selected exact create/update event through the existing Calendar apply gate.
- Reports month-day recurrence only after EventKit read-back returns the same bounded monthly rule and month-day set.
- If EventKit apply succeeds but read-back cannot prove the requested month-day recurrence, apply returns failure/partial according to the existing Calendar read-back contract rather than claiming success.

## Verification

Covered checks:

- Adapter create plan canonicalizes month days and binds them into recurrence preview and approval fingerprint.
- Adapter update plan supports monthly month days only for add-to-non-recurring-event update.
- Adapter rejects invalid month days and non-monthly month-day recurrence.
- Adapter apply forwards month-day recurrence to the helper and requires matching read-back.
- CLI accepts `--recurrence-month-days` for plan/apply.
- In-process MCP plan exposes `recurrence_month_days`.
- Runtime verifier proves direct plan/apply read-back for `[1, 15, -1]` canonicalized to `[-1, 1, 15]` and MCP plan proof for the same set.
- Swift source parses `recurrence_month_days`, uses `daysOfTheMonth`, and compares read-back month days in `recurrenceMatches`.

## Still Blocked

- mid-series recurrence replacement
- existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete
- custom monthly recurrence components beyond monthly BYDAY/BYMONTHDAY/monthly nth-weekday
- custom yearly recurrence rules
- unbounded recurrence
- attendee/invitation mutation
- travel time
- email/procedure alarms
- non-allow-listed URL schemes
- bulk Calendar mutation

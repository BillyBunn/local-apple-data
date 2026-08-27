# V1.99 Calendar Weekly Weekday Recurrence Write Design

Status: Apply-capable implementation.

This gate extends the existing bounded Calendar recurrence create and add-to-non-recurring-event update surface with explicit weekday selection for weekly recurrence only. It stays local-only, EventKit-only, exact-target gated, and finite-bound only. It does not add attendee, invitation, unbounded recurrence, mid-series recurrence replacement, existing-recurring-event mutation, non-allow-listed URL, or alarm-type semantics.

## Scope

- `recurrence_weekdays`: adapter/MCP list or comma-separated adapter value.
- `--recurrence-weekdays`: CLI comma-separated weekday names or integers 1 through 7.
- Accepted weekday aliases normalize to canonical names: `sunday`, `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`.
- Supported only with `recurrence_frequency:"weekly"`.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound using either `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update. Delete recurrence scopes are unchanged.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Normalizes duplicate and unordered weekday input into canonical weekday order.
- Adds `weekdays:[...]` inside `preview.proposed.recurrence` only when explicit weekdays are requested.
- Binds weekdays into the approval fingerprint and idempotency key.
- Refuses weekday input for non-weekly frequencies with `invalid_recurrence`.
- Refuses invalid weekday values with `invalid_recurrence`.
- Leaves existing simple recurrence payloads unchanged when no weekdays are requested.

## Apply Contract

Apply requires the existing exact matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- For create, applies an `EKRecurrenceRule` using EventKit's designated initializer with `daysOfTheWeek`.
- For update, still requires an exact event handle, expected current state, and `expected_recurrence_present:false`; existing recurring events remain blocked from recurrence mutation.
- Applies only to the selected exact create/update event through the existing Calendar apply gate.
- Reports weekday recurrence only after EventKit read-back returns the same bounded weekly rule and weekday set.
- If EventKit apply succeeds but read-back cannot prove the requested weekday recurrence, apply returns failure/partial according to the existing Calendar read-back contract rather than claiming success.

## Verification

Covered checks:

- Adapter create plan canonicalizes weekday aliases and binds weekdays into recurrence preview and approval fingerprint.
- Adapter update plan supports weekly weekdays only for add-to-non-recurring-event update.
- Adapter rejects invalid weekdays and non-weekly weekday recurrence.
- Adapter apply forwards weekday recurrence to the helper and requires matching read-back.
- CLI accepts `--recurrence-weekdays` for plan/apply.
- In-process MCP plan exposes `recurrence_weekdays`.
- Runtime verifier proves direct plan/apply read-back for `["monday", "wednesday", "friday"]` and MCP plan proof for the same weekday set.
- Swift source parses `recurrence_weekdays`, uses `EKRecurrenceDayOfWeek`, and compares read-back weekdays in `recurrenceMatches`.

## Still Blocked

- mid-series recurrence replacement
- existing-recurring-event update beyond selected/future-span/whole-series occurrence delete
- custom monthly/yearly recurrence components
- unbounded recurrence
- attendee/invitation mutation
- travel time
- email/procedure alarms
- non-allow-listed URL schemes
- bulk Calendar mutation

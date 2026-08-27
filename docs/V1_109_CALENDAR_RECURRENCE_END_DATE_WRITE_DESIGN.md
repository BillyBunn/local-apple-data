# V1.109 Calendar Recurrence End-Date Write Design

## Scope

Status: Apply-capable implementation.

This gate extends the bounded Calendar recurrence write surface with finite recurrence end dates through public EventKit `EKRecurrenceEnd(end:)`.

Approved inputs:

- `recurrence_end_date`: optional finite recurrence end timestamp for create/update.
- `--recurrence-end-date`: CLI ISO 8601 timestamp with timezone.

Exactly one of `recurrence_count` or `recurrence_end_date` is required when recurrence is requested. Count-bounded recurrence remains unchanged.

## Source Review

The local macOS SDK EventKit headers expose `EKRecurrenceEnd` as a public recurrence end object that can be created with either an occurrence count or an `NSDate` end date, and `EKRecurrenceRule` accepts a recurrence end. This gate uses only that public local SDK surface.

This gate approves only finite recurrence end dates. v1.139 separately approves explicit unbounded recurrence through nil `recurrenceEnd`; implicit unbounded recurrence remains blocked.

## Planning Contract

Plan stays non-mutating. It validates:

- `recurrence_end_date` is an ISO 8601 timestamp with timezone
- Rejects date-only recurrence end values.
- `recurrence_count` and `recurrence_end_date` are mutually exclusive
- recurrence requests include exactly one finite end bound for this v1.109 path
- Rejects `recurrence_end_date` at or before `start_date`.
- Rejects `recurrence_end_date` beyond 3650 days from `start_date`.
- all existing recurrence frequency, interval, weekday, month-day, monthly nth-weekday, and yearly month constraints still apply

Applies only to event create and add-to-non-recurring-event update.

Preview stores the normalized end date as `preview.proposed.recurrence.end_date` with `count:0`. Binds `end_date` into the approval fingerprint and idempotency key.

## Apply Contract

Apply requires the existing matching approval token and `confirm_apply:true`. The Swift helper re-validates the finite end-date shape, rejects count/end-date conflicts, rejects date-only end values, rechecks the bounded horizon against `start_date`, applies public EventKit `EKRecurrenceEnd(end:)`, and saves through EventKit.

Read-back must prove the same finite recurrence `end_date`. If read-back is missing or mismatched, apply returns `apply_unknown` with `recurrence_read_back_mismatch` and `mutation_applied:true`.

Existing selected-occurrence, future-span, whole-series delete, and first-visible recurrence-clear gates accept date-ended recurrence only after exact recurrence/occurrence binding. Delete apply now forwards exact `expected_recurrence` and Swift validates `recurrenceMatches(event, expectedRecurrence)` before removal.

Runtime verifier proves direct create plan/apply read-back and MCP plan plus invalid-token apply proof.

## Out Of Scope

- implicit unbounded recurrence
- date-only recurrence end values
- recurrence end dates beyond 3650 days from `start_date`
- mid-series recurrence replacement
- changing an existing recurring event except first-visible clear and selected/future-span/whole-series delete
- attendee/invitation mutation
- travel time
- procedure alarms

# v1.89 Calendar Simple Recurrence Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extended the existing Calendar create gate with simple bounded recurrence at v1.89. Later v1.93 support is governed by `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`. This document does not approve recurring-event deletes, attendees, invitations, default-calendar guessing, date-only parsing beyond explicit all-day, travel time, email/procedure alarms, monthly/yearly recurrence rules, custom weekday/month rules, unbounded recurrence, or bulk operations.

## Scope

Approved operation expansion:

- `create`: create one timed or explicit all-day event with one optional simple recurrence rule.

Recurrence fields:

- `recurrence_frequency`: `daily` or `weekly`.
- `recurrence_interval`: integer interval from 1 through 4. Omitted interval defaults to 1 only when recurrence is otherwise requested.
- `recurrence_count`: integer occurrence count from 2 through 52. Required when recurrence is requested.

The create plan returns a bounded `recurrence` preview and `recurrence_present:true` when recurrence is requested. The approval fingerprint binds the normalized frequency, interval, and count.

## Source Review

The local macOS SDK EventKit headers expose writable `EKCalendarItem.recurrenceRules`, plus `addRecurrenceRule:` and `removeRecurrenceRule:`. They also state recurrence rules cannot be modified directly; a caller must create a new rule and set it on the event.

The local SDK exposes `EKRecurrenceRule`, `EKRecurrenceEnd(occurrenceCount:)`, and `EKRecurrenceFrequency` values including daily and weekly. The implementation uses only `EKRecurrenceRule(recurrenceWith:interval:end:)` with an occurrence-count end. It does not set weekday, month, set-position, day-of-month, day-of-year, or unbounded rules.

The same source review confirms `EKCalendarItem.attendees` and `EKEvent.organizer` are readonly, so attendee/invitation mutation remains blocked.

## Safety Contract

Plan stays non-mutating. It validates recurrence before any approval fingerprint is returned. Invalid recurrence shapes return bounded `invalid_recurrence` warnings.

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends the normalized recurrence request to the Swift EventKit helper only after token verification.

The Swift helper creates exactly one `EKRecurrenceRule` for create. At v1.89, update and delete rejected proposed recurrence inputs with `unsupported_recurrence_for_operation`. Later v1.93 support is governed by `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`. Existing recurring events remain unsupported for update/delete through the existing bounded-mutation state check; they are not silently changed with `.futureEvents` or detached occurrence semantics.

Read-back returns only bounded recurrence metadata: `recurrence_present`, `frequency`, `interval`, and `count`. Apply output must not return raw EventKit identifiers, account identifiers, attendee identifiers, raw recurrence objects, framework exception text, or unrelated event content.

## Synthetic Tests Required

- Plan success for create with weekly recurrence, normalized interval/count, approval-token binding, and no mutation.
- Invalid recurrence shape refusals for unsupported frequency, invalid interval, and invalid count.
- Update/delete recurrence inputs refused before apply.
- Apply success for recurring create with read-back recurrence metadata.
- CLI recurrence plan/apply routing.
- MCP recurrence plan/apply preview-token binding without live EventKit.
- Runtime synthetic smoke proving direct recurrence create plan/apply and MCP recurrence plan plus invalid-token apply.
- Static Swift regression proving `EKRecurrenceRule(recurrenceWith:interval:end:)`, `EKRecurrenceEnd(occurrenceCount:)`, `event.recurrenceRules = [...]`, no `.futureEvents`, and unsupported update/delete recurrence refusal.

## Historical Release Gate

This v1.89 release approved only simple count-bound daily/weekly recurrence on Calendar create. Current recurrence-update support is governed by `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`. Calendar update/delete of existing recurring events, recurrence delete, attendees, invitations, default-calendar guessing, date-only/time-zone inference, travel time, email/procedure alarms, custom monthly/yearly recurrence rules, unbounded recurrence, and bulk operations remain blocked.

# V1.139 Calendar Unbounded Recurrence Write Design

## Scope

Status: Apply-capable implementation.

This gate extends Calendar recurrence writes with explicit unbounded recurrence through public EventKit nil `EKRecurrenceEnd`.

Approved inputs:

- `recurrence_unbounded`: optional explicit boolean recurrence bound for create/update.
- `--recurrence-unbounded`: CLI flag.

Exactly one of `recurrence_count`, `recurrence_end_date`, or `recurrence_unbounded:true` is required when recurrence is requested. The adapter never infers unbounded recurrence from omitted count/end-date input. This applies to event create, add-to-non-recurring-event update, and the existing mid-series `recurrence_update_scope:future_events` replacement gate.

## Source Review

The local macOS SDK EventKit headers expose nullable recurrence ends: `EKRecurrenceRule` accepts `end:(nullable EKRecurrenceEnd *)end`, and its `recurrenceEnd` property is nullable. EventKit represents unbounded recurrence by a nil recurrence end. This gate uses only that public local SDK surface.

## Planning Contract

Plan stays non-mutating. It validates:

- `recurrence_unbounded` is a real boolean input.
- Mutually exclusive with `recurrence_count` and `recurrence_end_date`.
- Exactly one recurrence bound is supplied when recurrence is requested.
- All existing recurrence frequency, interval, weekday, month-day, monthly nth-weekday, yearly selector, and set-position constraints still apply.

Applies only to event create, add-to-non-recurring-event update, and mid-series recurrence replacement through the existing `recurrence_update_scope:future_events` gate.

Preview stores explicit unbounded recurrence as `preview.proposed.recurrence.unbounded:true` with `count:0`. Binds `unbounded:true` into the approval fingerprint and idempotency key.

## Apply Contract

Apply requires the existing matching approval token and `confirm_apply:true`. The Swift helper re-validates the exact recurrence shape, rejects count/end-date/unbounded conflicts, applies public EventKit by creating an `EKRecurrenceRule` with `end:nil`, and saves through EventKit.

Read-back must prove `unbounded:true` from nil `recurrenceEnd`. If read-back is missing or mismatched, apply returns `apply_unknown` with `recurrence_read_back_mismatch` and `mutation_applied:true`.

Runtime verifier proves direct create plan/apply read-back and MCP plan plus invalid-token apply proof through `calendar_unbounded_recurrence_apply_read_back_unbounded` and `mcp_calendar_unbounded_recurrence_plan_unbounded`. Unit tests also prove exact mid-series replacement with an explicit unbounded rule.

## Out Of Scope

- implicit unbounded recurrence
- changing an existing recurring event except approved first-visible/mid-series clear, selected/future-span/whole-series delete, and selected-occurrence update gates
- attendee/invitation mutation
- travel time
- procedure alarms

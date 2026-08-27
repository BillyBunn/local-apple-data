# V1.105 Calendar Monthly Nth-Weekday Recurrence Write Design

Status: Apply-capable implementation.

This gate adds explicit monthly nth-weekday recurrence selection to the existing bounded Calendar recurrence create and add-to-non-recurring-event update flow. It stays local-only, EventKit-only, exact-target gated, and finite-bound only.

Uses public EventKit `EKRecurrenceDayOfWeek` week numbers through `daysOfTheWeek`.

## Approved Shape

- `recurrence_month_weekdays`: adapter/MCP list of objects or comma-separated adapter value.
- `--recurrence-month-weekdays`: CLI comma-separated `weekday:week_number` values.
- Each value contains `weekday` plus `week_number`.
- `weekday` accepts weekday names/aliases or integers 1 through 7.
- `week_number` accepts only -5 through -1 or 1 through 5.
- Supported only with `recurrence_frequency:"monthly"`.
- Must not be mixed with `recurrence_month_days`.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound using either `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update.

## Planning Contract

Planning canonicalizes duplicate and unordered values by week number then weekday. Adds `month_weekdays:[...]` inside `preview.proposed.recurrence` only when explicit monthly nth-weekdays are requested. Binds month-weekdays into the approval fingerprint and idempotency key. Non-monthly input, invalid weekdays, zero or out-of-range week numbers, boolean week numbers, and mixes with `recurrence_month_days` return `invalid_recurrence` before any mutation.

## Apply Contract

Apply accepts only the approved plan shape and writes one bounded monthly `EKRecurrenceRule` with `EKRecurrenceDayOfWeek(weekDay, weekNumber:)` values through EventKit `daysOfTheWeek`. Create writes the recurrence on the new event. Update first proves the exact event is non-recurring and then adds the recurrence.

Read-back must prove the same bounded monthly nth-weekday set. A mismatch returns the existing recurrence read-back warning path instead of claiming clean success.

## Verification

Runtime verifier proves direct create/update plan/apply read-back and MCP create/update plan plus invalid-token apply proof. Direct runtime proof checks `calendar_month_weekday_recurrence_plan_month_weekdays`, `calendar_month_weekday_recurrence_apply_read_back_month_weekdays`, `calendar_month_weekday_update_recurrence_plan_month_weekdays`, and `calendar_month_weekday_update_recurrence_apply_read_back_month_weekdays`. MCP runtime proof checks `mcp_calendar_month_weekday_recurrence_plan_month_weekdays` and `mcp_calendar_month_weekday_update_recurrence_plan_month_weekdays`, and rejects mismatched apply with `invalid_approval_token`.

Source tests cover adapter planning, invalid-shape refusal, EventKit helper binding/read-back strings, CLI parsing/apply binding, MCP plan/apply binding, public-surface audit expectations, and write-design audit coverage.

## Still Out Of Scope

- Mid-series recurrence clearing/replacement.
- Existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete.
- Custom monthly recurrence components beyond monthly BYDAY/BYMONTHDAY/monthly nth-weekday.
- custom yearly recurrence rules beyond yearly BYMONTH/BYMONTH+nth-BYDAY/BYYEARDAY/BYWEEK.
- Unbounded recurrence.
- attendee/invitation mutation.
- Travel time.
- Email/procedure alarms.

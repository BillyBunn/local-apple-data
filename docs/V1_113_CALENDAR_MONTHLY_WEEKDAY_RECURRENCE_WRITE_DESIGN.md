# V1.113 Calendar Monthly Weekday Recurrence Write Design

Status: Apply-capable implementation.

This gate adds monthly weekday recurrence selection to the existing bounded Calendar recurrence create and add-to-non-recurring-event update flow. It stays local-only, EventKit-only, exact-target gated, and finite-bound only.

Uses public EventKit `EKRecurrenceDayOfWeek` values without week numbers through `daysOfTheWeek`.

## Approved Shape

- `recurrence_weekdays`: adapter/MCP list or comma-separated adapter value.
- `--recurrence-weekdays`: CLI comma-separated weekdays.
- `weekday` accepts weekday names/aliases or integers 1 through 7.
- Supported with `recurrence_frequency:"monthly"`.
- Must not be mixed with `recurrence_month_days` or `recurrence_month_weekdays`.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound using either `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update.

## Planning Contract

Planning canonicalizes duplicate and unordered weekdays. Adds `weekdays:[...]` inside `preview.proposed.recurrence` only when explicit monthly weekdays are requested. Binds monthly weekdays into the approval fingerprint and idempotency key. Non-monthly unsupported use, invalid weekdays, boolean values, and mixes with `recurrence_month_days` or `recurrence_month_weekdays` return `invalid_recurrence` before any mutation.

## Apply Contract

Apply accepts only the approved plan shape and writes one bounded monthly `EKRecurrenceRule` with `EKRecurrenceDayOfWeek(weekDay)` values through EventKit `daysOfTheWeek`. Create writes the recurrence on the new event. Update first proves the exact event is non-recurring and then adds the recurrence.

Read-back must prove the same bounded monthly weekday set. A mismatch returns the existing recurrence read-back warning path instead of claiming clean success.

## Verification

Fixture-backed runtime verifier proves direct create/update plan/apply read-back and MCP create/update plan plus invalid-token apply proof. Direct runtime proof checks `calendar_monthly_weekday_recurrence_plan_weekdays`, `calendar_monthly_weekday_recurrence_apply_read_back_weekdays`, `calendar_monthly_weekday_update_recurrence_plan_weekdays`, and `calendar_monthly_weekday_update_recurrence_apply_read_back_weekdays`. MCP runtime proof checks `mcp_calendar_monthly_weekday_recurrence_plan_weekdays` and `mcp_calendar_monthly_weekday_update_recurrence_plan_weekdays`, and rejects mismatched apply with `invalid_approval_token`.

Source tests cover adapter planning, invalid-shape refusal, EventKit helper binding/read-back strings, CLI parsing/apply binding, MCP plan/apply binding, public-surface audit expectations, and write-design audit coverage.

## Still Out Of Scope

- true month-week arrays remain blocked because public EventKit has no `weeksOfTheMonth` field.
- Mid-series recurrence clearing/replacement.
- Existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete.
- Custom monthly recurrence components beyond monthly BYDAY/BYMONTHDAY/monthly nth-weekday.
- Custom yearly recurrence rules beyond yearly BYMONTH/BYMONTH+BYMONTHDAY/BYMONTH+nth-BYDAY/BYYEARDAY/BYWEEK.
- Unbounded recurrence.
- attendee/invitation mutation.
- Travel time.
- Non-allow-listed URLs.
- Procedure alarms.

# V1.112 Calendar Yearly Month Day Recurrence Write Design

Status: Apply-capable implementation.

This gate adds yearly month day-of-month recurrence selection to the existing bounded Calendar recurrence create and add-to-non-recurring-event update flow. It stays local-only, EventKit-only, exact-target gated, and finite-bound only.

Uses public EventKit `monthsOfTheYear` plus `daysOfTheMonth`.

## Approved Shape

- `recurrence_year_months`: adapter/MCP list of integers or comma-separated adapter value.
- `recurrence_year_month_days`: adapter/MCP list or comma-separated adapter value.
- `--recurrence-year-months`: CLI comma-separated integers 1 through 12.
- `--recurrence-year-month-days`: CLI comma-separated integers from -31 through -1 or 1 through 31.
- Requires `recurrence_year_months`.
- Supported only with `recurrence_frequency:"yearly"`.
- Must not be mixed with `recurrence_year_month_weekdays`, `recurrence_year_days`, or `recurrence_year_weeks`.
- Values are canonicalized to sorted unique months and sorted unique day-of-month selectors.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound using either `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update.

## Planning Contract

Planning canonicalizes duplicate and unordered values. Adds `year_months:[...]` and `year_month_days:[...]` inside `preview.proposed.recurrence` only when explicit yearly month day-of-month selection is requested. Adds `year_month_days:[...]` inside `preview.proposed.recurrence` only with exact `year_months`. Binds year-months and year-month-days into the approval fingerprint and idempotency key. Non-yearly input, missing year-months, zero or out-of-range month days, boolean values, string-list values, mixes with `recurrence_year_month_weekdays`, and mixes with `recurrence_year_days` or `recurrence_year_weeks` return `invalid_recurrence` before any mutation.

## Apply Contract

Apply accepts only the approved plan shape and writes one bounded yearly `EKRecurrenceRule` with `monthsOfTheYear` plus `daysOfTheMonth`. Create writes the recurrence on the new event. Update first proves the exact event is non-recurring and then adds the recurrence.

Read-back must prove the same bounded yearly month and day-of-month set. A mismatch returns the existing recurrence read-back warning path instead of claiming clean success. EventKit skips months without a requested day-of-month occurrence. That is EventKit recurrence behavior, not plugin-side failure.

## Verification

Fixture-backed runtime verifier proves direct create/update plan/apply read-back and MCP create/update plan plus invalid-token apply proof. Direct runtime proof checks `calendar_year_month_day_recurrence_plan_year_months`, `calendar_year_month_day_recurrence_plan_year_month_days`, `calendar_year_month_day_recurrence_apply_read_back_year_months`, `calendar_year_month_day_recurrence_apply_read_back_year_month_days`, `calendar_year_month_day_update_recurrence_plan_year_months`, `calendar_year_month_day_update_recurrence_plan_year_month_days`, `calendar_year_month_day_update_recurrence_apply_read_back_year_months`, and `calendar_year_month_day_update_recurrence_apply_read_back_year_month_days`. MCP runtime proof checks `mcp_calendar_year_month_day_recurrence_plan_year_months`, `mcp_calendar_year_month_day_recurrence_plan_year_month_days`, `mcp_calendar_year_month_day_update_recurrence_plan_year_months`, and `mcp_calendar_year_month_day_update_recurrence_plan_year_month_days`, and rejects mismatched apply with `invalid_approval_token`.

Source tests cover adapter planning, invalid-shape refusal, EventKit helper binding/read-back strings, CLI parsing/apply binding, MCP plan/apply binding, public-surface audit expectations, and write-design audit coverage.

## Still Out Of Scope

- Combining with yearly month nth-weekday, day-of-year, or week-of-year selectors.
- Set-position recurrence beyond the explicit month plus day-of-month shape.
- Mid-series recurrence clearing/replacement.
- Existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete.
- Unbounded recurrence.
- attendee/invitation mutation.
- Travel time.
- Non-allow-listed URLs.
- Procedure alarms.

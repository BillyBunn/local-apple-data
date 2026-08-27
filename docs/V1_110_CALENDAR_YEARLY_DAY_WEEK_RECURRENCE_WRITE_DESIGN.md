# V1.110 Calendar Yearly Day/Week Recurrence Write Design

Status: Apply-capable implementation.

This gate adds explicit yearly day-of-year and week-of-year recurrence selection to the existing bounded Calendar recurrence create and add-to-non-recurring-event update flow. It stays local-only, EventKit-only, exact-target gated, and finite bounded.

Uses public EventKit `daysOfTheYear` and `weeksOfTheYear`.

## Approved Shape

- `recurrence_year_days`: adapter/MCP list of integers or comma-separated adapter value.
- `recurrence_year_weeks`: adapter/MCP list of integers or comma-separated adapter value. Requires `recurrence_weekdays` so the selected week numbers are bound to exact weekdays.
- `--recurrence-year-days`: CLI comma-separated integers from -366 through -1 or 1 through 366.
- `--recurrence-year-weeks`: CLI comma-separated integers from -53 through -1 or 1 through 53. Requires `--recurrence-weekdays`.
- Supported only with `recurrence_frequency:"yearly"`.
- Values are canonicalized to sorted unique integers.
- Exactly one yearly selector is allowed: `recurrence_year_months`, `recurrence_year_days`, or `recurrence_year_weeks`.
- Keeps existing `recurrence_interval` range 1 through 4 and exactly one finite end bound: `recurrence_count` from 2 through 52 or timezone `recurrence_end_date` within 3650 days of `start_date`.
- Applies only to event create and add-to-non-recurring-event update.

## Planning Contract

Planning canonicalizes duplicate and unordered values. Adds `year_days:[...]` or `year_weeks:[...]` inside `preview.proposed.recurrence` only when explicit yearly day/week selection is requested; week-of-year plans also include `weekdays:[...]`. Binds the selected yearly values and week-of-year weekday values into the approval fingerprint and idempotency key. Non-yearly input, week-of-year input without weekdays, zero, out-of-range values, booleans, string-list values, and mixed yearly selectors return `invalid_recurrence` before any mutation.

## Apply Contract

Apply accepts only the approved plan shape and writes one bounded yearly `EKRecurrenceRule` with `daysOfTheYear`, or with `weeksOfTheYear` plus exact `daysOfTheWeek`. Create writes the recurrence on the new event. Update first proves the exact event is non-recurring and then adds the recurrence.

Read-back must prove the same bounded yearly day/week set and the same weekdays for week-of-year plans. A mismatch returns the existing recurrence read-back warning path instead of claiming clean success. The deterministic verifier proof is fixture-backed; live EventKit proof from the current Codex process remains host/TCC dependent.

## Verification

Fixture-backed runtime verifier proves direct create/apply read-back for yearly day-of-year recurrence, direct update/apply read-back for yearly week-of-year recurrence with exact weekdays, and MCP plan plus invalid-token apply proof for both selectors. Direct runtime proof checks `calendar_year_day_recurrence_plan_year_days`, `calendar_year_day_recurrence_apply_read_back_year_days`, `calendar_year_week_update_recurrence_plan_year_weeks`, `calendar_year_week_update_recurrence_plan_weekdays`, `calendar_year_week_update_recurrence_apply_read_back_year_weeks`, and `calendar_year_week_update_recurrence_apply_read_back_weekdays`. MCP runtime proof checks `mcp_calendar_year_day_recurrence_plan_year_days`, `mcp_calendar_year_week_update_recurrence_plan_year_weeks`, and `mcp_calendar_year_week_update_recurrence_plan_weekdays`, and rejects mismatched apply with `invalid_approval_token`.

Source tests cover adapter planning, invalid-shape refusal, EventKit helper binding/read-back strings, Swift CFBoolean-before-integer parsing guards, CLI parsing/apply binding, MCP plan/apply binding, public-surface audit expectations, and write-design audit coverage.

## Still Out Of Scope

- Combining yearly selectors.
- Yearly nth-weekday/set-position recurrence.
- Mid-series recurrence clearing/replacement.
- Existing-recurring-event update beyond first-visible clear and selected/future-span/whole-series occurrence delete.
- Custom yearly recurrence rules beyond yearly BYMONTH, BYYEARDAY, or BYWEEK.
- Unbounded recurrence.
- Attendee/invitation mutation.
- Travel time.
- Procedure alarms.

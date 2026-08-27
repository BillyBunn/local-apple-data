# v1.90 Calendar Recurrence And Date-Only Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar create/update/delete gate in two narrow ways:

- Create-only simple count-bound recurrence may use `daily`, `weekly`, `monthly`, or `yearly`.
- Date-only `YYYY-MM-DD` start/end values may be used for all-day create, update expected-state, update proposed-state, and delete expected-state. Date-only input infers `all_day:true` or `expected_all_day:true`.

Later v1.93 support is governed by `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`. This document does not approve recurrence delete, existing-recurring-event update/delete, custom weekday/month rules, unbounded recurrence, attendees, invitations, default-calendar guessing, timed-event time-zone inference, travel time, email/procedure alarms, availability changes, URL/attachment mutation, calendar creation/deletion, account management, or bulk operations.

## Source Review

Local macOS SDK headers show `EKRecurrenceFrequency` includes daily, weekly, monthly, and yearly values. `EKRecurrenceRule` has a simple `initRecurrenceWithFrequency:interval:end:` initializer, and `EKRecurrenceEnd` supports occurrence-count bounds. The implementation still uses only that simple initializer plus `EKRecurrenceEnd(occurrenceCount:)`; it does not set weekday, month, week, set-position, or unbounded recurrence components.

Local EventKit headers say floating events such as all-day events are returned in the default time zone. For date-only inputs, the Swift helper therefore parses `YYYY-MM-DD` through `Calendar.current` date components instead of converting the date to UTC midnight. The plan and apply payload keep date-only strings as date-only strings so approval tokens bind the user-requested day, not a shifted instant. EventKit read-back serializes all all-day event start/end values as `YYYY-MM-DD` through `Calendar.current` so date-only all-day proof cannot be masked by UTC timestamp echoes.

The same source review confirms `EKCalendarItem.attendees`, `EKEvent.organizer`, and `EKParticipant` properties are readonly, so attendee/invitation mutation remains blocked. The installed public EventKit headers do not expose a writable `travelTime` event property, so travel time remains blocked.

## Safety Contract

Plan stays non-mutating. It validates recurrence and date shapes before returning an approval fingerprint.

Recurrence create requires:

- `recurrence_frequency` of `daily`, `weekly`, `monthly`, or `yearly`.
- `recurrence_interval` from 1 through 4.
- `recurrence_count` from 2 through 52.
- Create operation only.

Date-only input requires:

- Start and end fields are both `YYYY-MM-DD`, or both timezone-bearing timestamps.
- Mixed date-only and timestamp pairs return `mixed_date_only_datetime`.
- Date-only pairs infer all-day state and reject `time_zone` / `expected_time_zone`.
- The approval fingerprint binds the exact normalized date-only strings and inferred all-day flag.

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends only normalized fields to the Swift EventKit helper after token verification. The helper parses date-only values using `Calendar.current`, applies exactly one EventKit event change, and reads back metadata or delete absence proof.

Existing recurring events remain unsupported for update/delete through the bounded-mutation state check. The helper does not use `.futureEvents` or detached occurrence semantics.

## Synthetic Tests Required

- Plan success for monthly recurrence and yearly recurrence.
- Apply success for yearly recurrence with read-back recurrence metadata.
- CLI recurrence plan/apply routing accepts monthly/yearly.
- MCP recurrence plan/apply token binding accepts monthly/yearly.
- Runtime verifier proves direct monthly/yearly recurrence and MCP monthly/yearly recurrence behavior.
- Plan success for date-only create infers all-day and binds date-only strings.
- Mixed date-only/timestamp pairs are refused without crashing.
- Date-only plus timed-event `time_zone` is refused.
- Apply create/update/delete binds date-only strings and inferred all-day expected state.
- Swift EventKit read-back returns all-day event dates as `YYYY-MM-DD`, not ISO timestamps.
- Static audit ties approved recurrence frequencies to adapter constants, Swift mappings, and CLI choices.

## Historical Release Gate

This v1.90 release approved only date-only all-day inference and simple count-bound daily/weekly/monthly/yearly recurrence on Calendar create. Later v1.93 support is governed by `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`. Calendar update/delete of existing recurring events, recurrence delete, attendees, invitations, default-calendar guessing, timed-event time-zone inference, travel time, email/procedure alarms, custom monthly/yearly recurrence rules, unbounded recurrence, availability changes, URL/attachment mutation, calendar creation/deletion, account management, and bulk operations remain blocked.

# v1.88 Calendar Absolute Alarm Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar create/update/delete gate with exact absolute display-alarm timestamps. It does not approve recurrence, attendees, invitations, URLs, attachments, availability changes, travel time, default-calendar guessing, date-only parsing, time-zone guessing, structured/email alarms, email alarms, procedure alarms, audio alarms, calendar moves beyond the existing target-calendar handle gate, or bulk operations.

## Scope

Approved operation expansion:

- `create`: create one timed or explicit all-day event with zero or more absolute display alarms.
- `update`: replace one exact event's title, start/end, all-day flag, location, notes, target calendar where already approved, and alarm state.
- `delete`: delete one exact event only when expected current alarm state matches.

Alarm fields:

- `alarm_absolute_dates`: JSON array of ISO 8601 timestamps with time zones for create/update.
- `expected_alarm_absolute_dates`: JSON array of expected current ISO 8601 timestamps with time zones for update/delete drift checks.
- Absolute alarm timestamps are bounded to at most 8 values, deduplicated, sorted, and normalized to UTC ISO 8601 seconds.
- Relative offsets and absolute dates are mutually exclusive in one plan. Use either `alarm_offsets_minutes` or `alarm_absolute_dates`, not both. The same rule applies to expected alarm fields.

## Source Review

The local macOS SDK EventKit headers expose `EKAlarm` as representing relative or absolute alarms, with `alarmWithAbsoluteDate:` for absolute trigger times and `alarmWithRelativeOffset:` for relative trigger times.

The same headers expose structured-location/proximity alarms, email alarms, audio alarms, and procedure alarms. Audio alarms are governed separately by `docs/V1_103_CALENDAR_AUDIO_ALARM_WRITE_DESIGN.md`; structured geofence alarms are governed separately by `docs/V1_104_CALENDAR_GEOFENCE_ALARM_WRITE_DESIGN.md`; email and procedure alarms remain blocked because they add recipient or URL behavior outside the exact alarm gate.

`EKCalendarItem.attendees` and `EKEvent.organizer` are readonly in the local SDK headers, so attendee/invitation mutation remains blocked rather than guessed.

## Safety Contract

Plan stays non-mutating. It validates and binds `alarm_absolute_dates` or `expected_alarm_absolute_dates` into the preview, idempotency key, and approval fingerprint.

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends absolute alarm timestamps to the Swift EventKit helper only after token verification.

For update/delete, the Swift helper rechecks title, calendar title, start date, end date, all-day flag, time zone when bound, alarm state, location, notes, recurrence, and attendees before mutation. Recurring or attendee-bearing events remain unsupported. Alarm-bearing events are supported only when their exact expected alarm state is supplied and matches.

The helper accepts only one alarm mode per event: all relative offsets, all absolute dates, or no alarms. Mixed alarm modes, structured-location/proximity alarms, or unsupported alarm action forms are treated as unsupported state for bounded mutation.

Read-back returns bounded event metadata with `alarm_absolute_dates` and `alarms_count` when absolute alarms are present. Apply output must not return raw EventKit identifiers, account identifiers, framework exception text, attendee identifiers, or unrelated event content.

## Synthetic Tests Required

- Plan success for create with absolute alarm timestamps and canonical sorted/unique UTC timestamps.
- Mixed relative and absolute alarm input refusal before approval fingerprinting.
- Apply success for absolute-alarm create with read-back timestamps.
- Delete apply payload binds `expected_alarm_absolute_dates`.
- CLI absolute-alarm plan/apply routing.
- MCP absolute-alarm plan/apply preview token binding without live EventKit.
- Runtime synthetic smoke proving absolute-alarm create plan/apply through the verifier.
- Static Swift regression proving expected absolute alarm dates are compared before update/delete apply, unsupported alarm modes stay blocked, and proposed absolute alarms are applied only after approval.

## Current Release Gate

This release approves only exact absolute display-alarm support inside the existing exact Calendar create/update/delete gates. Audio alarms are governed by v1.103. Calendar recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, calendar/account management, default-calendar guessing, date-only/time-zone inference, structured/email alarms, email/procedure alarms, and bulk operations remain blocked.

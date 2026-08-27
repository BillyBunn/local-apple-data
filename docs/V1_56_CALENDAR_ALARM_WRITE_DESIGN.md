# v1.56 Calendar Alarm Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar create/update/delete gate with exact relative alarm-offset support. Absolute display alarms are governed by `docs/V1_88_CALENDAR_ABSOLUTE_ALARM_WRITE_DESIGN.md`. It does not approve recurrence, attendees, invitations, URLs, attachments, availability, travel time, calendar moves, default-calendar guessing, date-only parsing, time-zone guessing, email/procedure alarms, or bulk operations.

## Scope

Approved operation expansion:

- `create`: create one timed or all-day event with zero or more explicit relative alarm offsets.
- `update`: replace one exact event's title, start/end, all-day flag, location, notes, and alarm offsets.
- `delete`: delete one exact event only when expected current alarm offsets match.

Alarm fields:

- `alarm_offsets_minutes`: JSON array of integer minute offsets for create/update. Negative values mean before event start; `0` means at event start.
- `expected_alarm_offsets_minutes`: JSON array of expected current integer minute offsets for update/delete drift checks.
- Offsets are bounded to at most 8 values, deduplicated, sorted, and limited to -40320 through 40320 minutes.

## Safety Contract

Plan stays non-mutating. It binds `alarm_offsets_minutes` or `expected_alarm_offsets_minutes` into the preview, idempotency key, and approval fingerprint.

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends alarm offsets to the Swift EventKit helper only after token verification.

For update/delete, the Swift helper rechecks title, calendar title, start date, end date, all-day flag, alarm offsets, location, notes, recurrence, and attendees before mutation. Recurring or attendee-bearing events remain unsupported. Alarm-bearing events are supported only when their exact expected offsets are supplied and match.

Read-back returns bounded event metadata with `alarm_offsets_minutes` and `alarms_count`. Apply output must not return raw EventKit identifiers, account identifiers, framework exception text, or unrelated event content.

## Synthetic Tests Required

- Plan success for create with alarm offsets and canonical sorted/unique offsets.
- Invalid alarm-offset input refusal before approval fingerprinting.
- Apply success for alarmed create with read-back offsets.
- Apply success for update with expected current offsets and proposed offsets bound.
- Delete apply payload binds `expected_alarm_offsets_minutes`.
- CLI alarm-offset plan/apply routing.
- MCP alarm-offset plan/apply preview token binding without live EventKit.
- Runtime synthetic smoke proving alarmed create plan/apply through the verifier.
- Static Swift regression proving expected alarm offsets are compared before update/delete apply and proposed alarm offsets are applied to create/update.

## Current Release Gate

This release approves only exact relative alarm-offset support inside the existing exact Calendar create/update/delete gates. Exact absolute display alarms are governed by `docs/V1_88_CALENDAR_ABSOLUTE_ALARM_WRITE_DESIGN.md`. Calendar recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, calendar/account management, default-calendar guessing, date-only/time-zone inference, email/procedure alarms, move, and bulk operations remain blocked.

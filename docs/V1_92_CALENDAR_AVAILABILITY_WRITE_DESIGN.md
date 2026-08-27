# V1.92 Calendar Availability Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar create/update/delete gate with exact busy/free/tentative/unavailable availability create/update. Recurrence update is governed by `docs/V1_93_CALENDAR_RECURRENCE_UPDATE_WRITE_DESIGN.md`. It does not approve attendees, invitations, travel time, calendar creation/deletion, account management, recurrence delete, existing-recurring-event update/delete, custom monthly/yearly recurrence rules, unbounded recurrence, silent default-calendar guessing or mutation, apply-time default-calendar re-resolution, timed-event time-zone inference, email/procedure alarms, URL/attachment mutation, unsupported availability values, or bulk operations.

## EventKit Source Review

EventKit source review is limited to public SDK headers shipped on this Mac plus official Apple EventKit documentation.

- `EKEvent.availability` is a mutable event property.
- `EKEventAvailability` exposes `notSupported`, `busy`, `free`, `tentative`, and `unavailable` raw values.
- `EKCalendar.supportedEventAvailabilities` exposes a support mask for the target calendar.
- `EKCalendarItem.attendees` and `EKEvent.organizer` remain read-only, so attendee/invitation mutation remains blocked.

## Plan Contract

`calendar_plan_change` and `local-apple-data calendar plan` accept `availability` for `operation=create` or `operation=update`.

Allowed `availability` values are:

- `busy`
- `free`
- `tentative`
- `unavailable`

Create planning:

- Stays non-mutating.
- Normalizes the requested availability to EventKit raw value plus safe name.
- Adds `availability`, `availability_name`, and `availability_requested:true` to `preview.proposed`.
- Binds the normalized value into the approval fingerprint and idempotency key.
- Does not call EventKit.

Update planning:

- Requires one exact `calendar:event:v1:` handle.
- Requires `expected_availability` when `availability` is supplied.
- Allows `expected_availability` values of `busy`, `free`, `tentative`, `unavailable`, or `not_supported`.
- Adds normalized expected and proposed availability state to the preview.
- Binds both values into the approval fingerprint and idempotency key.
- Stays non-mutating.

Delete planning accepts optional `expected_availability` for drift binding. It does not change availability and still removes only the selected exact event after approval.

## Apply Contract

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends availability fields to the Swift EventKit helper only after token verification.

Create apply:

- Resolves the approved explicit calendar title, exact `calendar:calendar:v1:` handle, or exact handle produced by a plan-only default-calendar resolver.
- Validates that the target calendar support mask contains the requested availability.
- Sets `event.availability` only when `availability_requested:true`.
- Saves one event and returns bounded read-back metadata.
- Verifies read-back availability when availability was requested.

Update apply:

- Resolves exactly one current event by opaque event handle.
- Rechecks expected current-state fields before mutation, including `expected_availability` when supplied.
- If the update moves the event to a target calendar, validates the requested availability against the destination calendar support mask.
- Sets `event.calendar` before `event.availability` when both a calendar move and availability change are approved.
- Saves one event and returns bounded read-back metadata.
- Verifies read-back availability when availability was requested.

Delete apply:

- Rechecks expected current-state fields before mutation, including optional `expected_availability`.
- Deletes only the selected exact event.
- Requires read-back absence proof.

If EventKit saves the mutation but read-back availability does not match the approved value, the adapter returns `status:"apply_unknown"`, `mutation_applied:true`, and warning code `availability_read_back_mismatch`.

## Synthetic Tests Required

- Adapter plan tests for create availability binding and invalid availability rejection.
- Adapter plan tests requiring `expected_availability` for availability update.
- Adapter apply tests for create availability read-back.
- Adapter apply tests for update availability with expected-state binding.
- Adapter apply tests for availability read-back mismatch `apply_unknown` reporting.
- CLI tests proving `--availability` and `--expected-availability` are forwarded.
- MCP tests proving plan/apply availability parameter binding without live EventKit mutation.
- Swift source assertions for `event.availability = proposedAvailability`, support-mask validation, expected availability parsing, and expected-state comparison.
- Runtime verifier keys for direct plan/apply availability read-back and MCP availability plan plus invalid-token refusal.

## Still Blocked

Availability outside explicit busy/free/tentative/unavailable create/update with target-calendar support-mask validation remains blocked.

Recurrence delete, existing-recurring-event update/delete, custom monthly/yearly recurrence rules, unbounded recurrence, existing recurring-event mutation, attendees, invitations, silent default-calendar guessing or mutation, apply-time default-calendar re-resolution, timed-event time-zone inference, travel time, email/procedure alarms, calendar creation/deletion, account management, URL/attachment mutation, and bulk Calendar mutation remain blocked.

# V1.86 Calendar Target Calendar Move Write Design

Status: Apply-capable implementation.

This document covers exact Calendar target-calendar selection and move support for the existing Calendar plan/apply gate. It adds read-only calendar target metadata selection and allows create/update to bind an exact target calendar handle. It does not add attendee, invitation, recurrence, travel-time, default-calendar guessing, or calendar/account administration.

Approved write tools remain `local-apple-data calendar apply` and `calendar_apply_change`. New read-only tools are `calendar_search_calendars`, `calendar_get_calendar`, `local-apple-data calendar calendars`, and `local-apple-data calendar calendar`.

## EventKit Source Review

EventKit source review is intentionally limited to public SDK symbols shipped on this Mac.

- `EKCalendarItem.calendar` is writable, so an existing event can be moved by assigning another EventKit calendar before save.
- `EKEvent.eventIdentifier` may change when the event changes calendars, so apply must return a fresh opaque event handle from read-back instead of promising handle stability.
- `EKEventStore.defaultCalendarForNewEvents` exposes the user's current default event calendar. The plugin may return that metadata when `include_default=true`, but apply must not guess it.
- `EKCalendar.allowsContentModifications` must be checked before create or move.
- `EKCalendarItem.attendees` and `EKEvent.organizer` are read-only. Attendee and organizer mutation remains blocked to avoid invitation surprises.

## Read-Only Target Selection

`calendar_search_calendars` and `local-apple-data calendar calendars` return bounded metadata only:

- opaque `calendar:calendar:v1:` handle
- title
- default-calendar flag
- modification capability flag
- subscribed/immutable flags
- redacted calendar/source type names
- supported event availability names

The search requires a meaningful title query or `include_default=true`. It returns no raw calendar identifiers, account identifiers, local paths, event bodies, event notes, attendee identifiers, or credentials.

`calendar_get_calendar` and `local-apple-data calendar calendar` accept only an exact `calendar:calendar:v1:` handle returned by selection output. Raw EventKit identifiers and fabricated handles are rejected.

## Plan Contract

Create accepts either:

- exact `calendar_title`
- `calendar_handle`: exact `calendar:calendar:v1:` handle for create.

Supplying both target forms is rejected. The plan is non-mutating and does not resolve the handle through EventKit. It binds the selected target handle into the preview, idempotency key, and approval fingerprint.

Update accepts:

- exact `calendar:event:v1:` event handle
- expected current event title, calendar title, start/end, all-day flag, alarm offsets, location, and notes
- `target_calendar_handle`: exact `calendar:calendar:v1:` handle for update/move.

The update plan remains non-mutating. A move request is explicit through `calendar_move_requested:true`.

## Apply Contract

Apply recomputes the same plan and requires the matching `calendar-apply:v1:<approval_fingerprint>` token plus explicit confirmation.

Apply resolves the target calendar handle only after the approval token and explicit confirmation pass. The resolved raw EventKit calendar identifier is used only inside the EventKit helper payload and is not returned to the caller.

For create with `calendar_handle`, the Swift helper resolves the target calendar, verifies `allowsContentModifications`, creates one event, saves through EventKit, and returns metadata-only read-back.

For update with `target_calendar_handle`, the Swift helper resolves the existing event from the exact event handle, rejects ambiguous duplicate source calendar titles before accepting the expected source-calendar state, resolves the target calendar, verifies `allowsContentModifications`, assigns `event.calendar`, saves through EventKit, and reads the event back. The read-back returns a fresh opaque event handle because EventKit may change identifiers during a calendar move.

For exact target-calendar create or move, the helper may return the raw EventKit calendar identifier only to the Python adapter as internal process-local proof. The adapter compares that internal identifier with the post-apply event read-back before returning success. Caller output returns only opaque handles and `target_calendar_verified:true`; it never returns raw calendar identifiers.

## Synthetic Tests Required

- Adapter tests for `calendar_search_calendars`, `calendar_get_calendar`, invalid calendar handles, create with `calendar_handle`, update with `target_calendar_handle`, and raw identifier redaction.
- CLI tests for `local-apple-data calendar calendars`, `local-apple-data calendar calendar`, and plan/apply propagation of exact calendar handles.
- MCP tests for `calendar_search_calendars`, `calendar_get_calendar`, and handle binding without EventKit mutation.
- Swift source tests proving `store.defaultCalendarForNewEvents`, `calendar.allowsContentModifications`, duplicate source-calendar title refusal, internal calendar-id read-back, and `event.calendar = targetCalendar` are present.
- Runtime verifier keys for target search, target-handle create, target-calendar move, target read-back verification, and MCP target-handle plan/apply parameter binding.

## Still Blocked

recurrence, attendees, invitations, date-only inference, travel time, email/procedure alarms, calendar creation/deletion, account management, and default-calendar guessing remain blocked. Exact absolute display alarms are governed by `docs/V1_88_CALENDAR_ABSOLUTE_ALARM_WRITE_DESIGN.md`. Any attendee mutation needs separate source review and explicit approval because public EventKit exposes attendees and organizer as read-only for this use case.

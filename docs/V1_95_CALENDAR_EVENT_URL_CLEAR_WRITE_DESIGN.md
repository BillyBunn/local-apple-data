# V1.95 Calendar Event URL Clear Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the Calendar update gate to clear one existing Calendar event URL from one exact event. It does not approve setting non-allow-listed URL schemes, attendee or invitation mutation, organizer mutation, travel time, recurrence delete, existing-recurring-event update/delete, custom/unbounded recurrence, email/procedure alarms, calendar creation/deletion, account management, or bulk operations.

## EventKit Source Review

- `EKCalendarItem.URL` is a mutable nullable `NSURL`.
- Clearing uses the same public EventKit property as v1.94 and sets `event.url = nil`.
- `EKCalendarItem.attendees` and `EKEvent.organizer` remain readonly, so attendee/invitation/organizer mutation remains blocked.
- This Mac's public EventKit SDK headers still do not expose a writable travel-time property. `scripts/audit_calendar_public_surface.py --json` remains the deterministic local proof for that blocker.

## Plan Contract

`calendar_plan_change` and `local-apple-data calendar plan` accept:

- `clear_event_url` / `--clear-event-url`: update-only request to clear the event URL.
- `expected_event_url_present` / `--expected-event-url-present`: must be `true`.
- `expected_event_url_sha256` / `--expected-event-url-sha256`: exact lowercase SHA-256 of the current URL from exact event detail.

Planning:

- Rejects simultaneous `event_url` and `clear_event_url`.
- Rejects `clear_event_url` for create and delete; it is update-only.
- Requires `expected_event_url_present:true`.
- Requires exact `expected_event_url_sha256`.
- Adds `event_url_clear_requested:true` to `preview.proposed`.
- Keeps raw current and proposed URLs out of public preview output.
- Binds expected URL presence and SHA-256 into the approval fingerprint.
- Stays non-mutating.

## Apply Contract

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, resolves exactly one target event by opaque handle, and only then calls the Swift EventKit helper.

Apply:

- Rechecks exact expected current state before mutation, including `expected_event_url_present:true` and exact `expected_event_url_sha256`.
- Refuses existing unsupported attendee, alarm, or recurrence states using the existing bounded Calendar mutation guards.
- Sets `event.url = nil` only when `event_url_clear_requested=true`.
- Saves one event with `.thisEvent`.
- Returns bounded metadata read-back only.
- returns `url_present:false` and `event_url_cleared_verified:true` only after read-back proves absence.

If EventKit saves the mutation but read-back still reports a URL, the adapter returns `status:"apply_unknown"`, `mutation_applied:true`, and warning code `event_url_clear_read_back_mismatch`.

## Synthetic Tests Required

- Adapter plan tests proving clear preview and approval fingerprint binding.
- Adapter plan tests rejecting missing expected URL state, set+clear conflicts, create-time clear, and delete-time clear.
- Adapter apply tests proving helper payload forwarding with `event_url_clear_requested:true` and read-back absence verification.
- Adapter apply tests proving URL-clear read-back mismatch returns `apply_unknown` with `mutation_applied:true`.
- CLI tests proving `--clear-event-url` forwards for plan/apply.
- MCP tests proving clear plan plus invalid-token apply preview binding without live EventKit mutation.
- Swift source assertions for `event.url = nil`, `event_url_clear_requested`, expected URL SHA-256 binding, and `event_url_clear_read_back_mismatch`.
- Runtime synthetic smoke proving direct event URL clear plan/apply absence proof and MCP clear plan plus invalid-token apply.

## Still Blocked

Attendees, invitations, organizer mutation, travel time, recurrence delete, existing-recurring-event update/delete, custom/unbounded recurrence rules, recurrence exception editing, email/procedure alarms, non-allow-listed URL schemes, calendar creation/deletion, account management, and bulk Calendar mutation remain blocked.

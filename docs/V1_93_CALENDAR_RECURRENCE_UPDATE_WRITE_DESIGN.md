# V1.93 Calendar Recurrence Update Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar update gate to add simple count-bound recurrence to a currently non-recurring exact Calendar event. It does not approve recurrence delete, existing-recurring-event update/delete, custom weekday/month rules, unbounded recurrence, attendees, invitations, silent default-calendar guessing or mutation, timed-event time-zone inference, travel time, email/procedure alarms, URL/attachment mutation, calendar creation/deletion, account management, or bulk operations.

## EventKit Source Review

EventKit source review is limited to public SDK headers shipped on this Mac plus official Apple EventKit documentation.

- `EKCalendarItem.recurrenceRules` is a mutable array of recurrence rules.
- `EKRecurrenceRule(recurrenceWith:interval:end:)` supports the simple frequency/interval/count shape already used for recurrence create.
- `EKRecurrenceEnd(occurrenceCount:)` supports bounded occurrence counts.
- Updating an existing recurring event safely requires series/occurrence semantics that are outside this gate, so existing recurring events remain unsupported for update/delete.
- The helper does not use `.futureEvents`.
- `EKCalendarItem.attendees` and `EKEvent.organizer` remain readonly, so attendee/invitation mutation remains blocked.

## Plan Contract

`calendar_plan_change` and `local-apple-data calendar plan` accept recurrence fields for `operation=update`:

- `recurrence_frequency` of `daily`, `weekly`, `monthly`, or `yearly`.
- `recurrence_interval` from 1 through 4.
- `recurrence_count` from 2 through 52.

Update planning:

- Requires one exact `calendar:event:v1:` handle.
- Requires expected current state: title, calendar title, start date, and end date, with optional expected all-day, time-zone, alarm, availability, location, and notes bindings following the existing update gate.
- Adds an expected no-recurrence binding when recurrence update fields are present.
- Normalizes recurrence to one simple bounded recurrence payload.
- Adds `recurrence` and `recurrence_present:true` to `preview.proposed`.
- Binds recurrence fields into the idempotency key and approval fingerprint.
- Stays non-mutating.

Delete planning still rejects recurrence fields with `unsupported_recurrence_for_operation`.

## Apply Contract

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, and sends recurrence fields to the Swift EventKit helper only after token verification.

Update apply:

- Resolves exactly one current event by opaque event handle.
- Rechecks expected current-state fields before mutation.
- Rejects attendees, unsupported alarm states, and existing recurrence before any already-applied shortcut.
- Rejects existing recurring events through the expected no-recurrence binding and bounded-mutation guard before applying recurrence or returning already-applied.
- Sets exactly one `EKRecurrenceRule` with an `EKRecurrenceEnd(occurrenceCount:)`.
- Saves one event with `.thisEvent`.
- Returns bounded read-back metadata.
- Verifies that read-back recurrence metadata must match the approved recurrence.

If EventKit saves the mutation but read-back recurrence does not match the approved value, the adapter returns `status:"apply_unknown"`, `mutation_applied:true`, and warning code `recurrence_read_back_mismatch`.

The Swift helper's already-applied shortcut includes `recurrenceMatches(event, proposedRecurrence)` when recurrence update is requested, so recurrence-only updates cannot be incorrectly reported as already applied. The shortcut runs only after scalar expected-state, attendee, alarm, target-calendar, availability, expected no-recurrence, and bounded-mutation checks. A pre-existing recurring event is refused instead of treated as an idempotent retry because this gate has no durable proof that a prior approved local apply created that recurrence.

## Synthetic Tests Required

- Adapter plan tests proving update recurrence preview and approval fingerprint binding.
- Adapter plan tests proving delete recurrence remains blocked.
- Adapter apply tests proving update recurrence helper payload forwarding and read-back verification.
- Adapter apply tests proving recurrence read-back mismatch returns `apply_unknown` with `mutation_applied:true`.
- CLI tests proving recurrence update arguments are forwarded for plan/apply.
- MCP tests proving recurrence update plan plus invalid-token apply preview binding without live EventKit mutation.
- Swift source assertions for recurrence update request detection, attendee/alarm guard ordering, expected no-recurrence binding, bounded-mutation ordering, `applyRecurrence(event, recurrence: proposedRecurrence)`, and already-applied recurrence matching.
- Runtime synthetic smoke proving direct recurrence update plan/apply, existing-recurring-event update refusal with `mutation_applied:false`, and MCP recurrence update plan plus invalid-token apply.

## Still Blocked

Recurrence delete, existing-recurring-event update/delete, custom monthly/yearly recurrence rules, unbounded recurrence, recurrence exception editing, attendee/invitation mutation, silent default-calendar guessing or mutation, timed-event time-zone inference, travel time, email/procedure alarms, calendar creation/deletion, account management, URL/attachment mutation, and bulk Calendar mutation remain blocked.

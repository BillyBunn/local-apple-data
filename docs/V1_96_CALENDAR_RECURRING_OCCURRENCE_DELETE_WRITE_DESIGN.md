# V1.96 Calendar Recurring Occurrence Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the Calendar delete gate to delete one selected occurrence of one exact recurring Calendar event. The selected occurrence can belong to any existing recurrence shape because EventKit handles the occurrence split; the gate still does not inspect, edit, clear, or create custom monthly/yearly recurrence rules, unbounded recurrence. It does not approve future-event span deletion, whole-series deletion, mid-series recurrence replacement, existing-recurring-event update, custom/unbounded recurrence editing, attendees, invitations, organizer mutation, travel time, email/procedure alarms, non-allow-listed URL schemes, calendar creation/deletion, account management, or bulk operations.

## EventKit Source Review

EventKit source review is limited to public SDK headers shipped on this Mac plus official Apple EventKit documentation.

- `EKCalendarItem.recurrenceRules` is readable for recurrence-presence checks.
- `EKEventStore.remove(_:span:commit:)` supports span-based event removal.
- Calendar event handles are opaque over EventKit event id plus selected occurrence start/end metadata, so recurring occurrences with the same EventKit identifier receive distinct handles in current search output.
- This gate resolves the selected occurrence by exact EventKit id plus expected start/end window before mutation and refuses legacy event-id-only handles for selected recurring occurrence delete.
- This gate also binds one adjacent same-series occurrence identity before mutation and proves that sibling occurrence still resolves after the selected occurrence is removed.
- This gate uses only `EKSpan.thisEvent` / `.thisEvent` for recurring-event delete.
- The helper does not use `.futureEvents`.
- `EKCalendarItem.attendees` and `EKEvent.organizer` remain readonly, so attendee/invitation/organizer mutation remains blocked.
- This Mac's public EventKit SDK headers still do not expose a writable travel-time property. `scripts/audit_calendar_public_surface.py --json` remains the deterministic local proof for that blocker.

## Plan Contract

`calendar_plan_change` and `local-apple-data calendar plan` accept one delete-only recurrence field:

- `recurrence_delete_scope` / `--recurrence-delete-scope` selects the recurring delete scope.
- `recurrence_delete_scope`: adapter/MCP value `this_event`.
- `--recurrence-delete-scope`: CLI value `this-event`, normalized to `this_event` before planning/apply.

Delete planning:

- Requires one exact `calendar:event:v1:` handle.
- Requires expected current state: title, calendar title, start date, and end date, with optional expected all-day, alarm, availability, URL presence/hash, location, and notes bindings following the existing delete gate.
- Rejects `recurrence_delete_scope` for create or update.
- Rejects `future_events`, whole-series, custom text, and empty values as recurrence-delete scope for recurring-event delete.
- Adds `recurrence_delete_scope:"this_event"` and `recurrence_present:true` to `preview.proposed`.
- Adds `recurrence_present:true` to `preview.target.expected_state`.
- Binds recurrence delete scope and recurrence presence into the approval fingerprint.
- Stays non-mutating.

Default delete without `recurrence_delete_scope` keeps the earlier exact-event delete behavior and still refuses existing recurring events at apply time.

## Apply Contract

Apply recomputes the same plan, requires the matching `calendar-apply:v1:<approval_fingerprint>` token, requires explicit confirmation, resolves exactly one target event by opaque handle, and only then calls the Swift EventKit helper.

Apply:

- Rechecks exact expected current-state fields before mutation.
- Re-resolves the target occurrence by approved EventKit id plus expected start/end window before mutation.
- Re-resolves one adjacent same-series occurrence by EventKit id plus start/end window before mutation.
- Rechecks `expected_recurrence_present:true` before mutation.
- Refuses unscoped delete of a recurring event with `unsupported_event_state`.
- Refuses scoped delete when the selected event is not recurring with `expected_state_mismatch`.
- Refuses scoped delete without a current occurrence-bound handle with `missing_occurrence_identity`.
- Refuses scoped delete when no adjacent same-series occurrence can be resolved with `adjacent_occurrence_not_found`.
- Refuses unsupported recurrence delete scopes with `unsupported_recurrence_delete_scope`.
- Rejects attendee and unsupported alarm states before mutation.
- Removes only the selected occurrence with `store.remove(event, span: .thisEvent, commit: true)`.
- Returns bounded read-back metadata only.
- Reports `verified_absent:true`, `selected_occurrence_verified_absent:true`, and `adjacent_occurrence_verified_present:true` only after read-back proves that the selected EventKit id/start/end no longer resolves and the sibling occurrence still resolves.

This gate intentionally does not use `EKSpan.futureEvents`. Future-span deletion changes the selected occurrence and every later occurrence in the series, so it needs a separate read-back proof that selected and future occurrences are gone or split exactly as expected while earlier occurrences remain intact.

## Synthetic Tests Required

- Adapter plan tests proving delete recurrence-scope preview and approval fingerprint binding.
- Adapter plan tests proving `future_events` and recurrence-delete scope on non-delete operations are rejected.
- Adapter apply tests proving helper payload forwarding with `recurrence_delete_scope:"this_event"` and `expected_recurrence_present:true`.
- Adapter apply tests proving helper payload forwarding with occurrence start/end identity.
- Adapter apply tests proving helper payload forwarding with adjacent occurrence start/end identity.
- Adapter apply tests proving legacy event-id-only handles are rejected for scoped recurring delete.
- Adapter apply tests proving scoped recurring delete refuses when adjacent occurrence preservation proof cannot be established.
- Adapter apply tests proving unscoped recurring delete refuses with `unsupported_event_state`.
- Adapter apply tests proving scoped delete of a non-recurring event refuses with `expected_state_mismatch`.
- Adapter apply tests proving scoped-token replay without scoped input fails with `invalid_approval_token`.
- CLI tests proving `--recurrence-delete-scope this-event` forwards for plan/apply.
- MCP tests proving fake or stale scoped recurring delete requests fail closed without current occurrence identity.
- Swift source assertions for `recurrence_delete_scope`, `expected_recurrence_present`, `missing_occurrence_identity`, adjacent occurrence identity, sibling preservation proof, `unsupported_recurrence_delete_scope`, and `.thisEvent`.
- Runtime synthetic smoke proving direct scoped recurring delete plan/apply absence proof with occurrence start/end identity and adjacent-preservation proof, direct unscoped recurring delete refusal, direct scoped non-recurring delete refusal, live subprocess MCP scoped recurring delete fails closed without mutation when live Calendar access/current recurrence proof is unavailable, and in-process MCP wrapper scoped recurring delete success with synthetic EventKit runner.

## Still Blocked

Future-event span deletion, whole-series deletion, mid-series recurrence replacement, existing-recurring-event update/delete beyond selected-occurrence delete, custom monthly/yearly recurrence rules, unbounded recurrence, recurrence exception editing, attendee/invitation mutation, silent default-calendar guessing or mutation, timed-event time-zone inference, travel time, email/procedure alarms, non-allow-listed event URL schemes, calendar creation/deletion, account management, and bulk Calendar mutation remain blocked.

# V1.97 Calendar Recurring Future Delete Write Design

Status: Apply-capable implementation.

This gate lets an agent delete one selected occurrence and later occurrences of one exact recurring Calendar event. It is local-only, EventKit-only, and exact-handle-only. It does not expose raw EventKit identifiers, event notes, event locations, attendee data, or URL values in tool output.

## Scope

- `recurrence_delete_scope` / `--recurrence-delete-scope` selects the recurring delete span.
- `recurrence_delete_scope`: adapter/MCP value `future_events`.
- `--recurrence-delete-scope`: CLI value `future-events`, normalized to `future_events` before planning/apply.
- Requires one exact `calendar:event:v1:` handle.
- The handle must be an occurrence-bound handle from Calendar search output. Legacy event-id-only handles are rejected.
- The selected occurrence must have one previous same-series occurrence and one future same-series occurrence in the bounded EventKit lookup window.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Adds `recurrence_delete_scope:"future_events"` and `recurrence_present:true` to `preview.proposed`.
- Adds `recurrence_present:true` to `preview.target.expected_state`.
- Binds selected occurrence start/end, previous occurrence start/end, and future occurrence start/end into the approval fingerprint.
- Refuses first-occurrence-like future deletes when no previous same-series occurrence is available with `previous_occurrence_not_found`.
- Refuses tail-occurrence future deletes when no future same-series occurrence is available with `future_occurrence_not_found`.
- Refuses unsupported scopes with `unsupported_recurrence_delete_scope`.

The previous-occurrence requirement intentionally blocks first-occurrence `future_events` deletes, because that is effectively whole-series deletion and needs a separate gate.

## Apply Contract

Apply requires the exact matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- Re-resolves the selected occurrence, previous occurrence, and future occurrence before mutation.
- Refuses if the live proof identities no longer match the approved plan.
- Rechecks `expected_recurrence_present:true` before mutation.
- Removes the selected and later occurrences with `store.remove(event, span: .futureEvents, commit: true)`.
- Reports `verified_absent:true`, `selected_occurrence_verified_absent:true`, `future_occurrence_verified_absent:true`, and `previous_occurrence_verified_present:true` only after read-back proves selected/future absence and previous preservation.

If EventKit reports success but read-back cannot prove all three conditions, apply returns `apply_unknown`, `mutation_applied:true`, and `read_back_unavailable`.

## Verification

Runtime synthetic smoke proving direct future-span recurring delete plan/apply selected/future absence proof and previous-preservation proof plus in-process MCP wrapper future-span recurring delete success with synthetic EventKit runner.

Covered checks:

- Direct plan binds `future_events`, previous occurrence identity, and future occurrence identity.
- Direct apply forwards selected, previous, and future occurrence identities to the helper.
- Direct apply requires selected/future absence proof and previous preservation proof.
- Direct apply refuses missing previous or future proof identities before mutation.
- In-process MCP plan/apply preserves the same scope and read-back proof.
- Swift source assertions require `.futureEvents` and the previous/future occurrence identity fields.

## Still Blocked

- whole-series recurrence delete
- mid-series recurrence replacement
- existing-recurring-event update beyond selected/future-span occurrence delete
- custom monthly/yearly recurrence rules
- unbounded recurrence
- attendee/invitation mutation
- travel time
- email/procedure alarms
- non-allow-listed URL schemes
- bulk Calendar mutation

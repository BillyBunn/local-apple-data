# V1.98 Calendar Recurring Series Delete Write Design

Status: Apply-capable implementation.

This gate lets an agent delete a whole bounded recurring Calendar series by selecting the first visible occurrence of one exact recurring event and applying EventKit's `.futureEvents` span from that first occurrence. It is local-only, EventKit-only, and exact-handle-only. It does not expose raw EventKit identifiers, event notes, event locations, attendee data, or URL values in tool output.

## Scope

- `recurrence_delete_scope` / `--recurrence-delete-scope` selects the recurring delete span.
- `recurrence_delete_scope`: adapter/MCP value `all_events`.
- `--recurrence-delete-scope`: CLI value `all-events`, normalized to `all_events` before planning/apply.
- Requires one exact `calendar:event:v1:` handle.
- The handle must be an occurrence-bound handle from Calendar search output. Legacy event-id-only handles are rejected.
- The selected occurrence must have no previous same-series occurrence in the bounded EventKit lookup window and at least one future same-series occurrence for absence proof.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Adds `recurrence_delete_scope:"all_events"`, `recurrence_present:true`, and `first_occurrence_verified:true` to `preview.proposed`.
- Adds `recurrence_present:true` to `preview.target.expected_state`.
- Binds selected occurrence start/end and future occurrence start/end into the approval fingerprint.
- Refuses non-first-occurrence plans when a previous same-series occurrence is found with `previous_occurrence_present`.
- Refuses tail-occurrence plans when no future same-series occurrence is available with `future_occurrence_not_found`.
- Refuses unsupported scopes with `unsupported_recurrence_delete_scope`.

The previous-occurrence absence proof is bounded by the same local EventKit scan window used for recurring delete proof. This gate therefore reports exactly what it proves: selected/future absence and no previous occurrence visible in that bounded proof window.

## Apply Contract

Apply requires the exact matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- Re-resolves the selected occurrence and future occurrence before mutation.
- Rechecks that no previous same-series occurrence is visible before mutation.
- Refuses if the live proof identities no longer match the approved plan.
- Rechecks `expected_recurrence_present:true` before mutation.
- Removes the selected and later occurrences with `store.remove(event, span: .futureEvents, commit: true)`.
- Reports `verified_absent:true`, `selected_occurrence_verified_absent:true`, `future_occurrence_verified_absent:true`, and `previous_occurrence_verified_absent:true` only after read-back proves selected/future absence and previous-occurrence absence in the bounded proof window.

If EventKit reports success but read-back cannot prove all required conditions, apply returns `apply_unknown`, `mutation_applied:true`, and `read_back_unavailable`.

## Verification

Runtime synthetic smoke proving direct whole-series recurring delete plan/apply selected/future absence proof and previous-absence proof plus in-process MCP wrapper whole-series recurring delete success with synthetic EventKit runner.

Covered checks:

- Direct plan binds `all_events`, selected occurrence identity, future occurrence identity, and first-occurrence proof.
- Direct apply forwards selected and future occurrence identities to the helper.
- Direct apply requires selected/future absence proof and bounded previous absence proof.
- Direct apply refuses a stale plan when a previous same-series occurrence appears before mutation.
- Direct apply refuses missing future proof identities before mutation.
- In-process MCP plan/apply preserves the same scope and read-back proof.
- CLI accepts `--recurrence-delete-scope all-events` for plan/apply.
- Swift source assertions require `.futureEvents`, `relativeOccurrenceCandidates`, `previous_occurrence_present`, and `previous_occurrence_verified_absent`.

## Still Blocked

- mid-series recurrence replacement
- existing-recurring-event update beyond selected/future-span/whole-series occurrence delete
- custom monthly/yearly recurrence rules
- unbounded recurrence
- attendee/invitation mutation
- travel time
- email/procedure alarms
- non-allow-listed URL schemes
- bulk Calendar mutation

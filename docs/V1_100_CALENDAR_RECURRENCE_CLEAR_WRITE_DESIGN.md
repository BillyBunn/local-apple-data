# V1.100 Calendar Recurrence Clear Write Design

Status: Apply-capable implementation.

This gate clears one simple bounded recurrence rule from a recurring Calendar event. It is local-only, EventKit-only, exact-handle gated, and proof-bound. It supports first-visible occurrence whole-series clearing where bounded local evidence shows no previous same-series occurrence and at least one future same-series occurrence, plus mid-series selected-and-future clearing where bounded local evidence shows exact previous, selected, and future same-series occurrence identities.

## Scope

- `clear_recurrence`: adapter/MCP boolean.
- `--clear-recurrence`: CLI flag.
- Optional `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events` only with `clear_recurrence` for mid-series clearing.
- Update-only on one exact `calendar:event:v1:` handle.
- Recurrence-only: proposed title, start/end, location, notes, all-day, time zone, and alarm fields must match expected state; target-calendar move, availability change, event URL set/clear, and new recurrence fields are rejected.
- Only simple bounded recurrence payloads already represented by the plugin are clearable: daily, weekly, monthly, or yearly, interval 1 through 4, count 2 through 52, and optional weekly weekdays.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Requires an occurrence-bound `calendar:event:v1:` handle from Calendar search output.
- Resolves the selected occurrence through the bounded EventKit metadata scan.
- Requires the selected occurrence to be recurring and to expose a supported normalized recurrence payload.
- Binds expected recurrence presence and the exact normalized expected recurrence payload into `preview.target.expected_state`.
- Binds selected occurrence start/end, future occurrence start/end, `clear_recurrence:true`, and either `first_occurrence_verified:true` or `recurrence_update_scope:future_events` plus exact previous occurrence start/end into the approval fingerprint and idempotency key.
- Refuses non-first occurrence plans without `recurrence_update_scope:future_events` when a previous same-series occurrence is found with `previous_occurrence_present`.
- Refuses mid-series plans when no previous same-series occurrence is available with `previous_occurrence_not_found`.
- Refuses tail occurrence plans when no future same-series occurrence is available with `future_occurrence_not_found`.
- Refuses `recurrence_update_scope:this_event`; `recurrence_update_scope:future_events`
  is allowed only with `clear_recurrence` here or with replacement recurrence
  fields through `docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md`.
- recurrence rule replacement on existing recurring events is governed by
  `docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md`, not this
  clear-only gate.
- Refuses scalar/alarm co-mutation with `unsupported_clear_recurrence_shape`.
- Refuses simultaneous recurrence-add fields with `conflicting_recurrence_fields`.

## Apply Contract

Apply requires a matching `calendar-apply:v1:<approval_fingerprint>` token and explicit confirmation.

- Re-resolves the selected occurrence and future occurrence before mutation.
- Rechecks exact expected recurrence presence and exact expected recurrence shape before mutation.
- Rechecks bounded previous-occurrence absence for first-visible clearing or exact previous-occurrence presence for mid-series clearing before mutation.
- Clears recurrence through public EventKit by setting `event.recurrenceRules = nil`.
- Saves with EventKit `.futureEvents` from the selected occurrence.
- Reports success only after read-back proves:
  - selected occurrence still exists and is non-recurring,
  - future occurrence is absent,
  - no previous same-series occurrence is visible in the bounded proof window for first-visible clearing, or the approved previous occurrence remains present for mid-series clearing.
- If EventKit apply succeeds but read-back proof is incomplete, apply returns `apply_unknown` with `mutation_applied:true` and `recurrence_clear_read_back_mismatch`.

## Verification

Covered checks:

- Adapter plan binds expected recurrence shape, selected occurrence identity, future occurrence identity, first-occurrence or previous-occurrence proof, and approval fingerprint.
- Adapter rejects create/delete use, recurrence-add conflicts, invalid clear scope, `future_events` without clear, and scalar co-mutation.
- Adapter apply forwards `clear_recurrence`, exact expected recurrence, selected occurrence identity, future occurrence identity, and mid-series previous occurrence identity.
- Adapter apply requires recurrence-cleared, future-absence, and previous-absence or previous-presence read-back proof.
- CLI accepts and forwards `--clear-recurrence` plus optional `--recurrence-update-scope future-events` for plan/apply.
- MCP accepts and fails closed without occurrence identity in direct wrapper tests; runtime verifier proves in-process MCP plan/apply with a synthetic EventKit runner.
- Swift source uses `event.recurrenceRules = nil`, EventKit `.futureEvents`, exact expected recurrence matching, selected/future occurrence proof, and previous-occurrence absence or preservation proof.
- Runtime verifier proves direct and MCP `clear_recurrence` plan/apply for first-visible and mid-series clearing with recurrence absent on read-back.

## Still Blocked

- existing-recurring-event update beyond selected/future-span/whole-series occurrence delete and first-visible/mid-series recurrence clear
- custom monthly/yearly recurrence components
- unbounded recurrence
- attendee/invitation mutation
- travel time
- email/procedure alarms
- non-allow-listed URL schemes
- bulk Calendar mutation

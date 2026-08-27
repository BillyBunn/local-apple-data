# V1.126 Calendar Recurrence Replacement Write Design

Status: Apply-capable implementation.

This gate replaces the recurrence rule for the selected occurrence and all future
occurrences of one exact recurring Calendar event. It is local-only,
EventKit-only, exact-handle gated, recurrence-only, and proof-bound.

## Scope

- `recurrence_update_scope:future_events` / `--recurrence-update-scope future-events`.
- New finite `recurrence_frequency`, `recurrence_interval`, and either
  `recurrence_count` or `recurrence_end_date` fields, with the same selector
  allowlist used by existing recurrence create/update gates.
- Update-only on one occurrence-bound `calendar:event:v1:` handle.
- Recurrence-only: proposed title, start/end, location, structured location,
  notes, all-day, time zone, alarm fields, event URL state, target calendar, and
  availability must match expected state.
- Supported recurrence shapes remain the approved simple finite EventKit-backed
  shapes: daily, weekly, monthly, or yearly with interval 1 through 4, count 2
  through 52 or end date within 3650 days, and approved weekday/month/year
  selectors including set positions.

## Plan Contract

Planning is non-mutating and returns `mutation_applied:false`.

- Requires an occurrence-bound `calendar:event:v1:` handle from Calendar search output.
- Resolves the selected occurrence through bounded EventKit metadata.
- Requires the selected occurrence to be recurring and to expose a supported
  normalized expected recurrence payload.
- Requires exact previous, selected, and future same-series occurrence identities.
- Binds expected recurrence presence, expected recurrence payload, replacement
  recurrence payload, selected occurrence start/end, previous occurrence
  start/end, future occurrence start/end, and
  `recurrence_update_scope:future_events` into the approval fingerprint and
  idempotency key.
- Refuses scalar, alarm, calendar move, availability, structured-location,
  event-URL, and clear-recurrence co-mutation.
- Refuses `recurrence_update_scope:future_events` without either
  `clear_recurrence` or replacement recurrence fields.

## Apply Contract

Apply requires a matching `calendar-apply:v1:<approval_fingerprint>` token and
explicit confirmation.

- Re-resolves the selected occurrence, previous occurrence, and future occurrence
  before mutation.
- Rechecks exact expected recurrence presence and expected recurrence shape.
- Applies the replacement through public EventKit by setting a new
  `EKRecurrenceRule` on the selected occurrence.
- Saves with EventKit `.futureEvents`.
- Reports success only after read-back proves:
  - the selected occurrence is recurring with the replacement recurrence,
  - at least one future occurrence remains recurring with the replacement recurrence,
  - the original approved future occurrence slot is absent or recurring with the
    replacement recurrence, not left behind on the original recurrence,
  - the approved previous occurrence remains present with the original expected
    recurrence.
- If EventKit apply succeeds but proof is incomplete, apply returns
  `apply_unknown`, `mutation_applied:true`, and
  `recurrence_replacement_read_back_mismatch`.

## Verification

Covered checks:

- Adapter plan binds expected recurrence, replacement recurrence, selected
  occurrence identity, previous occurrence identity, future occurrence identity,
  and approval fingerprint.
- Adapter rejects missing replacement fields, invalid future-events scope, and
  scalar/alarm/calendar/event-URL/availability co-mutation.
- Adapter apply forwards `recurrence_update_scope:future_events`, expected
  recurrence, replacement recurrence, and exact occurrence identities.
- Adapter apply requires replacement, future-occurrence, original future-slot,
  and previous-occurrence read-back proof.
- CLI accepts and forwards `--recurrence-update-scope future-events` with
  recurrence fields for plan/apply.
- MCP accepts and fails closed without occurrence identity in direct wrapper
  tests; runtime verifier proves in-process MCP plan/apply with a synthetic
  EventKit runner.
- Swift source uses public EventKit recurrence-rule replacement and
  `.futureEvents` save.
- Runtime verifier proves direct and MCP replacement plan/apply with previous,
  future, and original future-slot proof.

## Still Blocked

- custom recurrence shapes beyond approved selector-backed finite EventKit rules
- unbounded recurrence
- attendee/invitation mutation
- travel time
- non-allow-listed URL schemes
- procedure alarms
- non-synthetic calendar management beyond approved `LAD-TEST-*` create/rename
- bulk Calendar mutation

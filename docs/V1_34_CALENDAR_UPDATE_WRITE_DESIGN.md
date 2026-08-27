# v1.34 Calendar Update Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

This document extends the existing Calendar plan/apply surface with one non-destructive operation: update one exact event's title, start/end time, location, and notes through EventKit.

## Scope

Approved operation:

- `update`: modify one exact `calendar:event:v1:` handle.

Out of scope:

- Delete, move to another calendar, recurrence edits, attendees or invitations, URLs, attachments, travel time, availability changes, default-calendar guessing, date-only/time-zone inference, and bulk operations. Exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.
- All-day behavior was out of scope for this original v1.34 tranche; explicit all-day update support is now governed by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`.
- Raw EventKit identifier targeting.
- Mutations through iCloud.com, browser sessions, keychain credentials, private iCloud APIs, OAuth, IMAP, or external connectors.

## Tool Contract

`calendar plan --operation update` and `calendar_plan_change` are non-mutating. They require:

- `handle`: exact opaque event handle from Calendar search/get flow.
- `expected_title`, `expected_calendar_title`, `expected_start_date`, `expected_end_date`, `expected_location`, and `expected_notes`: caller-supplied current state.
- Proposed `title`, `start_date`, `end_date`, `location`, and `notes`.

Preview returns `mutation_applied:false`, `apply_available:true`, an idempotency key, and an approval fingerprint without calling EventKit or mutating Calendar data.

`calendar apply --operation update` and `calendar_apply_change` require the same inputs, a matching `calendar-apply:v1:<approval_fingerprint>` token, and explicit confirmation.

Apply recomputes the plan, resolves the opaque handle internally through the bounded EventKit scan, refuses missing targets, refuses stale expected state, refuses recurring/attendee-bearing events, saves only the selected event with `span: .thisEvent`, and returns bounded metadata read_back. Exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.

The approval-token binds the exact handle, expected current state, proposed new state, and idempotency key.

## Redaction

Transient plan/apply responses may include the selected handle and caller-provided Calendar text because they are the approval surface. Durable logs, docs, fixtures, and warnings must not persist real event titles, calendar names, locations, notes, raw EventKit identifiers, approval fingerprints, tokens, framework exception text, or account identifiers.

## Synthetic Tests Required

Required synthetic coverage:

- Update plan success with exact handle and expected-state preview.
- Invalid raw/fabricated handle refusal.
- Missing confirmation and invalid token inherited from the shared apply gate.
- Apply/read-back success using a mocked EventKit helper.
- Stale expected-state refusal.
- Output does not return raw EventKit identifiers and read-back does not expose notes text.

## Current Release Gate

This document allows Calendar create-event and exact-event update only. Calendar exact-event delete is governed by `docs/V1_36_CALENDAR_DELETE_WRITE_DESIGN.md`. Calendar explicit all-day update support is governed by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`. Calendar exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`. Calendar move, recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, default-calendar guessing, date-only/time-zone inference, and bulk operations remain blocked.

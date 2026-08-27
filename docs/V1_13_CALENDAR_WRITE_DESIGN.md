# v1.13 Calendar Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data calendar apply` and `calendar_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data calendar plan` and `calendar_plan_change`; those tools validate and preview future changes without writing Calendar data.

This document defines the first Calendar write lane: create one timed event in an explicit target calendar title through EventKit, with preview as the default behavior and independent read_back verification after apply.

## Scope

Candidate operation:

- Create one timed event in an explicitly selected Calendar.

Out of scope:

- Event update, delete, move, recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, default-calendar guessing, and bulk operations.
- All-day behavior was out of scope for this original v1.13 tranche; explicit all-day support is now governed by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`.
- Exact alarm offsets were out of scope for this original v1.13 tranche; exact alarm-offset support is now governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.
- Raw EventKit identifier targeting.
- Mutations through iCloud.com, browser sessions, keychain credentials, private iCloud APIs, OAuth, IMAP, or external connectors.

## Tool Contract

Every future Calendar write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching EventKit.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal EventKit-backed Calendar adapter.

The preview payload must include the operation, explicit target calendar title, normalized title, normalized start and end timestamps, optional location/notes presence, warning codes, and a deterministic idempotency key. It must not include raw EventKit identifiers, account identifiers, unrelated event content, or framework exception text.

The apply payload must require an approval token or equivalent explicit approval artifact generated from the preview. The token must bind the operation, target calendar title, normalized title, normalized timestamps, normalized location/notes, and idempotency key so an agent cannot apply a different mutation with a stale preview.

The read_back payload must return EventKit event metadata through the same bounded public fields used by `calendar_get_event`. It must not trust the write call alone.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data calendar plan`
- MCP: `calendar_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `create`.
- Require an explicit target calendar title.
- Require a title, start timestamp, and end timestamp.
- Require ISO 8601 timestamps with timezones and reject non-positive durations.
- Return a deterministic `calendar-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not call EventKit, read Calendar data, or mutate Calendar data.

Implemented apply tools:

- CLI: `local-apple-data calendar apply`
- MCP: `calendar_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `calendar-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the target calendar by exact title through EventKit.
- Refuse missing or ambiguous target calendars.
- Create only one non-recurring timed event.
- Return `mutation_applied:true` only after EventKit save succeeds and read_back data is available.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use the existing Swift EventKit helper path for Calendar writes:

- Swift owns EventKit calls, permission checks, calendar lookup, event save calls, and framework error normalization.
- Python owns CLI/MCP request validation, approval-token verification, logging, redaction, and JSON response shape.
- The MCP server stays stdio and local-only.

Swift is the right boundary for Calendar write calls because EventKit is native, typed, permission-aware, and already required for Calendar reads. Python remains the right boundary for the plugin because the current CLI, tests, redaction scanners, release gates, and MCP server already wrap narrow helper calls cheaply.

## Data Model

Required create input:

- `calendar_title`: exact target calendar title.
- `title`: event title.
- `start_date`: ISO 8601 timestamp with timezone.
- `end_date`: ISO 8601 timestamp with timezone and after `start_date`.

Optional create input:

- `location`, capped at the normal location limit.
- `notes`, capped at the normal text-content maximum.

All inputs are bounded. Attendees, recurrence, URLs, attachments, and all-day behavior were not accepted in this tranche. Explicit all-day support is now governed by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`; exact alarm-offset support is now governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`.

## Approval Gate

Before any additional apply-capable Calendar tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `calendar_plan_change` remains read-only; `calendar_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-safe:

- Create uses a deterministic idempotency key derived from target calendar title, normalized title, normalized timestamps, normalized location/notes, and approval token.
- The Swift helper treats an existing event in the same target calendar with matching title, start, end, location, and notes as `already_applied`.
- Existing partial or different events do not satisfy idempotency.

No implementation may create durable personal-content caches to solve idempotency. Any local operation ledger must store only opaque operation IDs, warning codes, timestamps, and hashes of normalized approved fields.

## Logging And Redaction

The redaction requirement applies to previews, applies, runtime smoke, tests, and release receipts.

Logs may include:

- Tool name.
- Status.
- Warning code.
- Counts.
- Duration.

Logs must not include:

- Event titles.
- Locations or notes.
- Calendar names.
- Raw EventKit identifiers.
- Account names.
- Approval tokens or fingerprints.
- Framework exception text.

## Synthetic Tests Required

Before exposure, the Calendar write implementation must add:

- Preview success tests for create.
- Preview validation tests for missing fields, invalid timestamps, non-positive durations, and oversized fields.
- Apply/read_back success tests using mocked EventKit helper responses.
- Missing-confirmation and invalid-token tests.
- Target-calendar-not-found and ambiguous-calendar tests.
- Idempotency tests for retry after success.
- Redaction tests proving logs do not contain titles, calendar names, locations, notes, approval fingerprints, tokens, raw EventKit identifiers, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The v1.13 release allowed only this Calendar create-event apply surface. Calendar exact-event update is governed by `docs/V1_34_CALENDAR_UPDATE_WRITE_DESIGN.md`. Calendar exact-event delete is governed by `docs/V1_36_CALENDAR_DELETE_WRITE_DESIGN.md`. Calendar explicit all-day support is governed by `docs/V1_55_CALENDAR_ALL_DAY_WRITE_DESIGN.md`. Calendar exact alarm-offset support is governed by `docs/V1_56_CALENDAR_ALARM_WRITE_DESIGN.md`. Calendar move, recurrence, attendees, invitations, URLs, attachments, travel time, availability changes, default-calendar guessing, date-only/time-zone inference, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

# v1.11 Reminders Write Design

Status: Preview-only implementation.

No mutating CLI or MCP tools are approved or exposed by this document. The current implementation exposes `local-apple-data reminders plan` and `reminders_plan_change` only; these tools validate and preview future changes but do not read, apply, or mutate Reminders state. Future implementation requires explicit approval before any apply-capable tool is exposed.

This document defines the first write lane for local Reminders. It is intentionally narrower than the overall write roadmap: create one reminder, complete one reminder, or update one reminder due date through EventKit, with preview as the default behavior and independent read_back verification after any future apply.

## Scope

Candidate operations:

- Create reminder in an explicitly selected Reminders list.
- Complete reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle.
- Update due date for a reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle.

Out of scope:

- Delete reminders.
- Bulk edits.
- Account, list, or sharing management.
- Reminder attachments, URLs, images, or rich content.
- Mutations through iCloud.com, browser sessions, keychain credentials, private iCloud APIs, OAuth, IMAP, or external connectors.

## Tool Contract

Every future Reminders write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching Apple data.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal read-only Reminders adapter.

The preview payload must include the operation, target list or exact reminder handle, normalized title, normalized due date, completion-state transition when relevant, warning codes, and a deterministic idempotency key. It must not include raw EventKit identifiers, raw local paths, account identifiers, personal content from unrelated reminders, or framework exception text.

The apply payload must require an approval token or equivalent explicit approval artifact generated from the preview. The token must bind the operation, target, normalized fields, and idempotency key so an agent cannot apply a different mutation with a stale preview.

The read_back payload must retrieve the changed reminder through EventKit and then return the same bounded public fields used by `reminders_get_content`. It must not trust the apply response alone.

## Current Preview Tools

Implemented now:

- CLI: `local-apple-data reminders plan`
- MCP: `reminders_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:false`.
- Require operation-specific inputs for `create`, `complete`, or `update_due_date`.
- Require exact opaque `reminders:reminder:eventkit:v1:` handles for existing-reminder operations.
- Return a deterministic `reminders-plan:v1:` idempotency key.
- Return an approval fingerprint for future apply-token binding.
- Do not call EventKit, read Reminders, or mutate Reminders.

They intentionally avoid tool names such as `create`, `complete`, `update`, `apply`, or `write` so agents and auditors do not mistake the preview surface for an approved mutation surface.

## Implementation Choice

Use the existing Swift EventKit helper path for performance and durability:

- Swift owns EventKit calls, permission checks, reminder save calls, and framework error normalization.
- Python owns CLI/MCP request validation, opaque handles, approval-token verification, logging, redaction, and JSON response shape.
- The MCP server stays stdio and local-only.

Swift is the right boundary for the Apple framework call because EventKit is native, typed, and already required for Calendar and Reminders reads. Python remains the right boundary for the plugin because the current CLI, tests, redaction scanners, release gates, and MCP server are already Python and can wrap narrow Swift helper calls cheaply.

## Data Model

Required create input:

- `list_handle` or a future opaque list selector returned by a metadata-only list tool.
- `title`.
- Optional due date with explicit time zone.
- Optional notes, capped and redacted from logs.

Required complete/update input:

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- Expected current title or completion state from a recent read result.
- Operation-specific fields.

All inputs must be bounded. Free-form notes must use the same maximum character policy as Reminder notes retrieval unless a later approved design changes it.

## Approval Gate

Before any future apply-capable Reminders tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `reminders_plan_change` may remain read-only; apply-capable tools need separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The future apply path must be retry-safe:

- Create uses a deterministic idempotency key derived from target list, normalized title, normalized due date, and caller approval token.
- Complete is idempotent when the reminder is already complete and the read_back result matches the approved target.
- Due-date update is idempotent when the reminder already has the approved due date.
- Partial failures must return a stable warning code and require read_back before retry advice.

No implementation may create durable personal-content caches to solve idempotency. Any local operation ledger must store only opaque operation IDs, warning codes, timestamps, and hashes of normalized approved fields.

## Logging And Redaction

Logs may include:

- Tool name.
- Status.
- Warning code.
- Counts.
- Duration.

Logs must not include:

- Reminder titles or notes.
- Handles.
- Raw EventKit identifiers.
- Account names.
- List names.
- Local paths.
- Framework exception text.
- Approval tokens.

## Synthetic Tests Required

Before exposure, the Reminders write implementation must add:

- Preview success tests for create, complete, and due-date update.
- Preview validation tests for missing target list, invalid handles, stale expected state, invalid dates, and oversized notes.
- Apply/read_back success tests using mocked EventKit helper responses.
- Permission-denied tests returning `reminders_access_unavailable`.
- Partial-failure tests returning stable warning codes.
- Idempotency tests for retry after success and retry after uncertain apply.
- Redaction tests proving logs do not contain titles, notes, handles, EventKit identifiers, approval tokens, raw paths, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The current release remains read-only. The implemented planning tools exist so the next implementation tranche can be reviewed against a specific contract instead of a vague write roadmap.

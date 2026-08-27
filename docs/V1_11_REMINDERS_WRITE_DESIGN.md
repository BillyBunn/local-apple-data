# v1.11 Reminders Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data reminders plan` and `reminders_plan_change`; those tools validate and preview future changes without mutating Reminders state.

This document defines the bounded write lane for local Reminders. It is intentionally narrower than the overall write roadmap: create one reminder, complete one reminder, uncomplete one reminder, update one reminder due date, update one reminder title, update one reminder notes field, update one reminder priority, move one exact reminder to one exact same-source target list with exact expected current-list identity proof, or delete one exact reminder through EventKit, with preview as the default behavior and independent read_back verification after apply. The destructive delete gate is additionally specified in `docs/V1_35_REMINDERS_DELETE_WRITE_DESIGN.md`; the exact same-source target-list move gate is specified in `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`.

## Scope

Candidate operations:

- Create reminder in an explicitly selected Reminders list.
- Complete reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle.
- Uncomplete reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle.
- Update due date for a reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle.
- Update title for a reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle.
- Update notes for a reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle and the current exact-content notes SHA-256.
- Update priority for a reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle and expected current priority.
- Move one reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle from one exact expected current-list opaque `reminders:list:eventkit:v1:` handle to one exact same-source opaque `reminders:list:eventkit:v1:` target list with expected current list name.
- Delete one reminder identified by an exact opaque `reminders:reminder:eventkit:v1:` handle, expected title, expected completion state, expected priority, and current exact-content notes SHA-256.

Out of scope:

- Bulk edits.
- Account, list, or sharing management.
- List/account moves outside the exact same-source expected-current-list plus target-list identity-proof gate in `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`.
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

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data reminders plan`
- MCP: `reminders_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Require operation-specific inputs for `create`, `complete`, `uncomplete`, or `update_due_date`.
- Require operation-specific inputs for `update_title`, `update_notes`, `update_priority`, and `delete`.
- Require operation-specific inputs for `move_to_list`.
- Require exact opaque `reminders:reminder:eventkit:v1:` handles for existing-reminder operations.
- Require exact opaque `reminders:list:eventkit:v1:` expected current-list and target-list handles for `move_to_list`.
- Require `expected_title` for every existing-reminder operation.
- Require `expected_list_name` for `move_to_list`.
- Require `expected_notes_sha256` for `update_notes`, sourced from exact `reminders content` retrieval; empty notes are allowed only when the caller explicitly supplies an empty replacement notes value.
- Require `expected_priority` and replacement `priority` for `update_priority`; priority is bounded to EventKit's `0..9` integer range.
- Require `expected_completed`, `expected_priority`, and `expected_notes_sha256` for `delete`.
- Return a deterministic `reminders-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not call EventKit, read Reminders, or mutate Reminders.

Implemented apply tools:

- CLI: `local-apple-data reminders apply`
- MCP: `reminders_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `reminders-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Require operation-specific expected state.
- Resolve existing Reminder targets from exact opaque `reminders:reminder:eventkit:v1:` handles.
- For `update_notes`, verify the current Reminder notes hash through exact EventKit read before applying the replacement.
- For `move_to_list`, resolve the exact expected current-list and same-source target-list handles through EventKit list metadata before applying the reassignment.
- For `delete`, verify the current Reminder notes hash through exact EventKit read before applying the removal and require read_back absence proof.
- Call the Swift EventKit helper only after the approval token and confirmation checks pass.
- Return `mutation_applied:true` only after EventKit save succeeds and read_back data is available.
- Use non-read-only, destructive, non-idempotent, closed-world MCP annotations because `reminders_apply_change` can delete.

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

Required complete/uncomplete/due-date/title/notes/priority update/delete input:

- Exact opaque `reminders:reminder:eventkit:v1:` handle.
- Expected current title from a recent read result.
- Optional expected current completion state for completion-state drift checks.
- Operation-specific fields.

Additional update inputs:

- `update_title`: replacement title, bounded to the normal Reminders title cap.
- `update_notes`: replacement notes text, bounded to the normal Reminder notes cap, plus `expected_notes_sha256` from exact Reminder content retrieval.
- `update_priority`: replacement priority and expected current priority, both integers from `0` to `9`.
- `move_to_list`: exact opaque `reminders:list:eventkit:v1:` expected current-list handle, exact same-source opaque target-list handle, expected current list name, expected completion state, and expected title.
- `delete`: expected completion state, expected current priority, and `expected_notes_sha256` from exact Reminder content retrieval.

All inputs must be bounded. Free-form notes must use the same maximum character policy as Reminder notes retrieval unless a later approved design changes it.

## Approval Gate

Before any additional apply-capable Reminders tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `reminders_plan_change` remains read-only; `reminders_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-safe only for operations whose current-state binding still matches:

- Create uses a deterministic idempotency key derived from target list, normalized title, normalized due date, and caller approval token.
- Complete is idempotent when the reminder is already complete and the read_back result matches the approved target.
- Uncomplete is idempotent when the reminder is already incomplete and the read_back result matches the approved target.
- Due-date update is idempotent when the reminder already has the approved due date.
- Title update is idempotent when the reminder already has the approved title.
- Notes update is idempotent when the reminder already has the approved replacement notes.
- Priority update is idempotent when the reminder already has the approved priority.
- List-move is not retry-safe with the original pre-move approval token after a successful move; stale expected current-list handle or title must return `expected_state_mismatch` before any already-target shortcut. A retry requires a fresh plan bound to the reminder's then-current list handle.
- Delete is not idempotent before apply without an operation ledger. If the target is absent before apply, return not found with `mutation_applied:false`; after apply, require read_back absence proof.
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

- Preview success tests for create, complete, uncomplete, and due-date update.
- Preview success tests for title, notes, and priority update.
- Preview success tests for exact same-source list-move with exact reminder, expected current-list, and target-list handles.
- Preview success tests for delete with exact handle plus expected completion, priority, and notes hash.
- Preview validation tests for missing target list, invalid handles, stale expected state, invalid dates, and oversized notes.
- Preview validation tests for missing expected notes hash, invalid notes hash, missing expected priority, missing replacement priority, out-of-range priority, malformed target-list handles, and missing expected list name.
- Preview validation tests for delete missing exact expected state and raw identifier rejection.
- Apply/read_back success tests using mocked EventKit helper responses.
- Apply/read_back success tests for title, notes, and priority update using mocked EventKit helper responses.
- Notes update drift tests proving apply refuses when current notes SHA-256 differs from the approved plan.
- Delete apply tests proving exact-handle resolution, current notes SHA-256 drift refusal, absence proof, and raw EventKit identifier redaction.
- Permission-denied tests returning `reminders_access_unavailable`.
- Partial-failure tests returning stable warning codes.
- Idempotency tests for retry after success where approved, stale-state refusal for list-move original-token retry, and retry after uncertain apply.
- Redaction tests proving logs do not contain titles, notes, handles, EventKit identifiers, approval tokens, raw paths, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

This document allows only this Reminders apply surface. Reminder bulk edits, list/account moves outside `docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md`, list/account management, attachments, images, rich-content mutation, and delete outside the exact-handle gate in `docs/V1_35_REMINDERS_DELETE_WRITE_DESIGN.md` remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`. The blanket URL blocker in this historical design is superseded only for exact URL update/clear by `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`; all other Reminder URL mutation remains blocked.

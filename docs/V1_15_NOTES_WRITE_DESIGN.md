# v1.15 Notes Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data notes apply` and `notes_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data notes plan` and `notes_plan_change`; those tools validate and preview future changes without writing Notes data.

This document defines the first Notes write lane: create one plaintext note in the default Notes account/folder through Notes.app automation, with preview as the default behavior and independent read_back verification after apply.

## Scope

Candidate operation:

- Create one plaintext note with a bounded title and bounded body text.

Out of scope:

- Note append, update, delete, move, folder creation, folder/account targeting, rich-text editing, checklist state, attachments, locked notes, shared-note mutation, Recently Deleted management, and bulk operations.
- Raw Notes Core Data identifiers or local Notes database paths as user inputs.
- Mutations through iCloud.com, browser sessions, keychain credentials, private iCloud APIs, OAuth, IMAP, or external connectors.

## Tool Contract

Every future Notes write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching Notes.app or the local Notes database.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal Notes metadata/content adapter.

The preview payload must include the operation, default target account/folder marker, normalized title, bounded body preview, body length, warning codes, and a deterministic idempotency key. It must not include raw Notes identifiers, local database paths, account identifiers, unrelated note content, attachments, or AppleScript exception text.

The apply payload must require an approval token or equivalent explicit approval artifact generated from the preview. The token must bind the operation, normalized title, normalized body hash, target marker, and idempotency key so an agent cannot apply a different mutation with a stale preview.

The read_back payload must return the created note through the existing Notes exact-content shape, using opaque `notes:note:v2:` handles and bounded plain text. It must not trust the AppleScript write call alone.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data notes plan`
- MCP: `notes_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `create`.
- Require a non-empty title with at least two letters or digits.
- Cap title and body input.
- Return a deterministic `notes-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not call Notes.app, read Notes data, or mutate Notes data.

Implemented apply tools:

- CLI: `local-apple-data notes apply`
- MCP: `notes_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `notes-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Use Notes.app automation to create one plaintext note in the default Notes destination.
- Treat an existing note with matching normalized title and body text as `already_applied`.
- Return `mutation_applied:true` only after Notes.app accepts the create request; return `status: "ok"` only after read_back data is available.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use the existing Python Notes adapter plus Notes.app AppleScript automation:

- Python owns CLI/MCP request validation, approval-token verification, Notes.app AppleScript generation, read-back selection through the existing SQLite-backed Notes adapter, logging, redaction, and JSON response shape.
- Notes.app automation owns the actual create operation because Apple does not expose a public Notes CRUD framework on macOS.
- The MCP server stays stdio and local-only.

Python remains the right boundary for this tranche because the current Notes read path already uses a bounded AppleScript runner abstraction, the CLI/MCP/test stack is Python, and synthetic tests can prove the mutation contract without executing real Notes.app writes. A separate Swift helper would not add a native public Notes API; it would still need to drive Notes automation or private stores.

## Data Model

Required create input:

- `operation`: `create`.
- `title`: non-empty plaintext title.

Optional create input:

- `body_text`: plaintext body, capped at 12000 normalized characters.

The create body is converted to minimal HTML for Notes.app with the title as a heading and body lines as paragraphs. Rich text, attachments, checklist state, folder/account targeting, append, update, delete, and move behavior are not accepted in this tranche.

## Approval Gate

Before any additional apply-capable Notes tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `notes_plan_change` remains read-only; `notes_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-safe:

- Create uses a deterministic idempotency key derived from the normalized title, normalized body hash, target marker, and approval token.
- Before creating, the adapter searches by the exact title and compares exact-handle content for same-title notes against the approved normalized body.
- A matching existing note returns `already_applied` and does not execute the create script.
- Existing partial or different notes do not satisfy idempotency.

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

- Note titles.
- Note bodies or body previews.
- Opaque note handles.
- Raw Notes identifiers.
- Local Notes database paths.
- Account or folder identifiers.
- Approval tokens or fingerprints.
- AppleScript exception text.

## Synthetic Tests Required

Before exposure, the Notes write implementation must add:

- Preview success tests for create.
- Preview validation tests for missing title, invalid operation, oversized title, and oversized body.
- Apply/read_back success tests using mocked Notes.app automation responses and synthetic SQLite rows.
- Missing-confirmation and invalid-token tests.
- Automation timeout/error tests.
- Idempotency tests for retry after success.
- Redaction tests proving logs do not contain titles, bodies, body previews, handles, approval fingerprints, tokens, raw Notes identifiers, raw paths, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The current release allows only this Notes create-note apply surface. Notes append, update, delete, move, folder creation, folder/account targeting, rich-text editing, checklist state, attachments, locked/shared-note mutation, Recently Deleted management, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

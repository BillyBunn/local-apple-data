# v1.16 Mail Draft Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data mail plan` and `mail_plan_change`; those tools validate and preview future changes without writing Mail data.

This document defines the first Mail write lane: create one plaintext draft in Apple Mail through Mail.app automation, with preview as the default behavior and independent read_back verification after apply when the local Mail store indexes the draft.

## Scope

Candidate operation:

- Create one plaintext draft with bounded recipients, subject, and body text.

Out of scope:

- Sending mail, reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, attachments, HTML/rich-text drafts, template storage, bulk operations, and sender selection outside the approved draft/send/reply/reply-all/forward sender gate.
- Raw Mail database row IDs, mailbox refs, local Mail file paths, or account identifiers as user inputs.
- Mutations through Gmail, IMAP, OAuth, iCloud.com, browser sessions, keychain credentials, private iCloud APIs, network mail APIs, or external connectors.

## Tool Contract

Every future Mail write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching Mail.app or the local Mail database.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal Mail metadata/content adapter when the local store exposes the draft.

The preview payload must include the operation, default Mail.app account marker, Drafts target marker, normalized recipients, normalized subject, bounded body preview, warning codes, and a deterministic idempotency key. It must not include raw Mail identifiers, local database paths, mailbox URLs, account identifiers, unrelated mail content, attachments, or AppleScript exception text.

The apply payload must require an approval token or equivalent explicit approval artifact generated from the preview. The token must bind the operation, recipients, normalized subject, normalized body hash, target marker, and idempotency key so an agent cannot apply a different mutation with a stale preview.

The read_back payload must return the created draft through the existing Mail exact-content shape, using opaque `mail:message:v2:` handles and bounded plain text when available. It must not trust the AppleScript save call alone.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data mail plan`
- MCP: `mail_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `create_draft`.
- Require at least one To recipient and a non-empty subject.
- Accept only bounded plain email-address recipients.
- Cap subject and body input.
- Return a deterministic `mail-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not call Mail.app, read Mail data, or mutate Mail data.

Implemented apply tools:

- CLI: `local-apple-data mail apply`
- MCP: `mail_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `mail-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Use save-only Mail.app automation to create one plaintext draft with `save`; the generated automation does not call `send`.
- Treat an existing Drafts mailbox message with matching normalized subject and body as `already_applied`.
- Return `mutation_applied:true` only after Mail.app accepts the save request; return `status: "ok"` only after read_back data is available.
- Return `status: "partial"` when Mail.app accepts the draft save but the local Mail store has not made read_back available yet.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use the existing Python Mail adapter plus Mail.app AppleScript automation:

- Python owns CLI/MCP request validation, approval-token verification, Mail.app AppleScript generation, best-effort idempotency through the existing local Mail read path, logging, redaction, and JSON response shape.
- Mail.app automation owns the actual draft save operation because Apple Mail exposes draft composition through its local scripting dictionary.
- The MCP server stays stdio and local-only.

Python remains the right boundary for this tranche because the current Mail read path and CLI/MCP/test stack are Python, and synthetic tests can prove the mutation contract without executing real Mail.app writes. Swift would not add a better public Mail draft API; it would still need to drive Mail automation or private stores.

## Data Model

Required create input:

- `operation`: `create_draft`.
- `to`: one or more plaintext email addresses.
- `subject`: non-empty plaintext subject.

Optional create input:

- `cc`: bounded plaintext email-address list.
- `bcc`: bounded plaintext email-address list.
- `body_text`: plaintext body, capped at 12000 normalized characters.

Sender-account selection is intentionally absent in this tranche. Mail.app uses its default send account for the saved draft. Attachments, HTML, rich text, reply/forward metadata, and send behavior are not accepted.

## Approval Gate

Before any additional apply-capable Mail tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `mail_plan_change` remains read-only; `mail_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-safe:

- Create uses a deterministic idempotency key derived from recipients, normalized subject, normalized body hash, target marker, and approval token.
- Before creating, the adapter searches by exact subject, narrows to Drafts mailbox metadata, and compares exact-handle content against the approved normalized body when content is available.
- A matching existing draft returns `already_applied` and does not execute the create script.
- Existing partial, differently addressed, or different-content drafts do not satisfy idempotency unless subject/body read-back match exactly. Recipient read-back is not available from the current local Mail metadata path, so this tranche treats subject/body/Drafts matching as best-effort idempotency only.

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

- Recipient addresses.
- Subjects.
- Body text or body previews.
- Opaque Mail handles.
- Raw Mail identifiers.
- Mailbox URLs.
- Local Mail database or `.emlx` paths.
- Account identifiers.
- Approval tokens or fingerprints.
- AppleScript exception text.

## Synthetic Tests Required

Before exposure, the Mail draft implementation must add:

- Preview success tests for create_draft.
- Preview validation tests for missing To recipient, invalid recipients, missing subject, invalid operation, oversized subject, and oversized body.
- Apply/read_back success tests using mocked Mail.app automation responses and synthetic SQLite/.emlx rows.
- Missing-confirmation and invalid-token tests.
- Automation timeout/error tests.
- Idempotency tests for retry after success.
- Redaction tests proving logs do not contain recipients, subjects, bodies, body previews, handles, approval fingerprints, tokens, raw Mail identifiers, raw paths, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The v1.16 release allowed only this Mail create-draft apply surface. Later Mail read/flag/archive/move/trash triage, send-message, reply-message, reply-all-message, forward-message, and capped exact bulk triage support are governed by their own design gates. Mail reply outside the exact-message sender-only or reply-all gates, forward outside the exact-message no-source-attachments/no-non-body-parts gate, source attachment/non-body-part forwarding, cross-account move outside the exact target-mailbox gate, permanent delete, mailbox/account management, attachments outside approved draft/send/reply/reply-all/forward local-file gates, HTML/rich-text draft mutation, template storage, query-result auto-apply, unbounded bulk mutation, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, and send outside the v1.43 send-message gate remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

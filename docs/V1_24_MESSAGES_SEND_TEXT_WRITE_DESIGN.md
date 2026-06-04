# v1.24 Messages Send-Text Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data messages apply` and `messages_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data messages plan` and `messages_plan_change`; those tools validate and preview future changes without writing Messages data.

This document defines the first Messages write lane: send one bounded plaintext message to one exact existing Messages chat selected by an opaque `messages:chat:v1:` handle, with preview as the default behavior and independent local read_back verification after apply.

## Scope

Candidate operation:

- Send one plaintext message to one existing selected chat.

Out of scope:

- Direct recipient sends, new chat creation, SMS fallback selection, outgoing-account selection, file sends, rich text, effects, inline replies, reactions/tapbacks, edit, unsend, delete, mark read, group management, participant lookup, contact lookup, network/iCloud APIs, IMCore injection, private frameworks, and bulk operations.
- Raw chat row IDs, chat GUIDs, addresses, phone numbers, email addresses, participant identifiers, local database paths, and direct Messages attachment paths as user-facing inputs.

## Source Review

The implementation follows the safest public-agent pattern visible in existing macOS Messages tools:

- `imsg` reads local `~/Library/Messages/chat.db` directly for reads/watch state and drives normal sends through Messages.app AppleScript automation: https://github.com/openclaw/imsg
- `imsg` documents that chat-target sends need local readback and ghost-row detection because Messages.app can report AppleScript success while writing an empty unjoined outgoing row on macOS 26: https://imsg.sh/send.html
- `imsg` documents group/chat sends through AppleScript `chat id "<handle>"`, and separately notes that AppleScript cannot force a particular outgoing local number/account: https://imsg.sh/groups.html

We intentionally do less than `imsg`: only exact existing-chat plaintext sends are approved. Advanced IMCore, direct recipients, attachments, rich send, reactions, and chat management remain out of scope.

## Tool Contract

Every future Messages write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching Messages.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through local Messages `chat.db` after apply.

The preview payload must include the operation, opaque target chat handle, bounded chat metadata, message-count and last-message state, proposed plaintext length, bounded body preview, and a deterministic idempotency key. It must not include participant handles, phone numbers, email addresses, chat GUIDs, raw row IDs, local database paths, full chat transcripts, or raw helper errors.

The apply payload must require an approval token generated from the preview. The token must bind the operation, exact target chat state, body SHA-256, and idempotency key so an agent cannot apply a different body or a stale chat state with an old preview.

The read_back payload must confirm a matching outgoing message joined to the same chat after the pre-send last-message row. It must return bounded metadata, body character count, text source, and body SHA-256; it must not return the sent body plaintext.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data messages plan`
- MCP: `messages_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `send_text`.
- Require an exact opaque `messages:chat:v1:` handle selected from Messages chat metadata.
- Require non-empty bounded plaintext.
- Return a deterministic `messages-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Bind the preview to current chat state, including `message_count`, `last_message_date`, and `last_message_rowid`.
- Do not call Messages.app automation and do not mutate Messages data.

Implemented apply tools:

- CLI: `local-apple-data messages apply`
- MCP: `messages_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `messages-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying so changed body text or changed chat state triggers stale chat-state refusal through approval-token mismatch.
- Use local Messages.app AppleScript automation to send plaintext to the selected existing chat id.
- Require local read_back from `chat.db` before returning success.
- Detect the empty unjoined outgoing ghost-row failure and return a non-success status.
- Return `mutation_applied:true` only when the send attempt occurred; return `status:"ok"` only when read_back confirms the matching outgoing body hash.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use Python for CLI/MCP validation and a narrow AppleScript call for the actual send:

- Python owns handle validation, body normalization, plan generation, approval-token verification, chat-state binding, readback polling, ghost-row detection, privacy-safe JSON shaping, logging, redaction, and synthetic tests.
- AppleScript owns only the public Messages.app send operation against an existing chat id.
- SQLite is read in read-only/query-only mode before and after apply.
- The MCP server stays stdio and local-only.

This is the fastest durable path for this project: it reuses the existing Python adapter/test/plugin architecture, avoids private APIs, and adopts the proven local readback pattern used by dedicated Messages tools without widening this plugin into a full Messages automation suite.

## Data Model

Required send input:

- `operation`: `send_text`.
- `handle`: exact opaque `messages:chat:v1:` handle.
- `body_text`: bounded plaintext message body.

Preview target metadata:

- `handle`
- `display_name`
- `service_name`
- `participants_count`
- `message_count`
- `last_message_date`
- `last_message_rowid`

Preview proposed metadata:

- `kind`
- `format`
- `body_chars`
- `body_preview_text`
- `body_preview_chars`
- `body_preview_truncated`
- `attachments_permitted:false`
- `direct_recipient_send_permitted:false`

Apply read_back metadata:

- `chat_handle_confirmed`
- `message_date`
- `direction`
- `service`
- `text_source`
- `body_chars`
- `body_sha256`

The sent body text is accepted as input and may appear in plan preview only as the explicit bounded preview returned to the caller. It is not logged, cached, or echoed in apply read_back.

## Approval Gate

Before any additional apply-capable Messages tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `messages_plan_change` remains read-only; `messages_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-disciplined:

- Preview creates a deterministic idempotency key from operation, target chat state, and body hash.
- Apply recomputes the plan immediately before sending; changed chat state or changed body text causes approval-token mismatch.
- Apply reads the current last-message row before sending and only accepts a newer outgoing row joined to the selected chat with matching normalized body text.
- If read_back is unavailable after an attempted send, the operation returns non-success and the caller must inspect/search Messages before retrying.
- A future operation ledger may improve duplicate handling, but it must store only opaque operation IDs, warning codes, timestamps, and hashes. It must not store body text, chat GUIDs, participant handles, raw row IDs, or local paths.

## Logging And Redaction

The redaction requirement applies to previews, applies, runtime smoke, tests, and release receipts.

Logs may include:

- Tool name.
- Status.
- Warning code.
- Counts.
- Duration.

Logs must not include:

- Message body text.
- Participant handles, phone numbers, email addresses, chat GUIDs, raw row IDs, or account identifiers.
- Opaque handles.
- Approval tokens or fingerprints.
- Body hashes.
- Local Messages database or attachment paths.
- Raw AppleScript or SQLite errors.
- Raw helper errors or stack traces.

## Synthetic Tests Required

Before exposure, the Messages send-text implementation must add:

- Preview success tests for `send_text`.
- Preview validation tests for invalid operation, invalid handle, empty body, and oversized body.
- Apply/read_back success tests using a mocked script runner and synthetic Messages database.
- Missing-confirmation and invalid-token tests.
- Stale chat-state refusal tests.
- Ghost-row detection tests.
- Automation timeout/error tests.
- Degraded-store tests.
- Redaction tests proving logs do not contain message bodies, participant handles, chat GUIDs, raw row IDs, local paths, body hashes, approval fingerprints, tokens, raw helper errors, or stack traces.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The current release allows only this Messages send-text apply surface. Direct recipient sends, new chat creation, SMS fallback selection, outgoing-account selection, file sends, rich text, effects, inline replies, reactions/tapbacks, edit, unsend, delete, mark read, group management, participant lookup, contact lookup, network/iCloud APIs, IMCore injection, private frameworks, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

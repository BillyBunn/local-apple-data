# V1.40 Mail Exact-Message Archive Write Design

Status: Apply-capable implementation.

## Scope

This document approves `archive_message` for one exact existing local Mail message selected by an opaque `mail:message:v2:` handle. It reuses the existing `mail plan` / `mail apply` CLI commands and `mail_plan_change` / `mail_apply_change` MCP tools.

The operation moves the selected message from its current mailbox to the selected message account's local Archive mailbox. It does not approve arbitrary mailbox moves, cross-account moves outside the exact target-mailbox gate, send, reply, forward, Trash, permanent delete, empty Trash/Junk, mailbox creation, mailbox rename, mailbox deletion, account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation, broad export, templates, HTML/rich-text mutation, or bulk operations. Exact-message Trash is governed separately by `docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md`.

## Preview

Planning resolves the exact message through the local Mail Envelope Index and the existing `.emlx` RFC Message-ID bridge. The plan refuses invalid handles, missing message identity, missing Archive mailbox, ambiguous Archive mailbox, and deleted messages.

The approval fingerprint binds:

- Operation: `archive_message`
- Exact opaque message handle
- Current read state
- Current flagged state
- Current mailbox reference
- Target mailbox kind: `archive`
- Target Archive mailbox reference
- Deterministic idempotency key

The preview does not call Mail.app and does not write Mail data. It does not return subjects, senders, recipients, body text, mailbox names, account identifiers, local paths, raw Mail database identifiers, approval tokens, or fingerprints outside the normal approval field.

## Apply

Apply recomputes the plan, requires `mail-apply:v1:<approval_fingerprint>`, requires `confirm_apply=true`, re-resolves the exact message identity, refuses stale message state, re-resolves the same-account Archive target, and refuses if that target changed since preview.

The Mail.app automation scopes to:

- The selected message's account id
- The selected message's current mailbox
- The selected message's RFC Message-ID from the exact local `.emlx` header
- The same account's Archive mailbox

The generated script moves exactly the selected message to Archive. It must not send, permanently delete, erase, empty, Trash, remove, or operate on multiple messages.

Read-back is mandatory. Success requires local Mail metadata read-back showing the message's mailbox reference equals the approved Archive mailbox reference. If Mail.app reports success but local read-back cannot confirm the Archive mailbox, apply returns a partial result with `mutation_applied:true` instead of claiming success.

## Refusals

- Raw Mail row IDs, AppleScript message IDs, local `.emlx` paths, mailbox names, mailbox URLs, account identifiers, and fabricated handles.
- Cross-account moves and arbitrary target mailboxes.
- Missing or ambiguous Archive mailbox resolution.
- Trash through this archive gate, or any permanent deletion.
- Send, reply, forward, drafts beyond the existing save-only draft gate, attachment mutation, broad export, and bulk operations.

## Synthetic Tests Required

- Plan success for `archive_message` with exact `mail:message:v2:` handle and same-account Archive mailbox.
- Plan refusal when Archive mailbox is missing or ambiguous.
- CLI wrapper coverage for `mail plan/apply --operation archive-message`.
- Apply success with mocked Mail.app move and local mailbox read-back.
- Missing confirmation and invalid approval-token refusals.
- Stale message state refusal before automation.
- Script safety assertions proving the Archive script moves exactly one selected message and never sends or permanently deletes.
- Runtime verifier coverage for archive plan/apply/read-back.

This archive release allowed exact-handle Mail draft creation, exact-message mark-read/mark-unread, exact-message flag/unflag, and exact-message archive. Later gates add exact-message move-to-Trash, send-message, reply-message, reply-all-message, forward-message, target-mailbox move, cross-account exact target support, and capped exact bulk triage. Mail reply outside the exact-message sender-only or reply-all gates, forward outside the exact-message no-source-attachments/no-non-body-parts gate, source attachment/non-body-part forwarding, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file gates, templates, HTML/rich-text mutation, query-result auto-apply, unbounded bulk mutation, and send outside the v1.43 send-message gate remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

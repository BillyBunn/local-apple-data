# V1.41 Mail Exact-Message Trash Write Design

Status: Apply-capable implementation.

## Scope

This document approves `trash_message` for one exact existing local Mail message selected by an opaque `mail:message:v2:` handle. It reuses the existing `mail plan` / `mail apply` CLI commands and `mail_plan_change` / `mail_apply_change` MCP tools.

The operation moves the selected message from its current mailbox to the selected message account's local Trash mailbox. It does not permanently delete mail and does not approve emptying Trash, erase/delete verbs, arbitrary mailbox moves, cross-account moves outside the exact target-mailbox gate, send, reply, forward, mailbox creation, mailbox rename, mailbox deletion, account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation, broad export, templates, HTML/rich-text mutation, or bulk operations.

## Preview

Planning resolves the exact message through the local Mail Envelope Index and the existing `.emlx` RFC Message-ID bridge. The plan refuses invalid handles, missing message identity, missing Trash mailbox, ambiguous Trash mailbox, and deleted messages.

The approval fingerprint binds:

- Operation: `trash_message`
- Exact opaque message handle
- Current read state
- Current flagged state
- Current mailbox reference
- Target mailbox kind: `trash`
- Target Trash mailbox reference
- Deterministic idempotency key

The preview does not call Mail.app and does not write Mail data. It does not return subjects, senders, recipients, body text, mailbox names, account identifiers, local paths, raw Mail database identifiers, approval tokens, or fingerprints outside the normal approval field.

## Apply

Apply recomputes the plan, requires `mail-apply:v1:<approval_fingerprint>`, requires `confirm_apply=true`, re-resolves the exact message identity, refuses stale message state, re-resolves the same-account Trash target, and refuses if that target changed since preview.

The Mail.app automation scopes to:

- The selected message's account id
- The selected message's current mailbox
- The selected message's RFC Message-ID from the exact local `.emlx` header
- The same account's Trash mailbox

The generated script moves exactly the selected message to Trash. It must not send, permanently delete, erase, empty, remove, or operate on multiple messages.

Read-back is mandatory. Success requires local Mail metadata read-back showing the message's mailbox reference equals the approved Trash mailbox reference. If Mail.app reports success but local read-back cannot confirm the Trash mailbox, apply returns a partial result with `mutation_applied:true` instead of claiming success.

## MCP Annotation

MCP tool annotations are static per tool. Because `mail_apply_change` can now run `trash_message`, it is annotated destructive and non-idempotent at the tool level even though create-draft, read-state, flag-state, and archive operations remain bounded and recoverable. The runtime synthetic smoke and MCP tests must prove this destructive annotation is present for `mail_apply_change`.

## Refusals

- Raw Mail row IDs, AppleScript message IDs, local `.emlx` paths, mailbox names, mailbox URLs, account identifiers, and fabricated handles.
- Cross-account moves and arbitrary target mailboxes.
- Missing or ambiguous Trash mailbox resolution.
- Permanent deletion, emptying Trash/Junk, and erase/delete/remove verbs.
- Send, reply, forward, drafts beyond the existing save-only draft gate, attachment mutation, broad export, and bulk operations.

## Synthetic Tests Required

- Plan success for `trash_message` with exact `mail:message:v2:` handle and same-account Trash mailbox.
- Plan refusal when Trash mailbox is missing or ambiguous.
- CLI wrapper coverage for `mail plan/apply --operation trash-message`.
- Apply success with mocked Mail.app move and local mailbox read-back.
- Apply success when Mail rekeys the moved row and read-back finds the same RFC Message-ID in the Trash mailbox.
- Missing confirmation and invalid approval-token refusals through the existing Mail apply gate.
- Stale message state refusal before automation.
- Script safety assertions proving the Trash script moves exactly one selected message and never sends or permanently deletes.
- Runtime synthetic smoke for `trash_message` plan/apply/read-back and `mail_apply_change` destructive annotation.

The current release allows exact-handle Mail draft creation, send-message, sender-only reply-message, reply-all-message, forward-message, exact-message or capped exact bulk mark-read/mark-unread, flag-message/unflag-message, archive-message, target-mailbox move including cross-account exact targets, and move-to-Trash. Mail reply outside the exact-message sender-only or reply-all gates, forward outside the exact-message forward-message gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, templates, HTML/rich-text mutation, query-result auto-apply, unbounded bulk operations, and send outside the v1.43 send-message gate remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

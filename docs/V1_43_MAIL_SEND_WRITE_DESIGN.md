# V1.43 Mail Send Write Design

Status: Apply-capable implementation.

## Scope

This document extends the approved Mail plan/apply surface with one irreversible external-send operation: send one new bounded plaintext Mail message through Mail.app automation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

No new mutating tool names are approved or exposed by this document.

This gate approves only `operation:send_message` / `send-message` with bounded plaintext `to`, optional `cc`/`bcc`, `subject`, and `body_text`. It does not approve reply, forward, arbitrary mailbox move, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachments, HTML/rich-text drafts, templates, private iCloud APIs, Gmail/IMAP/OAuth/network mail paths, or bulk operations.

## Preview

Mail send planning is non-mutating. It validates recipients, subject, and bounded plaintext body without calling Mail.app, reading Mail content, sending mail, saving drafts, or modifying local Mail data.

Preview returns `mutation_applied:false`, `apply_available:true`, a bounded body preview, `send_permitted:true`, `irreversible_external_send:true`, `retry_safe:false`, and an approval fingerprint bound to operation, recipients, normalized subject, normalized body SHA-256, target marker, and idempotency key.

## Apply

Apply recomputes the plan, requires the matching `mail-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply=true`.

The generated Mail.app automation creates one hidden outgoing message, sets the selected plaintext recipients, clears the message signature, then runs `send outboundMessage`. It must not call `save`, move messages, delete messages, permanently erase messages, empty mailboxes, mutate attachments, select sender accounts, or broad-select existing messages.

This send gate is not retry-safe. If Mail.app accepts the send but local Sent indexing is delayed, apply returns `status:"partial"`, `mutation_applied:true`, and `read_back_unavailable`; callers must not blindly retry.

Read-back uses the normal local Mail metadata/content path to find a matching Sent mailbox copy by exact subject and normalized plaintext body. Successful read-back returns selected metadata plus `sent_copy_confirmed:true`, normalized content SHA-256, content character count, and `body_returned:false`. Apply output must not echo the sent body text.

## MCP Annotation

MCP annotations are static per tool. `mail_plan_change` stays read-only. `mail_apply_change` remains annotated non-read-only, destructive, non-idempotent, and closed-world because the same static apply tool can send external mail and move one exact message to Trash.

## Refusals

- Missing, malformed, or broad recipient inputs.
- Missing or overlong subject.
- Overlong body.
- Message handle on send planning/apply.
- Missing confirmation or mismatched approval token.
- Mail.app automation timeout or error.
- Sent read-back unavailable, reported as partial after Mail.app accepts the send.
- Reply, forward, arbitrary mailbox move, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachments, HTML/rich-text drafts, templates, Gmail/IMAP/OAuth/network mail, private iCloud APIs, and bulk operations.

## Synthetic Tests Required

- Preview success for send-message with bounded recipients, subject, and body.
- Preview rejection for missing recipients, invalid recipients, malformed operation, and unexpected message handle.
- Apply rejection for missing confirmation and invalid approval token.
- Apply success proving Mail.app send automation, no draft save, no mailbox move/delete/empty/erase, no body echo, and Sent-copy read-back proof.
- Apply partial result when Mail.app accepts send but Sent read-back is unavailable.
- CLI tests for `mail plan/apply --operation send-message`.
- Runtime verifier coverage for send-message plan/apply success.
- MCP annotation tests proving `mail_apply_change` is destructive and non-idempotent.
- Release-readiness, write-design gate, redaction, and public-release coverage.

The current release allows Mail create-draft, send-message, reply-message, reply-all-message, forward-message, exact-message or capped exact bulk mark-read/mark-unread, flag-message/unflag-message, archive-message, move-message, and trash-message apply only. Mail reply outside the exact-message sender-only reply-message or reply-all-message gates, forward outside the exact-message forward with default source-part refusal-message gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file attachment gates, broad attachment export, HTML/rich-text draft mutation, templates, query-result auto-apply, and unbounded bulk mutation remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

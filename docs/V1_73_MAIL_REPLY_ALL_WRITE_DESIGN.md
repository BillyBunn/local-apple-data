# V1.73 Mail Reply-All Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

No new mutating tool names are approved or exposed by this document.

This gate approves only `operation:reply_all_message` / `reply-all-message`: send one bounded plaintext reply-all response to one exact selected Mail message. It does not approve direct recipient override, direct subject override, forward, redirect, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachments, HTML/rich-text drafts, templates, arbitrary mailbox move, permanent delete, empty Trash/Junk, mailbox/account management, private iCloud APIs, Gmail/IMAP/OAuth/network mail paths, or bulk operations.

## Source Review

Reviewed `/System/Applications/Mail.app/Contents/Resources/Mail.sdef` after `/usr/bin/sdef /System/Applications/Mail.app` was unavailable on this Command Line Tools-only host. The public Mail SDEF exposes the `reply` command with a boolean `reply to all` parameter and an outgoing-message result. This gate uses that public scripting surface only: `reply sourceMessage opening window false reply to all true`.

## Preview

Mail reply-all planning is non-mutating. Exact `mail:message:v2:` handle input is required. The planner resolves that handle through the local read-only Mail metadata path, recovers the source message's RFC Message-ID from the local `.emlx` file, validates a bounded plaintext reply body, and rejects direct To/Cc/Bcc recipients or direct subject input.

Preview returns `mutation_applied:false`, `apply_available:true`, `reply_all_permitted:true`, `reply_mode:"reply_all"`, `recipient_inputs_permitted:false`, `subject_input_permitted:false`, `irreversible_external_send:true`, `retry_safe:false`, a bounded body preview, and an approval fingerprint bound to operation, source message handle, current source state, reply mode, normalized reply body SHA-256, and idempotency key.

## Apply

Apply recomputes the plan, requires the matching `mail-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply=true`.

Apply re-resolves the source message immediately before sending and refuses if the source message state no longer matches the plan. The generated Mail.app automation scopes to `account id`, mailbox name, and RFC Message-ID, requires exactly one source match, runs `reply sourceMessage opening window false reply to all true`, sets the bounded plaintext body, clears the message signature, and sends the reply.

The generated automation must not call `save`, create direct recipients, forward, redirect, move messages, delete messages, permanently erase messages, empty mailboxes, mutate attachments, select sender accounts, or broad-select existing messages.

This reply-all gate is not retry-safe. If Mail.app accepts the reply-all but local Sent indexing is delayed, apply returns `status:"partial"`, `mutation_applied:true`, and `read_back_unavailable`; callers must not blindly retry.

Read-back uses the normal local Mail metadata/content path to find a matching Sent mailbox copy by derived reply subject and normalized plaintext body. Successful read-back returns selected metadata plus `sent_copy_confirmed:true`, `reply_copy_confirmed:true`, source message handle, `reply_mode:"reply_all"`, normalized content SHA-256, content character count, and `body_returned:false`. Apply output must not echo the reply body text.

## MCP Annotation

MCP annotations are static per tool. `mail_plan_change` stays read-only. `mail_apply_change` remains annotated non-read-only, destructive, non-idempotent, and closed-world because the same static apply tool can send external mail, send a reply, or move one exact message to Trash.

## Refusals

- Missing, malformed, or fabricated message handle.
- Missing local `.emlx` RFC Message-ID bridge.
- Missing or overlong reply body.
- Direct To/Cc/Bcc recipient input.
- Direct subject input.
- Missing confirmation or mismatched approval token.
- Stale source message state.
- Mail.app automation timeout or error.
- Sent read-back unavailable, reported as partial after Mail.app accepts the reply-all.
- Direct-recipient override, direct subject override, forward, redirect, arbitrary mailbox move, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachments, HTML/rich-text drafts, templates, Gmail/IMAP/OAuth/network mail, private iCloud APIs, and bulk operations.

## Synthetic Tests Required

- Preview success for reply-all-message with exact source handle, bounded plaintext body, reply-all mode, and irreversible-send metadata.
- Preview rejection for invalid source handle, missing body, direct recipients, direct subject, and unavailable RFC Message-ID bridge.
- Apply rejection for missing confirmation, invalid approval token, and stale source state.
- Apply success proving Mail.app reply automation, `reply to all true`, no direct recipient creation, no draft save, no mailbox move/delete/empty/erase, no body echo, and Sent-copy read-back proof.
- Apply partial result when Mail.app accepts the reply-all but Sent read-back is unavailable.
- CLI tests for `mail plan/apply --operation reply-all-message`.
- Runtime verifier coverage for reply-all-message plan/apply success.
- MCP annotation tests proving `mail_apply_change` remains destructive and non-idempotent.
- Release-readiness, write-design gate, redaction, and public-release coverage.

The current release allows Mail create-draft, send-message, reply-message, reply-all-message, forward-message, exact-message or capped exact bulk mark-read/mark-unread, flag-message/unflag-message, archive-message, move-message, and trash-message apply only. Mail reply outside the exact-message sender-only or reply-all gates, forward outside the exact-message forward with default source-part refusal-message gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file attachment gates, broad attachment export, HTML/rich-text draft mutation, templates, query-result auto-apply, and unbounded bulk mutation remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

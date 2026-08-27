# V1.50 Mail Forward Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

No new mutating tool names are approved or exposed by this document.

This gate approves only `operation:forward_message` / `forward-message`: send one bounded plaintext-prefaced forward of one exact selected Mail message to explicit plaintext recipients. It originally approved only no-source-attachments/no-non-body-parts forwarding; opt-in source attachment/non-body-part preservation later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`. It does not approve reply-all, redirect, direct subject override, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, HTML/rich-text drafts, templates, private iCloud APIs, Gmail/IMAP/OAuth/network mail paths, or bulk operations.

## Source Review

Local source review used `/System/Applications/Mail.app/Contents/Resources/Mail.sdef` because `sdef /System/Applications/Mail.app` is unavailable when Xcode is not installed and only Command Line Tools are active.

Observed Mail.app contract:

- Mail exposes a `forward` command with direct `message` parameter and optional `opening window` boolean.
- The `forward` command returns an `outgoing message`.
- Mail message objects respond to `forward`.
- Existing repo source review proved exact message addressing by account id, nested mailbox path, and RFC Message-ID recovered from the exact local `.emlx` file.

The syntax `tell application "Mail" to forward (first message of inbox) opening window false` compiled locally with `osacompile` and decompiled to `without opening window`.

## Preview

Mail forward planning is non-mutating. Exact `mail:message:v2:` handle input is required. The planner resolves that handle through the local read-only Mail metadata path, recovers the source message's RFC Message-ID from the local `.emlx` file, binds a source-content state fingerprint without returning source content, validates explicit To/Cc/Bcc recipients, validates a non-empty bounded plaintext `body_text` used as prepend text, rejects direct subject input, and by default rejects source messages with MIME attachments or non-body MIME parts that Mail may carry into the generated forward. `include_source_attachments:true` is governed by `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`.

Default preview returns `mutation_applied:false`, `apply_available:true`, `recipient_inputs_permitted:true`, `subject_input_permitted:false`, `source_body_included:true`, `source_attachments_permitted:false`, `source_non_text_parts_permitted:false`, `source_non_body_parts_permitted:false`, `irreversible_external_send:true`, `retry_safe:false`, a bounded body preview, and an approval fingerprint bound to operation, source message handle, current source state, source no-attachment/non-body-part state, source-content state, recipients, derived forward subject, normalized prepend body SHA-256, and idempotency key.

## Apply

Apply recomputes the plan, requires the matching `mail-apply:v1:<approval_fingerprint>` token, and requires `confirm_apply=true`.

Apply re-resolves the source message immediately before sending and refuses if the source message state, source attachment/non-body-part state, or source-content state no longer matches the plan. The generated Mail.app automation scopes to `account id`, nested mailbox path, and RFC Message-ID, requires exactly one source match, runs `forward sourceMessage opening window false`, clears the message signature, sets the deterministic derived subject, prepends the bounded plaintext body to the generated forward content, creates the explicit To/Cc/Bcc recipients, and sends the forward.

The generated automation must not call `save`, create a new unrelated outgoing message, reply, reply all, redirect, move messages, delete messages, permanently erase messages, empty mailboxes, select sender accounts, or broad-select existing messages. Caller-selected local attachment mutation is governed by `docs/V1_76_MAIL_OUTBOUND_ATTACHMENT_WRITE_DESIGN.md`; opt-in source attachment-like part preservation is governed by `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`.

This forward gate is not retry-safe. If Mail.app accepts the forward but local Sent indexing is delayed, apply returns `status:"partial"`, `mutation_applied:true`, and `read_back_unavailable`; callers must not blindly retry.

Read-back takes a pre-send Sent snapshot, then uses the normal local Mail metadata/content path to find a new matching Sent mailbox copy by derived forward subject and normalized prepend body prefix while excluding pre-existing Sent handles. Successful read-back returns selected metadata plus `sent_copy_confirmed:true`, `forward_copy_confirmed:true`, source message handle, `forward_mode:"exact_source_message"`, `source_body_included:true`, `source_attachments_permitted:false`, `source_non_text_parts_permitted:false`, `source_non_body_parts_permitted:false`, source-content state, prepended-body SHA-256, prepended-body character count, and `body_returned:false`. Apply output must not echo the forward body text or source message content.

## MCP Annotation

MCP annotations are static per tool. `mail_plan_change` stays read-only. `mail_apply_change` remains annotated non-read-only, destructive, non-idempotent, and closed-world because the same static apply tool can send external mail, send a reply or forward, and move one exact message to Trash.

## Refusals

- Missing, malformed, or fabricated message handle.
- Missing local `.emlx` RFC Message-ID bridge.
- Missing To recipient, malformed recipient, missing body, or overlong body.
- Direct subject input.
- Source message with any attachment or non-body MIME part unless `include_source_attachments:true` is used under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`.
- Source attachment/non-body-part state unavailable.
- Source content state unavailable.
- Missing confirmation or mismatched approval token.
- Stale source message state.
- Stale source attachment/non-body-part state.
- Stale source content state.
- Mail.app automation timeout or error.
- Sent read-back unavailable, reported as partial after Mail.app accepts the forward.
- Reply-all outside the separate v1.73 gate, redirect, direct subject override, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, HTML/rich-text drafts, templates, Gmail/IMAP/OAuth/network mail, private iCloud APIs, and bulk operations.

## Synthetic Tests Required

- Preview success for forward-message with exact source handle, explicit recipient, bounded plaintext prepend body, zero source attachments/non-body MIME parts, and irreversible-send metadata.
- Preview rejection for invalid source handle, missing body, direct subject, missing recipient, source attachments, and inline non-body MIME parts.
- Apply rejection for missing confirmation, invalid approval token, stale source state, stale source attachment/non-body-part state, and source content drift.
- Apply success proving Mail.app forward automation, exact source match including nested mailbox paths, explicit recipients, no unrelated outgoing-message create, no reply, no draft save, no mailbox move/delete/empty/erase, no body echo, no attachment forwarding, and Sent-copy read-back proof.
- Apply partial proof that a stale pre-existing Sent match does not confirm a new forward.
- Apply partial result when Mail.app accepts the forward but Sent read-back is unavailable.
- CLI tests for `mail plan/apply --operation forward-message`.
- Runtime verifier coverage for forward-message plan/apply success.
- MCP annotation tests proving `mail_apply_change` remains destructive and non-idempotent.
- Release-readiness, write-design gate, redaction, and public-release coverage.

The current release allows Mail create-draft, send-message, reply-message, reply-all-message, forward-message including optional source attachment-like part preservation through `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`, exact-message or capped exact bulk mark-read/mark-unread, flag-message/unflag-message, archive-message, move-message, and trash-message apply only. Mail reply outside the exact-message sender-only or reply-all gates, cross-account move outside the exact target-mailbox gate, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file attachment gates, broad attachment export, HTML/rich-text draft mutation, templates, query-result auto-apply, and unbounded bulk mutation remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

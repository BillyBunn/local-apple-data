# v1.37 Mail Flag Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

This document approves exactly two non-destructive Mail status operations on one exact existing message:
`flag_message` and `unflag_message`. Archive is governed separately by
`docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md`; no send, reply, forward, arbitrary move, delete,
mailbox/account management, attachment mutation, broad read/flag status mutation, bulk flagging, or arbitrary
flag/color selection is approved by this document.

## Scope

Allowed:

- `local-apple-data mail plan --operation flag-message`
- `local-apple-data mail plan --operation unflag-message`
- `mail_plan_change(operation="flag_message")`
- `mail_plan_change(operation="unflag_message")`
- `local-apple-data mail apply --operation flag-message`
- `local-apple-data mail apply --operation unflag-message`
- `mail_apply_change(operation="flag_message")`
- `mail_apply_change(operation="unflag_message")`

Required inputs:

- Exact opaque `mail:message:v2:` handle from the Mail metadata flow.
- Matching `mail-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply:true`.

Out of scope:

- Raw Mail row IDs, mailbox URLs, local `.emlx` paths, account IDs, or fabricated handles.
- Flagging by search query, mailbox, sender, date range, thread, conversation, or bulk filter.
- Flag color/category selection.
- Junk/not-junk classification.
- Send, reply, forward, arbitrary move, delete, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, or attachment mutation.
- Gmail connector, IMAP, OAuth, iCloud.com, browser/keychain paths, private iCloud APIs, network mail services, or external connectors.

## Safety Contract

Plan is non-mutating. It resolves the exact handle through the local Mail metadata path, recovers the RFC
Message-ID from the selected local `.emlx` header, reads the current Mail `read` and `flagged` state, returns
`mutation_applied:false`, and creates an approval fingerprint over the exact operation, handle, expected state,
and target flag state.

Apply recomputes the plan, requires the matching approval token, requires explicit confirmation, resolves the
same exact handle again, and refuses stale message state before automation. The expected-state fingerprint binds
the RFC Message-ID, mailbox reference, current read state, and current flagged state so apply refuses if a human
or another agent changed the message between plan and apply.

Automation may only set `flagged status` on the exact Mail.app message selected by account id, mailbox name, and
RFC Message-ID. The generated AppleScript for this flag gate must never send, move, delete, archive, empty
Trash, erase, or mutate attachments.

Read-back is mandatory. A successful apply must re-read the message through the local Mail metadata adapter and
confirm `flagged:true` for `flag_message` or `flagged:false` for `unflag_message`.

## MCP Annotation

`mail_plan_change` stays read-only. At this v1.37 gate, `mail_apply_change` was non-read-only,
non-destructive, idempotent, and closed-world because this gate only changed one reversible status bit. The
current combined `mail_apply_change` tool is statically destructive and non-idempotent once the v1.41
`trash_message` operation is exposed on the same MCP tool.

## Idempotency

If the selected message is already in the requested flagged state, apply returns `already_applied` with
`mutation_applied:false` and does not run Mail.app automation. There is no durable personal-content operation
ledger.

## Synthetic Tests Required

Required tests:

- Plan success for `flag_message` and `unflag_message` with exact handles.
- Public `plan_mail_change` and `apply_mail_change` dispatch for hyphenated and underscored operations.
- Apply success using mocked Mail.app automation and synthetic Mail read-back.
- Already-satisfied apply skips automation.
- Missing confirmation, invalid approval token, invalid handle, missing message, and missing RFC identity refusals.
- AppleScript safety tests proving the flag script contains `flagged status` and none of the forbidden move,
  send, delete, erase, empty, trash, or remove terms.
- CLI coverage for `mail plan/apply --operation flag-message`.
- Runtime synthetic smoke for `flag_message` without touching live Mail.

## Current Release Gate

The current release allows exact-handle Mail draft creation, send-message, sender-only reply-message, reply-all-message, forward-message, exact-message and capped exact bulk mark-read/mark-unread, flag/unflag, archive, target-mailbox move including cross-account exact targets, and move-to-Trash through `mail plan` / `mail apply` and `mail_plan_change` / `mail_apply_change`. Mail reply outside the exact-message sender-only or reply-all gates, forward outside the exact-message forward-message gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, cross-account move outside the exact target-mailbox gate, permanent delete, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file attachment gates, broad Mail attachment export, HTML/rich-text draft mutation, templates, query-result auto-apply, unbounded bulk Mail mutation, send outside the v1.43 send-message gate, and flag operations outside `flag_message` / `unflag_message` remain blocked.

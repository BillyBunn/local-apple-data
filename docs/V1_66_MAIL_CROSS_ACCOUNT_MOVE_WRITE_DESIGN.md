# V1.66 Mail Exact Cross-Account Move Write Design

Status: Apply-capable implementation.

## Scope

This document extends `move_message` for one exact existing local Mail message selected by an opaque `mail:message:v2:` handle and one exact existing target mailbox selected by an opaque `mail:mailbox:v1:` handle when the target mailbox is in a different Mail account. It reuses `local-apple-data mail plan`, `local-apple-data mail apply`, `mail_plan_change`, and `mail_apply_change`; it adds no new mutating tool names.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Mailbox selection tools: `local-apple-data mail mailboxes`, `local-apple-data mail mailbox`, `mail_search_mailboxes`, and `mail_get_mailbox`.

The operation moves exactly one selected message to exactly one selected non-Trash/Junk-class target mailbox. It approves cross-account target mailbox moves only through this exact-handle plan/apply gate. It does not approve move-to-Trash through `move_message`, Junk/Spam moves, permanent delete, empty Trash/Junk, send, reply, forward, mailbox creation, mailbox rename, mailbox deletion, account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation, broad export, templates, HTML/rich-text mutation, or bulk operations.

## Source Review

Source review uses the installed local Mail scripting resources because `/usr/bin/sdef /System/Applications/Mail.app` requires full Xcode on this machine. The reviewed files are `/System/Applications/Mail.app/Contents/Resources/Mail.sdef` and `/System/Library/ScriptingDefinitions/CocoaStandard.sdef`.

Observed Mail.app contract:

- Mail exposes a `move` command with direct object parameter and `to` location parameter.
- Mail message objects expose `message id`, `read status`, and `flagged status`.
- Mail account objects contain mailbox elements and expose an `id`.
- Mail mailbox objects contain nested mailboxes and messages.

The implementation uses the existing local `.emlx` RFC Message-ID bridge, the selected message's source account and mailbox, and the selected target mailbox's own account and mailbox. It does not use Gmail, IMAP, OAuth, iCloud.com, browser sessions, Keychain scraping, private APIs, network mail services, raw row IDs, local paths, or raw account identifiers as user inputs.

## Preview

Planning resolves the exact message through the local Mail Envelope Index and the existing `.emlx` RFC Message-ID bridge. It resolves the target mailbox through the local Mail mailbox table using the opaque `mail:mailbox:v1:` handle.

Mailbox target metadata may include an opaque `account_ref` for account grouping. Broad Mail message search/get metadata must not return account refs or raw account identifiers. Cross-account plans expose `target_account_relation:"cross_account"`, `source_account_ref`, and `target_account_ref` as opaque refs only. It must not return raw account identifiers.

The approval fingerprint binds:

- Operation: `move_message`
- Exact opaque message handle
- Current read state
- Current flagged state
- Current mailbox reference
- Target mailbox kind: `mailbox`
- Exact target mailbox handle
- Target mailbox reference
- Target account relation
- Deterministic idempotency key

The plan refuses invalid handles, missing message identity, missing mailbox identity, Trash/Deleted/Bin/Junk/Spam targets, stale or deleted messages, and target mailbox handles that no longer resolve. The preview does not call Mail.app and does not write Mail data.

## Apply

Apply recomputes the plan, requires `mail-apply:v1:<approval_fingerprint>`, requires `confirm_apply=true`, re-resolves the exact message identity, refuses stale message state, re-resolves the exact target mailbox, and refuses a stale mailbox target if the target changed since preview.

The Mail.app automation scopes to:

- The selected message's source account id
- The selected message's current mailbox
- The selected message's RFC Message-ID from the exact local `.emlx` header
- The selected target mailbox's target account id
- The selected target mailbox path

The generated script moves exactly the selected message to the selected target mailbox. It never sends or permanently deletes; it must not erase, empty, Trash, remove, call send, or operate on multiple messages.

Read-back is mandatory. Success requires local Mail metadata read-back showing the message's mailbox reference equals the approved target mailbox reference. If Mail.app reports success but local read-back cannot confirm the target mailbox, apply returns a partial result with `mutation_applied:true` instead of claiming success.

## Refusals

- Raw Mail row IDs, AppleScript message IDs, local `.emlx` paths, mailbox names as target input, mailbox URLs, raw account identifiers, and fabricated handles.
- Trash, Deleted, Bin, Junk, and Spam target mailboxes through `move_message`; use `trash_message` for same-account reversible Trash moves.
- Permanent deletion, emptying Trash/Junk, and erase/delete/remove verbs.
- Send, reply, forward, drafts beyond existing gates, attachment mutation, broad export, and bulk operations.
- Mailbox/account management, mailbox creation, mailbox rename, mailbox deletion, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, templates, or HTML/rich-text mutation.

## Synthetic Tests Required

- Mailbox target metadata search/detail return opaque `mail:mailbox:v1:` handles and opaque `account_ref`, not raw account identifiers; broad Mail message metadata omits account refs.
- Plan success for `move_message` with exact `mail:message:v2:` and cross-account `mail:mailbox:v1:` handles.
- Plan output shows `target_account_relation:"cross_account"`, distinct opaque source/target account refs, and no raw target account identifier.
- Apply success with mocked Mail.app cross-account move, source account scoping, target account scoping, and local mailbox read-back.
- Stale mailbox target refusal before automation.
- Trash/Junk-class target refusal.
- Script safety assertions proving the move script moves exactly one selected message and never sends or permanently deletes.
- Runtime verifier coverage for cross-account move plan/apply/read-back and raw account absence.

This release allows exact-handle Mail draft creation, send-message, sender-only reply-message, reply-all-message, forward-message, exact-message or capped exact bulk mark-read/mark-unread, flag/unflag, archive, target-mailbox move including cross-account exact targets, and move-to-Trash. Mail reply outside the approved exact-message sender-only or reply-all gates, forward outside the exact-message forward-message gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation outside approved draft/send/reply/reply-all/forward local-file attachment gates, broad attachment export, HTML/rich-text draft mutation, templates, query-result auto-apply, and unbounded bulk mutation remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

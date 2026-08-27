# V1.46 Mail Exact-Message Target-Mailbox Move Write Design

Status: Apply-capable implementation. Current cross-account extension is governed by `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`.

## Scope

This document approves `move_message` for one exact existing local Mail message selected by an opaque `mail:message:v2:` handle and one exact existing target mailbox selected by an opaque `mail:mailbox:v1:` handle. It reuses the existing `mail plan` / `mail apply` CLI commands and `mail_plan_change` / `mail_apply_change` MCP tools. The original v1.46 implementation was same-account only; v1.66 extends the same exact target-mailbox gate to cross-account targets.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Mailbox selection tools: `local-apple-data mail mailboxes`, `local-apple-data mail mailbox`, `mail_search_mailboxes`, and `mail_get_mailbox`.

The operation moves the selected message from its current mailbox to one exact selected target mailbox. It does not approve move-to-Trash through this general move gate, Junk/Spam moves, permanent delete, empty Trash/Junk, send, reply, forward, mailbox creation, mailbox rename, mailbox deletion, account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, attachment mutation, broad export, templates, HTML/rich-text mutation, or bulk operations. Exact-message Archive and Trash remain governed by `docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md` and `docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md`; cross-account target proof is governed by `docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md`.

## Source Review

Source review used the local bundled Mail scripting definition because `sdef /System/Applications/Mail.app` was unavailable under Command Line Tools-only Xcode. The reviewed files were `/System/Applications/Mail.app/Contents/Resources/Mail.sdef` and `/System/Library/ScriptingDefinitions/CocoaStandard.sdef`.

Observed Mail.app contract:

- Mail exposes a `move` command with direct object parameter and `to` location parameter.
- Mail message objects expose `mailbox`, `read status`, `flagged status`, and `message id`.
- Mail accounts contain mailbox elements and expose `id`.
- Mail mailboxes contain nested mailboxes, messages, a `name`, an `account`, and a `container`.

The implementation uses the existing local `.emlx` RFC Message-ID bridge, account-scoped source mailbox, and account-scoped target mailbox. It does not use Gmail, IMAP, OAuth, iCloud.com, browser sessions, Keychain scraping, private APIs, network mail services, raw row IDs, local paths, or raw account identifiers as user inputs.

## Preview

Planning resolves the exact message through the local Mail Envelope Index and the existing `.emlx` RFC Message-ID bridge. It resolves the exact target mailbox through the local Mail mailbox metadata table using the opaque `mail:mailbox:v1:` handle.

The plan refuses invalid handles, missing message identity, missing mailbox identity, Trash/Deleted/Bin/Junk/Spam targets, stale or deleted messages, and any target mailbox handle that does not resolve in the current local store.

The approval fingerprint binds:

- Operation: `move_message`
- Exact opaque message handle
- Current read state
- Current flagged state
- Current mailbox reference
- Target mailbox kind: `mailbox`
- Exact target mailbox handle
- Target mailbox reference
- Deterministic idempotency key

The preview does not call Mail.app and does not write Mail data. It does not return subjects, senders, recipients, body text, local paths, raw Mail database identifiers, raw mailbox URLs, raw account identifiers, approval tokens, or fingerprints outside the normal approval field.

## Apply

Apply recomputes the plan, requires `mail-apply:v1:<approval_fingerprint>`, requires `confirm_apply=true`, re-resolves the exact message identity, refuses stale message state, re-resolves the exact target mailbox, and refuses a stale mailbox target if the target changed since preview.

The Mail.app automation scopes to:

- The selected message's account id
- The selected message's current mailbox
- The selected message's RFC Message-ID from the exact local `.emlx` header
- The selected exact target mailbox

The generated script moves exactly the selected message to the target mailbox. It never sends or permanently deletes; it must not erase, empty, Trash, remove, call send, or operate on multiple messages.

Read-back is mandatory. Success requires local Mail metadata read-back showing the message's mailbox reference equals the approved target mailbox reference. If Mail.app reports success but local read-back cannot confirm the target mailbox, apply returns a partial result with `mutation_applied:true` instead of claiming success.

## Refusals

- Raw Mail row IDs, AppleScript message IDs, local `.emlx` paths, mailbox names, mailbox URLs, account identifiers, and fabricated handles.
- Trash, Deleted, Bin, Junk, and Spam target mailboxes through `move_message`; use `trash_message` for same-account reversible Trash moves.
- Permanent deletion, emptying Trash/Junk, and erase/delete/remove verbs.
- Send, reply, forward, drafts beyond the existing save-only draft gate, attachment mutation, broad export, and bulk operations.
- Mailbox/account management, mailbox creation, mailbox rename, mailbox deletion, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, templates, or HTML/rich-text mutation.

## Synthetic Tests Required

- Mailbox metadata search and exact get return only opaque `mail:mailbox:v1:` handles and bounded metadata.
- Plan success for `move_message` with exact `mail:message:v2:` and exact `mail:mailbox:v1:` handles.
- Plan refusal when the target mailbox handle is missing, malformed, or points to Trash/Junk-like mailboxes.
- CLI wrapper coverage for `mail mailboxes`, `mail mailbox`, `mail plan/apply --operation move-message`, and `--target-mailbox-handle`.
- MCP wrapper coverage for `mail_search_mailboxes`, `mail_get_mailbox`, `mail_plan_change`, and `mail_apply_change`.
- Apply success with mocked Mail.app move and local mailbox read-back.
- Missing confirmation and invalid approval-token refusals through the existing Mail apply gate.
- Stale message state refusal before automation.
- Stale mailbox target refusal before automation.
- Script safety assertions proving the move script moves exactly one selected message and never sends or permanently deletes.
- Runtime verifier coverage for mailbox search, move-message plan/apply/read-back, and unchanged destructive annotation on `mail_apply_change`.

This release allows exact-handle Mail draft creation, send-message, sender-only reply-message, reply-all-message, forward-message, exact-message or capped exact bulk mark-read/mark-unread, flag-message/unflag-message, archive-message, target-mailbox move including cross-account exact targets, and move-to-Trash. Mail reply outside the approved exact-message sender-only or reply-all gates, forward outside the exact-message forward with default source-part refusal-message gate, source attachment/non-body-part forwarding outside explicit `include_source_attachments`, permanent delete, empty Trash/Junk, mailbox/account management, sender selection outside the approved draft/send/reply/reply-all/forward sender gate, broad attachment export, HTML/rich-text draft mutation, templates, query-result auto-apply, and unbounded bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

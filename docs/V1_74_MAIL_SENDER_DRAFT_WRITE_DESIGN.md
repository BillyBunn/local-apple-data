# v1.74 Mail Sender Draft Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.
Planning tools: `local-apple-data mail plan` and `mail_plan_change`.
Sender selection tools: `local-apple-data mail senders`, `local-apple-data mail sender`, `mail_search_senders`, and `mail_get_sender`.

This gate approves optional exact sender selection for `operation:create_draft` / `create-draft` only. It does not approve sender selection for `send_message`, `reply_message`, `reply_all_message`, `forward_message`, triage operations, account configuration changes, SMTP delivery-account mutation, mailbox/account management, Gmail/IMAP/OAuth/network mail, iCloud.com, browser/keychain access, private APIs, attachment mutation, HTML/rich-text drafts, templates, bulk operations, or live mutation without the normal matching approval token plus explicit confirmation.

## Public Source Review

The reviewed local public source is `/System/Applications/Mail.app/Contents/Resources/Mail.sdef`.

- `outgoing message` exposes writable property `sender` with type `text`.
- `account` exposes `name`, read-only `id`, `enabled`, `email addresses`, `full name`, and `delivery account`.
- `smtp server` is account configuration and is not used for per-message selection.

The implementation sets only `sender of draftMessage` on the newly created outgoing draft before `save draftMessage`. It never mutates `delivery account`, SMTP server settings, account settings, mailbox state, existing messages, or credentials.

## Read-Only Sender Selection

`mail_search_senders` and `local-apple-data mail senders` enumerate configured enabled Mail accounts through public Mail.app scripting, returning metadata only:

- opaque `mail:sender:v1:` handle
- opaque `sender_ref`
- opaque `account_ref`
- bounded masked account label
- masked `email_preview`
- `selection_supported`
- `raw_identifier_returned:false`
- `account_identifier_returned:false`
- `full_email_returned:false`
- `sender_string_returned:false`

Sender search matching is limited to returned-safe masked account labels and masked email previews; hidden full names and full sender email strings must not be searchable side channels. `mail_get_sender` and `local-apple-data mail sender` return the same metadata for one exact `mail:sender:v1:` handle. Full email addresses, raw Mail account IDs, raw SMTP IDs, delivery-account identifiers, passwords, server names, and credentials must never be returned.

Sender handles are HMAC opaque and resolve by re-enumerating current configured sender identities. Raw sender emails, raw Mail account IDs, raw SMTP IDs, mailbox handles, and opaque `account_ref` values are refused as sender selectors.

## Plan Contract

`mail plan --operation create-draft --sender-handle <mail:sender:v1:...>` and `mail_plan_change(operation="create_draft", sender_handle=...)`:

- validate the sender handle through current public Mail.app account metadata
- refuse ambiguous duplicate configured sender addresses with `ambiguous_sender_address`
- refuse stale/missing handles with `sender_not_found`
- bind `sender_handle`, `sender_ref`, `account_ref`, masked preview metadata, recipients, subject, body hash, and idempotency key into the approval fingerprint
- return `mutation_applied:false` and `apply_available:true`
- return `retry_safe:false` for sender-selected drafts because automated sender read-back is required and matching-body idempotency cannot prove the selected sender
- return no full email address, raw account identifier, SMTP identifier, delivery account, or sender string

`sender_handle` on `send_message`, `reply_message`, `reply_all_message`, `forward_message`, or any triage operation returns `unexpected_sender_handle`.

## Apply Contract

`mail apply --operation create-draft --sender-handle <mail:sender:v1:...>` and `mail_apply_change(operation="create_draft", sender_handle=...)`:

- recompute the plan and require the exact `mail-apply:v1:<approval_fingerprint>` token
- require `confirm_apply:true`
- re-resolve the sender handle immediately before writing
- refuse stale sender state with `stale_sender_state`
- create one hidden plaintext outgoing draft
- set `message signature` to `missing value`
- set `sender of draftMessage` to the selected sender text
- run `save draftMessage`
- return `sender_selection_confirmed:true` only when Mail returns a sender string containing the selected sender address
- return `partial` with `sender_read_back_unavailable` if the draft was saved but sender read-back did not confirm the selected sender
- take a pre-apply draft handle snapshot and require exactly one new matching-body draft after excluding those handles from read-back so an older or concurrent same-subject/same-body draft cannot be annotated as the newly created sender-selected draft
- return `partial` with `ambiguous_draft_read_back` if multiple new matching drafts appear after the snapshot or if exact-subject Draft candidates exceed the bounded attribution limit
- disable matching-body draft idempotency for explicit sender selection because the local Mail database read-back does not prove draft sender identity

Apply output may include `sender_ref` and `sender_selection_confirmed`; it must not include the full sender email address, raw account ID, raw SMTP ID, delivery-account identifier, AppleScript exception text, local Mail paths, body text beyond existing approved read-back behavior, or credentials.

## Synthetic Tests Required

- Sender search/get returns opaque handles, masked email previews, and no full emails or raw account IDs.
- Broad sender search is rejected.
- Create-draft plan binds `sender_handle` and only masked sender metadata.
- Create-draft plan returns `retry_safe:false` when a sender is selected.
- Non-draft operations reject `sender_handle` with `unexpected_sender_handle`.
- Duplicate configured sender addresses are refused with `ambiguous_sender_address`.
- Create-draft apply sets `sender of draftMessage` before `save draftMessage`, never sends, and confirms `sender_selection_confirmed:true`.
- Sender search does not match hidden full sender email strings or hidden full-name values.
- Create-draft apply excludes preexisting same-subject/same-body Draft handles and refuses multiple new matching Draft handles before accepting read-back.
- Create-draft apply returns `partial` with `ambiguous_draft_read_back` when multiple new matching drafts appear after the pre-apply snapshot or when exact-subject candidate saturation prevents unique attribution.
- Apply returns `partial` with `sender_read_back_unavailable` when Mail does not confirm the selected sender.
- Runtime verifier covers sender search/get, draft plan/apply, send-operation refusal, MCP tool exposure, and full-email absence.

## Remaining Blocked Mail Work

Sender selection for `send_message`, `reply_message`, `reply_all_message`, and `forward_message` remains blocked until a follow-up gate proves durable sender read-back for irreversible sends. Outbound local-file attachments later landed under `docs/V1_76_MAIL_OUTBOUND_ATTACHMENT_WRITE_DESIGN.md`, capped exact bulk triage later landed under `docs/V1_78_MAIL_BULK_TRIAGE_WRITE_DESIGN.md`, and opt-in source attachment-like part forwarding later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`. Source attachment/non-body-part forwarding outside explicit `include_source_attachments`, templates/signatures, mailbox/account management, permanent delete, empty Trash/Junk, query-result auto-apply, unbounded bulk mutation, HTML/rich-text mutation, Gmail/IMAP/OAuth/network mail paths, iCloud.com, browser/keychain access, and private API paths remain blocked.

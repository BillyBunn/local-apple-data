# V1.82 Mail Outbound Sender Selection Write Design

Status: Source apply-capable implementation. Live synthetic sender-selected send proof is verified.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.
Planning tools: `local-apple-data mail plan` and `mail_plan_change`.
Sender selection tools: `local-apple-data mail senders`, `local-apple-data mail sender`, `mail_search_senders`, and `mail_get_sender`.

This gate extends the v1.74 exact sender-selection contract from `create_draft` to `send_message`, `reply_message`, `reply_all_message`, and `forward_message`. It does not approve sender selection for triage operations, account configuration changes, SMTP delivery-account mutation, mailbox/account management, permanent delete, empty Trash/Junk, Gmail/IMAP/OAuth/network mail, iCloud.com, browser/keychain access, private APIs, templates/signatures beyond signature clearing, HTML/rich-text messages, query-result auto-apply, unbounded bulk mutation, or live mutation without the normal matching approval token plus explicit confirmation. Later gates add signatures/templates/query-result planning and synthetic-only mailbox/cleanup without changing this sender-selection gate.

## Source Review

The reviewed local public source is `/System/Applications/Mail.app/Contents/Resources/Mail.sdef`.

- `outgoing message` exposes writable property `sender` with type `text`.
- `outgoing message` exposes writable `message signature`, `content`, `subject`, and recipient collections.
- `send`, `reply`, and `forward` are public Mail scripting commands that operate on outgoing messages.

The implementation sets only `sender` on the new outgoing message produced by create-draft, send, reply, reply-all, or forward automation. It never mutates `delivery account`, SMTP server settings, account settings, mailbox state, existing messages, or credentials.

## Plan Contract

`mail plan` / `mail_plan_change` accepts one exact `mail:sender:v1:` handle for `create_draft`, `send_message`, `reply_message`, `reply_all_message`, and `forward_message`.

- Sender handles resolve by re-enumerating current configured enabled Mail accounts through public Mail.app scripting.
- Missing, stale, fabricated, raw-email, raw-account, or duplicate-address sender handles are refused before approval metadata is issued.
- Plans bind `sender_handle`, `sender_ref`, `account_ref`, masked preview metadata, operation inputs, current source-message state when applicable, and idempotency key into the approval fingerprint.
- Plans return `sender_selection.mode:"exact_sender_handle"`, opaque `sender_ref`, opaque `account_ref`, masked `email_preview`, `full_email_returned:false`, and `sender_string_returned:false`.
- Plans for send/reply/reply-all/forward remain irreversible and return `retry_safe:false`.
- Triage operations still reject `sender_handle` with `unexpected_sender_handle`.

## Apply Contract

Apply recomputes the plan, requires the exact `mail-apply:v1:<approval_fingerprint>` token, requires `confirm_apply:true`, and re-resolves the sender handle immediately before Mail automation.

- Stale sender state is refused with `stale_sender_state` before mutation.
- Draft apply sets `sender of draftMessage` before `save draftMessage`.
- Send apply sets `sender of outboundMessage` before `send outboundMessage`.
- Reply and reply-all apply set `sender of replyMessage` before `send replyMessage`.
- Forward apply sets `sender of forwardMessage` before `send forwardMessage`.
- Apply clears `message signature` through the existing signature-clearing guard.
- Apply returns `sender_selection_confirmed:true` only when Mail automation reports the selected sender address before save/send returns.
- Apply returns `partial` with `sender_read_back_unavailable` if Mail accepted the draft/send/reply/reply-all/forward but sender read-back did not confirm the selected sender.
- Send/reply/forward sent-copy read-back waits for bounded local Mail sync, accepts public Sent mailboxes and Gmail-style `All Mail` sent copies, and tolerates Mail's local quoted-line rendering while still returning only hash/count proof.
- Apply output may include `sender_ref`, `sender_selection_confirmed`, `full_email_returned:false`, and `sender_string_returned:false`; it must not include the full sender email address, raw account ID, SMTP ID, delivery-account identifier, AppleScript exception text, local Mail paths, sent body text, source body text, or credentials.

## Synthetic Tests Required

- Send, reply, reply-all, and forward plans accept exact `mail:sender:v1:` handles and return only masked sender metadata.
- Triage still rejects `sender_handle`.
- Apply re-resolves sender handles and refuses stale sender state.
- Send, reply, reply-all, and forward AppleScript set `sender` before `send`.
- Apply confirms selected sender read-back for send, reply, and forward without returning the full email address.
- Runtime verifier proves synthetic sender-selected send apply through a mocked Mail runner.
- Live synthetic proof on 2026-06-25 sent `LAD-TEST-*` messages from iCloud to Google and Google to iCloud through public Mail.app automation with exact `mail:sender:v1:` handles. The final redacted proof artifact is `/tmp/local-apple-data-live-mail-v184-sender-send-proof-final.json` and shows `apply_status:"ok"`, `mutation_applied:true`, `sent_copy_confirmed:true`, `sender_selection_confirmed:true`, `full_email_returned:false`, `sender_string_returned:false`, and `body_returned:false` for both directions.
- CLI and MCP forwarding of `sender_handle` continues to pass exact inputs through plan/apply.
- Release-readiness, write-design gate, redaction, public-release, runtime, cross-agent, and artifact-hygiene checks cover this gate.

## Remaining Blocked Mail Work

Real/non-synthetic mailbox/account management, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, query-result auto-apply, unbounded bulk mutation, HTML/rich-text mutation, background indexing, Gmail/IMAP/OAuth/network mail paths, iCloud.com, browser/keychain access, and private API paths remain blocked until separate gates land. Signatures/templates/query-result planning later landed under `docs/V1_83_MAIL_SIGNATURE_TEMPLATE_QUERY_TRIAGE_DESIGN.md`; synthetic mailbox/cleanup later landed under `docs/V1_84_MAIL_SYNTHETIC_MAILBOX_CLEANUP_WRITE_DESIGN.md`.

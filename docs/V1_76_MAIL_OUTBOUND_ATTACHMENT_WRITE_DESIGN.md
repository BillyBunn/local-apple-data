# v1.76 Mail Outbound Attachment Write Design

Status: Source apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.
Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

This gate extends the v1.75 local-file attachment rules from saved drafts to `send_message`, `reply_message`, `reply_all_message`, and `forward_message`. It does not approve source-message attachment forwarding, non-body-part forwarding, broad attachment mutation, mailbox/account management, permanent delete, templates, HTML/rich-text messages, Gmail/IMAP/OAuth/network mail, iCloud.com, browser/keychain access, private APIs, or live mutation without a matching approval token plus explicit confirmation. Opt-in source-message attachment forwarding later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`; outbound exact sender selection later landed under `docs/V1_82_MAIL_OUTBOUND_SENDER_SELECTION_WRITE_DESIGN.md`; signatures/templates/query-result planning later landed under `docs/V1_83_MAIL_SIGNATURE_TEMPLATE_QUERY_TRIAGE_DESIGN.md`; synthetic mailbox/cleanup later landed under `docs/V1_84_MAIL_SYNTHETIC_MAILBOX_CLEANUP_WRITE_DESIGN.md`.

## Source Review

Reviewed local public Mail scripting usage already exercised by the existing gates:

- `outgoing message` supports writable `content`, recipients, `message signature`, `save`, and `send`.
- `attachment` can be created with `file name` file input on outgoing messages.
- `reply` and `forward` return outgoing messages before `send`, which allows caller-selected local attachments to be added before delivery.

`/usr/bin/sdef /System/Applications/Mail.app` remains unavailable on this Command Line Tools-only host, so this tranche does not claim a fresh local SDEF dump. It relies on the same public Mail.app AppleScript commands already proven by the draft, send, reply, reply-all, and forward gates and keeps verification synthetic.

## Plan Contract

`mail plan` / `mail_plan_change` with `--attachment-path` on `create-draft`, `send-message`, `reply-message`, `reply-all-message`, or `forward-message`:

- accepts up to 5 caller-selected local regular files
- requires non-empty files
- caps each file at 25 MiB and total selected bytes at 25 MiB
- rejects symlink paths, directories, missing files, duplicate paths, empty files, and oversized files
- resolves and stats all candidate paths, enforces count/per-file/total-size gates, and returns validation errors before hashing file contents
- binds each selected file identity into the approval fingerprint through resolved path, size, mtime, inode, device, and content SHA-256
- returns only bounded filename, inferred type, count, and total bytes
- returns `attachment_content_returned:false` and `attachment_paths_returned:false`
- sets `attachment_send_permitted:true` for send/reply/reply-all/forward attachment plans
- keeps source-message attachments blocked by default for forward through the existing no-source-attachments/no-non-body-parts proof

`attachment_paths` on read/flag/archive/move/trash triage operations remains rejected with `unexpected_attachment_paths`.

## Apply Contract

`mail apply` / `mail_apply_change` with matching `--attachment-path`:

- recomputes the plan and requires the exact `mail-apply:v1:<approval_fingerprint>` token
- requires `confirm_apply:true`
- uses token-validated private attachment identity metadata, not newly resolved post-token state
- revalidates local files immediately before writing
- copies each validated attachment to a private temporary file and passes only that private copy to Mail automation
- refuses post-approval file identity or byte drift with `current_attachment_changed` before Mail automation
- creates Mail `attachment` objects from the private validated copies
- confirms Mail-derived attachment count before reporting success
- keeps local source paths, private copy paths, file bytes, sent body text, and source message content out of apply output

For `send_message`, `reply_message`, `reply_all_message`, and `forward_message`, Mail automation confirms the outgoing attachment count before `send`. If Mail accepts the send but local Sent read-back is delayed or ambiguous, the existing partial-result rules still apply and must not echo body text or source content.

## Verification

Required deterministic coverage:

- Plan accepts local attachments for send/reply/reply-all/forward and returns no path/bytes.
- Rejected missing, too-many, per-file oversized, and total-overflow attachment inputs do not read/hash attachment file bytes.
- Triage rejects `attachment_paths`.
- Apply sends/replies/forwards with private attachment copies, never mutable source paths.
- AppleScript adds attachments to outgoing/reply/forward messages and checks `count of attachments of content of ...`.
- Apply returns bounded attachment metadata only and `attachments_confirmed_by_automation:true`.
- Runtime verifier proves synthetic send/reply/reply-all/forward attachment apply through mocked Mail runners.

## Remaining Blocked Mail Work

Mail body/attachment discovery later landed under `docs/V1_77_MAIL_SEARCH_DISCOVERY_DESIGN.md`, capped exact bulk triage later landed under `docs/V1_78_MAIL_BULK_TRIAGE_WRITE_DESIGN.md`, opt-in source attachment forwarding later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`, outbound exact sender selection later landed under `docs/V1_82_MAIL_OUTBOUND_SENDER_SELECTION_WRITE_DESIGN.md`, signatures/templates/query-result planning later landed under `docs/V1_83_MAIL_SIGNATURE_TEMPLATE_QUERY_TRIAGE_DESIGN.md`, and synthetic mailbox/cleanup later landed under `docs/V1_84_MAIL_SYNTHETIC_MAILBOX_CLEANUP_WRITE_DESIGN.md`. Real/non-synthetic mailbox/account management, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, and unbounded bulk mutation remain blocked until separate gates land.

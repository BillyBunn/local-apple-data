# v1.75 Mail Draft Attachment Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.
Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

This gate approves optional caller-selected local file attachments for `operation:create_draft` / `create-draft` only. It does not approve attachments for `send_message`, `reply_message`, `reply_all_message`, `forward_message`, source-message attachment forwarding, non-body-part forwarding, broad attachment mutation, attachment deletion/replacement, mailbox/account management, templates, HTML/rich-text drafts, Gmail/IMAP/OAuth/network mail, iCloud.com, browser/keychain access, private APIs, or live mutation without the normal matching approval token plus explicit confirmation.

## Public Source Review

Reviewed local public source: `/System/Applications/Mail.app/Contents/Resources/Mail.sdef`.

- `outgoing message` exposes writable `content`, writable `message signature`, recipients, and `save`.
- `attachment` is a Mail scripting class with `file name` type `file`; the SDEF describes it as usable mainly for `make` commands.
- `send` is a separate command and is not used by this draft-attachment gate.
- `reply` and `forward` return outgoing messages, but this tranche does not use those commands for adding caller-selected files because reply/forward/send attachment read-back and irreversible-send attribution need separate proof.

Current Apple web documentation for Mail-specific attachment AppleScript was not found in this run; the durable local source is the installed Mail SDEF on this Mac. General Apple scripting dictionary guidance confirms that app dictionaries are the source for scriptable terms.

## Plan Contract

`mail plan --operation create-draft --attachment-path <local-file>` and `mail_plan_change(operation="create_draft", attachment_paths=[...])`:

- accept up to 5 caller-selected local regular files
- require non-empty files
- cap each file at 25 MiB and the total selected attachment bytes at 25 MiB
- reject symlink paths, directories, missing files, duplicate paths, empty files, and oversized files
- bind each selected file identity into the approval fingerprint through resolved path, size, mtime, inode, device, and content SHA-256
- return only bounded filename, inferred type, count, and total bytes
- return `attachment_content_returned:false` and `attachment_paths_returned:false`
- set `source_message_attachments_permitted:false`
- set `retry_safe:false` when attachments are selected because matching-body idempotency cannot prove attachment identity from the local Drafts read-back

`attachment_paths` on `send_message`, `reply_message`, `reply_all_message`, `forward_message`, or triage operations returns `unexpected_attachment_paths`.

## Apply Contract

`mail apply --operation create-draft --attachment-path <local-file>` and `mail_apply_change(operation="create_draft", attachment_paths=[...])`:

- recompute the plan and require the exact `mail-apply:v1:<approval_fingerprint>` token
- require `confirm_apply:true`
- use the token-validated plan's private attachment identity metadata for apply-time copying instead of re-resolving a new approved identity after token validation
- revalidate the approved local files immediately before writing
- refuse stale file state through approval-token mismatch, including same-size content changes with restored mtime
- copy each validated attachment to a private temporary file and pass only that private copy to Mail automation so post-validation source-path races cannot change attached bytes
- return `current_attachment_changed` before mutation if attachment bytes or file identity change between approval-token validation and private-copy creation
- create one hidden plaintext outgoing draft
- set `message signature` to `missing value`
- make Mail `attachment` objects from the private validated copies on the outgoing draft
- run `save draftMessage`
- never call `send`
- take a pre-apply draft snapshot and require exactly one new matching-body Draft read-back after excluding preexisting handles
- return `partial` with `attachment_read_back_unavailable` if Mail reports save success but the Mail-derived saved attachment count cannot confirm every selected file
- return bounded attachment metadata only: count, total bytes, filenames, types, `attachment_content_returned:false`, and `attachment_paths_returned:false`

Apply output must not include local attachment paths, file bytes, raw MIME, full headers, AppleScript exception text, source Mail paths, credentials, or account identifiers.

## Existing Attachment Export Hardening

This tranche also hardens the existing exact Mail attachment export surface:

- `mail:attachment:v1:` handles now bind local attachment payload bytes when bytes are locally available, so same-name/type/size content drift invalidates stale handles.
- Export refuses symlink output directories.
- Export writes with exclusive no-follow semantics where the platform exposes `O_NOFOLLOW`, preventing a caller-selected filename collision from following a symlink out of the selected output directory.
- Forward apply now treats multiple new matching Sent copies as ambiguous and returns `partial` with `ambiguous_forward_read_back` instead of accepting the first match.

## Synthetic Tests Required

- Create-draft plan with one local file returns bounded metadata and no path/bytes.
- Missing, empty, symlink, directory, duplicate, and oversized file inputs are refused.
- Send/reply/reply-all/forward reject `attachment_paths`.
- Apply with a mocked Mail runner saves a draft, makes an attachment, never sends, confirms Mail-derived `attachment_count`, and returns no path/bytes.
- Stale file identity after planning invalidates the approval token, including same-size content drift with restored mtime.
- Apply-time source-file races after token validation, including races between token computation and private-copy creation, return `current_attachment_changed` before Mail automation.
- Apply passes a private validated copy to Mail automation and does not pass the mutable caller-selected source path.
- Mail draft AppleScript contains `make new attachment`, `save draftMessage`, and no `send`.
- Exact Mail attachment export rejects stale same-size content drift.
- Mail attachment export rejects symlink output directory and symlink target escape.
- Forward apply returns `partial` for ambiguous new matching Sent read-back.
- CLI and MCP wrappers pass `attachment_paths` to the adapter.
- Runtime verifier covers draft-attachment plan/apply, path non-leakage, and non-draft refusal.

## Remaining Blocked Mail Work

Outbound local-file attachments for `send_message`, `reply_message`, `reply_all_message`, and `forward_message` later landed under `docs/V1_76_MAIL_OUTBOUND_ATTACHMENT_WRITE_DESIGN.md`, capped exact bulk triage later landed under `docs/V1_78_MAIL_BULK_TRIAGE_WRITE_DESIGN.md`, opt-in source attachment-like part forwarding later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`, outbound exact sender selection later landed under `docs/V1_82_MAIL_OUTBOUND_SENDER_SELECTION_WRITE_DESIGN.md`, signatures/templates/query-result planning later landed under `docs/V1_83_MAIL_SIGNATURE_TEMPLATE_QUERY_TRIAGE_DESIGN.md`, and synthetic mailbox/cleanup later landed under `docs/V1_84_MAIL_SYNTHETIC_MAILBOX_CLEANUP_WRITE_DESIGN.md`. Source attachment/non-body-part forwarding outside explicit `include_source_attachments`, real/non-synthetic mailbox/account management, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, unbounded bulk mutation, Gmail/IMAP/OAuth/network mail paths, iCloud.com, browser/keychain access, and private API paths remain blocked.

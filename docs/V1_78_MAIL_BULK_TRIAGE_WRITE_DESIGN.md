# v1.78 Mail Bulk Triage Write Design

Status: Source apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.
Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

This gate extends the existing exact-message Mail triage operations to a capped list of exact selected `mail:message:v2:` handles. It does not approve query-result auto-apply, broad mailbox mutation, thread/conversation mutation, permanent delete, empty Trash/Junk, mailbox/account management, source attachment forwarding, templates/signatures, Gmail/IMAP/OAuth/network mail, iCloud.com, browser/keychain access, private APIs, or live mutation without a matching approval token plus explicit confirmation.

## Source Review

No new Mail.app scripting verbs are introduced. Bulk triage reuses the public AppleScript already approved by the exact single-message triage gates:

- `set read status of ...` for `mark_read` / `mark_unread`
- `set flagged status of ...` for `flag_message` / `unflag_message`
- `move ... to archiveBox` for `archive_message`
- `move ... to trashBox` for `trash_message`
- `move ... to targetBox` for `move_message`

Every generated script still scopes to one selected message's account, nested mailbox path, and RFC Message-ID recovered from the local `.emlx` file. The bulk wrapper runs those one-message scripts sequentially; it does not generate a broad mailbox-level AppleScript predicate, does not use raw database IDs, and does not address messages by search query.

## Plan Contract

`mail plan` / `mail_plan_change` accepts unique exact message handles only for the existing triage operations:

- `mark_read`
- `mark_unread`
- `flag_message`
- `unflag_message`
- `archive_message`
- `trash_message`
- `move_message`

The plan:

- requires at least two exact `mail:message:v2:` handles for bulk mode
- caps the batch at 20 handles
- rejects duplicate, invalid, raw, fabricated, or missing handles
- keeps reply/reply-all/forward bound to one exact source handle and rejects unique handles there
- resolves every selected message through the local Mail metadata plus `.emlx` RFC Message-ID bridge
- binds every selected message handle, current read/flag/mailbox state fingerprint, and target state into one approval fingerprint
- binds each Archive/Trash/exact target mailbox separately for each selected message
- returns only opaque message handles, opaque mailbox/account refs, current state booleans, target refs, counts, and approval metadata
- returns no message body, source path, raw account identifier, raw mailbox URL, raw row ID, or attachment bytes

## Apply Contract

`mail apply` / `mail_apply_change` for bulk triage:

- recomputes the bulk plan and requires the exact `mail-apply:v1:<approval_fingerprint>` token
- requires `confirm_apply:true`
- preflights every selected message and target before the first Mail automation call
- refuses stale read/flag/mailbox state with `stale_message_state` before mutating anything
- refuses stale target mailbox resolution with `stale_mailbox_target` before mutating anything
- skips already-satisfied selected messages without running Mail automation for those handles
- applies remaining selected messages sequentially through the exact one-message AppleScript path
- verifies each applied message through local read-back
- returns `partial` if Mail automation or read-back fails after at least one earlier message applied
- keeps every selected handle represented in partial output; later skipped handles use `status:"not_attempted"` and `warning_code:"not_attempted_after_prior_failure"`
- returns a bulk `read_back` object with `applied_count`, `already_satisfied_count`, `failed_count`, `not_attempted_count`, and per-message opaque handle rows
- returns no message body, raw identifiers, source paths, local attachment paths, or attachment bytes

## Verification

Required deterministic coverage:

- Direct adapter tests prove bulk plan shape, duplicate-handle rejection, mixed already-satisfied apply, stale preflight refusal, and partial result after mid-batch automation failure with unattempted rows preserved.
- CLI tests prove repeated `--message-handle` values are forwarded as one primary handle plus `message_handles`.
- MCP wrapper signatures expose optional `message_handles` without adding new tool names.
- Runtime verifier proves synthetic bulk `mark_read` over two exact handles with one mutation and one already-satisfied row.
- Mutation/write-design/surface audits continue to enforce that `mail_apply_change` is the only Mail write MCP tool and is statically destructive.

## Remaining Blocked Mail Work

Sender selection outside create-draft, templates/signatures beyond signature clearing, mailbox/account management, permanent delete, empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, and unbounded bulk mutation remain blocked until separate gates land. Opt-in private Mail FTS indexing later landed under `docs/V1_81_MAIL_FTS_INDEX_DESIGN.md`.

Attachment content/PDF/OCR snippets later landed under `docs/V1_79_MAIL_ATTACHMENT_CONTENT_SEARCH_DESIGN.md`; opt-in source attachment forwarding later landed under `docs/V1_80_MAIL_SOURCE_FORWARD_WRITE_DESIGN.md`.

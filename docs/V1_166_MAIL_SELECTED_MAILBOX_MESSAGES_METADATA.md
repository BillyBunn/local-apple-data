# v1.166 Mail Selected-Mailbox Messages Metadata

Status: implemented, synced, installed, and verified for the `0.1.0+codex.20260703055927` tranche.

## Surface

- Adapter: `list_mail_mailbox_messages`
- MCP: `mail_list_mailbox_messages`
- CLI: `local-apple-data mail mailbox-messages --json --handle <mail:mailbox:v1:...> --after <date-or-timestamp> [--before <date-or-timestamp>]`

## Contract

- Requires one exact opaque `mail:mailbox:v1:` handle returned by Mail mailbox metadata.
- Requires an explicit `after` or `before` date bound.
- Caps output at the existing Mail discovery cap of 50.
- Opens the local Mail Envelope Index read-only.
- Returns message metadata with `mail:message:v2:` handles and metadata-only `content_status`.
- Returns selected mailbox metadata and safe privacy flags.

## Safety

- No message bodies.
- No full headers.
- No raw Mail paths.
- No raw account IDs.
- No mailbox URL output.
- No mutation shortcut.
- No unbounded mailbox dumps.
- No Gmail, IMAP, iCloud.com, browser, keychain, or network mail fallback.

## Verification

- Synthetic adapter tests cover date-bound refusal, invalid mailbox handles, cap enforcement, and metadata-only output.
- CLI and MCP regression tests cover exact handle/date-bound forwarding.
- Runtime verifier proves tool presence and a synthetic selected-mailbox message listing with no content or raw path return.
- Source and installed-cache full pytest passed with `1848 passed`.

## Remaining Blockers

- Broad/unbounded Mailbox message dumps remain blocked.
- Full content still requires exact `mail:message:v2:` selection through `mail_get_content`.
- Real/non-synthetic Mail mailbox/account management remains limited to the approved plan/apply gates and source-gated synthetic cleanup.

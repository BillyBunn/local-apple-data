# V1.80 Mail Source Forward Write Design

Status: Source apply-capable implementation.

Approved write tools: `local-apple-data mail apply` and `mail_apply_change`.

Planning tools: `local-apple-data mail plan` and `mail_plan_change`.

No new mutating tool names are approved or exposed by this document.

This gate extends `forward_message` only. By default, Mail forward still refuses source messages with attachments or non-body MIME parts. When the caller explicitly sets `include_source_attachments`, the planner allows Mail.app's native exact-source forward to preserve source attachment-like parts: declared attachments plus non-body MIME parts that the local MIME scanner classifies as forwardable source parts. This gate does not approve direct subject override, sender selection for forward, templates/signatures beyond signature clearing, mailbox/account management, permanent delete, empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, unbounded bulk mutation, Gmail/IMAP/OAuth/network mail, iCloud.com, browser/keychain access, or private APIs.

## Source Review

Local source review used `/System/Applications/Mail.app/Contents/Resources/Mail.sdef` because `sdef /System/Applications/Mail.app` remains unavailable on this machine when only Command Line Tools are active.

Observed Mail.app contract:

- Mail exposes a `forward` command with direct `message` parameter and optional `opening window` boolean.
- The `forward` command returns an `outgoing message`.
- `outgoing message` exposes writable recipients, `sender`, `subject`, `content`, and `message signature`.
- Rich text `attachment` exposes a `file name` property for caller-selected local attachments.

The implementation keeps exact source selection through account id, nested mailbox path, and RFC Message-ID recovered from the selected local `.emlx` file. It parses source MIME structure only enough to count and hash header-level source part state for token binding; it does not parse or export source attachment bytes for forwarding. Mail.app performs the native forward.

## Preview

Mail forward planning is non-mutating. Exact `mail:message:v2:` source handle input, explicit recipients, and bounded non-empty plaintext prepend body are required. Direct subject input remains rejected.

Default preview behavior remains unchanged: source attachments and non-body MIME parts are refused. With `include_source_attachments:true`, preview resolves source attachment-like part state through an uncapped header-only MIME scan, returns only counts and booleans such as `source_attachment_count`, `source_attachment_like_part_count`, `source_declared_attachment_count`, `source_non_body_part_count`, and `source_attachments_permitted:true`, and binds the source part state plus source content state into the approval fingerprint.

Preview output must not return source attachment bytes, source attachment paths, raw MIME, full headers, local `.emlx` paths, full email addresses, raw account identifiers, raw row IDs, approval tokens, or approval fingerprints outside the transient preview response.

## Apply

Apply recomputes the plan, requires the matching `mail-apply:v1:<approval_fingerprint>` token, requires `confirm_apply=true`, and requires the same `include_source_attachments` value as the plan.

Apply re-resolves the source message immediately before sending and refuses stale source message state, stale source attachment/non-body-part state, or stale source content state before Mail automation. Automation runs `forward sourceMessage opening window false`, clears the message signature, sets the deterministic derived subject, prepends bounded plaintext body, adds explicit recipients, optionally adds caller-selected local attachment copies, checks the Mail-derived attachment count against local attachments plus the locally counted source attachment-like part count before sending, and sends the forward.

Read-back takes a pre-send Sent snapshot, then finds a new matching Sent copy by derived forward subject and normalized prepend body prefix while excluding pre-existing Sent handles. Successful read-back returns selected metadata plus `sent_copy_confirmed:true`, `forward_copy_confirmed:true`, `source_attachment_count`, `source_attachment_like_part_count`, `source_declared_attachment_count`, `source_non_body_part_count`, `forwarded_attachment_count`, `source_forward_verification:"mail_attachment_count_pre_send"`, `source_attachments_permitted:true`, `source_non_text_parts_permitted:true`, `source_non_body_parts_permitted:true`, `body_returned:false`, and no source body, attachment bytes, or paths. It does not expose or claim per-part identity/content read-back from Sent.

## Refusals

- Missing, malformed, or fabricated message handle.
- Missing local `.emlx` RFC Message-ID bridge.
- Missing To recipient, malformed recipient, missing body, or overlong body.
- Direct subject input.
- Source message with attachments or non-body MIME parts unless `include_source_attachments:true`.
- Source attachment/non-body-part state unavailable.
- Source content state unavailable.
- Missing confirmation or mismatched approval token.
- Stale source message state.
- Stale source attachment/non-body-part state.
- Stale source content state.
- Mail.app automation timeout or error.
- Mail-derived attachment count mismatch.
- Sent read-back unavailable, reported as partial after Mail.app accepts the forward.

## Synthetic Tests Required

- Preview default still rejects source messages with attachments or non-body MIME parts.
- Preview accepts source attachment-like parts only when `include_source_attachments:true`.
- Preview counts more than the public 50-result attachment listing cap through an uncapped source-part scanner.
- Preview and apply cover inline/fileless non-body MIME parts with count-only source-part verification.
- Preview and apply reject `include_source_attachments` outside `forward_message`.
- Apply recomputes source attachment/non-body state and refuses drift.
- Apply proves Mail.app exact-source forward automation, total forwarded attachment count confirmation, Sent-copy read-back, no body echo, no source attachment byte/path echo, and no direct subject/sender/mailbox mutation.
- CLI and MCP tests prove `include_source_attachments` wiring.
- Runtime verifier proves synthetic source attachment forward through mocked Mail runner.
- Release-readiness, write-design gate, redaction, and public-release coverage.

Sender selection outside create-draft, templates/signatures beyond signature clearing, mailbox/account management, permanent delete, empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, unbounded bulk mutation, and background/unbounded Mail indexing remain blocked until separate gates land. Opt-in private Mail FTS indexing later landed under `docs/V1_81_MAIL_FTS_INDEX_DESIGN.md`.

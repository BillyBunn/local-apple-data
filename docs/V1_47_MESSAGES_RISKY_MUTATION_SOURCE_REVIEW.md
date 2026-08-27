# v1.47 Messages Risky Mutation Source Review

Date: 2026-06-17
Status: Source-reviewed blocker design gate with machine-readable public Messages SDEF audit; no apply-capable implementation.

## Objective

Decide whether Messages direct-recipient sends, new-chat creation, SMS/RCS/iMessage fallback selection, account selection, reactions/tapbacks, edit, unsend, delete, mark read, or group management can safely move from the blocked roadmap into an approved write design.

This document approves no new mutation. It exists to make the source-review result durable and machine-checkable before any higher-risk Messages CRUD work.

## Local Source Review

- Reviewed `/System/Applications/Messages.app/Contents/Resources/Messages.sdef`.
- Verified local Messages bundle metadata: `CFBundleIdentifier=com.apple.MobileSMS`, version `26.0`, bundle `1450.600.61.1.4`.
- The local scripting dictionary exposes only `send`, `login`, and `logout` commands.
- The `send` command accepts text or file input addressed to a `participant` or `chat`; the current plugin already restricts this to one exact existing `messages:chat:v1:` chat handle through `send_text` and `send_file`.
- Machine-readable audit command: `uv run python scripts/audit_messages_public_surface.py --json`.
- Current audit result: `status:"ok"`, `messages_public_surface_reviewed:true`, `finding_count:0`, expected commands `login`, `logout`, and `send`, `send` direct types `file`/`text`, and `send` target types `chat`/`participant`.
- The audit is a public scripting-surface drift check only. It does not inspect Messages content, `chat.db`, participants beyond SDEF type names, local chats, contacts, account identifiers, or message bodies.
- The audit recognizes `account.enabled` as a known non-readonly property but does not approve account mutation, outgoing-account selection, login/logout automation, or any broader Messages apply surface.
- The `application`, `account`, and `chat` elements expose read-only participant/chat/file-transfer lists useful for metadata and read-back, but not a durable public mutation surface for chat lifecycle or message lifecycle operations.
- The `chat` participant element says participants may be specified at creation time, but the dictionary exposes no public create/new-chat command for the plugin to call safely.
- No public scripting command is exposed for edit, unsend, delete, reaction, tapback, mark read, group management, direct-recipient creation, or new-chat creation.
- Although `send` can target a `participant` and v1.64 adds exact read-only `messages:participant:v1:` metadata handles inside a selected existing chat, this repo still has no fallback/account-control contract, no direct-recipient approval design, and no approved read-back gate for participant-targeted sends that proves no new-chat, service fallback, raw recipient, contact lookup, or account-selection side effects.

## Decision

No new mutating CLI or MCP tool is approved by this document.

The current approved Messages apply surface remains exactly:

- `send_text` to one exact existing `messages:chat:v1:` chat.
- `send_file` to one exact existing `messages:chat:v1:` chat.

`send_text` and `send_file` to one exact existing `messages:chat:v1:` chat remain the only approved Messages apply operations.

SQLite `chat.db` remains read-back only. Direct SQLite mutation is not an acceptable implementation path.

## Still Blocked

- Direct-recipient sends.
- New-chat creation.
- SMS/RCS/iMessage fallback selection.
- Outgoing-account selection.
- Participant lookup or contact lookup for mutation.
- Reactions or tapbacks.
- Edit, unsend, or delete.
- Mark read.
- Group management.
- Rich text, effects, inline replies, and bulk operations.
- IMCore injection, private frameworks, private iCloud APIs, browser sessions, keychain access, Messages UI scraping, raw handle inputs, or connector fallback.

## Future Gate Requirements

Future implementation requires a separate approved write design and must first prove a durable public local API or app-automation path that does not require private frameworks, raw participant identifiers, direct database mutation, browser/keychain state, network services, or broad personal-content inspection.

Any future Messages mutation design must include:

- Exact opaque target handles from a metadata-first flow.
- Non-mutating preview.
- Approval-token apply with explicit confirmation.
- Current-state binding and stale-state refusal.
- Independent local read-back or absence proof.
- Synthetic tests only.
- Redaction coverage for bodies, participant identifiers, chat GUIDs, raw row IDs, paths, approval fingerprints, and helper errors.
- Runtime verifier coverage.
- Mutation/write-design/surface-contract auditor coverage.
- Installed-cache and cross-agent verification before any completion claim.

## Synthetic Tests Required

This source-review gate is enforced by `scripts/audit_messages_public_surface.py`, `scripts/audit_write_design_gates.py`, `scripts/audit_release_readiness.py`, and packaging tests. There is no apply/read-back test because no new operation is exposed.

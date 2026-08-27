# v1.38 Messages Send-File Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data messages apply` and `messages_apply_change`.

This document approves exactly one additional Messages operation: send one bounded local file to one exact existing Messages chat selected by an opaque `messages:chat:v1:` handle. It does not approve direct-recipient
sends, new chat creation, SMS fallback selection, outgoing-account selection, rich text, effects, inline replies,
reactions/tapbacks, edit, unsend, delete, mark read, group management, participant lookup for mutation, contact lookup, network
or iCloud APIs, IMCore injection, private frameworks, bulk operations, or arbitrary attachment mutation.

Current note: v1.64 later added a separate read-only exact-chat participant metadata/detail surface. Participant lookup for mutation, direct-recipient sends, new chats, contact lookup, group management, and participant-target sends remain out of scope here.

## Scope

Allowed:

- `local-apple-data messages plan --operation send-file`
- `messages_plan_change(operation="send_file")`
- `local-apple-data messages apply --operation send-file`
- `messages_apply_change(operation="send_file")`

Required inputs:

- Exact opaque `messages:chat:v1:` handle from the Messages chat metadata flow.
- Local regular file path selected by the caller.
- Matching `messages-apply:v1:<approval_fingerprint>` approval token.
- Explicit `confirm_apply:true`.

Out of scope:

- Raw chat row IDs, chat GUIDs, phone numbers, email addresses, participant identifiers, or fabricated handles.
- Direct-recipient sends, new chats, SMS fallback selection, outgoing account selection, or participant lookup for mutation.
- Direct Messages attachment handles as send inputs.
- Directories, empty files, missing files, non-local URLs, file bytes returned inline, or local file paths returned in output.
- Files larger than the implementation cap.
- Messages edit, unsend, delete, reactions/tapbacks, mark read, group management, bulk mutation, private frameworks, or network APIs.

## Safety Contract

Plan is non-mutating. It resolves the exact chat handle through the local Messages metadata path, validates the
selected local file as a regular non-empty file under the size cap, returns bounded file metadata, and creates an
approval fingerprint over the exact operation, chat state, and internal file identity. The preview must not return
the resolved local path, file bytes, chat GUID, participant identifiers, raw row IDs, approval token, or raw helper
errors.

Apply recomputes the plan, requires the matching approval token, requires explicit confirmation, revalidates the
same local file identity, resolves the same exact chat again, and refuses stale chat or file state before
automation. The approval token binds the exact chat state, file size, file modification time, device, inode, and
resolved path internally; these identity fields are not returned in normal output.

Automation may only send the selected local file to the selected existing Messages chat id through Messages.app
AppleScript. It must not address a direct recipient, create a new chat, choose SMS fallback, delete, edit, remove,
or mutate existing Messages attachments.

Read-back is mandatory. A successful apply must re-read local `chat.db` and confirm a newer outgoing attachment
joined to the same chat, matching the selected filename and known file size when Messages records it. Apply output
returns bounded attachment metadata and never returns file bytes or local file paths.

## MCP Annotation

`messages_plan_change` stays read-only. `messages_apply_change` remains non-read-only, non-destructive,
idempotent, and closed-world because this gate sends one selected file to one selected existing chat and does not
delete or alter existing data. Destructive Messages operations remain absent.

## Idempotency

Preview creates a deterministic idempotency key from operation, target chat state, and internal file identity.
Apply recomputes the plan immediately before sending; changed chat state, changed file path, changed file size, or
changed file modification identity causes approval-token mismatch. If read-back is unavailable after an attempted
send, apply returns non-success with `mutation_applied:true` and the caller must inspect/search Messages before
retrying.

## Synthetic Tests Required

Required tests:

- Plan success for `send_file` with exact chat handle and local synthetic file.
- Plan validation for missing file path, invalid handle, missing file, directory, empty file, and oversized file.
- Apply success using mocked Messages.app automation and synthetic `chat.db` attachment read-back.
- Missing confirmation, invalid approval token, stale chat state, and stale file identity refusals.
- Ghost-row detection or read-back unavailable behavior after attempted send.
- AppleScript safety tests proving the file script targets `chat id` and never uses direct recipient terms or destructive verbs.
- CLI coverage for `messages plan/apply --operation send-file`.
- Runtime synthetic smoke for `send_file` without touching live Messages.

## Current Release Gate

This release allows only exact-chat Messages `send_text` and `send_file` through `messages plan` / `messages apply`
and `messages_plan_change` / `messages_apply_change`. Direct-recipient sends, new chats, SMS fallback selection,
outgoing-account selection, rich text, effects, inline replies, reactions/tapbacks, edit, unsend, delete, mark
read, group management, participant lookup for mutation, contact lookup, broad attachment mutation, network/iCloud APIs, IMCore
injection, private frameworks, and bulk operations remain blocked.

Read-only exact-chat participant metadata is governed separately by `docs/V1_64_MESSAGES_PARTICIPANTS_METADATA.md`; it does not approve participant-target sends or any other Messages mutation.

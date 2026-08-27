# V1.64 Messages Participant Metadata

Status: Read-only implementation.

Approved read tools: `local-apple-data messages participants`, `local-apple-data messages participant`, `messages_list_participants`, and `messages_get_participant`.

No write tool is approved by this document.

## Scope

This tranche adds metadata-first participant selection for one exact existing Messages chat selected by opaque `messages:chat:v1:` handle.

It is not approval for direct-recipient send, new-chat creation, SMS/RCS/iMessage fallback selection, outgoing-account selection, participant lookup for mutation, contact lookup, edit, unsend, delete, reaction/tapback, mark read, group management, Messages UI scraping, direct SQLite mutation, private frameworks, or network fallback.

## List

`messages_list_participants` and `local-apple-data messages participants` require one exact `messages:chat:v1:` handle returned by `messages_search`.

List output is metadata-only:

- Opaque `messages:participant:v1:` handle.
- Service label.
- Message count and last-message timestamp for that participant in the selected chat.
- `participant_id_returned:false`.

List output does not return raw participant identifiers, masked participant previews, phone numbers, email addresses, chat GUIDs, raw handle row IDs, message text, attachment bytes, local paths, or contact details.

## Exact Detail

`messages_get_participant` and `local-apple-data messages participant` require both the original exact `messages:chat:v1:` handle and one selected `messages:participant:v1:` handle returned by the participant list.

Exact detail may return the selected participant identifier because the caller already selected the participant handle inside the selected chat. The response remains bounded and does not return chat GUIDs, raw row IDs, contacts data, message text, attachment bytes, local paths, or mutation affordances.

## Safety

- SQLite `chat.db` remains read-only.
- Participant handles are opaque and bound to schema fingerprint, chat identity, participant row, normalized identifier, and service.
- Search/list remains metadata-first and does not expose participant identifier previews.
- Full participant identifiers are exact-handle detail only.
- The surface does not call Messages.app automation.
- The surface does not send messages or create chats.
- The surface does not inspect Keychain, browser sessions, iCloud.com, private APIs, IMAP, OAuth, Gmail, Contacts, or network services.

## Tests Required

- Synthetic adapter coverage proving participant list output has opaque handles without identifier previews.
- Synthetic adapter coverage for exact participant detail by chat and participant handle.
- Synthetic adapter coverage proving participant handles cannot be replayed against a different chat handle.
- Synthetic adapter coverage proving participant handles are refused as Messages mutation targets.
- Invalid chat and participant handle refusal.
- CLI `messages participants` and `messages participant` coverage.
- CLI event-log redaction coverage proving participant handles and raw participant identifiers are not durably logged.
- MCP direct wrapper and tool inventory coverage proving list output remains metadata-only while exact detail remains gated.
- Runtime verifier coverage proving list output has no identifier preview, serialized direct and MCP participant lists do not contain the selected synthetic identifier, exact-detail identifier return, cross-chat refusal, invalid-handle refusal, and no mutation.
- Surface-contract and mutation-gate count updates.
- Redaction scan coverage proving raw participant identifiers do not leak into durable logs or docs.

The current Messages apply surface remains only `send_text` and `send_file` to one exact existing `messages:chat:v1:` chat. Risky Messages direct-recipient/new-chat/edit/delete/reaction/tapback/mark-read work remains blocked by `docs/V1_47_MESSAGES_RISKY_MUTATION_SOURCE_REVIEW.md` and the public SDEF audit.

# v1.23 Messages attributedBody Fallback Design

Status: implemented read-only surface refinement.

This release improves exact-handle Messages transcript completeness by decoding bounded plaintext from local `message.attributedBody` rows when modern Messages records have an empty `message.text` column. It does not add broad Messages text search, participant detail, participant lookup for mutation, reactions, attachment scanning, or any mutating tool.

Current note: v1.64 later added a separate read-only exact-chat participant metadata/detail surface with no list-time phone/email previews. This v1.23 gate still does not expose participants through transcript retrieval.

## Why This Exists

Public Messages tooling documents that recent macOS Messages data often stores body text in `message.attributedBody` as an Apple typedstream/NSArchiver payload rather than in the `message.text` column:

- `imessage-core` documents `attributedBody` typedstream decoding for plaintext fallback: https://docs.rs/imessage-core/latest/imessage_core/typedstream/index.html
- `iMessagePrinter` documents the same `message.text` NULL pattern and explains why `NSUnarchiver` is the correct native decoder for the legacy typedstream data: https://blog.fsck.com/agent-blog/2026/02/19/imessageprinter/
- Apple documents `NSUnarchiver.unarchiveObject(with:)` as decoding data archived with `NSArchiver`: https://developer.apple.com/documentation/foundation/nsunarchiver/unarchiveobject%28with%3A%29

## Approved Surface

- CLI: `local-apple-data messages get --handle <messages:chat:v1:...>`
- MCP: `messages_get_chat`

The caller must first select an exact `messages:chat:v1:` handle from Messages chat display-name metadata output. The transcript path remains bounded by `max_messages` and `max_chars`. The returned message object can include `text_source:"text"` or `text_source:"attributed_body"` so clients can explain where plaintext came from.

## Implementation

- Python remains the adapter/MCP/CLI layer for consistency with the rest of the project.
- The native helper `scripts/messages_helper.swift` decodes selected `attributedBody` blobs through Foundation `NSUnarchiver` and returns only bounded plaintext.
- The adapter invokes the helper only for exact selected transcript rows whose normal `message.text` is empty.
- If batch decoding fails, the adapter retries per item so one malformed typedstream value does not hide other decodable fallback rows.
- Helper failures degrade to `messages_attributed_body_unavailable` and preserve normal `message.text` rows.

## Data Boundaries

- Raw typedstream bytes are never returned.
- Attributed-string attributes, runs, effects, reactions, tapbacks, edits, send state, participant identifiers, phone numbers, email addresses, chat GUIDs, raw row IDs, and local database paths are never returned.
- No durable personal-content cache is created.
- No broad message-text search is added.
- No private iCloud web/API, browser, keychain, network, or Messages.app automation path is used.

## Refusals

The surface refuses:

- Raw chat IDs, chat GUIDs, old handles, fabricated handles, local database paths, and direct typedstream payload inputs.
- Broad transcript dumps or message-text searches.
- Raw attributed-body export or attributed-string attribute extraction.
- Messages send, edit, delete, reaction, attachment mutation, or unavailable iCloud media fetch.

## Verification

The implementation is covered by synthetic fixtures only:

- Exact transcript retrieval from normal `message.text` rows.
- Exact transcript fallback from a valid synthetic `attributedBody` typedstream row.
- Malformed attributed-body degradation that preserves normal and individually decodable rows.
- Runtime smoke proof that a synthetic attributed-body row is returned with `text_source:"attributed_body"`.
- Helper presence, release-readiness, cross-agent sync, compile, and redaction coverage.

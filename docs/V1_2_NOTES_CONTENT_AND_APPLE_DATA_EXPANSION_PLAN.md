# v1.2 Notes Content and Apple Data Expansion Plan

## Status

Status: v1.2 Notes exact-handle content, v1.3 iCloud Drive exact-handle text-file content, v1.4 Calendar exact-handle event detail retrieval, v1.5 Reminders exact-handle note retrieval, v1.6 Contacts exact-handle detail retrieval, v1.7 Photos exact-handle asset/resource metadata and asset export, v1.8 Messages exact-handle chat transcript retrieval, v1.9 Voice Memos exact-handle existing transcript and audio export retrieval, v1.10 inferred Hide My Email exact-handle alias detail retrieval, v1.20 Notes exact-handle attachment metadata/export, and v1.21 Mail exact-handle attachment metadata/export implemented. Broader Apple data expansion remains planned behind separate surface gates.

## Why This Phase Exists

The original plugin stopped at Notes title/snippet metadata. That was too narrow for the product mission: a local Apple data MCP server should be able to read user-approved local Apple data surfaces while preserving a strict privacy model.

This phase expands Notes from metadata-only to exact-handle content retrieval, adds local iCloud Drive filename search and exact text-file content retrieval, adds EventKit Calendar title search and exact event detail retrieval, adds EventKit Reminders title search and exact note retrieval, adds Contacts.framework name/organization search and exact contact detail retrieval, adds PhotoKit original-filename search plus exact asset/resource metadata and asset export, adds local Messages chat display-name search and exact chat transcript retrieval, adds local Voice Memos title/filename search plus exact existing transcript and audio export retrieval, adds inferred Hide My Email alias evidence from local Mail address metadata, and records the durable architecture for expanding toward future write paths.

## Research Summary

External tools commonly do expose Notes body content. The missing capability was not an ecosystem norm; it was a conservative local boundary in this repo.

For the public architecture comparison and source review, see `docs/ECOSYSTEM_REVIEW.md`.

References checked:

- Apple Developer Forums, "Apple Notes API": Apple DTS says there is no public Notes API; AppleScript is possible on macOS but is less ideal and macOS-only. https://developer.apple.com/forums/thread/813810
- `sirmews/apple-notes-mcp`: an MCP server that reads the local Apple Notes database and exposes full-note reads/search. https://github.com/sirmews/apple-notes-mcp
- GitHub `apple-notes` topic: multiple current Notes MCP/export projects use AppleScript, direct Notes database parsing, or both. https://github.com/topics/apple-notes
- Apple EventKit documentation: official framework for retrieving and modifying Calendar events and Reminders. https://developer.apple.com/documentation/eventkit
- Apple Contacts `CNContactStore` documentation: official framework for fetching and saving Contacts. https://developer.apple.com/documentation/contacts/cncontactstore
- Apple PhotoKit fetching and change documentation: official framework for Photos metadata/content fetches and explicit change blocks. https://developer.apple.com/documentation/photokit/fetching_objects_and_requesting_changes and https://developer.apple.com/documentation/photokit/requesting-changes-to-the-photo-library
- `RhetTbull/osxphotos` and `RhetTbull/photokit`: mature references for querying local Photos libraries and using PhotoKit from Python/macOS. https://github.com/RhetTbull/osxphotos and https://github.com/RhetTbull/photokit
- `openclaw/imsg`: current agent-oriented Messages CLI that reads `~/Library/Messages/chat.db` and uses AppleScript for send paths. https://github.com/openclaw/imsg
- `chatwire`: local-first Messages bridge with MCP integration that reads `chat.db` and drives Messages.app through AppleScript. https://chatwire.app/
- Apple Support Voice Memos iCloud sync documentation: Voice Memos recordings can appear across signed-in Apple devices when Voice Memos is enabled in iCloud settings. https://support.apple.com/guide/voice-memos/see-your-recordings-on-all-your-apple-devices-vma6cc4d0571/mac
- Apple Support Voice Memos title encryption note: current OS releases encrypt iCloud Voice Memos titles in addition to the recordings. https://support.apple.com/en-us/105006
- `jwulff/apple-voice-memo-mcp`: MCP reference for local Voice Memos metadata/audio/transcript tools using `CloudRecordings.db` and `.m4a` files. https://github.com/jwulff/apple-voice-memo-mcp
- `jessedc/apple-voice-memos` and `uasi/extract-apple-voice-memos-transcript`: references for read-only `CloudRecordings.db` metadata and `tsrp` atom transcript extraction. https://github.com/jessedc/apple-voice-memos and https://github.com/uasi/extract-apple-voice-memos-transcript
- Apple Support iCloud Drive documentation: Desktop/Documents and iCloud Drive files are represented locally on Mac and can be read from local file-system surfaces when downloaded. https://support.apple.com/en-gb/109344
- Apple Support Hide My Email documentation and Apple private relay documentation: user Hide My Email management exists in Settings/iCloud surfaces; developer-facing private relay docs do not provide a local user CRUD API for arbitrary Hide My Email inventory. https://support.apple.com/guide/iphone/iphcb02e76f7/26/ios/26 and https://developer.apple.com/documentation/signinwithapple/communicating-using-the-private-email-relay-service
- Third-party Hide My Email managers such as `mark-liu/hme`, `lukenmorris/icloud-hide-my-email-manager`, and `not-knope/Hide-My-Email-iCloud-Manager` are useful references for expected user workflows, but they rely on private iCloud web/API or credential-bearing paths. Those paths are intentionally out of scope for this local-only plugin. https://github.com/mark-liu/hme https://github.com/lukenmorris/icloud-hide-my-email-manager https://github.com/not-knope/Hide-My-Email-iCloud-Manager

## Architecture Decision

Keep the MCP server, CLI, tests, handles, redacted logging, and plugin packaging in Python with `uv`. This is the fastest durable path for Codex, Claude Code, OpenClaw, Cursor, and other MCP clients because stdio MCP and JSON tooling are already stable here.

Use native Swift helpers for official Apple frameworks:

- EventKit for Calendar and Reminders.
- Contacts for Contacts.
- PhotoKit for Photos.
- AppKit/Foundation file APIs for iCloud Drive local file metadata and exact file reads.

Use direct SQLite only for local stores where Apple does not provide a suitable public framework and only with read-only/query-only connections, schema guards, narrow searches, and opaque handles:

- Mail metadata and existing `.emlx` content mapping.
- Inferred Hide My Email alias evidence from local Mail `addresses`/`messages`/`recipients` metadata.
- Notes metadata.
- Messages chat display-name metadata and exact transcript content.
- Voice Memos title/filename metadata and exact existing embedded transcript content.

Use AppleScript/JXA automation only when Apple provides no public framework and local automation is the least-bad exact-handle path:

- Notes exact body retrieval in v1.2.
- Optional Messages send or Notes mutation in later write phases, behind explicit approval gates.

Do not use network scraping, Gmail/IMAP/OAuth fallback, browser cookies, iCloud.com automation, or private web APIs for this plugin.

## Implemented v1.2 Surface

Tools:

- `notes_get_content(handle: str, max_chars: int = 4000)`
- `local-apple-data notes content --json --handle '<notes:note:v2:...>' --max-chars 4000`

Behavior:

- Accepts only opaque `notes:note:v2:` handles returned by the metadata flow.
- Rejects raw row IDs, old handles, direct database IDs, direct file paths, and fabricated handles.
- Resolves the note internally from the read-only Notes SQLite store.
- Excludes deleted and password-protected notes.
- Uses the local Notes app automation dictionary to retrieve the exact selected note body by Core Data object URI.
- Converts Notes HTML body output to bounded plain text.
- Defaults to 4000 characters and hard-caps at 12000.
- Returns `content_text`, `content_chars`, `truncated`, already-allowed note metadata, and safe warning codes only.
- Logs command/status/privacy/warning codes only; never logs content, handles, titles, snippets, raw paths, raw database rows, or raw automation errors.

## Implemented v1.3 Surface

Tools:

- `icloud_drive_search(query: str, limit: int = 20)`
- `icloud_drive_get_metadata(handle: str)`
- `icloud_drive_get_content(handle: str, max_chars: int = 4000)`
- `local-apple-data icloud-drive search --json --query '<filename text>' --limit 20`
- `local-apple-data icloud-drive content --json --handle '<icloud:file:v1:...>' --max-chars 4000`

Behavior:

- Searches local iCloud Drive by filename only.
- Rejects empty and broad filename queries before scanning.
- Returns filename, extension, file/folder kind, size, modified timestamp, depth, and opaque handle without raw local paths.
- Accepts only opaque `icloud:file:v1:` handles returned by the metadata flow.
- Rejects direct paths, fabricated handles, hidden files, symlinks, unsupported binary/document types, broad content search, background indexing, and durable content caches.
- Reads content only for supported text-like file suffixes.
- Defaults to 4000 characters and hard-caps at 12000.
- Returns `content_text`, `content_chars`, `truncated`, already-allowed file metadata, and safe warning codes only.
- Logs command/status/privacy/warning codes only; never logs content, handles, filenames, raw local paths, or raw exceptions.

## Implemented v1.4 Surface

Tools:

- `calendar_search(query: str, limit: int = 20, days_back: int = 365, days_forward: int = 730)`
- `calendar_get_event(handle: str, max_chars: int = 4000, days_back: int = 365, days_forward: int = 730)`
- `local-apple-data calendar search --json --query '<event title text>' --limit 20`
- `local-apple-data calendar get --json --handle '<calendar:event:v1:...>' --max-chars 4000`

Behavior:

- Uses a local Swift EventKit helper.
- Does not request Calendar permission automatically; if the current process is not authorized, returns `calendar_access_unavailable`.
- Searches Calendar events by title only.
- Rejects empty and broad title queries before EventKit access.
- Returns event title, calendar title, start/end dates, all-day flag, availability, presence/count metadata, and opaque handle without raw EventKit identifiers.
- Reads event location and notes only for exact selected event handles.
- Defaults to 4000 notes characters and hard-caps at 12000.
- Rejects raw EventKit identifiers, fabricated handles, broad Calendar dumps, mutations, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs event notes, locations, raw EventKit identifiers, or raw exceptions.

## Implemented v1.5 Surface

Tools:

- `reminders_eventkit_search(query: str, limit: int = 20, include_completed: bool = False)`
- `reminders_get_content(handle: str, max_chars: int = 4000)`
- `local-apple-data reminders eventkit-search --json --query '<reminder title text>' --limit 20`
- `local-apple-data reminders content --json --handle '<reminders:reminder:eventkit:v1:...>' --max-chars 4000`

Behavior:

- Uses the local Swift EventKit helper.
- Does not request Reminders permission automatically; if the current process is not authorized, returns `reminders_access_unavailable`.
- Searches Reminders by title only.
- Rejects empty and broad title queries before EventKit access.
- Returns reminder title, list name, due/start dates, completion state, priority, presence/count metadata, and opaque handle without raw EventKit identifiers.
- Reads reminder notes only for exact selected EventKit reminder handles.
- Defaults to 4000 notes characters and hard-caps at 12000.
- Rejects raw EventKit identifiers, legacy SQLite reminder handles, fabricated handles, broad Reminder dumps, mutations, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs reminder notes, raw EventKit identifiers, or raw exceptions.

## Implemented v1.6 Surface

Tools:

- `contacts_search(query: str, limit: int = 20, max_scan_contacts: int = 10000)`
- `contacts_get(handle: str, max_chars: int = 4000, max_scan_contacts: int = 10000)`
- `local-apple-data contacts search --json --query '<name or organization text>' --limit 20`
- `local-apple-data contacts get --json --handle '<contacts:contact:v1:...>' --max-chars 4000`

Behavior:

- Uses a local Swift Contacts.framework helper around `CNContactStore`.
- Does not request Contacts permission automatically; if the current process is not authorized, returns `contacts_access_unavailable`.
- Searches Contacts by display name, given name, family name, nickname, organization, department, or job title only.
- Rejects empty and broad queries before Contacts.framework access.
- Returns contact display name, type, organization/job metadata, presence/count metadata, and opaque handle without raw Contacts identifiers.
- Reads exact selected contact details including email addresses, phone numbers, postal addresses, URL addresses, birthdays, dates, social profiles, instant-message addresses, and contact relations.
- Does not fetch Contact notes because `CNContactNoteKey` requires Apple’s `com.apple.developer.contacts.notes` entitlement on macOS 13 and later.
- Does not return image bytes inline; exact selected asset export writes to a caller-selected output directory.
- Rejects raw Contacts identifiers, fabricated handles, broad Contacts dumps, mutations, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs contact details, raw Contacts identifiers, or raw exceptions.

## Implemented v1.7 Surface

Tools:

- `photos_search(query: str, limit: int = 20, media_type: str = "all", max_scan_assets: int = 5000)`
- `photos_get_asset(handle: str, max_scan_assets: int = 5000)`
- `local-apple-data photos search --json --query '<original filename text>' --limit 20`
- `local-apple-data photos get --json --handle '<photos:asset:v1:...>'`

Behavior:

- Uses a local Swift PhotoKit helper.
- Does not request Photos permission automatically; if the current process is not authorized, returns `photos_access_unavailable`.
- Searches Photos assets by original filename only, with optional media-type filter.
- Rejects empty and broad filename queries before PhotoKit access.
- Returns media type, dimensions, dates, favorite/hidden flags, source type, primary filename, resource count, and opaque handle without raw Photos identifiers.
- Reads asset resource filenames, resource types, and uniform type identifiers only for exact selected asset handles.
- Does not return image/video bytes inline, thumbnails, raw Photos identifiers, or source paths.
- Exact selected asset export writes to a caller-selected output directory with local PhotoKit network access disabled.
- Rejects raw Photos identifiers, fabricated handles, broad Photos dumps, mutations, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs raw Photos identifiers, asset bytes, export paths, or raw exceptions.

## Implemented v1.8 Surface

Tools:

- `messages_search(query: str, limit: int = 20)`
- `messages_get_chat(handle: str, max_messages: int = 25, max_chars: int = 4000)`
- `local-apple-data messages search --json --query '<chat display name text>' --limit 20`
- `local-apple-data messages get --json --handle '<messages:chat:v1:...>' --max-messages 25 --max-chars 4000`

Behavior:

- Uses a read-only/query-only SQLite connection to the local Messages `chat.db`.
- Searches Messages chats by `chat.display_name` only.
- Rejects empty and broad chat-display-name queries before opening the Messages store.
- Returns chat display name, service name, participant count, message count, last message date, and opaque handle without raw chat GUIDs, message row IDs, handle IDs, phone numbers, or email addresses.
- Reads bounded recent transcript text only for exact selected `messages:chat:v1:` handles.
- Defaults to 25 messages and 4000 transcript characters; hard-caps at 100 messages and 12000 transcript characters.
- Rejects raw Messages identifiers, fabricated handles, broad Messages text search, attachments, contact resolution, send/edit/delete paths, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs transcript text, participant identifiers, raw Messages identifiers, local database paths, or raw exceptions.

## Implemented v1.9 Surface

Tools:

- `voice_memos_search(query: str, limit: int = 20)`
- `voice_memos_get_recording(handle: str, max_chars: int = 4000)`
- `local-apple-data voice-memos search --json --query '<recording title text>' --limit 20`
- `local-apple-data voice-memos get --json --handle '<voice_memos:recording:v1:...>' --max-chars 4000`

Behavior:

- Uses a read-only/query-only SQLite connection to the local Voice Memos `CloudRecordings.db`.
- Searches Voice Memos by recording title or filename only.
- Rejects empty and broad title/filename queries before opening the Voice Memos store.
- Returns title, recorded date, duration, local audio availability, and opaque handle without raw recording IDs, unique IDs, local paths, filenames, audio bytes, or transcript text.
- Reads existing Apple-generated transcript JSON only for exact selected `voice_memos:recording:v1:` handles when the local `.m4a` contains a `tsrp` atom.
- Defaults to 4000 transcript characters and hard-caps at 12000.
- Does not return audio bytes inline, raw recording paths, or generated transcription.
- Exact selected audio export writes to a caller-selected output directory and does not expose the source recording path.
- Rejects raw Voice Memos identifiers, fabricated handles, broad transcript search, generated transcription, mutations, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs transcript text, recording identifiers, local paths, filenames, raw database rows, or raw exceptions.

## Implemented v1.10 Surface

Tools:

- `hide_my_email_search(query: str, limit: int = 20)`
- `hide_my_email_get_alias(handle: str)`
- `local-apple-data hide-my-email search --json --query '<specific alias substring>' --limit 20`
- `local-apple-data hide-my-email get --json --handle '<hide_my_email:alias:v1:...>'`

Behavior:

- Uses a read-only/query-only SQLite connection to the local Mail Envelope Index.
- Searches Mail address metadata only, not message bodies.
- Rejects empty, wildcard-only, domain-only, and generic Hide My Email queries before opening the Mail store.
- Returns masked alias previews, domain, inference kind, confidence, sender/recipient/message counts, last seen date, provenance, opaque handle, and `authoritative_inventory:false`.
- Reads the full alias only for exact selected `hide_my_email:alias:v1:` handles.
- Classifies `privaterelay.appleid.com` aliases as high-confidence Sign in with Apple private relay evidence.
- Classifies random-looking iCloud aliases with separators and digits as medium-confidence possible Hide My Email aliases from local Mail evidence.
- Does not claim authoritative iCloud inventory and does not create, deactivate, delete, or manage aliases.
- Rejects raw Hide My Email identifiers, fabricated handles, broad domain searches, iCloud.com/browser automation, private iCloud web APIs, keychain credentials, mutations, background indexing, and durable content caches.
- Logs command/status/privacy/warning codes only; never logs full aliases, raw Mail paths, raw database rows, raw identifiers, or raw exceptions.

## Expansion Roadmap

v1.11 Other iCloud-Backed Stores:

- Inventory local stores and official APIs first.
- Add each surface only after a threat-model and test gate.
- Prefer exact-handle content retrieval over broad content search.

## Publishable Standard

Before publishing:

- Replace operator-specific copy with generic user-facing plugin text.
- Keep personal plugin install docs separate from public README.
- Add a public privacy model that explains TCC, Full Disk Access, Automation permissions, and local-only execution.
- Add a capability matrix for each Apple surface: API used, read support, write support, permissions, tested macOS versions, and known limitations.
- Add CI that runs synthetic tests, compile checks, plugin validation where available, and redaction scans.
- Add no telemetry.
- Keep all tests synthetic and fixture-only.

## v1.2 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Notes narrowly for a note I name, select only the exact opaque notes:note:v2 handle from the search result, and call notes_get_content with max_chars 1200. Do not print the note body unless I explicitly ask; report status, content_chars, truncated, and warning codes.
```

## v1.3 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search iCloud Drive narrowly by filename text I provide, select only the exact opaque icloud:file:v1 handle from the search result, and call icloud_drive_get_content with max_chars 1200 if the selected item is a supported text file. Do not print the file content unless I explicitly ask; report status, content_chars, truncated, and warning codes.
```

## v1.4 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Calendar narrowly by event title text I provide, select only the exact opaque calendar:event:v1 handle from the search result, and call calendar_get_event with max_chars 1200. Do not print event notes or location unless I explicitly ask; report status, notes_chars, notes_truncated, authorization_status, and warning codes.
```

## v1.5 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Reminders narrowly by title text I provide using reminders_eventkit_search, select only the exact opaque reminders:reminder:eventkit:v1 handle from the search result, and call reminders_get_content with max_chars 1200. Do not print reminder notes unless I explicitly ask; report status, notes_chars, notes_truncated, authorization_status if present, and warning codes.
```

## v1.6 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Contacts narrowly by name or organization text I provide using contacts_search, select only the exact opaque contacts:contact:v1 handle from the search result, and call contacts_get with max_chars 1200. Do not print contact detail fields unless I explicitly ask; report status, email_count, phone_count, note_status, authorization_status if present, and warning codes.
```

## v1.7 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Photos narrowly by original filename text I provide using photos_search, select only the exact opaque photos:asset:v1 handle from the search result, and call photos_get_asset. If I ask to export it, call photos_export_asset with my requested output directory. Do not print Photos asset/resource metadata unless I explicitly ask; report status, media_type, primary_filename, resource_count, asset_content_returned, asset_content_exported when exporting, authorization_status if present, and warning codes.
```

## v1.8 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Messages narrowly by chat display-name text I provide using messages_search, select only the exact opaque messages:chat:v1 handle from the search result, and call messages_get_chat with max_messages 10 and max_chars 1200. Do not print transcript text unless I explicitly ask; report status, message_count_returned, content_chars, truncated, and warning codes.
```

## v1.9 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Voice Memos narrowly by recording title text I provide using voice_memos_search, select only the exact opaque voice_memos:recording:v1 handle from the search result, and call voice_memos_get_recording with max_chars 1200. If I ask to export it, call voice_memos_export_audio with my requested output directory. Do not print transcript text unless I explicitly ask; report status, transcript_status, transcript_chars, transcript_truncated, audio_content_returned, audio_content_exported when exporting, and warning codes.
```

## v1.10 Acceptance Prompt

Fresh-session acceptance:

```text
Use @local-apple-data. First run apple_data_health. Then search Hide My Email narrowly by a specific alias substring I provide using hide_my_email_search, select only the exact opaque hide_my_email:alias:v1 handle from the result, and call hide_my_email_get_alias. Do not print the full alias unless I explicitly ask; report status, alias_preview, confidence, provenance, authoritative_inventory, and warning codes. Do not use iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or network services.
```

## Stop Gates

- Stop if Notes.app automation prompts for access that the user has not approved.
- Stop if a content path requires printing raw database rows, raw paths, raw automation errors, or personal content into docs/logs.
- Stop before any mutation, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, background index, durable personal-content cache, iCloud.com/browser automation, private iCloud web/API access, network credential path, or cross-agent config mutation unless that exact action is explicitly approved.

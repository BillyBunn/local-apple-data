# Ecosystem Review

This review records the public-tooling research behind the current architecture. It is not a benchmark or endorsement list; it explains why this plugin chooses a broad, local-only, exact-handle design instead of cloning a single-surface MCP server.

## Current Pattern

The local Apple data ecosystem is not metadata-only. Current tools commonly expose note bodies, Messages transcripts, Voice Memos transcripts or audio, and in some cases write operations. That confirms the original metadata-only boundary was conservative, not an ecosystem requirement.

The durable design problem is not whether local content can be read. It is how to read it without broad dumps, durable personal-content indexes, raw local paths, guessed identifiers, private iCloud APIs, or ungated write tools.

## References Checked

### Notes

- `sweetrb/apple-notes-mcp` exposes Apple Notes through MCP, including note creation, search, full note reads, updates, deletes, folder management, exports, attachments, sync awareness, and diagnostics. It uses AppleScript against Notes.app and targets Claude plus other MCP clients. Source: https://github.com/sweetrb/apple-notes-mcp
- `harperreed/notes-mcp` is another Apple Notes MCP implementation, using a standalone Go server shape. Source: https://github.com/harperreed/notes-mcp
- Apple Developer Forums confirm there is no public Apple Notes CRUD API; AppleScript works on macOS but is a limited automation interface rather than a cross-platform public framework. Source: https://developer.apple.com/forums/thread/813810

Architecture implication: Notes content retrieval and selected attachment export are appropriate for a local Mac plugin, but they should remain exact-handle and bounded. Notes create-note and append-text apply are appropriate only behind preview/apply/read-back gates because other Notes MCP servers expose broader writes, and that is exactly where privacy and accidental mutation risk rises.

### Messages

- `anipotts/imessage-mcp` is a read-only local iMessage MCP server. Its README describes local database access, read-only tool annotations, no uploads, and support for Claude Code, Cursor, Codex CLI, and other clients. Source: https://github.com/anipotts/imessage-mcp
- `carterlasalle/mac_messages_mcp` exposes querying and sending paths for Messages, including delivery logic and direct Messages database access. Source: https://github.com/carterlasalle/mac_messages_mcp
- `ReagentX/imessage-exporter` and independent schema notes document that Messages attachment metadata lives in `chat.db` via `attachment` and `message_attachment_join`, while attachment files can be missing locally when they were not downloaded from iCloud. Sources: https://github.com/ReagentX/imessage-exporter and https://johnlarkin1.github.io/2022/message-parser/
- `imessage-core` documents that modern `message.attributedBody` values use Apple's legacy typedstream/NSArchiver format and can be decoded for plaintext when `message.text` is empty. Source: https://docs.rs/imessage-core/latest/imessage_core/typedstream/index.html
- `iMessagePrinter` documents the same modern Messages pattern and uses native `NSUnarchiver` because the typedstream data is not an `NSKeyedUnarchiver` archive. Source: https://blog.fsck.com/agent-blog/2026/02/19/imessageprinter/
- `macos-messages` is another agent-oriented, read-only local Messages library/CLI and explicitly frames the value as letting terminal agents read local Messages without accessing Apple ID or modifying state. Source: https://macos-messages.readthedocs.io/en/latest/

Architecture implication: Messages reads are common enough to be expected, and modern transcript completeness requires `attributedBody` plaintext fallback instead of relying only on `message.text`. Native Swift/Foundation decoding is the most direct local path for this plugin because it avoids vendoring a partial typedstream parser while preserving bounded exact-handle behavior. Selected local attachment export is a reasonable read/export path, but it should stay exact-chat and exact-attachment directed because broad attachment export can become a large media dump and unavailable iCloud media can tempt private network fetches. Sending is implemented elsewhere, but this plugin should keep it narrower: exact existing chat only, no direct-recipient/new-chat/account-selection behavior, plan approval-token binding, Messages.app automation, local `chat.db` readback, and ghost-row detection.

### Mail

- `sweetrb/apple-mail-mcp` exposes Apple Mail through MCP, including message search/read, draft creation, immediate send, reply/forward, flag/read changes, deletion/move, mailbox/account operations, attachments, rules, and diagnostics. Source: https://github.com/sweetrb/apple-mail-mcp
- Apple Mail `.emlx` conversion/export tools document that normal `.emlx` files can contain MIME attachments, while some partial messages externalize attachment bytes. Sources: https://github.com/Crosten/emlx2mbox and https://github.com/LRGH/emlx2eml
- Apple Support documents that Mail can be automated through Script Editor and that scripts can create and send messages. Source: https://support.apple.com/guide/mail/automate-mail-tasks-mlhlp1120/mac
- The local Mail.app scripting dictionary exposes `outgoing message`, recipient objects, `save`, and `send`; compile-only checks confirm draft creation and save syntax on this Mac.

Architecture implication: Mail write operations are common in other MCP servers, but broad send/manage tools are too risky for this plugin's current privacy model. A save-only draft gate is the durable first Mail write path because it keeps the user in control of final sending and can be independently checked through the local Mail read surface when Drafts indexing is available. Selected Mail MIME attachment export is appropriate as an exact-handle read/export path, but externalized or partial-message attachments should report unavailable rather than using private network fetches or broad filesystem scans.

### Voice Memos

- `jwulff/apple-voice-memo-mcp` exposes Voice Memos metadata, audio access, transcript extraction, and generated transcription. Its README documents `CloudRecordings.db`, local `.m4a` files, and Apple's `tsrp` transcript atom. Source: https://github.com/jwulff/apple-voice-memo-mcp
- `Like-Butter/apple-voice-memo-MCP` uses a split bridge design to avoid granting the AI client Full Disk Access directly, and focuses on metadata, Apple-generated transcripts, local/offline operation, and reduced permission exposure. Source: https://github.com/Like-Butter/apple-voice-memo-MCP
- Apple Support documents that Voice Memos recordings can sync through iCloud across signed-in devices. Source: https://support.apple.com/guide/voice-memos/see-your-recordings-on-all-your-apple-devices-vma6cc4d0571/mac

Architecture implication: Voice Memos belongs in the broad local Apple data surface. Existing transcript and caller-selected export are reasonable read paths; generated transcription and broad transcript search should remain separate approval phases.

### iCloud Drive

- Apple Support documents that iCloud Drive and Desktop/Documents files appear locally on Mac and can be found through Finder/iCloud Drive. Source: https://support.apple.com/en-gb/109344

Architecture implication: local iCloud Drive text-file content can be exact-handle and file-system based, but binary extraction, broad content search, symlink traversal, hidden files, and network iCloud fetches should remain out of scope.

### Books

- Apple Support documents highlights and notes in Books on Mac and notes that the feature depends on book type. Source: https://support.apple.com/en-ae/guide/books/ibks3975f128/mac
- `jladicos/apple-books-highlights` exports Apple Books highlights and notes by reading the local Books SQLite databases after refreshing Books.app. Source: https://github.com/jladicos/apple-books-highlights
- BooknoteWorthy documents the local Apple Books `BKLibrary` and `AEAnnotation` SQLite files and exports annotations from those stores without uploading data. Source: https://oliwang.github.io/BooknoteWorthy/
- The OpenClaw Apple Books skill describes local read-only access to Books library metadata, highlights, notes, collections, and reading progress through the same local SQLite database family. Source: https://clawhub.ai/alexissan/apple-books

Architecture implication: Books belongs in the broad local Apple data surface. Existing tools prove that reading highlights and notes from local SQLite stores is normal, but this plugin should avoid broad annotation exports by default. The durable first tranche is specific-query metadata search plus selected-book annotations behind an opaque `books:book:v1:` handle, without book/chapter/PDF/EPUB text extraction, raw IDs, local paths, iCloud fetches, Books.app automation, or mutation.

### Podcasts

- Apple Support documents that followed shows, subscriptions, stations, and current play position sync across devices when the user signs in with the same Apple Account and enables Sync Library. Source: https://support.apple.com/guide/podcasts/sync-podcasts-across-devices-pod5c911347/mac
- Apple Podcasts & Privacy says Apple Podcasts syncs favorite categories, play position, and library contents, including followed shows, saved episodes, and stations. Source: https://www.apple.com/legal/privacy/data/en/apple-podcasts/
- `dado3212/apple-podcast-transcripts` is a local browser-based Apple Podcasts transcript viewer/exporter and documents local transcript/cache inputs. Source: https://github.com/dado3212/apple-podcast-transcripts
- Audioscrape's MCP integration exposes remote podcast/audio search and exact episode content with transcript/speaker information. Source: https://www.audioscrape.com/docs/integrations/mcp

Architecture implication: Podcasts belongs in the broad local Apple data surface because Apple treats the library and playback position as synced Apple data, and third-party tools show that transcript/audio-oriented podcast surfaces are expected. The durable first tranche should be stricter than those transcript/audio examples: specific-query show metadata, selected-show episode metadata, and bounded selected-episode descriptions behind opaque `podcasts:show:v1:` and `podcasts:episode:v1:` handles, without transcript text/export, audio bytes, feed/enclosure URLs, local paths, broad dumps, iCloud media fetches, Podcasts.app automation, or mutation.

### Music

- Apple Support documents Sync Library for Apple Music and iTunes Match as the way to make a user's music library available across devices signed in with the same Apple Account. Source: https://support.apple.com/en-us/118285
- `rinsuki/musicdb2sqlite` is a public parser/converter for Apple Music's local `Library.musicdb` format. Source: https://github.com/rinsuki/musicdb2sqlite
- `pitetb/AppMusicLibParser` is another public Apple Music library parser for extracting metadata from `Library.musicdb`. Source: https://github.com/pitetb/AppMusicLibParser
- A local probe on this Mac showed `~/Music/Music/Music Library.musiclibrary/Library.musicdb` is a proprietary data file rather than SQLite, so direct SQLite-style reads are not a stable first tranche.

Architecture implication: Music belongs in the broad local Apple data surface because Apple treats the library as synced Apple data. Parser projects show direct metadata extraction is possible, but vendoring or reverse-engineering the proprietary database is a bigger publication and maintenance risk. The durable first tranche is bounded Music.app automation for specific track/playlist metadata and exact-handle detail behind opaque `music:track:v1:` and `music:playlist:v1:` handles, without audio bytes, lyrics, file paths, raw identifiers, play history, ratings/favorites, playlist track dumps, playback/queue control, iCloud media fetches, raw database parsing, or mutation. A later native parser can be added only after a separate design proves synthetic fixtures, redaction, stable version handling, and no durable personal-content cache.

### TV

- Apple Support documents managing a local library in the Apple TV app on Mac, including library organization and media stored in the TV app. Source: https://support.apple.com/guide/tvapp-mac/manage-your-library-atvbe9ddc3f/mac
- A local probe on this Mac showed `~/Movies/TV/TV Library.tvlibrary/Library.tvdb` is a proprietary data file rather than SQLite, so direct SQLite-style reads are not a stable first tranche.

Architecture implication: TV belongs in the broad local Apple data surface because TV.app manages local Apple media library metadata and iCloud-backed purchases/downloads. The durable first tranche should match the Music safety model: bounded TV.app automation for specific item/playlist metadata and exact-handle detail behind opaque `tv:item:v1:` and `tv:playlist:v1:` handles, without video bytes, file paths, artwork, descriptions, raw identifiers, playback or watched state, ratings/favorites, playlist item dumps, playback/queue control, iCloud media fetches, raw library parsing, or mutation.

### Freeform

- Apple Support documents that Freeform boards stored in iCloud stay up to date across Apple devices signed in with the same Apple Account. Source: https://support.apple.com/guide/freeform/get-started-frfm85d6f7b58/mac
- A local schema-only probe on this Mac showed Freeform stores board metadata in `~/Library/Group Containers/group.com.apple.freeform/Boards/boards.db`, with board content/title data in BLOB/CRDT columns and folder titles in a plain `folders.title` column.

Architecture implication: Freeform belongs in the broad local Apple data surface because Apple treats boards as iCloud-synced app data. The durable first tranche should avoid BLOB/CRDT decoding and asset extraction: capped recent-board metadata, folder-title search, and exact board/folder metadata behind opaque `freeform:board:v1:` and `freeform:folder:v1:` handles, without board title/content extraction, decoded board item dumps, assets, previews, collaboration payloads, raw identifiers/rows, Freeform.app automation, or mutation.

### Safari

- `MrGo2/icloud-mcp` includes Safari as one of its local-mode services and advertises Safari tab access in examples. Source: https://github.com/MrGo2/icloud-mcp
- `krmj22/macos-mcp` documents a broad local macOS MCP pattern using EventKit, JXA, and SQLite/local database reads across Apple apps. Source: https://github.com/krmj22/macos-mcp

Architecture implication: Safari belongs on the broader local Apple data roadmap, but the first durable tranche should be lower-risk than tabs/history/browser automation. Local `Bookmarks.plist` supports bookmark and Reading List search/detail without touching browser sessions, page content, cookies, passwords, private browsing state, or live Safari UI.

### Shortcuts

- Apple Support documents the local `shortcuts` command, including `shortcuts list`, `shortcuts list --folders`, `shortcuts run`, `shortcuts view`, and `shortcuts sign`. Source: https://support.apple.com/guide/shortcuts-mac/apd455c82f02/mac
- Public Shortcuts MCP examples commonly expose list/open/run operations and parse `shortcuts list --show-identifiers` output as `Name (UUID)`. Source: https://glama.ai/mcp/servers/%40dvcrn/mcp-server-siri-shortcuts/blob/49d67127ba8373300d0c9d94c059b4c873bf2ef8/shortcuts.ts

Architecture implication: Shortcuts belongs in the broad local Apple data surface, but the first durable tranche should stop at shortcut/folder name metadata. Running, opening, signing, exporting, inspecting bodies, or creating dynamic per-shortcut run tools can trigger app behavior, reveal automation internals, contact Apple services, or mutate user workflows.

### Official Apple Frameworks

- EventKit is Apple's framework family for Calendar and Reminders. Source: https://developer.apple.com/documentation/eventkit
- Contacts.framework exposes `CNContactStore` for Contacts access. Source: https://developer.apple.com/documentation/contacts/cncontactstore
- PhotoKit provides Photos fetch and change APIs. Source: https://developer.apple.com/documentation/photokit/fetching_objects_and_requesting_changes

Architecture implication: Calendar, Reminders, Contacts, and Photos should use native framework helpers instead of scraping app databases where public frameworks exist. Writes are possible in those frameworks but must stay behind mutation gates.

## Design Position

This plugin should be broader than single-surface MCP servers and stricter than most single-surface examples:

- Broad surface: Mail, Messages, inferred Hide My Email aliases, Voice Memos, Safari bookmarks/Reading List, Shortcuts metadata, Books metadata/selected-book annotations, Podcasts metadata/selected-episode descriptions, Music track/playlist metadata, TV item/playlist metadata, Freeform board/folder metadata, Notes, iCloud Drive, Calendar, Reminders, Contacts, and Photos.
- Local-only transport: stdio MCP and CLI through local files/frameworks only.
- Metadata-first search: narrow query gates before local store/framework access.
- Exact-handle content: content/detail/export requires opaque handles returned by matching search tools.
- Bounded output: caps, truncation fields, and stable warning codes.
- No durable content cache: avoid persistent personal-content indexes.
- No private network paths: no Gmail API, IMAP, OAuth, iCloud.com, browser sessions, keychain credentials, or private iCloud APIs.
- Cross-client packaging: Codex plugin and skill, generic MCP config, Claude Code, Cursor, and OpenClaw config renderers.
- Release gates: redaction scan, public release scan, mutation-gate audit, surface-contract audit, release-readiness audit, public tree staging, committed public git checkout preparation, and path-redacted release receipts.

## Open Decisions

- Whether to add a small privileged helper architecture for users who do not want their AI client process to hold Full Disk Access.
- Whether future generated transcription belongs in this plugin or a separate transcription tool connected by handles.
- Whether future write support after the approved Reminders, iCloud Drive create/append-text, Calendar, Contacts, Notes create/append-text, Mail draft, Photos import, Messages exact-chat send-text, Safari bookmark/Reading List reads, Shortcuts metadata reads, Books metadata/selected annotation reads, Podcasts metadata/selected-episode description reads, Music metadata reads, TV metadata reads, Freeform metadata reads, and Mail/Messages/Notes attachment export tranches should prioritize Mail send, richer Messages mutation, Photos edit/delete/album support, arbitrary Notes update/delete/move, Safari history/tabs/bookmark mutation, Shortcuts run/import/export, Books richer export/mutation, Podcasts transcript/audio export or mutation, Music/TV native parsing/playback/library mutation, Freeform BLOB decoding/asset export/mutation, or richer framework-backed edits.
- Whether public registry packaging should target npm, PyPI, a Codex personal marketplace, Smithery-style registries, or only GitHub source installation first.

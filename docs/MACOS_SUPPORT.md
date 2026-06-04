# macOS Support

## Current Test Baseline

- Local development smoke: macOS 26.5, build 25F71.
- CI: GitHub Actions `macos-latest`, synthetic fixtures only.

The project is expected to need macOS because it depends on local Apple stores and Apple frameworks. Older macOS releases may work when the local database schemas and framework permissions match, but support should be verified with the test suite and `health` command before relying on a surface. Health checks are non-prompting: they verify local store presence/readability and supported schema fingerprints where practical, and they report framework access requirements without requesting Calendar, Reminders, Contacts, Photos, or Automation permission.

## Client App Permissions

macOS privacy grants are per host process. A CLI run from Terminal can report `health.status: "ok"` while a GUI MCP client such as Claude Desktop reports `health.status: "degraded"` because that app does not have Full Disk Access or framework permission. In that case the plugin is connected, but local stores behind TCC may be unreadable from that client.

For GUI clients, grant the client app the same privacy access expected for the surfaces you intend to use, then restart the app and rerun `apple_data_health`. At minimum, broad local-store surfaces such as Mail, Messages, Voice Memos, Safari, Freeform, Notes, Books, Podcasts, and legacy Reminders metadata may require Full Disk Access for the client process. Exact apply tools may also require app-specific Automation, Calendar, Reminders, Contacts, or Photos permission depending on the surface.

## Framework And Store Map

| Surface | Local mechanism | Permission class |
| --- | --- | --- |
| Mail | Mail.app local metadata and `.emlx` content/attachment MIME files plus save-only Mail.app automation for approved create-draft apply | Full Disk Access and Automation may be required |
| Messages | Messages local `chat.db`, native `NSUnarchiver` plaintext fallback for exact selected `attributedBody` rows, local attachment files for exact selected-chat attachment export, and Messages.app automation for approved send-text apply | Full Disk Access may be required for local stores; Automation permission may be required for send apply |
| Hide My Email | Inferred local Mail address metadata | Full Disk Access may be required |
| Voice Memos | Voice Memos local database and embedded transcript atom | Full Disk Access may be required |
| Safari | Safari local `Bookmarks.plist` for bookmarks and Reading List items | Full Disk Access may be required |
| Shortcuts | Apple `shortcuts` command-line interface | Shortcuts CLI availability |
| Books | Apple Books local `BKLibrary` and `AEAnnotation` SQLite stores | Full Disk Access may be required |
| Podcasts | Apple Podcasts local `MTLibrary.sqlite` store | Full Disk Access may be required |
| Music | Music.app automation plus local Music library package readiness | Automation permission may be required |
| TV | TV.app automation plus local TV library package readiness | Automation permission may be required |
| Freeform | Apple Freeform local `boards.db` store | Full Disk Access may be required |
| Notes | Local Notes SQLite plus bounded Notes.app automation for exact content and approved create/append-text apply; local Notes media files for exact attachment export | Full Disk Access and Automation may be required |
| Calendar | EventKit helper | Calendar permission |
| Reminders | EventKit helper plus legacy SQLite metadata | Reminders permission |
| Contacts | Contacts.framework helper | Contacts permission |
| Photos | PhotoKit helper | Photos permission |
| iCloud Drive | Local filesystem under the user's iCloud Drive location | Local file access |

## Degraded Behavior

Permission, schema, or local sync problems should return structured warning codes. They should not print raw database rows, raw framework identifiers, local file paths, private content, or raw system exception strings.

Expected degraded cases include:

- Local store unavailable.
- Permission not granted.
- Private Apple schema changed.
- Requested iCloud Drive file is not downloaded locally.
- Requested content type is intentionally unsupported.
- Exact handle is invalid, stale, or fabricated.

## Public Support Notes

- This is not an iCloud web client.
- It does not manage iCloud account state.
- Hide My Email support is inferred from local Mail evidence, not an authoritative iCloud inventory.
- Messages support returns bounded transcripts from local text or attributed-body plaintext fallback, can export one exact selected attachment to a caller-selected output directory, and can send one approved plaintext message to an exact existing chat only after plan approval-token and explicit-confirmation checks. It does not return participant identifiers, raw attributed-body blobs, source media paths, inline attachment bytes, sent body text in apply output, or fetch unavailable iCloud media.
- Photos support returns asset/resource metadata, can export one exact selected asset to a caller-selected output directory, and can import one caller-selected image/video source file after plan approval. It does not return image or video bytes inline and does not edit, delete, target albums, mutate metadata, or fetch iCloud media over the network.
- Voice Memos support returns existing embedded transcript text when present and can export one exact selected `.m4a` to a caller-selected output directory; it does not generate transcripts.
- Safari support returns bookmark and Reading List title/domain metadata during search and full URLs only by exact `safari:item:v1:` handle. It does not read history, open tabs, private browsing data, passwords, cookies, browser caches, page content, or mutate bookmarks.
- Shortcuts support returns shortcut/folder name metadata by specific query and exact `shortcuts:item:v1:` handle. It does not run, open, view, sign, export, return bodies/action graphs, expose raw identifiers, or mutate shortcuts.
- Books support returns title/author/genre/read-state metadata by specific query and selected-book annotations only by exact `books:book:v1:` handle. It does not extract book/chapter/PDF/EPUB text, perform broad annotation dumps or searches, expose raw asset IDs/annotation UUIDs/local paths, fetch iCloud content, automate Books.app, or mutate Books data.
- Podcasts support returns show metadata by specific query, selected-show episode metadata by exact `podcasts:show:v1:` handle, and bounded selected-episode descriptions only by exact `podcasts:episode:v1:` handle. It does not return transcripts, audio/video bytes, feed/enclosure/web URLs, local download paths, expose raw identifiers, fetch iCloud media, automate Podcasts.app, or mutate Podcasts data.
- Music support returns bounded track and playlist metadata by specific query and exact `music:track:v1:` or `music:playlist:v1:` handle. It does not return audio bytes, lyrics, file paths, raw identifiers, play history, ratings/favorites, playlist track dumps, playback/queue state, fetch iCloud media, or mutate Music data.
- TV support returns bounded item and playlist metadata by specific query and exact `tv:item:v1:` or `tv:playlist:v1:` handle. It does not return video bytes, file paths, artwork, descriptions, raw identifiers, playback state, watched state, ratings/favorites, playlist item dumps, fetch iCloud media, or mutate TV data.
- Freeform support returns capped recent-board metadata and folder-title metadata by exact `freeform:board:v1:` or `freeform:folder:v1:` handle. It does not decode board BLOB/CRDT data, return board titles/content, dump decoded board items, export assets, return previews/collaboration payloads/raw identifiers/raw rows, automate Freeform.app, or mutate Freeform data.
- Write and mutation tools require separate approval gates before implementation. The current Mail write gate is limited to save-only draft creation; it does not send mail. The current Photos write gate is limited to importing one local image or video file; it does not edit or delete Photos assets. The current Messages write gate is limited to send-text apply for one exact existing chat; it does not support direct recipients, new chats, SMS fallback selection, file sends, reactions, edit, or delete.

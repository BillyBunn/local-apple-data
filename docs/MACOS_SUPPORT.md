# macOS Support

## Current Test Baseline

- Local development smoke: macOS 26.5, build 25F71.
- CI: GitHub Actions `macos-latest`, synthetic fixtures only.

The project is expected to need macOS because it depends on local Apple stores and Apple frameworks. Older macOS releases may work when the local database schemas and framework permissions match, but support should be verified with the test suite and `health` command before relying on a surface. Health checks are non-prompting: they verify local store presence/readability and supported schema fingerprints where practical, and they report framework access requirements without requesting Calendar, Reminders, Contacts, Photos, or Automation permission. Calendar, Reminders, Contacts, and Photos consent prompts are explicit CLI-only opt-in commands: `local-apple-data calendar request-access --json`, `local-apple-data reminders request-access --json`, `local-apple-data contacts request-access --json`, and `local-apple-data photos request-access --json`. If Photos request-access times out with `authorization_status:"not_determined"`, approve `Local Apple Data Photos Helper` manually under Privacy & Security > Photos; if it returns `authorization_status:"limited"`, change Photos access for the helper to full access before using regular-album management.

## Client App Permissions

macOS privacy grants are keyed to the responsible code identity. Full Disk
Access and Automation may belong to a host client, while Calendar, Reminders,
Contacts, and Photos grants for this project belong to the signed helper apps.
A CLI run from Terminal can therefore differ from a GUI MCP client for local
store or Automation access even when both use the same framework-helper grants.

For GUI clients, grant the client app the Full Disk Access and Automation
needed by the surfaces you intend to use, then restart the app and rerun
`apple_data_health`. Use the explicit signed-helper request commands below for
Calendar, Reminders, Contacts, and Photos; do not grant those framework
permissions to a generic interpreter as a substitute.

Claude Desktop has a second process identity that matters. The desktop app bundle is `com.anthropic.claudefordesktop`, but Desktop local-agent sessions can launch an embedded Claude Code helper from:

```text
~/Library/Application Support/Claude/claude-code/<version>/claude.app
```

That helper is signed as `com.anthropic.claude-code` and then launches the local MCP server. If `com.anthropic.claudefordesktop` has Full Disk Access but `com.anthropic.claude-code` is denied, Desktop can still connect to `local-apple-data` while returning local-store or Automation warnings. Grant Full Disk Access to both Claude Desktop and the embedded Claude Code helper when those host-level surfaces need it. Calendar and Reminders grants are keyed to the configured EventKit helper identity (default `com.local-apple-data.eventkit-helper`); Contacts is keyed to `com.local-apple-data.contacts-helper`; Photos is keyed to the configured PhotoKit helper identity (default `com.local-apple-data.photos-helper`). Use the explicit request-access commands after TCC resets.

The signed-helper bundle identifiers are configurable so an operator with an existing TCC grant can keep it after upgrading. Set `LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID` to override the Calendar/Reminders EventKit helper identifier (default `com.local-apple-data.eventkit-helper`) and `LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID` to override the Photos PhotoKit helper identifier (default `com.local-apple-data.photos-helper`). The value must match the bundle identifier the existing grant is keyed to; changing it rebuilds the helper app with the new identifier, which macOS treats as a new grant. Put durable machine-local assignments in mode-`0600` `~/Library/Application Support/local-apple-data/.env.operator` so direct CLI, source, personal-root, and installed-cache launches share the same identity unless an explicit helper-ID process environment variable overrides it. Only the two helper-ID keys and simple `export KEY=value` / `KEY=value` syntax are accepted; all other keys and shell syntax fail closed. The Python CLI/MCP entrypoint gives a checkout-local `.env.local` precedence. `LOCAL_APPLE_DATA_OPERATOR_ENV_FILE` selects another absolute file and fails closed if it is missing or unsafe.

## Signed Framework Helper One-Time Setup

macOS TCC presents the Calendar, Reminders, Contacts, and Photos consent prompts
to these helper processes only when they have a stable code-signing identity.
Run each needed request command once in a Terminal from the GUI login session:

```
uv run local-apple-data calendar request-access --json
uv run local-apple-data reminders request-access --json
uv run local-apple-data contacts request-access --json
uv run local-apple-data photos request-access --json
```

On a fresh machine the first run provisions a local self-signed code-signing certificate named `Local Apple Data Signing` in your login keychain (using `openssl` and `security`, both present on stock macOS), rebuilds the helper app signed with that identity, then triggers the consent prompt. Expect two dialogs the first time:

1. A keychain access dialog for the freshly imported signing key — click **Always Allow** so subsequent rebuilds sign without prompting.
2. The macOS consent prompt for the surface — allow access; choose full access for Calendar, Reminders, and Photos.

This setup is one-time. The certificate is self-signed, carries no personal identifiers, and is used only to sign the local helper apps; it grants no other trust. Provisioning and rebuilds happen only on the explicit request-access paths — read and mutation paths never provision or block on a prompt, and simply use whatever signature already exists.

Operators who prefer to sign with an existing certificate (for example an Apple Development identity) can set `LOCAL_APPLE_DATA_SIGNING_IDENTITY` to that identity's name; it takes precedence over the self-signed cert and suppresses provisioning. If no stable identity is resolvable, normal helper construction may fall back to ad-hoc signing, but explicit Calendar, Reminders, Contacts, and Photos request-access commands fail closed until a stable identity exists.

The locally self-signed Contacts helper intentionally omits Apple's restricted
`com.apple.developer.contacts.notes` entitlement because it requires a suitable
provisioning profile. Contact-note reads and mutations therefore fail closed;
ordinary Contacts operations remain available, and archive export omits notes.

### Known limitation: creating a brand-new Calendar/Reminders list in an iCloud source

Creating a *new* synthetic `LAD-TEST-*` Calendar calendar (or Reminders list) can fail with `eventkit_apply_failed` on an iCloud-backed account. This is a macOS/EventKit platform restriction, not a defect: `EKEventStore.saveCalendar` only reliably creates a new calendar/list in a **Local** (`sourceType == .local`) source, and iCloud/CalDAV sources reject programmatic creation. Accounts whose calendars all live in iCloud typically expose no writable Local source, so there is no source EventKit will accept a new calendar into. This affects only *new-calendar/new-list creation*; creating, updating, and deleting events or reminders inside existing calendars/lists is unaffected. To create a new calendar on such an account, add it in Calendar.app (or enable a Local source) first.

## Framework And Store Map

| Surface | Local mechanism | Permission class |
| --- | --- | --- |
| Mail | Mail.app local metadata and `.emlx` content/attachment MIME files plus Mail.app automation for approved create-draft, send-message, reply-message, reply-all-message, forward-message, and exact-message read/flag/archive/move/trash apply | Full Disk Access and Automation may be required |
| Messages | Messages local `chat.db`, native `NSUnarchiver` plaintext fallback for exact selected `attributedBody` rows, local attachment files for exact selected-chat attachment export, and Messages.app automation for approved send-text/send-file apply | Full Disk Access may be required for local stores; Automation permission may be required for send apply |
| Hide My Email | Inferred local Mail address metadata | Full Disk Access may be required |
| Voice Memos | Voice Memos local database and embedded transcript atom | Full Disk Access may be required |
| Safari | Safari local `Bookmarks.plist` for bookmarks, Reading List items, and bookmark folders | Full Disk Access may be required |
| Shortcuts | Apple `shortcuts` command-line interface | Shortcuts CLI availability |
| Books | Apple Books local `BKLibrary` and `AEAnnotation` SQLite stores | Full Disk Access may be required |
| Podcasts | Apple Podcasts local `MTLibrary.sqlite` store | Full Disk Access may be required |
| Music | Music.app automation plus local Music library package readiness | Automation permission may be required |
| TV | TV.app automation plus local TV library package readiness | Automation permission may be required |
| Freeform | Apple Freeform local `boards.db` store | Full Disk Access may be required |
| Notes | Local Notes SQLite plus bounded Notes.app automation for exact content, folder metadata, approved default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty same-account child-folder move, append-text, replace-text, rich-text body create/replace, move-to-folder, and exact-note delete apply; local Notes media files for exact attachment export | Full Disk Access and Automation may be required |
| Calendar | EventKit helper | Calendar permission |
| Reminders | EventKit helper app plus legacy SQLite metadata; `reminders request-access` prompts the stable helper after TCC resets | Reminders permission |
| Contacts | Signed Contacts.framework helper app; `contacts request-access` is the explicit recovery path | Contacts permission |
| Photos | PhotoKit helper app with PhotoKit usage strings and Photos Library entitlement; `photos request-access` is the explicit prompt/manual-approval recovery path after TCC resets | Photos permission |
| iCloud Drive | Local filesystem under the user's iCloud Drive location for exact text-file content retrieval plus approved create-folder/create-folder-path, exact folder CRUD, create-text, append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply | Local file access |
| Filesystem | Local filesystem under the operator home directory for metadata/detail/export plus the same bounded plan/apply/read-back gates as iCloud Drive, re-rooted under the home directory with within-root and credential/secret-path guards | Local file access |

Supported iCloud Drive write gates include bounded folder path creation, exact regular-file rename/copy/move, import-file, replace-file, trash-file, and exact regular-file delete.

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
- Messages support returns bounded transcripts from local text or attributed-body plaintext fallback, can list exact selected-chat participant handles without phone/email previews, can return one exact selected participant identifier by original chat handle plus participant handle, can export one exact selected attachment to a caller-selected output directory, and can send one approved plaintext message or one approved local file to an exact existing chat only after plan approval-token and explicit-confirmation checks. It does not return participant identifiers outside exact participant detail, raw attributed-body blobs, source media paths, inline attachment bytes, file bytes, local file paths, sent body text in apply output, or fetch unavailable iCloud media.
- Photos support returns asset/resource metadata and regular-album metadata, can export one exact selected asset to a caller-selected output directory, and can import one caller-selected image/video source file, update exact favorite/hidden flags, delete one exact selected asset, add/remove one exact asset to/from one exact regular album, or create/rename/delete one exact regular album after plan approval. Regular-album management requires full Photos Library authorization. It does not return image or video bytes inline, permanently delete or empty Recently Deleted, target smart/shared/synced albums, run bulk album membership, edit content, mutate metadata outside exact favorite/hidden, or fetch iCloud media over the network.
- Voice Memos support returns existing embedded transcript text when present and can export one exact selected `.m4a` to a caller-selected output directory; it does not generate transcripts.
- Safari support returns bookmark and Reading List title/domain metadata during item search, full URLs only by exact `safari:item:v1:` handle, and folder/direct-child metadata only by exact `safari:folder:v1:` handle. It does not read history, open tabs, private browsing data, passwords, cookies, browser caches, page content, broad recursive dumps, or mutate bookmarks/folders.
- Shortcuts support returns shortcut/folder name metadata by specific query, exact shortcut/folder metadata by `shortcuts:item:v1:` handle, and exact selected-folder shortcut metadata by folder handle. It can run one exact identifier-bound shortcut through the approved plan-token/explicit-confirmation gate, invoked by argv under a hard timeout; success proves invocation only because arbitrary shortcut side effects cannot be independently read back. It does not run outside that gate, open, view, sign, export, return bodies/action graphs, expose raw identifiers or arbitrary folder-name filters, or mutate shortcut definitions.
- Books support returns title/author/genre/read-state metadata by specific query and selected-book annotations only by exact `books:book:v1:` handle. It does not extract book/chapter/PDF/EPUB text, perform broad annotation dumps or searches, expose raw asset IDs/annotation UUIDs/local paths, fetch iCloud content, automate Books.app, or mutate Books data.
- Podcasts support returns show metadata by specific query, selected-show episode metadata by exact `podcasts:show:v1:` handle, and bounded selected-episode descriptions only by exact `podcasts:episode:v1:` handle. It does not return transcripts, audio/video bytes, feed/enclosure/web URLs, local download paths, expose raw identifiers, fetch iCloud media, automate Podcasts.app, or mutate Podcasts data.
- Music support returns bounded track, playlist, and selected-playlist track metadata by specific query and exact `music:track:v1:` or `music:playlist:v1:` handle. It does not return audio bytes, lyrics, file paths, raw identifiers, play history, ratings/favorites, broad playlist track dumps, playback/queue state, fetch iCloud media, or mutate Music data.
- TV support returns bounded item, playlist, and selected-playlist item metadata by specific query and exact `tv:item:v1:` or `tv:playlist:v1:` handle. It does not return video bytes, file paths, artwork, descriptions, raw identifiers, playback state, watched state, ratings/favorites, broad playlist item dumps, fetch iCloud media, or mutate TV data.
- Freeform support returns capped recent-board metadata, folder-title metadata, exact selected-folder board metadata, and exact selected-folder child-folder metadata by exact `freeform:board:v1:` or `freeform:folder:v1:` handle. It does not decode board BLOB/CRDT data, return board titles/content, dump decoded board items, export assets, return previews/collaboration payloads/raw identifiers/raw rows, automate Freeform.app, or mutate Freeform data.
- New write and mutation classes require separate design and approval gates before implementation. The current release exposes 14 approved MCP apply tools. The current Mail write gate is limited to save-only draft creation with optional exact `mail:sender:v1:` sender selection and optional bounded caller-selected local file attachments, bounded send-message/reply-message/reply-all-message/forward-message with optional exact `mail:sender:v1:` sender selection and optional bounded caller-selected local file attachments, exact-message forward-message with default source-part refusal and optional source attachment-like part preservation through explicit `include_source_attachments`, exact-message or capped exact bulk read/flag/archive/move/trash triage, synthetic top-level `LAD-TEST-*` mailbox create/rename/delete, and synthetic-only permanent delete/empty Trash/Junk cleanup; it does not select sender accounts outside the approved draft/send/reply/reply-all/forward sender gate, forward source attachments or non-body source parts outside explicit `include_source_attachments`, forward outside the approved exact-message forward-message gate, run query-result auto-apply, run unbounded bulk mutation, permanently delete non-synthetic messages, empty Trash/Junk when any non-synthetic target is present, or manage real mailboxes/accounts. Mail sender/signature metadata and apply paths may require Automation permission. Send-message, reply-message, reply-all-message, and forward-message apply are irreversible, require a matching approval token plus explicit confirmation, and do not echo sent body or source content in apply output; source-forward apply verifies Mail's attachment count before send and returns no per-part Sent identity/content proof; synthetic cleanup requires absence proof before success. The current iCloud Drive write gate is limited to exact text-file create/append/replace/trash/delete/rename/copy/move, exact regular-file rename/copy/move/import/replace/trash/delete, exact child-folder create, exact folder rename/trash/move/copy/delete, and requires approval-token checks, expected current SHA-256 or file/directory metadata SHA-256 where applicable, exact file identity binding for delete-text, expected metadata binding for delete-file, no-overwrite target controls, hidden staging identity proof for permanent delete gates, metadata-only regular-file read-back with no returned content hash, and read-back/absence proof. It does not permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate unbounded folder copy, recursive folder writes, or unbounded recursive folder delete, write binary/document content, follow symlinks/packages, or accept raw paths. The current Notes write gate is limited to default/exact-folder note create, exact child-folder create under one exact normal parent folder, exact-folder rename, exact empty child-folder delete, exact empty same-account child-folder move, exact-note append/replace/delete/move-to-folder, and exact rich-text body create/replace with approval-token checks and content, parent, folder, rename, or absence proof. It does not delete root/non-empty/recursive folders, move folders outside the exact empty same-account child-folder gate, create root/default-account folders, mutate rich text outside the exact body create/replace gate, mutate attachments, or bulk-edit notes. The current Photos write gate is limited to importing one local image or video file, exact asset favorite/hidden update, exact selected-asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete with full Photos Library authorization; it does not edit asset content, permanently delete or empty Recently Deleted, target smart/shared/synced albums, or run bulk membership. The current Messages write gate is limited to send-text/send-file apply for one exact existing chat; it does not support direct recipients, new chats, SMS fallback selection, reactions, edit, or delete. The current Filesystem write gate reuses the bounded iCloud Drive plan/apply/read-back operations under the operator home directory with within-root and credential/secret-path guards. The current Shortcuts write gate runs one exact identifier-bound shortcut only after the matching plan token and explicit confirmation, under a hard timeout, and proves invocation rather than arbitrary side effects.
  exact regular-file delete is limited to the iCloud Drive delete-file gate.

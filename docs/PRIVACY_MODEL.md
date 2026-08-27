# Privacy Model

This project handles local personal-data surfaces. The default is metadata-first and read-only for discovery/content retrieval, with content retrieval exposed only through exact opaque handles and bounded output. The only approved mutation surfaces are Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact URL update/clear/exact absolute/relative/mixed display-alarm set/clear/start-date set/clear/recurrence create/update/clear/exact same-source list-move/delete apply and exact list create/rename/empty-delete/same-source migrate-delete apply, iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply, Calendar create-event/update/delete apply including exact target-calendar, date-only all-day, relative-or-absolute display/audio/email/geofence alarm, explicit timed-event time-zone, exact availability, simple count-, end-date-, or explicit-unbounded recurrence, selected-occurrence recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, selected/future-span/whole-series recurring-event delete, and explicit default-calendar create-planning gates, plus synthetic `LAD-TEST-*` Calendar calendar create/rename/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete apply with full Photos Library authorization, and Messages send-text/send-file apply, home-directory Filesystem create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply rooted at the operator home directory reusing the exact iCloud Drive within-root plan/apply/read-back gates with a credential/secret path denylist, and Shortcuts run apply of one exact identifier-bound shortcut through the plan/apply approval-token/confirm gate, resolved by an exact `shortcuts:item:v1:` handle with the resolved identifier bound into the approval fingerprint, invoked by argv (never a shell string) under a hard execution timeout, proving invocation of the named shortcut only because a shortcut's arbitrary side effects are not verifiable by read-back through plan/apply/read-back gates.

## Data Tiers

1. Health: tool availability, macOS version, and store presence/readability only.
2. Metadata: bounded subjects/titles/snippets, Mail mailbox target metadata, date-bounded selected-mailbox Mail message metadata, and Mail content-availability hints only when the user asks for the workflow.
3. Content/detail/export: exact-handle retrieval for Mail, Mail selected-mailbox message metadata, Messages chats, Messages participants, inferred Hide My Email aliases, Voice Memos, Safari bookmarks/Reading List URLs and selected-folder metadata/direct-child listings, Shortcuts metadata/selected-folder shortcut metadata, Books metadata/selected-book annotations, Podcasts metadata/selected-episode descriptions, Music track/playlist/selected-playlist track metadata, TV item/playlist/selected-playlist item metadata, Freeform board/folder/selected-folder board/child-folder metadata, Notes, Notes folders, Calendar events, Contacts, Contact groups, Photos asset/resource metadata and selected-album child asset metadata, Reminders, supported iCloud Drive text files, exact selected iCloud Drive regular-file export, and bounded home-directory Filesystem metadata/content/export after the metadata flow returns a `mail:message:v2:`, `mail:mailbox:v1:`, `messages:chat:v1:`, `messages:participant:v1:`, `hide_my_email:alias:v1:`, `voice_memos:recording:v1:`, `safari:item:v1:`, `safari:folder:v1:`, `shortcuts:item:v1:`, `books:book:v1:`, `podcasts:show:v1:`, `podcasts:episode:v1:`, `music:track:v1:`, `music:playlist:v1:`, `tv:item:v1:`, `tv:playlist:v1:`, `freeform:board:v1:`, `freeform:folder:v1:`, `notes:note:v2:`, `notes:folder:v1:`, `calendar:event:v1:`, `contacts:contact:v1:`, `contacts:group:v1:`, `photos:asset:v1:`, `photos:album:v1:`, `reminders:reminder:eventkit:v1:`, `reminders:list:eventkit:v1:`, `icloud:file:v1:`, or `fs:file:v1:` handle and the user explicitly requests that selected item. Media/file export tools additionally require a caller-selected output directory and do not return bytes inline or source paths.
4. Attachments: exact selected Mail, Messages, and Notes attachment metadata/export only, using the selected parent item handle plus selected attachment handle where required; Mail `attachment-search` may return date-bounded redacted text/PDF/OCR snippets with exact attachment handles and no bytes/paths; Mail draft/send/reply/reply-all/forward may attach bounded caller-selected local files through the approved plan/apply gates. Broad attachment export, inline bytes, source paths, remote fetches, and attachment mutation outside approved Messages send-file or Mail draft/send/reply/reply-all/forward local-file attachment gates remain blocked.
5. Local cache: `mail fts-build` / `mail_build_fts_index` may write an opt-in private SQLite FTS cache for a required date range only after explicit `confirm_index`; it may persist extracted Mail subject/header/body text and optional attachment text/PDF/OCR text in local private state, but output returns only counts, booleans, `next_cursor`, safe warning codes, and an opaque `index_ref`, never the cache path or raw cached text. Build rejects symlink/non-regular cache, ancestor, and sidecar paths, rejects `reset` on continuation cursors before touching the index, and reset validates then removes the private cache plus WAL/SHM/journal sidecars before rebuilding from scratch. Build cursors are offset cursors over the current bounded Mail query, not immutable Mail snapshots; rerun from `reset` if Mail changes during a multi-page audit build. `mail fts-search` / `mail_search_fts` requires a date bound, opens the existing index read-only, returns only capped redacted snippets and exact handles after live-row/date/content-state revalidation, skips stale content rows, and does not mutate Apple Mail data.
6. Preview: non-mutating Reminders future-change planning for exact requested create/complete/uncomplete/update-due-date/update-title/update-notes/update-priority/update-url/clear-url/move-to-list/delete workflows, non-mutating iCloud Drive create-folder planning for exact requested parent handles plus non-mutating iCloud Drive exact folder rename, Trash, permanent delete, move, and copy planning for exact requested directory handles plus `metadata_sha256` and exact target parent handles where applicable, non-mutating iCloud Drive create-text planning for exact requested parent folder handles, non-mutating iCloud Drive append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file planning for exact requested file handles or parent handles plus expected current content, metadata hash, or private source-file binding, non-mutating Calendar create-event planning for explicit target calendar titles, exact target-calendar handles, plan-only explicit default-calendar resolution, date-only all-day inference, relative-or-absolute display/audio/email/geofence alarms, explicit timed-event time zones, exact availability, and simple count-, end-date-, or explicit-unbounded recurrence, non-mutating Calendar exact-event update planning for exact requested event handles plus expected current state including optional expected availability, non-mutating Contacts create-contact planning for bounded contact fields, non-mutating Contacts exact scalar/method/rich-field/image update planning for exact requested contact handles plus `update_safe_sha256`, non-mutating Contacts exact group membership planning for exact contact and group handles plus contact/group safe hashes, non-mutating Contacts exact batch planning over capped existing-contact operation objects, non-mutating Contacts exact delete planning for exact requested contact handles plus `delete_safe_sha256`, non-mutating Notes create-note planning for bounded title/body input and optional exact Notes folder handles, non-mutating Notes rich-text body create (`create_html`) planning for bounded sanitized body HTML and optional exact Notes folder handles, non-mutating Notes exact child-folder create planning for one exact normal parent folder handle plus a bounded folder title, non-mutating Notes exact empty child-folder move planning for one exact source folder and exact same-account destination parent with metadata-state binding, non-mutating Notes append-text, replace-text, move-to-folder, and delete planning for exact requested note handles plus expected current content hash and exact folder handle where applicable, non-mutating Notes rich-text body replace (`replace_html`) planning for one exact requested note handle plus bounded sanitized body HTML and the expected current extracted visible-text SHA-256, non-mutating Mail create-draft and send-message planning for bounded recipient/subject/body input plus optional local attachment filenames/sizes/types without paths or bytes, non-mutating Mail reply-message and reply-all-message planning for exact requested message handles plus bounded body text and optional local attachment filenames/sizes/types without paths or bytes, non-mutating Mail forward-message planning for exact requested message handles, explicit recipients, bounded prepend text, optional caller-selected local attachments, default source attachment/non-body-part refusal, and optional `include_source_attachments` state binding for count-only source preservation, non-mutating Mail mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message planning for exact requested message handles, including capped exact bulk triage, plus current read/flag/mailbox state binding and exact target-mailbox binding where applicable, with cross-account target-mailbox moves exposing only opaque source/target account refs, non-mutating Photos import planning for caller-selected image/video source files, and non-mutating Messages send-text/send-file planning for exact existing chat handles plus bounded body preview or file metadata.
7. Mutation: approved only for Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact URL update/clear/exact absolute/relative/mixed display-alarm set/clear/start-date set/clear/recurrence create/update/clear/exact same-source list-move/delete apply and exact list create/rename/empty-delete/same-source migrate-delete apply, iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply, Calendar create-event/update/delete apply including exact target-calendar, date-only all-day, relative-or-absolute display/audio/email/geofence alarm, explicit timed-event time-zone, exact availability, simple count-, end-date-, or explicit-unbounded recurrence, selected-occurrence recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, future-series recurring-event title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move update, selected/future-span/whole-series recurring-event delete, and explicit default-calendar create-planning gates, plus synthetic `LAD-TEST-*` Calendar calendar create/rename/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete apply with full Photos Library authorization, and Messages send-text/send-file apply, home-directory Filesystem create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply rooted at the operator home directory reusing the exact iCloud Drive within-root plan/apply/read-back gates with a credential/secret path denylist, and Shortcuts run apply of one exact identifier-bound shortcut through the plan/apply approval-token/confirm gate, resolved by an exact `shortcuts:item:v1:` handle with the resolved identifier bound into the approval fingerprint, invoked by argv (never a shell string) under a hard execution timeout, proving invocation of the named shortcut only because a shortcut's arbitrary side effects are not verifiable by read-back; all other mutation requires a separate design and approval phase.

Tier 6 also includes the current Reminders alarm/start-date/recurrence and exact-list planners, Calendar calendar-management planner, Notes exact-folder rename/delete/move planners, bounded home-directory `filesystem_plan_change`, and exact identifier-bound `shortcuts_plan_run`. The matching apply tools remain separate and still require the exact approval token plus explicit confirmation.

Contacts note append/set/clear/merge contracts remain designed and synthetic-testable, but are not live-usable on this installation: the local helper lacks Apple's restricted Contacts-notes entitlement, so note planning/apply fails closed with `contacts_note_unavailable` before mutation. Contacts free-form labels are implemented up to 255 characters; control characters and oversize labels are refused.

## Never Persist

- Machine-local operator environment values outside the private
  `.env.operator` file; health may report active variable names and booleans
  only, never their values.
Do not persist any of the following in logs, docs, prompts, fixtures, tests, commits, or durable plan files:

- Message bodies
- Mail draft/send/reply/reply-all/forward planned recipients, subjects, body previews, body hashes, handles, source handles, mailbox references, source-state fingerprints, source attachment/non-body-part/content-state fingerprints, local attachment paths/file identities/filenames, approval tokens, or approval fingerprints outside transient preview/apply responses
- Mail read/flag/archive/move/trash triage planned handles, mailbox handles, mailbox references, target mailbox references, state fingerprints, approval tokens, or approval fingerprints outside transient preview/apply responses
- Mail selected-mailbox message listing handles, mailbox references, subjects, dates, or state metadata outside transient selected-list responses
- Messages transcripts outside exact selected responses
- Messages participant identifiers outside exact selected participant responses
- Messages send body text, body previews, body hashes, send-file local paths, file bytes, file identity, chat handles, chat GUIDs, participant identifiers, approval tokens, or approval fingerprints outside transient preview/apply responses
- Messages attachment metadata outside selected-chat responses and exported Messages attachments outside the caller-selected export path
- Full Hide My Email aliases outside exact selected responses
- Voice Memos transcript text outside exact selected responses
- Voice Memos audio bytes in chat, source recording paths, and raw recording identifiers
- Full Safari URLs outside exact selected item responses; Safari folder metadata/listing responses must not return full URLs
- Raw Shortcuts identifiers or shortcut bodies/action graphs
- Books annotation text outside exact selected-book responses
- Book/chapter/PDF/EPUB text
- Raw Books asset IDs, annotation UUIDs, and local Books paths
- Podcasts transcript text, audio/video bytes, feed/enclosure/web URLs, local download paths, raw show/episode identifiers, and episode descriptions outside exact selected-episode responses
- Music audio bytes, lyrics, file paths, raw identifiers, play history, ratings/favorites, and broad playlist track dumps
- TV video bytes, file paths, artwork, descriptions, raw identifiers, playback state, watched state, ratings/favorites, and broad playlist item dumps
- Freeform board BLOBs, decoded board items, board titles/content, asset bytes, previews, collaboration payloads, raw identifiers, and raw rows
- Note bodies (transient exact-handle `notes_get_content` and v1.182 confirm-gated `notes_export_folder_content` responses are the only places note text may appear; this repo never logs, fixtures, caches, or documents it)
- Note planned titles, Notes folder-create titles, body previews, handles, content hashes, replacement-body hashes, or approval fingerprints outside transient preview/apply responses
- Calendar event notes and locations
- Calendar planned titles, calendar names, locations, notes, handles, expected-state fields, or approval fingerprints outside transient preview/apply responses
- Contact email addresses, phone numbers, postal addresses, URLs, relations, and dates
- Contact planned names, organization names, email addresses, phone numbers, URLs, handles, update-safe/delete-safe/current-state hashes, or approval fingerprints outside transient preview/apply responses
- Contact notes and image data
- Photo asset bytes in chat, thumbnails, raw Photos identifiers, and asset/resource metadata outside exact selected responses
- Photos import source paths, source filenames, source-file hashes, handles, or approval fingerprints outside transient preview/apply responses
- Reminder titles or notes
- Reminder planning titles, notes, handles, expected notes hashes, expected priority values, or approval fingerprints outside transient preview/apply responses
- iCloud Drive file contents or raw local paths
- Mail FTS cache paths, raw cached FTS rows, or raw indexed Mail text outside the private local index file
- Safari history, open tabs, private browsing data, passwords, cookies, sessions, autofill, keychain data, or browser caches. Safari bookmark mutation (create/edit/delete/move) is refused as infeasible-to-do-safely: the Safari scripting dictionary has no bookmark write command, and the only path (editing the CloudKit-synced binary `Bookmarks.plist`) risks iCloud sync corruption and is clobbered by a running Safari, so it stays read-only.
- Shortcut bodies, action graphs, raw Shortcuts identifiers, open/view/sign/export, run by fuzzy/raw name, inline shortcut definitions, or Shortcuts mutation other than the approved exact identifier-bound `operation:run` gate. The approved run gate intentionally returns the invoked shortcut's bounded, truncation-flagged stdout as its apply result while documenting (`side_effects_unverifiable`) that a shortcut's arbitrary side effects cannot be proven by read-back; approval tokens and fingerprints are never returned outside transient preview/apply responses.
- iCloud Drive planned filenames, content, handles, content hashes, or approval fingerprints outside transient preview/apply responses
- Home-directory Filesystem file contents or raw local paths; the `filesystem` surface reuses the iCloud Drive gates re-rooted at the operator home directory (`~`) through the `fs:file:v1:` handle namespace, and the privacy floor is: every resolved target stays within the home root after realpath/symlink resolution (targets escaping via `..`/symlink, other users' home directories, and system paths are refused), and content-read plus mutation of a credential/secret denylist (`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `~/.config/gcloud`, `~/.netrc`, `~/.docker/config.json`, `~/.kube`, `~/Library/Keychains`, `~/Library/Application Support/com.apple.TCC`, and any `.env`/`.env.*`) are refused with `credential_path_blocked` — metadata-only (name/size/mtime) may still be returned so listings work, but never content bytes and never mutation — operator-overridable via `LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1`. This honors the standing rule to never print or copy secret values from local config, credentials, app-support stores, env files, or launchd environments.
- Attachment content
- Attachment source media paths
- Full email addresses
- Raw Hide My Email identifiers
- Account identifiers
- Raw database rows
- Credentials, tokens, app passwords, cookies, OAuth artifacts, keychain data, or environment secrets

Opaque search-result handles are allowed. Mail, Messages, Messages participant, inferred Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Freeform, Notes, Notes folder, Calendar, Contacts, Photos, Reminders, iCloud Drive, and bounded home-directory Filesystem handles are signed with a local secret so exact metadata fetches cannot be performed with guessed database row IDs, raw framework identifiers, raw alias identifiers, raw Messages chat/message/participant identifiers, recording identifiers, Shortcuts identifiers, Books asset IDs, Books annotation UUIDs, raw Podcasts identifiers, raw Music identifiers, raw TV identifiers, raw Freeform identifiers, raw Notes folder identifiers, raw Filesystem identifiers, or direct local paths. The same handles gate exact content/detail retrieval and approved exact-folder create targeting where applicable. The handle secret lives under the local plugin state directory and must not be printed or copied into durable docs.

## Allowed In Phase 0

- macOS version
- Tool availability
- Redacted tool path labels only, not full executable paths
- Redacted path labels for expected local stores
- Store presence and readability booleans
- Synthetic test data

## Redacted Audit Logs

The CLI and the MCP server both write redacted command events to
`~/.local/state/local-apple-data/events.jsonl`. At that default location the log is kept `0600`
inside a `0700` directory, matching `handle-secret.key` and `mail-fts.sqlite` beside it; the mode
is reasserted on each write, so a log created before that rule existed is repaired in place. When
`LOCAL_APPLE_DATA_LOG_DIR` points somewhere else the modes are left entirely alone — that
directory belongs to whoever chose it.

Allowed log fields:

- Timestamp
- Command name
- Source
- Status
- Schema version
- Result count
- Warning codes
- Privacy flags

Forbidden log fields:

- Query text
- Result titles, subjects, snippets, note text, reminder text, or message content
- Warning messages that might include paths or private content
- Raw rows or stack traces from local stores
- Full local executable paths
- Handles, subjects, bodies, raw MIME, full headers, local Mail file paths, or raw exception strings

Warning payloads returned to the user should use stable warning codes and safe generic messages only. Do not include local store paths, store filenames, raw exception strings, query text, or result metadata in warning messages.

### Reading the log

Most non-`ok` events carry a warning code, so failures group usefully with no extra tooling.
A few statuses — `not_found` in particular — record an empty `warning_codes` list, so the
status column matters as well as the codes:

```bash
jq -r 'select(.status != "ok") | [.command, .status, (.warning_codes | join(","))] | @tsv' \
  ~/.local/state/local-apple-data/events.jsonl | sort | uniq -c | sort -rn | head -20
```

### Retention

The log is append-only and is not rotated. That is deliberate rather than unfinished:

- The file is written concurrently by every running CLI invocation and MCP server process, and
  in practice several MCP servers are live at once — one per connected client, plus any stale
  ones left behind by clients that exited without reaping them. Each event is a single small
  `O_APPEND` write, which is safe under that. A rename-based rotation is not: two processes can
  both decide to rotate, and the second rename can overwrite the first one's backup. Because
  `log_result` deliberately swallows `OSError` so that logging can never break a data access
  command, that loss would be silent.
- Steady-state growth is small — recently on the order of tens of kilobytes per day. Large
  historical logs are dominated by test and verification traffic rather than operator activity;
  `tests/conftest.py` now redirects `LOCAL_APPLE_DATA_LOG_DIR` for the whole suite so the suite
  can no longer contribute to it.
- The log contains only the allowlisted fields above — no content, no handles, no paths.

Trim it manually when it gets large. Concurrent writes during the swap are lost, so do this when
no MCP server is running; check with `pgrep -fl local_apple_data.mcp_server` first, and note that
clients respawn their server on next use.

```bash
cd ~/.local/state/local-apple-data
tail -n 20000 events.jsonl > events.jsonl.trimmed \
  && mv events.jsonl.trimmed events.jsonl \
  && chmod 600 events.jsonl
```

## Approval Required

Ask the local operator before:

- Changing TCC or Full Disk Access
- Editing Codex config
- Editing launchd jobs
- Editing OpenClaw runtime state
- Mutating the bounded home-directory Filesystem or running an exact Shortcut outside its approved plan/token/explicit-confirmation gate
- Mutating Mail, Messages, Notes, Reminders, Gmail, or iCloud state outside the approved Reminders, iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file, Calendar, Contacts, Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete, Mail draft/send/reply/reply-all/forward/read/flag/archive/move/trash triage, Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete with full Photos Library authorization, and Messages send-text/send-file apply gates
- Adding direct network mail access
- Adding authoritative Hide My Email inventory or Hide My Email creation/deactivation/deletion
- Adding private iCloud web/API access, iCloud.com automation, browser sessions, or keychain credential access
- Adding new content classes beyond exact-handle Mail content/attachment export and date-bounded selected-mailbox message metadata, Messages chat transcripts/participant detail/attachment export, inferred Hide My Email aliases, Voice Memos existing embedded transcripts/audio export, Safari bookmark/Reading List URL detail and selected-folder metadata/direct child listing, Shortcuts metadata/selected-folder shortcut metadata, Books metadata/selected-book annotations, Podcasts metadata/selected-episode descriptions, Music track/playlist/selected-playlist track metadata, TV item/playlist/selected-playlist item metadata, Freeform board/folder/selected-folder board/child-folder metadata, Notes content/attachment export, Calendar event detail/participant detail, Contact detail, Photos asset/resource metadata/export and selected-album child asset metadata, Reminder notes, exact selected-folder iCloud Drive child/tree metadata listing, supported iCloud Drive text-file retrieval, and exact iCloud Drive regular-file export
- Adding home-directory Filesystem content/detail/export outside the bounded exact `fs:file:v1:` gate and its within-home plus credential/secret-path guards

## v1.11 Reminders Planning And Apply

The implemented v1.11/v1.35/v1.65/v1.136/v1.137/v1.138/v1.176 phases add non-mutating Reminders planning and the approved apply-capable mutation surface for Reminders create, complete, uncomplete, due-date update, title update, notes update, priority update, exact URL update/clear, exact absolute/relative/mixed display-alarm set/clear/start-date set/clear/recurrence create/update/clear, exact same-source target-list move, and exact-handle delete. It is not permission to run bulk changes, create/rename/delete/manage real lists, move reminders across accounts, move reminders outside the exact same-source target-list gate, mutate attachments/rich content, return raw URLs, run broad Reminder URL search, mutate mixed-with-audio/email/geofence/procedure alarms, return raw alarm state, delete outside the exact-handle gate, or mutate any other Apple data surface.

The implemented v1.136 Reminders URL update/clear gate is `docs/V1_136_REMINDERS_URL_WRITE_DESIGN.md`; it binds exact Reminder handle, expected title, expected URL presence, expected URL SHA-256 when present, allow-listed URL input with ASCII-only validation, EventKit apply, hash-only URL read-back or absence proof, and no raw URL return.

The implemented v1.137 Reminders absolute display-alarm set/clear gate is `docs/V1_137_REMINDERS_ABSOLUTE_DISPLAY_ALARM_WRITE_DESIGN.md`; it binds exact Reminder handle, expected title, expected completed state, expected alarm count, expected alarm-state SHA-256 when current alarms exist, timezone-explicit absolute alarm dates for set, EventKit apply, exact date read-back or absence proof, and no raw alarm state return.

The implemented v1.138 Reminders relative display-alarm set and broadened pure display-alarm clear gate is `docs/V1_138_REMINDERS_RELATIVE_DISPLAY_ALARM_WRITE_DESIGN.md`; it binds exact Reminder handle, expected title, expected completed state, expected alarm count, expected alarm-state SHA-256 when current alarms exist, bounded integer minute offsets for set, EventKit apply, exact offset read-back or absence proof, and no raw alarm state return.

The implemented v1.176 Reminders mixed display-alarm set/clear gate is `docs/V1_176_REMINDERS_MIXED_DISPLAY_ALARM_WRITE_DESIGN.md`; it approves exact mixed absolute-plus-relative display-alarm set/clear mutation with exact Reminder handle, expected title, expected completed state, expected alarm count, expected alarm-state SHA-256 when present, bounded relative offsets plus timezone-explicit absolute alarm dates, EventKit apply, exact mixed offset/date read-back or absence proof, and no raw alarm state return.

The implemented v1.177 Reminders start-date set/clear gate is `docs/V1_177_REMINDERS_START_DATE_WRITE_DESIGN.md`; it binds exact Reminder handle for update, expected title, exact expected current start-date state for update, a date-only or timezone-explicit start date that is on or before the due date when both are present, EventKit apply, exact start-date read-back proof for set, and start-date absence proof for clear.

The implemented v1.177 Reminders recurrence create/update/clear gate is `docs/V1_177_REMINDERS_RECURRENCE_WRITE_DESIGN.md`; it reuses the exact Calendar recurrence payload contract and shared `_normalize_recurrence` builder, binds exact Reminder handle for update, expected title, exact expected recurrence shape for update, a due date anchor for any recurring reminder, bounded recurrence selectors identical to Calendar recurrence, EventKit apply, exact recurrence-shape read-back proof for create or replace, and recurrence absence proof for clear.

The v1.11 planning implementation:

- Exposes `local-apple-data reminders plan` and MCP `reminders_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create, complete, uncomplete, update-due-date, update-title, update-notes, update-priority, update-url, clear-url, set-absolute-display-alarm, clear-display-alarm, move-to-list, and delete operations without calling EventKit or writing Reminders.
- Requires exact opaque `reminders:reminder:eventkit:v1:` handles for existing-reminder operation planning.
- Requires exact opaque `reminders:list:eventkit:v1:` expected current-list and target-list handles plus expected current list name for move-to-list planning.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, notes, handles, list names, expected notes hashes, priority values, and approval fingerprints.

The v1.11 apply implementation:

- Exposes `local-apple-data reminders apply` and MCP `reminders_apply_change`.
- Requires the matching `reminders-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque Reminder handles internally before existing-reminder updates.
- Resolves exact opaque expected current-list and target-list handles internally before move-to-list apply and refuses cross-account/source list moves.
- Refuses notes update drift by comparing the current notes SHA-256 before apply.
- Refuses priority update and delete drift by checking expected current priority before apply.
- Refuses delete drift by checking expected completed state and current notes SHA-256 before EventKit removal.
- Calls EventKit only after approval checks pass.
- Returns read-back metadata and never logs titles, notes, handles, raw EventKit identifiers, list names, or approval tokens.

## v1.12 iCloud Drive Planning And Apply

The implemented v1.12 phase adds non-mutating iCloud Drive create-text planning and the approved apply-capable mutation surface for creating one supported text-like file under an exact opaque parent folder handle. Append-text is governed separately by v1.18, replace-text is governed separately by v1.51, create-folder is governed separately by v1.52, create-folder-path is governed separately by v1.157, trash-text is governed separately by v1.53, text-file rename/copy/move is governed separately by v1.54, exact folder rename is governed separately by v1.60, exact folder Trash is governed separately by v1.61, exact folder move is governed separately by v1.62, exact empty folder copy is governed separately by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete is governed separately by v1.67, and exact text-file delete is governed separately by v1.68. v1.12 is not permission to replace content, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate folders outside approved folder gates, generate binary/documents, use raw paths, or run unbounded recursive folder writes.

The v1.12 planning implementation:

- Exposes `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create-text operations without resolving the parent handle or writing iCloud Drive files.
- Requires exact opaque `icloud:file:v1:` parent folder handles.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned filenames, content, handles, content hashes, and approval fingerprints.

The v1.12 apply implementation:

- Exposes `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque parent folder handles internally before writing.
- Uses exclusive create so existing files are never overwritten.
- Returns read-back metadata and never logs filenames, content, handles, raw paths, content hashes, approval fingerprints, or approval tokens.

## v1.18 iCloud Drive Append Planning And Apply

The implemented v1.18 phase adds non-mutating iCloud Drive append-text planning and the approved apply-capable mutation surface for appending bounded UTF-8 text to one supported text-like file selected by exact opaque handle. Replace-text is governed separately by v1.51, create-folder is governed separately by v1.52, create-folder-path is governed separately by v1.157, trash-text is governed separately by v1.53, text-file rename/copy/move is governed separately by v1.54, exact folder rename is governed separately by v1.60, exact folder Trash by v1.61 plus v1.146, exact folder move by v1.62, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete by v1.67, exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to replace content outside that exact gate, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate folders outside approved folder gates, generate binary/documents, use raw paths, or run unbounded recursive folder writes.

The v1.18 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` surfaces with `operation: append_text`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates the exact opaque `icloud:file:v1:` handle shape, expected current SHA-256, and bounded append text without resolving the handle or writing iCloud Drive files.
- Requires the caller to obtain `expected_current_sha256` from exact-handle iCloud Drive content retrieval.

The v1.18 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces with `operation: append_text`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves the exact opaque file handle internally.
- Reads the current normalized text content, refuses to append if the current SHA-256 differs from the approved plan, then appends bounded UTF-8 text.
- Returns read-back metadata plus the new content SHA-256 and never logs filenames, content, handles, raw paths, content hashes, approval fingerprints, or approval tokens.

## v1.51 iCloud Drive Replace Planning And Apply

The implemented v1.51 phase adds non-mutating iCloud Drive replace-text planning and the approved apply-capable mutation surface for replacing bounded UTF-8 text in one supported text-like file selected by exact opaque handle. Create-folder is governed separately by v1.52, create-folder-path by v1.157, trash-text by v1.53, text-file rename/copy/move by v1.54, exact folder rename by v1.60, exact folder Trash by v1.61 plus v1.146, exact folder move by v1.62, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete by v1.67, exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to replace content outside the exact replace-text gate, permanently delete files outside the exact delete-text or delete-file gates, generate binary/documents, use raw paths, or run unbounded recursive folder writes.

The v1.51 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` surfaces with `operation: replace_text`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates the exact opaque `icloud:file:v1:` handle shape, expected current SHA-256, and bounded replacement text without resolving the handle or writing iCloud Drive files.

## v1.52 iCloud Drive Folder Create Planning And Apply

The implemented v1.52 phase adds non-mutating iCloud Drive create-folder planning and the approved apply-capable mutation surface for creating one child directory under an exact opaque parent folder handle. Trash-text is governed separately by v1.53, text-file rename/copy/move is governed separately by v1.54, exact folder rename is governed separately by v1.60, exact folder Trash by v1.61 plus v1.146, exact folder move by v1.62, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, and exact selected-folder delete by v1.67. It is not permission to create recursive folder trees, permanently delete files, generate binary/documents, use raw paths, traverse symlinks/packages, or write hidden folders.

The v1.52 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` surfaces with `operation: create_folder`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates the exact opaque `icloud:file:v1:` parent handle shape and bounded folder name without resolving the handle or writing iCloud Drive folders.
- Rejects unexpected `content_text`, file handles, expected-current SHA input, hidden names, path separators, and package suffixes.

The v1.52 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces with `operation: create_folder`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves the exact opaque parent folder handle internally.
- Uses no-follow parent validation plus exclusive fd-relative `mkdir`.
- Returns metadata-only read-back with `privacy.content_inspected:false`, no content hash, and no child listing.
- Returns `already_applied` with `mutation_applied:false` when the exact directory already exists.
- Never logs folder names, handles, raw paths, approval fingerprints, or approval tokens.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of folder names, handles, raw paths, approval fingerprints, and approval tokens.

## v1.157 iCloud Drive Folder Path Create Planning And Apply

The implemented v1.157 phase adds non-mutating iCloud Drive create-folder-path
planning and the approved apply-capable mutation surface for creating one to
three bounded folder components under an exact opaque parent folder handle. It
is not permission to accept raw paths, write unbounded directory trees, traverse
symlinks or packages, write hidden folders, overwrite files, return raw paths,
or return content.

The v1.157 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP
  `icloud_drive_plan_change` surfaces with `operation: create_folder_path`.
- Requires exact `icloud:file:v1:` parent handles and `folder_components`.
- Binds stable parent identity into the approval fingerprint without returning
  raw filesystem identifiers.
- Rejects slash-delimited raw paths, more than three components, hidden names,
  package suffixes, trailing dot/space names, `filename`, and `content_text`.

The v1.157 apply implementation:

- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves the exact opaque parent folder handle internally.
- Uses fd-based no-follow `mkdir` per missing component.
- Treats existing directory components as idempotent.
- Returns `partial` with `mutation_applied:true` if a later component fails
  after earlier creation.
- Returns final metadata only with `content_text_returned:false`,
  `content_hash_returned:false`, `final_folder_verified:true`, and no raw path
  return.

## v1.53 iCloud Drive Trash Planning And Apply

The implemented v1.53 phase adds non-mutating iCloud Drive trash-text planning and the approved apply-capable mutation surface for moving one supported text-like file selected by exact opaque handle to recoverable Trash. Rename/copy/move is governed separately by v1.54, exact folder rename is governed separately by v1.60, exact folder Trash by v1.61 plus v1.146, exact folder move by v1.62, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete by v1.67, and exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to permanently delete files outside the exact delete-text or delete-file gates, empty Trash, trash folders outside the exact folder Trash gate, move folders outside the exact folder move gate, copy folders outside the exact selected-folder copy gate, trash binary/document/package files, use raw paths, traverse symlinks/packages, or run bulk deletion.

The v1.53 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` surfaces with `operation: trash_text`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Provides non-mutating iCloud Drive append-text, replace-text, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file planning for exact requested file handles or parent handles plus expected current content, metadata hash, or private source-file binding.
- Validates the exact opaque `icloud:file:v1:` handle shape and expected current SHA-256 without resolving the handle or writing iCloud Drive files.
- Rejects parent handles, filenames, and unexpected `content_text`.

The v1.53 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces with `operation: trash_text`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque file handles internally before moving.
- Refuses unsupported suffixes, directories, invalid UTF-8, current-content drift, package traversal, and symlink traversal.
- Moves the file to recoverable Trash by fd-based no-follow atomic swap, verifies the moved file's post-swap SHA-256, swaps back and fails closed on drift, and never permanently unlinks the selected file.
- Returns absence read-back with `original_present:false`, `trashed:true`, and `trash_path_returned:false`.
- Never logs filenames, content, handles, raw paths, Trash paths, content hashes, approval fingerprints, or approval tokens.

## v1.54 iCloud Drive Rename, Copy, And Move Planning And Apply

The implemented v1.54 phase adds non-mutating iCloud Drive rename-text/copy-text/move-text planning and the approved apply-capable mutation surface for relocating one supported text-like file selected by exact opaque handle. It is not permission to permanently delete outside the exact delete-text or delete-file gates, empty Trash, move/copy folders, mutate packages, generate binary/documents, use raw paths, traverse symlinks/packages, overwrite targets, or run bulk file operations.

The v1.54 planning implementation:

- Uses the existing `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change` surfaces with `operation: rename_text`, `operation: copy_text`, and `operation: move_text`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates the exact opaque `icloud:file:v1:` handle shape, expected current SHA-256, target filename, and exact parent handle where applicable without resolving local paths or writing files.
- Rejects unexpected content text and invalid target names.

The v1.54 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque file and parent handles internally before moving or copying.
- Refuses unsupported suffixes, directories, invalid UTF-8, current-content drift, package traversal, symlink traversal, and existing targets.
- Uses a no-overwrite target reservation plus fd-relative no-follow swap for rename/move, then verifies target identity and SHA-256 before removing the placeholder.
- Uses fd-relative no-follow exclusive create for copy, verifies target identity and SHA-256, then rechecks the source SHA-256 and removes only the created target on source drift.
- Returns read-back with `source_present`, `target_present`, target content hash, and `content_text_returned:false`.
- Rejects hidden CLI iCloud Drive `--root` overrides outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1` so normal CLI reads and writes cannot target arbitrary filesystem roots.

## v1.60/v1.145 iCloud Drive Exact Folder Rename Planning And Apply

The implemented v1.60 phase adds non-mutating iCloud Drive rename-folder planning and the approved apply-capable mutation surface for renaming one exact directory selected by opaque `icloud:file:v1:` handle. v1.145 broadens that gate to allow non-empty directories without child listing or content return. Exact folder move is governed separately by v1.62 plus v1.145, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete by v1.67, and exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to recursively rename folders, copy folders outside the exact selected-folder copy gate, delete folders outside the exact selected-folder delete gate, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate packages, generate binary/documents, use raw paths, traverse symlinks/packages, overwrite targets, or run bulk folder operations.

Privacy behavior:

- Provides non-mutating iCloud Drive rename-folder planning for exact requested directory handles plus expected directory `metadata_sha256`.
- Validates the exact opaque `icloud:file:v1:` handle shape, expected metadata SHA-256, and bounded folder name without resolving the handle or writing iCloud Drive folders.
- Rejects unexpected `content_text`, parent handles, hidden names, path separators, and package suffixes.
- Requires the caller to obtain `expected_current_sha256` from selected-folder metadata.
- Apply requires explicit confirmation and a matching approval token.
- Apply rechecks directory metadata SHA-256, refuses symlink/package traversal, and refuses target overwrite before mutation.
- If apply-time read-back cannot verify the relocated directory snapshot, the result is `partial` with bounded warning codes.
- Returns metadata-only read-back with `privacy.content_inspected:false`, no child listing, `content_text_returned:false`, `content_hash_returned:false`, source/target presence proof, `empty_folder_confirmed` as a boolean, and `non_empty_allowed:true`.
- Never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.
- Never logs filenames, content, handles, raw paths, content hashes, approval fingerprints, or approval tokens.

The v1.60 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces with `operation: rename_folder`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque directory handles internally before writing.
- Refuses current metadata drift before rename.
- Uses fd-relative no-overwrite rename with no-follow semantics in the same parent directory.
- Allows non-empty directories, preserves children through the filesystem rename, and reports `partial` when read-back cannot verify the relocated directory snapshot.
- Returns metadata-only read-back and never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.

## v1.61/v1.146 iCloud Drive Exact Folder Trash Planning And Apply

The implemented v1.61 phase added non-mutating iCloud Drive trash-folder planning and the approved apply-capable mutation surface for moving one exact directory selected by opaque `icloud:file:v1:` handle to recoverable Trash. v1.146 broadens that gate to allow non-empty directories without child listing or content return. Exact folder move is governed separately by v1.62 plus v1.145, exact empty folder copy by v1.63 and bounded non-empty selected-folder copy by v1.147, exact selected-folder delete by v1.67, and exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to recursively delete folders, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, copy folders outside the exact selected-folder copy gate, mutate packages, generate binary/documents, use raw paths, traverse symlinks/packages, overwrite targets, or run bulk folder operations.

Privacy behavior:

- Provides non-mutating iCloud Drive trash-folder planning for exact requested directory handles plus expected directory `metadata_sha256`.
- Validates the exact opaque `icloud:file:v1:` handle shape and expected metadata SHA-256 without resolving the handle or writing iCloud Drive folders.
- Rejects unexpected `content_text`, parent handles, filenames, file handles, and malformed handles.
- Requires the caller to obtain `expected_current_sha256` from selected-folder metadata.
- Apply requires explicit confirmation and a matching approval token.
- Apply rechecks directory metadata SHA-256, allows non-empty folders, and refuses symlink/package traversal before mutation.
- If folder Trash read-back cannot verify the approved target state, apply reports bounded warning codes and never returns child listings or raw Trash paths.
- Returns metadata-only read-back with `privacy.content_inspected:false`, no child listing, `original_present:false`, `trashed:true`, `trash_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `empty_folder_confirmed` as a boolean, and `non_empty_allowed:true`.
- Never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.

The v1.61 apply implementation:

- Uses the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces with `operation: trash_folder`.
- Requires the matching `icloud-drive-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Resolves exact opaque directory handles internally before writing.
- Refuses current metadata drift before Trash move.
- Uses no-follow fd-relative swap into recoverable Trash with identity-checked placeholder cleanup.
- Preserves directory children through the recoverable Trash move and reports `partial` only when identity-checked cleanup or read-back cannot be verified.
- Returns metadata-only absence read-back and never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.

## v1.62/v1.145 iCloud Drive Exact Folder Move Planning And Apply

The implemented v1.62 phase adds non-mutating iCloud Drive move-folder planning and the approved apply-capable mutation surface for moving one exact directory selected by opaque `icloud:file:v1:` handle to one exact target parent directory selected by opaque `icloud:file:v1:` handle. v1.145 broadens that gate to allow non-empty directories without child listing or content return. Exact selected-folder copy is governed separately by v1.63/v1.147, exact selected-folder delete by v1.67, and exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to recursively move folders, copy folders outside the exact selected-folder copy gate, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate packages, generate binary/documents, use raw paths, traverse symlinks/packages, overwrite targets, or run bulk folder operations.

Privacy behavior:

- Provides non-mutating iCloud Drive move-folder planning for exact requested directory handles, exact target parent handles, optional bounded target folder names, and expected directory `metadata_sha256`.
- Rejects unexpected `content_text`, missing parent handles, file handles, hidden names, path separators, package suffixes, self-parent moves, and malformed handles.
- Requires the caller to obtain `expected_current_sha256` from selected-folder metadata.
- Apply requires explicit confirmation and a matching approval token.
- Apply rechecks directory metadata SHA-256, target parent identity, no-overwrite target state, descendant-parent refusal, and symlink/package traversal before mutation.
- Apply verifies moved-folder identity after the fd-relative no-overwrite move and returns `partial` with bounded warning codes if post-move identity or read-back cannot be verified.
- Non-empty directories are allowed and their children are preserved by the filesystem move.
- Returns metadata-only read-back with `privacy.content_inspected:false`, no child listing, `source_present:false`, `target_present:true`, `moved:true`, `content_text_returned:false`, `content_hash_returned:false`, `empty_folder_confirmed` as a boolean, and `non_empty_allowed:true`.
- Never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.

## v1.63 iCloud Drive Exact Empty Folder Copy Planning And Apply

The implemented v1.63/v1.147 phase adds non-mutating iCloud Drive copy-folder planning and the approved apply-capable mutation surface for copying one exact selected directory tree selected by opaque `icloud:file:v1:` handle to one exact target parent directory selected by opaque `icloud:file:v1:` handle. Exact selected-folder delete is governed separately by v1.67 and exact text-file delete by v1.68, regular-file rename/copy/move by v1.127, and import-file by v1.129. It is not permission to run unbounded folder copy, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate packages, generate binary/documents, use raw paths, traverse symlinks/packages, overwrite targets, or run bulk folder operations.

Privacy behavior:

- Provides non-mutating iCloud Drive copy-folder planning for exact requested directory handles, exact target parent handles, optional bounded target folder names, and expected directory `metadata_sha256`.
- Rejects unexpected `content_text`, missing parent handles, file handles, hidden names, path separators, package suffixes, self-parent copies, and malformed handles.
- Requires the caller to obtain `expected_current_sha256` from selected-folder metadata.
- Apply requires explicit confirmation and a matching approval token.
- Apply rechecks directory metadata SHA-256, target parent identity, empty-folder state, no-overwrite target state, and symlink/package traversal before mutation.
- Apply creates one empty target directory only after source validation, then rechecks source identity, emptiness, and metadata hash.
- If source recheck fails after target creation, apply removes only the identity-matched empty target when possible; otherwise it returns `partial` with bounded warning codes.
- Returns metadata-only read-back with `privacy.content_inspected:false`, no child listing, `source_present:true`, `target_present:true`, `copied:true`, `content_text_returned:false`, `content_hash_returned:false`, `empty_folder_confirmed` as a boolean, and `non_empty_allowed:true`.
- Never logs folder names, handles, metadata hashes, raw paths, approval fingerprints, or approval tokens.

## v1.67 iCloud Drive Exact Selected-Folder Delete Planning And Apply

The implemented v1.67 phase adds non-mutating iCloud Drive delete-folder planning and the approved apply-capable mutation surface for permanently deleting one exact selected directory tree selected by opaque `icloud:file:v1:` handle. Exact text-file delete is governed separately by v1.68. It is not permission to run unbounded recursive deletes, permanently delete files outside the exact delete-text or delete-file gates, empty Trash, mutate packages, generate binary/documents, use raw paths, traverse symlinks/packages, overwrite targets, or run bulk folder operations.

Privacy behavior:

- Provides non-mutating iCloud Drive delete-folder planning for exact requested directory handles plus expected directory `metadata_sha256`.
- Validates the exact opaque `icloud:file:v1:` handle shape and expected metadata SHA-256 without resolving the handle or writing iCloud Drive folders.
- Rejects unexpected `content_text`, parent handles, filenames, file handles, and malformed handles.
- Requires the caller to obtain `expected_current_sha256` from selected-folder metadata.
- Apply requires explicit confirmation and a matching approval token.
- Apply rechecks directory metadata SHA-256, private bounded tree identity, hidden/package/symlink traversal, and staged directory identity before bounded permanent staged-tree removal.
- If a tree changes during apply before deletion starts, apply attempts an exact identity-checked rollback to the original name; if rollback cannot be verified, the result is `partial` with bounded warning codes and `permanently_deleted:false`.
- Returns metadata-only read-back with `privacy.content_inspected:false`, no child listing, `original_present:false`, `verified_absent:true`, `permanently_deleted:true` only on successful removal, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, `content_hash_returned:false`, `empty_folder_confirmed` as a boolean, and `non_empty_allowed:true`.
- Never logs folder names, handles, metadata hashes, raw paths, staging paths, approval fingerprints, or approval tokens.

## v1.68 iCloud Drive Exact Text File Delete Planning And Apply

The implemented v1.68 phase adds non-mutating iCloud Drive delete-text planning and the approved apply-capable mutation surface for permanently deleting one exact supported text-like file selected by opaque `icloud:file:v1:` handle. It is not permission to delete binary/document/package files, empty Trash, delete folders outside the exact selected-folder delete gate, use raw paths, traverse symlinks/packages, or run bulk file operations.

Privacy behavior:

- Provides non-mutating iCloud Drive delete-text planning for exact requested file handles plus expected current content hash.
- Resolves the exact opaque `icloud:file:v1:` handle during planning only to compute `expected_file_identity_sha256`; it does not write files or return raw paths, raw device/inode/timestamp fields, or content.
- Rejects unexpected `content_text`, parent handles, filenames, target parents, target names, folder handles, and malformed handles.
- Requires the caller to obtain `expected_current_sha256` from selected-file content metadata.
- Apply requires explicit confirmation and a matching approval token bound to the root-aware preview and exact file identity hash, so stale approval replay against a recreated same-path/same-content file is refused before mutation.
- Apply rechecks current content SHA-256, refuses unsupported suffixes, invalid UTF-8, hidden/package/symlink traversal, and staged-file identity mismatch before permanent unlink.
- Returns absence read-back with `original_present:false`, `verified_absent:true`, `permanently_deleted:true` only on successful unlink, `trash_path_returned:false`, `staging_path_returned:false`, `content_text_returned:false`, and `content_hash_returned:false`.
- Hidden staging names are random-only and do not include the original filename or extension.
- Never logs filenames, handles, raw paths, staging paths, content hashes, approval fingerprints, or approval tokens.

## v1.13 Calendar Planning And Apply

The implemented v1.13 phase adds non-mutating Calendar create-event planning and the approved apply-capable mutation surface for creating one timed event in an explicit target calendar title. The v1.34 Calendar update gate adds non-mutating exact-event update planning and approved title/time/location/notes update for one exact event with expected current-state binding. The v1.36 Calendar delete gate adds exact-event delete with expected-state binding, unsupported-event refusal, destructive annotation, and read-back absence proof. The v1.55 Calendar all-day gate adds explicit all-day create/update/delete support by binding `all_day` or `expected_all_day` into the plan, approval fingerprint, helper payload, and read-back proof. The v1.56 Calendar alarm-offset gate adds exact relative alarm-offset create/update/delete support by binding `alarm_offsets_minutes` or `expected_alarm_offsets_minutes` into the plan, approval fingerprint, helper payload, and read-back proof. The v1.86 Calendar target-calendar gate adds metadata-only target calendar search/detail plus exact create-by-calendar-handle and update move-by-calendar-handle. The v1.87 Calendar time-zone gate adds explicit timed-event IANA time-zone support by binding `time_zone` or `expected_time_zone` into the plan, approval fingerprint, helper payload, and read-back proof. The v1.88 Calendar absolute alarm gate adds exact absolute display-alarm create/update/delete support by binding `alarm_absolute_dates` or `expected_alarm_absolute_dates` into the plan, approval fingerprint, helper payload, and read-back proof. The v1.89 Calendar recurrence gate adds simple count-bound daily/weekly recurrence create by binding `recurrence_frequency`, `recurrence_interval`, and `recurrence_count` into the plan, approval fingerprint, helper payload, and read-back proof. The v1.90 Calendar recurrence/date-only gate extends that to simple count-bound monthly/yearly recurrence create and date-only all-day inference by binding date-only start/end strings plus inferred all-day state into the plan, approval fingerprint, helper payload, and read-back proof. The v1.91 Calendar default-calendar gate adds plan-only explicit default-calendar create planning by resolving to an exact writable `calendar:calendar:v1:` handle and requiring apply to use that approved handle. The v1.92 Calendar availability gate adds exact busy/free/tentative/unavailable availability create/update by binding `availability` and update-only `expected_availability`, validating the EventKit target calendar support mask, and verifying read-back availability. The v1.93 Calendar recurrence update gate adds simple finite recurrence add-to-non-recurring-event update by binding `recurrence_frequency`, `recurrence_interval`, and recurrence bounds into the exact-event update approval fingerprint, helper payload, and read-back proof. The v1.139 Calendar unbounded recurrence gate adds explicit `recurrence_unbounded:true` create/update/replacement while keeping implicit unbounded recurrence blocked. The v1.94/v1.95 Calendar event URL gates add exact allow-listed URL set and clear with hash-only read-back and expected URL hash binding. The v1.96-v1.98 recurring delete gates add selected-occurrence, future-span, and whole-series delete with occurrence identity and absence/preservation proof. The v1.99/v1.101/v1.105/v1.106/v1.110/v1.111 recurrence gates add weekly weekday, monthly weekday, monthly day-of-month, monthly nth-weekday, and yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year. The v1.123 selector-backed set-position recurrence gate adds exact `recurrence_set_positions` binding for approved recurrence create and add-to-non-recurring-event update when another recurrence selector is present. The v1.100 recurrence-clear gate adds first-visible and mid-series recurrence clearing with future absence plus previous absence-or-preservation proof. The v1.126 recurrence replacement gate (`docs/V1_126_CALENDAR_RECURRENCE_REPLACEMENT_WRITE_DESIGN.md`) adds mid-series selected-and-future recurrence replacement with exact previous/selected/future occurrence binding and previous-preservation plus future-replacement proof. The v1.102 structured location gate adds bounded `structured_location` and `expected_structured_location` binding with `EKStructuredLocation` read-back proof. The v1.103 audio alarm gate adds bounded `alarm_sound_name` and `expected_alarm_sound_name` binding with `EKAlarm.soundName` read-back proof. The v1.108 email alarm gate accepts bounded `alarm_email_address` input only as plan/apply input and returns only `alarm_email_address_sha256` in preview/read-back/log-safe output. The v1.114 selected occurrence update gate adds title/plain-location/notes-only `.thisEvent` update with selected occurrence and adjacent occurrence proof. The v1.115 selected occurrence reschedule gate adds timed start/end/time-zone `.thisEvent` update with selected occurrence read-back at the approved new time, original occurrence absence proof, and adjacent occurrence preservation proof. The v1.117 selected occurrence event URL gate adds exact allow-listed URL set/clear with hash-only selected-occurrence read-back or absence proof plus adjacent occurrence URL-state preservation proof. The v1.118 selected occurrence structured-location gate adds set/clear with expected absence or exact expected structured-location binding, selected-occurrence structured-location read-back or absence proof, and adjacent occurrence preservation proof. The v1.119 selected occurrence display-alarm gate adds relative or absolute display alarm set/clear with exact expected display-alarm state binding, selected-occurrence display-alarm read-back proof, and adjacent occurrence URL/plain-location/structured-location/alarm-state preservation proof. The v1.120 selected occurrence action-alarm gate adds audio, email, and structured geofence alarm action set/clear with exact expected display/audio/email/geofence alarm state binding, raw email accepted only as plan/apply input, hash-only email output, selected-occurrence action-alarm read-back proof, and adjacent occurrence URL/plain-location/structured-location/alarm-state preservation proof. The v1.121 selected occurrence all-day gate adds all-day set/clear/date-only reschedule with exact expected all-day/time-zone binding, date-only all-day set input, explicit time-zone timed clear input, selected-occurrence all-day read-back proof, and adjacent occurrence URL/plain-location/structured-location/alarm-state preservation proof. The v1.122 selected occurrence target-calendar gate adds exact selected-occurrence calendar move with target-calendar handle binding, selected-occurrence target-calendar proof, and adjacent-occurrence original-calendar proof. Calendar title search does not return event time zones, alarm state, recurrence metadata, event URLs, or structured locations. These gates are not permission to delete outside the approved exact-event gate, delete recurrence, mutate selected recurring occurrences outside title/plain-location/notes/timed reschedule/availability/event URL set/clear/structured-location set/clear/display-alarm set/clear/action-alarm set/clear/all-day set/clear/date-only reschedule/target-calendar move, create custom recurrence rules beyond approved selector-backed EventKit rules, infer unbounded recurrence without explicit `recurrence_unbounded:true`, perform attendee/invitation/organizer mutation, silently guess or mutate a default calendar, infer timed-event time-zone semantics, mutate unsupported event types, create procedure alarms, or run bulk Calendar mutations.

Calendar participant access is read-only and exact-handle gated. `calendar_list_participants` returns opaque `calendar:participant:v1:` handles plus role/status/type/current-user metadata and name/URL presence flags only; `calendar_get_participant` may return bounded selected participant name/URL only when called with the original event handle plus a selected participant handle. Attendee, invitation, and organizer mutation remains blocked because EventKit exposes participant fields as read-only.

The implemented v1.112 Calendar yearly month day-of-month recurrence gate is `docs/V1_112_CALENDAR_YEARLY_MONTH_DAY_RECURRENCE_WRITE_DESIGN.md`; it binds `recurrence_year_months` plus `recurrence_year_month_days` into the approval fingerprint, helper payload, and read-back proof. The implemented v1.113 Calendar monthly weekday recurrence gate is `docs/V1_113_CALENDAR_MONTHLY_WEEKDAY_RECURRENCE_WRITE_DESIGN.md`; it binds `recurrence_weekdays` for monthly recurrence into the approval fingerprint, helper payload, and read-back proof. The implemented v1.114 Calendar selected recurring occurrence scalar update gate is `docs/V1_114_CALENDAR_SELECTED_OCCURRENCE_UPDATE_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, title/plain-location/notes-only mutation, EventKit `.thisEvent` save, selected-occurrence read-back proof, and adjacent-occurrence preservation proof into the approval fingerprint, helper payload, and read-back proof. The implemented v1.115 Calendar selected recurring occurrence reschedule gate is `docs/V1_115_CALENDAR_SELECTED_OCCURRENCE_RESCHEDULE_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, timed start/end/time-zone mutation, EventKit `.thisEvent` save, selected-occurrence read-back proof at the approved new time, original occurrence absence proof, and adjacent-occurrence preservation proof. The implemented v1.116 Calendar selected recurring occurrence availability gate is `docs/V1_116_CALENDAR_SELECTED_OCCURRENCE_AVAILABILITY_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity, required `expected_availability`, availability mutation, EventKit `.thisEvent` save, selected-occurrence availability read-back proof, and adjacent-occurrence preservation proof. The implemented v1.117 Calendar selected recurring occurrence event URL gate is `docs/V1_117_CALENDAR_SELECTED_OCCURRENCE_EVENT_URL_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only URL-state binding, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.thisEvent` save, selected-occurrence hash-only URL read-back or absence proof, no raw URL return, and adjacent-occurrence presence/recurrence/URL-state preservation proof. The implemented v1.118 Calendar selected recurring occurrence structured-location gate is `docs/V1_118_CALENDAR_SELECTED_OCCURRENCE_STRUCTURED_LOCATION_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location state binding, expected structured-location absence or exact expected structured-location binding, EventKit `.thisEvent` save, selected-occurrence structured-location read-back or structured/plain-location absence proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location preservation proof. The implemented v1.119 Calendar selected recurring occurrence display-alarm gate is `docs/V1_119_CALENDAR_SELECTED_OCCURRENCE_DISPLAY_ALARM_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display-alarm state binding, EventKit `.thisEvent` save, selected-occurrence display-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof. The implemented v1.120 Calendar selected recurring occurrence action-alarm gate is `docs/V1_120_CALENDAR_SELECTED_OCCURRENCE_ACTION_ALARM_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.thisEvent` save, selected-occurrence action-alarm read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof. The implemented v1.121 Calendar selected recurring occurrence all-day gate is `docs/V1_121_CALENDAR_SELECTED_OCCURRENCE_ALL_DAY_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.thisEvent` save, selected-occurrence all-day read-back proof, and adjacent-occurrence presence/recurrence/URL/plain-location/structured-location/alarm-state preservation proof. The implemented v1.122 Calendar selected recurring occurrence target-calendar move gate is `docs/V1_122_CALENDAR_SELECTED_OCCURRENCE_CALENDAR_MOVE_WRITE_DESIGN.md`; it binds `recurrence_update_scope:this_event`, selected occurrence identity, adjacent occurrence identity plus hash-only sibling URL/plain-location/structured-location/alarm-state binding, exact target `calendar:calendar:v1:` handle, EventKit `.thisEvent` save, selected-occurrence target-calendar read-back proof, and adjacent-occurrence original-calendar preservation proof. The implemented v1.167 Calendar future-series scalar update gate is `docs/V1_167_CALENDAR_FUTURE_SERIES_SCALAR_UPDATE_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, title/plain-location/notes-only mutation, EventKit `.futureEvents` save, selected/future recurrence-shape plus scalar read-back proof, and previous-occurrence preservation proof. The implemented v1.168 Calendar future-series timed reschedule gate is `docs/V1_168_CALENDAR_FUTURE_SERIES_RESCHEDULE_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, explicit expected/proposed time zones, EventKit `.futureEvents` save, selected/future recurrence-shape plus timed read-back proof, original selected/future slot absence-or-approved-replacement proof when dates move, and previous-occurrence preservation proof. The implemented v1.169 Calendar future-series availability gate is `docs/V1_169_CALENDAR_FUTURE_SERIES_AVAILABILITY_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, expected/proposed availability, EventKit `.futureEvents` save, selected/future recurrence-shape plus availability read-back proof, and previous-occurrence preservation proof. The implemented v1.170 Calendar future-series event URL gate is `docs/V1_170_CALENDAR_FUTURE_SERIES_EVENT_URL_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact allow-listed event URL or `clear_event_url`, expected URL state binding for clear, EventKit `.futureEvents` save, selected/future recurrence-shape plus hash-only URL read-back or absence proof, no raw URL return, and previous-occurrence preservation proof.
The implemented v1.171 Calendar future-series structured-location gate is `docs/V1_171_CALENDAR_FUTURE_SERIES_STRUCTURED_LOCATION_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded structured-location input or `clear_structured_location`, expected structured-location binding for clear, EventKit `.futureEvents` save, selected/future recurrence-shape plus structured-location read-back or absence proof, and previous-occurrence preservation proof. This gate permits only update-only future-series recurring-event structured-location set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded structured-location input or `clear_structured_location`, expected structured-location binding for clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus structured-location read-back or absence proof, and previous-occurrence preservation proof.
The implemented v1.172 Calendar future-series display-alarm gate is `docs/V1_172_CALENDAR_FUTURE_SERIES_DISPLAY_ALARM_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded relative or absolute display-alarm input or display-alarm clear, exact expected display-alarm state binding, EventKit `.futureEvents` save, selected/future recurrence-shape plus display-alarm read-back or absence proof, and previous-occurrence preservation proof. This gate permits only update-only future-series recurring-event display-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, bounded relative or absolute display-alarm input or display-alarm clear, exact expected display-alarm state binding, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus display-alarm read-back or absence proof, and previous-occurrence preservation proof.

The implemented v1.173 Calendar future-series action-alarm gate is `docs/V1_173_CALENDAR_FUTURE_SERIES_ACTION_ALARM_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.futureEvents` save, selected/future recurrence-shape plus action-alarm read-back or absence proof, and previous-occurrence preservation proof. This gate permits only update-only future-series recurring-event action-alarm set/clear mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected display/audio/email/geofence alarm state binding, explicit proposed trigger/action state, raw email input accepted only as plan/apply input, no raw email output, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus action-alarm read-back or absence proof, and previous-occurrence preservation proof.

The implemented v1.174 Calendar future-series all-day gate is `docs/V1_174_CALENDAR_FUTURE_SERIES_ALL_DAY_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.futureEvents` save, selected/future recurrence-shape plus all-day read-back proof, original selected/future slot absence-or-approved-replacement proof, and previous-occurrence preservation proof. This gate permits only update-only future-series recurring-event all-day set/clear/date-only reschedule mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact expected all-day/time-zone state binding, date-only proposed start/end for all-day set or same-state all-day date-only reschedule, explicit proposed time zone for all-day-to-timed clear, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus all-day read-back proof, original selected/future slot absence-or-approved-replacement proof, and previous-occurrence preservation proof.

The implemented v1.175 Calendar future-series target-calendar move gate is `docs/V1_175_CALENDAR_FUTURE_SERIES_CALENDAR_MOVE_WRITE_DESIGN.md`; it binds `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact target `calendar:calendar:v1:` handle, EventKit `.futureEvents` save, selected/future recurrence-shape plus target-calendar read-back proof, and previous-occurrence original-calendar preservation proof. This gate permits only update-only future-series recurring-event target-calendar move mutation with `recurrence_update_scope:future_events`, selected occurrence identity, previous occurrence identity, future occurrence identity, exact `calendar:calendar:v1:` target handle, EventKit `.futureEvents` save, selected and future occurrence recurrence-shape plus target-calendar read-back proof, and previous-occurrence original-calendar preservation proof.

The v1.13 planning implementation:

- Exposes `local-apple-data calendar plan` and MCP `calendar_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create operations without calling EventKit or writing Calendar data.
- Requires explicit target calendar title or exact `calendar:calendar:v1:` handle, title, start timestamp, and end timestamp.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, calendar names, locations, notes, and approval fingerprints.

The v1.13 apply implementation:

- Exposes `local-apple-data calendar apply` and MCP `calendar_apply_change`.
- Requires the matching `calendar-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Calls EventKit only after approval checks pass.
- Resolves the target calendar by exact title or exact `calendar:calendar:v1:` handle and refuses missing or ambiguous calendars. Raw EventKit calendar identifiers are never returned.
- Returns read-back metadata and never logs event titles, calendar names, locations, notes, raw EventKit identifiers, approval fingerprints, or approval tokens.

The v1.34 Calendar update implementation:

- Uses the existing `local-apple-data calendar plan/apply` and MCP `calendar_plan_change`/`calendar_apply_change` surfaces with `operation: update`.
- Requires an exact `calendar:event:v1:` handle and expected current title, calendar title, start date, end date, location, and notes.
- Refuses stale expected state plus recurring or attendee-bearing events before applying; events with alarms require exact expected offsets/dates that match.
- Saves only the selected event, may move it to an exact target calendar handle, and returns EventKit read-back metadata.

## v1.1 Mail Content Retrieval

The implemented v1.1 phase is exact-handle Mail content retrieval only. It is not permission to retrieve content by default.

The v1.1 implementation:

- Require a `mail:message:v2:` handle returned by `mail_search`.
- Add a `content_status` hint to Mail search results using a metadata-only local file-presence check; it does not read message bodies.
- Add date-bounded Mail body, advanced, and attachment discovery tools. Body/advanced discovery returns capped redacted snippets or masked header metadata only, attachment discovery returns filename/MIME metadata plus exact attachment handles only, and full content/export still requires exact selected handles.
- Add date-bounded selected-mailbox message metadata using one exact `mail:mailbox:v1:` handle. It returns capped message metadata only and no bodies, full headers, raw paths, or raw account IDs.
- Reject raw IDs, old handles, mailbox refs, direct paths, and fabricated handles.
- Return bounded plain text with truncation metadata.
- Exclude broad attachment export, inline attachment bytes, raw MIME, full headers, remote resources, Notes bodies, Reminder notes, broad content search, background indexing, and durable content caches. Exact selected Mail attachment export is governed separately by v1.21.
- Keep automated tests synthetic-only.
- Keep redacted event logs free of handles, subjects, bodies, warning messages, raw paths, and raw exceptions.

## v1.2 Notes Content Retrieval

The implemented v1.2 phase adds exact-handle Apple Notes content retrieval. It is not permission to retrieve Notes content by default or to run broad Notes exports.

The v1.2 implementation:

- Requires a `notes:note:v2:` handle returned by `notes_search`.
- Resolves the handle internally and derives the Notes app Core Data ID without returning or logging it.
- Reads one selected note through local Notes automation with a hard timeout.
- Returns bounded plain text with truncation metadata.
- Rejects raw IDs, old handles, fabricated handles, and direct paths.
- Excludes locked/deleted notes, source attachment paths, inline attachment bytes, raw database rows, local paths, broad content search, background indexing, and durable content caches.
- Keeps automated tests synthetic-only and verifies the live path only by redacted status/count output when explicitly requested.

## v1.20 Notes Attachment Export

The implemented v1.20 phase adds exact-handle Apple Notes attachment metadata and local export. It is not permission to run broad Notes exports or return attachment bytes inline.

The v1.20 implementation:

- Requires a `notes:note:v2:` handle returned by `notes_search` before listing attachments.
- Returns bounded metadata and opaque `notes:attachment:v1:` handles for attachments on that selected note.
- Exports one selected attachment only to a caller-selected output directory.
- Prefers locally available Notes media files and falls back to local database BLOB data when present.
- Does not return source media paths, remote attachment URLs, or attachment bytes inline.
- Does not fetch remote iCloud-only attachments.
- Keeps automated tests synthetic-only and verifies redacted logs exclude handles, filenames, warning messages, and export paths.

## v1.21 Mail Attachment Export

The implemented v1.21 phase adds exact-handle Apple Mail attachment metadata and local MIME attachment export. It is not permission to run broad Mail attachment exports, expose raw MIME/full headers, fetch externalized attachments, or mutate Mail attachments.

The v1.21 implementation:

- Requires a `mail:message:v2:` handle returned by `mail_search` before listing attachments.
- Returns bounded metadata and opaque `mail:attachment:v1:` handles for attachments on that selected message.
- Requires both the selected message handle and selected attachment handle before export, so export does not scan the whole Mail store to resolve a detached token.
- Exports one selected MIME attachment only to a caller-selected output directory.
- Does not return source `.emlx` paths, raw MIME, full headers, or attachment bytes inline.
- Reports externalized or partial-message attachments as unavailable when bytes are not in the local `.emlx`; it does not fetch remote or missing attachment data.
- Keeps automated tests synthetic-only and verifies redacted logs exclude handles, filenames, warning messages, source paths, and export paths.

## v1.22 Messages Attachment Export

The implemented v1.22 phase adds exact-handle Apple Messages attachment metadata and local export. It is not permission to run broad Messages attachment exports, reveal participant identifiers or source paths, fetch unavailable iCloud media, or mutate Messages.

The v1.22 implementation:

- Requires a `messages:chat:v1:` handle returned by `messages_search` before listing attachments.
- Returns bounded metadata and opaque `messages:attachment:v1:` handles for attachments linked to that selected chat.
- Requires both the selected chat handle and selected attachment handle before export, so export does not scan the whole Messages store to resolve a detached token.
- Exports one selected local attachment only to a caller-selected output directory.
- Does not return participant identifiers, chat GUIDs, attachment GUIDs, source media paths, or attachment bytes inline.
- Reports unavailable local media as unavailable and does not fetch remote or missing iCloud attachment data.
- Keeps automated tests synthetic-only and verifies redacted logs exclude handles, filenames, warning messages, source paths, and export paths.

## v1.3 iCloud Drive Content Retrieval

The implemented v1.3/v1.85/v1.141/v1.142/v1.162 phases add exact-handle local iCloud Drive item metadata, configured-root metadata selection, exact selected-folder direct child metadata listing, bounded exact selected-folder tree metadata listing, supported text-file content retrieval, and read-only exact regular-file export to a caller-selected output directory outside the configured iCloud Drive root. Root metadata returns only an opaque root directory handle, `is_root:true`, and ordinary directory metadata without raw paths. Direct folder listing is capped, non-recursive, skips hidden/symlink/package entries, and returns no content or raw paths. Folder-tree listing is depth-capped, result-capped, tree-scan-capped, child-metadata-bound before recursion, skips hidden/symlink/package entries, and returns no content or raw paths. Content/export byte reads bind the selected source identity after handle resolution. Export returns no inline bytes and no source path. It is not permission to run broad file dumps, parse arbitrary binary/document contents, export packages, export recursively, mutate the iCloud Drive root as a folder source, or use raw source paths.

The v1.3 implementation:

- Requires a `icloud:file:v1:` handle returned by `icloud-drive search`, `icloud-drive root`, `icloud-drive list`, or `icloud-drive tree`.
- Allows root handles only for read/list/tree and approved create/import parent targeting; folder rename, Trash, delete, move, and copy reject the root as a source.
- Searches local iCloud Drive by filename only, with empty and broad queries rejected before scanning.
- Returns filenames, file/folder kind, extension, size, modified timestamp, depth, and opaque handle without raw local paths.
- Lists direct children and bounded descendant trees only for exact selected folder handles; results are capped, metadata-only, and omit hidden, symlink, and package entries.
- Reads content only for supported text-like file suffixes and exact selected file handles.
- Returns bounded plain text with truncation metadata.
- Rejects direct source paths, fabricated handles, hidden files, symlinks, package-internal files, unsupported inline binary/document extraction, broad content search, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.4 Calendar Event Retrieval

The implemented v1.4 phase adds EventKit-backed Calendar event title search and exact-handle event detail retrieval. It is not permission to run broad calendar dumps or mutate Calendar data.

The v1.4 implementation:

- Requires a `calendar:event:v1:` handle returned by `calendar search`.
- Searches local Calendar events by title only, with empty and broad queries rejected before EventKit access.
- Uses a stable app-bundled EventKit helper for Calendar so macOS can grant full
  Calendar access to `com.local-apple-data.eventkit-helper`; normal
  Calendar reads are non-prompting and return a safe `calendar_access_unavailable`
  warning if full access is absent. `calendar request-access` is the explicit
  one-time prompt path. It keeps the helper run loop alive and activates the
  helper app before requesting access, but live Calendar access still requires
  visible macOS GUI consent for the helper app.
- Returns event title, calendar title, start/end dates, all-day flag, availability, and presence/count metadata during search.
- Lists events for one exact selected `calendar:calendar:v1:` handle only with
  explicit start/end bounds, a 366-day window cap, and a 50-event output cap.
  Selected-calendar event listing returns event metadata and opaque event
  handles only, not notes, location text, attendee names/URLs, event URL values,
  raw EventKit identifiers, or raw alarm detail.
- Reads event location and notes only for exact selected event handles.
- Returns bounded notes text with truncation metadata.
- Rejects raw EventKit identifiers, fabricated handles, broad content search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.5 Reminders EventKit Retrieval

The implemented v1.5 phase adds EventKit-backed Reminders title search, exact-handle Reminder note retrieval, and exact selected-list item metadata. It is not permission to run broad Reminder dumps or mutate Reminders data.

The v1.5 implementation:

- Requires a `reminders:reminder:eventkit:v1:` handle returned by `reminders eventkit-search`.
- Searches local Reminders by title only, with empty and broad queries rejected before EventKit access.
- Uses the stable app-bundled EventKit helper. If Reminders are not authorized
  for the helper app, normal reads return a safe `reminders_access_unavailable`
  warning; `reminders request-access` is the explicit one-time prompt path for
  `com.local-apple-data.eventkit-helper`.
- Returns reminder title, list name, due/start dates, completion state, priority, and presence/count metadata during search.
- Lists reminder metadata in one exact selected EventKit list through a `reminders:list:eventkit:v1:` handle, capped and incomplete-only by default.
- Reads reminder notes only for exact selected EventKit reminder handles.
- Returns bounded notes text with truncation metadata.
- Rejects raw EventKit identifiers, legacy SQLite reminder handles, fabricated handles, broad content/list search, broad dumps, mutations, background indexing, raw URLs, raw alarm detail, attachments, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.6 Contacts Retrieval

The implemented v1.6 phase adds Contacts.framework-backed contact name/organization search, exact-handle contact detail retrieval, exact selected-group member metadata, and exact selected-container member metadata. Contacts create-contact apply is separately approved by v1.14, exact scalar update by v1.48, exact email/phone/URL method-array update by v1.69, read-only Contacts count/export and exact note append by v1.70, rich-field/image update, note set/clear/merge, group membership, and exact batch by v1.71, exact group create/rename/delete and exact container-targeted create by v1.72, and exact delete by v1.49. v1.6 alone is not permission to run broad Contacts dumps outside the v1.70 backup export gate, return contact note text in chat output, update/delete Contacts outside the approved gates, or mutate Contacts data outside the v1.14/v1.48/v1.69/v1.70/v1.71/v1.72/v1.49 gates. This is historical design coverage, not a live-availability claim: the note gates remain synthetic-testable, but every live note operation now fails closed with `contacts_note_unavailable` before mutation.

The v1.6 implementation:

- Requires a `contacts:contact:v1:` handle returned by `contacts search`.
- Requires a `contacts:group:v1:` handle returned by `contacts groups` for exact group detail, selected-group member metadata, membership, rename, or delete, and a `contacts:container:v1:` handle returned by `contacts containers` for exact container-targeted creates or selected-container member metadata.
- Searches local Contacts by name, nickname, organization, department, or job title only, with empty and broad queries rejected before Contacts.framework access.
- Uses a stable signed Contacts helper app for all reads, writes, and the
  explicit CLI-only `contacts request-access` recovery command. Normal tool
  calls never prompt; if the helper is not authorized, they return a safe
  `contacts_access_unavailable` warning.
- Returns display name, contact type, organization/job metadata, count/presence metadata, and opaque handle during search.
- Reads email addresses, phone numbers, postal addresses, URLs, birthdays, dates, social profiles, instant-message addresses, and contact relations only for exact selected contact handles.
- Exact `contacts group-members` returns capped member contact metadata for one selected group only; it returns opaque contact handles plus count/presence metadata, not raw member IDs, email/phone/postal/URL values, note text, image bytes, or contact detail values.
- Exact `contacts container-members` returns capped member contact metadata for one selected container only; it returns opaque contact handles plus count/presence metadata, not raw container/contact IDs, email/phone/postal/URL values, note text, image bytes, or contact detail values.
- Exact `contacts get` may read `CNContactNoteKey` only to return `note_chars`
  and `note_safe_sha256`; it does not return existing note text. Apple's
  restricted Contacts-notes entitlement requires a suitable provisioning
  profile and is absent from the locally self-signed helper, so note reads and
  mutations fail closed and archive export omits notes on this installation.
  A separately provisioned helper may include notes only within the existing
  exact-handle/archive gates.
- Does not return image bytes; image access remains a separate content gate.
- Rejects raw Contacts identifiers, fabricated handles, broad content search, update/delete/note/image mutation outside approved gates, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.14 Contacts Create Apply

The implemented v1.14 phase adds non-mutating Contacts create-contact planning and the approved apply-capable mutation surface for creating one contact through Contacts.framework. The implemented v1.48 phase adds exact-contact scalar name/organization update with `update_safe_sha256` stale-state refusal. The implemented v1.69 phase adds exact email/phone/URL method-array replacement under the same exact-contact update gate; omitted method arrays are preserved, provided arrays replace the selected arrays, and explicit empty arrays clear the selected arrays. The implemented v1.70 phase adds read-only Contacts count/export backup tools plus exact-contact note append with `note_safe_sha256` stale-state refusal and hash-only note read-back. The implemented v1.71 phase adds exact-contact rich-field/image update, exact note set/clear/merge, exact group membership, and capped exact batch over approved existing-contact operations. The implemented v1.72 phase adds exact group create/rename/delete and exact container-targeted create with `container_safe_sha256` / `group_safe_sha256` state binding. The implemented v1.49 phase adds exact-contact delete with `delete_safe_sha256` stale-state refusal and absence proof. These gates are not permission to use raw Contacts identifiers, run broad in-chat contact dumps, write Contacts databases directly, automate duplicate merge, or claim full CRUD. The note sentences above describe the historical v1.70/v1.71 contract and its synthetic tests, not a usable live surface: this helper lacks the restricted Contacts-notes entitlement and fails closed with `contacts_note_unavailable` before mutation. Free-form labels are implemented up to 255 characters; control characters and oversize labels are refused.

The v1.14 planning implementation:

- Exposes `local-apple-data contacts plan` and MCP `contacts_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create operations without calling Contacts.framework or writing Contacts.
- Requires a person contact to include `given_name` or `family_name`.
- Requires an organization contact to include `organization_name`.
- Caps email, phone, and URL lists at five entries each.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned names, organizations, email addresses, phone numbers, URLs, handles, and approval fingerprints.

The v1.14 apply implementation:

- Exposes `local-apple-data contacts apply` and MCP `contacts_apply_change`.
- Requires the matching `contacts-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through Contacts.framework only after those checks.
- Returns bounded read-back contact detail through the existing Contacts detail shape.
- Keeps automated tests synthetic-only.

## v1.15 Notes Create Apply

The implemented v1.15 phase adds non-mutating Notes create-note planning and the approved apply-capable mutation surface for creating one plaintext note through Notes.app automation. The implemented v1.39 phase adds exact existing folder selection by `notes:folder:v1:` handle for create-note planning and apply. The implemented v1.19 phase adds non-mutating Notes append-text planning and approved append-text apply for exact note handles plus expected current SHA-256. The implemented v1.34 Notes replace gate adds non-mutating replace-text planning and approved full-plaintext replacement for one exact note handle plus expected current SHA-256. The implemented v1.45 Notes move gate adds non-mutating exact-note/exact-folder move-to-folder planning and approved move apply with same-account folder proof. The implemented v1.158 Notes folder move gate adds non-mutating exact empty child-folder move planning and approved destination-parent proof. The implemented v1.42 Notes delete gate adds non-mutating delete planning and approved exact-note deletion with expected current SHA-256, Notes.app delete automation, and absence read-back proof. The implemented v1.179 Notes rich-text body gate is operator-authorized: note body content (the rich-text HTML body plus its extracted visible text) is now readable behind the exact `notes:note:v2:` handle gate through `local-apple-data notes content` / `notes_get_content` with `content_format:html`, bounded by a documented HTML cap and truncation flag, with no broad or bulk body dumps and no broad body search; and it adds approved rich-text `create_html`/`replace_html` apply through sanitized input HTML (`<script>`, event-handler `on*` attributes, and `javascript:`/`vbscript:`/`data:` URIs stripped or rejected) with a semantic (extracted visible-text) read-back proof, because Notes.app normalizes stored HTML so exact-HTML round-trip is not guaranteed. These gates are not permission to move notes outside the exact-note/exact-folder move-to-folder gate, manage folders/accounts outside exact create/rename/empty-child-delete/empty-child-move gates, target folders/accounts outside exact create/move gates, mutate checklist state, create or mutate attachments, mutate locked/shared notes, manage Recently Deleted, delete outside the exact-note delete gate, run broad body search, or run bulk Notes operations outside the v1.182 gate. The implemented v1.182 Notes folder content export gate is operator-authorized (2026-07-07 body-level personal-data ingest approval, order Messages → Mail → Notes; surface green-lit 2026-07-09): `local-apple-data notes export-content` / `notes_export_folder_content` returns bounded (≤ 20 notes/page, ≤ 12000 chars/note), offset-paged, date-bounded (`modified_after` required) plain note text plus full-text `content_sha256` for ONE exact normal `notes:folder:v1:` folder per call, only with an explicit `confirm_bulk` acknowledgement; password-protected and deleted notes are excluded in SQL, smart folders fail closed, responses are transient, and this repo persists nothing — durable storage happens only in the operator's approved downstream private-tier store. It is not permission for broad body search, cross-folder or all-notes single-call dumps, attachment bytes, or any Notes mutation.

The v1.15 planning implementation:

- Exposes `local-apple-data notes plan` and MCP `notes_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create operations without calling Notes.app, reading Notes data, or writing Notes.
- Requires a bounded non-empty title and caps body text at 12000 normalized characters.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned titles, body previews, handles, and approval fingerprints.

The v1.15 apply implementation:

- Exposes `local-apple-data notes apply` and MCP `notes_apply_change`.
- Requires the matching `notes-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through Notes.app automation only after those checks.
- Returns read-back content through the existing exact-handle Notes content shape.
- Keeps automated tests synthetic-only.

The v1.39/v1.159/v1.160 exact-folder selection implementation:

- Exposes read-only `local-apple-data notes folders`, `local-apple-data notes folder`, `local-apple-data notes folder-items`, `local-apple-data notes folder-tree`, `notes_search_folders`, `notes_get_folder`, `notes_list_folder_items`, and `notes_list_folder_tree`.
- Returns `notes:folder:v1:` handles, folder titles, bounded count metadata, capped direct child folder metadata, capped descendant folder metadata, capped direct note metadata, and no account identifiers, raw folder IDs, paths, folder content, note bodies, snippets, or attachment bytes.
- Allows create planning to include one exact `notes:folder:v1:` handle.
- Refuses missing, stale, deleted, fabricated, raw-ID, and smart-folder targets.
- Applies through Notes.app automation by internal folder object ID and requires exact-content read-back plus selected-folder proof.

The v1.34 Notes replace implementation:

- Uses the existing `local-apple-data notes plan/apply` and MCP `notes_plan_change`/`notes_apply_change` surfaces with `operation: replace_text`.
- Requires an exact `notes:note:v2:` handle and expected current content SHA-256 from exact Notes content retrieval.
- Refuses missing, deleted, locked, shared, or drifted notes before applying.
- Replaces only bounded plaintext through Notes.app automation.
- Returns exact-content read-back and never logs handles, content, content hashes, titles, raw IDs, approval fingerprints, or approval tokens.

## v1.16 Mail Draft Create Apply

The implemented v1.16 phase adds non-mutating Mail create-draft planning and the approved apply-capable mutation surface for saving one plaintext draft through Mail.app automation. Later Mail send-message is governed separately by `docs/V1_43_MAIL_SEND_WRITE_DESIGN.md`; v1.16 itself is not permission to send, reply, forward, archive, move, delete, mark read/unread, flag, manage mailboxes/accounts, select sender accounts, attach files, create HTML/rich-text drafts, or run bulk Mail operations.

The v1.16 planning implementation:

- Exposes `local-apple-data mail plan` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested create-draft operations without calling Mail.app, reading Mail data, or writing Mail.
- Requires at least one bounded To recipient and a bounded non-empty subject.
- Caps body text at 12000 normalized characters.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned recipients, subjects, body previews, handles, and approval fingerprints.

The v1.16 apply implementation:

- Exposes `local-apple-data mail apply` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through save-only Mail.app automation after those checks and does not call `send`.
- Returns read-back through the existing exact-handle Mail content shape when the local Drafts store indexes the saved draft.
- Returns `partial` if Mail.app accepts the draft save but read-back is not available yet.
- Keeps automated tests synthetic-only.

## v1.74 Mail Sender Draft Selection

The implemented v1.74 phase adds read-only configured Mail sender metadata and optional exact sender selection for `create_draft` only. `mail_search_senders` / `local-apple-data mail senders` and `mail_get_sender` / `local-apple-data mail sender` return opaque `mail:sender:v1:` handles, masked email previews, `sender_ref`, `account_ref`, and explicit flags that raw identifiers, full email addresses, and sender strings are not returned. Sender search matching is limited to returned-safe masked account labels and masked email previews so hidden full names and full sender email strings are not searchable side channels.

The v1.74 planning implementation:

- Accepts `sender_handle` only for `create_draft`.
- Refuses `sender_handle` on send, reply, reply-all, forward, and triage operations with `unexpected_sender_handle`.
- Re-enumerates configured enabled Mail accounts through public Mail.app scripting and refuses missing, invalid, or duplicate-address sender handles.
- Binds `sender_handle`, `sender_ref`, and `account_ref` into the approval fingerprint without returning full email addresses or raw account IDs.

The v1.74 apply implementation:

- Requires the matching `mail-apply:v1:<approval_fingerprint>` token and explicit confirmation.
- Re-resolves the exact sender handle before writing.
- Sets `sender of draftMessage` before `save draftMessage`.
- Requires selected-sender read-back before returning `sender_selection_confirmed:true`.
- Returns `partial` with `sender_read_back_unavailable` if the draft was saved but Mail did not confirm the selected sender.
- Does not approve sender selection for irreversible send, reply, reply-all, or forward operations.

## v1.82 Mail Outbound Sender Selection

The v1.82 phase extends exact sender selection to `send_message`, `reply_message`, `reply_all_message`, and `forward_message` under `docs/V1_82_MAIL_OUTBOUND_SENDER_SELECTION_WRITE_DESIGN.md`. It reuses the same `mail:sender:v1:` handle search/get surface from v1.74, still returns only masked sender metadata, and still refuses raw sender emails, raw Mail account IDs, SMTP identifiers, mailbox handles, account refs, and fabricated handles.

The v1.82 planning implementation:

- Accepts `sender_handle` for `create_draft`, `send_message`, `reply_message`, `reply_all_message`, and `forward_message`.
- Refuses `sender_handle` on triage operations with `unexpected_sender_handle`.
- Re-enumerates configured enabled Mail accounts through public Mail.app scripting and refuses missing, invalid, stale, or duplicate-address sender handles.
- Binds `sender_handle`, `sender_ref`, `account_ref`, masked preview metadata, operation inputs, and source-message state when applicable into the approval fingerprint without returning full email addresses or raw account IDs.

The v1.82 apply implementation:

- Requires the matching `mail-apply:v1:<approval_fingerprint>` token and explicit confirmation.
- Re-resolves the exact sender handle before writing.
- Sets `sender` on the outgoing draft/send/reply/reply-all/forward message before save/send.
- Requires selected-sender read-back before returning `sender_selection_confirmed:true`.
- Returns `partial` with `sender_read_back_unavailable` if Mail accepted the save/send but did not confirm the selected sender.
- Does not return full sender email addresses, raw account IDs, SMTP IDs, delivery-account identifiers, sent body text, source body text, local Mail paths, or credentials.

## v1.43 Mail Send-Message Apply

The implemented v1.43 phase adds non-mutating Mail send-message planning and the approved apply-capable mutation surface for sending one bounded plaintext outbound message through Mail.app automation. It is not permission to reply, forward, select sender accounts, attach files, create HTML/rich-text mail, use templates, mutate mailboxes/accounts, use network mail paths, or run bulk Mail operations. Reply-message is governed separately by the later v1.44 gate below, and forward-message is governed separately by the later v1.50 gate below.

The v1.43 planning implementation:

- Exposes `local-apple-data mail plan --operation send-message` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, `send_permitted:true`, `irreversible_external_send:true`, and `retry_safe:false`.
- Validates requested send-message operations without calling Mail.app, reading Mail data, saving drafts, sending mail, or writing Mail.
- Requires at least one bounded To recipient and a bounded non-empty subject.
- Caps body text at 12000 normalized characters.
- Returns deterministic idempotency keys and approval fingerprints bound to normalized recipient/subject/body identity for the apply gate.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of planned recipients, subjects, body previews, body hashes, handles, approval tokens, and approval fingerprints.

The v1.43 apply implementation:

- Exposes `local-apple-data mail apply --operation send-message` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Applies through Mail.app automation that creates one hidden outgoing message and runs `send`, without saving a draft, moving/deleting existing messages, or selecting sender accounts.
- Returns Sent-copy read-back when the local Mail store indexes the sent message.
- Returns `partial` with `read_back_unavailable` when Mail.app accepts the send but local Sent indexing is delayed.
- Does not echo the sent body in apply output.
- Keeps automated tests synthetic-only.

## v1.44 Mail Reply-Message Apply

The implemented v1.44 phase adds non-mutating Mail reply-message planning and the approved apply-capable mutation surface for sending one bounded plaintext sender-only reply to one exact selected Mail message through Mail.app automation. Reply-all is governed separately by the v1.73 gate below. It is not permission to reply all outside that gate, forward, redirect, override recipients or subject, select sender accounts, attach files, create HTML/rich-text mail, mutate mailboxes/accounts, use network mail paths, or run bulk Mail operations. Forward-message is governed separately by the later v1.50 gate below.

The v1.44 planning implementation:

- Exposes `local-apple-data mail plan --operation reply-message` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, `reply_all_permitted:false`, `irreversible_external_send:true`, and `retry_safe:false`.
- Requires an exact opaque `mail:message:v2:` handle from Mail metadata output.
- Resolves the selected message through read-only Mail metadata and local `.emlx` RFC Message-ID extraction.
- Rejects direct To/Cc/Bcc recipient input and direct subject input because Mail.app derives reply routing from the exact source message.
- Caps body text at 12000 normalized characters and returns only a bounded body preview.
- Binds approval to the source message handle, current source state, reply mode, and normalized reply body hash.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of reply body previews, body hashes, message handles, mailbox references, RFC Message-IDs, approval tokens, and approval fingerprints.

The v1.44 apply implementation:

- Exposes `local-apple-data mail apply --operation reply-message` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying and refuses stale source-message state.
- Applies through Mail.app automation scoped by account, mailbox, and RFC Message-ID, then runs `reply sourceMessage opening window false reply to all false`.
- Sets the bounded plaintext reply body, clears the message signature, and sends the reply without saving a draft, moving/deleting existing messages, or adding direct recipients.
- Returns Sent-copy read-back when the local Mail store indexes the sent reply.
- Returns `partial` with `read_back_unavailable` when Mail.app accepts the reply but local Sent indexing is delayed.
- Does not echo the reply body in apply output.
- Keeps automated tests synthetic-only.

## v1.73 Mail Reply-All Apply

The implemented v1.73 phase adds non-mutating Mail reply-all-message planning and the approved apply-capable mutation surface for sending one bounded plaintext reply-all response to one exact selected Mail message through Mail.app automation. It is not permission to override recipients or subject, forward, redirect, select sender accounts, attach files, create HTML/rich-text mail, mutate mailboxes/accounts, use network mail paths, or run bulk Mail operations.

The v1.73 planning implementation:

- Exposes `local-apple-data mail plan --operation reply-all-message` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, `reply_all_permitted:true`, `reply_mode:"reply_all"`, `recipient_inputs_permitted:false`, `irreversible_external_send:true`, and `retry_safe:false`.
- Requires an exact opaque `mail:message:v2:` handle from Mail metadata output.
- Resolves the selected message through read-only Mail metadata and local `.emlx` RFC Message-ID extraction.
- Rejects direct To/Cc/Bcc recipient input and direct subject input because Mail.app derives reply-all routing from the exact source message.
- Caps body text at 12000 normalized characters and returns only a bounded body preview.
- Binds approval to the source message handle, current source state, reply mode, and normalized reply body hash.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of reply body previews, body hashes, message handles, mailbox references, RFC Message-IDs, approval tokens, and approval fingerprints.

The v1.73 apply implementation:

- Exposes `local-apple-data mail apply --operation reply-all-message` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying and refuses stale source-message state.
- Applies through Mail.app automation scoped by account, mailbox, and RFC Message-ID, then runs `reply sourceMessage opening window false reply to all true`.
- Sets the bounded plaintext reply body, clears the message signature, and sends the reply-all without saving a draft, moving/deleting existing messages, or adding direct recipients.
- Returns Sent-copy read-back when the local Mail store indexes the sent reply.
- Returns `partial` with `read_back_unavailable` when Mail.app accepts the reply-all but local Sent indexing is delayed.
- Does not echo the reply body in apply output.
- Keeps automated tests synthetic-only.

## v1.50 Mail Forward-Message Apply

The implemented v1.50 phase adds non-mutating Mail forward-message planning and the approved apply-capable mutation surface for sending one bounded plaintext-prefaced forward of one exact selected Mail message through Mail.app automation. It is not permission to reply all outside the separate v1.73 gate, redirect, override subject, forward source messages with attachments or non-body source parts, add new attachments, select sender accounts, create HTML/rich-text mail, mutate mailboxes/accounts, use network mail paths, or run bulk Mail operations.

The v1.50 planning implementation:

- Exposes `local-apple-data mail plan --operation forward-message` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, `recipient_inputs_permitted:true`, `subject_input_permitted:false`, `source_body_included:true`, `source_attachments_permitted:false`, `source_non_text_parts_permitted:false`, `irreversible_external_send:true`, and `retry_safe:false`.
- Requires an exact opaque `mail:message:v2:` handle from Mail metadata output.
- Resolves the selected message through read-only Mail metadata and local `.emlx` RFC Message-ID extraction.
- Rejects direct subject input because the forward subject is derived from the exact source message.
- Rejects source messages with MIME attachments or non-body MIME parts so this gate cannot forward attachments or non-body source parts.
- Requires at least one bounded To recipient and a non-empty bounded plaintext `body_text` used as prepend text.
- Binds approval to the source message handle, current source state, zero-attachment/non-body-part state, recipients, derived forward subject, and normalized prepend body hash.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of forward body previews, body hashes, message handles, mailbox references, RFC Message-IDs, approval tokens, approval fingerprints, recipients, and source content.

The v1.50 apply implementation:

- Exposes `local-apple-data mail apply --operation forward-message` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying and refuses stale source-message state, stale source attachment/non-body-part state, or stale source-content state.
- Applies through Mail.app automation scoped by account, nested mailbox path, and RFC Message-ID, then runs `forward sourceMessage opening window false`.
- Sets a deterministic derived subject, prepends bounded plaintext body text, adds explicit recipients, clears message signature, and sends the forward without saving a draft, moving/deleting existing messages, or forwarding source attachments/non-body source parts.
- Returns Sent-copy read-back when the local Mail store indexes the sent forward.
- Returns `partial` with `read_back_unavailable` when Mail.app accepts the forward but local Sent indexing is delayed.
- Does not echo the forward body or source message content in apply output.
- Keeps automated tests synthetic-only.

The implemented v1.80 phase extends forward-message only. Default planning still refuses source messages with attachments or non-body MIME parts. When the caller explicitly sets `include_source_attachments`, planning binds uncapped header-only source attachment-like part state and apply lets Mail.app preserve those source parts through native exact-source forwarding. Apply verifies Mail's pre-send attachment count against caller-selected local attachments plus locally counted source parts, then returns counts and booleans only. It does not expose source attachment bytes, source attachment paths, raw MIME, source message content, per-part Sent identity/content proof, sender selection, subject override, real/non-synthetic mailbox/account management, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, HTML/rich-text mutation, query-result auto-apply, or unbounded bulk mutation. Later gates add signatures/templates/query-result planning and synthetic-only mailbox/cleanup without changing this forward gate.

## v1.32 Mail Read-State Apply

The implemented v1.32/v1.37/v1.40/v1.41/v1.46/v1.66/v1.78 Mail triage phases add non-mutating Mail mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message planning and the approved apply-capable mutation surface for exact selected message read state, flagged state, same-account Archive mailbox move, exact target-mailbox move including cross-account exact targets, same-account Trash mailbox move, and capped exact bulk triage over unique selected handles. The implemented v1.83 phase can turn capped FTS/search results into an exact bulk triage plan, but still does not auto-apply query results. The implemented v1.84 phase adds synthetic `LAD-TEST-*` mailbox management and synthetic-only permanent delete/empty Trash/Junk cleanup with read-back/absence proof. These gates are not permission to send outside the send-message gate, reply outside the sender-only or reply-all gates, forward outside the exact forward-message gate, forward source attachments/non-body parts outside explicit `include_source_attachments`, cross-account move messages outside the approved exact target-mailbox gate, permanently delete non-synthetic mail, empty Trash/Junk when any non-synthetic target is present, flag outside the approved exact-message or capped exact bulk flag/unflag gate, archive outside the approved exact-message or capped exact bulk same-account Archive gate, move outside the approved exact-message or capped exact bulk target-mailbox gate, move to Trash outside the approved exact-message or capped exact bulk same-account Trash gate, manage non-synthetic mailboxes/accounts, select sender accounts outside the draft/send/reply/reply-all/forward sender gate, mutate attachments outside the approved outbound local-file attachment gates, create HTML/rich-text drafts, query-result auto-apply, or run unbounded bulk Mail operations.

The v1.32 Stage 1 planning implementation:

- Exposes `local-apple-data mail plan --operation mark-read|mark-unread|flag-message|unflag-message` and MCP `mail_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Requires an exact opaque `mail:message:v2:` handle from Mail metadata output.
- Resolves the selected message through read-only Mail metadata and local `.emlx` RFC Message-ID extraction.
- Binds approval to the current read and flagged state so apply refuses stale message state.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of message handles, mailbox references, RFC Message-IDs, state fingerprints, approval fingerprints, and tokens.

The v1.32 Stage 1 apply implementation:

- Exposes `local-apple-data mail apply --operation mark-read|mark-unread|flag-message|unflag-message` and MCP `mail_apply_change`.
- Requires the matching `mail-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying.
- Uses Mail.app automation scoped to the selected account, mailbox, and RFC Message-ID.
- Returns read-back metadata and refuses stale message state before applying.
- Keeps redacted event logs free of handles, raw Mail paths, raw Mail identifiers, RFC Message-IDs, approval fingerprints, and tokens.

The v1.78 bulk triage implementation:

- Exposes repeated `--message-handle` inputs on `local-apple-data mail plan/apply` and optional MCP `message_handles` for the same triage operations only.
- Requires at least two exact selected `mail:message:v2:` handles for bulk mode and caps the batch at 20 handles.
- Binds every selected handle, current read/flag/mailbox state, and target state into one approval fingerprint.
- Preflights every selected message before the first Mail automation call.
- Skips already-satisfied selected messages without automation.
- Returns `partial` if Mail automation or read-back fails after at least one earlier message applied.
- Does not allow query-result auto-apply, broad mailbox operations, real/non-synthetic permanent delete, real/non-synthetic empty Trash/Junk, real account management, or unbounded bulk mutation. Synthetic `LAD-TEST-*` mailbox/cleanup is governed separately by `docs/V1_84_MAIL_SYNTHETIC_MAILBOX_CLEANUP_WRITE_DESIGN.md`.

## v1.17 Photos Import Apply

The implemented v1.17 phase adds non-mutating Photos import planning and the approved apply-capable mutation surface for importing one caller-selected local image or video file through PhotoKit. The implemented v1.134 phase adds exact asset favorite/hidden update planning and approved apply with expected-state binding and read-back verification. The implemented v1.149 phase adds exact selected-asset delete planning and approved apply with expected-state binding, public PhotoKit delete support checks, and absence proof. The implemented v1.151 phase adds exact regular-album membership add/remove planning and approved apply with exact `photos:asset:v1:` and `photos:album:v1:` handles, `expected_in_album` binding, public PhotoKit album membership change requests, and read-back proof. The implemented v1.154 phase adds exact regular-album create/rename/delete with full Photos Library authorization planning and approved apply with full Photos Library authorization, bounded-title validation, exact album-state binding, duplicate-title refusal, empty-delete proof, and title or absence read-back. These gates are not permission to edit asset content, delete assets outside the exact selected-asset gate, permanently delete or empty Recently Deleted, target smart/shared/synced albums, mutate metadata outside favorite/hidden, return thumbnails, return inline asset bytes, fetch missing iCloud media over the network, or run bulk Photos operations.

The v1.17 planning implementation:

- Exposes `local-apple-data photos plan` and MCP `photos_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested import operations without calling PhotoKit or writing Photos.
- Requires a caller-selected regular local image or video source file.
- Refuses symlinks, directories, empty files, unsupported media types, media-type mismatches, and oversized files.
- Returns deterministic idempotency keys and approval fingerprints for the apply gate.
- Returns source filename, media type, file size, and source-file hash in the transient preview response.
- Does not echo the raw source path.
- Keeps automated tests synthetic-only.
- Keeps redacted event logs free of source paths, source filenames, source hashes, PhotoKit identifiers, handles, and approval fingerprints.

The v1.17 apply implementation:

- Exposes `local-apple-data photos apply` and MCP `photos_apply_change`.
- Requires the matching `photos-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying so changed source bytes invalidate stale approval tokens.
- Applies through a Swift PhotoKit helper and `PHPhotoLibrary.performChanges`.
- Returns read-back metadata for the created asset through the existing opaque-handle Photos detail shape.
- Keeps automated tests synthetic-only.
- v1.134 `update_flags` apply binds an exact `photos:asset:v1:` handle plus expected favorite/hidden state and verifies selected-asset read-back without raw PhotoKit identifiers.
- v1.149 `delete` apply binds an exact `photos:asset:v1:` handle plus expected safe state, requires PhotoKit `canPerform(.delete)`, and reports success only with `verified_absent:true`, `recently_deleted_empty:false`, no raw PhotoKit identifier return, and no asset bytes.

## v1.24 Messages Send-Text Apply

The implemented v1.24 phase adds non-mutating Messages send-text planning and the approved apply-capable mutation surface for sending one bounded plaintext message to one exact existing chat through Messages.app automation. Send-file is governed separately by the later v1.38 gate below; v1.24 itself is not permission to send to direct recipients, create chats, choose SMS fallback or outgoing accounts, react/tapback, edit, unsend, delete, mark read, manage groups, expose participants, or run bulk Messages operations.

The v1.24 planning implementation:

- Exposes `local-apple-data messages plan` and MCP `messages_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested send-text operations without calling Messages.app or writing Messages data.
- Requires exact opaque `messages:chat:v1:` handles for target-chat planning.
- Returns bounded body preview text, body length, deterministic idempotency keys, and approval fingerprints for the apply gate.
- Binds approval to current chat state, including message count and last-message row.
- Keeps redacted event logs free of body text, body previews, body hashes, chat GUIDs, handles, participant identifiers, and approval fingerprints.
- Keeps automated tests synthetic-only.

The v1.24 apply implementation:

- Exposes `local-apple-data messages apply` and MCP `messages_apply_change`.
- Requires the matching `messages-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying so changed body text or changed chat state invalidates stale approval tokens.
- Applies through Messages.app AppleScript only after approval checks pass.
- Returns success only after local `chat.db` read-back confirms a newer outgoing row joined to the selected chat with matching body hash.
- Detects empty unjoined outgoing ghost rows and returns a non-success status.
- Does not echo the sent body text in apply read-back.
- Keeps automated tests synthetic-only.

## v1.38 Messages Send-File Apply

The implemented v1.38 phase adds non-mutating Messages send-file planning and the approved apply-capable mutation
surface for sending one bounded local file to one exact existing chat through Messages.app automation. It is not
permission to send to direct recipients, create chats, choose SMS fallback or outgoing accounts, return file bytes
or local file paths, react/tapback, edit, unsend, delete, mark read, manage groups, expose participants, mutate
attachments broadly, or run bulk Messages operations.

The v1.38 planning implementation:

- Reuses `local-apple-data messages plan` and MCP `messages_plan_change`.
- Returns `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Validates requested send-file operations without calling Messages.app or writing Messages data.
- Requires exact opaque `messages:chat:v1:` handles for target-chat planning.
- Validates one local regular non-empty file under the implementation size cap.
- Returns bounded file name/type/size metadata, deterministic idempotency keys, and approval fingerprints for the apply gate.
- Binds approval to current chat state and internal file identity without returning local file paths or file bytes.
- Keeps redacted event logs free of file paths, file bytes, chat GUIDs, handles, participant identifiers, and approval fingerprints.
- Keeps automated tests synthetic-only.

The v1.38 apply implementation:

- Reuses `local-apple-data messages apply` and MCP `messages_apply_change`.
- Requires the matching `messages-apply:v1:<approval_fingerprint>` token.
- Requires explicit confirmation.
- Recomputes the plan before applying so changed file identity or changed chat state invalidates stale approval tokens.
- Applies through Messages.app AppleScript only after approval checks pass.
- Returns success only after local `chat.db` read-back confirms a newer outgoing attachment joined to the selected chat.
- Detects empty unjoined outgoing ghost rows and returns a non-success status.
- Does not return file bytes or local file paths in apply read-back.
- Keeps automated tests synthetic-only.

## v1.7 Photos Asset Detail Retrieval

The implemented v1.7 phase adds PhotoKit-backed Photos original-filename search, exact-handle asset resource metadata retrieval, and exact-handle asset export to a caller-selected output directory. It is not permission to run broad Photos dumps, return image/video bytes inline, fetch missing iCloud media over the network, or mutate Photos data.

The v1.7 implementation:

- Requires a `photos:asset:v1:` handle returned by `photos search`.
- Searches local Photos by original filename only, with empty and broad queries rejected before PhotoKit access.
- Uses a non-prompting PhotoKit helper app for normal reads/writes. If Photos are not authorized for the current process, it returns a safe `photos_access_unavailable` warning; `photos request-access` is the explicit CLI-only prompt path after TCC resets. The helper declares PhotoKit purpose strings and the macOS Photos Library entitlement; if macOS leaves authorization `not_determined`, the operator must approve `Local Apple Data Photos Helper` in Privacy & Security > Photos.
- Returns media type, dimensions, dates, favorite/hidden flags, source type, primary filename, resource count, and opaque handle during search.
- Reads asset resource filenames, resource types, and uniform type identifiers only for exact selected asset handles.
- Does not return image/video bytes inline, thumbnails, raw Photos identifiers, or source paths. Export returns only caller-selected destination metadata.
- Rejects raw Photos identifiers, fabricated handles, broad content search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.8 Messages Chat Transcript Retrieval

The implemented v1.8 phase adds read-only Messages chat display-name search and exact-handle bounded chat transcript retrieval. It is not permission to run broad Messages text search, expose participant phone/email identifiers, or mutate/send Messages.

The v1.8 implementation:

- Requires a `messages:chat:v1:` handle returned by `messages search`.
- Searches local Messages chats by chat display name only, with empty and broad queries rejected before opening `chat.db`.
- Opens `~/Library/Messages/chat.db` read-only and query-only.
- Returns chat display name, service name, participant count, message count, last message date, and opaque handle during search.
- Reads recent message text only for exact selected chat handles, with `max_messages` and `max_chars` caps. When modern Messages rows leave `message.text` empty, it may decode bounded plaintext from the local `message.attributedBody` typedstream value.
- Does not return participant phone numbers, email addresses, chat GUIDs, raw message IDs, attachments, raw attributed-body blobs, attributed-string attributes, tapbacks/reactions, or send-state metadata.
- Rejects raw row IDs, raw chat GUIDs, fabricated handles, broad message-text search, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.64 Messages Participant Metadata

The implemented v1.64 phase adds read-only Messages selected-chat participant metadata and exact selected-participant detail. It is not permission to run broad participant dumps, return phone/email previews in list output, perform contact lookup, send to direct recipients, create chats, choose SMS fallback or outgoing accounts, react/tapback, edit, unsend, delete, mark read, manage groups, or run bulk Messages operations.

The v1.64 implementation:

- Requires a `messages:chat:v1:` handle returned by `messages search` before listing participants.
- Returns opaque `messages:participant:v1:` handles, service, message count, and last-message timestamp during participant listing.
- Does not return participant phone numbers, email addresses, or masked identifier previews during participant listing.
- Requires both the original selected chat handle and selected participant handle before exact participant detail can return the full selected participant identifier.
- Opens `~/Library/Messages/chat.db` read-only and query-only.
- Rejects raw participant identifiers, raw row IDs, raw chat GUIDs, fabricated handles, mutation targeting, broad participant dumps, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.9 Voice Memos Transcript Retrieval

The implemented v1.9 phase adds read-only Voice Memos title/filename search, exact-handle existing embedded transcript retrieval, and exact-handle `.m4a` export to a caller-selected output directory. It is not permission to run broad transcript search, return audio bytes inline, generate transcripts, or mutate Voice Memos data.

The v1.9 implementation:

- Requires a `voice_memos:recording:v1:` handle returned by `voice-memos search`.
- Searches local Voice Memos by title or filename only, with empty and broad queries rejected before opening `CloudRecordings.db`.
- Opens the local Voice Memos `CloudRecordings.db` read-only and query-only.
- Returns title, recorded date, duration, local audio availability, and opaque handle during search.
- Reads existing Apple-generated transcript JSON only for exact selected recording handles when a local `.m4a` contains the `tsrp` atom.
- Returns bounded transcript text with truncation metadata and never returns audio bytes inline, raw source file paths, or recording identifiers.
- Rejects raw recording IDs, fabricated handles, broad transcript search, generated transcription, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.25 Safari Bookmarks And Reading List

The implemented v1.25 phase adds read-only Safari bookmark and Reading List search plus exact-handle URL detail, folder-title search, exact folder metadata, and exact selected-folder direct child metadata listing. It is not permission to read Safari history, open tabs, private browsing data, passwords, cookies, sessions, page content, browser caches, broad recursive bookmark/folder dumps, or to mutate bookmarks/folders.

The v1.25 implementation:

- Requires a `safari:item:v1:` handle returned by `safari search` before returning a full URL.
- Requires a `safari:folder:v1:` handle returned by `safari folders` before returning folder detail or direct child metadata.
- Searches local Safari `Bookmarks.plist` by title or URL, with empty and broad queries rejected before reading the store.
- Returns title, kind, URL domain, URL scheme, query-presence, path depth, dates when present, and opaque handle during item search; folder search/listing returns folder titles/counts and child item metadata only.
- Does not return full URLs during search or folder listing.
- Reads and returns the full URL only for exact selected handles.
- Rejects raw identifiers, fabricated handles, Safari history, open tabs, private browsing data, passwords, cookies, browser caches, page content, broad or recursive dumps, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.26 Shortcuts Metadata

The implemented v1.26 phase historically added read-only Apple Shortcuts shortcut/folder name metadata search plus exact-handle metadata detail and exact selected-folder shortcut metadata listing; at that checkpoint it did not permit run/open/view/sign/export/inspect/mutation. The later v1.180C gate supersedes only the run case by approving one exact identifier-bound plan/apply run with matching token, explicit confirmation, argv-only invocation, and a hard timeout; broader execution remains blocked.

The v1.26 implementation:

- Requires a `shortcuts:item:v1:` handle returned by `shortcuts search` before exact metadata detail or selected-folder listing.
- Searches local Shortcuts through Apple's `shortcuts list --show-identifiers` and `shortcuts list --folders --show-identifiers` commands, and lists one selected folder through `shortcuts list --folder-name <identifier> --show-identifiers` using a privately resolved folder identifier from the selected opaque handle. Callers never pass or receive that raw folder identifier, and empty/broad search queries are rejected before invoking the CLI.
- Returns title, kind, identifier-presence, and opaque handle during search.
- Does not return raw Shortcuts identifiers, shortcut bodies, action graphs, source paths, icons, colors, URL schemes, or generated dynamic run tools.
- Refuses folder-scoped searches so handles always resolve from the same global metadata flow.
- Rejects fabricated handles; shortcut runs outside the approved exact-handle plan/apply gate; shortcut open/view/sign/export/body/action-graph reads; dynamic or name-resolved runs; import/create/update/delete/duplicate; Shortcuts SQLite scraping; private iCloud APIs; browser/keychain access; background indexing; and durable content caches.
- Keeps automated tests synthetic-only.

## v1.29 Apple Music Metadata

The implemented v1.29 phase adds read-only Apple Music track and playlist metadata search plus exact-handle metadata detail and capped selected-playlist track metadata. It is not permission to export audio, lyrics, file paths, play history, ratings/favorites, broad playlist track dumps, playback/queue state, raw Music database parsing, iCloud media fetch, or mutate Music.app.

The v1.29 implementation:

- Requires `music:track:v1:` or `music:playlist:v1:` handles returned by `music search` or `music playlists`.
- Searches through bounded Music.app automation with empty/broad queries rejected before invoking `osascript`.
- Health checks only Music.app/osascript/library-package readiness and does not open Music.app or inspect tracks.
- Returns track title/artist/album/album-artist/genre/duration/track/disc/year, playlist title/kind/count/duration, or capped selected-playlist track metadata.
- Does not return raw persistent IDs/database IDs, file paths, audio bytes, lyrics, play history, ratings/favorites, cloud account state, or broad playlist track dumps.
- Rejects fabricated handles, broad dumps, playback/queue control, Music.app mutation, private APIs, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.30 Apple TV Metadata

The implemented v1.30 phase adds read-only Apple TV item, playlist, and selected-playlist item metadata search plus exact-handle metadata detail. It is not permission to export video, file paths, artwork, descriptions, playback state, watched state, ratings/favorites, broad playlist items, raw TV library parsing, iCloud media fetch, or mutate TV.app.

The v1.30 implementation:

- Requires `tv:item:v1:` or `tv:playlist:v1:` handles returned by `tv search` or `tv playlists`.
- Searches through bounded TV.app automation with empty/broad queries rejected before invoking `osascript`.
- Health checks only TV.app/osascript/library-package readiness and does not open TV.app or inspect TV items.
- Returns item title/show/artist/genre/video-kind/duration/season/episode/year, playlist title/kind/count/duration, or capped selected-playlist item metadata.
- Does not return raw persistent IDs/database IDs, file paths, video bytes, artwork, descriptions, playback state, watched state, ratings/favorites, cloud account state, or broad playlist item dumps.
- Rejects fabricated handles, broad dumps, playback/queue control, TV.app mutation, private APIs, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.10 Hide My Email Inferred Alias Retrieval

The implemented v1.10 phase adds read-only inferred Hide My Email alias search from local Mail address metadata and exact-handle alias detail retrieval. It is not an authoritative iCloud Hide My Email inventory, and it is not permission to create, deactivate, delete, or manage aliases.

The v1.10 implementation:

- Requires a `hide_my_email:alias:v1:` handle returned by `hide-my-email search` before returning a full alias.
- Searches local Mail `addresses`, `messages`, and `recipients` metadata only, with empty, domain-only, and generic queries rejected before opening the Mail store.
- Returns masked alias previews, domain, inference kind, confidence, message-count metadata, provenance, and `authoritative_inventory:false` during search.
- Reads and returns the full alias only for exact selected handles.
- Distinguishes high-confidence Sign in with Apple private relay aliases from medium-confidence iCloud Hide My Email-like aliases inferred from local Mail evidence.
- Rejects raw identifiers, fabricated handles, broad domain searches, iCloud.com/browser automation, private iCloud web APIs, keychain credentials, mutations, background indexing, and durable content caches.
- Keeps automated tests synthetic-only.

## v1.184 Exact Mail Unsubscribe Metadata

This read-only exact-detail gate returns only allowlisted endpoint URLs from
`List-Unsubscribe` and `List-Help`, plus the RFC 8058 post-header classification,
for one selected `mail:message:v2:` handle. It reads only a bounded local header
prefix, never the body or unrelated headers, and returns only opaque
account/mailbox refs. Endpoint URLs are permitted only in this exact selected
response and are excluded from durable event logs. Control-bearing, malformed,
credential-bearing, and non-http(s)/mailto values are omitted without echoing
them. `List-Help` is always manual-only. This gate adds no network access,
unsubscribe action, Mail mutation, broad header search, or durable cache.

Body-link inspection remains off by default. Explicit `include_body_links`
inspects only HTML anchor metadata in the exact selected MIME body, returns at
most five conservatively matched URLs, and returns no body text, anchor labels,
or unrelated URLs. Its privacy flags set `message_body_inspected:true`; every
returned body endpoint is manual-required and never one-click. MIME input is
bounded at 10 MiB and too-large or unparseable content fails closed with safe
warning codes.

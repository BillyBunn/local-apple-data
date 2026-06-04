# Changelog

All notable public-release changes are tracked here.

## 0.1.0+codex.20260605050000 - 2026-06-04

### Added

- Read-only Apple Freeform recent-board metadata listing through `local-apple-data freeform boards` and MCP `freeform_list_boards`.
- Exact selected Apple Freeform board metadata retrieval through `local-apple-data freeform get` and MCP `freeform_get_board`.
- Read-only Apple Freeform folder title metadata search through `local-apple-data freeform folders` and MCP `freeform_search_folders`.
- Exact selected Apple Freeform folder metadata retrieval through `local-apple-data freeform folder` and MCP `freeform_get_folder`.
- Synthetic Freeform SQLite fixtures, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Freeform metadata surface.

### Security

- Freeform board listing returns recency, favorite/collaborator-cursor flags, item counts, and asset-reference counts only; board titles are not returned because the title/content lives in BLOB/CRDT data.
- Freeform folder search returns folder-title metadata only for specific folder-title queries.
- Board BLOB decoding, board content export, asset export, previews, collaboration payloads, raw identifiers, raw `boards.db` rows, broad dumps, and Freeform mutation remain blocked.

## 0.1.0+codex.20260605040000 - 2026-06-04

### Added

- Read-only Apple TV item metadata search through `local-apple-data tv search` and MCP `tv_search`.
- Exact selected Apple TV item metadata retrieval through `local-apple-data tv get` and MCP `tv_get_item`.
- Read-only Apple TV playlist metadata search through `local-apple-data tv playlists` and MCP `tv_search_playlists`.
- Exact selected Apple TV playlist metadata retrieval through `local-apple-data tv playlist` and MCP `tv_get_playlist`.
- Synthetic TV.app automation runner, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the TV metadata surface.

### Security

- TV search returns item/playlist metadata and opaque handles only; raw TV identifiers, file paths, video bytes, artwork, descriptions, playback state, watched state, ratings, and playlist item dumps are not returned.
- The first TV tranche uses bounded read-only TV.app automation because the local `Library.tvdb` format is proprietary and not SQLite.
- TV playback, queue changes, playlist mutation, rating/favorite mutation, library import/delete, video export, file-path export, raw TV library parsing, iCloud media fetch, and broad library dumps remain blocked.

## 0.1.0+codex.20260605030000 - 2026-06-04

### Added

- Read-only Apple Music track metadata search through `local-apple-data music search` and MCP `music_search`.
- Exact selected Apple Music track metadata retrieval through `local-apple-data music get` and MCP `music_get_track`.
- Read-only Apple Music playlist metadata search through `local-apple-data music playlists` and MCP `music_search_playlists`.
- Exact selected Apple Music playlist metadata retrieval through `local-apple-data music playlist` and MCP `music_get_playlist`.
- Synthetic Music.app automation runner, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Music metadata surface.

### Security

- Music search returns track/playlist metadata and opaque handles only; raw Music identifiers, file paths, audio bytes, lyrics, play history, ratings, and playlist track dumps are not returned.
- The first Music tranche uses bounded read-only Music.app automation because the local `Library.musicdb` format is proprietary and not SQLite.
- Music playback, queue changes, playlist mutation, rating/favorite mutation, library import/delete, audio export, lyrics export, raw Music database parsing, and broad library dumps remain blocked.

## 0.1.0+codex.20260605020000 - 2026-06-04

### Added

- Read-only Apple Podcasts show metadata search through `local-apple-data podcasts search` and MCP `podcasts_search`.
- Exact selected Apple Podcasts show metadata retrieval through `local-apple-data podcasts get` and MCP `podcasts_get_show`.
- Bounded selected-show episode listing through `local-apple-data podcasts episodes` and MCP `podcasts_list_episodes`.
- Exact selected-episode bounded description retrieval through `local-apple-data podcasts episode` and MCP `podcasts_get_episode`.
- Synthetic Apple Podcasts SQLite fixtures, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Podcasts surface.

### Security

- Podcasts search returns show metadata and opaque handles only; raw show IDs, feed URLs, web URLs, local paths, and episode descriptions are not returned.
- Episode descriptions are returned only after an exact `podcasts:episode:v1:` handle from the selected-show episode flow.
- Transcript text/export, audio/video bytes, feed/enclosure URL extraction, broad episode-description dumps/search, raw Podcasts identifiers/paths, iCloud media fetch, Podcasts.app automation, and Podcasts mutation remain blocked.

## 0.1.0+codex.20260605010000 - 2026-06-04

### Added

- Read-only Apple Books library metadata search through `local-apple-data books search` and MCP `books_search`.
- Exact selected Apple Books metadata retrieval through `local-apple-data books get` and MCP `books_get`.
- Exact selected-book annotation listing through `local-apple-data books annotations` and MCP `books_list_annotations`, with bounded highlight/note text.
- Synthetic Apple Books SQLite fixtures, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Books surface.

### Security

- Books search returns title/author/genre metadata and opaque handles only; raw asset IDs, local paths, and annotation UUIDs are not returned.
- Annotation text is returned only after an exact `books:book:v1:` handle from the Books metadata flow.
- Book/chapter text extraction, PDF/EPUB parsing, broad annotation dumps/search, raw local book paths, iCloud fetch, and Books mutation remain blocked.

## 0.1.0+codex.20260605000000 - 2026-06-04

### Added

- Read-only Apple Shortcuts shortcut/folder metadata search through `local-apple-data shortcuts search` and MCP `shortcuts_search`.
- Exact selected Shortcuts metadata retrieval through `local-apple-data shortcuts get` and MCP `shortcuts_get_item`.
- Synthetic Shortcuts CLI runner, adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Shortcuts metadata surface.

### Security

- Shortcuts search returns names and opaque handles only; raw Shortcuts identifiers are not returned.
- The Shortcuts surface does not run, open, view, sign, export, or return shortcut bodies/action graphs.
- Shortcut creation, update, delete, duplication, import, signing, dynamic run tools, folder-scoped handles, Shortcuts SQLite scraping, and mutation remain blocked.

## 0.1.0+codex.20260604235900 - 2026-06-04

### Added

- Read-only Safari bookmarks and Reading List search through `local-apple-data safari search` and MCP `safari_search`.
- Exact selected Safari bookmark or Reading List URL detail through `local-apple-data safari get` and MCP `safari_get_item`.
- Synthetic plist adapter, CLI, MCP, health, runtime, surface-contract, and redaction coverage for the Safari read surface.

### Security

- Safari search returns title/domain metadata only and does not return full URLs.
- Full URLs are returned only by exact opaque `safari:item:v1:` handle.
- Safari history, open tabs/iCloud tabs, private browsing data, cookies, passwords, browser caches, page content, browser sessions, Safari UI automation, and bookmark mutation remain blocked.

## 0.1.0+codex.20260604230000 - 2026-06-04

### Added

- Approved Messages send-text apply through `local-apple-data messages apply` and MCP `messages_apply_change`.
- Non-mutating Messages send-text planning through `local-apple-data messages plan` and MCP `messages_plan_change`.
- Exact-existing-chat handle binding, body-hash approval tokens, explicit confirmation, stale chat-state refusal, Messages.app automation, ghost-row detection, and local `chat.db` read-back verification for Messages send-text apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Messages send-text apply surface.

### Security

- `messages_apply_change` is the only approved Messages mutation tool and is non-destructive, idempotent, and closed-world at the MCP annotation level.
- Apply output confirms the send by metadata and body SHA-256 but does not echo the sent body text.
- Direct-recipient sends, new chat creation, SMS fallback selection, outgoing-account selection, file sends, rich text/effects, reactions/tapbacks, edit, unsend, delete, group management, participant lookup, broad Messages text search, and Messages attachment mutation remain blocked by mutation gates.

## 0.1.0+codex.20260604220000 - 2026-06-04

### Added

- Exact Messages transcript fallback for modern local `message.attributedBody` typedstream rows when `message.text` is empty.
- Native Swift helper coverage for extracting bounded plaintext from exact selected Messages rows without returning raw attributed-body blobs or attributes.
- Synthetic unit, runtime, helper presence, release-readiness, and cross-agent sync coverage for the attributed-body fallback path.

### Security

- Messages `attributedBody` decoding remains exact-chat only, bounded by existing `max_messages` and `max_chars` caps, and never exposes raw typedstream payloads, participant identifiers, reactions, source paths, or message database row IDs.
- If one attributed-body value cannot be decoded safely, the adapter returns a stable warning and preserves any normal text rows plus any individually decodable fallback rows.

## 0.1.0+codex.20260604210000 - 2026-06-04

### Added

- Exact-handle Messages attachment metadata listing through `local-apple-data messages attachments` and MCP `messages_list_attachments`.
- Exact-handle local Messages attachment export through `local-apple-data messages export-attachment` and MCP `messages_export_attachment`.
- Synthetic Messages `chat.db` attachment metadata/export, unavailable-media, CLI, MCP, runtime, surface-contract, and redacted-log coverage.

### Security

- Messages attachment bytes are never returned inline, source media paths are never returned, and export writes only to a caller-selected output directory.
- Export requires both the selected `messages:chat:v1:` chat handle and selected `messages:attachment:v1:` attachment handle so a detached token cannot trigger a broad Messages media scan.
- Messages send/edit/delete, broad attachment export, participant identifiers, reactions, source paths, remote/iCloud media fetch, and attachment mutation remain blocked.

## 0.1.0+codex.20260604200000 - 2026-06-04

### Added

- Exact-handle Mail attachment metadata listing through `local-apple-data mail attachments` and MCP `mail_list_attachments`.
- Exact-handle local Mail MIME attachment export through `local-apple-data mail export-attachment` and MCP `mail_export_attachment`.
- Synthetic MIME attachment export, externalized/partial attachment unavailable, CLI, MCP, runtime, surface-contract, and redacted-log coverage for Mail attachment export.

### Security

- Mail attachment bytes are never returned inline, source `.emlx` or attachment paths are never returned, and remote or externalized missing attachments are not fetched.
- Export requires both the selected `mail:message:v2:` message handle and selected `mail:attachment:v1:` attachment handle so the tool does not scan the whole Mail store to resolve a detached token.
- Mail send/reply/forward, attachment mutation, broad attachment export, raw MIME/full-header exposure, and mailbox/account mutation remain blocked.

## 0.1.0+codex.20260604190000 - 2026-06-04

### Added

- Exact-handle Notes attachment metadata listing through `local-apple-data notes attachments` and MCP `notes_list_attachments`.
- Exact-handle local Notes attachment export through `local-apple-data notes export-attachment` and MCP `notes_export_attachment`.
- Synthetic media-file export, BLOB fallback, remote-only unavailable, CLI, MCP, runtime, surface-contract, and redacted-log coverage for Notes attachment export.

### Security

- Notes attachment bytes are never returned inline, source media paths are never returned, and remote attachment URLs are not fetched.
- Notes attachment creation, replacement, deletion, rename, move, OCR, transcription, broad export, and attachment mutation remain blocked.

## 0.1.0+codex.20260604180000 - 2026-06-04

### Added

- Approved Notes append-text apply through the existing `local-apple-data notes apply` and MCP `notes_apply_change` surfaces.
- Non-mutating Notes append-text planning through `local-apple-data notes plan` and MCP `notes_plan_change`.
- Exact-note-handle, expected-current-SHA-256, approval-token, explicit-confirmation, bounded plaintext append, drift-refusal, shared/locked-note refusal, and exact-content read-back verification checks for Notes append-text apply.
- Synthetic adapter, CLI, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the expanded Notes apply surface.

### Security

- `notes_apply_change` remains non-destructive, idempotent, and closed-world at the MCP annotation level; append-text refuses to apply when the current note content hash no longer matches the approved plan.
- Notes arbitrary update, delete, move, folder/account targeting, rich text, attachments, locked/shared-note mutation, Recently Deleted management, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604170000 - 2026-06-04

### Added

- Approved iCloud Drive append-text apply through the existing `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change` surfaces.
- Non-mutating iCloud Drive append-text planning through `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Exact-file-handle, expected-current-SHA-256, approval-token, explicit-confirmation, bounded UTF-8 append, drift-refusal, and read-back hash verification checks for iCloud Drive append-text apply.
- Synthetic adapter, CLI, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the expanded iCloud Drive text apply surface.

### Security

- `icloud_drive_apply_change` remains non-destructive, idempotent, and closed-world at the MCP annotation level; append-text refuses to apply when the current content hash no longer matches the approved plan.
- iCloud Drive overwrite, rename, move, copy, delete, binary/document writes, raw path writes, hidden-file writes, symlink/package traversal, and broad folder writes remain blocked by mutation gates.

## 0.1.0+codex.20260604160000 - 2026-06-04

### Added

- Approved Photos image/video import apply through `local-apple-data photos apply` and MCP `photos_apply_change`.
- Non-mutating Photos import planning through `local-apple-data photos plan` and MCP `photos_plan_change`.
- Approval-token, explicit-confirmation, source-file hash binding, PhotoKit change-block import, and created-asset read-back verification checks for Photos import apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Photos import apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, `notes_apply_change`, `mail_apply_change`, and `photos_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Photos edit, delete, album targeting, hidden/favorite mutation, metadata mutation, network iCloud fetch, thumbnails, inline asset bytes, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604150000 - 2026-06-04

### Added

- Approved Mail create-draft apply through `local-apple-data mail apply` and MCP `mail_apply_change`.
- Non-mutating Mail create-draft planning through `local-apple-data mail plan` and MCP `mail_plan_change`.
- Approval-token, explicit-confirmation, bounded recipient/subject/body, save-only Mail.app automation, best-effort idempotency, and local Drafts read-back verification checks for Mail create-draft apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Mail draft apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, `notes_apply_change`, and `mail_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Mail send, reply, forward, archive, move, delete, mark read/unread, flag, mailbox/account management, attachments, HTML/rich-text drafts, sender-account selection, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604140000 - 2026-06-04

### Added

- Approved Notes create-note apply through `local-apple-data notes apply` and MCP `notes_apply_change`.
- Non-mutating Notes create-note planning through `local-apple-data notes plan` and MCP `notes_plan_change`.
- Approval-token, explicit-confirmation, bounded title/body, idempotency, Notes.app automation, and exact-content read-back verification checks for Notes create-note apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Notes apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, and `notes_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Notes append, update, delete, move, folder/account targeting, rich text, attachments, locked/shared-note mutation, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604130000 - 2026-06-04

### Added

- Approved Contacts create-contact apply through `local-apple-data contacts apply` and MCP `contacts_apply_change`.
- Non-mutating Contacts create-contact planning through `local-apple-data contacts plan` and MCP `contacts_plan_change`.
- Approval-token, explicit-confirmation, bounded labeled email/phone/URL, idempotency, and read-back verification checks for Contacts create-contact apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved Contacts apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, and `contacts_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Contacts update, delete, merge, move, group membership, postal addresses, birthdays, relationships, social profiles, notes, image data, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604120000 - 2026-06-04

### Added

- Approved Calendar create-event apply through `local-apple-data calendar apply` and MCP `calendar_apply_change`.
- Non-mutating Calendar create-event planning through `local-apple-data calendar plan` and MCP `calendar_plan_change`.
- Approval-token, explicit-confirmation, explicit-calendar-title, timed-event, idempotency, and read-back verification checks for Calendar create-event apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change`, `icloud_drive_apply_change`, and `calendar_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- Calendar update, delete, recurrence, attendees, invitations, alarms, all-day events, default-calendar guessing, and bulk operations remain blocked by mutation gates.

## 0.1.0+codex.20260604110000 - 2026-06-04

### Added

- Approved iCloud Drive create-text apply through `local-apple-data icloud-drive apply` and MCP `icloud_drive_apply_change`.
- Non-mutating iCloud Drive create-text planning through `local-apple-data icloud-drive plan` and MCP `icloud_drive_plan_change`.
- Approval-token, explicit-confirmation, exact-parent-handle, exclusive-create, idempotency, and read-back verification checks for iCloud Drive create-text apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change` and `icloud_drive_apply_change` are the only non-read-only MCP tools and are annotated non-destructive, idempotent, and closed-world.
- iCloud Drive append, overwrite, rename, move, copy, delete, binary/document writes, broad folder writes, and raw path writes remain blocked by mutation gates.

## 0.1.0+codex.20260604100000 - 2026-06-04

### Added

- Approved Reminders apply through `local-apple-data reminders apply` and MCP `reminders_apply_change`.
- Apply support for Reminder create, complete, and due-date update through the Swift EventKit helper.
- Approval-token, explicit-confirmation, expected-state, idempotency, and read-back verification checks for Reminders apply.
- Synthetic adapter, CLI, MCP annotation, runtime, mutation-gate, write-design, surface-contract, and redacted-log coverage for the approved apply surface.

### Security

- `reminders_apply_change` is the only non-read-only MCP tool and is annotated non-destructive, idempotent, and closed-world.
- All non-Reminders mutation surfaces remain blocked by mutation gates.

## 0.1.0+codex.20260604090000 - 2026-06-04

### Added

- Preview-only Reminders planning through `local-apple-data reminders plan` and MCP `reminders_plan_change`.
- Deterministic `reminders-plan:v1:` idempotency keys plus approval fingerprints for future apply-token binding.
- Synthetic adapter, CLI, MCP, runtime, redacted-log, surface-contract, and packaging coverage for Reminders planning.

### Security

- Reminders planning returns `mutation_applied:false` and `apply_available:false`, does not call EventKit, and does not mutate Reminders.
- Apply-capable Reminders tools remain absent.

## 0.1.0+codex.20260604080000 - 2026-06-04

### Added

- Public Reminders write design gate for future create/complete/due-date operations through EventKit, with preview/apply/read_back contract language and explicit approval requirements.
- Write-design gate auditor that fails when required write design docs drift or preview/apply/read_back-style CLI/MCP tools appear before approval.
- Release-readiness, CI, staged-public-tree, cross-agent sync, and path-redacted release receipt coverage for the write-design gate.

### Security

- The current release remains read-only. The new Reminders write document is design-only and exposes no mutating CLI or MCP tools.

## 0.1.0+codex.20260604074000 - 2026-06-04

### Added

- Read-only local Apple data CLI and stdio MCP server.
- Codex plugin manifest, bundled skill, and MCP runner script.
- Metadata-first search plus exact opaque-handle detail/content flows for Mail, Messages, inferred Hide My Email aliases, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive.
- Exact Mail plain-text content, Notes plain-text content, Reminder notes, Calendar details, Contact details, Photos asset/resource metadata, Messages bounded transcripts, Voice Memos existing embedded transcripts, iCloud Drive text-file content, and inferred Hide My Email selected alias detail.
- Synthetic unit, CLI, MCP, runtime, packaging, and redaction tests.
- macOS GitHub Actions workflow with tests, compile, Swift helper typechecks, runtime smoke, and redaction scan.
- Public capability matrix, mutation gates, publishing checklist, install guide, sample outputs, macOS support notes, security policy, and MIT license.
- Notes content pagination for long imported notes through `offset`, `content_total_chars`, and `next_offset`.
- Public release scan for local-path/operator-term leakage in publishable files.
- Release-readiness audit for required files, version/changelog consistency, public scan status, sanitized git-checkout prep, and git remote presence.
- Public release tree builder for staging the sanitized publishable file set outside the working repo.
- Public git-checkout preparer for creating a sanitized local GitHub-ready checkout without pushing, including optional initial local commit creation.
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw configuration, including compact server-object output for CLI registration commands.
- Optional Cursor MCP config verification in the cross-agent sync verifier, with explicit `--require-cursor` and `--cursor-config` controls.
- Exact-handle Photos asset export and Voice Memos `.m4a` export to caller-selected output directories without returning media bytes inline.
- Broad-surface health and doctor readiness covering Messages, Voice Memos, iCloud Drive, normalized per-surface summaries, and non-prompting access requirements in addition to Mail, Notes, and Reminders schema checks.
- Mutation-gate auditor that fails release readiness if write-like CLI/MCP surfaces appear before a mutation gate is intentionally approved.
- CI and staged-public-tree verification run the mutation-gate audit.
- Surface-contract auditor that fails release readiness if supported Apple data surfaces drift across MCP tools, CLI commands, health summaries, access requirements, and `docs/CAPABILITY_MATRIX.md`.
- CI and staged-public-tree verification run the surface-contract audit.
- Public contributor guide plus GitHub PR and issue templates that require synthetic fixtures, redaction checks, surface-contract checks, and explicit mutation-gate review for write-like changes.
- Path-redacted release receipt generator for reviewer handoff before a GitHub push or tag, with committed public checkout proof and CI coverage in source and staged public trees.
- Public ecosystem review comparing current Apple Notes, Messages, Voice Memos, iCloud Drive, and official Apple framework references against this plugin's broad-surface exact-handle architecture.

### Security

- The current release is read-only and local-only.
- Search is metadata-first; content/detail retrieval requires exact opaque handles returned by metadata tools.
- Runtime avoids Gmail API, IMAP, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, network mail services, telemetry, background indexing, and durable personal-content caches.

### Deferred

- Mutating tools.
- Attachments, broad content search, broad Messages text search, generated Voice Memos transcription, Contact notes/images, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API paths, and arbitrary binary/document extraction.

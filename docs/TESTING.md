# Testing

The test strategy is synthetic-first. Real local stores are used only for health/doctor schema checks and only when explicitly run as a local smoke.

For publication gates, use this file together with `docs/CAPABILITY_MATRIX.md`, `docs/MUTATION_GATES.md`, `docs/PUBLISHING.md`, `docs/INSTALL.md`, `docs/SAMPLE_OUTPUTS.md`, and `docs/MACOS_SUPPORT.md`.

## Test Layers

- Unit tests: adapter query policy, handle generation, handle tamper rejection, warning redaction, Mail path discovery, Mail content-availability hints, synthetic Mail content parsing/attachment export/create-draft plan/apply, synthetic Messages chat transcript retrieval, attachment export, and send-text plan/apply, synthetic Hide My Email alias inference, synthetic Voice Memos transcript extraction, synthetic Safari bookmark/Reading List plist search and exact URL detail, synthetic Shortcuts CLI metadata search, synthetic Books metadata and selected-book annotation retrieval, synthetic Podcasts show metadata, selected-show episode metadata, and selected-episode description retrieval, synthetic Apple Music track and playlist metadata, synthetic Apple TV item and playlist metadata, synthetic Notes content retrieval/pagination/attachment export/create/append-text plan/apply, synthetic Calendar and Reminders EventKit helper responses, synthetic Calendar create-event plan/apply, synthetic Contacts helper responses and create-contact plan/apply, synthetic Photos helper responses and import plan/apply, synthetic iCloud Drive file retrieval and create/append-text plan/apply, reminder due-window caps, and non-mutating Reminders plan previews.
- CLI tests: synthetic Mail/Messages/Hide My Email/Voice Memos/Safari/Shortcuts/Books/Podcasts/Music/TV/Notes/Calendar/Contacts/Photos/iCloud Drive/Reminders stores, CLI output, or mocked helpers with redacted logs.
- MCP tests: tool listing plus read-only and approved write annotations.
- Runtime smoke: `scripts/verify_runtime.py` exercises the current plugin root through the same MCP runner used by `.mcp.json`, plus synthetic exact-handle Mail content/attachment export, Messages transcript/attachment export/send-text plan/apply, Hide My Email, Voice Memos, Safari bookmark/Reading List URL detail, Shortcuts metadata, Books metadata/selected-book annotations, Podcasts metadata/selected-episode descriptions, Music track/playlist metadata, TV item/playlist metadata, Notes content/attachment export, Calendar, Contacts, Photos, Reminders, and iCloud Drive content/detail flows and synthetic apply flows for the approved write tools.
- Cross-agent sync smoke: `scripts/verify_cross_agent_sync.py` confirms Codex, Claude Code, and OpenClaw are all pointed at the same project runner and installed plugin version, and verifies Cursor `mcp.json` when a local-apple-data Cursor entry is present or `--require-cursor` is used. Public checkouts can pass `--skip-codex --skip-file-sync --skip-claude --skip-openclaw --skip-cursor` for a source-only smoke.
- Install consistency: compare source and installed-cache manifest, MCP config, skill, server, handle helper, doctor helper, and adapters.
- Privacy scans: `scripts/redaction_scan.py` fails on high-confidence secrets and literal iCloud/private-relay email aliases without printing matched values.
- Public release scan: `scripts/public_release_scan.py` fails when public files contain local operator paths, private note titles, or operator-specific terms outside explicit author metadata.
- Mutation-gate audit: `scripts/audit_mutation_gates.py` fails if write-like CLI/MCP surfaces appear without an intentional mutation gate, if approved write tools lack write annotations, or if unapproved MCP tools are not annotated read-only.
- Write-design gate audit: `scripts/audit_write_design_gates.py` fails if first-tranche write design docs are missing, required safeguards drift, or preview/apply/read_back tool names appear before approval.
- Surface-contract audit: `scripts/audit_surface_contract.py` fails if a supported Apple data surface is missing from the MCP tools, CLI parser, health summary, access requirements, or public capability matrix.

## Commands

Run from the plugin root:

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
swiftc -typecheck scripts/eventkit_helper.swift
swiftc -typecheck scripts/contacts_helper.swift
swiftc -typecheck scripts/photos_helper.swift
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_runtime.py
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py --cursor-config .cursor/mcp.json --require-cursor
```

Also run the plugin and skill validator scripts when those local validator helpers are installed in the current Codex skills cache.

After reinstalling, run the runtime verifier from the installed cache:

```bash
cd /absolute/path/to/installed/local-apple-data/<version>
uv run python scripts/verify_runtime.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
```

For a public source-only checkout without configured clients:

```bash
uv run python scripts/verify_cross_agent_sync.py --skip-codex --skip-file-sync --skip-claude --skip-openclaw --skip-cursor
```

## Current Acceptance Criteria

- Tests pass.
- Compile succeeds.
- Plugin and skill validators pass when the local validator helpers are installed.
- Runtime verifier prints JSON and exits zero.
- Empty Mail search returns `empty_query`.
- Wildcard-only Mail, Messages, Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Notes, Calendar, Contacts, Photos, iCloud Drive, SQLite Reminders, and EventKit Reminders searches return `broad_query`.
- Mail, Messages, Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive exact-get accept opaque handles from search output.
- Mail, Messages, Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive exact-get reject legacy raw row-ID, raw framework identifier, raw alias identifier, recording identifier, Shortcuts identifier, raw Books asset IDs, raw Books annotation UUIDs, raw Podcasts identifiers, raw Music identifiers, raw TV identifiers, or direct-path handles with `invalid_handle`.
- Mail search returns a metadata-only `content_status` hint without reading message bodies.
- Mail and Notes metadata handles use the `v2` fully opaque HMAC format.
- Mail content accepts only `mail:message:v2:` handles, returns bounded plain text, and rejects raw IDs, old handles, mailbox refs, and paths.
- Mail content truncation returns `content_truncated`.
- Mail attachment listing accepts only exact `mail:message:v2:` handles, returns bounded metadata with `mail:attachment:v1:` handles, and rejects raw message IDs.
- Mail attachment export requires both the selected message handle and exact `mail:attachment:v1:` handle, writes to a caller-selected output directory, reports externalized/partial attachments as unavailable, never returns inline bytes, and does not log source message paths.
- Mail planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, at least one To recipient, and a bounded subject.
- Mail apply requires a matching approval token, explicit confirmation, save-only Mail.app automation, and local Drafts read-back when available.
- Messages get accepts only `messages:chat:v1:` handles, returns bounded chat transcript text, rejects raw row IDs and fabricated handles, and does not return participant identifiers.
- Messages transcript truncation returns `content_truncated`.
- Messages attachment listing accepts only exact `messages:chat:v1:` handles, returns bounded metadata with `messages:attachment:v1:` handles, and rejects raw chat IDs.
- Messages attachment export requires both the selected chat handle and exact `messages:attachment:v1:` handle, writes to a caller-selected output directory, reports missing local media as unavailable, never returns inline bytes, and does not log source media paths.
- Messages planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, bounded body preview, and requires exact opaque chat handles.
- Messages apply requires a matching approval token, explicit confirmation, stale chat-state refusal, Messages.app automation, ghost-row detection, local `chat.db` read-back verification, and does not echo the sent body in apply output.
- Hide My Email search rejects domain-only and generic queries, returns masked alias previews only, includes `authoritative_inventory:false`, and never returns full aliases during search.
- Hide My Email get accepts only `hide_my_email:alias:v1:` handles, returns exact selected alias detail, rejects raw identifiers and fabricated handles, and reports local Mail metadata provenance.
- Voice Memos get accepts only `voice_memos:recording:v1:` handles, returns bounded existing embedded transcript text when available, rejects raw recording IDs and fabricated handles, and does not return audio bytes, raw paths, or recording identifiers.
- Voice Memos transcript truncation returns `content_truncated`.
- Safari search rejects empty and broad queries, returns title/domain metadata without full URLs, and uses opaque `safari:item:v1:` handles.
- Safari get accepts only `safari:item:v1:` handles, returns the selected full URL only by exact handle, and rejects raw identifiers and fabricated handles.
- Shortcuts search rejects empty and broad queries, returns shortcut/folder name metadata without raw identifiers or shortcut bodies, and uses opaque `shortcuts:item:v1:` handles.
- Shortcuts get accepts only `shortcuts:item:v1:` handles, returns selected metadata only, and rejects raw identifiers and fabricated handles.
- Books search rejects empty and broad queries, returns title/author/genre/read-state metadata and annotation counts without annotation text, book text, raw identifiers, or local paths, and uses opaque `books:book:v1:` handles.
- Books get accepts only `books:book:v1:` handles, returns selected metadata only, and rejects raw identifiers and fabricated handles.
- Books annotations accepts only exact `books:book:v1:` handles, returns bounded selected-book annotations with truncation metadata, and rejects broad annotation search/dumps, raw asset IDs, raw annotation UUIDs, and fabricated handles.
- Podcasts search rejects empty and broad queries, returns show title/author/category/provider metadata without episode descriptions, transcripts, audio bytes, URLs, raw identifiers, or local paths, and uses opaque `podcasts:show:v1:` handles.
- Podcasts get accepts only `podcasts:show:v1:` handles, returns selected show metadata only, and rejects raw identifiers and fabricated handles.
- Podcasts episodes accepts only exact `podcasts:show:v1:` handles, returns bounded selected-show episode metadata without descriptions or transcript text, and returns opaque `podcasts:episode:v1:` handles.
- Podcasts episode accepts only exact `podcasts:episode:v1:` handles, returns bounded selected-episode descriptions with truncation metadata, and rejects raw identifiers and fabricated handles.
- Music search rejects empty and broad queries, returns track title/artist/album/album-artist/genre/duration metadata without audio bytes, lyrics, file paths, raw identifiers, play history, ratings, or favorites, and uses opaque `music:track:v1:` handles.
- Music get accepts only `music:track:v1:` handles, returns selected track metadata only, and rejects raw identifiers and fabricated handles.
- Music playlists rejects empty and broad queries, returns playlist title/kind/count/duration metadata without playlist track dumps or raw identifiers, and uses opaque `music:playlist:v1:` handles.
- Music playlist accepts only `music:playlist:v1:` handles, returns selected playlist metadata only, and rejects raw identifiers and fabricated handles.
- TV search rejects empty and broad queries, returns item title/show/artist/genre/video-kind/duration/season/episode/year metadata without video bytes, file paths, artwork, descriptions, raw identifiers, playback state, watched state, ratings, or favorites, and uses opaque `tv:item:v1:` handles.
- TV get accepts only `tv:item:v1:` handles, returns selected item metadata only, and rejects raw identifiers and fabricated handles.
- TV playlists rejects empty and broad queries, returns playlist title/kind/count/duration metadata without playlist item dumps or raw identifiers, and uses opaque `tv:playlist:v1:` handles.
- TV playlist accepts only `tv:playlist:v1:` handles, returns selected playlist metadata only, and rejects raw identifiers and fabricated handles.
- Notes content accepts only `notes:note:v2:` handles, returns bounded plain text, and rejects raw IDs, old handles, direct database IDs, and fabricated handles.
- Notes content truncation returns `content_truncated`, `content_total_chars`, and `next_offset` so long imported notes can be retrieved in bounded chunks.
- Notes content automation failures return safe warning codes without raw AppleScript errors or database paths.
- Notes attachment listing accepts only exact `notes:note:v2:` handles, returns bounded metadata with `notes:attachment:v1:` handles, and rejects raw note IDs.
- Notes attachment export accepts only exact `notes:attachment:v1:` handles, writes to a caller-selected output directory, prefers local media files, falls back to local BLOB data, reports remote-only attachments as unavailable, never returns inline bytes, and does not log source media paths.
- iCloud Drive content accepts only `icloud:file:v1:` handles, returns bounded text for supported text-like files, and rejects direct paths, fabricated handles, symlinks, hidden files, and unsupported binary/document types.
- iCloud Drive content truncation returns `content_truncated`.
- iCloud Drive planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and requires exact opaque parent folder handles.
- iCloud Drive apply requires a matching approval token, explicit confirmation, exact parent folder handle, exclusive create, and read-back verification.
- Calendar get accepts only `calendar:event:v1:` handles, returns bounded exact event location/notes details, and rejects raw EventKit identifiers and fabricated handles.
- Calendar notes truncation returns `content_truncated`.
- Calendar planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and requires explicit calendar title plus ISO 8601 start/end timestamps.
- Calendar apply requires a matching approval token, explicit confirmation, EventKit helper apply, and read-back verification.
- Contacts get accepts only `contacts:contact:v1:` handles, returns exact contact detail fields, rejects raw Contacts identifiers and fabricated handles, and reports contact notes as `requires_entitlement`.
- Contacts planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and requires a person name or organization name.
- Contacts apply requires a matching approval token, explicit confirmation, Contacts.framework helper apply, and read-back verification.
- Notes planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and requires a bounded title.
- Notes apply requires a matching approval token, explicit confirmation, Notes.app automation, and exact-content read-back verification.
- Photos get/export accepts only `photos:asset:v1:` handles, returns exact asset/resource or destination metadata, rejects raw Photos identifiers and fabricated handles, and never returns inline asset bytes.
- Photos planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, source filename/media type/size/hash, and does not echo the raw source path.
- Photos apply requires a matching approval token, explicit confirmation, source-file hash binding, PhotoKit helper apply, and created-asset read-back verification.
- Reminders content accepts only `reminders:reminder:eventkit:v1:` handles, returns bounded exact reminder notes, and rejects raw EventKit identifiers, legacy SQLite reminder handles, and fabricated handles.
- Reminder notes truncation returns `content_truncated`.
- Reminders planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and requires exact EventKit reminder handles for existing-reminder operations.
- Reminders apply requires a matching approval token, explicit confirmation, expected state, EventKit helper apply, and read-back verification.
- Health and doctor do not expose full local executable paths.
- Health and doctor report broad local Apple data readiness without content reads, raw rows, credentials, prompt-triggering framework access, or raw absolute store paths.
- Health covers schema-only Mail, Messages, Voice Memos, Books, Podcasts, Notes, and Reminders checks plus Safari bookmarks, Shortcuts CLI availability, Music.app/TV.app osascript readiness, and iCloud Drive root readiness, a normalized per-surface summary, and non-prompting access requirements for Calendar, Contacts, Photos, Reminders, Notes automation, Messages automation, Music/TV automation-on-exact-call, and other framework-backed surfaces.
- Write-design gates require the Reminders, iCloud Drive, Calendar, Contacts, Notes create/append, Mail draft, Photos import, and Messages send-text write design contracts and allow only `reminders apply` / `reminders_apply_change`, `icloud-drive apply` / `icloud_drive_apply_change`, `calendar apply` / `calendar_apply_change`, `contacts apply` / `contacts_apply_change`, `notes apply` / `notes_apply_change`, `mail apply` / `mail_apply_change`, `photos apply` / `photos_apply_change`, and `messages apply` / `messages_apply_change` as approved write tools.
- No repo docs or tests persist real personal search terms or result metadata.

## v1.1 Acceptance Criteria

The v1.1 Mail content phase uses synthetic-only tests before any runtime install:

- Exact `mail_get_content` succeeds from a synthetic opaque `mail:message:v2:` handle.
- Invalid raw IDs, old handles, mailbox refs, and paths fail closed.
- Deleted messages do not return content.
- Content is bounded by `max_chars` and reports truncation.
- Logs do not contain handles, subjects, content, warning messages, raw paths, or raw exceptions.
- Runtime verification covers synthetic content success and invalid-handle rejection without touching real message bodies.

## v1.2 Acceptance Criteria

The v1.2 Notes content phase keeps the same synthetic-first test posture:

- Exact `notes_get_content` succeeds from a synthetic opaque `notes:note:v2:` handle.
- Invalid raw IDs, old handles, direct database IDs, and fabricated handles fail closed.
- Deleted and password-protected notes do not return content.
- Content is read through bounded local Notes automation, converted from HTML to plain text, capped by `max_chars`, supports zero-based `offset`, and reports `next_offset` for long notes.
- Exact Notes content returns `content_sha256` over normalized plaintext.
- Logs do not contain handles, titles, snippets, content, warning messages, raw paths, raw database rows, or raw automation errors.
- Runtime verification covers synthetic content success and invalid-handle rejection without touching real note bodies.
- Optional live smoke may be run only for a user-requested exact note and must report status/count/truncation only unless the user explicitly asks to view the content.

## v1.3 Acceptance Criteria

The v1.3 iCloud Drive content phase keeps the same synthetic-first test posture:

- Exact `icloud_drive_get_content` succeeds from a synthetic opaque `icloud:file:v1:` handle.
- Invalid direct paths, fabricated handles, hidden files, symlinks, and unsupported file types fail closed.
- Empty and wildcard-only filename searches fail before scanning.
- File search returns filenames and bounded metadata without raw local paths.
- Content is capped by `max_chars` and reports truncation.
- Logs do not contain handles, filenames, content, warning messages, raw paths, or raw exceptions.
- Runtime verification covers synthetic content success and invalid-handle rejection without touching real iCloud Drive file content.

## v1.4 Acceptance Criteria

The v1.4 Calendar EventKit phase keeps the same synthetic-first test posture:

- Exact `calendar_get_event` succeeds from a synthetic opaque `calendar:event:v1:` handle.
- Invalid raw EventKit identifiers and fabricated handles fail closed.
- Empty and wildcard-only title searches fail before EventKit access.
- Search output returns event metadata without event identifiers, notes, locations, attendee identities, or URLs.
- Exact event details return bounded notes/location text and report truncation.
- EventKit helper access is non-prompting; unavailable permission returns `calendar_access_unavailable`.
- Runtime verification covers synthetic content success and invalid-handle rejection without touching real Calendar content.

## v1.5 Acceptance Criteria

The v1.5 Reminders EventKit phase keeps the same synthetic-first test posture:

- Exact `reminders_get_content` succeeds from a synthetic opaque `reminders:reminder:eventkit:v1:` handle.
- Invalid raw EventKit identifiers, legacy SQLite reminder handles, and fabricated handles fail closed.
- Empty and wildcard-only title searches fail before EventKit access.
- Search output returns reminder metadata without EventKit identifiers or notes.
- Exact reminder details return bounded notes text and report truncation.
- EventKit helper access is non-prompting; unavailable permission returns `reminders_access_unavailable`.
- Runtime verification covers synthetic content success and invalid-handle rejection without touching real Reminder content.

## v1.6 Acceptance Criteria

The v1.6 Contacts.framework phase keeps the same synthetic-first test posture:

- Exact `contacts_get` succeeds from a synthetic opaque `contacts:contact:v1:` handle.
- Invalid raw Contacts identifiers and fabricated handles fail closed.
- Empty and wildcard-only name/organization searches fail before Contacts.framework access.
- Search output returns contact metadata without Contacts identifiers, email addresses, phone numbers, postal addresses, notes, or image bytes.
- Exact contact details return bounded email, phone, postal address, URL, date, relation, social profile, and instant-message fields.
- Contact notes are not fetched and report `requires_entitlement`.
- Contacts helper access is non-prompting; unavailable permission returns `contacts_access_unavailable`.
- Runtime verification covers synthetic detail success and invalid-handle rejection without touching real Contacts content.

## v1.7 Acceptance Criteria

The v1.7 PhotoKit phase keeps the same synthetic-first test posture:

- Exact `photos_get_asset` succeeds from a synthetic opaque `photos:asset:v1:` handle.
- Invalid raw Photos identifiers and fabricated handles fail closed.
- Empty and wildcard-only filename searches fail before PhotoKit access.
- Search output returns Photos metadata without Photos identifiers or resource arrays.
- Exact asset detail returns resource filenames, resource types, and uniform type identifiers only.
- Exact asset export writes one selected asset resource to a caller-selected output directory and returns export metadata without inline image/video bytes.
- Photos import planning returns preview-only approval metadata and refuses missing, unsupported, symlink, directory, empty, oversized, and mismatched source files without calling PhotoKit.
- Photos import apply requires the matching approval token, explicit confirmation, source-file hash binding, and created-asset read-back through the mocked PhotoKit helper.
- No thumbnails, raw Photos identifiers, broad dumps, network iCloud fetches, edit, delete, album targeting, metadata mutation, or bulk Photos operations are returned.
- PhotoKit helper access is non-prompting; unavailable permission returns `photos_access_unavailable`.
- Runtime verification covers synthetic asset detail/export, synthetic import plan/apply success, missing confirmation, and invalid-handle rejection without touching real Photos content.

## v1.8 Acceptance Criteria

The v1.8 Messages phase keeps the same synthetic-first test posture:

- Exact `messages_get_chat` succeeds from a synthetic opaque `messages:chat:v1:` handle.
- Exact `messages_get_chat` decodes a synthetic modern `attributedBody` row when `message.text` is empty and reports `text_source:"attributed_body"`.
- A malformed attributed-body blob returns a stable warning while preserving normal text rows and individually decodable fallback rows.
- Invalid raw row IDs, raw chat GUIDs, and fabricated handles fail closed.
- Empty and wildcard-only chat display-name searches fail before opening `chat.db`.
- Search output returns chat metadata without message text, phone numbers, email addresses, chat GUIDs, raw row IDs, or participant identifiers.
- Exact chat transcript returns bounded message text, text source, direction, date, and service only.
- Transcript text is capped by `max_messages` and `max_chars`, and truncation reports `content_truncated`.
- Broad attachment export, inline attachment bytes, source media paths, raw attributed-body blobs, attributed-string attributes, tapbacks/reactions, send-state metadata, broad message-text search, and mutation are out of scope.
- Runtime verification covers synthetic transcript success, attributed-body plaintext fallback, attachment list/export success, and invalid-handle rejection without touching real Messages content.

## v1.9 Acceptance Criteria

The v1.9 Voice Memos phase keeps the same synthetic-first test posture:

- Exact `voice_memos_get_recording` succeeds from a synthetic opaque `voice_memos:recording:v1:` handle.
- Invalid raw recording IDs and fabricated handles fail closed.
- Empty and wildcard-only title/filename searches fail before opening `CloudRecordings.db`.
- Search output returns Voice Memo metadata without transcript text, audio bytes, raw local paths, raw recording identifiers, or filenames.
- Exact recording retrieval returns bounded existing embedded transcript text, title, recorded date, duration, and audio availability only.
- Exact audio export copies one selected `.m4a` to a caller-selected output directory and returns export metadata without inline audio bytes or source paths.
- Transcript text is capped by `max_chars`, and truncation reports `content_truncated`.
- Generated transcription, broad transcript search, and mutation are out of scope.
- Runtime verification covers synthetic transcript/export success and invalid-handle rejection without touching real Voice Memos content.

## v1.10 Acceptance Criteria

The v1.10 Hide My Email phase keeps the same synthetic-first test posture:

- Exact `hide_my_email_get_alias` succeeds from a synthetic opaque `hide_my_email:alias:v1:` handle.
- Invalid raw alias identifiers and fabricated handles fail closed.
- Empty, wildcard-only, domain-only, and generic Hide My Email queries fail before opening the Mail store.
- Search output returns masked alias previews, domain, inference kind, confidence, count metadata, provenance, and `authoritative_inventory:false` without returning full aliases.
- Exact alias retrieval returns the selected full alias only after the opaque handle is provided.
- Private relay aliases are identified as high-confidence Sign in with Apple private relay evidence; iCloud-style aliases are medium-confidence local Mail evidence.
- Authoritative iCloud inventory, alias creation/deactivation/deletion, private iCloud web/API access, browser sessions, keychain credential access, broad Mail address dumps, and mutation are out of scope.
- Runtime verification covers synthetic alias success and invalid-handle rejection without touching real Mail address rows.

## v1.11 Acceptance Criteria

The v1.11 Reminders phase exposes planning plus one approved apply surface:

- `reminders plan` and `reminders_plan_change` return `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Create planning requires title and target list name.
- Existing-reminder planning requires an exact opaque `reminders:reminder:eventkit:v1:` handle.
- Due-date planning accepts `YYYY-MM-DD` or timezone-aware ISO 8601 and rejects naive timestamps.
- Planning returns a deterministic `reminders-plan:v1:` idempotency key and approval fingerprint.
- `reminders apply` and `reminders_apply_change` require the matching `reminders-apply:v1:<approval_fingerprint>` token and explicit confirmation.
- Existing-reminder apply resolves exact opaque handles internally and checks expected state before calling EventKit.
- Apply returns `mode: "apply"`, `mutation_applied:true`, and read-back metadata only after EventKit save succeeds.
- Logs do not contain planned titles, notes, list names, handles, or approval fingerprints.
- Runtime verification covers synthetic planning and mocked apply without touching live Reminders.
- MCP annotation tests prove `reminders_apply_change` is non-read-only while other tools remain read-only.

## v1.19 Acceptance Criteria

The v1.19 Notes append phase expands the existing Notes apply surface without adding new write tool names:

- `notes plan --operation append-text` and `notes_plan_change(operation="append_text")` return `mode: "plan"`, `mutation_applied:false`, and `apply_available:true`.
- Append planning requires an exact opaque `notes:note:v2:` handle, expected current SHA-256 from exact content retrieval, and non-empty bounded plaintext.
- `notes apply --operation append-text` and `notes_apply_change(operation="append_text")` require the matching `notes-apply:v1:<approval_fingerprint>` token and explicit confirmation.
- Apply refuses stale hashes with `current_content_changed`, refuses shared-note mutation, appends only escaped bounded plaintext through Notes.app body HTML, and verifies exact-content read-back plus `content_sha256`.
- Logs do not contain planned titles, note content, handles, content hashes, raw Notes IDs, raw paths, approval fingerprints, or approval tokens.
- Runtime verification covers synthetic append planning, mocked append apply, and stale-hash refusal without touching live Notes content.

## v1.20 Notes Attachment Export Acceptance Criteria

The v1.20 Notes attachment phase adds read/export-only exact attachment access:

- `notes attachments` / `notes_list_attachments` require an exact `notes:note:v2:` handle and return opaque `notes:attachment:v1:` handles.
- `notes export-attachment` / `notes_export_attachment` require an exact attachment handle and a caller-selected output directory.
- Media-file export, BLOB fallback, invalid-handle refusal, and remote-only unavailable warnings are covered with synthetic fixtures.
- Runtime verification covers attachment list/export success and legacy attachment handle refusal without touching live Notes attachments.
- Redacted logs do not contain attachment handles, note handles, filenames, warning messages, source media paths, or export paths.

## v1.21 Mail Attachment Export Acceptance Criteria

The v1.21 Mail attachment phase adds read/export-only exact attachment access:

- `mail attachments` / `mail_list_attachments` require an exact `mail:message:v2:` handle and return opaque `mail:attachment:v1:` handles.
- `mail export-attachment` / `mail_export_attachment` require both the original message handle, the selected attachment handle, and a caller-selected output directory.
- MIME-contained attachment bytes are copied to the output directory with sanitized filenames; externalized or partial-message attachments with missing bytes return `mail_attachment_unavailable`.
- Runtime verification covers Mail attachment list/export success and legacy message-handle refusal without touching live Mail attachments.
- Redacted logs do not contain attachment handles, message handles, filenames, warning messages, source message paths, or export paths.

## v1.22 Messages Attachment Export Acceptance Criteria

The v1.22 Messages attachment phase adds read/export-only exact attachment access:

- `messages attachments` / `messages_list_attachments` require an exact `messages:chat:v1:` handle and return opaque `messages:attachment:v1:` handles.
- `messages export-attachment` / `messages_export_attachment` require both the original chat handle, the selected attachment handle, and a caller-selected output directory.
- Local attachment bytes are copied to the output directory with sanitized filenames; missing local media returns `messages_attachment_unavailable`.
- Runtime verification covers Messages attachment list/export success and legacy attachment-handle refusal without touching live Messages attachments.
- Redacted logs do not contain attachment handles, chat handles, filenames, warning messages, source media paths, or export paths.

## v1.24 Messages Send-Text Acceptance Criteria

The v1.24 Messages send-text phase adds one approved apply surface:

- `messages plan` / `messages_plan_change` require an exact `messages:chat:v1:` handle and non-empty bounded plaintext body.
- Planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, a deterministic `messages-plan:v1:` idempotency key, bounded body preview, current chat-state metadata, and an approval fingerprint.
- `messages apply` / `messages_apply_change` require the matching `messages-apply:v1:<approval_fingerprint>` token, explicit confirmation, the same exact chat handle, and the same body text.
- Apply recomputes the plan before sending so changed body text or changed chat state refuses through approval-token mismatch.
- Apply uses a mocked script runner in tests and verifies local `chat.db` read-back for a newer outgoing row joined to the selected chat with matching body hash.
- Apply output includes read-back metadata and body SHA-256, but not the sent body text.
- Ghost-row detection returns a non-success warning when automation creates an empty unjoined outgoing row.
- Runtime verification covers synthetic Messages plan/apply success and missing-confirmation refusal without touching live Messages.
- Redacted logs do not contain body text, body previews, body hashes, chat handles, chat GUIDs, participant identifiers, approval fingerprints, approval tokens, raw AppleScript errors, warning messages, source media paths, or local database paths.

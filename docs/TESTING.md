# Testing

The test strategy is synthetic-first. Real local stores are used only for health/doctor schema checks and only when explicitly run as a local smoke.

For publication gates, use this file together with `docs/CAPABILITY_MATRIX.md`, `docs/MUTATION_GATES.md`, `docs/PUBLISHING.md`, `docs/INSTALL.md`, `docs/SAMPLE_OUTPUTS.md`, and `docs/MACOS_SUPPORT.md`.

## Test Layers

- Unit tests: adapter query policy, handle generation, handle tamper rejection, warning redaction, Mail path discovery, Mail content-availability hints, exact selected-mailbox Mail message metadata date-bound guards and metadata-only output, synthetic Mail content parsing/attachment export/create-draft with sender selection and local file attachments plus send/reply/reply-all/forward local file attachment plan/apply/read-back, capped exact Mail bulk triage planning/apply/preflight/partial reporting, Mail signature/template/query-result triage planning, synthetic Mail `LAD-TEST-*` mailbox management and synthetic-only cleanup planning/apply/read-back/absence proof, Mail attachment stale-content and symlink-export hardening, opt-in Mail FTS build/search over synthetic body/header/attachment content with confirmation/date-bound guards, hidden cache paths, redacted snippets, read-only search, live-row/date/content-state revalidation, stale-content skip, build and search cursor pagination, symlink/non-regular index-path refusal, secure drop/vacuum reset, schema-init connection cleanup, paginated scope filtering, and separated attachment count/filename/MIME metadata, synthetic Messages chat transcript retrieval, attachment export, and send-text plan/apply, synthetic Hide My Email alias inference, synthetic Voice Memos transcript extraction, synthetic Safari bookmark/Reading List plist search, exact URL detail, folder search/detail, and exact selected-folder direct child metadata listing, synthetic Shortcuts CLI metadata search, exact get, and exact selected-folder shortcut listing, synthetic Books metadata and selected-book annotation retrieval, synthetic Podcasts show metadata, selected-show episode metadata, and selected-episode description retrieval, synthetic Apple Music track and playlist metadata, synthetic Apple TV item, playlist, and selected-playlist item metadata, synthetic Apple Freeform board/folder/selected-folder board/child-folder metadata, synthetic Notes content retrieval/pagination/folder metadata/folder-targeted note create/exact child-folder create/attachment export/create/append-text/replace-text/delete plan/apply including parent-folder proof, metadata-only read-back, idempotent existing-child handling, wrong returned folder-id refusal, and wrong-parent partial read-back, synthetic Calendar and Reminders EventKit helper responses, synthetic Calendar participant list/detail exact handles with metadata-only list redaction, synthetic Calendar timed/all-day/relative-or-absolute-alarm/time-zone/availability/target-calendar/default-calendar/simple recurrence/exact allow-listed event URL create/update/delete plan/apply plus update-only event URL clearing/structured-location create/update/delete plan/apply plus structured event location, selected recurring occurrence title/plain-location/notes/timed reschedule update, selected/future/whole-series recurring-event delete, and structured-location, Reminder URL update/clear plan/apply with hash-only read-back and no raw URL return, Reminder absolute/relative/mixed display-alarm set/clear plan/apply with exact date/offset read-back or absence proof and no raw alarm state return, strict Calendar boolean, relative-or-absolute alarm, time-zone, availability, and event URL validation including path-like time-zone refusal, event URL raw-preview non-disclosure, invalid-token raw-URL non-disclosure, availability expected-state binding, support-mask Swift source assertions, availability read-back mismatch partial reporting, event URL hash-only read-back mismatch and URL-clear absence-proof partial reporting, Calendar search metadata alarm, time-zone, availability, and recurrence non-disclosure, exact target-calendar read-back verification, duplicate source-calendar title ambiguity refusal, and Swift expected-state-before-already-applied ordering proof, synthetic Contacts helper responses and create-contact/exact name-organization-method update/delete plan/apply, synthetic Photos helper responses, exact selected-album asset listing, and import plan/apply, synthetic iCloud Drive file retrieval and create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file plan/apply including folder directory metadata read-back, exact file export source-identity race refusal, exact folder Trash absence proof, exact selected-folder permanent delete original absence proof, exact folder move source/target proof, non-empty child preservation, exact folder copy bounded private tree source-preservation and target proof with non-empty child preservation, no content-hash return, already-applied retry, stale-content refusal, no-overwrite rename/copy/move, rename/move post-swap race rollback, folder Trash/delete non-empty-race rollback, folder rename/move apply-time read-back mismatch partial reporting, folder delete rollback-failure partial reporting without false permanent-delete proof, folder copy source-race partial reporting without unsafe cleanup, folder copy target-identity race partial reporting, copy post-write source recheck cleanup, hidden-root CLI refusal, source/target presence proof, text-file target hash read-back without content text, regular-file metadata-only read-back with `content_text_returned:false` and `content_hash_returned:false`, regular-file recoverable Trash original absence proof without raw Trash path or content hash return, regular-file post-swap metadata race refusal, regular-file target-byte mismatch partial proof without returned hash, create symlink refusal, append existing-byte preservation, append/replace concurrent-drift refusal, read-back mismatch handling, and same-directory temp cleanup, reminder due-window caps, and non-mutating Reminders plan previews.
- Focused mutation tests also cover exact identifier-bound Shortcuts run plan/apply (approval fingerprint, argv-only invocation, timeout, and invocation-only proof), bounded home-directory Filesystem reuse of the iCloud Drive gates, Notes rich-text body create/replace, and exact empty child-folder move.
- CLI tests: synthetic Mail/Messages/Hide My Email/Voice Memos/Safari/Shortcuts/Books/Podcasts/Music/TV/Freeform/Notes/Calendar/Contacts/Photos/iCloud Drive/Reminders stores, CLI output, or mocked helpers with redacted logs.
- MCP tests: tool listing plus read-only and approved write annotations.
- Runtime smoke: `scripts/verify_runtime.py` exercises the current plugin root through the same MCP runner used by `.mcp.json`, plus synthetic exact-handle Mail content/selected-mailbox message metadata/attachment export/create-draft with optional sender selection and local file attachments/send-message/reply/reply-all/forward local file attachments/read/flag/archive/move/trash plan/apply, capped exact Mail bulk triage over mixed applied/already-satisfied handles, Mail signature/template/query-result triage planning, synthetic Mail `LAD-TEST-*` mailbox create/rename and synthetic-only cleanup apply, opt-in Mail FTS build/search with private cache path hidden, read-only search output, and live-row/date/content-state revalidation, Messages transcript/attachment export/send-text plan/apply, Hide My Email, Voice Memos, Safari bookmark/Reading List URL detail plus exact folder metadata/direct-child listing without full URLs, Shortcuts metadata/selected-folder shortcut metadata, Books metadata/selected-book annotations, Podcasts metadata/selected-episode descriptions, Music track/playlist/selected-playlist track metadata, TV item/playlist/selected-playlist item metadata, Freeform board/folder/selected-folder board/child-folder metadata, Notes content/folder metadata/folder-targeted note create/exact child-folder create/attachment export/append-text/replace-text/move-to-folder/delete, Calendar timed/all-day/relative-or-absolute-alarm/time-zone/availability/target-calendar/default-calendar plan-only exact-handle resolution/simple recurrence/exact allow-listed event URL/structured-location search/detail/create/update/move/delete plus selected recurring occurrence title/plain-location/notes/timed reschedule update, selected/future/whole-series recurring-event delete, and structured-location, Contacts selected-group and selected-container member metadata plus create/exact name-organization-method update/delete, Photos exact asset, exact regular-album, exact selected-album asset listing, and approved Photos apply flows, Reminders, and iCloud Drive content/detail plus create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file apply flows, including Calendar target-calendar handle read-back verification, default-calendar resolution verification, availability read-back verification, event URL hash-only read-back verification without raw URL return, selected-occurrence update read-back plus adjacent-occurrence preservation proof, Notes child-folder parent proof with no content returned, folder directory metadata read-back, no folder content-hash return, already-applied retry, exact-hash success, stale-content no-mutation proof for iCloud Drive text updates, exact folder rename source/target presence proof with non-empty child preservation, `non_empty_allowed:true`, and no content hash return, exact folder Trash original absence proof with non-empty support and no content hash or raw Trash path return, exact selected-folder permanent delete original absence proof with `empty_folder_confirmed:false` for non-empty proof, `non_empty_allowed:true`, `verified_absent:true`, `permanently_deleted:true`, and no content hash, raw Trash path, or staging path return, exact folder move source/target presence proof with non-empty child preservation, `non_empty_allowed:true`, descendant-parent refusal, and no content hash return, exact folder copy source-preservation and target-presence proof with bounded non-empty child preservation, `non_empty_allowed:true`, `empty_folder_confirmed:false` for non-empty proof, and no content hash or child listing return, trash-text original-handle absence proof without returning raw Trash paths, text-file rename/copy/move source/target presence proof plus target hash read-back without content text, regular-file rename/copy/move metadata-only source/target presence proof without returned content hash, and regular-file Trash original absence proof without raw Trash path, content hash, or inline content return. It also starts the MCP server with a synthetic `LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT` and verifies successful `icloud_drive_plan_change` / `icloud_drive_apply_change` create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file plan/apply through MCP without touching real iCloud Drive contents, plus Calendar target-calendar, time-zone, absolute-alarm, availability, recurrence, recurrence-update, event URL, selected-occurrence update, and selected/future/whole-series recurring-delete plan/apply parameter binding through MCP without reaching live EventKit mutation.
- Runtime verification also exercises the installed/public Filesystem and exact Shortcuts plan/apply tool surface synthetically; it does not infer or verify arbitrary Shortcut side effects.
- Cross-agent sync smoke: `scripts/verify_cross_agent_sync.py` confirms Codex, Claude Code, and OpenClaw are all pointed at the same project runner and installed plugin version, verifies Cursor `mcp.json` when a local-apple-data Cursor entry is present or `--require-cursor` is used, and degrades when direct live `python -m local_apple_data.mcp_server`-style server processes are still running from an older installed Codex cache version, cannot be classified to the current source/personal/current-cache roots, or cannot be enumerated. The live-process detector uses token-level module detection so shell/audit commands that only contain the module string are not counted as live servers, and it classifies pathless Codex app-server `uv run --no-project` children by process CWD when the command line omits a plugin path. Public checkouts can pass `--skip-codex --skip-file-sync --skip-claude --skip-openclaw --skip-cursor --skip-live-processes` for a source-only smoke.
- GUI-client smoke: use the actual desktop client, call only `apple_data_health`, and verify both connection and per-app macOS permission readiness. A connected GUI client can still return degraded health when that app lacks Full Disk Access, Automation, Calendar, Reminders, Contacts, or Photos permission.
- Install consistency: `scripts/verify_cross_agent_sync.py` compares the source checkout, personal plugin root, and installed cache across static release/runtime files including `.gitignore`, `pyproject.toml`, and `uv.lock`, plus `.codex-plugin`, `.github`, docs, scripts, skills, `src/local_apple_data`, and tests; it also verifies Codex, Claude Code, Cursor when configured, OpenClaw routing, and live MCP process freshness.
- Privacy scans: `scripts/redaction_scan.py` fails on high-confidence secrets and literal iCloud/private-relay email aliases without printing matched values; use `--json` for machine-readable findings that still omit matched values.
- Public release scan: `scripts/public_release_scan.py` fails when public files contain local operator paths, private note titles, operator-specific terms outside explicit author metadata, or references back to excluded operator-only docs; local env files and key/certificate-like artifacts are excluded from the public file set. Pass an explicit root to scan a staged public tree, and use `--json` for machine-readable findings that do not include matched text.
- Messages public-surface audit: `scripts/audit_messages_public_surface.py` parses the public Messages scripting definition and fails if unreviewed public commands, send-signature drift, non-read-only elements, or unreviewed writable properties appear before a separate Messages risky-mutation design gate is approved.
- Release-readiness audit: `scripts/audit_release_readiness.py` fails local package readiness for git checkouts with uncommitted source changes, redaction findings, public-release leakage, mutation/write-design/surface drift, Messages public-surface drift, or public checkout failures, and reports missing, unavailable, timed-out, non-GitHub, or non-plain remotes separately from local package health.
- Mutation-gate audit: `scripts/audit_mutation_gates.py` fails if write-like CLI/MCP surfaces appear without an intentional mutation gate, if approved write tools lack write annotations, or if unapproved MCP tools are not annotated read-only.
- Write-design gate audit: `scripts/audit_write_design_gates.py` fails if first-tranche write design docs are missing, required safeguards drift, installed skill create-folder wording drifts, required source/runtime proof text disappears, or preview/apply/read_back tool names appear before approval.
- Surface-contract audit: `scripts/audit_surface_contract.py` fails if a supported Apple data surface is missing from the MCP tools, CLI parser, health summary, access requirements, or public capability matrix.

## Commands

Run from the plugin root:

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py --json .
uv run python scripts/public_release_scan.py --json
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_messages_public_surface.py --json
uv run python scripts/audit_surface_contract.py
swiftc -typecheck scripts/eventkit_helper.swift
swiftc -typecheck scripts/contacts_helper.swift
swiftc -typecheck scripts/photos_helper.swift
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_runtime.py
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py --cursor-config .cursor/mcp.json --require-cursor
uv run python scripts/audit_plugin_artifact_hygiene.py --json
```

Also run the plugin and skill validator scripts when those local validator helpers are installed in the current Codex skills cache.

After source checks pass and before reinstalling, sync the personal plugin root. After reinstalling, run runtime/audit checks from the installed cache, then run artifact hygiene from the source checkout. Installed-cache commands can still create generated artifacts such as `.venv`; MCP startup and the runtime verifier must not create installed-cache bytecode artifacts:

```bash
cd /absolute/path/to/local-apple-data
uv run python scripts/sync_personal_plugin.py --json
codex plugin add local-apple-data@personal
cd /absolute/path/to/installed/local-apple-data/<version>
uv run python scripts/verify_runtime.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_messages_public_surface.py --json
uv run python scripts/audit_surface_contract.py
cd /absolute/path/to/local-apple-data
uv run python scripts/verify_cross_agent_sync.py
uv run python scripts/audit_plugin_artifact_hygiene.py --json
```

For a public source-only checkout without configured clients:

```bash
uv run python scripts/verify_cross_agent_sync.py --skip-codex --skip-file-sync --skip-claude --skip-openclaw --skip-cursor --skip-live-processes
```

## Current Acceptance Criteria

- Tests pass.
- Compile succeeds.
- Plugin and skill validators pass when the local validator helpers are installed.
- Runtime verifier prints JSON and exits zero.
- Empty Mail search returns `empty_query`.
- Wildcard-only Mail, Messages, Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Freeform folders, Notes, Calendar, Contacts, Photos, iCloud Drive, SQLite Reminders, and EventKit Reminders searches return `broad_query`.
- Mail, Messages, Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Freeform, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive exact-get accept opaque handles from search/list output.
- Mail, Messages, Hide My Email, Voice Memos, Safari, Shortcuts, Books, Podcasts, Music, TV, Freeform, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive exact-get reject legacy raw row-ID, raw framework identifier, raw alias identifier, recording identifier, Shortcuts identifier, raw Books asset IDs, raw Books annotation UUIDs, raw Podcasts identifiers, raw Music identifiers, raw TV identifiers, raw Freeform identifiers, or direct-path handles with `invalid_handle`.
- Mail search returns a metadata-only `content_status` hint without reading message bodies.
- Mail selected-mailbox message metadata requires one exact `mail:mailbox:v1:` handle plus a date bound, caps results, and returns no bodies, full headers, raw paths, or raw account IDs.
- Mail body/advanced/attachment discovery requires date bounds and returns only capped snippets, masked header metadata, or attachment filename/MIME metadata. Regression tests also enforce subject-only advanced search without `.emlx` parsing, metadata-only attachment paths without nonmatching payload reads, ISO date bounds matching Unix-scale local Mail timestamps, Mail MCP wrapper failures returning redacted `mcp_tool_error` payloads, and a same-stdio-session Mail MCP error followed by a successful Contacts response.
- Mail FTS build requires date bounds plus explicit confirmation, paginates with `next_cursor`, rejects `reset` on continuation cursors, rejects symlink/non-regular index, ancestor, and sidecar paths, and reset validates then removes the private index plus WAL/SHM/journal sidecars before rebuilding from scratch.
- Mail FTS search requires date bounds, opens the index read-only, rechecks current live row/date/content state, returns only exact handles plus capped redacted snippets, and never returns cache paths, raw indexed text, full bodies, attachment bytes, or raw MIME.
- Mail and Notes metadata handles use the `v2` fully opaque HMAC format.
- Mail content accepts only `mail:message:v2:` handles, returns bounded paged plain text with `next_offset`, and rejects raw IDs, old handles, mailbox refs, paths, and negative offsets.
- Mail unsubscribe metadata accepts only one exact `mail:message:v2:` handle; reads only the bounded local header prefix; returns ordered allowlisted http(s)/mailto `List-Unsubscribe` and `List-Help` endpoints; classifies one-click only for HTTPS plus an exact RFC 8058 `List-Unsubscribe=One-Click` post header; keeps `List-Help` manual-only; rejects control-bearing, credential-bearing, malformed, and other-scheme endpoints without returning them; and returns no body, unrelated/full headers, raw account ID, or local path.
- Mail unsubscribe metadata body-link inspection is off by default and requires `include_body_links:true` / `--include-body-links`. It inspects only the exact selected MIME body's HTML anchors, returns no body/labels/unrelated links, caps accepted URLs at five, accepts only explicit unsubscribe/opt-out/stop-receiving text, unsubscribe/optout path-query signals, or conservative adjacent unsubscribe-then-click-here context, rejects generic manage/preferences/login/resubscribe links unless the anchor text itself explicitly says unsubscribe, and always classifies accepted body links as manual-required and never one-click.
- Each accepted body link returns only a bounded `match_reason` enum (`explicit_unsubscribe_text`, `unsubscribe_url`, or `adjacent_unsubscribe_phrase`) for conservative downstream selection; explicit anchor wording wins over URL/context signals, and no anchor label is returned.
- Mail content truncation returns `content_truncated`.
- Mail attachment listing accepts only exact `mail:message:v2:` handles, returns bounded metadata with `mail:attachment:v1:` handles, and rejects raw message IDs.
- Mail attachment export requires both the selected message handle and exact `mail:attachment:v1:` handle, writes to a caller-selected output directory, reports externalized/partial attachments as unavailable, never returns inline bytes, and does not log source message paths.
- Mail planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, at least one To recipient, and a bounded subject.
- Mail capped bulk triage planning returns `kind:"mail_bulk_triage"`, accepts unique exact message handles only for read/flag/archive/move/trash operations, caps selected handles at 20, binds every current selected-message state into the approval fingerprint, and rejects duplicate or raw handles.
- Mail archive/move/trash read-back after Mail re-keys a row filters `message_global_data.message_id_header` by both normalized and bracketed RFC Message-ID inside the exact target mailbox, caps the query at two rows, refuses duplicate matches, and never recursively scans the target Mail tree; synthetic single-message and bulk archive regressions enforce that performance shape.
- Mail create-draft apply requires a matching approval token, explicit confirmation, save-only Mail.app automation, and local Drafts read-back when available.
- Mail send-message planning returns `send_permitted:true`, `irreversible_external_send:true`, `retry_safe:false`, a bounded body preview, and no mutation.
- Mail send-message apply requires a matching approval token, explicit confirmation, scoped Mail.app send automation without draft save, Sent-copy read-back when available, no sent body echo, and a `partial` result when Mail.app accepts the send but Sent read-back is delayed.
- Messages get accepts only `messages:chat:v1:` handles, returns bounded chat transcript text, rejects raw row IDs and fabricated handles, and does not return participant identifiers.
- Messages participant listing accepts only `messages:chat:v1:` handles, returns opaque `messages:participant:v1:` handles plus service/count/timestamp metadata without phone/email previews, rejects raw chat IDs, and does not return participant identifiers.
- Messages participant detail requires both the original `messages:chat:v1:` handle and a selected `messages:participant:v1:` handle, returns the full selected participant identifier only in exact detail, and rejects fabricated participant handles.
- Messages transcript truncation returns `content_truncated`.
- Messages attachment listing accepts only exact `messages:chat:v1:` handles, returns bounded metadata with `messages:attachment:v1:` handles, and rejects raw chat IDs.
- Messages attachment export requires both the selected chat handle and exact `messages:attachment:v1:` handle, writes to a caller-selected output directory, reports missing local media as unavailable, never returns inline bytes, and does not log source media paths.
- Messages planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, bounded body preview, and requires exact opaque chat handles.
- Messages apply requires a matching approval token, explicit confirmation, stale chat-state refusal, Messages.app automation, ghost-row detection, local `chat.db` read-back verification, and does not echo the sent body in apply output.
- Hide My Email search rejects domain-only and generic queries, returns masked alias previews only, includes `authoritative_inventory:false`, and never returns full aliases during search.
- Hide My Email get accepts only `hide_my_email:alias:v1:` handles, returns exact selected alias detail, rejects raw identifiers and fabricated handles, and reports local Mail metadata provenance.
- Voice Memos get accepts only `voice_memos:recording:v1:` handles, returns bounded existing embedded transcript text when available, rejects raw recording IDs and fabricated handles, and does not return audio bytes, raw paths, or recording identifiers.
- Voice Memos transcript truncation returns `content_truncated`.
- Safari item search rejects empty and broad queries, returns title/domain metadata without full URLs, and uses opaque `safari:item:v1:` handles.
- Safari get accepts only `safari:item:v1:` handles, returns the selected full URL only by exact handle, and rejects raw identifiers and fabricated handles.
- Safari folder search/detail/listing uses opaque `safari:folder:v1:` handles, returns direct child metadata only, omits full URLs, and rejects raw/fabricated folder handles.
- Shortcuts search rejects empty and broad queries, returns shortcut/folder name metadata without raw identifiers or shortcut bodies, and uses opaque `shortcuts:item:v1:` handles.
- Shortcuts get and folder-items accept only `shortcuts:item:v1:` handles, return selected metadata only, reject raw identifiers/fabricated handles, and folder-items refuses shortcut handles plus arbitrary folder-name filters.
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
- Music playlist-tracks accepts only an exact `music:playlist:v1:` handle, returns capped selected-playlist track metadata only, and rejects raw identifiers and fabricated handles.
- TV search rejects empty and broad queries, returns item title/show/artist/genre/video-kind/duration/season/episode/year metadata without video bytes, file paths, artwork, descriptions, raw identifiers, playback state, watched state, ratings, or favorites, and uses opaque `tv:item:v1:` handles.
- TV get accepts only `tv:item:v1:` handles, returns selected item metadata only, and rejects raw identifiers and fabricated handles.
- TV playlists rejects empty and broad queries, returns playlist title/kind/count/duration metadata without broad playlist item dumps or raw identifiers, and uses opaque `tv:playlist:v1:` handles.
- TV playlist accepts only `tv:playlist:v1:` handles, returns selected playlist metadata only, and rejects raw identifiers and fabricated handles.
- TV playlist-items accepts only an exact `tv:playlist:v1:` handle, returns capped selected-playlist item metadata only, and rejects raw identifiers and fabricated handles.
- Freeform boards returns capped recent board metadata without board titles/content, board BLOBs, decoded board items, asset bytes, previews, collaboration payloads, raw identifiers, or raw rows, and uses opaque `freeform:board:v1:` handles.
- Freeform get accepts only `freeform:board:v1:` handles, returns selected board metadata only, and rejects raw identifiers and fabricated handles.
- Freeform folders rejects empty and broad queries, returns folder-title metadata without folder BLOBs, raw identifiers, or raw rows, and uses opaque `freeform:folder:v1:` handles.
- Freeform folder accepts only `freeform:folder:v1:` handles, returns selected folder metadata only, and rejects raw identifiers and fabricated handles.
- Freeform folder-boards accepts only an exact `freeform:folder:v1:` handle, returns capped selected-folder board metadata only, excludes deleted boards, and rejects raw identifiers and fabricated handles.
- Freeform child-folders accepts only an exact `freeform:folder:v1:` handle, returns capped direct child-folder metadata only, excludes deleted/hidden folders, and rejects raw identifiers and fabricated handles.
- Notes content accepts only `notes:note:v2:` handles, returns bounded plain text, and rejects raw IDs, old handles, direct database IDs, and fabricated handles.
- Notes folder metadata, folder-items, and folder-tree accept only `notes:folder:v1:` handles from `notes folders` / `notes_search_folders`, return no raw folder IDs or account identifiers, reject raw IDs, old handles, direct database IDs, and fabricated handles. Folder-items returns capped direct child folder metadata plus direct note metadata without note bodies, snippets, or attachment bytes; folder-tree returns capped descendant folder metadata without notes, note bodies, snippets, attachment bytes, or paths.
- Notes content truncation returns `content_truncated`, `content_total_chars`, and `next_offset` so long imported notes can be retrieved in bounded chunks.
- Notes content automation failures return safe warning codes without raw AppleScript errors or database paths.
- Notes attachment listing accepts only exact `notes:note:v2:` handles, returns bounded metadata with `notes:attachment:v1:` handles, and rejects raw note IDs.
- Notes attachment export accepts only exact `notes:attachment:v1:` handles, writes to a caller-selected output directory, prefers local media files, falls back to local BLOB data, reports remote-only attachments as unavailable, never returns inline bytes, and does not log source media paths.
- iCloud Drive content accepts only `icloud:file:v1:` handles, returns bounded text for supported text-like files, and rejects direct paths, fabricated handles, symlinks, hidden files, and unsupported binary/document types.
- iCloud Drive content truncation returns `content_truncated`.
- iCloud Drive planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, exact opaque parent folder handles for create-folder/create-text, exact opaque directory handles plus directory `metadata_sha256` for rename-folder, trash-folder, and delete-folder, exact opaque directory handles plus exact opaque target parent handles plus directory `metadata_sha256` for move-folder and copy-folder, exact opaque file handles plus expected current SHA-256 for append-text, replace-text, trash-text, delete-text, rename-text, copy-text, and move-text, and an `expected_file_identity_sha256` preview target only for delete-text.
- iCloud Drive apply requires a matching approval token, explicit confirmation, fd-based no-follow exclusive mkdir for create-folder, fd-based no-follow exclusive rename for exact rename-folder with metadata drift refusal, source/target proof, non-empty child preservation, `non_empty_allowed:true`, and no content hash return, fd-based no-follow recoverable Trash move for exact trash-folder with metadata drift refusal, original absence proof, non-empty child preservation, `non_empty_allowed:true`, and no raw Trash path/content hash return, fd-based no-follow hidden staging plus bounded permanent staged-tree removal for exact selected-folder delete-folder with metadata and private tree drift refusal, hidden/symlink/package/tree-size refusal, original absence proof, `verified_absent:true`, no content hash/text return, no Trash path return, no staging path return, and no false `permanently_deleted` proof on partial rollback failure, fd-based no-follow exclusive move for exact move-folder with exact target-parent binding, metadata drift refusal, descendant-parent refusal, no-overwrite target proof, source/target proof, non-empty child preservation, `non_empty_allowed:true`, and no content hash return, bounded no-follow recursive copy for exact copy-folder with exact target-parent binding, private source-tree binding, metadata and tree drift refusal, hidden/symlink/package/tree-size refusal, descendant-parent refusal, no-overwrite target proof, source preservation proof, target identity proof, source-race cleanup/partial reporting without child listing, `non_empty_allowed:true`, and no content hash return, fd-based no-follow exclusive create for create-text, current-SHA drift refusal for append-text/replace-text/trash-text/rename-text/copy-text/move-text with no target mutation on stale input, delete-text exact file identity token binding with stale-token replay refusal for recreated same-path/same-content files, same-directory atomic replacement plus immediate pre-replace SHA recheck for append-text and replace-text, fd-based no-follow atomic Trash swap plus post-swap SHA verification and swap-back on drift for trash-text, fd-based no-follow random-only hidden staging plus permanent unlink for delete-text with original absence proof, `verified_absent:true`, no content hash/text return, no Trash path return, no staging path return, no false `permanently_deleted` proof on partial rollback failure, and no original filename or extension in rollback staging leftovers, no-overwrite target reservation plus fd-relative no-follow swap for rename-text/move-text, post-swap target identity/SHA proof before placeholder cleanup, rollback only when identities are verifiable before target proof, no rollback after verified target proof if source-placeholder cleanup races, no-follow exclusive create plus post-copy source SHA recheck for copy-text, original-handle absence proof for trash-text/delete-text and rename/move, source preservation proof for copy, accurate content-inspection privacy flags on stale/refusal paths, hidden CLI `--root` refusal outside `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`, and read-back verification with `partial`/`read_back_mismatch` on mismatch.
- Calendar get accepts only `calendar:event:v1:` handles, returns bounded exact event location/notes details, and rejects raw EventKit identifiers and fabricated handles.
- Calendar notes truncation returns `content_truncated`.
- Calendar planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, requires explicit calendar title plus ISO 8601 start/end timestamps for create, and binds structured-location plus selected/future/whole-series recurring-delete proof metadata for scoped delete.
- Calendar apply requires a matching approval token, explicit confirmation, EventKit helper apply, structured-location proof where requested, and read-back verification.
- Contacts get accepts only `contacts:contact:v1:` handles, returns exact contact detail fields plus `update_safe_sha256`, `delete_safe_sha256`, and note hash/length when Contacts.framework note access is available, rejects raw Contacts identifiers and fabricated handles, and never returns existing note text.
- Contacts count/export tests cover metadata-only live counts and JSON/vCard backup files with count-match verification and no contact-data echo in the response. Contacts group-member tests assert exact group-handle gating, capped metadata output, degraded response shape, and absence of raw member IDs or helper-provided contact detail values. Contacts container-member tests assert exact container-handle gating, capped metadata output, degraded response shape, and absence of raw contact IDs or helper-provided contact detail values. Contacts write tests cover exact scalar/method/rich-field/image update, exact note append/set/clear/merge, exact group membership, exact group create/rename/delete, exact batch, and exact delete with synthetic Contacts.framework helper payloads only. Contacts note cases are synthetic contract tests only; the live helper is expected to fail closed with `contacts_note_unavailable`. Free-form label tests cover the 255-character ceiling and control-character refusal.
- Contacts planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, requires a person name or organization name for contact create, binds optional exact container handles through `container_safe_sha256`, requires an exact handle plus `update_safe_sha256` for exact scalar/method/rich-field/image update, requires an exact handle plus `note_safe_sha256` for exact note mutation, requires contact/group safe hashes for group membership, requires exact group handle plus `group_safe_sha256` for group rename/delete, and requires an exact contact handle plus `delete_safe_sha256` for exact contact delete. For live Contacts note operations, planning instead fails closed with `contacts_note_unavailable` before an apply-capable preview.
- Contacts apply requires a matching approval token, explicit confirmation, Contacts.framework helper apply, stale-state refusal for exact update, note mutation, group membership, group create/rename/delete, and exact contact delete, read-back verification for create/update, hash-only note read-back for note mutation, group metadata read-back for membership/create/rename, group absence proof with `contacts_deleted:false` for group delete, and contact absence proof for contact delete. Omitted method arrays preserve existing values, provided method arrays replace, and explicit empty arrays clear. Note apply/read-back assertions are synthetic contract coverage only; live note apply never reaches mutation on this signing path.
- Notes planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, and deterministic idempotency metadata for default/exact-folder plaintext or rich-text note create, exact child-folder create, exact-folder rename, exact empty child-folder delete or same-account move, exact-note plaintext append/replace, rich-text body replace, move-to-folder, and exact-note delete. Note changes bind exact handles and expected content state; folder changes bind exact source/destination handles, normal-folder/empty/same-account constraints, title or metadata state, and target-parent proof; rich-text inputs are sanitized before an apply-capable preview.
- Notes apply requires the matching approval token, explicit confirmation, Notes.app automation, and operation-specific read-back: exact content for plaintext create/update, extracted-visible-text semantic proof for sanitized rich-text create/replace, parent/title/absence/destination-parent proof for folder create/rename/delete/move, selected-folder proof for note move, and exact-handle absence proof for note delete.
- Photos get/export accepts only `photos:asset:v1:` handles, returns exact asset/resource or destination metadata, rejects raw Photos identifiers and fabricated handles, and never returns inline asset bytes.
- Photos planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, import source filename/media type/size/hash without echoing the raw source path, or exact asset favorite/hidden target metadata with expected-state binding and no raw PhotoKit identifier return.
- Photos apply requires a matching approval token, explicit confirmation, source-file hash binding and created-asset read-back for import, or exact asset handle plus expected favorite/hidden state binding and target-state read-back verification for `update_flags`.
- Reminders content accepts only `reminders:reminder:eventkit:v1:` handles, returns bounded exact reminder notes, and rejects raw EventKit identifiers, legacy SQLite reminder handles, and fabricated handles.
- Reminders list metadata accepts only `reminders:list:eventkit:v1:` handles after bounded list-title metadata search and rejects raw list names/identifiers as apply targets.
- Reminders selected-list item metadata accepts only `reminders:list:eventkit:v1:` handles, fetches only that EventKit list, caps output, defaults to incomplete reminders, and returns no note bodies, raw EventKit identifiers, raw URLs, raw alarm detail, or attachments.
- Reminders reads through the EventKit helper are non-prompting; unavailable
  permission returns `reminders_access_unavailable`. `reminders request-access`
  is the explicit prompt path for the stable helper app, with source assertions
  that the helper calls `requestFullAccessToReminders` or the legacy
  `requestAccess(to: .reminder)` fallback.
- Reminder notes truncation returns `content_truncated`.
- Reminders planning returns `mode: "plan"`, `mutation_applied:false`, `apply_available:true`, deterministic idempotency metadata, and requires exact EventKit reminder handles for existing-reminder operations plus exact expected current-list and same-source target-list handles for list-move.
- Reminders apply requires a matching approval token, explicit confirmation, expected state, EventKit helper apply, URL hash-only or absence proof where requested, and read-back verification for create, complete, uncomplete, due-date/title/notes/priority/URL update, URL clear, exact same-source list-move with exact expected current-list handle and `target_list_verified:true`, and exact delete.
- Health and doctor do not expose full local executable paths.
- Health and doctor report broad local Apple data readiness without content reads, raw rows, credentials, prompt-triggering framework access, or raw absolute store paths.
- Health covers schema-only Mail, Messages, Voice Memos, Books, Podcasts, Freeform, Notes, and Reminders checks plus Safari bookmarks, Shortcuts CLI availability, Music.app/TV.app osascript readiness, and iCloud Drive root readiness, a normalized per-surface summary, and non-prompting access requirements for Calendar, Contacts, Photos, Reminders, Notes automation, Messages automation, Music/TV automation-on-exact-call, and other framework-backed surfaces.
- Write-design gates require the Reminders create/complete/uncomplete/due-date/title/notes/priority/exact URL update-clear/exact same-source list-move/delete plus exact list create/rename/empty-delete/same-source migrate-delete, iCloud Drive, Calendar target-calendar create/move/default-calendar plan-only exact-handle resolution/availability create-update/simple recurrence create-update/exact allow-listed event URL create-update/structured-location/synthetic `LAD-TEST-*` calendar create-rename-delete with absence proof, Contacts create/exact scalar-method-rich-image update/exact group membership/exact group create-rename-delete/exact batch/delete, Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, rich-text body create, rich-text body replace, move-to-folder, and exact-note delete, Mail draft/send/reply/reply-all/forward plus read/flag/archive/move/trash triage/synthetic mailbox/synthetic cleanup, Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete, Messages send-text/send-file, bounded home-directory Filesystem, and exact identifier-bound Shortcuts run write design contracts and allow only `reminders apply` / `reminders_apply_change`, `reminders apply-list` / `reminders_apply_list_change`, `icloud-drive apply` / `icloud_drive_apply_change`, `calendar apply` / `calendar_apply_change`, `calendar apply-calendar` / `calendar_apply_calendar_change`, `contacts apply` / `contacts_apply_change`, `notes apply` / `notes_apply_change`, `mail apply` / `mail_apply_change`, `mail apply-mailbox` / `mail_apply_mailbox_change`, `mail apply-cleanup` / `mail_apply_cleanup`, `photos apply` / `photos_apply_change`, `messages apply` / `messages_apply_change`, `filesystem apply` / `filesystem_apply_change`, and `shortcuts apply` / `shortcuts_apply_run` as the 14 approved public MCP apply tools. Contacts note design tests remain synthetic-only because live note operations fail closed with `contacts_note_unavailable`.
- The count is 14 MCP apply-tool names. Their paired CLI command aliases are
  documented alongside them but are not counted as additional MCP tools.
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
- Exact `icloud_drive_get_root` succeeds from a synthetic configured root,
  returns an opaque root directory handle without raw paths, resolves through
  list/tree, and rejects the root as a folder rename/Trash/delete/move/copy
  source while allowing it as a create/import parent.
- Exact `icloud_drive_list_folder` succeeds from a synthetic opaque directory
  handle, returns direct child metadata only, skips hidden/symlink/package
  entries, streams child enumeration with a scan cap before sorting, and returns
  no content or raw paths.
- Exact `icloud_drive_list_tree` succeeds from a synthetic opaque directory
  handle, returns bounded descendant metadata only, includes directories at the
  requested max depth without descending past them, refuses child metadata drift
  before recursion, respects total tree scan caps, skips hidden/symlink/package
  entries at every level, and returns no content or raw paths.
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
- Search output returns event metadata without event identifiers, notes, locations, attendee identities, raw URLs, or event URL hashes.
- Selected-calendar event listing requires an exact `calendar:calendar:v1:`
  handle plus explicit start/end bounds, caps output, and returns no raw
  EventKit identifiers, notes, location text, attendee names/URLs, event URL
  values, or raw alarm detail.
- Exact event details return bounded notes/location text and report truncation.
- Calendar reads through the EventKit helper are non-prompting; unavailable
  permission returns `calendar_access_unavailable`. `calendar request-access`
  is the explicit prompt path for the stable helper app, with source assertions
  that the helper keeps the run loop alive and activates AppKit before the
  access request.
- Runtime verification covers synthetic content success and invalid-handle rejection without touching real Calendar content.

## v1.5 Acceptance Criteria

The Reminders EventKit phase keeps synthetic fixtures and exact-handle proof:

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
- Existing contact note text is not returned; exact detail may expose note hash/length, and backup export writes note text only into the caller-selected archive files.
- Normal Contacts helper access is non-prompting; unavailable permission
  returns `contacts_access_unavailable`. `contacts request-access` is the
  explicit CLI-only prompt path for the stable signed helper app. Tests redirect
  the helper root, mock signing/framework calls, verify private IPC and safe
  timeout/error contracts, and assert the prompt path is absent from MCP.
- The locally self-signed helper has no restricted Contacts-notes entitlement. Therefore live Contacts note plan/apply must return `contacts_note_unavailable` before mutation; note success cases use synthetic helper fixtures only.
  Synthetic tests require note operations to fail before mutation and archive
  fallback to retain a note-free JSON result if notes or vCard serialization
  are unavailable; tests never export the operator's real Contacts.
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
- Photos import apply requires the matching approval token, explicit confirmation, source-file hash binding, and created-asset read-back through the mocked PhotoKit helper; Photos `update_flags` planning refuses missing target flags and missing or stale expected state, and apply requires the matching approval token, explicit confirmation, exact asset handle, expected favorite/hidden state binding, and target favorite/hidden read-back; Photos `delete` planning/apply requires exact asset handle binding, matching approval token, explicit confirmation, helper delete proof, and `verified_absent:true` absence read-back without raw PhotoKit identifiers; exact regular-album create/rename/delete planning/apply requires duplicate-title refusal, exact album-state binding where applicable, empty-album proof for delete, title read-back for create/rename, absence proof for delete, and preserved `apply_unknown` mutation state.
- No thumbnails, raw Photos identifiers, broad dumps, network iCloud fetches, content edit, permanent delete, smart/shared/synced album targeting, album membership outside exact regular-album add/remove, metadata mutation outside favorite/hidden, or bulk Photos operations are returned.
- PhotoKit helper access is non-prompting during normal reads/writes; unavailable permission returns `photos_access_unavailable`, and `photos request-access` is the explicit one-time prompt path after TCC resets. The helper app carries PhotoKit usage strings plus the macOS Photos Library entitlement; if macOS does not surface the prompt, the live unblock is manual Privacy & Security > Photos approval for `Local Apple Data Photos Helper`.
- Runtime verification covers synthetic asset detail/export, synthetic import plan/apply success, synthetic update_flags plan/apply/stale-state behavior, synthetic regular-album create/rename/delete plan/apply, missing confirmation, and invalid-handle rejection without touching real Photos content.

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
- List-move planning requires an exact opaque `reminders:reminder:eventkit:v1:` handle, exact expected current-list opaque `reminders:list:eventkit:v1:` handle, exact same-source opaque `reminders:list:eventkit:v1:` target list handle, expected title, expected completed state, and expected current list name.
- URL update/clear planning requires an exact opaque `reminders:reminder:eventkit:v1:` handle, expected title, expected completed state, exact expected URL presence, expected URL SHA-256 when present, and update-only replacement URL input; apply requires hash-only URL read-back or absence proof and no raw URL return.
- Due-date planning accepts `YYYY-MM-DD` or timezone-aware ISO 8601 and rejects naive timestamps.
- Planning returns a deterministic `reminders-plan:v1:` idempotency key and approval fingerprint.
- `reminders apply` and `reminders_apply_change` require the matching `reminders-apply:v1:<approval_fingerprint>` token and explicit confirmation.
- Existing-reminder apply resolves exact opaque handles internally and checks expected state before calling EventKit; list-move also resolves the exact expected current-list handle and exact same-source target-list handle, then requires `target_list_verified:true` identity proof instead of title-only proof.
- Apply returns `mode: "apply"`, `mutation_applied:true`, and read-back metadata only after EventKit save succeeds.
- Logs do not contain planned titles, notes, list names, handles, or approval fingerprints.
- Runtime verification covers synthetic planning, list search, list handle opacity, list-move apply, exact list create/rename/empty-delete/same-source migrate-delete with ordinary fixture titles, and mocked apply without touching live Reminders.
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

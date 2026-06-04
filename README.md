# local-apple-data

[![CI](https://github.com/BillyBunn/local-apple-data/actions/workflows/ci.yml/badge.svg)](https://github.com/BillyBunn/local-apple-data/actions/workflows/ci.yml)

Local-first Apple data access for Codex and other MCP clients.

This project provides a privacy-gated CLI and MCP server for locally synced:

- Mail.app mail, including iCloud and Gmail accounts synced locally through Mail.app
- Messages chats synced locally through Messages.app
- Inferred Hide My Email aliases observed in local Mail address metadata
- Voice Memos synced locally through Voice Memos.app
- Safari bookmarks and Reading List items synced locally through Safari/iCloud
- Apple Shortcuts shortcut and folder metadata through the local `shortcuts` CLI
- Apple Notes
- Apple Calendar
- Apple Reminders
- Apple Contacts
- Apple Photos
- iCloud Drive local files and folders

The current release is local-only and read-mostly. The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, Photos import apply, and Messages send-text apply, and each requires a matching plan approval token plus explicit confirmation. The plugin does not use the Gmail connector, Gmail API, IMAP credentials, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or any network mail service.

## Current Status

The MCP server, local skill/plugin packaging, exact-handle content/detail/export retrieval, approved Reminders, iCloud Drive, Calendar, Contacts, Notes, Mail draft, Photos import, and Messages send-text apply paths, and synthetic runtime verification paths are implemented for the surfaces listed below. Real-machine smoke stays schema-only unless a user intentionally requests a specific metadata search, provides/selects a specific Mail, Messages, inferred Hide My Email, Voice Memos, Safari, Shortcuts, Notes, Calendar, Reminders, Contacts, Photos, or iCloud Drive handle for content/detail/export retrieval, or explicitly approves a Reminder, iCloud Drive, Calendar, Contacts, Notes, Mail draft, Photos import, or Messages send-text apply operation generated from a matching plan.

Implemented now:

- Repo guidance and privacy model
- `local-apple-data health --json` with redacted broad-surface readiness summaries, schema-only Mail/Messages/Voice Memos/Notes/Reminders checks, Safari bookmarks and iCloud Drive root checks, Shortcuts CLI availability, and non-prompting access requirements for framework-backed surfaces
- `local-apple-data doctor --json` with redacted non-mutating remediation guidance
- `local-apple-data mail search/get` metadata commands
- Metadata-only `content_status` hints in Mail search results so agents can prefer locally retrievable messages before exact content calls
- `local-apple-data mail content --json --handle <mail:message:v2:...> --max-chars 4000` for exact-handle local Mail plain-text content
- `local-apple-data mail attachments --json --handle <mail:message:v2:...>` for exact selected-message attachment metadata with opaque `mail:attachment:v1:` handles
- `local-apple-data mail export-attachment --json --message-handle <mail:message:v2:...> --handle <mail:attachment:v1:...> --output-dir <dir>` for exact local Mail attachment export without inline bytes or source message paths
- `local-apple-data mail plan --json --operation create-draft --to <address> --subject <subject> --body-text <text>` for non-mutating future draft-create previews with idempotency and approval metadata
- `local-apple-data mail apply --json --operation create-draft --to <address> --subject <subject> --body-text <text> --approval-token <token> --confirm-apply` for the approved Mail create-draft path, with save-only Mail.app automation and local read-back verification when the Drafts store exposes the saved draft
- `local-apple-data messages search/get` commands for local Messages chat display-name metadata and exact bounded transcripts, including modern local `attributedBody` plaintext fallback when `message.text` is empty
- `local-apple-data messages attachments --json --handle <messages:chat:v1:...>` for exact selected-chat attachment metadata with opaque `messages:attachment:v1:` handles
- `local-apple-data messages export-attachment --json --chat-handle <messages:chat:v1:...> --handle <messages:attachment:v1:...> --output-dir <dir>` for exact local Messages attachment export without inline bytes or source media paths
- `local-apple-data messages plan --json --operation send-text --handle <messages:chat:v1:...> --body-text <text>` for non-mutating future send-text previews with chat-state, body-hash, idempotency, and approval metadata
- `local-apple-data messages apply --json --operation send-text --handle <messages:chat:v1:...> --body-text <text> --approval-token <token> --confirm-apply` for the approved Messages send-text path, with Messages.app automation, stale chat-state refusal, ghost-row detection, and local read-back verification without echoing the sent body in apply output
- `local-apple-data hide-my-email search/get` commands for inferred Hide My Email aliases observed in local Mail address metadata
- `local-apple-data voice-memos search/get/export` commands for local Voice Memos title/filename metadata, exact existing embedded transcripts, and exact-handle `.m4a` export to a caller-selected output directory
- `local-apple-data safari search/get` commands for local Safari bookmarks and Reading List title/URL metadata plus exact selected URL detail by opaque handle
- `local-apple-data shortcuts search/get` commands for local Apple Shortcuts shortcut/folder name metadata by opaque handle, without running, opening, signing, exporting, or returning shortcut bodies
- `local-apple-data notes search/get` metadata commands
- `local-apple-data notes content --json --handle <notes:note:v2:...> --max-chars 4000 --offset 0` for exact-handle local Notes plain-text content, with `next_offset` pagination for long imported notes
- `local-apple-data notes attachments --json --handle <notes:note:v2:...>` for exact selected-note attachment metadata with opaque `notes:attachment:v1:` handles
- `local-apple-data notes export-attachment --json --handle <notes:attachment:v1:...> --output-dir <dir>` for exact local Notes attachment export without inline bytes or source media paths
- `local-apple-data notes plan --json --operation create --title <title> --body-text <text>` for non-mutating future note-create previews with idempotency and approval metadata
- `local-apple-data notes apply --json --operation create --title <title> --body-text <text> --approval-token <token> --confirm-apply` for the approved Notes create-note path, with Notes.app automation and exact-content read-back verification
- `local-apple-data notes plan --json --operation append-text --handle <notes:note:v2:...> --expected-current-sha256 <sha256> --body-text <text>` for non-mutating future note append previews with expected-current-content binding
- `local-apple-data notes apply --json --operation append-text --handle <notes:note:v2:...> --expected-current-sha256 <sha256> --body-text <text> --approval-token <token> --confirm-apply` for the approved Notes append-text path, with drift refusal and exact-content read-back verification
- `local-apple-data icloud-drive search/get` metadata commands for local iCloud Drive items by filename
- `local-apple-data icloud-drive content --json --handle <icloud:file:v1:...> --max-chars 4000` for exact-handle local iCloud Drive text-file content
- `local-apple-data icloud-drive plan --json --operation create-text --parent-handle <icloud:file:v1:...> --filename <name.md> --content-text <text>` for non-mutating future text-file create previews with idempotency and approval metadata
- `local-apple-data icloud-drive apply --json --operation create-text --parent-handle <icloud:file:v1:...> --filename <name.md> --content-text <text> --approval-token <token> --confirm-apply` for the approved iCloud Drive create-text path, with exclusive create and read-back verification
- `local-apple-data icloud-drive plan --json --operation append-text --handle <icloud:file:v1:...> --expected-current-sha256 <sha256> --content-text <text>` for non-mutating future text append previews with expected-current-content binding
- `local-apple-data icloud-drive apply --json --operation append-text --handle <icloud:file:v1:...> --expected-current-sha256 <sha256> --content-text <text> --approval-token <token> --confirm-apply` for the approved iCloud Drive append-text path, with drift refusal and read-back hash verification
- `local-apple-data calendar search/get` commands for local Calendar events by title through EventKit
- `local-apple-data calendar plan --json --operation create --title <title> --calendar-title <calendar> --start-date <ISO> --end-date <ISO>` for non-mutating future timed-event create previews with idempotency and approval metadata
- `local-apple-data calendar apply --json --operation create --title <title> --calendar-title <calendar> --start-date <ISO> --end-date <ISO> --approval-token <token> --confirm-apply` for the approved Calendar create-event path, with EventKit apply and read-back verification
- `local-apple-data contacts search/get` commands for local Contacts by name or organization through Contacts.framework
- `local-apple-data contacts plan --json --operation create --contact-type person --given-name <name> --family-name <name>` for non-mutating future contact-create previews with idempotency and approval metadata
- `local-apple-data contacts apply --json --operation create --contact-type person --given-name <name> --family-name <name> --approval-token <token> --confirm-apply` for the approved Contacts create-contact path, with Contacts.framework apply and read-back verification
- `local-apple-data photos search/get/export` commands for local Photos asset metadata by original filename, exact asset/resource metadata, and exact-handle asset export to a caller-selected output directory through PhotoKit
- `local-apple-data photos plan --json --operation import --source-file <path>` for non-mutating future image/video import previews with source-file hash binding and approval metadata
- `local-apple-data photos apply --json --operation import --source-file <path> --approval-token <token> --confirm-apply` for the approved Photos import path, with PhotoKit apply and created-asset read-back verification
- `local-apple-data reminders search/due` metadata commands
- `local-apple-data reminders eventkit-search` for local Reminders title metadata through EventKit
- `local-apple-data reminders content --json --handle <reminders:reminder:eventkit:v1:...> --max-chars 4000` for exact-handle local Reminder notes
- `local-apple-data reminders plan --json --operation create|complete|update-due-date ...` for non-mutating future-change previews with idempotency and approval metadata
- `local-apple-data reminders apply --json --operation create|complete|update-due-date ... --approval-token <token> --confirm-apply` for the approved Reminders create/complete/due-date update path, with EventKit apply and read-back verification
- Highest-version Mail store discovery without exposing raw local store paths in normal output
- `local-apple-data-mcp` stdio MCP server with read-only tools plus the approved non-destructive `reminders_apply_change`, `icloud_drive_apply_change`, `calendar_apply_change`, `contacts_apply_change`, `notes_apply_change`, `mail_apply_change`, `photos_apply_change`, and `messages_apply_change` write tools
- MCP runner script that avoids package builds during normal plugin startup
- Codex skill under `skills/local-apple-data/`
- Local plugin manifest under `.codex-plugin/plugin.json`
- Bundled MCP config under `.mcp.json`
- Redacted command event logging
- Opaque signed handles for exact Mail/Messages/Voice Memos/Safari/Shortcuts/Notes/Calendar/Contacts/Photos/Reminders/iCloud Drive metadata fetches
- Exact Mail content retrieval through the same opaque `mail:message:v2:` handles
- Exact Messages chat transcript retrieval through opaque `messages:chat:v1:` handles, using local text plus bounded `attributedBody` plaintext fallback when available
- Exact Messages attachment metadata/export through opaque `messages:chat:v1:` and `messages:attachment:v1:` handles
- Exact inferred Hide My Email alias detail through opaque `hide_my_email:alias:v1:` handles
- Exact Voice Memos transcript retrieval through opaque `voice_memos:recording:v1:` handles when Apple-generated local transcript data is embedded in the selected `.m4a`
- Exact Voice Memos audio export through opaque `voice_memos:recording:v1:` handles to a caller-selected output directory without returning audio bytes inline
- Exact Safari bookmark and Reading List URL detail retrieval through opaque `safari:item:v1:` handles without returning full URLs in search results
- Exact Shortcuts shortcut/folder metadata retrieval through opaque `shortcuts:item:v1:` handles without returning raw identifiers or shortcut bodies
- Exact iCloud Drive text-file retrieval through opaque `icloud:file:v1:` handles
- Exact Calendar event detail retrieval through opaque `calendar:event:v1:` handles
- Exact Contact detail retrieval through opaque `contacts:contact:v1:` handles
- Exact Photos asset metadata/resource detail retrieval through opaque `photos:asset:v1:` handles
- Exact Photos asset export through opaque `photos:asset:v1:` handles to a caller-selected output directory without returning image/video bytes inline
- Exact Reminder note retrieval through opaque `reminders:reminder:eventkit:v1:` handles
- Broad-query rejection for empty, wildcard-only, and one-character searches
- Runtime verification script under `scripts/verify_runtime.py`
- Cross-client sync verifier under `scripts/verify_cross_agent_sync.py`, including optional Cursor `mcp.json` validation
- macOS CI workflow under `.github/workflows/ci.yml`
- Contributor guide under `CONTRIBUTING.md` and GitHub issue/PR templates with privacy and mutation-gate checklists
- Repo-local redaction scanner under `scripts/redaction_scan.py`
- Release-readiness auditor under `scripts/audit_release_readiness.py`
- Mutation-gate auditor under `scripts/audit_mutation_gates.py` so write-like CLI/MCP surfaces cannot appear without explicit gates
- Write-design gate auditor under `scripts/audit_write_design_gates.py` so first-tranche write tools stay machine-checkable and limited to the approved Reminders, iCloud Drive, Calendar, Contacts, Notes create/append, Mail draft, Photos import, and Messages send-text apply surfaces
- Surface-contract auditor under `scripts/audit_surface_contract.py` so MCP tools, CLI commands, health surfaces, access requirements, and the capability matrix stay aligned
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw under `scripts/render_mcp_client_config.py`
- Public release tree builder under `scripts/build_public_release_tree.py`
- Public git checkout preparer under `scripts/prepare_public_git_checkout.py`, including optional initial local commit creation
- Path-redacted release receipt generator under `scripts/generate_release_receipt.py`
- Synthetic unit and CLI tests
- Local git repo on branch `main`

Deferred:

- Any mutating tools other than the approved Reminders create/complete/due-date apply surface, iCloud Drive create/append-text apply surface, Calendar create-event apply surface, Contacts create-contact apply surface, Notes create/append-text apply surface, Mail create-draft apply surface, Photos import apply surface, and Messages send-text apply surface
- Mail send/reply/forward/archive/move/delete/mark/flag/mailbox/account mutation, Mail attachment mutation, broad Mail attachment export, Calendar update/delete/recurrence/attendees/alarms/all-day/default-calendar guessing, Contacts update/delete/merge/move/group membership/postal-address/birthday/relationship/social-profile/notes/image mutation, Notes arbitrary update/delete/move/folder-account/rich-text/attachment mutation, Notes broad attachment export, locked/shared-note mutation, Photos edit/delete/album/hidden/favorite/metadata mutation, Photos network iCloud fetch, Messages direct-recipient send/new-chat/SMS-fallback selection/edit/delete/reaction/tapback/file-send/other mutation, broad Messages attachment export, Messages attachment mutation, Voice Memos mutation or attachments, Safari history/open-tabs/passwords/private-browsing data/bookmark mutation, Shortcuts run/open/view/sign/export/body/action-graph/mutation, Reminders delete/bulk/list/account mutation or attachments, iCloud Drive overwrite/rename/move/copy/delete/binary/document writes, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API access, browser/keychain credential access, generated Voice Memos transcription, broad content search, broad Messages text search, broad Voice Memos transcript search, unsupported/binary iCloud Drive content extraction, and durable content caches

The v1.1 design gate for exact-handle Mail content retrieval is documented in `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md`.
The v1.2 Notes content and broader local Apple data expansion plan is documented in `docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md`.
The public capability matrix is documented in `docs/CAPABILITY_MATRIX.md`.
The ecosystem research and architecture comparison is documented in `docs/ECOSYSTEM_REVIEW.md`.
The write/mutation approval gates are documented in `docs/MUTATION_GATES.md`.
The future write-tool roadmap is documented in `docs/WRITE_TOOL_ROADMAP.md`.
The first Reminders write design gate is documented in `docs/V1_11_REMINDERS_WRITE_DESIGN.md`.
The first iCloud Drive write design gate is documented in `docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md`.
The first Calendar write design gate is documented in `docs/V1_13_CALENDAR_WRITE_DESIGN.md`.
The first Contacts write design gate is documented in `docs/V1_14_CONTACTS_WRITE_DESIGN.md`.
The first Notes write design gate is documented in `docs/V1_15_NOTES_WRITE_DESIGN.md`.
The first Mail draft write design gate is documented in `docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md`.
The first Photos import write design gate is documented in `docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md`.
The first iCloud Drive append-text write design gate is documented in `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`.
The first Notes append-text write design gate is documented in `docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md`.
The first Notes attachment export design gate is documented in `docs/V1_20_NOTES_ATTACHMENT_EXPORT.md`.
The first Mail attachment export design gate is documented in `docs/V1_21_MAIL_ATTACHMENT_EXPORT.md`.
The first Messages attachment export design gate is documented in `docs/V1_22_MESSAGES_ATTACHMENT_EXPORT.md`.
The Messages attributed-body fallback design gate is documented in `docs/V1_23_MESSAGES_ATTRIBUTED_BODY.md`.
The first Messages send-text write design gate is documented in `docs/V1_24_MESSAGES_SEND_TEXT_WRITE_DESIGN.md`.
The Safari bookmarks and Reading List read gate is documented in `docs/V1_25_SAFARI_BOOKMARKS.md`.
The publication checklist is documented in `docs/PUBLISHING.md`.
The public install guide is documented in `docs/INSTALL.md`.
Synthetic sample outputs are documented in `docs/SAMPLE_OUTPUTS.md`.
macOS support notes are documented in `docs/MACOS_SUPPORT.md`.
Security reporting is documented in `SECURITY.md`.
Contribution rules are documented in `CONTRIBUTING.md`.
Release notes are documented in `CHANGELOG.md`.
Public release file boundaries are documented in `docs/PUBLIC_RELEASE_MANIFEST.md`.

## Quick Checks

```bash
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
uv run python scripts/audit_write_design_gates.py
uv run python scripts/audit_surface_contract.py
uv run python scripts/audit_release_readiness.py --json
uv run python scripts/generate_release_receipt.py --json
uv run python scripts/render_mcp_client_config.py --client claude-code
uv run python scripts/render_mcp_client_config.py --client cursor
uv run python scripts/render_mcp_client_config.py --client openclaw --server-only --compact
uv run python scripts/build_public_release_tree.py --dest /tmp/local-apple-data-public --force
uv run python scripts/prepare_public_git_checkout.py --dest /tmp/local-apple-data-public-git --force --init-git --commit
uv run python scripts/verify_runtime.py
uv run local-apple-data health --json
uv run local-apple-data mail search --json --query '<subject text>'
uv run local-apple-data mail content --json --handle '<mail:message:v2:...>' --max-chars 4000
uv run local-apple-data mail attachments --json --handle '<mail:message:v2:...>'
uv run local-apple-data mail export-attachment --json --message-handle '<mail:message:v2:...>' --handle '<mail:attachment:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data messages search --json --query '<chat display name text>'
uv run local-apple-data messages get --json --handle '<messages:chat:v1:...>' --max-messages 25 --max-chars 4000
uv run local-apple-data messages attachments --json --handle '<messages:chat:v1:...>'
uv run local-apple-data messages export-attachment --json --chat-handle '<messages:chat:v1:...>' --handle '<messages:attachment:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data hide-my-email search --json --query '<specific alias substring>'
uv run local-apple-data hide-my-email get --json --handle '<hide_my_email:alias:v1:...>'
uv run local-apple-data voice-memos search --json --query '<recording title text>'
uv run local-apple-data voice-memos get --json --handle '<voice_memos:recording:v1:...>' --max-chars 4000
uv run local-apple-data voice-memos export --json --handle '<voice_memos:recording:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data safari search --json --query '<bookmark title or URL text>'
uv run local-apple-data safari get --json --handle '<safari:item:v1:...>'
uv run local-apple-data shortcuts search --json --query '<shortcut or folder name text>'
uv run local-apple-data shortcuts get --json --handle '<shortcuts:item:v1:...>'
uv run local-apple-data notes search --json --query '<title or snippet text>'
uv run local-apple-data notes content --json --handle '<notes:note:v2:...>' --max-chars 4000 --offset 0
uv run local-apple-data notes attachments --json --handle '<notes:note:v2:...>'
uv run local-apple-data notes export-attachment --json --handle '<notes:attachment:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data notes plan --json --operation create --title '<note title>' --body-text '<plain text>'
uv run local-apple-data notes apply --json --operation create --title '<note title>' --body-text '<plain text>' --approval-token '<notes-apply:v1:...>' --confirm-apply
uv run local-apple-data notes plan --json --operation append-text --handle '<notes:note:v2:...>' --expected-current-sha256 '<sha256-from-content>' --body-text '<text>'
uv run local-apple-data notes apply --json --operation append-text --handle '<notes:note:v2:...>' --expected-current-sha256 '<sha256-from-content>' --body-text '<text>' --approval-token '<notes-apply:v1:...>' --confirm-apply
uv run local-apple-data icloud-drive search --json --query '<filename text>'
uv run local-apple-data icloud-drive content --json --handle '<icloud:file:v1:...>' --max-chars 4000
uv run local-apple-data icloud-drive plan --json --operation create-text --parent-handle '<icloud:file:v1:...>' --filename '<new-file.md>' --content-text '<text>'
uv run local-apple-data icloud-drive apply --json --operation create-text --parent-handle '<icloud:file:v1:...>' --filename '<new-file.md>' --content-text '<text>' --approval-token '<icloud-drive-apply:v1:...>' --confirm-apply
uv run local-apple-data icloud-drive plan --json --operation append-text --handle '<icloud:file:v1:...>' --expected-current-sha256 '<sha256-from-content>' --content-text '<text>'
uv run local-apple-data icloud-drive apply --json --operation append-text --handle '<icloud:file:v1:...>' --expected-current-sha256 '<sha256-from-content>' --content-text '<text>' --approval-token '<icloud-drive-apply:v1:...>' --confirm-apply
uv run local-apple-data calendar search --json --query '<event title text>'
uv run local-apple-data calendar get --json --handle '<calendar:event:v1:...>' --max-chars 4000
uv run local-apple-data calendar plan --json --operation create --title '<event title>' --calendar-title '<target calendar>' --start-date '<ISO timestamp>' --end-date '<ISO timestamp>'
uv run local-apple-data calendar apply --json --operation create --title '<event title>' --calendar-title '<target calendar>' --start-date '<ISO timestamp>' --end-date '<ISO timestamp>' --approval-token '<calendar-apply:v1:...>' --confirm-apply
uv run local-apple-data contacts search --json --query '<name or organization text>'
uv run local-apple-data contacts get --json --handle '<contacts:contact:v1:...>'
uv run local-apple-data contacts plan --json --operation create --contact-type person --given-name '<given>' --family-name '<family>' --email 'work=<email>'
uv run local-apple-data contacts apply --json --operation create --contact-type person --given-name '<given>' --family-name '<family>' --email 'work=<email>' --approval-token '<contacts-apply:v1:...>' --confirm-apply
uv run local-apple-data photos search --json --query '<original filename text>'
uv run local-apple-data photos get --json --handle '<photos:asset:v1:...>'
uv run local-apple-data photos export --json --handle '<photos:asset:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data photos plan --json --operation import --source-file /path/to/local-image.jpg
uv run local-apple-data photos apply --json --operation import --source-file /path/to/local-image.jpg --approval-token '<photos-apply:v1:...>' --confirm-apply
uv run local-apple-data reminders due --json --days 14
uv run local-apple-data reminders eventkit-search --json --query '<reminder title text>'
uv run local-apple-data reminders content --json --handle '<reminders:reminder:eventkit:v1:...>' --max-chars 4000
uv run local-apple-data reminders plan --json --operation create --title '<new reminder title>' --list-name '<target list name>' --due-date '<YYYY-MM-DD>'
uv run local-apple-data reminders apply --json --operation create --title '<new reminder title>' --list-name '<target list name>' --due-date '<YYYY-MM-DD>' --approval-token '<reminders-apply:v1:...>' --confirm-apply
```

Run the plugin and skill validator scripts too when those local validator helpers are installed in the current Codex skills cache.

The installed-plugin consistency check for a configured local operator setup is:

```bash
cd /absolute/path/to/local-apple-data && uv run python scripts/verify_cross_agent_sync.py
```

If a Cursor project or global MCP config should be treated as mandatory, verify it explicitly:

```bash
uv run python scripts/verify_cross_agent_sync.py --require-cursor
uv run python scripts/verify_cross_agent_sync.py --cursor-config .cursor/mcp.json --require-cursor
```

The health command reports redacted local readiness only. Search commands may print local metadata such as subjects, Messages chat display names, masked inferred Hide My Email alias previews, Voice Memo titles, Safari bookmark titles/domains, note titles/snippets, calendar event titles, contact names/organizations, Photos filenames, iCloud Drive filenames, and reminder titles, so run them only for an intentional user-requested workflow. The Mail, Messages, inferred Hide My Email, Voice Memos, Safari, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive content/detail/export commands may print bounded local text, exact selected alias or URL detail, asset/resource metadata, or caller-selected export paths and should be run only with an exact handle selected from metadata output.

Search handles are opaque and are generated from a local secret under the plugin state directory. They are not reusable credentials and are not logged. Mail search results include a best-effort metadata-only `content_status` hint of `available`, `unavailable`, or `unknown`; the hint checks local content-file availability without reading message bodies. Hide My Email results are inferred from local Mail address metadata and set `authoritative_inventory:false`; they are not an iCloud account inventory or management API. Safari search returns titles and URL metadata such as domain/scheme/query presence, not full URLs. Mail, Messages, inferred Hide My Email, Voice Memos, Safari, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive retrieval reject raw row IDs, older handle formats, mailbox refs, direct paths, raw framework identifiers, raw Hide My Email identifiers, and arbitrary inputs.

## Safety Model

See `docs/PRIVACY_MODEL.md`.

See also `docs/THREAT_MODEL.md` and `docs/TESTING.md`.

For the capability matrix, see `docs/CAPABILITY_MATRIX.md`.
For ecosystem research and architecture comparison, see `docs/ECOSYSTEM_REVIEW.md`.
For future write gates, see `docs/MUTATION_GATES.md`.
For the future write roadmap, see `docs/WRITE_TOOL_ROADMAP.md`.
For the first Reminders write design gate, see `docs/V1_11_REMINDERS_WRITE_DESIGN.md`.
For public release readiness, see `docs/PUBLISHING.md`.
For installation, see `docs/INSTALL.md`.
For synthetic examples, see `docs/SAMPLE_OUTPUTS.md`.
For macOS support, see `docs/MACOS_SUPPORT.md`.
For security reporting, see `SECURITY.md`.
For public release file boundaries, see `docs/PUBLIC_RELEASE_MANIFEST.md`.

For the implemented Mail content phase, see `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md` and `docs/V1_1_KICKOFF_PROMPT.md`.
For the implemented Notes/iCloud Drive content phases and the broader Apple-data roadmap, see `docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md`.

For Codex, Claude Code, Cursor, and OpenClaw routing, see `docs/CROSS_AGENT_ROUTING.md`.

## Codex Plugin

See `docs/CODEX_PLUGIN.md`.

## License

MIT. See `LICENSE`.

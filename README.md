# local-apple-data

[![CI](https://github.com/BillyBunn/local-apple-data/actions/workflows/ci.yml/badge.svg)](https://github.com/BillyBunn/local-apple-data/actions/workflows/ci.yml)

Local-first Apple data access for Codex and other MCP clients.

This project provides a privacy-gated CLI and MCP server for locally synced:

- Mail.app mail, including iCloud and Gmail accounts synced locally through Mail.app
- Messages chats synced locally through Messages.app
- Inferred Hide My Email aliases observed in local Mail address metadata
- Voice Memos synced locally through Voice Memos.app
- Apple Notes
- Apple Calendar
- Apple Reminders
- Apple Contacts
- Apple Photos
- iCloud Drive local files and folders

The current release is read-only and does not use the Gmail connector, Gmail API, IMAP credentials, OAuth, app passwords, iCloud.com, browser sessions, keychain credentials, private iCloud web APIs, or any network mail service.

## Current Status

The read-only MCP, local skill/plugin packaging, exact-handle content/detail/export retrieval, and synthetic runtime verification paths are implemented for the surfaces listed below. Real-machine smoke stays schema-only unless a user intentionally requests a specific metadata search or provides/selects a specific Mail, Messages, inferred Hide My Email, Voice Memos, Notes, Calendar, Reminders, Contacts, Photos, or iCloud Drive handle for content/detail/export retrieval.

Implemented now:

- Repo guidance and privacy model
- `local-apple-data health --json` with redacted broad-surface readiness summaries, schema-only Mail/Messages/Voice Memos/Notes/Reminders checks, iCloud Drive root checks, and non-prompting access requirements for framework-backed surfaces
- `local-apple-data doctor --json` with redacted non-mutating remediation guidance
- `local-apple-data mail search/get` metadata commands
- Metadata-only `content_status` hints in Mail search results so agents can prefer locally retrievable messages before exact content calls
- `local-apple-data mail content --json --handle <mail:message:v2:...> --max-chars 4000` for exact-handle local Mail plain-text content
- `local-apple-data messages search/get` commands for local Messages chat display-name metadata and exact bounded transcripts
- `local-apple-data hide-my-email search/get` commands for inferred Hide My Email aliases observed in local Mail address metadata
- `local-apple-data voice-memos search/get/export` commands for local Voice Memos title/filename metadata, exact existing embedded transcripts, and exact-handle `.m4a` export to a caller-selected output directory
- `local-apple-data notes search/get` metadata commands
- `local-apple-data notes content --json --handle <notes:note:v2:...> --max-chars 4000 --offset 0` for exact-handle local Notes plain-text content, with `next_offset` pagination for long imported notes
- `local-apple-data icloud-drive search/get` metadata commands for local iCloud Drive items by filename
- `local-apple-data icloud-drive content --json --handle <icloud:file:v1:...> --max-chars 4000` for exact-handle local iCloud Drive text-file content
- `local-apple-data calendar search/get` commands for local Calendar events by title through EventKit
- `local-apple-data contacts search/get` commands for local Contacts by name or organization through Contacts.framework
- `local-apple-data photos search/get/export` commands for local Photos asset metadata by original filename, exact asset/resource metadata, and exact-handle asset export to a caller-selected output directory through PhotoKit
- `local-apple-data reminders search/due` metadata commands
- `local-apple-data reminders eventkit-search` for local Reminders title metadata through EventKit
- `local-apple-data reminders content --json --handle <reminders:reminder:eventkit:v1:...> --max-chars 4000` for exact-handle local Reminder notes
- Highest-version Mail store discovery without exposing raw local store paths in normal output
- `local-apple-data-mcp` stdio MCP server with read-only tools
- MCP runner script that avoids package builds during normal plugin startup
- Codex skill under `skills/local-apple-data/`
- Local plugin manifest under `.codex-plugin/plugin.json`
- Bundled MCP config under `.mcp.json`
- Redacted command event logging
- Opaque signed handles for exact Mail/Messages/Voice Memos/Notes/Calendar/Contacts/Photos/Reminders/iCloud Drive metadata fetches
- Exact Mail content retrieval through the same opaque `mail:message:v2:` handles
- Exact Messages chat transcript retrieval through opaque `messages:chat:v1:` handles
- Exact inferred Hide My Email alias detail through opaque `hide_my_email:alias:v1:` handles
- Exact Voice Memos transcript retrieval through opaque `voice_memos:recording:v1:` handles when Apple-generated local transcript data is embedded in the selected `.m4a`
- Exact Voice Memos audio export through opaque `voice_memos:recording:v1:` handles to a caller-selected output directory without returning audio bytes inline
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
- Surface-contract auditor under `scripts/audit_surface_contract.py` so MCP tools, CLI commands, health surfaces, access requirements, and the capability matrix stay aligned
- MCP client config renderer for generic stdio, Claude Code, Cursor, and OpenClaw under `scripts/render_mcp_client_config.py`
- Public release tree builder under `scripts/build_public_release_tree.py`
- Public git checkout preparer under `scripts/prepare_public_git_checkout.py`, including optional initial local commit creation
- Path-redacted release receipt generator under `scripts/generate_release_receipt.py`
- Synthetic unit and CLI tests
- Local git repo on branch `main`

Deferred:

- Any mutating tools
- Calendar/Reminder/Contacts/Photos/Messages/Voice Memos mutation, authoritative Hide My Email inventory, Hide My Email creation/deactivation/deletion, private iCloud web/API access, browser/keychain credential access, generated Voice Memos transcription, broad content search, broad Messages text search, broad Voice Memos transcript search, attachments, Contact notes/image data, unsupported/binary iCloud Drive content extraction, and durable content caches

The v1.1 design gate for exact-handle Mail content retrieval is documented in `docs/V1_1_CONTENT_RETRIEVAL_PLAN.md`.
The v1.2 Notes content and broader local Apple data expansion plan is documented in `docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md`.
The public capability matrix is documented in `docs/CAPABILITY_MATRIX.md`.
The ecosystem research and architecture comparison is documented in `docs/ECOSYSTEM_REVIEW.md`.
The write/mutation approval gates are documented in `docs/MUTATION_GATES.md`.
The future write-tool roadmap is documented in `docs/WRITE_TOOL_ROADMAP.md`.
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
uv run python -m compileall src tests
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
uv run python scripts/audit_mutation_gates.py
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
uv run local-apple-data messages search --json --query '<chat display name text>'
uv run local-apple-data messages get --json --handle '<messages:chat:v1:...>' --max-messages 25 --max-chars 4000
uv run local-apple-data hide-my-email search --json --query '<specific alias substring>'
uv run local-apple-data hide-my-email get --json --handle '<hide_my_email:alias:v1:...>'
uv run local-apple-data voice-memos search --json --query '<recording title text>'
uv run local-apple-data voice-memos get --json --handle '<voice_memos:recording:v1:...>' --max-chars 4000
uv run local-apple-data voice-memos export --json --handle '<voice_memos:recording:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data notes search --json --query '<title or snippet text>'
uv run local-apple-data notes content --json --handle '<notes:note:v2:...>' --max-chars 4000 --offset 0
uv run local-apple-data icloud-drive search --json --query '<filename text>'
uv run local-apple-data icloud-drive content --json --handle '<icloud:file:v1:...>' --max-chars 4000
uv run local-apple-data calendar search --json --query '<event title text>'
uv run local-apple-data calendar get --json --handle '<calendar:event:v1:...>' --max-chars 4000
uv run local-apple-data contacts search --json --query '<name or organization text>'
uv run local-apple-data contacts get --json --handle '<contacts:contact:v1:...>'
uv run local-apple-data photos search --json --query '<original filename text>'
uv run local-apple-data photos get --json --handle '<photos:asset:v1:...>'
uv run local-apple-data photos export --json --handle '<photos:asset:v1:...>' --output-dir /tmp/local-apple-data-exports
uv run local-apple-data reminders due --json --days 14
uv run local-apple-data reminders eventkit-search --json --query '<reminder title text>'
uv run local-apple-data reminders content --json --handle '<reminders:reminder:eventkit:v1:...>' --max-chars 4000
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

The health command reports redacted local readiness only. Search commands may print local metadata such as subjects, Messages chat display names, masked inferred Hide My Email alias previews, Voice Memo titles, note titles/snippets, calendar event titles, contact names/organizations, Photos filenames, iCloud Drive filenames, and reminder titles, so run them only for an intentional user-requested workflow. The Mail, Messages, inferred Hide My Email, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive content/detail/export commands may print bounded local text, exact selected alias detail, asset/resource metadata, or caller-selected export paths and should be run only with an exact handle selected from metadata output.

Search handles are opaque and are generated from a local secret under the plugin state directory. They are not reusable credentials and are not logged. Mail search results include a best-effort metadata-only `content_status` hint of `available`, `unavailable`, or `unknown`; the hint checks local content-file availability without reading message bodies. Hide My Email results are inferred from local Mail address metadata and set `authoritative_inventory:false`; they are not an iCloud account inventory or management API. Mail, Messages, inferred Hide My Email, Voice Memos, Notes, Calendar, Contacts, Photos, Reminders, and iCloud Drive retrieval reject raw row IDs, older handle formats, mailbox refs, direct paths, raw framework identifiers, raw Hide My Email identifiers, and arbitrary inputs.

## Safety Model

See `docs/PRIVACY_MODEL.md`.

See also `docs/THREAT_MODEL.md` and `docs/TESTING.md`.

For the capability matrix, see `docs/CAPABILITY_MATRIX.md`.
For ecosystem research and architecture comparison, see `docs/ECOSYSTEM_REVIEW.md`.
For future write gates, see `docs/MUTATION_GATES.md`.
For the future write roadmap, see `docs/WRITE_TOOL_ROADMAP.md`.
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

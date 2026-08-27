# Install

This project runs as a local CLI and stdio MCP server. The same runner script can be registered with Codex, Claude Code, Cursor, OpenClaw, and other MCP clients that support local stdio servers.

## Requirements

- macOS with locally synced Apple data.
- Python 3.11 or newer.
- `uv`.
- Xcode command line tools or another Swift toolchain for helper typechecks.
- `sqlite3`.
- macOS permissions for the surfaces you intend to use.

Some surfaces may need Full Disk Access, Automation, Calendar, Contacts, Photos, or Reminders permission. Safari bookmark/Reading List/folder metadata reads use the local Safari bookmarks file and may need Full Disk Access. Books metadata and selected-book annotation reads use local Apple Books stores and may need Full Disk Access. Podcasts metadata reads use the local Apple Podcasts store and may need Full Disk Access. Music metadata reads use bounded Music.app automation and may need Automation permission. TV metadata reads use bounded TV.app automation and may need Automation permission. Freeform board/folder/selected-folder board/child-folder metadata reads use the local Freeform store and may need Full Disk Access. Shortcuts metadata/selected-folder shortcut metadata reads require Apple's local `shortcuts` CLI but health checks only CLI availability and do not list shortcuts. Permission failures should return structured warning codes rather than raw system errors.

Calendar/Reminders (EventKit), Contacts (Contacts.framework), and Photos
(PhotoKit) access runs through signed helper apps. Their bundle identifiers
default to `com.local-apple-data.eventkit-helper`,
`com.local-apple-data.contacts-helper`, and
`com.local-apple-data.photos-helper`. EventKit and Photos identities are
operator-configurable to preserve existing grants across upgrades; Contacts
uses one fixed helper identity. See `docs/MACOS_SUPPORT.md` for details.

For clients that launch from an installed plugin cache, put persistent
machine-local assignments in
`~/Library/Application Support/local-apple-data/.env.operator` and restrict the
file to the current user (`0600`). The CLI and MCP server parse only the two
allowlisted helper-ID keys from that file; shell syntax and other variables are
rejected. A checkout-local `.env.local` must be equally private. The Python
CLI/MCP entrypoint gives it precedence. `LOCAL_APPLE_DATA_OPERATOR_ENV_FILE`
can select another absolute file and fails closed if it is missing or unsafe.
Neither operator file belongs in the plugin package.
An already-set helper-ID process environment variable remains the
highest-precedence explicit override.

macOS only shows these framework consent prompts to a stably signed helper.
Run each needed request-access command once in a Terminal from the GUI login
session to complete one-time setup:

```
uv run local-apple-data calendar request-access --json
uv run local-apple-data reminders request-access --json
uv run local-apple-data contacts request-access --json
uv run local-apple-data photos request-access --json
```

The first run provisions a local self-signed `Local Apple Data Signing`
certificate in your login keychain, rebuilds the helper stably signed, and
prompts: click **Always Allow** on the keychain dialog, then allow the requested
framework access. Choose full access for Calendar, Reminders, and Photos; the
Contacts helper also requires authorization for its bounded search and CRUD
surface. Set `LOCAL_APPLE_DATA_SIGNING_IDENTITY` to use your own certificate
(for example an Apple Development identity) instead. Without a stable identity
the helpers fall back to ad-hoc signing for non-prompting operation, but the
explicit prompt command fails closed. See `docs/MACOS_SUPPORT.md` for the full
walkthrough.

Apple's `com.apple.developer.contacts.notes` entitlement requires a suitable
provisioning profile and is not attached to the locally self-signed Contacts
helper. Ordinary Contacts search and supported non-note operations remain
available; note reads/mutations fail closed, and archive export omits notes.

## From Source

```bash
git clone <repo-url> local-apple-data
cd local-apple-data
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/redaction_scan.py .
uv run python scripts/verify_runtime.py
uv run local-apple-data health --json
```

`health` is schema/readiness oriented. It should not print private content, raw rows, credentials, or local store paths.

## Generic MCP Stdio

Use the runner script as the MCP command:

```bash
uv run python scripts/render_mcp_client_config.py --client generic
```

```json
{
  "mcpServers": {
    "local-apple-data": {
      "command": "/absolute/path/to/local-apple-data/scripts/run_mcp_server.sh",
      "args": []
    }
  }
}
```

If your client supports a working directory field, set it to the project root:

```json
{
  "cwd": "/absolute/path/to/local-apple-data"
}
```

## Codex

The repo includes a Codex plugin manifest at `.codex-plugin/plugin.json`, a bundled `.mcp.json`, and a skill under `skills/local-apple-data/`.

For local development with a configured personal marketplace, reinstall with:

```bash
uv run python scripts/sync_personal_plugin.py --json
codex plugin add local-apple-data@personal
```

Then verify the installed cache:

```bash
cd /absolute/path/to/codex-plugin-cache/personal/local-apple-data/<installed-version>
uv run python scripts/verify_runtime.py
cd /absolute/path/to/local-apple-data
uv run python scripts/audit_plugin_artifact_hygiene.py --json
```

## Claude Code

Claude Code supports project `.mcp.json` files with local stdio `command` and `args` entries. Generate a project config from the repo root:

Project-local example:

```bash
uv run python scripts/render_mcp_client_config.py --client claude-code > .mcp.json
```

```json
{
  "mcpServers": {
    "local-apple-data": {
      "command": "/absolute/path/to/local-apple-data/scripts/run_mcp_server.sh",
      "args": []
    }
  }
}
```

For a local or user-scoped Claude Code entry, render the server object and pass it to `claude mcp add-json`:

```bash
claude mcp add-json local-apple-data \
  "$(uv run python scripts/render_mcp_client_config.py --client claude-code --server-only --compact)"
```

Allow the specific MCP tools according to your Claude Code permissions model.

## Cursor

Cursor-style MCP configuration uses an `mcpServers` object in a project `.cursor/mcp.json` file or global `~/.cursor/mcp.json` file. Project config is the better default when the Apple data tools should only be available for one workspace.

Project example:

```bash
mkdir -p .cursor
uv run python scripts/render_mcp_client_config.py --client cursor > .cursor/mcp.json
```

```json
{
  "mcpServers": {
    "local-apple-data": {
      "type": "stdio",
      "command": "${workspaceFolder}/scripts/run_mcp_server.sh",
      "args": []
    }
  }
}
```

For a global Cursor config, use an absolute command:

```bash
uv run python scripts/render_mcp_client_config.py --client cursor --absolute > ~/.cursor/mcp.json
```

To verify a Cursor config with the repo's local sync verifier:

```bash
uv run python scripts/verify_cross_agent_sync.py --cursor-config .cursor/mcp.json --require-cursor
```

## OpenClaw

OpenClaw can save a local stdio server definition and then probe it. Generate the server object and pass it to `openclaw mcp set`:

```bash
openclaw mcp set local-apple-data \
  "$(uv run python scripts/render_mcp_client_config.py --client openclaw --server-only --compact)"

openclaw mcp doctor local-apple-data --probe
```

Use tool filters if a client should remain strictly read-only. The current release exposes 14 approved MCP write tools: `reminders_apply_change`, `reminders_apply_list_change`, `icloud_drive_apply_change`, `filesystem_apply_change`, `calendar_apply_change`, `calendar_apply_calendar_change`, `contacts_apply_change`, `notes_apply_change`, `mail_apply_change`, `mail_apply_mailbox_change`, `mail_apply_cleanup`, `photos_apply_change`, `messages_apply_change`, and `shortcuts_apply_run`. Reminders list management supports exact create/rename/empty-delete/same-source migrate-delete with exact source/target list handles, empty-list proof for rename/delete, and bounded same-source migration plus target-count/absence proof for migrate-delete. Calendar calendar management is limited to synthetic `LAD-TEST-*` create/rename/delete; delete requires an event-only non-default writable empty synthetic calendar plus absence proof. Mail draft/send/reply/reply-all/forward may use exact sender selection and bounded caller-selected local file attachments, and Mail triage bulk mode requires unique exact message handles capped at 20. Static apply tools are annotated destructive when they can send, delete, trash, move, rename, replace content, append text, import media, or mutate external app state after the matching plan token and explicit confirmation.

## First Smoke

After wiring a client, run a readiness check first:

```bash
uv run local-apple-data health --json
```

Then use narrow metadata searches before any exact content/detail calls. Do not fabricate handles; exact tools only accept handles returned by the matching search flow.

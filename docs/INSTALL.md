# Install

This project runs as a local CLI and stdio MCP server. The same runner script can be registered with Codex, Claude Code, Cursor, OpenClaw, and other MCP clients that support local stdio servers.

## Requirements

- macOS with locally synced Apple data.
- Python 3.11 or newer.
- `uv`.
- Xcode command line tools or another Swift toolchain for helper typechecks.
- `sqlite3`.
- macOS permissions for the surfaces you intend to use.

Some surfaces may need Full Disk Access, Automation, Calendar, Contacts, Photos, or Reminders permission. Safari bookmark/Reading List reads use the local Safari bookmarks file and may need Full Disk Access. Books metadata and selected-book annotation reads use local Apple Books stores and may need Full Disk Access. Podcasts metadata reads use the local Apple Podcasts store and may need Full Disk Access. Music metadata reads use bounded Music.app automation and may need Automation permission. Shortcuts metadata reads require Apple's local `shortcuts` CLI but health checks only CLI availability and do not list shortcuts. Permission failures should return structured warning codes rather than raw system errors.

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
codex plugin add local-apple-data@personal
```

Then verify the installed cache:

```bash
cd /absolute/path/to/installed/local-apple-data
uv run python scripts/verify_runtime.py
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

Use tool filters if a client should remain strictly read-only. The current release exposes eight approved write tools: `reminders_apply_change` for Reminders create/complete/due-date apply, `icloud_drive_apply_change` for iCloud Drive create/append-text apply, `calendar_apply_change` for Calendar create-event apply, `contacts_apply_change` for Contacts create-contact apply, `notes_apply_change` for Notes create/append-text apply, `mail_apply_change` for Mail create-draft apply, `photos_apply_change` for Photos import apply, and `messages_apply_change` for Messages send-text apply after plan approval-token and explicit-confirmation checks.

## First Smoke

After wiring a client, run a readiness check first:

```bash
uv run local-apple-data health --json
```

Then use narrow metadata searches before any exact content/detail calls. Do not fabricate handles; exact tools only accept handles returned by the matching search flow.

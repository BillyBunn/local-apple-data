# Cowork / Claude Code integration

Register the `local-apple-data` MCP server with **Cowork** (the Claude desktop
app's local agent mode) and **Claude Code**, so their agents can call the
`mcp__local-apple-data__*` tools the same way OpenClaw does.

## How Cowork discovers MCP servers

Cowork's local agent mode runs Claude Code underneath. Both read their **global**
MCP server list from:

```
~/.claude.json   →   .mcpServers   (stdio servers)
```

This is a *different* surface from Cowork's **plugins / connectors** marketplace
(`list_plugins` / `list_connectors`). Those being empty does **not** mean MCP
servers are unavailable — stdio MCP servers registered in `~/.claude.json` are
exposed to agents as `mcp__<server>__<tool>` regardless of the marketplace.

> Note: the legacy `~/Library/Application Support/Claude/claude_desktop_config.json`
> (classic Claude Desktop `mcpServers`) is **not** used by Cowork local agent
> mode on this setup — it holds only `coworkUserFilesPath` / `preferences`.
> The authoritative file is `~/.claude.json`.

## Current status

As of 2026-08-26 the entry is **already present** in `~/.claude.json` and the
Claude Code/Cowork route is live. That receipt is date-stamped, not a durable
assumption: after any recovery, reset, launcher, plugin, or routing change, rerun
`uv run python scripts/verify_cross_agent_sync.py` and confirm
`apple_data_health` returns `status: ok`. The installer below is therefore
primarily a **reproducibility / recovery** tool: re-apply the registration on a
new machine, or repair it if the config is reset.

## Install

```bash
# Quit Cowork / Claude Code first (they may overwrite ~/.claude.json on exit).
integrations/cowork/install.sh --dry-run   # preview; writes nothing
integrations/cowork/install.sh             # apply (idempotent)
```

The script:

- writes only the `mcpServers["local-apple-data"]` key — every other key in
  `~/.claude.json` is preserved untouched;
- backs up `~/.claude.json` to `~/.claude.json.bak.YYYYMMDD-HHMMSS` before any write;
- writes atomically (temp file + `mv`) and validates JSON before swapping;
- is idempotent — if the entry already matches canonical it writes nothing;
- embeds the **absolute launcher path for this checkout**, so it works from
  wherever the repo lives.

Override the target for testing with `CLAUDE_CONFIG=/path/to/test.json`.

## The registered entry

See [`mcp-entry.json`](./mcp-entry.json) for the canonical shape
(`<REPO_ROOT>` is filled in with the absolute path at install time):

```json
{
  "type": "stdio",
  "command": "<REPO_ROOT>/scripts/run_mcp_server.sh",
  "args": [],
  "env": {}
}
```

This mirrors the OpenClaw registration in `~/.openclaw/openclaw.json` under
`mcp.servers["local-apple-data"]`.

## Verify (after restarting Cowork / Claude Code)

1. **Tool surface** — in a fresh Cowork/Claude Code session, the
   `mcp__local-apple-data__*` tools should be available (e.g.
   `mcp__local-apple-data__apple_data_health`).
2. **Live readiness** — call `apple_data_health`; expect `"status":"ok"` with
   stores `present`/`readable`. This is metadata-only and non-mutating.
3. **CLI cross-check** — `claude mcp list` (Claude Code) should list
   `local-apple-data` if the CLI is installed.

If the tools are absent after restart, run `install.sh --dry-run` to confirm the
entry is present and points at an existing, executable launcher.

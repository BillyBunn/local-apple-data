# V1.160 Notes Folder Tree Metadata

## Goal

Allow agents to browse bounded Notes child-folder structure from one selected
folder without exposing note content, snippets, attachment bytes, raw database
IDs, account identifiers, paths, or mutation capability.

## Surface

- MCP: `notes_list_folder_tree`
- CLI: `local-apple-data notes folder-tree --handle <notes:folder:v1:...>`
- Adapter: `list_notes_folder_tree(handle, depth=2, limit=50)`

## Access Rules

- Input must be one opaque `notes:folder:v1:` handle returned by
  `notes_search_folders` / `local-apple-data notes folders`.
- Raw folder IDs, legacy handles, note handles, database IDs, fabricated
  handles, and smart-folder roots are rejected.
- Depth is clamped to 1 through 3.
- Descendant count is clamped to 1 through 50.
- Output returns only folder metadata plus `parent_handle` and `tree_depth`.
- Output never includes notes, note bodies, snippets, attachment bytes, raw
  folder IDs, account identifiers, paths, or AppleScript output.

## Result Shape

```json
{
  "status": "ok",
  "source": "notes",
  "query": {
    "scope": "selected_folder_tree",
    "limit": 50,
    "max_depth": 2,
    "recursive": true
  },
  "folder": {"handle": "notes:folder:v1:..."},
  "results": [
    {
      "handle": "notes:folder:v1:...",
      "parent_handle": "notes:folder:v1:...",
      "tree_depth": 1,
      "folder_content_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "folder_content_returned": false,
  "note_content_returned": false,
  "raw_identifier_returned": false
}
```

## Verification

Minimum source checks:

```bash
uv run pytest tests/test_notes_adapter.py tests/test_cli_metadata.py tests/test_mcp_server.py tests/test_surface_contract_audit.py
uv run pytest
uv run python -m compileall -q src tests scripts
uv run python scripts/verify_runtime.py --json
uv run python scripts/audit_surface_contract.py --json
uv run python scripts/audit_mutation_gates.py --json
uv run python scripts/redaction_scan.py --json .
uv run python scripts/public_release_scan.py --json
```

Minimum packaging checks:

```bash
uv run python scripts/sync_personal_plugin.py --json
codex plugin add local-apple-data@personal
cd <installed-plugin-cache> && UV_PROJECT_ENVIRONMENT=<installed-venv> uv run pytest -q
cd <installed-plugin-cache> && UV_PROJECT_ENVIRONMENT=<installed-venv> uv run python scripts/verify_runtime.py --json
cd <source-checkout> && uv run python scripts/verify_cross_agent_sync.py
cd <source-checkout> && uv run python scripts/audit_plugin_artifact_hygiene.py --json
```

## Future Work

Note listing from folder trees, folder-context attachment export, root/default
account folder creation, root/non-empty/cross-account folder moves, rich text,
attachment mutation, Recently Deleted management, and bulk operations remain
blocked until separate design gates define exact scopes and deterministic proof.

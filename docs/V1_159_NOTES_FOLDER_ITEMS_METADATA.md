# v1.159 Notes Folder Items Metadata

## Objective

Add a read-only exact selected-folder item metadata surface for Apple Notes
without returning note bodies, snippets, attachment bytes, raw folder IDs,
account identifiers, recursive folder dumps, or using network/iCloud/web paths.

## Supported Surface

- CLI: `local-apple-data notes folder-items`
- MCP: `notes_list_folder_items`

The caller must provide one opaque `notes:folder:v1:` handle returned by
`local-apple-data notes folders` / `notes_search_folders`. The adapter resolves
that handle locally, rejects fabricated or raw-ID handles, rejects smart folders,
and returns capped direct children only:

- direct child folders as `notes:folder:v1:` metadata
- direct notes as `notes:note:v2:` metadata

The output does not include note bodies, snippets, attachment bytes, raw primary
keys, raw folder IDs, account identifiers, local paths, or recursive
descendants.

## Boundaries

This phase does not add:

- broad or empty Notes folder dumps
- recursive folder traversal
- note body retrieval from folder listing
- attachment export from folder listing
- raw folder IDs, account IDs, or paths
- folder creation, rename, delete, move, or note mutation beyond existing gates
- iCloud.com, private iCloud APIs, browser sessions, keychain access, or network fallback

## Safety Properties

- Exact `notes:folder:v1:` handles are required.
- Limit is clamped to a bounded range.
- Smart folders fail closed.
- Direct child folders are listed before direct notes under the same combined cap.
- Note metadata deliberately omits snippets because folder browsing is not a
  text search path.
- Automated tests use synthetic SQLite fixtures only.
- Runtime smoke uses a synthetic Notes database and proves no content,
  snippets, or raw IDs return.

## Verification

Required before publication:

```bash
uv run pytest tests/test_notes_adapter.py tests/test_cli_metadata.py tests/test_mcp_server.py tests/test_surface_contract_audit.py
uv run pytest
uv run python -m compileall -q src tests scripts
uv run python scripts/verify_runtime.py --json
uv run python scripts/audit_surface_contract.py --json
uv run python scripts/redaction_scan.py --json .
uv run python scripts/public_release_scan.py --json
uv run python scripts/sync_personal_plugin.py --json
codex plugin add local-apple-data@personal
cd <installed-plugin-cache> && UV_PROJECT_ENVIRONMENT=<installed-venv> uv run pytest -q
cd <installed-plugin-cache> && UV_PROJECT_ENVIRONMENT=<installed-venv> uv run python scripts/verify_runtime.py --json
cd <source-checkout> && uv run python scripts/verify_cross_agent_sync.py
cd <source-checkout> && uv run python scripts/audit_plugin_artifact_hygiene.py --json
```

## Future Work

Recursive Notes folder traversal, broad folder dumps, raw folder/account
identifier exposure, folder content export, and attachment export from folder
context remain blocked until separate design gates define exact scopes,
non-disclosure rules, and deterministic synthetic proof.

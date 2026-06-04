# v1.26 Shortcuts Metadata

## Objective

Add a read-only Apple Shortcuts metadata surface through Apple's local `shortcuts` command-line interface without running, opening, signing, exporting, or inspecting shortcut bodies.

## Supported Surface

- CLI: `local-apple-data shortcuts search`
- CLI: `local-apple-data shortcuts get`
- MCP: `shortcuts_search`
- MCP: `shortcuts_get_item`

Search calls `shortcuts list --show-identifiers` and `shortcuts list --folders --show-identifiers`, requires a specific query, and returns bounded shortcut/folder name metadata only. Raw Shortcuts identifiers are used only for stable opaque handle generation and are not returned in output.

Exact get requires an opaque `shortcuts:item:v1:` handle from search output and returns the selected shortcut or folder metadata. It does not return a shortcut body, action graph, URL scheme, source path, icon, color, or identifier.

## Boundaries

This phase does not add:

- Shortcut run/open/view/sign/export
- Shortcut body/action graph reads
- Raw shortcut identifiers in output
- Dynamic per-shortcut run tools
- Folder-scoped handles
- Shortcuts SQLite scraping
- Shortcut creation, update, delete, duplication, import, signing, or mutation
- Network validation, iCloud.com, private iCloud APIs, browser sessions, or keychain access

## Safety Properties

- Health checks only CLI availability and never lists real shortcuts.
- Search rejects empty and broad queries.
- Search output contains only names, kind, opaque handles, and identifier-presence booleans.
- Exact get is handle-bound to the same global metadata flow as search.
- All tests use synthetic runner output; runtime smoke uses a synthetic runner and does not list real user shortcuts.

## Verification

Required before publication:

```bash
uv run pytest tests/test_shortcuts_adapter.py tests/test_cli_shortcuts.py tests/test_mcp_server.py tests/test_health.py tests/test_surface_contract_audit.py
uv run pytest
uv run python -m compileall src tests scripts
uv run python scripts/verify_runtime.py
uv run python scripts/audit_surface_contract.py --json
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
```

## Future Work

Shortcut execution, editor opening, signing, import/export, and mutation require separate design gates because they can trigger app behavior, write files, contact Apple services, reveal automation internals, or mutate user workflows.

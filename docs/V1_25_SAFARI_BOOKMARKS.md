# v1.25 Safari Bookmarks And Reading List

Date: 2026-06-04
Status: Implemented

## Objective

Add read-only, exact-handle access to locally synced Safari bookmarks and Reading List items. This closes another iCloud-backed local Apple data surface without adding browser automation, network access, or mutation.

## Scope

Implemented:

- CLI: `local-apple-data safari search`
- CLI: `local-apple-data safari get`
- MCP: `safari_search`
- MCP: `safari_get_item`
- Health: redacted Safari bookmarks store presence/readability
- Runtime verifier: synthetic Safari plist search/get smoke

Search reads local `~/Library/Safari/Bookmarks.plist` with Python `plistlib`, requires a specific query, and returns bounded title plus URL metadata only: domain, scheme, query-presence, path depth, kind, and dates when present. Exact get requires an opaque `safari:item:v1:` handle from search output and returns the selected full URL.

## Boundaries

Out of scope:

- Safari history
- Open tabs or iCloud tabs
- Private browsing data
- Passwords, passkeys, cookies, sessions, autofill, keychain, or browser caches
- Favicons, thumbnails, page content, or network fetches
- Broad bookmark dumps
- Bookmark, Reading List, folder, or Safari profile mutation
- Safari.app UI automation

## Safety Properties

- Empty and broad/generic queries fail before reading the plist.
- Search results do not include full URLs.
- Exact detail requires a signed opaque handle.
- Handles bind to a fingerprint of the current plist contents and a per-item key.
- Raw local paths are not returned.
- Event logs contain command/status/count/warning metadata only.
- Tests use synthetic plist fixtures only.

## Verification

Required checks:

```bash
uv run pytest tests/test_safari_adapter.py tests/test_cli_safari.py tests/test_mcp_server.py tests/test_health.py tests/test_surface_contract_audit.py
uv run python -m compileall src tests scripts
uv run python scripts/verify_runtime.py
uv run python scripts/audit_surface_contract.py --json
uv run python scripts/redaction_scan.py .
uv run python scripts/public_release_scan.py
```

## Next Work

Safari history, open tabs/iCloud tabs, and bookmark mutation require separate design gates because they have broader privacy and mutation risk than selected bookmark/Reading List URL retrieval.

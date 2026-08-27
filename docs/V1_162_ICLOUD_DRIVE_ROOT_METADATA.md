# v1.162 iCloud Drive Root Metadata

Status: implemented in source, synced to the personal plugin root, installed in
Codex, verified from the installed cache, cross-agent synced, and
artifact-hygiene clean.

## Surface

- MCP: `icloud_drive_get_root()`
- CLI: `local-apple-data icloud-drive root --json`
- Adapter: `get_icloud_drive_root_metadata()`

The command returns metadata for the configured local iCloud Drive root:
opaque `icloud:file:v1:` handle, name, directory kind, modified timestamp,
depth `0`, `is_root:true`, and metadata SHA-256. It returns no raw path and no
file content.

## Safety Rules

- Root metadata is read-only.
- The root handle is allowed for `get`, `list`, `tree`, and approved parent
  targeting for create/import operations.
- The root handle is rejected as a folder rename, Trash, delete, move, or copy
  source.
- Hidden CLI `--root` overrides remain limited to synthetic tests through
  `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT=1`.
- No iCloud.com, private API, browser, keychain, network, or raw path fallback.

## Regression Proof

- Adapter tests prove root metadata returns no raw path, resolves through
  selected-folder listing, permits root as a create parent, and rejects root as a
  destructive/relocation folder source.
- CLI tests cover `icloud-drive root --json` plus root-override refusal.
- MCP tests cover `icloud_drive_get_root`.
- Runtime verifier proved direct plus MCP root metadata status, opaque root
  handle, `is_root:true`, no raw path return, and root-handle listing. The
  historical tranche landed at `tool_count:132`; current live baselines may be
  higher and must be rechecked with `scripts/verify_runtime.py`.

## Remaining Gaps

- Unbounded recursive listing, broad export, inline binary/document extraction,
  empty Trash, root mutation, and raw filesystem-path selection remain blocked.

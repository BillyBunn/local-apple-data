# v1.141 iCloud Drive Folder Listing

Status: Implemented 2026-07-01.

## Goal

Add exact selected-folder direct-child metadata listing for iCloud Drive without
recursive traversal, content reads, raw path return, or mutation.

## Approved Surface

- MCP: `icloud_drive_list_folder(handle, limit=20)`
- CLI: `local-apple-data icloud-drive list --json --handle <icloud:file:v1:...> [--limit 20]`
- Input must be one exact `icloud:file:v1:` directory handle returned by the
  iCloud Drive metadata flow.
- Output returns parent metadata, direct child metadata, `result_count`,
  warnings, and `query.recursive:false`.
- Result limit is capped at 50, and child scanning is separately capped before
  sorting so huge folders cannot force unbounded memory use. Hidden entries,
  symlinks, and package directories are skipped. File handles, fabricated
  handles, packages, and symlinks fail closed.

## Non-Goals

- No recursive folder listing.
- No folder export.
- No content text, content hash, inline bytes, or source path return.
- No broad content search.
- No package traversal.
- No non-empty or recursive folder mutation.
- No empty Trash.
- No binary/document generation or editing.

## Verification Targets

- Adapter tests cover direct-child-only behavior, result truncation, child
  scan-cap truncation, hidden/package/symlink skipping, selected-folder symlink
  race refusal, file-handle refusal, and no raw path/content return.
- CLI tests cover exact folder handles and hidden root override refusal.
- MCP tests cover exact-handle forwarding and tool inventory.
- Runtime verifier proves direct and MCP folder-list status, direct-only query
  metadata, no content return, and no raw path return.

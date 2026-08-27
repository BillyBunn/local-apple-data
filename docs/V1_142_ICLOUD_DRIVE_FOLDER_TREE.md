# v1.142 iCloud Drive Folder Tree Metadata

Status: Implemented 2026-07-01.

## Goal

Add bounded recursive metadata listing for one exact selected iCloud Drive
folder without content reads, export, raw path return, or mutation.

## Approved Surface

- MCP: `icloud_drive_list_tree(handle, depth=2, limit=50)`
- CLI: `local-apple-data icloud-drive tree --json --handle <icloud:file:v1:...> [--depth 2] [--limit 50]`
- Input must be one exact `icloud:file:v1:` directory handle returned by the
  iCloud Drive metadata flow.
- Output returns parent metadata plus descendant metadata through
  `query.max_depth`, with `query.recursive:true`, `tree_depth`, and
  `parent_handle` for each returned descendant.
- Depth is capped at 3, result count is capped at 100, total directory recursion
  is capped, and child scans are capped before sorting. Hidden entries,
  symlinks, and package directories are skipped at every level.
- Directories at `max_depth` are returned but not descended into.

## Safety Model

- The surface is read-only and metadata-only. It returns no content text, content
  hashes, inline bytes, raw source paths, raw child paths, or package contents.
- It reuses the v1.141 direct-folder listing primitive, including exact opaque
  handle validation, selected-folder no-follow open, child scan streaming,
  hidden/symlink/package filtering, and selected-path read-back checks.
- Queued child folders are bound to the metadata SHA-256 observed when the
  parent was listed. If a queued child directory is replaced before recursion,
  its children are not returned and `child_metadata_changed` is reported.
- Recursive child scanning is bounded by low tree-specific caps after the
  selected folder handle is resolved through the normal capped metadata flow.
  This is not a broad iCloud Drive dump or recursive export.

## Non-Goals

- No folder export.
- No content text, content hash, inline bytes, or source path return.
- No broad content search.
- No package traversal.
- No broad root traversal without an exact selected folder handle.
- No non-empty or recursive folder mutation.
- No empty Trash.
- No binary/document generation or editing.

## Verification Targets

- Adapter tests cover bounded recursive metadata, depth semantics, result
  truncation, total scan-cap truncation, child metadata drift refusal,
  hidden/package/symlink skipping, file-handle refusal, and no raw path/content
  return.
- CLI tests cover exact folder handles and hidden root override refusal.
- MCP tests cover exact-handle forwarding and tool inventory.
- Runtime verifier proves direct and MCP folder-tree status, recursive query
  metadata, no content return, and no raw path return.

# v1.31 Apple Freeform Metadata

## Objective

Add a read-only Apple Freeform surface for locally synced Freeform board, folder, exact selected-folder board, and exact selected-folder child-folder metadata without returning board content, board BLOBs, decoded board items, asset bytes, previews, collaboration payloads, raw identifiers, raw rows, or mutating Freeform.

Apple documents that Freeform boards can be stored in iCloud and kept up to date across a user's Apple devices. Local probing on this Mac found Freeform data under the Freeform group container with `Boards/boards.db`, `Boards/side.db`, and asset storage. The first publishable tranche uses only SQLite schema-backed metadata from `boards.db`.

## Supported

- `local-apple-data freeform boards --json --limit 20`
- `local-apple-data freeform get --json --handle <freeform:board:v1:...>`
- `local-apple-data freeform folders --json --query <folder-title-fragment>`
- `local-apple-data freeform folder --json --handle <freeform:folder:v1:...>`
- `local-apple-data freeform folder-boards --json --handle <freeform:folder:v1:...>`
- `local-apple-data freeform child-folders --json --handle <freeform:folder:v1:...>`
- MCP `freeform_list_boards`, `freeform_get_board`, `freeform_search_folders`, `freeform_get_folder`, `freeform_list_folder_boards`, and `freeform_list_child_folders`.

## Returned Fields

- Board opaque handle, last activity timestamp, favorite flag, collaborator-cursor flag, item count, asset-reference count, deletion/hidden flags, and unsynced-change flag.
- Folder opaque handle, folder title, last activity timestamp, board count, deletion/hidden flags, and unsynced-change flag.
- Exact selected-folder board listing returns the selected folder metadata plus capped board metadata for boards directly in that folder.
- Exact selected-folder child-folder listing returns the selected parent folder metadata plus capped child folder metadata for direct visible child folders.
- Metadata booleans proving board title/content, board items, asset content, folder BLOBs, and raw identifiers were not returned.

## Explicitly Blocked

- Board title extraction, because current board title/content appears to live in BLOB/CRDT data rather than a plain metadata column.
- Board BLOB/CRDT decoding, board content export, decoded board item dumps, asset bytes/export, previews, collaboration payloads, raw identifiers, raw `boards.db` rows, broad dumps, Freeform.app automation, iCloud web/API access, and mutation.

## Implementation Notes

- The adapter reads `~/Library/Group Containers/group.com.apple.freeform/Boards/boards.db` through the existing read-only/query-only SQLite helper.
- The health check is schema-only and does not inspect board content or asset files.
- Folder search requires a specific folder title query and rejects broad terms.
- Board listing is capped and returns recent metadata only because board titles are not safely queryable without a separate BLOB decoder design.

## Verification

- Synthetic adapter tests cover schema checks, recent board metadata, exact board retrieval, folder search/detail, exact selected-folder board listing, exact selected-folder child-folder listing, invalid handles, broad folder-query rejection, degraded-store behavior, and non-leakage of raw identifiers/BLOB content.
- CLI tests cover all six Freeform commands.
- MCP tests cover tool registration and invalid-handle behavior.
- Health and surface-contract tests cover Freeform readiness and CLI/MCP/docs alignment.
- Runtime smoke uses a synthetic Freeform SQLite fixture and asserts opaque handles, selected-folder board metadata counts, selected-folder child-folder metadata counts, broad-query refusal, and no raw identifier, BLOB, board item, asset, or board title leakage.

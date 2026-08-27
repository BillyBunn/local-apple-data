# v1.152 Photos Album Asset Listing

## Scope

Add read-only selected-album asset listing for Photos regular albums.

- CLI: `local-apple-data photos album-assets --handle <photos:album:v1:...>`
- MCP: `photos_list_album_assets`
- Input: one opaque `photos:album:v1:` handle returned by `photos_search_albums` / `photos albums`
- Output: capped child `photos:asset:v1:` metadata only

## Public API Basis

Apple PhotoKit documents `PHAsset.fetchAssets(in:options:)` for retrieving assets from a `PHAssetCollection`. The helper already resolves only regular albums through public PhotoKit and now calls that API for the selected album.

## Safety Rules

- Reject raw album identifiers and fabricated/legacy handles.
- Resolve the album handle through bounded regular-album metadata first.
- Return only existing Photos asset metadata already allowed by `photos_search`.
- Do not include resources, thumbnails, bytes, local paths, raw PhotoKit identifiers, asset content, or raw album identifiers.
- Cap output at 50 results and scan work at 10,000 selected-album assets.
- Return `result_truncated` / `scan_truncated` warnings when applicable.
- Normal reads stay non-prompting; use `photos request-access` for explicit TCC prompt recovery.

## Still Blocked

- Smart/shared/synced album targeting.
- Broad or recursive Photos dumps.
- Inline image/video bytes, thumbnails, rendered previews, or asset export outside `photos_export_asset`.
- Album create/rename/delete.
- Bulk album membership outside the existing exact regular-album membership plan/apply gate.
- Content edits, metadata mutation outside approved favorite/hidden, permanent delete, and Recently Deleted empty.

## Verification

Required proof for this tranche:

- Swift helper compile/typecheck.
- Adapter, CLI, MCP, and surface-contract tests.
- Runtime verifier proof for `photos_list_album_assets`, including child asset handle shape, no content return, and no raw Photos IDs.
- Full test suite, compileall, audits, runtime install proof, cross-agent sync, redaction/public-release scans, and artifact hygiene before release/commit.

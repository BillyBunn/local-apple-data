# v1.151 Photos Album Membership Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data photos apply` and `photos_apply_change`.
`local-apple-data photos plan` and `photos_plan_change` validate and preview the
same operation without writing Photos data.

## Scope

- Add one exact selected Photos asset to one exact selected regular Photos album
  with `operation:add_to_album`.
- Remove one exact selected Photos asset from one exact selected regular Photos
  album with `operation:remove_from_album`.
- Select assets only by exact opaque `photos:asset:v1:` handles returned from
  Photos metadata search.
- Select albums only by exact opaque `photos:album:v1:` handles returned from
  regular-album metadata search.

## Non-Scope

- Photos smart albums, shared albums, synced albums,
  folder/list mutation, bulk membership, query-result membership, permanent
  delete/Recently Deleted empty, content edits, metadata mutation outside
  favorite/hidden, thumbnails, inline asset bytes, network iCloud fetch, private
  Photos databases, and raw PhotoKit identifiers.

## Public API Evidence

- `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/Photos.framework/Headers/PHCollection.h`
  exposes `PHAssetCollection`, `fetchAssetCollectionsWithType:subtype:options:`,
  and collection edit-operation checks.
- `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/Photos.framework/Headers/PHAssetCollectionChangeRequest.h`
  exposes `PHAssetCollectionChangeRequest`, `addAssets`, and `removeAssets`.
- `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/Photos.framework/Headers/PhotosTypes.h`
  exposes regular album subtype and add/remove collection edit operations.

No private Photos database mutation, browser/iCloud API, or raw database access
is used.

## Safety Contract

- Plan requires one exact opaque `photos:asset:v1:` handle, one exact opaque
  `photos:album:v1:` handle, and explicit `expected_in_album`.
- Plan resolves current asset metadata, current regular-album metadata, and
  current membership before issuing an approval token.
- Apply recomputes the plan, verifies the approval token and `confirm_apply`,
  re-resolves the exact asset and album, rechecks asset state, album state, and
  `expected_in_album`, then applies through PhotoKit.
- Apply uses `PHAssetCollectionChangeRequest` with `addAssets` or
  `removeAssets` only after `canPerform(.addContent)` or
  `canPerform(.removeContent)` permits the requested operation.
- Read-back must prove the target membership state after apply. Output includes
  `raw_album_identifier_returned:false`, `raw_asset_identifier_returned:false`,
  `asset_content_returned:false`, and no inline asset bytes.

## Synthetic Tests Required

- Album search returns `photos:album:v1:` handles and no raw album identifiers.
- Exact album get returns regular-album metadata only.
- `operation:add_to_album` rejects missing `expected_in_album`.
- Approved add-to-album apply returns `mutation_applied:true` and
  `read_back.in_album:true`.
- Runtime verifier covers album search/get plus album-membership plan/apply
  using synthetic helper responses.

## Remaining Blockers

Photos regular album management is governed by `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`; smart albums, shared albums, synced albums, bulk membership, permanent delete/Recently Deleted empty, content edits, and Photos metadata writes beyond approved favorite/hidden/delete/album-membership/regular-album-management gates remain blocked.

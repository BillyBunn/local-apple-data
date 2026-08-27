# V1.154 Photos Regular Album Management Write Design

Status: Apply-capable implementation.

## Scope

Approved write tools: `local-apple-data photos apply` and `photos_apply_change`.

Preview tools: `local-apple-data photos plan` and `photos_plan_change`.

Approved operations:

- `operation:create_album`
- `operation:rename_album`
- `operation:delete_album`

This gate is limited to regular Photos albums; smart albums, shared albums, synced albums, permanent delete/Recently Deleted empty, content edits, and bulk album membership remain blocked.

Album management requires full Photos Library authorization (`authorization_status:"authorized"`). Limited Photos access is insufficient because duplicate-title and absence proofs must scan the full regular-album set.

## Public API Basis

Apple documents `PHAssetCollectionChangeRequest` as the PhotoKit request type used to create, delete, or modify a Photos asset collection inside a photo-library change block:

- `PHAssetCollectionChangeRequest.creationRequestForAssetCollection`
- `PHAssetCollectionChangeRequest(for: album)`
- `PHAssetCollectionChangeRequest.deleteAssetCollections`

The helper uses only PhotoKit public APIs through the bundled local Photos helper app.

## Plan Contract

`create_album` requires:

- A bounded non-empty title.
- Duplicate title absence proof from the local regular-album metadata scan.
- Fail-closed on `duplicate_album_title`, `scan_truncated`, or `result_truncated`.

`rename_album` requires:

- One exact opaque `photos:album:v1:` handle.
- A bounded non-empty title.
- `expected_album_state` plus album safe hash binding.
- `can_rename:true`.
- Duplicate target-title absence proof.

`delete_album` requires:

- One exact opaque `photos:album:v1:` handle.
- `expected_album_state` plus album safe hash binding.
- `can_delete:true`.
- Empty album proof; non-empty delete returns `non_empty_album_blocked`.

Plans return `mutation_applied:false`, `apply_available:true`, and an approval fingerprint. They do not return raw PhotoKit identifiers.

## Apply Contract

Apply recomputes the plan and requires:

- Matching approval token.
- Explicit confirmation.
- Same title, exact-handle, and expected-state gates as plan.
- Helper-level duplicate-title recheck immediately before create/rename.
- PhotoKit apply through `PHPhotoLibrary.performChanges`.
- `PHAssetCollectionChangeRequest.creationRequestForAssetCollection` for create.
- `PHAssetCollectionChangeRequest(for: album)` and title assignment for rename.
- `PHAssetCollectionChangeRequest.deleteAssetCollections` for delete.
- Title read-back for create/rename.
- Post-apply duplicate-title check for create/rename.
- Absence proof with `verified_absent:true` for delete.
- `raw_album_identifier_returned:false`.

Apply output returns selected safe album metadata for create/rename or metadata-only delete absence proof. It never returns raw PhotoKit identifiers, asset bytes, thumbnails, paths, or resource metadata.

## Failure Behavior

The gate fails closed on:

- Missing or invalid exact handle.
- Missing or invalid title.
- Duplicate title or unproven duplicate absence.
- Expected-state drift.
- Unsupported `can_rename` or `can_delete`.
- Non-empty album delete.
- Missing approval token or confirmation.
- PhotoKit timeout, unavailable Photos authorization, or limited Photos authorization (`photos_full_access_required`).

If PhotoKit may have applied a mutation but read-back or post-apply uniqueness proof fails, status is `apply_unknown` with `mutation_applied:true`.

## Synthetic Tests Required

- Create accepts a non-`LAD-TEST-*` regular album title.
- Create rejects missing title.
- Create rejects duplicate title.
- Title uniqueness fails closed on result truncation.
- Create apply reads back the new title and hides raw album identifiers.
- Rename apply reads back a non-`LAD-TEST-*` title and hides raw album identifiers.
- Delete rejects non-empty albums.
- Delete apply returns `verified_absent:true`.
- Helper duplicate-race errors are surfaced without claiming success.
- Helper `apply_unknown` preserves `mutation_applied:true`.
- Swift source regression checks full Photos Library authorization, `PHAssetCollectionChangeRequest` create/rename/delete calls, duplicate-title helper, title validation, and result-truncation warning.

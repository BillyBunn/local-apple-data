# v1.149 Photos Delete Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data photos apply` and `photos_apply_change`.

No new mutating CLI or MCP tool names are approved or exposed by this document. The existing `local-apple-data photos plan` and `photos_plan_change` tools validate and preview future changes without writing Photos data.

This document approves `operation:delete`: delete one exact selected Photos asset by opaque handle through public PhotoKit.

## Scope

Candidate operation:

- Delete one exact opaque `photos:asset:v1:` handle returned by Photos metadata search/detail.

Out of scope:

- Photos permanent delete/Recently Deleted empty, album-only removal, album membership outside `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`, regular album management outside `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`, content edits, metadata mutation outside favorite/hidden, thumbnails, inline asset bytes, network iCloud fetch, iCloud.com, browser sessions, private Photos databases, raw PhotoKit identifiers as user input, and bulk operations.

## Source Review

The implementation uses public PhotoKit APIs from the local macOS SDK:

- `PHAsset.h` exposes `canPerformEditOperation:` / Swift `canPerform(_:)` and the `.delete` edit operation.
- `PHAssetChangeRequest` exposes `deleteAssets`.
- `PHPhotoLibrary` exposes `performChanges`.

No private Photos database mutation, Photos UI automation, browser/iCloud API path, or raw PhotoKit identifier input is used.

## Tool Contract

Preview:

- Requires `operation:delete`.
- Requires one exact opaque `photos:asset:v1:` handle.
- Resolves the opaque handle through current PhotoKit metadata.
- Binds current safe metadata into `expected_state` and `delete_safe_sha256`.
- Returns `mutation_applied:false`, `apply_available:true`, `raw_asset_identifier_returned:false`, no asset bytes, and an approval fingerprint.

Apply:

- Recomputes the preview immediately before mutation.
- Requires matching `photos-apply:v1:<approval_fingerprint>`.
- Requires `confirm_apply=true`.
- Resolves the same opaque handle again.
- Sends only the private local PhotoKit identifier plus approved `expected_state` to the Swift helper.
- Checks `canPerform(.delete)`, checks expected current safe metadata again, deletes through `PHAssetChangeRequest.deleteAssets`, and reads back absence through PhotoKit.
- Returns `mutation_applied:true` only after PhotoKit reports success and `verified_absent:true`.

Read-back:

- Returns absence proof only: `deleted:true`, `verified_absent:true`, `recently_deleted_empty:false`, `asset_content_returned:false`, and `raw_asset_identifier_returned:false`.
- Does not return raw PhotoKit identifiers, inline bytes, thumbnails, or source paths.

## Approval Gate

The approval fingerprint binds:

- `operation:delete`
- exact opaque asset handle
- current safe metadata `expected_state`
- `delete_safe_sha256`
- proposed delete scope
- idempotency key

Any current-state drift produces an approval-token mismatch or helper-side `expected_state_mismatch` before mutation. Invalid handles, missing expected state, Photos access failure, unsupported delete, missing read-back, and absence-proof mismatch fail closed.

## Synthetic Tests Required

- Preview success for exact delete.
- Preview includes `delete_safe_sha256` and no raw PhotoKit identifier.
- Apply success with `verified_absent:true` absence proof.
- Missing confirmation and invalid approval-token refusal.
- Missing helper absence proof returns `apply_unknown` with `mutation_applied:true`.
- CLI and MCP wrapper argument wiring.
- Runtime verifier keys for plan/apply absence proof.
- Swift typecheck proving public PhotoKit delete symbols compile.

## Current Release Gate

The current release allows Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete only through the plan/apply/read-back gate. Photos album membership is governed by `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`; regular album management is governed by `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`; Photos permanent delete/Recently Deleted empty, content edits, and metadata mutation outside favorite/hidden remain blocked. Network iCloud fetch, private Photos database access, and bulk Photos operations remain blocked.

# v1.134 Photos Update Flags Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data photos apply` and `photos_apply_change`.

No new mutating CLI or MCP tool names are approved or exposed by this document. The existing `local-apple-data photos plan` and `photos_plan_change` tools validate and preview future changes without writing Photos data.

This document approves `operation:update_flags`: update the `favorite` and/or `hidden` flags on one exact selected Photos asset.

## Scope

Candidate operation:

- Set `favorite` and/or `hidden` on one exact opaque `photos:asset:v1:` handle returned by Photos metadata search/detail.

Out of scope:

- Photos asset delete except through the separate `docs/V1_149_PHOTOS_DELETE_WRITE_DESIGN.md` gate, album membership outside `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`, regular album management outside `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`, content edits, metadata mutation outside favorite/hidden, thumbnails, inline asset bytes, network iCloud fetch, iCloud.com, browser sessions, private Photos databases, raw PhotoKit identifiers as user input, and bulk operations.

## Source Review

The implementation uses public PhotoKit APIs from the local macOS SDK:

- `PHAsset.h` exposes read-only `favorite`, `hidden`, and `canPerformEditOperation:` / Swift `canPerform(_:)`.
- `PHAssetChangeRequest.h` exposes `changeRequestForAsset:` plus writable `favorite` and `hidden` properties, and warns callers to check edit support before requesting a change.
- `PHPhotoLibrary.h` exposes `performChanges`.

No private Photos database mutation, Photos UI automation, browser/iCloud API path, or raw PhotoKit identifier input is used.

## Tool Contract

Preview:

- Requires `operation:update_flags`.
- Requires one exact opaque `photos:asset:v1:` handle.
- Requires `expected_favorite` and `expected_hidden`.
- Requires at least one target flag: `favorite` or `hidden`.
- Resolves the opaque handle through current PhotoKit metadata and refuses stale expected state.
- Returns `mutation_applied:false`, `apply_available:true`, `raw_asset_identifier_returned:false`, no asset bytes, and an approval fingerprint.

Apply:

- Recomputes the preview immediately before mutation.
- Requires matching `photos-apply:v1:<approval_fingerprint>`.
- Requires `confirm_apply=true`.
- Resolves the same opaque handle again, sends only the private local PhotoKit identifier to the Swift helper, checks `canPerform(.properties)`, checks expected current flags again, mutates through `PHAssetChangeRequest`, and reads the asset back through PhotoKit.
- Returns `mutation_applied:true` only after PhotoKit reports success and read-back metadata matches the approved target favorite/hidden state.
- Uses `read_back` metadata to prove the selected asset's final favorite/hidden state.

Read-back:

- Uses the existing Photos exact-detail shape with an opaque `photos:asset:v1:` handle.
- Returns bounded asset/resource metadata, `favorite`, `hidden`, and `asset_content_returned:false`.
- Does not return raw PhotoKit identifiers, inline bytes, thumbnails, or source paths.

## Approval Gate

The approval fingerprint binds:

- `operation:update_flags`
- exact opaque asset handle
- expected current `favorite`
- expected current `hidden`
- proposed `favorite`
- proposed `hidden`
- idempotency key

Any current-state drift produces `expected_state_mismatch` before mutation. Invalid handles, missing target flags, missing expected state, Photos access failure, unsupported property updates, missing read-back, and target-state read-back mismatch fail closed.

## Synthetic Tests Required

- Preview success for exact favorite/hidden update.
- Missing expected-state refusal.
- Stale expected-state refusal.
- Missing target flag refusal.
- Apply success with read-back favorite/hidden proof.
- Target-state read-back mismatch refusal without reporting a successful mutation.
- Missing confirmation and invalid approval-token refusal.
- CLI and MCP wrapper argument wiring.
- Runtime verifier keys for plan/apply/stale-state behavior.
- Swift typecheck proving public PhotoKit symbols compile.

## Current Release Gate

The current release allows Photos import, exact asset favorite/hidden update, exact asset delete, exact regular-album membership add/remove, and exact regular-album create/rename/delete only through the plan/apply/read-back gate. Photos asset delete is governed by `docs/V1_149_PHOTOS_DELETE_WRITE_DESIGN.md`; album membership is governed by `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`; regular album management is governed by `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`; content edits and metadata mutation outside favorite/hidden remain blocked. Network iCloud fetch, private Photos database access, and bulk Photos operations remain blocked.

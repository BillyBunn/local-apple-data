# v1.17 Photos Import Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data photos apply` and `photos_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data photos plan` and `photos_plan_change`; those tools validate and preview future changes without writing Photos data.

This document defines the first Photos write lane: import one image or video asset from a caller-selected local file into the system Photos library through PhotoKit, with preview as the default behavior and independent read_back verification after apply.

## Scope

Candidate operation:

- Import one local image or video file into Photos.

Out of scope:

- Photos edits, delete, album membership outside `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`, regular album management outside `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`, metadata mutation outside the exact favorite/hidden gate, thumbnails, inline asset bytes, network iCloud fetch, iCloud.com, browser sessions, private Photos databases, and bulk operations.
- Raw PhotoKit local identifiers as user inputs.
- Importing from URLs, symlinks, packages, directories, or remote/cloud-only sources.

## Source Review

The implementation uses public PhotoKit APIs exposed by the local macOS SDK:

- `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/Photos.framework/Headers/PHPhotoLibrary.h` exposes `authorizationStatusForAccessLevel:`, `performChanges:completionHandler:`, and `performChangesAndWait:error:`.
- `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/Photos.framework/Headers/PHAssetChangeRequest.h` exposes image/video asset creation requests from file URLs and `placeholderForCreatedAsset`.

No private Photos database mutation or browser/iCloud API path is used.

## Tool Contract

Every future Photos write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching Photos.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through PhotoKit asset metadata after apply.

The preview payload must include the operation, target library marker, source filename, inferred media type, file size, file hash, warning codes, and a deterministic idempotency key. It must not include the caller's raw source path, PhotoKit local identifiers, inline asset bytes, thumbnails, unrelated Photos metadata, or raw helper errors.

The apply payload must require an approval token generated from the preview. The token must bind the operation, target marker, source filename, media type, file size, source-file SHA-256, and idempotency key so an agent cannot apply a different import with a stale preview.

The read_back payload must return the created asset through the existing Photos exact-detail shape, using an opaque `photos:asset:v1:` handle and bounded asset/resource metadata. It must not trust the PhotoKit change completion alone.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data photos plan`
- MCP: `photos_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `import`.
- Require a caller-selected local source file.
- Accept only common image and video file extensions.
- Refuse symlink, directory, empty, unreadable, unsupported, and oversized source files.
- Return a deterministic `photos-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not call PhotoKit, read Photos metadata, or mutate Photos data.

Implemented apply tools:

- CLI: `local-apple-data photos apply`
- MCP: `photos_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `photos-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying so changed files invalidate stale approval tokens.
- Use a Swift PhotoKit helper and `PHPhotoLibrary.performChanges` to import one image or video file.
- Fetch the created placeholder identifier after the change block and return created-asset metadata through the existing opaque-handle shape.
- Return `mutation_applied:true` only after PhotoKit reports success and read_back metadata is available.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use Python for CLI/MCP validation and a Swift PhotoKit helper for the actual import:

- Python owns request validation, source-file hashing, approval-token verification, privacy-safe JSON shaping, logging, redaction, and synthetic tests.
- Swift owns PhotoKit authorization checks, `performChanges`, asset creation, and created-asset read-back because Photos.framework is a native Apple framework.
- The MCP server stays stdio and local-only.

This split is the most durable and performant path: Swift talks directly to PhotoKit without database scraping, while Python preserves the existing plugin architecture and test harness.

## Data Model

Required import input:

- `operation`: `import`.
- `source_file`: caller-selected local image or video file.

Optional import input:

- `media_type`: `auto`, `image`, or `video`. When provided as `image` or `video`, it must match the source-file extension.

Preview metadata:

- `source_filename`
- `source_extension`
- `media_type`
- `file_size_bytes`
- `file_sha256`
- `source_path_returned:false`
- `asset_content_returned:false`

The raw source path is accepted only as an apply input and is not echoed in preview, apply output, logs, receipts, or docs.

## Approval Gate

Before any additional apply-capable Photos tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `photos_plan_change` remains read-only; `photos_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-disciplined:

- Preview creates a deterministic idempotency key from the operation, target marker, source filename, media type, file size, and source-file SHA-256.
- Apply recomputes the plan immediately before import; changed source bytes cause approval-token mismatch.
- PhotoKit does not provide a public duplicate-prevention primitive for arbitrary imports. If an apply times out or returns `apply_unknown`, the caller must search Photos by filename before retrying.
- A future local operation ledger may improve duplicate handling, but it must store only opaque operation IDs, warning codes, timestamps, and hashes. It must not store source paths, PhotoKit identifiers, thumbnails, or asset bytes.

## Logging And Redaction

The redaction requirement applies to previews, applies, runtime smoke, tests, and release receipts.

Logs may include:

- Tool name.
- Status.
- Warning code.
- Counts.
- Duration.

Logs must not include:

- Source file paths.
- PhotoKit local identifiers.
- Opaque Photos handles.
- Source filenames when they came from personal data.
- Source-file hashes.
- Approval tokens or fingerprints.
- Asset bytes, thumbnails, exported bytes, or image/video metadata beyond counts/status.
- Raw helper errors or stack traces.

## Synthetic Tests Required

Before exposure, the Photos import implementation must add:

- Preview success tests for import.
- Preview validation tests for missing source file, unsupported media type, media-type mismatch, symlink/directory/unreadable inputs, empty files, oversized files, and invalid operations.
- Apply/read_back success tests using a mocked PhotoKit helper response.
- Missing-confirmation and invalid-token tests.
- Helper timeout/error tests.
- Access-denied/degraded tests.
- Redaction tests proving logs do not contain source paths, source filenames, file hashes, PhotoKit identifiers, handles, approval fingerprints, tokens, raw helper errors, or asset bytes.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

This document approves only Photos import. Additional Photos mutation requires a separate write-design gate. Exact asset favorite/hidden updates are governed by `docs/V1_134_PHOTOS_UPDATE_FLAGS_WRITE_DESIGN.md`; Photos permanent delete/Recently Deleted empty, album membership outside `docs/V1_151_PHOTOS_ALBUM_MEMBERSHIP_WRITE_DESIGN.md`, regular album management outside `docs/V1_154_PHOTOS_REGULAR_ALBUM_MANAGEMENT_WRITE_DESIGN.md`, metadata mutation outside favorite/hidden, thumbnails, inline asset bytes, network iCloud fetch, iCloud.com, private Photos database access, and bulk operations remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

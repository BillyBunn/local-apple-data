# v1.12 iCloud Drive Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No other mutating CLI or MCP tools are approved or exposed by this document. The current implementation also exposes `local-apple-data icloud-drive plan` and `icloud_drive_plan_change`; those tools validate and preview future changes without writing to iCloud Drive.

This document defines the first iCloud Drive write lane: create one supported text-like file under an exact opaque `icloud:file:v1:` parent folder handle, with preview as the default behavior, exclusive create on apply, and independent read_back verification after apply.

## Scope

Candidate operation:

- Create one text-like file in an explicitly selected iCloud Drive folder.

Out of scope:

- Append (governed by v1.18), replace-text (governed by v1.51), trash-text (governed by v1.53), rename/copy/move (governed by v1.54), or delete outside the approved trash-text gate.
- Binary or document generation.
- Hidden files, symlinks, package traversal, broad folder writes, or recursive operations.
- Raw path targeting.
- Mutations through iCloud.com, browser sessions, keychain credentials, private iCloud APIs, OAuth, IMAP, or external connectors.

## Tool Contract

Every future iCloud Drive write operation must keep the same three-step shape:

- `preview`: validate input and return the planned change without touching local files.
- `apply`: perform exactly the approved change after explicit user approval.
- `read_back`: verify the resulting state through the normal local iCloud Drive adapter.

The preview payload must include the operation, exact opaque `icloud:file:v1:` parent folder handle, normalized filename, text-content length, extension, warning codes, and a deterministic idempotency key. It must not include raw local paths, file contents, unrelated filenames, account identifiers, or framework exception text.

The apply payload must require an approval token or equivalent explicit approval artifact generated from the preview. The token must bind the operation, target parent handle, normalized filename, content hash, and idempotency key so an agent cannot apply a different mutation with a stale preview.

The read_back payload must inspect the created file through the same local adapter path and return bounded metadata plus `content_chars` and `content_sha256`. It must not trust the write call alone.

## Current Tools

Implemented preview tools:

- CLI: `local-apple-data icloud-drive plan`
- MCP: `icloud_drive_plan_change`

These tools:

- Return `mode: "plan"`.
- Return `mutation_applied:false`.
- Return `apply_available:true`.
- Accept only `create_text`.
- Require an exact opaque `icloud:file:v1:` parent folder handle from iCloud Drive search output.
- Require a single safe text-like filename.
- Require bounded non-empty text content and reject NUL bytes.
- Return a deterministic `icloud-drive-plan:v1:` idempotency key.
- Return an approval fingerprint for approval token binding.
- Do not resolve the parent handle, read iCloud Drive, create files, or mutate iCloud Drive.

Implemented apply tools:

- CLI: `local-apple-data icloud-drive apply`
- MCP: `icloud_drive_apply_change`

These tools:

- Return `mode: "apply"`.
- Require a matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Require explicit apply confirmation.
- Recompute the plan before applying.
- Resolve the parent directory only from the exact opaque `icloud:file:v1:` parent folder handle.
- Refuse missing, symlinked, package-traversing, or non-directory parent targets.
- Use fd-based no-follow exclusive create so an existing file or symlink is never overwritten or followed.
- Treat an existing file with matching normalized content as idempotent `already_applied`.
- Return `mutation_applied:true` only after the file is created and read_back data is available.
- Use non-read-only, non-destructive, idempotent, closed-world MCP annotations.

## Implementation Choice

Use the existing Python adapter and local filesystem APIs for this tranche:

- Python already owns CLI/MCP validation, opaque handles, approval-token verification, redacted logging, release gates, and JSON response shape.
- Local iCloud Drive files are exposed through the regular filesystem under CloudDocs, so a native Apple framework bridge is not required for a simple exclusive text-file create.
- `os.open` with `O_CREAT | O_EXCL | O_NOFOLLOW` gives the required exclusive create behavior without overwrite or symlink-following risk.
- The adapter resolves opaque handles by scanning within the configured iCloud Drive root, verifies the target remains under that root, rejects package or symlink traversal, and writes through a parent directory file descriptor before read-back verification.

Swift remains the right boundary for EventKit, Contacts, and PhotoKit operations. For this iCloud Drive create-text path, adding Swift would add process overhead and another failure mode without improving privacy or durability.

## Data Model

Required create input:

- `parent_handle`: exact opaque `icloud:file:v1:` handle for a directory returned by iCloud Drive filename search.
- `filename`: one basename only, max 255 characters, not hidden, no path separators, text-like suffix, and limited safe characters.
- `content_text`: non-empty UTF-8 text, normalized to LF, capped at the normal text-content maximum.

All inputs are bounded. File contents are used only to compute the approval fingerprint and write the approved file; they are not logged.

## Approval Gate

Before any additional apply-capable iCloud Drive tool is exposed:

- `docs/MUTATION_GATES.md` must name the approved operation.
- `docs/WRITE_TOOL_ROADMAP.md` must move the operation from candidate to approved.
- `scripts/audit_mutation_gates.py` must allow only the exact approved CLI and MCP names.
- `scripts/audit_write_design_gates.py` must move the operation from design-only to approved-with-tests.
- `icloud_drive_plan_change` remains read-only; `icloud_drive_apply_change` uses separate non-read-only MCP annotations.
- Runtime smoke must prove MCP write annotations are non-read-only and destructive only when the operation is destructive.
- The skill, README, privacy model, threat model, testing doc, capability matrix, changelog, and plugin manifest must describe the new state consistently.

## Idempotency

The apply path must be retry-safe:

- Create uses a deterministic idempotency key derived from parent handle, stable parent identity, normalized filename, content hash, and approval token.
- Apply uses exclusive create to prevent overwrites.
- Retry after success returns `already_applied` only when the existing file content exactly matches the approved normalized content.
- Existing files with different content return `target_exists` and do not mutate the file.

No implementation may create durable personal-content caches to solve idempotency. Any local operation ledger must store only opaque operation IDs, warning codes, timestamps, and hashes of normalized approved fields.

## Logging And Redaction

Logs may include:

- Tool name.
- Status.
- Warning code.
- Counts.
- Duration.

The redaction requirement applies to previews, applies, runtime smoke, tests, and release receipts.

Logs must not include:

- File contents.
- Filenames.
- Handles.
- Raw local paths.
- Account names.
- Content hashes.
- Approval tokens or fingerprints.
- Framework or filesystem exception text.

## Synthetic Tests Required

Before exposure, the iCloud Drive write implementation must add:

- Preview success tests for create text.
- Preview validation tests for invalid parent handles, invalid filenames, unsupported suffixes, oversized content, and binary-like content.
- Apply/read_back success tests using temporary synthetic roots.
- Missing-confirmation and invalid-token tests.
- Target-not-found, target-exists, parent-symlink, and target-symlink tests.
- Idempotency tests for retry after success.
- Redaction tests proving logs do not contain filenames, content, handles, hashes, approval fingerprints, tokens, raw paths, or raw exceptions.
- MCP annotation tests proving write tools are not marked read-only.

## Current Release Gate

The v1.12 release allowed only this iCloud Drive create-text apply surface. iCloud Drive append-text is governed separately by `docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md`; replace-text is governed separately by `docs/V1_51_ICLOUD_DRIVE_REPLACE_WRITE_DESIGN.md`; create-folder is governed separately by `docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md`; create-folder-path is governed separately by `docs/V1_157_ICLOUD_DRIVE_FOLDER_PATH_CREATE_WRITE_DESIGN.md`; trash-text is governed separately by `docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md`; file rename/copy/move is governed separately by `docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md`; folder rename by `docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md`; exact folder Trash by `docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md`; folder move by `docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md`; exact selected-folder copy by `docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md`; exact selected-folder delete by `docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md`; and non-empty folder rename/move by `docs/V1_145_ICLOUD_DRIVE_NON_EMPTY_FOLDER_RENAME_MOVE_WRITE_DESIGN.md`. File permanent delete outside the exact delete-text/delete-file gates, empty Trash, unbounded recursive folder copy/delete, binary/document generation, recursive folder writes, raw path writes, content replacement outside the exact replace-text gate, and every other mutation class remain blocked by `docs/MUTATION_GATES.md` and `docs/WRITE_TOOL_ROADMAP.md`.

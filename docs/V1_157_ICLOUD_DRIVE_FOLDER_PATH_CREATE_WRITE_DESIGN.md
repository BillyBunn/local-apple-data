# v1.157 iCloud Drive Folder Path Create Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.

No new write tool names are approved or exposed by this document. The existing
`local-apple-data icloud-drive plan` and `icloud_drive_plan_change` tools support
`operation: create_folder_path` as a non-mutating preview, and the existing apply
tools support the matching approved bounded folder-path create operation.

## Scope

This gate broadens the single-folder create lane to create a short child path
under one exact selected iCloud Drive directory.

Allowed:

- Create one to three bounded folder components under one exact opaque `icloud:file:v1:` parent directory handle.
- Accept folder names only through `folder_components`.
- Treat existing directory components as existing-directory idempotency.
- Use fd-based no-follow `mkdir` per missing component.
- Return final directory metadata only after apply.

Blocked:

- Raw paths, slash-delimited path strings, hidden names, package names, symlinks,
  unsupported filesystem entries, unbounded recursive folder write, broad folder
  trees, overwrite, delete, move, copy, file content writes, raw path return,
  content return, and content hash return.
- iCloud.com, private iCloud APIs, browser sessions, keychain credentials,
  network fallback, or live personal-data mutation outside the exact approved
  plan/apply gate.

## Preview

Preview validates inputs and returns `mutation_applied:false`.

- `create_folder_path` requires one exact opaque parent directory handle,
  plan-time stable parent identity binding, and `folder_components`.
- It accepts one to three bounded folder components.
- Each component uses the same safe folder-name rules as create-folder:
  non-hidden, no path separators, no trailing dot or space, no package suffix,
  and bounded UTF-8 length.
- Preview rejects `filename`, `content_text`, file handles, target handles,
  source files, raw local paths, and more than three components.
- Preview returns the parent handle, expected parent identity SHA-256, and
  component list only in the transient plan response.

## Apply

Apply requires:

- Matching `icloud-drive-apply:v1:<approval_fingerprint>` approval token.
- Explicit confirmation.
- Exact opaque parent directory handle.
- Expected parent identity SHA-256 bound into the approval fingerprint.
- The same one to three bounded folder components.
- Recomputed plan match before mutation.
- Stale parent refusal if the selected parent directory is deleted, recreated,
  or otherwise changes after planning.
- Parent resolution inside the configured iCloud Drive root.
- No-follow parent and child directory opens.
- Package and symlink traversal refusal.
- fd-based no-follow `mkdir` or existing-directory idempotency per component.
- Partial reporting if mutation begins before a later failure.

If an intermediate component exists as a directory, apply descends into it. If it
exists as a file, symlink, package, or unsupported entry, apply returns an error
without treating it as created. If a later component fails after an earlier
component was created, apply returns `partial` with `mutation_applied:true`.

## Read Back

Read-back is metadata-only:

- `final_folder_verified:true`
- `component_count`
- `created_count`
- `existing_count`
- `content_text_returned:false`
- `content_hash_returned:false`
- no raw path return
- no content return

The output must not include full raw filesystem paths, child listings, file
content, content hashes, approval tokens, or private source paths. Apply output
uses the standard mutation response approval metadata and may echo the verified
approval fingerprint.

## Synthetic Tests Required

- Plan success for one, two, and three components.
- Plan refusal for hidden names, path separators, package suffixes, trailing
  spaces or dots, raw path input, and more than three components.
- Apply success creating a two-component path.
- Apply idempotency when every component already exists.
- Apply refusal when an existing component is not a directory.
- Apply refusal when the selected parent directory is replaced after planning.
- Apply refusal when folder components differ from the approved plan.
- Partial apply reporting when a later component fails after an earlier
  component was created.
- CLI plan/apply coverage for repeated `--folder-component`.
- MCP preview and apply coverage.
- Runtime verifier coverage for direct and MCP create-folder-path flows.
- Redaction scan coverage proving no raw path, content text, content hash,
  approval tokens, or component-derived private paths leak through logs.

The current release allows iCloud Drive create-text, append-text, replace-text, create-folder, create-folder-path, exact folder rename, exact folder Trash, exact folder move, exact selected-folder copy, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply only.

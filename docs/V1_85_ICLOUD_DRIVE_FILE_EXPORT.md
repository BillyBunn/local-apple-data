# v1.85 iCloud Drive Exact File Export

Status: Implemented.

## Scope

Add read-only export for one exact selected local iCloud Drive regular file.

This is not a write gate. It does not mutate iCloud Drive, does not inspect file
contents beyond bounded byte copying, and does not return inline file bytes or
the source local path.

## Source Review

The surface uses only the local filesystem under the configured iCloud Drive
root. It does not use iCloud.com, private iCloud APIs, browser sessions,
keychain credentials, network fetches, or direct raw-path input as the selected
source.

The source file must be resolved from an opaque `icloud:file:v1:` handle
returned by the metadata walk. The adapter refuses hidden entries skipped by the
metadata walk, symlinks, package-internal files, directory handles, non-regular
files, and files above the export byte cap. After metadata validation, exact
content and export reads bind the selected parent and file stat, reopen the
selected parent through the root-relative no-follow directory walker, open the
final file with `O_NOFOLLOW`, and verify the opened file still matches the
selected file state before returning bytes. Source-root ancestor swaps,
real-directory root replacements, and selected-file replacement races fail
closed instead of returning or exporting a different file.

## Interface

- CLI: `local-apple-data icloud-drive export --json --handle <icloud:file:v1:...> --output-dir <dir> [--filename <name>] [--max-bytes <bytes>]`
- MCP: `icloud_drive_export_file(handle, output_dir, filename="", max_bytes=262144000)`

The output directory is caller-selected and must be outside the configured
iCloud Drive root. The adapter creates the directory if needed, refuses symlink
output directories and arbitrary symlink ancestors, writes a sanitized unique
filename with exclusive create through a stable directory fd, verifies the
returned path still names the created file identity, and returns the exported
path, exported filename, and exported byte count. macOS top-level `/var` and
`/tmp` aliases are normalized to their canonical `/private/...` roots before the
no-follow walk so system temp paths work without allowing nested symlink
ancestors.

## Privacy Contract

Returned:

- Selected file metadata already allowed by iCloud Drive metadata search.
- `file_content_returned:false`
- `file_content_exported:true` on success.
- `source_path_returned:false`
- Caller-selected export path and byte count.

Not returned:

- Source local path.
- Inline file bytes.
- Content hash for arbitrary exported files.
- Raw iCloud Drive paths.
- Hidden staging paths or temporary paths.

## Refusals

- Invalid or fabricated handles: `invalid_handle`
- Missing iCloud Drive root: `icloud_drive_unavailable`
- Missing selected file: `not_found`
- Directory, symlink, package-internal, or non-regular target: `unsupported_file_type`
- Output directory inside the configured iCloud Drive root: `output_dir_in_icloud_root`
- Symlink or non-directory output path: `invalid_output_dir`
- Bad byte cap: `invalid_byte_limit`
- File over cap: `file_too_large`
- Copy/write race or other safe-copy failure: `icloud_drive_export_failed`

## Verification

Synthetic coverage must prove:

- Exact binary file export without source path return.
- Regular document-like file export as an opaque file copy, not inline parsing.
- Output directory under iCloud Drive is refused before creation.
- Symlink output directory is refused.
- Direct/deep symlink output ancestors and nested output symlinks back into the iCloud root are refused.
- Source-root ancestor swaps, real-directory root replacements, and selected-file replacement races between validation and read fail closed.
- Existing export filenames are not overwritten; a unique suffix is selected.
- Post-write export path identity mismatches clean up the created file and fail closed.
- Oversized files fail before creating the output directory.
- macOS `/var` temporary-directory aliases work after canonicalization.
- CLI export root overrides are refused unless the synthetic test-root opt-in is set.
- Package-internal handles fail closed.
- Directory handles fail closed.
- Malformed byte caps fail closed.
- CLI and MCP surfaces forward exact handle/output inputs.
- Runtime verifier proves source and MCP export smokes with no inline bytes and no source path return.

## Out Of Scope

- Inline binary/document extraction.
- Document parsing, OCR, preview generation, or text extraction.
- Package export.
- Broad or recursive export.
- Raw path source selection.
- Non-empty or recursive folder export.
- Binary/document create, update, delete, rename, copy, move, or import writes.
- Any network iCloud fetch or private API fallback.

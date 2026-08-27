# v1.178 Filesystem Home-Scope Write Design

Status: Apply-capable implementation.

Approved write tools: `local-apple-data filesystem apply` and `filesystem_apply_change`.

The existing `local-apple-data filesystem plan` and `filesystem_plan_change` tools
support the full home-directory operation set as a non-mutating preview, and the
matching apply tools apply the approved change and read back proof. No new write
tool names are approved beyond the filesystem plan/apply pair introduced by this
document.

## Scope

This gate extends the well-tested iCloud Drive file-mutation and read surface
from the iCloud-Drive-only root to the operator home directory (`~`,
`/Users/<operator>`). The operator explicitly authorized "home dir (`~`)
read+write" scope. It is an additive extension, not a fork: the new
`filesystem` adapter reuses the exact iCloud Drive plan/apply/read-back gates
with the home directory passed as the root, and existing iCloud Drive behavior
is byte-for-byte unchanged (the `icloud_drive_*` tools and `icloud:file:v1:`
handles are untouched).

The home root is `Path.home()` (`/Users/<operator>`) with an env override
`LOCAL_APPLE_DATA_FS_ROOT` mirroring the existing iCloud `LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT`
override. Synthetic-test roots are gated by `LOCAL_APPLE_DATA_ALLOW_TEST_ROOT`
exactly like the iCloud CLI test-root gate.

Handles use a distinct `fs:file:v1:` namespace. Because the reused opaque-handle
token is an HMAC keyed on the iCloud prefix and the path relative to the root,
the filesystem adapter swaps only the visible handle prefix string
(`fs:file:v1:` <-> `icloud:file:v1:`) at the boundary and rewrites the result
`source` label to `filesystem`, so the public surface presents a separate
namespace while reusing the resolver.

Allowed:

- The full iCloud Drive operation set re-rooted at the operator home directory:
  create-text, append-text, replace-text, create-folder, create-folder-path,
  rename-folder, trash-folder, delete-folder, move-folder, copy-folder,
  trash-text, delete-text, rename-text, copy-text, move-text, rename-file,
  copy-file, move-file, import-file, replace-file, trash-file, delete-file.
- Read/list/tree/content/export for exact `fs:file:v1:` handles under the home
  root, subject to the credential denylist for content.

Blocked:

- Any resolved target outside the home root. Every resolved target stays within
  the home root after realpath/symlink resolution; a symlink or `..` component
  that would escape the home root is refused. Other users' home directories
  (`/Users/<otheruser>`), `/System`, `/Library` (system), `/usr`, `/bin`,
  `/etc`, `/private`, and any absolute path not under the home root are refused.
- Content-read and mutation of a credential/secret denylist (see below).
- Hidden files, symlink traversal, package/bundle traversal, raw path return,
  unbounded recursive folder write, empty Trash, and binary/document content
  generation, exactly as in the iCloud Drive gates.

## Reuse of the iCloud Drive gates

This surface reuses the exact iCloud Drive plan/apply/read-back gates with the
home root passed in. That means it inherits, unchanged:

- No-overwrite on create/copy/move/rename.
- Expected-SHA / expected-metadata binding with drift refusal.
- Hidden-staging identity proof plus absence proof for permanent delete.
- Reversible Trash for trash operations, using a `reversible ~/.Trash` move for
  the home root.
- Package/bundle traversal refusal and no-follow / no-symlink traversal guards.
- `MAX_EXPORT_BYTES` and scan-entry caps.

The apply path uses a `filesystem-apply:v1:<approval_fingerprint>` approval
token (the reused iCloud approval token with the visible prefix rewritten).

## Credential/secret denylist

The operator's standing global instruction is "Never print or copy secret
values from local config, credentials, app-support stores, env files, or
launchd environments." This surface honors it: it refuses BOTH content-read AND
mutation of a denylist of secret-bearing paths under home, returning a distinct
code `credential_path_blocked`. The denylist (prefix match, case-insensitive on
macOS):

- `~/.ssh`
- `~/.aws`
- `~/.gnupg`
- `~/.config/gh`
- `~/.config/gcloud`
- `~/.netrc`
- `~/.docker/config.json`
- `~/.kube`
- `~/Library/Keychains`
- `~/Library/Application Support/com.apple.TCC`
- any file named exactly `.env` or matching `.env.*`

General dotfiles such as `~/.zshrc`, `~/.bashrc`, and `~/.envrc` are not
denylisted; only the credential list above is. Metadata-only access
(name/size/mtime, no content bytes) is still allowed for these paths so
listings and search continue to work, but content bytes are never returned and
mutation is never performed. The denylist is a module constant, documented as
operator-overridable via env `LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1`.

## Preview

Preview reuses the iCloud Drive `plan` logic with the home root and returns
`mutation_applied:false`. Before delegating, the filesystem plan refuses
mutation whose target handle or parent handle resolves to a credential/secret
path.

## Apply

Apply reuses the iCloud Drive `apply` logic with the home root. It requires a
matching `filesystem-apply:v1:<approval_fingerprint>` approval token, explicit
confirmation, and an exact `fs:file:v1:` handle or parent handle. It refuses
mutation of credential/secret paths before delegating, and every resolved
target stays within the home root after realpath/symlink resolution.

Permanent delete stays behind the same hidden-staging identity-proof and
absence-proof gate as iCloud delete. Trash (reversible) remains the default
destructive path.

## Read Back

Read-back is metadata-only for structural operations and reuses the iCloud
Drive read-back proofs (`content_text_returned:false`,
`content_hash_returned:false`, no raw path return) with handles rewritten to the
`fs:file:v1:` namespace and `source: filesystem`.

## Synthetic Tests Required

- Full CRUD happy path on a tmp home root: create-text, content read,
  create-folder, create-folder-path, rename, copy, move, trash, and permanent
  delete.
- Outside-home refusal: a target resolving outside the home root is refused.
- Symlink-escape refusal: a symlink pointing outside the home root is not
  resolvable and any forged handle for it fails closed.
- `..`-escape refusal: a filename or component containing `..` is refused.
- Credential-path refusal: reading `~/.ssh/id_rsa` content is refused with
  `credential_path_blocked`, mutating a denylisted path is refused, and
  metadata-only access to a denylisted path is still allowed.
- CLI plan/apply coverage for the home-directory operation set.
- MCP preview and apply coverage.
- Runtime verifier coverage for direct and MCP create/read/update/move/trash/
  delete flows plus the outside-home, symlink-escape, and credential-path
  refusals.
- Redaction scan coverage proving no raw path, content text, content hash,
  approval tokens, or credential values leak through logs.

## Gate contract summary

For clarity, the gate reuses the iCloud Drive per-operation gates unchanged and
adds the home-scope and credential boundaries. The load-bearing invariants:

- No new write tool names are approved beyond the filesystem plan/apply pair introduced by this document.
- existing iCloud Drive behavior is byte-for-byte unchanged.
- every resolved target stays within the home root after realpath/symlink resolution.
- Content-read and mutation of denylisted credential/secret paths are refused, while metadata-only access is still allowed.
- The denylist matches `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `~/.config/gcloud`, `~/.netrc`, `~/.docker/config.json`, `~/.kube`, `~/Library/Keychains`, `~/Library/Application Support/com.apple.TCC`, and any file named exactly `.env` or matching .env or .env.*; general dotfiles such as `~/.zshrc` are not denylisted.
- Trash operations use a reversible `~/.Trash` move; permanent delete stays behind the same hidden-staging identity-proof and absence-proof gate as iCloud delete.
- Reused per-operation invariants: no-overwrite on create/copy/move/rename, expected-SHA / expected-metadata binding, package/bundle traversal refusal, no-follow / no-symlink traversal, `MAX_EXPORT_BYTES`, and scan-entry caps.

The current release allows home-directory Filesystem create-text, append-text, replace-text, create-folder, create-folder-path, rename-folder, trash-folder, delete-folder, move-folder, copy-folder, trash-text, delete-text, rename-text, copy-text, move-text, rename-file, copy-file, move-file, import-file, replace-file, trash-file, and delete-file apply within the operator home root only.

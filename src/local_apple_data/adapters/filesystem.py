"""Home-directory filesystem CRUD surface (v1.178).

This module is a thin, additive wrapper around the well-tested iCloud Drive
CRUD adapter in :mod:`local_apple_data.adapters.icloud_drive`. It re-roots the
same plan/apply/read-back machinery at the operator's home directory
(``~`` / ``/Users/<operator>``) so agents get full-CRUD access across the
operator's personal files, not only iCloud Drive.

Design (see ``docs/V1_178_FILESYSTEM_HOME_SCOPE_WRITE_DESIGN.md``):

* The iCloud helpers already take a ``root: Path`` argument and enforce
  within-root, no-follow, no-symlink-traversal, no-package-traversal,
  hidden-staging + absence-proof delete, and reversible ``.Trash`` moves
  relative to that root. This wrapper passes the *home* root and reuses those
  gates unchanged. No iCloud behavior is altered; the ``icloud_drive_*`` tools
  and ``icloud:file:v1:`` handles are untouched.
* Handles use a distinct ``fs:file:v1:`` namespace. Because the underlying
  opaque-handle token is an HMAC keyed on the ``icloud:file`` prefix and the
  path relative to the root, this module swaps only the *visible* prefix
  string on the boundary (``fs:file:v1:`` <-> ``icloud:file:v1:``) so the token
  round-trips against the reused resolver while the public surface presents a
  separate namespace. The result ``source`` label is rewritten to
  ``filesystem``.
* Two hard safety boundaries are layered on top of the reused within-root
  gate:
    1. Every resolved target must stay within the home root after realpath /
       symlink resolution (already enforced by the reused guards; confirmed by
       tests for both ``..`` escapes and symlink escapes).
    2. A credential/secret denylist refuses BOTH content-read and mutation of
       secret-bearing paths under home (``credential_path_blocked``).
       Metadata-only (name/size/mtime, no content bytes) is still allowed so
       listings work. The denylist is operator-overridable via
       ``LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1``.

Permanent delete stays behind the exact same gate design as the iCloud
``delete_file`` / ``delete_folder`` path (expected metadata, hidden-staging
identity proof, permanent unlink, absence proof). Trash (reversible) remains
the default destructive path and uses ``~/.Trash`` for the home root.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import icloud_drive as _icloud

# The filesystem surface reuses the iCloud Drive operation set verbatim. This
# is defined as a literal set (not an alias) so scripts/audit_mutation_gates.py
# can read it via AST.
PLAN_OPERATIONS = {
    "create_text",
    "append_text",
    "replace_text",
    "create_folder",
    "create_folder_path",
    "rename_folder",
    "trash_folder",
    "delete_folder",
    "move_folder",
    "copy_folder",
    "trash_text",
    "delete_text",
    "rename_text",
    "copy_text",
    "move_text",
    "rename_file",
    "copy_file",
    "move_file",
    "import_file",
    "replace_file",
    "trash_file",
    "delete_file",
}

# Visible handle namespaces. The wrapper presents ``fs:file:v1:`` while the
# reused resolver keys on ``icloud:file:v1:`` tokens.
FS_HANDLE_PREFIX = "fs:file"
FS_HANDLE_MARKER = "fs:file:v1:"
ICLOUD_HANDLE_MARKER = "icloud:file:v1:"
SOURCE_LABEL = "filesystem"
ICLOUD_SOURCE_LABEL = "icloud_drive"

# Approval-token prefix used by the reused apply path.
FS_APPROVAL_TOKEN_MARKER = "filesystem-apply:v1:"
ICLOUD_APPROVAL_TOKEN_MARKER = "icloud-drive-apply:v1:"

_ALLOW_CREDENTIAL_PATHS_ENV = "LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS"

# Credential/secret denylist. Prefix match, case-insensitive on macOS.
# Content-read AND mutation of these are refused with ``credential_path_blocked``.
# General dotfiles (e.g. ``.zshrc``) are intentionally NOT listed. Metadata-only
# access is still allowed so listings/search continue to work. Operator can
# override with ``LOCAL_APPLE_DATA_FS_ALLOW_CREDENTIAL_PATHS=1``.
CREDENTIAL_DENYLIST_RELATIVE = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".config/gh",
    ".config/gcloud",
    ".netrc",
    ".docker/config.json",
    ".kube",
    "Library/Keychains",
    "Library/Application Support/com.apple.TCC",
)


def _default_fs_root() -> Path:
    configured = os.environ.get("LOCAL_APPLE_DATA_FS_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home()


DEFAULT_FS_ROOT = _default_fs_root()


def _credential_paths_allowed() -> bool:
    return os.environ.get(_ALLOW_CREDENTIAL_PATHS_ENV) == "1"


def _is_env_file_name(name: str) -> bool:
    lowered = name.casefold()
    return lowered == ".env" or lowered.startswith(".env.")


def _is_credential_relative(relative: str) -> bool:
    """True when ``relative`` (POSIX, relative to the home root) is on the
    credential/secret denylist by prefix, or is an ``.env`` / ``.env.*`` file.

    Comparison is case-insensitive to match macOS's case-insensitive HFS+/APFS
    default and to defeat trivial case-based bypasses.
    """

    if relative in ("", "."):
        return False
    normalized = relative.strip("/").casefold()
    parts = [part for part in normalized.split("/") if part]
    # Any component named exactly `.env` or matching `.env.*`.
    for part in parts:
        if _is_env_file_name(part):
            return True
    for denied in CREDENTIAL_DENYLIST_RELATIVE:
        denied_norm = denied.casefold()
        if normalized == denied_norm or normalized.startswith(denied_norm + "/"):
            return True
    return False


def _relative_for_handle(handle: str, root: Path) -> str | None:
    """Resolve an ``fs:file:v1:`` (or root) handle to its path relative to the
    home root. Returns ``None`` when the handle does not resolve.

    The reused iCloud resolver skips hidden entries, which would let the
    credential guard miss hidden secret paths (e.g. ``~/.ssh/id_rsa`` or
    ``~/.env``). To keep the credential guard defense-in-depth, this resolver
    first tries the reused (hidden-skipping) resolver, then falls back to a
    bounded hidden-inclusive scan so the guard can still recognize a
    denylisted target and fail closed with the distinct blocked code.
    """

    icloud_handle = _to_icloud_handle(handle)
    if not _icloud.is_opaque_handle(icloud_handle, "icloud:file"):
        return None
    path = _icloud._resolve_handle(
        icloud_handle,
        root,
        max_scan_entries=_icloud.MAX_SCAN_ENTRIES,
    )
    if path is not None:
        try:
            return _icloud._relative_path(path, root)
        except ValueError:
            return None
    return _resolve_handle_including_hidden(icloud_handle, root)


def _resolve_handle_including_hidden(icloud_handle: str, root: Path) -> str | None:
    """Resolve a handle to its home-relative POSIX path, scanning hidden and
    symlinked entries too. Used only by the credential guard so denylisted
    hidden paths are still recognized. Bounded by ``MAX_SCAN_ENTRIES``.
    """

    expanded_root = root.expanduser()
    if _icloud.opaque_handle_matches(icloud_handle, "icloud:file", "."):
        return "."
    scanned = 0
    for current_root, dirnames, filenames in os.walk(expanded_root, followlinks=False):
        dirnames.sort()
        current = Path(current_root)
        for name in sorted(dirnames) + sorted(filenames):
            candidate = current / name
            try:
                relative = candidate.relative_to(expanded_root).as_posix()
            except ValueError:
                continue
            if _icloud.opaque_handle_matches(icloud_handle, "icloud:file", relative):
                return relative
            scanned += 1
            if scanned >= _icloud.MAX_SCAN_ENTRIES:
                return None
    return None


def _to_icloud_handle(handle: str) -> str:
    """Rewrite a visible ``fs:file:v1:`` handle to the reused ``icloud:file:v1:``
    handle. Non-``fs`` handles are passed through unchanged so that forged or
    malformed input is rejected by the reused validator rather than silently
    accepted.
    """

    stripped = handle.strip()
    if stripped.startswith(FS_HANDLE_MARKER):
        return ICLOUD_HANDLE_MARKER + stripped[len(FS_HANDLE_MARKER):]
    return handle


def _to_icloud_approval_token(token: str) -> str:
    stripped = token.strip()
    if stripped.startswith(FS_APPROVAL_TOKEN_MARKER):
        return ICLOUD_APPROVAL_TOKEN_MARKER + stripped[len(FS_APPROVAL_TOKEN_MARKER):]
    return token


def _rewrite_payload(value: Any) -> Any:
    """Recursively rewrite iCloud namespace strings to the filesystem namespace
    in a result payload: handle prefixes, approval-token format, and the
    ``source`` label.
    """

    if isinstance(value, str):
        rewritten = value
        rewritten = rewritten.replace(ICLOUD_HANDLE_MARKER, FS_HANDLE_MARKER)
        rewritten = rewritten.replace(
            ICLOUD_APPROVAL_TOKEN_MARKER, FS_APPROVAL_TOKEN_MARKER
        )
        return rewritten
    if isinstance(value, list):
        return [_rewrite_payload(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "source" and item == ICLOUD_SOURCE_LABEL:
                result[key] = SOURCE_LABEL
            else:
                result[key] = _rewrite_payload(item)
        return result
    return value


def _credential_block_result(*, content: bool, mutation: bool) -> dict[str, Any]:
    warning = {
        "code": "credential_path_blocked",
        "message": (
            "Filesystem content-read and mutation of credential/secret paths is "
            "blocked. Metadata-only access is available. Override with "
            f"{_ALLOW_CREDENTIAL_PATHS_ENV}=1."
        ),
    }
    if mutation:
        return {
            "schema_version": 1,
            "status": "error",
            "source": SOURCE_LABEL,
            "privacy": {
                "content_inspected": False,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "mutation",
            },
            "mode": "apply",
            "mutation_applied": False,
            "apply_available": True,
            "preview": None,
            "read_back": None,
            "result_count": 0,
            "warnings": [warning],
        }
    return {
        "schema_version": 1,
        "status": "error",
        "source": SOURCE_LABEL,
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "content" if content else "metadata",
        },
        "result": None,
        "result_count": 0,
        "warnings": [warning],
    }


def _guard_handle_credentials(
    handle: str,
    root: Path,
    *,
    content: bool,
    mutation: bool,
) -> dict[str, Any] | None:
    """Return a ``credential_path_blocked`` result when ``handle`` resolves to a
    denylisted secret path and the credential override is not set. Returns
    ``None`` when the operation may proceed.
    """

    if _credential_paths_allowed():
        return None
    relative = _relative_for_handle(handle, root)
    if relative is None:
        return None
    if _is_credential_relative(relative):
        return _credential_block_result(content=content, mutation=mutation)
    return None


# ---------------------------------------------------------------------------
# Read-only surface
# ---------------------------------------------------------------------------


def search_filesystem_metadata(
    query: str,
    *,
    root: Path | None = None,
    limit: int = 20,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    payload = _icloud.search_icloud_drive_metadata(
        query,
        root=root,
        limit=limit,
        max_scan_entries=max_scan_entries,
    )
    return _rewrite_payload(payload)


def get_filesystem_metadata(
    handle: str,
    *,
    root: Path | None = None,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    # Metadata (name/size/mtime, no content bytes) is allowed for credential
    # paths so listings still work; no credential guard here.
    payload = _icloud.get_icloud_drive_metadata(
        _to_icloud_handle(handle),
        root=root,
        max_scan_entries=max_scan_entries,
    )
    return _rewrite_payload(payload)


def get_filesystem_root_metadata(
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    payload = _icloud.get_icloud_drive_root_metadata(root=root)
    return _rewrite_payload(payload)


def list_filesystem_folder(
    handle: str,
    *,
    root: Path | None = None,
    limit: int = 20,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
    max_child_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    # Listing returns metadata only (never content bytes), so credential
    # directories may still be listed by name.
    payload = _icloud.list_icloud_drive_folder(
        _to_icloud_handle(handle),
        root=root,
        limit=limit,
        max_scan_entries=max_scan_entries,
        max_child_scan_entries=max_child_scan_entries,
    )
    return _rewrite_payload(payload)


def list_filesystem_folder_tree(
    handle: str,
    *,
    root: Path | None = None,
    depth: int = 2,
    limit: int = 50,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
    max_child_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
    max_directory_scan_entries: int = _icloud.MAX_TREE_DIRECTORY_SCAN_ENTRIES,
    max_tree_scan_entries: int = _icloud.MAX_TREE_DIRECTORY_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    payload = _icloud.list_icloud_drive_folder_tree(
        _to_icloud_handle(handle),
        root=root,
        depth=depth,
        limit=limit,
        max_scan_entries=max_scan_entries,
        max_child_scan_entries=max_child_scan_entries,
        max_directory_scan_entries=max_directory_scan_entries,
        max_tree_scan_entries=max_tree_scan_entries,
    )
    return _rewrite_payload(payload)


def get_filesystem_content(
    handle: str,
    *,
    root: Path | None = None,
    max_chars: int = _icloud.DEFAULT_CONTENT_CHARS,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    blocked = _guard_handle_credentials(
        handle, root, content=True, mutation=False
    )
    if blocked is not None:
        return blocked
    payload = _icloud.get_icloud_drive_content(
        _to_icloud_handle(handle),
        root=root,
        max_chars=max_chars,
        max_scan_entries=max_scan_entries,
    )
    return _rewrite_payload(payload)


def export_filesystem_file(
    handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    root: Path | None = None,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
    max_bytes: int = _icloud.MAX_EXPORT_BYTES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    blocked = _guard_handle_credentials(
        handle, root, content=False, mutation=False
    )
    if blocked is not None:
        return blocked
    payload = _icloud.export_icloud_drive_file(
        _to_icloud_handle(handle),
        output_dir=output_dir,
        filename=filename,
        root=root,
        max_scan_entries=max_scan_entries,
        max_bytes=max_bytes,
    )
    return _rewrite_payload(payload)


# ---------------------------------------------------------------------------
# Plan / apply surface
# ---------------------------------------------------------------------------


def plan_filesystem_change(
    operation: str,
    *,
    parent_handle: str = "",
    handle: str = "",
    filename: str = "",
    folder_components: list[str] | tuple[str, ...] | str | None = None,
    source_file: str | Path = "",
    content_text: str = "",
    expected_current_sha256: str = "",
    root: Path | None = None,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
    include_internal: bool = False,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    blocked = _plan_credential_guard(
        operation,
        parent_handle,
        handle,
        root,
        filename=filename,
        folder_components=folder_components,
    )
    if blocked is not None:
        return blocked
    payload = _icloud.plan_icloud_drive_change(
        operation,
        parent_handle=_to_icloud_handle(parent_handle),
        handle=_to_icloud_handle(handle),
        filename=filename,
        folder_components=folder_components,
        source_file=source_file,
        content_text=content_text,
        expected_current_sha256=expected_current_sha256,
        root=root,
        max_scan_entries=max_scan_entries,
        include_internal=include_internal,
    )
    internal = payload.pop("_internal", None) if isinstance(payload, dict) else None
    rewritten = _rewrite_payload(payload)
    if include_internal and internal is not None:
        rewritten["_internal"] = internal
    return rewritten


def apply_filesystem_change(
    operation: str,
    *,
    parent_handle: str = "",
    handle: str = "",
    filename: str = "",
    folder_components: list[str] | tuple[str, ...] | str | None = None,
    source_file: str | Path = "",
    content_text: str = "",
    expected_current_sha256: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    root: Path | None = None,
    max_scan_entries: int = _icloud.MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_fs_root() if root is None else root
    blocked = _plan_credential_guard(
        operation,
        parent_handle,
        handle,
        root,
        filename=filename,
        folder_components=folder_components,
        mutation=True,
    )
    if blocked is not None:
        return blocked
    payload = _icloud.apply_icloud_drive_change(
        operation,
        parent_handle=_to_icloud_handle(parent_handle),
        handle=_to_icloud_handle(handle),
        filename=filename,
        folder_components=folder_components,
        source_file=source_file,
        content_text=content_text,
        expected_current_sha256=expected_current_sha256,
        approval_token=_to_icloud_approval_token(approval_token),
        confirm_apply=confirm_apply,
        root=root,
        max_scan_entries=max_scan_entries,
    )
    return _rewrite_payload(payload)


def _join_relative(parent_relative: str, name: str) -> str:
    """Join a home-relative POSIX parent path and a child name into a
    home-relative POSIX path, treating the root ("." or "") as empty.
    """

    name = name.strip().strip("/")
    if parent_relative in ("", "."):
        return name
    return f"{parent_relative}/{name}"


def _effective_destination_relatives(
    operation: str,
    parent_handle: str,
    handle: str,
    filename: str,
    folder_components: list[str] | tuple[str, ...] | str | None,
    root: Path,
) -> list[str]:
    """Compute the home-relative POSIX path(s) a mutation will create, rename
    to, or land on — the *effective destination(s)*, not just the input
    handles. These are denylist-checked so a write composed from a
    non-denylisted parent plus a denylisted child name/component cannot slip
    through (e.g. parent ``Library`` + ``Keychains``).

    Parent/source paths are resolved with the within-home resolver, so a
    symlinked parent resolves to its real relative path before the composed
    name is appended — a symlink cannot dodge the composed check.
    """

    op = operation.strip().replace("-", "_")
    destinations: list[str] = []

    # Resolve the parent (create/import/copy/move target parent) and the
    # source handle to their real home-relative paths.
    parent_relative = _relative_for_handle(parent_handle, root) if parent_handle.strip() else None
    source_relative = _relative_for_handle(handle, root) if handle.strip() else None

    name = filename.strip()

    if op in {"create_text", "create_folder", "import_file"}:
        # New entry created as parent + name.
        if parent_relative is not None and name:
            destinations.append(_join_relative(parent_relative, name))
    elif op == "create_folder_path":
        # Each cumulative prefix under the parent, so an intermediate
        # denylisted component (e.g. Library + Keychains) is caught even
        # without the trailing component.
        components: list[str]
        if folder_components is None or folder_components == "":
            components = []
        elif isinstance(folder_components, str):
            components = [folder_components]
        else:
            components = [str(c) for c in folder_components]
        if parent_relative is not None:
            prefix = parent_relative
            for component in components:
                component = component.strip()
                if not component:
                    continue
                prefix = _join_relative(prefix, component)
                destinations.append(prefix)
    elif op in {"rename_folder", "rename_text", "rename_file"}:
        # Rename to a sibling: source's parent + new name.
        if source_relative is not None and name:
            source_parent = Path(source_relative).parent.as_posix()
            destinations.append(_join_relative(source_parent, name))
    elif op in {"copy_folder", "copy_file", "copy_text", "move_folder", "move_file", "move_text"}:
        # Target = target parent (parent_handle) + target name; the target name
        # is the proposed rename or, when absent, the source basename.
        target_name = name or (Path(source_relative).name if source_relative is not None else "")
        if parent_relative is not None and target_name:
            destinations.append(_join_relative(parent_relative, target_name))

    return destinations


def _source_relatives(
    operation: str,
    parent_handle: str,
    handle: str,
    root: Path,
) -> list[str]:
    """Home-relative POSIX path(s) the mutation reads from or acts on in place
    (source handle and, for handle-based in-place ops, the resolved handle).
    A move/copy/rename/trash/delete of a denylisted secret must be refused
    because it reads or removes the secret.
    """

    sources: list[str] = []
    if handle.strip():
        source_relative = _relative_for_handle(handle, root)
        if source_relative is not None:
            sources.append(source_relative)
    if parent_handle.strip():
        parent_relative = _relative_for_handle(parent_handle, root)
        if parent_relative is not None:
            sources.append(parent_relative)
    return sources


def _plan_credential_guard(
    operation: str,
    parent_handle: str,
    handle: str,
    root: Path,
    *,
    filename: str = "",
    folder_components: list[str] | tuple[str, ...] | str | None = None,
    mutation: bool = False,
) -> dict[str, Any] | None:
    """Refuse any mutation that reads from or writes to the credential denylist.

    This checks two path sets, both resolved through the within-home realpath
    resolver so a symlinked parent cannot dodge the check:

    * Source/in-place paths — the resolved ``handle`` and ``parent_handle``.
      A trash/delete/rename/copy/move whose source is a denylisted secret is
      refused because it reads or removes the secret.
    * Effective destination paths — the actual path(s) the op will create,
      rename to, or land on, composed from the resolved parent plus the
      proposed filename, folder components (each cumulative prefix), or target
      name. This closes the compose bypass where a non-denylisted parent (e.g.
      ``Library``) plus a denylisted child (e.g. ``Keychains``) would otherwise
      write inside a sealed credential directory.

    Denylist matching is by path component (via ``_is_credential_relative``),
    case-insensitive, on the composed home-relative path. This is the
    application's own guarantee and does not rely on OS-level protection.
    """

    if _credential_paths_allowed():
        return None

    candidates: list[str] = []
    candidates.extend(_source_relatives(operation, parent_handle, handle, root))
    candidates.extend(
        _effective_destination_relatives(
            operation, parent_handle, handle, filename, folder_components, root
        )
    )
    for relative in candidates:
        if _is_credential_relative(relative):
            return _credential_block_result(content=False, mutation=True)
    return None

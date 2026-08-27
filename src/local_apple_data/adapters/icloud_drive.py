from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality
from .warning_safety import safe_warning_payloads


def _default_icloud_drive_root() -> Path:
    configured = os.environ.get("LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"


DEFAULT_ICLOUD_DRIVE_ROOT = _default_icloud_drive_root()
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_EXPORT_BYTES = 250 * 1024 * 1024
REGULAR_FILE_COPY_CHUNK_BYTES = 1024 * 1024
MAX_PREVIEW_FILENAME_CHARS = 255
MAX_SCAN_ENTRIES = 20000
MAX_TREE_DEPTH = 3
MAX_TREE_RESULTS = 100
MAX_TREE_CHILD_SCAN_ENTRIES = 500
MAX_TREE_DIRECTORY_SCAN_ENTRIES = 2000
MAX_FOLDER_PATH_COMPONENTS = 3
MAX_FOLDER_COPY_TREE_ENTRIES = 500
MAX_FOLDER_COPY_TREE_BYTES = MAX_EXPORT_BYTES
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
    "import_file",
    "replace_file",
    "rename_file",
    "copy_file",
    "move_file",
    "trash_file",
    "delete_file",
    "trash_text",
    "delete_text",
    "rename_text",
    "copy_text",
    "move_text",
}
APPROVAL_TOKEN_PREFIX = "icloud-drive-apply:v1:"
RENAME_SWAP = 0x00000002
RENAME_EXCL = 0x00000004
RENAME_NOFOLLOW_ANY = 0x00000010
TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".htm",
    ".html",
    ".js",
    ".json",
    ".log",
    ".markdown",
    ".md",
    ".py",
    ".sh",
    ".text",
    ".ts",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
PACKAGE_SUFFIXES = {
    ".app",
    ".band",
    ".bundle",
    ".docx",
    ".framework",
    ".key",
    ".numbers",
    ".pages",
    ".pkg",
    ".rtfd",
    ".scptd",
    ".sparsebundle",
    ".workflow",
    ".xcodeproj",
}


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _content_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
    }


def _export_privacy(*, content_exported: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "content_exported": content_exported,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "export",
    }


def _preview_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "preview",
    }


def _mutation_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "mutation",
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "iCloud Drive search requires a non-empty filename query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "iCloud Drive search requires at least two letters or digits.",
            )
        ],
    }


def _unavailable_result(*, content: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "icloud_drive",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": [
            _warning(
                "icloud_drive_unavailable",
                "iCloud Drive root is missing or unreadable.",
            )
        ],
    }


def search_icloud_drive_metadata(
    query: str,
    *,
    root: Path | None = None,
    limit: int = 20,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()
    if not _root_available(root):
        return _unavailable_result()

    bounded_limit = max(1, min(limit, 50))
    results: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    lowered_query = query.casefold()
    for path in _iter_entries(root, max_entries=max_scan_entries):
        scanned += 1
        if lowered_query not in path.name.casefold():
            continue
        results.append(_path_metadata(path, root))
        if len(results) >= bounded_limit:
            break
    else:
        truncated = scanned >= max_scan_entries

    warnings = []
    if truncated:
        warnings.append(
            _warning(
                "scan_truncated",
                "iCloud Drive search stopped at the scan limit.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "query": {
            "scope": "filename",
            "limit": bounded_limit,
            "max_scan_entries": max_scan_entries,
        },
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def get_icloud_drive_metadata(
    handle: str,
    *,
    root: Path | None = None,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    if not is_opaque_handle(handle, "icloud:file"):
        return _invalid_handle_result(content=False)
    if not _root_available(root):
        return _unavailable_result()

    path = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    return {
        "schema_version": 1,
        "status": "ok" if path else "not_found",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "result": _path_metadata(path, root) if path else None,
        "warnings": [],
    }


def get_icloud_drive_root_metadata(
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    if not _root_available(root):
        return _unavailable_result()
    root_path = root.expanduser()
    try:
        root_stat = root_path.lstat()
    except OSError:
        return _unavailable_result()
    if not stat.S_ISDIR(root_stat.st_mode):
        return _unavailable_result()
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "result": _path_metadata(root_path, root_path, path_stat=root_stat),
        "warnings": [],
    }


def list_icloud_drive_folder(
    handle: str,
    *,
    root: Path | None = None,
    limit: int = 20,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
    max_child_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    if not is_opaque_handle(handle, "icloud:file"):
        return _invalid_handle_result(content=False)
    if not _root_available(root):
        return _unavailable_result()

    path = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    if path is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": None,
            "results": [],
            "result_count": 0,
            "warnings": [],
        }
    return _list_resolved_icloud_drive_folder(
        path,
        root=root,
        limit=limit,
        max_child_scan_entries=max_child_scan_entries,
    )


def _list_resolved_icloud_drive_folder(
    path: Path,
    *,
    root: Path,
    limit: int,
    max_child_scan_entries: int,
    expected_metadata_sha256: str | None = None,
) -> dict[str, Any]:
    try:
        selected_stat = path.lstat()
    except OSError:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": None,
            "results": [],
            "result_count": 0,
            "warnings": [],
        }
    parent_metadata = _path_metadata(path, root, path_stat=selected_stat)
    if (
        expected_metadata_sha256
        and parent_metadata.get("metadata_sha256") != expected_metadata_sha256
    ):
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": parent_metadata,
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "child_metadata_changed",
                    "iCloud Drive child folder changed before recursive listing.",
                )
            ],
        }
    if (
        parent_metadata["kind"] != "directory"
        or path.is_symlink()
        or _has_package_component(path, root)
        or _has_symlink_component(path, root)
    ):
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": parent_metadata,
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "unsupported_file_type",
                    "iCloud Drive folder listing requires an exact non-package directory handle.",
                )
            ],
        }

    bounded_limit = max(1, min(limit, 50))
    child_scan_limit = max(1, min(max_child_scan_entries, MAX_SCAN_ENTRIES))
    results: list[dict[str, Any]] = []
    truncated = False
    scan_truncated = False
    folder_fd = -1
    try:
        folder_fd = _open_resolved_directory_no_follow(
            path,
            root,
            expected_stat=selected_stat,
        )
        candidates: list[tuple[str, str, dict[str, Any]]] = []
        scanned = 0
        with os.scandir(folder_fd) as child_entries:
            for child_entry in child_entries:
                scanned += 1
                if scanned > child_scan_limit:
                    scan_truncated = True
                    break
                child_name = child_entry.name
                child_path = path / child_name
                if (
                    child_name.startswith(".")
                    or child_path.suffix.lower() in PACKAGE_SUFFIXES
                ):
                    continue
                try:
                    child_stat = _entry_stat_no_follow_at(folder_fd, child_name)
                except OSError:
                    continue
                if stat.S_ISLNK(child_stat.st_mode):
                    continue
                candidates.append(
                    (
                        child_name.casefold(),
                        child_name,
                        _path_metadata(child_path, root, path_stat=child_stat),
                    )
                )
        candidates.sort(key=lambda item: (item[0], item[1]))
        if len(candidates) > bounded_limit:
            truncated = True
        results = [item[2] for item in candidates[:bounded_limit]]
        final_stat = path.lstat()
        if not _same_stat_identity(selected_stat, final_stat) or not stat.S_ISDIR(
            final_stat.st_mode
        ):
            raise _UnsafeTargetError()
    except _UnsafeTargetError:
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": parent_metadata,
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "read_back_mismatch",
                    "iCloud Drive folder listing target changed before read-back.",
                )
            ],
        }
    except OSError:
        return {
            "schema_version": 1,
            "status": "content_unavailable",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": parent_metadata,
            "results": [],
            "result_count": 0,
            "warnings": [_warning("read_error", "iCloud Drive folder listing was unavailable.")],
        }
    finally:
        if folder_fd >= 0:
            os.close(folder_fd)

    warnings = []
    if truncated:
        warnings.append(
            _warning(
                "result_truncated",
                "iCloud Drive folder listing was truncated to the requested limit.",
            )
        )
    if scan_truncated:
        warnings.append(
            _warning(
                "scan_truncated",
                "iCloud Drive folder listing stopped at the child scan limit.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "query": {
            "scope": "folder_children",
            "limit": bounded_limit,
            "recursive": False,
        },
        "parent": parent_metadata,
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def list_icloud_drive_folder_tree(
    handle: str,
    *,
    root: Path | None = None,
    depth: int = 2,
    limit: int = 50,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
    max_child_scan_entries: int = MAX_SCAN_ENTRIES,
    max_directory_scan_entries: int = MAX_TREE_DIRECTORY_SCAN_ENTRIES,
    max_tree_scan_entries: int = MAX_TREE_DIRECTORY_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    if not is_opaque_handle(handle, "icloud:file"):
        payload = _invalid_handle_result(content=False)
        payload.update({"parent": None, "results": [], "result_count": 0})
        return payload
    if not _root_available(root):
        return _unavailable_result()

    bounded_depth = max(1, min(depth, MAX_TREE_DEPTH))
    bounded_limit = max(1, min(limit, MAX_TREE_RESULTS))
    directory_scan_limit = max(1, min(max_directory_scan_entries, MAX_TREE_DIRECTORY_SCAN_ENTRIES))
    per_directory_child_scan_limit = max(
        1,
        min(max_child_scan_entries, MAX_TREE_CHILD_SCAN_ENTRIES),
    )
    tree_scan_remaining = max(1, min(max_tree_scan_entries, MAX_TREE_DIRECTORY_SCAN_ENTRIES))
    results: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    result_truncated = False
    scan_truncated = False
    child_listing_unavailable = False
    parent_metadata: dict[str, Any] | None = None
    child_metadata_changed = False
    selected_path = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    if selected_path is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _privacy(),
            "parent": None,
            "results": [],
            "result_count": 0,
            "warnings": [],
        }
    queue: list[tuple[str, Path, int, str | None]] = [(handle, selected_path, 0, None)]
    directories_scanned = 0

    while queue and len(results) < bounded_limit:
        if directories_scanned >= directory_scan_limit or tree_scan_remaining <= 0:
            scan_truncated = True
            break
        current_handle, current_path, current_depth, expected_metadata_sha256 = queue.pop(0)
        directories_scanned += 1
        remaining = bounded_limit - len(results)
        child_limit = min(50, remaining)
        child_scan_limit = min(per_directory_child_scan_limit, tree_scan_remaining)
        tree_scan_remaining -= child_scan_limit
        folder = _list_resolved_icloud_drive_folder(
            current_path,
            root=root,
            limit=child_limit,
            max_child_scan_entries=child_scan_limit,
            expected_metadata_sha256=expected_metadata_sha256,
        )
        if current_handle == handle:
            parent_metadata = folder.get("parent")
        if folder["status"] != "ok":
            if current_handle == handle:
                return {
                    "schema_version": 1,
                    "status": folder["status"],
                    "source": "icloud_drive",
                    "privacy": _privacy(),
                    "query": {
                        "scope": "folder_tree",
                        "limit": bounded_limit,
                        "max_depth": bounded_depth,
                        "recursive": True,
                    },
                    "parent": parent_metadata,
                    "results": [],
                    "result_count": 0,
                    "warnings": folder.get("warnings", []),
                }
            folder_warning_codes = {warning["code"] for warning in folder.get("warnings", [])}
            if "child_metadata_changed" in folder_warning_codes:
                child_metadata_changed = True
            else:
                child_listing_unavailable = True
            continue

        folder_warning_codes = {warning["code"] for warning in folder.get("warnings", [])}
        result_truncated = result_truncated or "result_truncated" in folder_warning_codes
        scan_truncated = scan_truncated or "scan_truncated" in folder_warning_codes
        for child in folder["results"]:
            if len(results) >= bounded_limit:
                result_truncated = True
                break
            item = dict(child)
            item["parent_handle"] = current_handle
            item["tree_depth"] = current_depth + 1
            results.append(item)
            if (
                child.get("kind") == "directory"
                and current_depth + 1 < bounded_depth
            ):
                queue.append(
                    (
                        str(child["handle"]),
                        current_path / str(child["name"]),
                        current_depth + 1,
                        str(child.get("metadata_sha256") or ""),
                    )
                )

    if queue:
        if len(results) >= bounded_limit:
            result_truncated = True
        else:
            scan_truncated = True
    if result_truncated:
        warnings.append(
            _warning(
                "result_truncated",
                "iCloud Drive folder tree was truncated to the requested limit.",
            )
        )
    if scan_truncated:
        warnings.append(
            _warning(
                "scan_truncated",
                "iCloud Drive folder tree stopped at a scan limit.",
            )
        )
    if child_listing_unavailable:
        warnings.append(
            _warning(
                "child_listing_unavailable",
                "One or more iCloud Drive child folders could not be listed safely.",
            )
        )
    if child_metadata_changed:
        warnings.append(
            _warning(
                "child_metadata_changed",
                "One or more iCloud Drive child folders changed before recursive listing.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _privacy(),
        "query": {
            "scope": "folder_tree",
            "limit": bounded_limit,
            "max_depth": bounded_depth,
            "recursive": True,
            "directory_scan_limit": directory_scan_limit,
            "child_scan_limit": per_directory_child_scan_limit,
            "tree_scan_limit": max(1, min(max_tree_scan_entries, MAX_TREE_DIRECTORY_SCAN_ENTRIES)),
        },
        "parent": parent_metadata,
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def get_icloud_drive_content(
    handle: str,
    *,
    root: Path | None = None,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    if not is_opaque_handle(handle, "icloud:file"):
        return _invalid_handle_result(content=True)
    if not _root_available(root):
        return _unavailable_result(content=True)

    path = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    if path is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [],
        }

    try:
        selected_parent_stat = path.parent.lstat()
        selected_file_stat = path.lstat()
    except OSError:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [],
        }

    result = _path_metadata(path, root, path_stat=selected_file_stat)
    result.update({"content_text": "", "content_chars": 0, "truncated": False})
    if result["kind"] != "file":
        return _content_unavailable(result, "unsupported_file_type")
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return _content_unavailable(result, "unsupported_file_type")
    if _has_package_component(path, root) or _has_symlink_component(path, root):
        return _content_unavailable(result, "unsupported_file_type")

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    try:
        text = _read_supported_text(
            path,
            root=root,
            expected_parent_stat=selected_parent_stat,
            expected_file_stat=selected_file_stat,
        )
    except OSError:
        return _content_unavailable(result, "read_error")
    except UnicodeDecodeError:
        return _content_unavailable(result, "unsupported_file_type")

    truncated = len(text) > bounded_chars
    content_text = text[:bounded_chars] if truncated else text
    result.update(
        {
            "content_text": content_text,
            "content_chars": len(content_text),
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "truncated": truncated,
        }
    )
    warnings = []
    if truncated:
        warnings.append(
            _warning(
                "content_truncated",
                "iCloud Drive file content was truncated to the requested limit.",
            )
        )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def export_icloud_drive_file(
    handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    root: Path | None = None,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
    max_bytes: int = MAX_EXPORT_BYTES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    if not is_opaque_handle(handle, "icloud:file"):
        return _invalid_export_handle_result()
    if not _root_available(root):
        return _unavailable_export_result()

    path = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    if path is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [],
        }

    try:
        selected_parent_stat = path.parent.lstat()
        selected_file_stat = path.lstat()
    except OSError:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "icloud_drive",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": [],
        }

    result = _path_metadata(path, root, path_stat=selected_file_stat)
    result.update(
        {
            "file_content_returned": False,
            "file_content_exported": False,
            "source_path_returned": False,
            "exported_path": "",
            "exported_filename": "",
            "exported_bytes": 0,
        }
    )
    if result["kind"] != "file" or not stat.S_ISREG(selected_file_stat.st_mode):
        return _export_unavailable_result(result, "unsupported_file_type")
    if _has_package_ancestor(path, root) or _has_symlink_component(path, root):
        return _export_unavailable_result(result, "unsupported_file_type")

    target_dir = output_dir.expanduser()
    if target_dir.is_symlink() or (target_dir.exists() and not target_dir.is_dir()):
        return _export_unavailable_result(result, "invalid_output_dir")
    if _path_is_within(target_dir.resolve(strict=False), root.expanduser().resolve(strict=False)):
        return _export_unavailable_result(result, "output_dir_in_icloud_root")

    try:
        requested_max_bytes = int(max_bytes)
    except (TypeError, ValueError):
        return _export_unavailable_result(result, "invalid_byte_limit")
    if requested_max_bytes <= 0:
        return _export_unavailable_result(result, "invalid_byte_limit")
    bounded_max_bytes = min(requested_max_bytes, MAX_EXPORT_BYTES)
    try:
        data = _read_export_file_bytes_no_follow(
            path,
            root=root,
            max_bytes=bounded_max_bytes,
            expected_parent_stat=selected_parent_stat,
            expected_file_stat=selected_file_stat,
        )
        target_dir_fd, stable_target_dir = _open_export_directory_no_follow(target_dir, root=root)
        try:
            target = _write_unique_export_file_at(
                target_dir_fd,
                stable_target_dir,
                _export_filename(filename, result["name"]),
                data,
            )
        finally:
            os.close(target_dir_fd)
    except ICloudDriveExportTooLarge:
        return _export_unavailable_result(result, "file_too_large")
    except ICloudDriveOutputDirectoryInsideRoot:
        return _export_unavailable_result(result, "output_dir_in_icloud_root")
    except ICloudDriveInvalidOutputDirectory:
        return _export_unavailable_result(result, "invalid_output_dir")
    except (OSError, ValueError):
        return _export_unavailable_result(result, "icloud_drive_export_failed")

    result.update(
        {
            "file_content_exported": True,
            "exported_path": str(target),
            "exported_filename": target.name,
            "exported_bytes": len(data),
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _export_privacy(content_exported=True),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def plan_icloud_drive_change(
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
    max_scan_entries: int = MAX_SCAN_ENTRIES,
    include_internal: bool = False,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation create_text, append_text, replace_text, create_folder, create_folder_path, rename_folder, trash_folder, delete_folder, move_folder, copy_folder, import_file, replace_file, rename_file, copy_file, move_file, trash_file, delete_file, trash_text, delete_text, rename_text, copy_text, or move_text.",
            )
        )

    normalized_parent_handle = parent_handle.strip()
    normalized_handle = handle.strip()
    if normalized_operation not in {"import_file", "replace_file"} and str(source_file).strip():
        warnings.append(
            _warning(
                "unexpected_source_file",
                "Only import-file and replace-file planning accept source_file.",
            )
        )
    if normalized_operation in {"create_text", "create_folder", "import_file"} and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Expected icloud:file:v1 opaque directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "create_folder_path" and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Expected icloud:file:v1 opaque directory handle from iCloud Drive search output.",
            )
        )
    text_handle_operations = {
        "append_text",
        "replace_text",
        "trash_text",
        "delete_text",
        "rename_text",
        "copy_text",
        "move_text",
    }
    folder_handle_operations = {"rename_folder", "trash_folder", "delete_folder", "move_folder", "copy_folder"}
    file_handle_operations = {"replace_file", "rename_file", "copy_file", "move_file", "trash_file", "delete_file"}
    if normalized_operation in text_handle_operations and not is_opaque_handle(
        normalized_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected icloud:file:v1 opaque file handle from iCloud Drive search output.",
            )
        )
    if normalized_operation in folder_handle_operations and not is_opaque_handle(
        normalized_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected icloud:file:v1 opaque directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation in folder_handle_operations and _is_root_handle(normalized_handle):
        warnings.append(
            _warning(
                "unsupported_file_type",
                "iCloud Drive root folder cannot be used as a rename, trash, delete, move, or copy source.",
            )
        )
    if normalized_operation in file_handle_operations and not is_opaque_handle(
        normalized_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected icloud:file:v1 opaque regular-file handle from iCloud Drive search output.",
            )
        )
    if normalized_operation in {"create_text", "create_folder", "create_folder_path", "import_file"} and normalized_handle:
        warnings.append(
            _warning(
                "unexpected_handle",
                "Create/import planning requires a parent handle, not a file handle.",
            )
        )
    if normalized_operation in {"append_text", "replace_text", "trash_text", "delete_text", "trash_folder", "delete_folder", "trash_file", "delete_file"} and (
        normalized_parent_handle or filename.strip()
    ):
        warnings.append(
            _warning(
                "unexpected_create_target",
                "Append/replace/trash/delete planning requires a file or folder handle, not a parent handle or filename.",
            )
        )
    if normalized_operation == "rename_text" and normalized_parent_handle:
        warnings.append(
            _warning(
                "unexpected_parent_handle",
                "Rename planning keeps the same parent directory and does not accept parent_handle.",
            )
        )
    if normalized_operation == "rename_folder" and normalized_parent_handle:
        warnings.append(
            _warning(
                "unexpected_parent_handle",
                "Folder rename planning keeps the same parent directory and does not accept parent_handle.",
            )
        )
    if normalized_operation == "rename_file" and normalized_parent_handle:
        warnings.append(
            _warning(
                "unexpected_parent_handle",
                "Regular-file rename planning keeps the same parent directory and does not accept parent_handle.",
            )
        )
    if normalized_operation == "replace_file" and (normalized_parent_handle or filename.strip()):
        warnings.append(
            _warning(
                "unexpected_create_target",
                "Regular-file replace planning requires a file handle, not a parent handle or filename.",
            )
        )
    if normalized_operation == "copy_text" and normalized_parent_handle and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Expected icloud:file:v1 opaque directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "move_text" and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Move planning requires an exact icloud:file:v1 directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "move_folder" and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Move-folder planning requires an exact icloud:file:v1 directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "copy_folder" and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Copy-folder planning requires an exact icloud:file:v1 directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "copy_file" and normalized_parent_handle and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Expected icloud:file:v1 opaque directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "move_file" and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Move-file planning requires an exact icloud:file:v1 directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation in {"create_text", "create_folder", "create_folder_path", "import_file"} and expected_current_sha256.strip():
        warnings.append(
            _warning(
                "unexpected_expected_current_sha256",
                "Create/import planning does not accept expected_current_sha256.",
            )
        )

    normalized_filename = ""
    normalized_folder_components: list[str] = []
    import_source: dict[str, Any] = {}
    replace_source: dict[str, Any] = {}
    if folder_components and normalized_operation != "create_folder_path":
        warnings.append(
            _warning(
                "unexpected_folder_components",
                "folder_components is only supported for create-folder-path.",
            )
        )
    if normalized_operation == "create_text":
        normalized_filename, filename_warning = _normalize_create_filename(filename)
        if filename_warning is not None:
            warnings.append(filename_warning)
    if normalized_operation == "create_folder":
        normalized_filename, folder_warning = _normalize_create_folder_name(filename)
        if folder_warning is not None:
            warnings.append(folder_warning)
        if content_text:
            warnings.append(
                _warning(
                    "unexpected_content_text",
                    "Create-folder planning does not accept content_text.",
                )
            )
    if normalized_operation == "create_folder_path":
        normalized_folder_components, components_warning = _normalize_folder_components(folder_components)
        if components_warning is not None:
            warnings.append(components_warning)
        if filename.strip():
            warnings.append(
                _warning(
                    "unexpected_filename",
                    "Create-folder-path planning requires folder_components, not filename.",
                )
            )
        if content_text:
            warnings.append(
                _warning(
                    "unexpected_content_text",
                    "Create-folder-path planning does not accept content_text.",
                )
            )
    if normalized_operation == "import_file":
        import_source = _import_source_file_metadata(source_file, root=root)
        warnings.extend(import_source.pop("warnings"))
        if filename.strip():
            normalized_filename, filename_warning = _normalize_regular_file_name(filename)
        else:
            normalized_filename, filename_warning = _normalize_regular_file_name(str(import_source.get("filename") or ""))
        if filename_warning is not None:
            warnings.append(filename_warning)
        if content_text:
            warnings.append(
                _warning(
                    "unexpected_content_text",
                    "Import-file planning does not accept content_text.",
                )
            )
    if normalized_operation == "replace_file":
        replace_source = _import_source_file_metadata(source_file, root=root)
        warnings.extend(replace_source.pop("warnings"))
    if normalized_operation == "rename_folder":
        normalized_filename, folder_warning = _normalize_create_folder_name(filename)
        if folder_warning is not None:
            warnings.append(folder_warning)
    if normalized_operation == "move_folder" and filename.strip():
        normalized_filename, folder_warning = _normalize_create_folder_name(filename)
        if folder_warning is not None:
            warnings.append(folder_warning)
    if normalized_operation == "copy_folder" and filename.strip():
        normalized_filename, folder_warning = _normalize_create_folder_name(filename)
        if folder_warning is not None:
            warnings.append(folder_warning)
    if normalized_operation in {"rename_file", "copy_file"}:
        normalized_filename, filename_warning = _normalize_regular_file_name(filename)
        if filename_warning is not None:
            warnings.append(filename_warning)
    if normalized_operation == "move_file" and filename.strip():
        normalized_filename, filename_warning = _normalize_regular_file_name(filename)
        if filename_warning is not None:
            warnings.append(filename_warning)
    if normalized_operation in {"trash_text", "delete_text", "trash_folder", "delete_folder", "trash_file", "delete_file"} and content_text:
        warnings.append(
            _warning(
                "unexpected_content_text",
                "Trash/delete planning does not accept content_text.",
            )
        )
    if normalized_operation in {"rename_text", "copy_text"}:
        normalized_filename, filename_warning = _normalize_create_filename(filename)
        if filename_warning is not None:
            warnings.append(filename_warning)
    if normalized_operation == "move_text" and filename.strip():
        normalized_filename, filename_warning = _normalize_create_filename(filename)
        if filename_warning is not None:
            warnings.append(filename_warning)
    if normalized_operation in {"rename_text", "copy_text", "move_text", "rename_folder", "move_folder", "copy_folder", "replace_file", "rename_file", "copy_file", "move_file"} and content_text:
        warnings.append(
            _warning(
                "unexpected_content_text",
                "Rename/copy/move/replace-file planning does not accept content_text.",
            )
        )

    normalized_content = ""
    if normalized_operation in {"create_text", "append_text", "replace_text"}:
        normalized_content, content_warning = _normalize_create_text(content_text)
        if content_warning is not None:
            warnings.append(content_warning)

    normalized_expected_sha = ""
    if normalized_operation in text_handle_operations | folder_handle_operations | file_handle_operations:
        normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
        if sha_warning is not None:
            warnings.append(sha_warning)

    if warnings:
        return _plan_error(warnings)

    delete_text_identity_sha256 = ""
    folder_tree_sha256 = ""
    parent_identity_sha256 = ""
    parent_create_operations = {"create_text", "create_folder", "create_folder_path", "import_file"}
    if normalized_operation in parent_create_operations:
        parent_identity = _resolve_create_parent_identity_sha256(
            normalized_parent_handle,
            root=root,
            max_scan_entries=max_scan_entries,
        )
        if isinstance(parent_identity, dict):
            return _plan_error([parent_identity])
        parent_identity_sha256 = parent_identity
    if normalized_operation == "delete_text":
        identity = _resolve_delete_text_plan_identity(
            normalized_handle,
            root=root,
            max_scan_entries=max_scan_entries,
        )
        if isinstance(identity, dict):
            return _plan_error([identity])
        delete_text_identity_sha256 = identity
    if normalized_operation == "copy_folder":
        source = _resolve_handle(
            normalized_handle,
            root,
            max_scan_entries=max_scan_entries,
        )
        if source is None:
            return _plan_error([_warning("target_not_found", "iCloud Drive source folder was not found.")])
        if _is_root_path(source, root):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive root folder cannot be copied.")]
            )
        if source.is_symlink() or not _is_directory_no_follow(source):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive folder copy requires an exact directory handle.")]
            )
        if _has_package_component(source, root) or _has_symlink_component(source, root):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive folder copy source must not traverse packages or symlinks.")]
            )
        try:
            folder_tree_sha256, _copy_tree_empty = _folder_copy_tree_fingerprint(
                source,
                root,
                max_entries=MAX_FOLDER_COPY_TREE_ENTRIES,
            )
        except _FolderCopyTooLargeError:
            return _plan_error(
                [_warning("folder_tree_too_large", "iCloud Drive folder copy is limited to bounded selected-folder trees.")]
            )
        except (_UnsafeTargetError, OSError):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive folder copy source must not contain hidden, package, symlink, or unsupported entries.")]
            )
    if normalized_operation == "delete_folder":
        source = _resolve_handle(
            normalized_handle,
            root,
            max_scan_entries=max_scan_entries,
        )
        if source is None:
            return _plan_error([_warning("target_not_found", "iCloud Drive target folder was not found.")])
        if _is_root_path(source, root):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive root folder cannot be deleted.")]
            )
        if source.is_symlink() or not _is_directory_no_follow(source):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive folder delete requires an exact directory handle.")]
            )
        if _has_package_component(source, root) or _has_symlink_component(source, root):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive folder delete target must not traverse packages or symlinks.")]
            )
        try:
            folder_tree_sha256, _delete_tree_empty = _folder_copy_tree_fingerprint(
                source,
                root,
                max_entries=MAX_FOLDER_COPY_TREE_ENTRIES,
            )
        except _FolderCopyTooLargeError:
            return _plan_error(
                [_warning("folder_tree_too_large", "iCloud Drive folder delete is limited to bounded selected-folder trees.")]
            )
        except (_UnsafeTargetError, OSError):
            return _plan_error(
                [_warning("unsupported_file_type", "iCloud Drive folder delete target must not contain hidden, package, symlink, or unsupported entries.")]
            )

    if normalized_operation == "create_text":
        target = {
            "parent_handle": normalized_parent_handle,
            "expected_parent_identity_sha256": parent_identity_sha256,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "content_chars": len(normalized_content),
            "extension": Path(normalized_filename).suffix.lower() or None,
        }
    elif normalized_operation == "create_folder":
        target = {
            "parent_handle": normalized_parent_handle,
            "expected_parent_identity_sha256": parent_identity_sha256,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "directory",
            "content": "blocked",
            "overwrite": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "create_folder_path":
        target = {
            "parent_handle": normalized_parent_handle,
            "expected_parent_identity_sha256": parent_identity_sha256,
            "folder_components": normalized_folder_components,
        }
        proposed = {
            "kind": "directory_path",
            "component_count": len(normalized_folder_components),
            "existing_directories": "allowed",
            "content": "blocked",
            "overwrite": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "rename_folder":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "directory",
            "rename_to": normalized_filename,
            "empty_folder_required": False,
            "non_empty_allowed": True,
            "overwrite": "blocked",
            "recursive_content_read": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "trash_folder":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "directory",
            "move_to_trash": True,
            "empty_folder_required": False,
            "non_empty_allowed": True,
            "permanent_delete": "blocked",
            "recursive_delete": "blocked",
            "recursive_content_read": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "delete_folder":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "directory",
            "permanent_delete": True,
            "empty_folder_required": False,
            "non_empty_allowed": True,
            "recursive_delete": "bounded_private_tree",
            "source_tree_binding": "private",
            "trash_fallback": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "move_folder":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "parent_handle": normalized_parent_handle,
            "filename": normalized_filename or None,
        }
        proposed = {
            "kind": "directory",
            "move_to_parent": "exact_handle",
            "move_to_name": normalized_filename or "source_name",
            "empty_folder_required": False,
            "non_empty_allowed": True,
            "overwrite": "blocked",
            "recursive_content_read": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "copy_folder":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "parent_handle": normalized_parent_handle,
            "filename": normalized_filename or None,
        }
        proposed = {
            "kind": "directory",
            "copy_to_parent": "exact_handle",
            "copy_to_name": normalized_filename or "source_name",
            "empty_folder_required": False,
            "non_empty_allowed": True,
            "overwrite": "blocked",
            "recursive_copy": "bounded_private_tree",
            "source_tree_binding": "private",
            "source_mutation": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "import_file":
        target = {
            "parent_handle": normalized_parent_handle,
            "expected_parent_identity_sha256": parent_identity_sha256,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "source_filename": import_source["filename"],
            "source_size_bytes": import_source["file_size_bytes"],
            "source_path_returned": False,
            "source_hash_returned": False,
            "overwrite": "blocked",
            "source_mutation": "blocked",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "replace_file":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "replace_from_source_filename": replace_source["filename"],
            "source_size_bytes": replace_source["file_size_bytes"],
            "source_path_returned": False,
            "source_hash_returned": False,
            "target_name_preserved": True,
            "source_mutation": "blocked",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "rename_file":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "rename_to": normalized_filename,
            "overwrite": "blocked",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "copy_file":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "parent_handle": normalized_parent_handle or None,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "copy_to_filename": normalized_filename,
            "target_parent": "same_parent" if not normalized_parent_handle else "exact_handle",
            "overwrite": "blocked",
            "source_mutation": "blocked",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "move_file":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "parent_handle": normalized_parent_handle,
            "filename": normalized_filename or None,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "move_to_parent": "exact_handle",
            "rename_to": normalized_filename or None,
            "overwrite": "blocked",
            "permanent_delete": "blocked",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "trash_file":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "move_to_trash": True,
            "permanent_delete": "blocked",
            "source_mutation": "recoverable_trash",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "delete_file":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "file",
            "content_type": "regular_file",
            "permanent_delete": True,
            "recoverable_trash": "blocked",
            "content_return": "blocked",
            "content_hash_return": "blocked",
        }
    elif normalized_operation == "append_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "append_chars": len(normalized_content),
            "append_content_sha256": hashlib.sha256(normalized_content.encode("utf-8")).hexdigest(),
            "overwrite": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "replace_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "replace_chars": len(normalized_content),
            "replace_content_sha256": hashlib.sha256(normalized_content.encode("utf-8")).hexdigest(),
            "append": "blocked",
            "delete": "blocked",
        }
    elif normalized_operation == "trash_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "move_to_trash": True,
            "permanent_delete": "blocked",
            "folder_delete": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "delete_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "expected_file_identity_sha256": delete_text_identity_sha256,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "permanent_delete": True,
            "trash_fallback": "blocked",
            "folder_delete": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "rename_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "rename_to": normalized_filename,
            "overwrite": "blocked",
            "content_return": "blocked",
        }
    elif normalized_operation == "copy_text":
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "parent_handle": normalized_parent_handle or None,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "copy_to_filename": normalized_filename,
            "target_parent": "same_parent" if not normalized_parent_handle else "exact_handle",
            "overwrite": "blocked",
            "source_mutation": "blocked",
            "content_return": "blocked",
        }
    else:
        target = {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "parent_handle": normalized_parent_handle,
            "filename": normalized_filename or None,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "move_to_parent": "exact_handle",
            "rename_to": normalized_filename or None,
            "overwrite": "blocked",
            "permanent_delete": "blocked",
            "content_return": "blocked",
        }
    fingerprint_target = dict(target)
    if normalized_operation == "import_file":
        fingerprint_target.update(
            {
                "source_identity_sha256": import_source["source_identity_sha256"],
                "source_content_sha256": import_source["source_content_sha256"],
            }
        )
    if normalized_operation == "replace_file":
        fingerprint_target.update(
            {
                "source_identity_sha256": replace_source["source_identity_sha256"],
                "source_content_sha256": replace_source["source_content_sha256"],
            }
        )
    if normalized_operation in {"copy_folder", "delete_folder"}:
        fingerprint_target["source_tree_sha256"] = folder_tree_sha256
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": fingerprint_target,
        "proposed": _fingerprint_proposed(
            normalized_operation,
            proposed,
            normalized_content,
        ),
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    result = {
        "schema_version": 1,
        "status": "ok",
        "source": "icloud_drive",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }
    if include_internal and normalized_operation == "import_file":
        result["_internal"] = {"import_source": import_source}
    if include_internal and normalized_operation == "replace_file":
        result["_internal"] = {"replace_source": replace_source}
    if include_internal and normalized_operation == "copy_folder":
        result["_internal"] = {"copy_source_tree_sha256": folder_tree_sha256}
    if include_internal and normalized_operation == "delete_folder":
        result["_internal"] = {"delete_source_tree_sha256": folder_tree_sha256}
    return result


def apply_icloud_drive_change(
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
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    # Resolve first: callers below pass `root` into guards before delegating.
    root = _default_icloud_drive_root() if root is None else root
    plan = plan_icloud_drive_change(
        operation,
        parent_handle=parent_handle,
        handle=handle,
        filename=filename,
        folder_components=folder_components,
        source_file=source_file,
        content_text=content_text,
        expected_current_sha256=expected_current_sha256,
        root=root,
        max_scan_entries=max_scan_entries,
        include_internal=True,
    )
    internal = plan.pop("_internal", {}) if isinstance(plan, dict) else {}
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)
    preview = plan["preview"]
    approval = preview["approval"]
    expected_token = _approval_token(str(approval["approval_fingerprint"]))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "iCloud Drive apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "iCloud Drive apply approval token did not match the plan.")],
            plan=plan,
        )
    if not _root_writable(root):
        return _apply_error(
            [_warning("icloud_drive_unavailable", "iCloud Drive root is missing or not writable.")],
            plan=plan,
            status="degraded",
        )

    normalized_operation = str(preview["operation"])
    if normalized_operation == "append_text":
        return _apply_append_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            content_text=content_text,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "replace_text":
        return _apply_replace_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            content_text=content_text,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "create_folder":
        return _apply_create_folder(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "create_folder_path":
        return _apply_create_folder_path(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "rename_folder":
        return _apply_rename_folder(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "trash_folder":
        return _apply_trash_folder(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "delete_folder":
        return _apply_delete_folder(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
            source_tree_sha256=str(internal.get("delete_source_tree_sha256") or ""),
        )
    if normalized_operation == "move_folder":
        return _apply_move_folder(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "copy_folder":
        return _apply_copy_folder(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
            source_tree_sha256=str(internal.get("copy_source_tree_sha256") or ""),
        )
    if normalized_operation == "import_file":
        return _apply_import_file(
            preview,
            source_info=internal.get("import_source") if isinstance(internal, dict) else None,
            source_file=source_file,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "replace_file":
        return _apply_replace_file(
            preview,
            source_info=internal.get("replace_source") if isinstance(internal, dict) else None,
            source_file=source_file,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "rename_file":
        return _apply_rename_file(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "copy_file":
        return _apply_copy_file(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "move_file":
        return _apply_move_file(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "trash_file":
        return _apply_trash_file(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "delete_file":
        return _apply_delete_file(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "trash_text":
        return _apply_trash_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "delete_text":
        return _apply_delete_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "rename_text":
        return _apply_rename_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "copy_text":
        return _apply_copy_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )
    if normalized_operation == "move_text":
        return _apply_move_text(
            preview,
            root=root,
            max_scan_entries=max_scan_entries,
            approval_fingerprint=approval["approval_fingerprint"],
        )

    parent = _resolve_handle(parent_handle.strip(), root, max_scan_entries=max_scan_entries)
    if parent is None or parent.is_symlink() or not _is_directory_no_follow(parent):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan=plan,
            status="not_found",
        )
    if _has_package_component(parent, root) or _has_symlink_component(parent, root):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan=plan,
            status="not_found",
        )
    if _parent_identity_changed(preview, parent, root):
        return _apply_error(
            [_warning("parent_identity_changed", "iCloud Drive parent directory changed after planning.")],
            plan=plan,
        )
    target = parent / preview["target"]["filename"]
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan=plan,
        )
    if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive create target must not traverse packages or symlinks.")],
            plan=plan,
        )
    normalized_content, _ = _normalize_create_text(content_text)
    target_exists = False
    parent_fd = -1
    try:
        parent_fd = _open_directory_no_follow(parent)
        existing = _read_supported_text_at(parent_fd, target.name)
        target_exists = True
    except FileNotFoundError:
        existing = None
    except (OSError, UnicodeDecodeError):
        existing = None
        target_exists = True
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
    if target_exists:
        content_inspected = existing is not None
        try:
            existing_matches = existing == normalized_content
        except UnicodeEncodeError:
            existing_matches = False
        if existing_matches:
            return _apply_success(
                target,
                root=root,
                idempotency_key=preview["idempotency_key"],
                approval_fingerprint=approval["approval_fingerprint"],
                operation=normalized_operation,
                mutation_applied=False,
                warnings=[_warning("already_applied", "iCloud Drive file already exists with matching content.")],
            )
        return _apply_error(
            [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
            plan=plan,
            content_inspected=content_inspected,
        )
    try:
        _create_text_no_follow(parent, target.name, normalized_content)
    except FileExistsError:
        return _apply_error(
            [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
            plan=plan,
        )
    except OSError:
        return _apply_error(
            [_warning("write_error", "iCloud Drive file could not be created safely.")],
            plan=plan,
        )
    return _apply_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval["approval_fingerprint"],
        operation=normalized_operation,
        mutation_applied=True,
        expected_content_sha256=hashlib.sha256(normalized_content.encode("utf-8")).hexdigest(),
        warnings=[],
    )


def _invalid_handle_result(*, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected icloud:file:v1 opaque handle from search output.",
            )
        ],
    }


def _invalid_export_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": _export_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected icloud:file:v1 opaque handle from search output.",
            )
        ],
    }


def _content_unavailable(result: dict[str, Any], code: str) -> dict[str, Any]:
    messages = {
        "read_error": "iCloud Drive file content could not be read safely.",
        "unsupported_file_type": "iCloud Drive file type is not supported for plain-text extraction.",
    }
    return {
        "schema_version": 1,
        "status": "content_unavailable",
        "source": "icloud_drive",
        "privacy": _content_privacy(content_inspected=False),
        "result": result,
        "warnings": [_warning(code, messages[code])],
    }


def _unavailable_export_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "icloud_drive",
        "privacy": _export_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "icloud_drive_unavailable",
                "iCloud Drive root is missing or unreadable.",
            )
        ],
    }


def _export_unavailable_result(result: dict[str, Any], code: str) -> dict[str, Any]:
    messages = {
        "file_too_large": "iCloud Drive file exceeds the exact export byte cap.",
        "icloud_drive_export_failed": "iCloud Drive file could not be exported safely.",
        "invalid_byte_limit": "iCloud Drive export byte cap must be an integer.",
        "invalid_output_dir": "iCloud Drive export output path was not a directory.",
        "output_dir_in_icloud_root": (
            "iCloud Drive export output directory must be outside the configured iCloud Drive root."
        ),
        "unsupported_file_type": "iCloud Drive export supports only regular non-package files.",
    }
    return {
        "schema_version": 1,
        "status": "export_unavailable",
        "source": "icloud_drive",
        "privacy": _export_privacy(),
        "result": result,
        "warnings": [_warning(code, messages.get(code, "iCloud Drive export was unavailable."))],
    }


def _root_available(root: Path) -> bool:
    try:
        return root.expanduser().is_dir() and os.access(root.expanduser(), os.R_OK)
    except OSError:
        return False


def _root_writable(root: Path) -> bool:
    try:
        expanded = root.expanduser()
        return expanded.is_dir() and os.access(expanded, os.R_OK | os.W_OK | os.X_OK)
    except OSError:
        return False


def _iter_entries(root: Path, *, max_entries: int):
    root = root.expanduser()
    yielded = 0
    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(current_root)
        safe_dirnames = []
        for dirname in sorted(dirnames):
            path = current / dirname
            if dirname.startswith(".") or path.suffix.lower() in PACKAGE_SUFFIXES:
                continue
            if path.is_symlink():
                continue
            safe_dirnames.append(dirname)
        dirnames[:] = safe_dirnames
        for dirname in safe_dirnames:
            path = current / dirname
            yield path
            yielded += 1
            if yielded >= max_entries:
                return
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = current / name
            if path.is_symlink():
                continue
            yield path
            yielded += 1
            if yielded >= max_entries:
                return


def _path_metadata(path: Path, root: Path, *, path_stat: os.stat_result | None = None) -> dict[str, Any]:
    path_stat = path_stat if path_stat is not None else path.lstat()
    mode = path_stat.st_mode
    is_file = stat.S_ISREG(mode)
    is_directory = stat.S_ISDIR(mode)
    relative = _relative_path(path, root)
    metadata = {
        "handle": make_opaque_handle("icloud:file", relative),
        "name": path.name,
        "extension": path.suffix.lower() or None,
        "kind": "file" if is_file else "directory" if is_directory else "other",
        "size": path_stat.st_size if is_file else None,
        "modified": int(path_stat.st_mtime),
        "depth": len(Path(relative).parts),
    }
    if relative == ".":
        metadata["is_root"] = True
    if is_directory:
        metadata["metadata_sha256"] = _directory_metadata_sha256_from_stat(path, root, path_stat)
    if is_file:
        metadata["metadata_sha256"] = _file_metadata_sha256_from_stat(path, root, path_stat)
    return metadata


def _directory_metadata_sha256(path: Path, root: Path) -> str:
    return _directory_metadata_sha256_from_stat(path, root, path.lstat())


def _directory_identity_sha256(path: Path, root: Path) -> str:
    return _directory_identity_sha256_from_stat(path, root, path.lstat())


def _directory_identity_sha256_from_stat(path: Path, root: Path, path_stat: os.stat_result) -> str:
    payload = {
        "relative": _relative_path(path, root),
        "name": path.name,
        "kind": "directory",
        "mode": stat.S_IFMT(path_stat.st_mode),
        "dev": path_stat.st_dev,
        "ino": path_stat.st_ino,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _directory_metadata_sha256_from_stat(path: Path, root: Path, path_stat: os.stat_result) -> str:
    payload = {
        "relative": _relative_path(path, root),
        "name": path.name,
        "kind": "directory",
        "mode": stat.S_IFMT(path_stat.st_mode),
        "size": path_stat.st_size,
        "mtime_ns": path_stat.st_mtime_ns,
        "ctime_ns": path_stat.st_ctime_ns,
        "dev": path_stat.st_dev,
        "ino": path_stat.st_ino,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _delete_text_identity_sha256(path: Path, root: Path) -> str:
    return _delete_text_identity_sha256_from_stat(path, root, path.lstat())


def _file_metadata_sha256(path: Path, root: Path) -> str:
    return _file_metadata_sha256_from_stat(path, root, path.lstat())


def _file_metadata_sha256_from_stat(path: Path, root: Path, path_stat: os.stat_result) -> str:
    payload = {
        "relative": _relative_path(path, root),
        "name": path.name,
        "kind": "file",
        "mode": stat.S_IFMT(path_stat.st_mode),
        "size": path_stat.st_size,
        "mtime_ns": path_stat.st_mtime_ns,
        "ctime_ns": path_stat.st_ctime_ns,
        "dev": path_stat.st_dev,
        "ino": path_stat.st_ino,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _delete_text_identity_sha256_from_stat(path: Path, root: Path, path_stat: os.stat_result) -> str:
    payload = {
        "relative": _relative_path(path, root),
        "name": path.name,
        "kind": "file",
        "mode": stat.S_IFMT(path_stat.st_mode),
        "size": path_stat.st_size,
        "mtime_ns": path_stat.st_mtime_ns,
        "ctime_ns": path_stat.st_ctime_ns,
        "dev": path_stat.st_dev,
        "ino": path_stat.st_ino,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_delete_text_plan_identity(
    handle: str,
    *,
    root: Path,
    max_scan_entries: int,
) -> str | dict[str, str]:
    target = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    if target is None or target.is_symlink() or not target.is_file():
        return _warning("target_file_not_found", "iCloud Drive target file was not found.")
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _warning("target_outside_root", "iCloud Drive target escaped the configured root.")
    if target.suffix.lower() not in TEXT_SUFFIXES:
        return _warning("unsupported_file_type", "iCloud Drive delete target must be a supported text-like file.")
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _warning("unsupported_file_type", "iCloud Drive delete target must not traverse packages or symlinks.")
    return _delete_text_identity_sha256(target, root)


def _resolve_create_parent_identity_sha256(
    handle: str,
    *,
    root: Path,
    max_scan_entries: int,
) -> str | dict[str, str]:
    parent = _resolve_handle(handle, root, max_scan_entries=max_scan_entries)
    if parent is None or parent.is_symlink() or not _is_directory_no_follow(parent):
        return _warning("target_parent_not_found", "iCloud Drive parent directory was not found.")
    if _has_package_component(parent, root) or _has_symlink_component(parent, root):
        return _warning("target_parent_not_found", "iCloud Drive parent directory was not found.")
    return _directory_identity_sha256(parent, root)


def _parent_identity_changed(preview: dict[str, Any], parent: Path, root: Path) -> bool:
    expected_parent_sha = str(preview["target"].get("expected_parent_identity_sha256") or "")
    if not expected_parent_sha:
        return False
    try:
        current_parent_sha = _directory_identity_sha256(parent, root)
    except (OSError, ValueError):
        return True
    return current_parent_sha != expected_parent_sha


def _resolve_handle(handle: str, root: Path, *, max_scan_entries: int) -> Path | None:
    expanded_root = root.expanduser()
    if _is_root_handle(handle):
        return expanded_root
    for path in _iter_entries(root, max_entries=max_scan_entries):
        relative = _relative_path(path, root)
        if opaque_handle_matches(handle, "icloud:file", relative):
            return path
    return None


def _is_root_handle(handle: str) -> bool:
    return opaque_handle_matches(handle, "icloud:file", ".")


def _is_root_path(path: Path, root: Path) -> bool:
    try:
        return _relative_path(path, root) == "."
    except ValueError:
        return False


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root.expanduser()).as_posix()


def _has_package_component(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root.expanduser())
    except ValueError:
        return True
    parts = relative.parts[:-1] if path.suffix.lower() in TEXT_SUFFIXES else relative.parts
    return any(Path(part).suffix.lower() in PACKAGE_SUFFIXES for part in parts)


def _has_package_ancestor(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root.expanduser())
    except ValueError:
        return True
    return any(Path(part).suffix.lower() in PACKAGE_SUFFIXES for part in relative.parts[:-1])


def _has_symlink_component(path: Path, root: Path) -> bool:
    root = root.expanduser()
    try:
        if root.is_symlink():
            return True
    except OSError:
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _has_symlink_parent_component(path: Path, root: Path) -> bool:
    root = root.expanduser()
    try:
        if root.is_symlink():
            return True
    except OSError:
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _absolute_existing_no_symlink_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if not absolute.name:
        raise OSError("missing source file")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        entry_stat = current.lstat()
        if stat.S_ISLNK(entry_stat.st_mode):
            raise _UnsafeTargetError()
    return absolute


def _has_package_component_absolute(path: Path) -> bool:
    return any(Path(part).suffix.lower() in PACKAGE_SUFFIXES for part in path.parts)


def _import_source_identity_sha256(path: Path, path_stat: os.stat_result, content_sha256: str) -> str:
    payload = {
        "path": str(path),
        "name": path.name,
        "kind": "file",
        "mode": stat.S_IFMT(path_stat.st_mode),
        "size": path_stat.st_size,
        "mtime_ns": path_stat.st_mtime_ns,
        "ctime_ns": path_stat.st_ctime_ns,
        "dev": path_stat.st_dev,
        "ino": path_stat.st_ino,
        "content_sha256": content_sha256,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_directory_no_follow(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _read_file_bytes_no_follow(
    path: Path,
    *,
    root: Path | None = None,
    expected_parent_stat: os.stat_result | None = None,
    expected_file_stat: os.stat_result | None = None,
) -> bytes:
    if root is None:
        parent_fd = _open_directory_no_follow(path.parent)
    elif expected_parent_stat is None:
        parent_fd = _open_resolved_directory_no_follow(path.parent, root)
    else:
        parent_fd = _open_resolved_directory_no_follow(path.parent, root, expected_stat=expected_parent_stat)
    try:
        if expected_file_stat is None:
            return _read_file_bytes_no_follow_at(parent_fd, path.name)
        return _read_file_bytes_no_follow_at(parent_fd, path.name, expected_stat=expected_file_stat)
    finally:
        os.close(parent_fd)


class ICloudDriveExportTooLarge(Exception):
    pass


class ICloudDriveInvalidOutputDirectory(Exception):
    pass


class ICloudDriveOutputDirectoryInsideRoot(Exception):
    pass


def _read_export_file_bytes_no_follow(
    path: Path,
    *,
    root: Path,
    max_bytes: int,
    expected_parent_stat: os.stat_result | None = None,
    expected_file_stat: os.stat_result | None = None,
) -> bytes:
    parent_fd = _open_resolved_directory_no_follow(path.parent, root, expected_stat=expected_parent_stat)
    fd = -1
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path.name, flags, dir_fd=parent_fd)
        opened_stat = os.fstat(fd)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OSError("not a regular file")
        if expected_file_stat is not None and not _same_stat_snapshot(expected_file_stat, opened_stat):
            raise _UnsafeTargetError()
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ICloudDriveExportTooLarge()
            chunks.append(chunk)
        if expected_file_stat is not None and not _same_stat_snapshot(expected_file_stat, os.fstat(fd)):
            raise _UnsafeTargetError()
        return b"".join(chunks)
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent_fd)


def _read_file_bytes_no_follow_at(
    parent_fd: int,
    name: str,
    *,
    expected_stat: os.stat_result | None = None,
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        opened_stat = os.fstat(fd)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OSError("not a regular file")
        if expected_stat is not None and not _same_stat_snapshot(expected_stat, opened_stat):
            raise _UnsafeTargetError()
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if expected_stat is not None and not _same_stat_snapshot(expected_stat, os.fstat(fd)):
            raise _UnsafeTargetError()
        return b"".join(chunks)
    finally:
        os.close(fd)


def _open_regular_file_no_follow_at(
    parent_fd: int,
    name: str,
    *,
    expected_stat: os.stat_result | None = None,
) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        opened_stat = os.fstat(fd)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OSError("not a regular file")
        if expected_stat is not None and not _same_stat_snapshot(expected_stat, opened_stat):
            raise _UnsafeTargetError()
        return fd
    except Exception:
        os.close(fd)
        raise


def _copy_regular_file_stream_no_follow_at(
    source_parent_fd: int,
    source_name: str,
    target_fd: int,
    *,
    expected_stat: os.stat_result,
) -> bytes:
    source_fd = _open_regular_file_no_follow_at(source_parent_fd, source_name)
    digest = hashlib.sha256()
    try:
        if not _same_stat_snapshot(expected_stat, os.fstat(source_fd)):
            raise _ContentChangedDuringReplaceError()
        while True:
            chunk = os.read(source_fd, REGULAR_FILE_COPY_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            _write_all(target_fd, chunk)
        if not _same_stat_snapshot(expected_stat, os.fstat(source_fd)):
            raise _ContentChangedDuringReplaceError()
        return digest.digest()
    finally:
        os.close(source_fd)


def _hash_regular_file_stream_no_follow_at(
    parent_fd: int,
    name: str,
    *,
    expected_stat: os.stat_result,
) -> bytes:
    fd = _open_regular_file_no_follow_at(parent_fd, name, expected_stat=expected_stat)
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(fd, REGULAR_FILE_COPY_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        if not _same_stat_snapshot(expected_stat, os.fstat(fd)):
            raise _UnsafeTargetError()
        return digest.digest()
    finally:
        os.close(fd)


def _hash_regular_file_absolute_no_follow(path: Path, *, expected_stat: os.stat_result) -> bytes:
    parent_fd = _open_absolute_directory_no_follow(path.parent)
    try:
        return _hash_regular_file_stream_no_follow_at(parent_fd, path.name, expected_stat=expected_stat)
    finally:
        os.close(parent_fd)


def _decode_supported_text(raw: bytes) -> str:
    if b"\x00" in raw:
        raise UnicodeDecodeError("utf-8", raw, 0, 1, "NUL byte")
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _read_supported_text(
    path: Path,
    *,
    root: Path | None = None,
    expected_parent_stat: os.stat_result | None = None,
    expected_file_stat: os.stat_result | None = None,
) -> str:
    return _decode_supported_text(
        _read_file_bytes_no_follow(
            path,
            root=root,
            expected_parent_stat=expected_parent_stat,
            expected_file_stat=expected_file_stat,
        )
    )


def _read_supported_text_at(parent_fd: int, name: str) -> str:
    return _decode_supported_text(_read_file_bytes_no_follow_at(parent_fd, name))


def _create_text_no_follow(parent: Path, name: str, content: str) -> None:
    parent_fd = _open_directory_no_follow(parent)
    fd = -1
    opened_new = False
    created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        opened_new = True
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise OSError("not a regular file")
        _write_all(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.fsync(parent_fd)
        created = True
    finally:
        if fd >= 0:
            os.close(fd)
        if opened_new and not created:
            with contextlib.suppress(OSError):
                os.unlink(name, dir_fd=parent_fd)
        os.close(parent_fd)


def _create_directory_no_follow(parent: Path, name: str) -> None:
    parent_fd = _open_directory_no_follow(parent)
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _open_directory_no_follow(path: Path) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISDIR(mode):
            raise OSError("not a directory")
        return fd
    except Exception:
        os.close(fd)
        raise


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = os.write(fd, view[total:])
        if written <= 0:
            raise OSError("short write")
        total += written


def _export_filename(value: str | None, fallback_name: str) -> str:
    candidate = (
        _bounded_string(value, 200).strip()
        if value
        else _bounded_string(fallback_name, 200).strip()
    )
    if not candidate:
        candidate = "icloud-file"
    name = Path(candidate).name
    fallback_suffix = Path(fallback_name).suffix
    suffix = Path(name).suffix or fallback_suffix
    stem = Path(name).stem if Path(name).suffix else name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    if not safe_stem:
        safe_stem = "icloud-file"
    return f"{safe_stem[:120]}{suffix.lower()}"


def _bounded_string(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text).strip()
    return text[:limit]


def _open_export_directory_no_follow(directory: Path, *, root: Path) -> tuple[int, Path]:
    absolute_dir = _normalize_export_output_directory(directory)
    root_resolved = root.expanduser().resolve(strict=False)
    if _path_is_within(absolute_dir.resolve(strict=False), root_resolved):
        raise ICloudDriveOutputDirectoryInsideRoot()
    if absolute_dir.exists() and not absolute_dir.is_dir():
        raise ICloudDriveInvalidOutputDirectory()

    parts = absolute_dir.parts
    if not absolute_dir.is_absolute() or not parts:
        raise ICloudDriveInvalidOutputDirectory()

    current_fd = _open_directory_no_follow(Path(parts[0]))
    try:
        for part in parts[1:]:
            next_fd = -1
            try:
                flags = os.O_RDONLY
                if hasattr(os, "O_DIRECTORY"):
                    flags |= os.O_DIRECTORY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                try:
                    next_fd = os.open(part, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                    os.fsync(current_fd)
                    next_fd = os.open(part, flags, dir_fd=current_fd)
                mode = os.fstat(next_fd).st_mode
                if not stat.S_ISDIR(mode):
                    raise ICloudDriveInvalidOutputDirectory()
            except ICloudDriveInvalidOutputDirectory:
                if next_fd >= 0:
                    os.close(next_fd)
                raise
            except OSError as exc:
                if next_fd >= 0:
                    os.close(next_fd)
                raise ICloudDriveInvalidOutputDirectory() from exc
            os.close(current_fd)
            current_fd = next_fd

        expected = absolute_dir.lstat()
        actual = os.fstat(current_fd)
        if not stat.S_ISDIR(expected.st_mode) or not _same_stat_identity(expected, actual):
            raise ICloudDriveInvalidOutputDirectory()
        if _path_is_within(absolute_dir.resolve(strict=False), root_resolved):
            raise ICloudDriveOutputDirectoryInsideRoot()
        return current_fd, absolute_dir
    except Exception:
        os.close(current_fd)
        raise


def _write_unique_export_file_at(parent_fd: int, directory: Path, filename: str, data: bytes) -> Path:
    for index in range(0, 1000):
        target_name = filename
        if index:
            target_name = f"{Path(filename).stem}-{index}{Path(filename).suffix}"
        target = directory / target_name
        fd = -1
        opened_new = False
        completed = False
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(target_name, flags, 0o600, dir_fd=parent_fd)
            opened_new = True
            created_stat = os.fstat(fd)
            if not stat.S_ISREG(created_stat.st_mode):
                raise OSError("not a regular file")
            _write_all(fd, data)
            os.fsync(fd)
            os.fsync(parent_fd)
            path_stat = target.lstat()
            if not _same_stat_identity(created_stat, path_stat):
                raise OSError("export path identity changed")
            completed = True
            return target
        except FileExistsError:
            continue
        finally:
            if fd >= 0:
                os.close(fd)
            if opened_new and not completed:
                with contextlib.suppress(OSError):
                    os.unlink(target_name, dir_fd=parent_fd)
    raise OSError("could not allocate unique export path")


def _normalize_export_output_directory(directory: Path) -> Path:
    absolute_dir = Path(os.path.abspath(os.fspath(directory.expanduser())))
    parts = absolute_dir.parts
    if len(parts) <= 1:
        return absolute_dir
    first_component = Path(parts[0]) / parts[1]
    if parts[1] not in {"tmp", "var"} or not first_component.is_symlink():
        return absolute_dir
    try:
        resolved_first = first_component.resolve(strict=True)
    except OSError:
        return absolute_dir
    return resolved_first.joinpath(*parts[2:])


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _normalize_create_filename(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: filename.")
    if len(normalized) > MAX_PREVIEW_FILENAME_CHARS:
        return "", _warning("input_too_large", "Filename exceeds maximum length.")
    if normalized.startswith("."):
        return "", _warning("invalid_filename", "Hidden filenames are not supported.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        return "", _warning("invalid_filename", "Filename must not contain path separators.")
    if Path(normalized).suffix.lower() not in TEXT_SUFFIXES:
        return "", _warning("unsupported_file_type", "iCloud Drive create supports text-like file extensions only.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*", normalized):
        return "", _warning("invalid_filename", "Filename contains unsupported characters.")
    return normalized, None


def _normalize_create_folder_name(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: filename.")
    if normalized != value:
        return "", _warning("invalid_filename", "Folder name must not start or end with whitespace.")
    if len(normalized) > MAX_PREVIEW_FILENAME_CHARS:
        return "", _warning("input_too_large", "Folder name exceeds maximum length.")
    if normalized.startswith("."):
        return "", _warning("invalid_filename", "Hidden folder names are not supported.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        return "", _warning("invalid_filename", "Folder name must not contain path separators.")
    if Path(normalized).suffix.lower() in PACKAGE_SUFFIXES:
        return "", _warning("unsupported_file_type", "iCloud Drive create-folder does not create packages.")
    if normalized[-1] in {" ", "."}:
        return "", _warning("invalid_filename", "Folder name must not end with space or period.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*", normalized):
        return "", _warning("invalid_filename", "Folder name contains unsupported characters.")
    return normalized, None


def _normalize_folder_components(
    value: list[str] | tuple[str, ...] | str | None,
) -> tuple[list[str], dict[str, str] | None]:
    if value is None or value == "":
        return [], _warning("missing_required_field", "Missing required field: folder_components.")
    if isinstance(value, str):
        raw_components: list[Any] = [value]
    else:
        raw_components = list(value)
    if not raw_components:
        return [], _warning("missing_required_field", "Missing required field: folder_components.")
    if len(raw_components) > MAX_FOLDER_PATH_COMPONENTS:
        return [], _warning(
            "input_too_large",
            f"create-folder-path supports at most {MAX_FOLDER_PATH_COMPONENTS} folder components.",
        )
    normalized: list[str] = []
    for component in raw_components:
        if not isinstance(component, str):
            return [], _warning("invalid_filename", "folder_components values must be strings.")
        folder_name, warning = _normalize_create_folder_name(component)
        if warning is not None:
            return [], warning
        normalized.append(folder_name)
    return normalized, None


def _normalize_regular_file_name(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: filename.")
    if len(normalized) > MAX_PREVIEW_FILENAME_CHARS:
        return "", _warning("input_too_large", "Filename exceeds maximum length.")
    if normalized.startswith("."):
        return "", _warning("invalid_filename", "Hidden filenames are not supported.")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        return "", _warning("invalid_filename", "Filename must not contain path separators.")
    suffix = Path(normalized).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return "", _warning("unsupported_file_type", "Use the text-file operations for supported text-like files.")
    if suffix in PACKAGE_SUFFIXES:
        return "", _warning("unsupported_file_type", "iCloud Drive regular-file operations do not mutate packages.")
    if normalized[-1] in {" ", "."}:
        return "", _warning("invalid_filename", "Filename must not end with space or period.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*", normalized):
        return "", _warning("invalid_filename", "Filename contains unsupported characters.")
    return normalized, None


def _import_source_file_metadata(source_file: str | Path, *, root: Path) -> dict[str, Any]:
    if not str(source_file).strip():
        return {"warnings": [_warning("missing_source_file", "iCloud Drive import-file requires source_file.")]}
    try:
        source = _absolute_existing_no_symlink_path(Path(source_file).expanduser())
    except _UnsafeTargetError:
        return {"warnings": [_warning("symlink_source_blocked", "iCloud Drive import source must not traverse symlinks.")]}
    except OSError:
        return {"warnings": [_warning("source_file_unavailable", "iCloud Drive import source_file is unavailable.")]}

    try:
        source_stat = source.lstat()
    except OSError:
        return {"warnings": [_warning("source_file_unavailable", "iCloud Drive import source_file is unavailable.")]}
    if not stat.S_ISREG(source_stat.st_mode):
        return {"warnings": [_warning("source_file_unavailable", "iCloud Drive import source_file must be a regular file.")]}

    root_path = Path(os.path.abspath(os.path.expanduser(str(root))))
    try:
        source.relative_to(root_path)
    except ValueError:
        pass
    else:
        return {
            "warnings": [
                _warning(
                    "source_inside_icloud_root",
                    "Use exact iCloud Drive copy-file or move-file for files already inside iCloud Drive.",
                )
            ]
        }

    filename, filename_warning = _normalize_regular_file_name(source.name)
    if filename_warning is not None:
        return {"warnings": [filename_warning]}
    if _has_package_component_absolute(source):
        return {"warnings": [_warning("unsupported_file_type", "iCloud Drive import source must not traverse packages.")]}

    try:
        content_sha256 = _hash_regular_file_absolute_no_follow(source, expected_stat=source_stat).hex()
    except _UnsafeTargetError:
        return {"warnings": [_warning("symlink_source_blocked", "iCloud Drive import source must not traverse symlinks.")]}
    except OSError:
        return {"warnings": [_warning("source_file_unavailable", "iCloud Drive import source_file is unreadable.")]}

    return {
        "warnings": [],
        "path": source,
        "stat": source_stat,
        "filename": filename,
        "extension": source.suffix.lower() or None,
        "file_size_bytes": int(source_stat.st_size),
        "source_content_sha256": content_sha256,
        "source_identity_sha256": _import_source_identity_sha256(source, source_stat, content_sha256),
    }


def _normalize_create_text(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: content_text.")
    if len(normalized) > MAX_CONTENT_CHARS:
        return "", _warning("input_too_large", "content_text exceeds maximum length.")
    if "\x00" in normalized:
        return "", _warning("unsupported_file_type", "Binary content is not supported.")
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError:
        return "", _warning("unsupported_file_type", "content_text must be valid UTF-8 text.")
    return normalized, None


def _normalize_sha256(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().lower()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: expected_current_sha256.")
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        return "", _warning("invalid_expected_sha256", "expected_current_sha256 must be a 64-character SHA-256 hex digest.")
    return normalized, None


def _fingerprint_proposed(
    operation: str,
    proposed: dict[str, Any],
    normalized_content: str,
) -> dict[str, Any]:
    if operation == "create_text":
        return {
            **proposed,
            "content_sha256": hashlib.sha256(normalized_content.encode("utf-8")).hexdigest(),
        }
    return proposed


def _apply_create_folder(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    parent = _resolve_handle(
        str(preview["target"]["parent_handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if parent is None or parent.is_symlink() or not _is_directory_no_follow(parent):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _has_package_component(parent, root) or _has_symlink_component(parent, root):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _parent_identity_changed(preview, parent, root):
        return _apply_error(
            [_warning("parent_identity_changed", "iCloud Drive parent directory changed after planning.")],
            plan={"preview": preview},
        )

    target = parent / str(preview["target"]["filename"])
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive create-folder target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    try:
        parent_fd = _open_resolved_directory_no_follow(parent, root)
    except OSError:
        return _apply_error(
            [_warning("write_error", "iCloud Drive folder could not be created safely.")],
            plan={"preview": preview},
        )

    try:
        try:
            existing_stat = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing_stat = None

        if existing_stat is not None:
            if stat.S_ISDIR(existing_stat.st_mode):
                return _apply_directory_success(
                    target,
                    root=root,
                    idempotency_key=preview["idempotency_key"],
                    approval_fingerprint=approval_fingerprint,
                    operation="create_folder",
                    mutation_applied=False,
                    warnings=[_warning("already_applied", "iCloud Drive folder already exists.")],
                )
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target already exists and will not be overwritten.")],
                plan={"preview": preview},
            )

        try:
            os.mkdir(target.name, 0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target already exists and will not be overwritten.")],
                plan={"preview": preview},
            )
        except OSError:
            return _apply_error(
                [_warning("write_error", "iCloud Drive folder could not be created safely.")],
                plan={"preview": preview},
            )
    finally:
        os.close(parent_fd)

    return _apply_directory_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="create_folder",
        mutation_applied=True,
        warnings=[],
    )


def _apply_create_folder_path(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    parent = _resolve_handle(
        str(preview["target"]["parent_handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if parent is None or parent.is_symlink() or not _is_directory_no_follow(parent):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _has_package_component(parent, root) or _has_symlink_component(parent, root):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _parent_identity_changed(preview, parent, root):
        return _apply_error(
            [_warning("parent_identity_changed", "iCloud Drive parent directory changed after planning.")],
            plan={"preview": preview},
        )

    components = list(preview["target"].get("folder_components") or [])
    current = parent
    created_count = 0
    existing_count = 0

    def fail(code: str, message: str) -> dict[str, Any]:
        warnings = [_warning(code, message)]
        if created_count == 0:
            return _apply_error(warnings, plan={"preview": preview})
        return _apply_folder_path_partial(
            preview,
            approval_fingerprint=approval_fingerprint,
            created_count=created_count,
            existing_count=existing_count,
            component_count=len(components),
            warnings=warnings,
        )

    for component in components:
        target = current / str(component)
        try:
            target.relative_to(root.expanduser())
        except ValueError:
            return fail("target_outside_root", "iCloud Drive target escaped the configured root.")
        if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
            return fail(
                "unsupported_file_type",
                "iCloud Drive create-folder-path target must not traverse packages or symlinks.",
            )
        try:
            current_fd = _open_resolved_directory_no_follow(current, root)
        except OSError:
            return fail("write_error", "iCloud Drive folder path could not be created safely.")
        try:
            try:
                existing_stat = os.stat(target.name, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                try:
                    os.mkdir(target.name, 0o700, dir_fd=current_fd)
                    os.fsync(current_fd)
                    created_count += 1
                    existing_stat = os.stat(target.name, dir_fd=current_fd, follow_symlinks=False)
                except FileExistsError:
                    existing_stat = os.stat(target.name, dir_fd=current_fd, follow_symlinks=False)
                    existing_count += 1
                except OSError:
                    return fail("write_error", "iCloud Drive folder path could not be created safely.")
            else:
                existing_count += 1

            if not stat.S_ISDIR(existing_stat.st_mode):
                return fail("target_exists", "iCloud Drive folder path component already exists and is not a directory.")
        finally:
            os.close(current_fd)
        current = target

    result = _apply_folder_path_success(
        current,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=created_count > 0,
        created_count=created_count,
        existing_count=existing_count,
        component_count=len(components),
        warnings=[],
    )
    if created_count == 0:
        result["warnings"] = [_warning("already_applied", "iCloud Drive folder path already exists.")]
    return result


def _apply_append_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    content_text: str,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target is None or target.is_symlink() or not target.is_file():
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if target.suffix.lower() not in TEXT_SUFFIXES:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive append supports text-like file extensions only.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive append target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    try:
        existing_bytes = _read_file_bytes_no_follow(target, root=root)
        existing_text = _decode_supported_text(existing_bytes)
    except OSError:
        return _apply_error(
            [_warning("read_error", "iCloud Drive target file could not be read before append.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be appended through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
    expected_sha = str(preview["target"]["expected_current_sha256"])
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )

    normalized_content, content_warning = _normalize_create_text(content_text)
    if content_warning is not None:
        return _apply_error([content_warning], plan={"preview": preview}, content_inspected=True)
    replacement_sha = hashlib.sha256((existing_text + normalized_content).encode("utf-8")).hexdigest()
    try:
        _atomic_replace_bytes(
            target,
            existing_bytes + normalized_content.encode("utf-8"),
            expected_sha=expected_sha,
            root=root,
        )
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive append target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be appended through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except OSError:
        return _apply_error(
            [_warning("append_error", "iCloud Drive text could not be appended safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    return _apply_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="append_text",
        mutation_applied=True,
        expected_content_sha256=replacement_sha,
        warnings=[],
    )


def _apply_replace_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    content_text: str,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target is None or target.is_symlink() or not target.is_file():
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if target.suffix.lower() not in TEXT_SUFFIXES:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive replace supports text-like file extensions only.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive replace target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    try:
        existing_text = _read_supported_text(target, root=root)
    except OSError:
        return _apply_error(
            [_warning("read_error", "iCloud Drive target file could not be read before replace.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be replaced through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
    expected_sha = str(preview["target"]["expected_current_sha256"])
    normalized_content, content_warning = _normalize_create_text(content_text)
    if content_warning is not None:
        return _apply_error([content_warning], plan={"preview": preview}, content_inspected=True)
    replacement_sha = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
    if current_sha != expected_sha:
        if current_sha == replacement_sha:
            return _apply_success(
                target,
                root=root,
                idempotency_key=preview["idempotency_key"],
                approval_fingerprint=approval_fingerprint,
                operation="replace_text",
                mutation_applied=False,
                warnings=[
                    _warning(
                        "already_applied",
                        "iCloud Drive file already has the approved replacement content.",
                    )
                ],
            )
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    if current_sha == replacement_sha:
        return _apply_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="replace_text",
            mutation_applied=False,
            warnings=[
                _warning(
                    "already_applied",
                    "iCloud Drive file already has the approved replacement content.",
                )
            ],
        )
    try:
        _atomic_replace_text(target, normalized_content, expected_sha=expected_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive replace target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be replaced through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except OSError:
        return _apply_error(
            [_warning("replace_error", "iCloud Drive text could not be replaced safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    return _apply_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="replace_text",
        mutation_applied=True,
        expected_content_sha256=replacement_sha,
        warnings=[],
    )


def _apply_trash_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target is None or target.is_symlink() or not target.is_file():
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if target.suffix.lower() not in TEXT_SUFFIXES:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive trash supports text-like file extensions only.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive trash target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    try:
        existing_text = _read_supported_text(target, root=root)
    except OSError:
        return _apply_error(
            [_warning("read_error", "iCloud Drive target file could not be read before trash.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be trashed through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
    expected_sha = str(preview["target"]["expected_current_sha256"])
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    try:
        trashed_name = _move_text_file_to_trash(target, expected_sha=expected_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive trash target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be trashed through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except OSError:
        return _apply_error(
            [_warning("trash_error", "iCloud Drive text file could not be moved to Trash safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )

    original_present = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    ) is not None
    warnings: list[dict[str, str]] = []
    status = "ok"
    if original_present:
        status = "partial"
        warnings.append(
            _warning(
                "read_back_mismatch",
                "iCloud Drive original handle was still present after Trash apply.",
            )
        )
    return _apply_trash_success(
        preview,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        original_name=target.name,
        trashed_name=trashed_name,
        content_sha256=current_sha,
        original_present=original_present,
        status=status,
        warnings=warnings,
    )


def _apply_delete_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target is None or target.is_symlink() or not target.is_file():
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if target.suffix.lower() not in TEXT_SUFFIXES:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive delete supports text-like file extensions only.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive delete target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    original_name = target.name
    expected_sha = str(preview["target"]["expected_current_sha256"])
    try:
        _delete_text_file_permanently(
            target,
            expected_sha=expected_sha,
            expected_identity_sha256=str(preview["target"]["expected_file_identity_sha256"]),
            root=root,
        )
    except _ApprovedFileIdentityChangedError:
        return _apply_error(
            [_warning("invalid_approval_token", "iCloud Drive target identity no longer matches the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive delete target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be deleted through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _PartialLocationMutationError as exc:
        original_present = _resolve_handle(
            str(preview["target"]["handle"]),
            root,
            max_scan_entries=max_scan_entries,
        ) is not None
        return _apply_delete_text_success(
            preview,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            original_name=original_name,
            original_present=original_present,
            status="partial",
            warnings=[_warning(exc.code, exc.safe_message)],
        )
    except OSError:
        return _apply_error(
            [_warning("delete_error", "iCloud Drive text file could not be deleted safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )

    original_present = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    ) is not None
    warnings: list[dict[str, str]] = []
    status = "ok"
    if original_present:
        status = "partial"
        warnings.append(
            _warning(
                "read_back_mismatch",
                "iCloud Drive original handle was still present after delete apply.",
            )
        )
    return _apply_delete_text_success(
        preview,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        original_name=original_name,
        original_present=original_present,
        status=status,
        warnings=warnings,
    )


def _apply_trash_folder(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    target = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target is None:
        return _apply_error(
            [_warning("target_not_found", "iCloud Drive target folder was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _is_root_path(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive root folder cannot be trashed.")],
            plan={"preview": preview},
        )
    if target.is_symlink() or not _is_directory_no_follow(target):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder trash requires an exact directory handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder trash target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    expected_sha = str(preview["target"]["expected_current_sha256"])
    current_sha = _directory_metadata_sha256(target, root)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder metadata changed before Trash apply.")],
            plan={"preview": preview},
        )
    original_name = target.name
    try:
        trashed_name, empty_folder_confirmed = _move_folder_to_trash(target, expected_sha=expected_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder metadata changed before Trash apply.")],
            plan={"preview": preview},
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder trash target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    except _PartialLocationMutationError as exc:
        original_present = _resolve_handle(
            str(preview["target"]["handle"]),
            root,
            max_scan_entries=max_scan_entries,
        ) is not None
        trashed = exc.code == "cleanup_unverified"
        return _apply_trash_folder_success(
            preview,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            original_name=original_name,
            trashed_name="",
            original_present=original_present,
            empty_folder_confirmed=False,
            non_empty_allowed=True,
            status="partial",
            warnings=[_warning(exc.code, exc.safe_message)],
            trashed=trashed,
            mutation_applied=trashed or not original_present,
        )
    except OSError:
        return _apply_error(
            [_warning("trash_error", "iCloud Drive folder could not be moved to Trash safely.")],
            plan={"preview": preview},
        )

    original_present = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    ) is not None
    warnings: list[dict[str, str]] = []
    status = "ok"
    if original_present:
        status = "partial"
        warnings.append(
            _warning(
                "read_back_mismatch",
                "iCloud Drive original folder handle was still present after Trash apply.",
            )
        )
    return _apply_trash_folder_success(
        preview,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        original_name=original_name,
        trashed_name=trashed_name,
        original_present=original_present,
        empty_folder_confirmed=empty_folder_confirmed,
        non_empty_allowed=True,
        status=status,
        warnings=warnings,
    )


def _apply_delete_folder(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
    source_tree_sha256: str,
) -> dict[str, Any]:
    target = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target is None:
        return _apply_error(
            [_warning("target_not_found", "iCloud Drive target folder was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _is_root_path(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive root folder cannot be deleted.")],
            plan={"preview": preview},
        )
    if target.is_symlink() or not _is_directory_no_follow(target):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder delete requires an exact directory handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder delete target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    expected_sha = str(preview["target"]["expected_current_sha256"])
    current_sha = _directory_metadata_sha256(target, root)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder metadata changed before delete apply.")],
            plan={"preview": preview},
        )
    original_name = target.name
    try:
        empty_folder_confirmed = _delete_folder_tree_permanently(
            target,
            expected_sha=expected_sha,
            expected_tree_sha=source_tree_sha256,
            root=root,
        )
    except _FolderCopyTooLargeError:
        return _apply_error(
            [_warning("folder_tree_too_large", "iCloud Drive folder delete is limited to bounded selected-folder trees.")],
            plan={"preview": preview},
        )
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder tree changed before delete apply.")],
            plan={"preview": preview},
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder delete target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    except _PartialLocationMutationError as exc:
        original_present = _resolve_handle(
            str(preview["target"]["handle"]),
            root,
            max_scan_entries=max_scan_entries,
        ) is not None
        return _apply_delete_folder_success(
            preview,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            original_name=original_name,
            original_present=original_present,
            empty_folder_confirmed=False,
            non_empty_allowed=True,
            status="partial",
            warnings=[_warning(exc.code, exc.safe_message)],
        )
    except OSError:
        return _apply_error(
            [_warning("delete_error", "iCloud Drive folder could not be deleted safely.")],
            plan={"preview": preview},
        )

    original_present = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    ) is not None
    warnings: list[dict[str, str]] = []
    status = "ok"
    if original_present:
        status = "partial"
        warnings.append(
            _warning(
                "read_back_mismatch",
                "iCloud Drive original folder handle was still present after delete apply.",
            )
        )
    return _apply_delete_folder_success(
        preview,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        original_name=original_name,
        original_present=original_present,
        empty_folder_confirmed=empty_folder_confirmed,
        non_empty_allowed=True,
        status=status,
        warnings=warnings,
    )


def _apply_rename_folder(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    source = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if source is None:
        return _apply_error(
            [_warning("target_not_found", "iCloud Drive target folder was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _is_root_path(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive root folder cannot be renamed.")],
            plan={"preview": preview},
        )
    if source.is_symlink() or not _is_directory_no_follow(source):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder rename requires an exact directory handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(source, root) or _has_symlink_component(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder rename target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    source_stat = source.lstat()
    expected_sha = str(preview["target"]["expected_current_sha256"])
    current_sha = _directory_metadata_sha256(source, root)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder metadata changed before mutation could be applied.")],
            plan={"preview": preview},
        )

    target_name = str(preview["target"]["filename"])
    target = source.parent / target_name
    if source.name == target_name:
        return _apply_directory_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="rename_folder",
            mutation_applied=False,
            source_present=True,
            expected_source_present=True,
            target_present=True,
            operation_flags={"renamed": False},
            warnings=[_warning("already_applied", "iCloud Drive folder already has the approved name.")],
            require_empty_folder=False,
        )
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive folder rename target escaped the configured root.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder rename target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
    except OSError:
        return _apply_error(
            [_warning("rename_error", "iCloud Drive folder could not be renamed safely.")],
            plan={"preview": preview},
        )

    try:
        _renameatx_excl_no_follow(source_parent_fd, source.name, source_parent_fd, target_name)
        os.fsync(source_parent_fd)
        target_stat = target.lstat()
        if not _same_stat_relocated_snapshot(source_stat, target_stat):
            return _apply_directory_location_success(
                target,
                root=root,
                idempotency_key=preview["idempotency_key"],
                approval_fingerprint=approval_fingerprint,
                operation="rename_folder",
                mutation_applied=True,
                source_present=_path_exists_no_follow(source),
                expected_source_present=False,
                target_present=_path_is_directory_no_follow(target),
                operation_flags={"renamed": True},
                warnings=[
                    _warning(
                        "read_back_mismatch",
                        "iCloud Drive renamed folder identity could not be verified after apply.",
                    )
                ],
                status="partial",
                require_empty_folder=False,
            )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target folder already exists and will not be overwritten.")],
                plan={"preview": preview},
            )
        return _apply_error(
            [_warning("rename_error", "iCloud Drive folder could not be renamed safely.")],
            plan={"preview": preview},
        )
    finally:
        os.close(source_parent_fd)

    return _apply_directory_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="rename_folder",
        mutation_applied=True,
        source_present=_path_exists_no_follow(source),
        expected_source_present=False,
        target_present=_path_is_directory_no_follow(target),
        operation_flags={"renamed": True},
        warnings=[],
        require_empty_folder=False,
    )


def _apply_move_folder(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    source = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if source is None:
        return _apply_error(
            [_warning("target_not_found", "iCloud Drive source folder was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _is_root_path(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive root folder cannot be moved.")],
            plan={"preview": preview},
        )
    if source.is_symlink() or not _is_directory_no_follow(source):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder move requires an exact directory handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(source, root) or _has_symlink_component(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder move target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    target_parent = _resolve_handle(
        str(preview["target"]["parent_handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target_parent is None:
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive target parent directory was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if target_parent.is_symlink() or not _is_directory_no_follow(target_parent):
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive folder move requires an exact directory parent handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(target_parent, root) or _has_symlink_component(target_parent, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder move parent must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    source_stat = source.lstat()
    if _same_stat_identity(source_stat, target_parent.lstat()):
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive folder cannot be moved into itself.")],
            plan={"preview": preview},
        )
    with contextlib.suppress(ValueError):
        target_parent.relative_to(source)
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive folder cannot be moved into its own descendant.")],
            plan={"preview": preview},
        )

    expected_sha = str(preview["target"]["expected_current_sha256"])
    current_sha = _directory_metadata_sha256(source, root)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder metadata changed before move apply.")],
            plan={"preview": preview},
        )

    target_name = str(preview["target"].get("filename") or source.name)
    target = target_parent / target_name
    if source == target:
        return _apply_directory_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="move_folder",
            mutation_applied=False,
            source_present=True,
            expected_source_present=True,
            target_present=True,
            operation_flags={"moved": False},
            warnings=[_warning("already_applied", "iCloud Drive folder already has the approved location.")],
            require_empty_folder=False,
        )
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive folder move target escaped the configured root.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder move target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    source_parent_fd = -1
    target_parent_fd = -1
    move_applied = False
    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        _renameatx_excl_no_follow(source_parent_fd, source.name, target_parent_fd, target_name)
        move_applied = True
        with contextlib.suppress(OSError):
            os.fsync(source_parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
        target_stat = target.lstat()
        if not _same_stat_relocated_snapshot(source_stat, target_stat):
            return _apply_directory_location_success(
                target,
                root=root,
                idempotency_key=preview["idempotency_key"],
                approval_fingerprint=approval_fingerprint,
                operation="move_folder",
                mutation_applied=True,
                source_present=_path_exists_no_follow(source),
                expected_source_present=False,
                target_present=_path_is_directory_no_follow(target),
                operation_flags={"moved": True},
                warnings=[
                    _warning(
                        "read_back_mismatch",
                        "iCloud Drive moved folder identity could not be verified after apply.",
                    )
                ],
                status="partial",
                require_empty_folder=False,
            )
    except OSError as exc:
        if not move_applied and exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target folder already exists and will not be overwritten.")],
                plan={"preview": preview},
            )
        if move_applied:
            return _apply_directory_location_success(
                target,
                root=root,
                idempotency_key=preview["idempotency_key"],
                approval_fingerprint=approval_fingerprint,
                operation="move_folder",
                mutation_applied=True,
                source_present=_path_exists_no_follow(source),
                expected_source_present=False,
                target_present=_path_is_directory_no_follow(target),
                operation_flags={"moved": True},
                warnings=[
                    _warning(
                        "read_back_unavailable",
                        "iCloud Drive folder move read-back was unavailable after apply.",
                    )
                ],
                status="partial",
                require_empty_folder=False,
            )
        return _apply_error(
            [_warning("move_error", "iCloud Drive folder could not be moved safely.")],
            plan={"preview": preview},
        )
    finally:
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)

    return _apply_directory_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="move_folder",
        mutation_applied=True,
        source_present=_path_exists_no_follow(source),
        expected_source_present=False,
        target_present=_path_is_directory_no_follow(target),
        operation_flags={"moved": True},
        warnings=[],
        require_empty_folder=False,
    )


def _apply_copy_folder(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
    source_tree_sha256: str,
) -> dict[str, Any]:
    source = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if source is None:
        return _apply_error(
            [_warning("target_not_found", "iCloud Drive source folder was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if _is_root_path(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive root folder cannot be copied.")],
            plan={"preview": preview},
        )
    if source.is_symlink() or not _is_directory_no_follow(source):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder copy requires an exact directory handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(source, root) or _has_symlink_component(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder copy source must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    target_parent = _resolve_handle(
        str(preview["target"]["parent_handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if target_parent is None:
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive target parent directory was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if target_parent.is_symlink() or not _is_directory_no_follow(target_parent):
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive folder copy requires an exact directory parent handle.")],
            plan={"preview": preview},
        )
    if _has_package_component(target_parent, root) or _has_symlink_component(target_parent, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder copy parent must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    source_stat = source.lstat()
    if _same_stat_identity(source_stat, target_parent.lstat()):
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive folder cannot be copied into itself.")],
            plan={"preview": preview},
        )
    with contextlib.suppress(ValueError):
        target_parent.relative_to(source)
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive folder cannot be copied into its own descendant.")],
            plan={"preview": preview},
        )

    expected_sha = str(preview["target"]["expected_current_sha256"])
    current_sha = _directory_metadata_sha256(source, root)
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder metadata changed before copy apply.")],
            plan={"preview": preview},
        )

    target_name = str(preview["target"].get("filename") or source.name)
    target = target_parent / target_name
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive folder copy target escaped the configured root.")],
            plan={"preview": preview},
        )
    if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder copy target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )

    def unverified_target_partial(warnings: list[dict[str, str]]) -> dict[str, Any]:
        return _apply_directory_unverified_target_partial(
            target,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="copy_folder",
            mutation_applied=True,
            source_present=_path_is_directory_no_follow(source),
            expected_source_present=True,
            target_present=_path_is_directory_no_follow(target),
            operation_flags={"copied": False, "target_identity_verified": False},
            warnings=warnings,
        )

    try:
        _copy_folder_tree(
            source,
            target_parent,
            target_name,
            expected_metadata_sha=expected_sha,
            expected_tree_sha=source_tree_sha256,
            root=root,
        )
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive folder tree changed before copy apply.")],
            plan={"preview": preview},
        )
    except _FolderCopyTooLargeError:
        return _apply_error(
            [_warning("folder_tree_too_large", "iCloud Drive folder copy is limited to bounded selected-folder trees.")],
            plan={"preview": preview},
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive folder copy target must not traverse hidden entries, packages, or symlinks.")],
            plan={"preview": preview},
        )
    except _FolderCopyCleanedError as exc:
        return _apply_error(
            [_warning(exc.code, exc.safe_message)],
            plan={"preview": preview},
        )
    except _PartialLocationMutationError as exc:
        if exc.code == "target_exists":
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target folder already exists and will not be overwritten.")],
                plan={"preview": preview},
            )
        return unverified_target_partial(
            [
                _warning(exc.code, exc.safe_message),
            ]
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target folder already exists and will not be overwritten.")],
                plan={"preview": preview},
            )
        return _apply_error(
            [_warning("copy_error", "iCloud Drive folder could not be copied safely.")],
            plan={"preview": preview},
        )
    try:
        final_target_stat = target.lstat()
        if not stat.S_ISDIR(final_target_stat.st_mode):
            return unverified_target_partial(
                [
                    _warning(
                        "read_back_mismatch",
                        "iCloud Drive copied folder target could not be verified after apply.",
                    )
                ]
            )
    except OSError:
        return unverified_target_partial(
            [
                _warning(
                    "read_back_unavailable",
                    "iCloud Drive copied folder target identity could not be verified after apply.",
                )
            ]
        )

    return _apply_directory_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="copy_folder",
        mutation_applied=True,
        source_present=_path_is_directory_no_follow(source),
        expected_source_present=True,
        target_present=_path_is_directory_no_follow(target),
        operation_flags={"copied": True},
        warnings=[],
        require_empty_folder=False,
    )


def _apply_import_file(
    preview: dict[str, Any],
    *,
    source_info: Any,
    source_file: str | Path,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    if not isinstance(source_info, dict):
        source_info = _import_source_file_metadata(source_file, root=root)
        source_info.pop("warnings", None)
    source_path = source_info.get("path")
    source_stat = source_info.get("stat")
    source_content_sha256 = str(source_info.get("source_content_sha256") or "")
    if not isinstance(source_path, Path) or source_stat is None or not source_content_sha256:
        return _apply_error(
            [_warning("source_file_unavailable", "iCloud Drive import source_file is unavailable.")],
            plan={"preview": preview},
            status="not_found",
            content_inspected=False,
        )

    target_parent_result = _resolve_location_parent(
        str(preview["target"]["parent_handle"]),
        fallback_parent=root.expanduser(),
        plan={"preview": preview},
        root=root,
        max_scan_entries=max_scan_entries,
        required=True,
    )
    if isinstance(target_parent_result, dict):
        return target_parent_result
    target_parent = target_parent_result
    if _parent_identity_changed(preview, target_parent, root):
        return _apply_error(
            [_warning("parent_identity_changed", "iCloud Drive parent directory changed after planning.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    target_name = str(preview["target"]["filename"])
    target = target_parent / target_name
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive import target escaped the configured root.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    try:
        _import_regular_file(
            source_path,
            source_stat,
            target_parent,
            target_name,
            expected_source_content_sha256=source_content_sha256,
            root=root,
        )
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("source_file_changed", "iCloud Drive import source file changed after the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        return _apply_import_file_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            mutation_applied=True,
            imported=True,
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive import target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive import target already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=False,
            )
        return _apply_error(
            [_warning("import_error", "iCloud Drive file could not be imported safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    return _apply_import_file_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        imported=True,
        warnings=[],
    )


def _apply_replace_file(
    preview: dict[str, Any],
    *,
    source_info: Any,
    source_file: str | Path,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    if not isinstance(source_info, dict):
        source_info = _import_source_file_metadata(source_file, root=root)
        source_info.pop("warnings", None)
    source_path = source_info.get("path")
    source_stat = source_info.get("stat")
    source_content_sha256 = str(source_info.get("source_content_sha256") or "")
    if not isinstance(source_path, Path) or source_stat is None or not source_content_sha256:
        return _apply_error(
            [_warning("source_file_unavailable", "iCloud Drive replace source_file is unavailable.")],
            plan={"preview": preview},
            status="not_found",
            content_inspected=False,
        )

    resolved = _resolve_location_file_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="replace",
    )
    if isinstance(resolved, dict):
        return resolved
    target, current_sha = resolved
    try:
        _replace_regular_file_from_source(
            source_path,
            source_stat,
            target,
            expected_target_metadata_sha=current_sha,
            expected_source_content_sha256=source_content_sha256,
            root=root,
        )
    except _SourceFileChangedDuringReplaceError:
        return _apply_error(
            [_warning("source_file_changed", "iCloud Drive replace source file changed after the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        return _apply_replace_file_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            mutation_applied=True,
            replaced=True,
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive replace-file target/source must be non-text, non-package regular files with matching extensions and no symlink traversal.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError:
        return _apply_error(
            [_warning("replace_error", "iCloud Drive regular file could not be replaced safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    return _apply_replace_file_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        mutation_applied=True,
        replaced=True,
        warnings=[],
    )


def _apply_rename_file(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_file_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="rename",
    )
    if isinstance(resolved, dict):
        return resolved
    source, current_sha = resolved
    target_name = str(preview["target"]["filename"])
    target = source.parent / target_name
    if source.name == target_name:
        return _apply_regular_file_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="rename_file",
            mutation_applied=False,
            source_present=True,
            expected_source_present=True,
            target_present=True,
            operation_flags={"renamed": False},
            warnings=[_warning("already_applied", "iCloud Drive regular file already has the approved name.")],
        )
    try:
        _move_regular_file(source, source.parent, target_name, expected_metadata_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        return _apply_regular_file_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="rename_file",
            mutation_applied=True,
            source_present=_path_exists_no_follow(source),
            expected_source_present=False,
            target_present=_path_is_regular_file_no_follow(target),
            operation_flags={"renamed": True},
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive regular-file rename target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=False,
            )
        return _apply_error(
            [_warning("rename_error", "iCloud Drive regular file could not be renamed safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    return _apply_regular_file_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="rename_file",
        mutation_applied=True,
        source_present=_path_exists_no_follow(source),
        expected_source_present=False,
        target_present=_path_is_regular_file_no_follow(target),
        operation_flags={"renamed": True},
        warnings=[],
    )


def _apply_copy_file(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_file_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="copy",
    )
    if isinstance(resolved, dict):
        return resolved
    source, current_sha = resolved
    target_parent_result = _resolve_location_parent(
        str(preview["target"].get("parent_handle") or ""),
        fallback_parent=source.parent,
        plan={"preview": preview},
        root=root,
        max_scan_entries=max_scan_entries,
        required=False,
    )
    if isinstance(target_parent_result, dict):
        return target_parent_result
    target_parent = target_parent_result
    target_name = str(preview["target"]["filename"])
    target = target_parent / target_name
    try:
        _copy_regular_file(source, target_parent, target_name, expected_metadata_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        return _apply_regular_file_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="copy_file",
            mutation_applied=True,
            source_present=_path_exists_no_follow(source),
            expected_source_present=True,
            target_present=_path_is_regular_file_no_follow(target),
            operation_flags={"copied": True},
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive regular-file copy target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=False,
            )
        return _apply_error(
            [_warning("copy_error", "iCloud Drive regular file could not be copied safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    return _apply_regular_file_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="copy_file",
        mutation_applied=True,
        source_present=_path_exists_no_follow(source),
        expected_source_present=True,
        target_present=_path_is_regular_file_no_follow(target),
        operation_flags={"copied": True},
        warnings=[],
    )


def _apply_move_file(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_file_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="move",
    )
    if isinstance(resolved, dict):
        return resolved
    source, current_sha = resolved
    target_parent_result = _resolve_location_parent(
        str(preview["target"].get("parent_handle") or ""),
        fallback_parent=source.parent,
        plan={"preview": preview},
        root=root,
        max_scan_entries=max_scan_entries,
        required=True,
    )
    if isinstance(target_parent_result, dict):
        return target_parent_result
    target_parent = target_parent_result
    target_name = str(preview["target"].get("filename") or source.name)
    target = target_parent / target_name
    if _same_file_identity(source.parent, target_parent) and source.name == target_name:
        return _apply_regular_file_location_success(
            source,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="move_file",
            mutation_applied=False,
            source_present=True,
            expected_source_present=True,
            target_present=True,
            operation_flags={"moved": False},
            warnings=[_warning("already_applied", "iCloud Drive regular file is already at the approved destination.")],
        )
    try:
        _move_regular_file(source, target_parent, target_name, expected_metadata_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        return _apply_regular_file_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="move_file",
            mutation_applied=True,
            source_present=_path_exists_no_follow(source),
            expected_source_present=False,
            target_present=_path_is_regular_file_no_follow(target),
            operation_flags={"moved": True},
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive regular-file move target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=False,
            )
        return _apply_error(
            [_warning("move_error", "iCloud Drive regular file could not be moved safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    return _apply_regular_file_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="move_file",
        mutation_applied=True,
        source_present=_path_exists_no_follow(source),
        expected_source_present=False,
        target_present=_path_is_regular_file_no_follow(target),
        operation_flags={"moved": True},
        warnings=[],
    )


def _apply_trash_file(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_file_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="trash",
    )
    if isinstance(resolved, dict):
        return resolved
    target, current_sha = resolved
    original_name = target.name
    try:
        trashed_name = _move_regular_file_to_trash(target, expected_metadata_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        original_present = _resolve_handle(
            str(preview["target"]["handle"]),
            root,
            max_scan_entries=max_scan_entries,
        ) is not None
        mutation_applied = not original_present
        return _apply_trash_file_success(
            preview,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            original_name=original_name,
            trashed_name="",
            original_present=original_present,
            trashed=mutation_applied,
            mutation_applied=mutation_applied,
            status="partial",
            warnings=[_warning(exc.code, exc.safe_message)],
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive regular-file trash target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError:
        return _apply_error(
            [_warning("trash_error", "iCloud Drive regular file could not be moved to Trash safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    original_present = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    ) is not None
    warnings: list[dict[str, str]] = []
    status = "ok"
    if original_present:
        status = "partial"
        warnings.append(
            _warning(
                "read_back_mismatch",
                "iCloud Drive original regular-file handle was still present after Trash apply.",
            )
        )
    return _apply_trash_file_success(
        preview,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        original_name=original_name,
        trashed_name=trashed_name,
        original_present=original_present,
        status=status,
        warnings=warnings,
    )


def _apply_delete_file(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_file_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="delete",
    )
    if isinstance(resolved, dict):
        return resolved
    target, current_sha = resolved
    original_name = target.name
    try:
        _delete_regular_file_permanently(target, expected_metadata_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except _PartialLocationMutationError as exc:
        original_present = _resolve_handle(
            str(preview["target"]["handle"]),
            root,
            max_scan_entries=max_scan_entries,
        ) is not None
        mutation_applied = not original_present
        return _apply_delete_file_success(
            preview,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            original_name=original_name,
            original_present=original_present,
            mutation_applied=mutation_applied,
            status="partial",
            warnings=[_warning(exc.code, exc.safe_message)],
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive regular-file delete target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=False,
        )
    except OSError:
        return _apply_error(
            [_warning("delete_error", "iCloud Drive regular file could not be deleted safely.")],
            plan={"preview": preview},
            content_inspected=False,
        )

    original_present = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    ) is not None
    warnings: list[dict[str, str]] = []
    status = "ok"
    mutation_applied = True
    if original_present:
        status = "partial"
        mutation_applied = False
        warnings.append(
            _warning(
                "read_back_mismatch",
                "iCloud Drive original regular-file handle was still present after delete apply.",
            )
        )
    return _apply_delete_file_success(
        preview,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        original_name=original_name,
        original_present=original_present,
        mutation_applied=mutation_applied,
        status=status,
        warnings=warnings,
    )


def _apply_rename_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_text_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="rename",
    )
    if isinstance(resolved, dict):
        return resolved
    source, current_sha = resolved
    target_name = str(preview["target"]["filename"])
    target = source.parent / target_name
    if source.name == target_name:
        return _apply_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="rename_text",
            mutation_applied=False,
            expected_content_sha256=current_sha,
            source_present=True,
            expected_source_present=True,
            target_present=True,
            operation_flags={"renamed": False},
            warnings=[_warning("already_applied", "iCloud Drive file already has the approved name.")],
        )
    try:
        _move_text_file(source, source.parent, target_name, expected_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsupportedTextContentError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be renamed through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _PartialLocationMutationError as exc:
        return _apply_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="rename_text",
            mutation_applied=True,
            expected_content_sha256=current_sha,
            source_present=_path_exists_no_follow(source),
            expected_source_present=False,
            target_present=_path_is_regular_file_no_follow(target),
            operation_flags={"renamed": True},
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive rename target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=True,
            )
        return _apply_error(
            [_warning("rename_error", "iCloud Drive text file could not be renamed safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )

    source_present = _path_exists_no_follow(source)
    target_present = _path_is_regular_file_no_follow(target)
    return _apply_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="rename_text",
        mutation_applied=True,
        expected_content_sha256=current_sha,
        source_present=source_present,
        expected_source_present=False,
        target_present=target_present,
        operation_flags={"renamed": True},
        warnings=[],
    )


def _apply_copy_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_text_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="copy",
    )
    if isinstance(resolved, dict):
        return resolved
    source, current_sha = resolved
    target_parent_result = _resolve_location_parent(
        str(preview["target"].get("parent_handle") or ""),
        fallback_parent=source.parent,
        plan={"preview": preview},
        root=root,
        max_scan_entries=max_scan_entries,
        required=False,
    )
    if isinstance(target_parent_result, dict):
        return target_parent_result
    target_parent = target_parent_result
    target_name = str(preview["target"]["filename"])
    target = target_parent / target_name
    try:
        _copy_text_file(source, target_parent, target_name, expected_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsupportedTextContentError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be copied through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _PartialLocationMutationError as exc:
        return _apply_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="copy_text",
            mutation_applied=True,
            expected_content_sha256=current_sha,
            source_present=_path_exists_no_follow(source),
            expected_source_present=True,
            target_present=_path_is_regular_file_no_follow(target),
            operation_flags={"copied": True},
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive copy target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=True,
            )
        return _apply_error(
            [_warning("copy_error", "iCloud Drive text file could not be copied safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )

    source_present = _path_exists_no_follow(source)
    target_present = _path_is_regular_file_no_follow(target)
    return _apply_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="copy_text",
        mutation_applied=True,
        expected_content_sha256=current_sha,
        source_present=source_present,
        expected_source_present=True,
        target_present=target_present,
        operation_flags={"copied": True},
        warnings=[],
    )


def _apply_move_text(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    approval_fingerprint: str,
) -> dict[str, Any]:
    resolved = _resolve_location_text_source(
        preview,
        root=root,
        max_scan_entries=max_scan_entries,
        verb="move",
    )
    if isinstance(resolved, dict):
        return resolved
    source, current_sha = resolved
    target_parent_result = _resolve_location_parent(
        str(preview["target"].get("parent_handle") or ""),
        fallback_parent=source.parent,
        plan={"preview": preview},
        root=root,
        max_scan_entries=max_scan_entries,
        required=True,
    )
    if isinstance(target_parent_result, dict):
        return target_parent_result
    target_parent = target_parent_result
    target_name = str(preview["target"].get("filename") or source.name)
    target = target_parent / target_name
    if _same_file_identity(source.parent, target_parent) and source.name == target_name:
        return _apply_location_success(
            source,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="move_text",
            mutation_applied=False,
            expected_content_sha256=current_sha,
            source_present=True,
            expected_source_present=True,
            target_present=True,
            operation_flags={"moved": False},
            warnings=[_warning("already_applied", "iCloud Drive file is already at the approved destination.")],
        )
    try:
        _move_text_file(source, target_parent, target_name, expected_sha=current_sha, root=root)
    except _ContentChangedDuringReplaceError:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _UnsupportedTextContentError:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be moved through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except _PartialLocationMutationError as exc:
        return _apply_location_success(
            target,
            root=root,
            idempotency_key=preview["idempotency_key"],
            approval_fingerprint=approval_fingerprint,
            operation="move_text",
            mutation_applied=True,
            expected_content_sha256=current_sha,
            source_present=_path_exists_no_follow(source),
            expected_source_present=False,
            target_present=_path_is_regular_file_no_follow(target),
            operation_flags={"moved": True},
            warnings=[_warning(exc.code, exc.safe_message)],
            status="partial",
        )
    except _UnsafeTargetError:
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive move target must not traverse packages or symlinks.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return _apply_error(
                [_warning("target_exists", "iCloud Drive target file already exists and will not be overwritten.")],
                plan={"preview": preview},
                content_inspected=True,
            )
        return _apply_error(
            [_warning("move_error", "iCloud Drive text file could not be moved safely.")],
            plan={"preview": preview},
            content_inspected=True,
        )

    source_present = _path_exists_no_follow(source)
    target_present = _path_is_regular_file_no_follow(target)
    return _apply_location_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="move_text",
        mutation_applied=True,
        expected_content_sha256=current_sha,
        source_present=source_present,
        expected_source_present=False,
        target_present=target_present,
        operation_flags={"moved": True},
        warnings=[],
    )


def _resolve_location_text_source(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    verb: str,
) -> tuple[Path, str] | dict[str, Any]:
    source = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if source is None or source.is_symlink() or not source.is_file():
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    try:
        source.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if source.suffix.lower() not in TEXT_SUFFIXES:
        return _apply_error(
            [_warning("unsupported_file_type", f"iCloud Drive {verb} supports text-like file extensions only.")],
            plan={"preview": preview},
        )
    if _has_package_component(source, root) or _has_symlink_component(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", f"iCloud Drive {verb} target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    try:
        existing_text = _read_supported_text(source, root=root)
    except OSError:
        return _apply_error(
            [_warning("read_error", f"iCloud Drive target file could not be read before {verb}.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    except UnicodeDecodeError:
        return _apply_error(
            [_warning("unsupported_file_type", f"Binary iCloud Drive files cannot be {verb}ed through this tool.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
    expected_sha = str(preview["target"]["expected_current_sha256"])
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
            content_inspected=True,
        )
    return source, current_sha


def _resolve_location_file_source(
    preview: dict[str, Any],
    *,
    root: Path,
    max_scan_entries: int,
    verb: str,
) -> tuple[Path, str] | dict[str, Any]:
    source = _resolve_handle(
        str(preview["target"]["handle"]),
        root,
        max_scan_entries=max_scan_entries,
    )
    if source is None or source.is_symlink() or not source.is_file():
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    try:
        source.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan={"preview": preview},
        )
    if source.suffix.lower() in TEXT_SUFFIXES:
        return _apply_error(
            [_warning("unsupported_file_type", f"Use the text-file operations for supported text-like files before {verb}.")],
            plan={"preview": preview},
        )
    if _has_package_component(source, root) or _has_symlink_component(source, root):
        return _apply_error(
            [_warning("unsupported_file_type", f"iCloud Drive regular-file {verb} target must not traverse packages or symlinks.")],
            plan={"preview": preview},
        )
    try:
        source_stat = source.lstat()
    except OSError:
        return _apply_error(
            [_warning("target_file_not_found", "iCloud Drive target file was not found.")],
            plan={"preview": preview},
            status="not_found",
        )
    if not stat.S_ISREG(source_stat.st_mode):
        return _apply_error(
            [_warning("unsupported_file_type", "iCloud Drive regular-file operations require a regular file handle.")],
            plan={"preview": preview},
        )
    current_sha = _file_metadata_sha256_from_stat(source, root, source_stat)
    expected_sha = str(preview["target"]["expected_current_sha256"])
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_metadata_changed", "iCloud Drive regular-file metadata did not match the approved plan.")],
            plan={"preview": preview},
        )
    return source, current_sha


def _resolve_location_parent(
    parent_handle: str,
    *,
    fallback_parent: Path,
    plan: dict[str, Any] | None,
    root: Path,
    max_scan_entries: int,
    required: bool,
) -> Path | dict[str, Any]:
    parent = fallback_parent
    if parent_handle:
        resolved = _resolve_handle(parent_handle, root, max_scan_entries=max_scan_entries)
        if resolved is None or resolved.is_symlink() or not _is_directory_no_follow(resolved):
            return _apply_error(
                [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
                plan=plan,
                status="not_found",
            )
        parent = resolved
    elif required:
        return _apply_error(
            [_warning("invalid_parent_handle", "iCloud Drive move requires an exact target parent handle.")],
            plan=plan,
        )
    try:
        parent.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan=plan,
        )
    if _has_package_component(parent, root) or _has_symlink_component(parent, root):
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan=plan,
            status="not_found",
        )
    return parent


def _atomic_replace_text(target: Path, content: str, *, expected_sha: str, root: Path | None = None) -> None:
    _atomic_replace_bytes(target, content.encode("utf-8"), expected_sha=expected_sha, root=root)


def _delete_text_file_permanently(
    target: Path,
    *,
    expected_sha: str,
    expected_identity_sha256: str,
    root: Path,
) -> None:
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        raise _UnsafeTargetError()
    parent_fd = -1
    staging_fd = -1
    staging_root: Path | None = None
    staged_name = ""
    moved_to_staging = False
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        source_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not stat.S_ISREG(source_stat.st_mode):
            raise _UnsafeTargetError()
        current_identity_sha256 = _delete_text_identity_sha256_from_stat(target, root, source_stat)
        if current_identity_sha256 != expected_identity_sha256:
            raise _ApprovedFileIdentityChangedError()
        existing_text = _decode_supported_text(_read_file_bytes_no_follow_at(parent_fd, target.name))
        current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()

        staging_root = _delete_staging_root_for(root)
        staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if staging_root.is_symlink() or not _is_directory_no_follow(staging_root):
            raise _UnsafeTargetError()
        staging_fd = _open_directory_no_follow(staging_root)
        for _ in range(20):
            candidate = f"local-apple-data-delete-{secrets.token_hex(16)}"
            try:
                _renameatx_excl_no_follow(parent_fd, target.name, staging_fd, candidate)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    continue
                raise
            staged_name = candidate
            moved_to_staging = True
            break
        if not staged_name:
            raise OSError("delete staging name reservation failed")

        staged_stat = _entry_stat_no_follow_at(staging_fd, staged_name)
        if not _same_stat_identity(source_stat, staged_stat):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive staged file identity changed before delete.",
            )
        try:
            staged_text = _decode_supported_text(_read_file_bytes_no_follow_at(staging_fd, staged_name))
            staged_sha = hashlib.sha256(staged_text.encode("utf-8")).hexdigest()
            if staged_sha != expected_sha:
                _rollback_staged_file_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
                raise _ContentChangedDuringReplaceError()
            os.unlink(staged_name, dir_fd=staging_fd)
            moved_to_staging = False
        except (_ContentChangedDuringReplaceError, _PartialLocationMutationError):
            raise
        except OSError:
            _rollback_staged_file_delete(
                staging_fd,
                staged_name,
                parent_fd,
                target.name,
                source_stat,
            )
            moved_to_staging = False
            raise
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(staging_fd)
    except _PartialLocationMutationError:
        raise
    except OSError:
        if moved_to_staging:
            try:
                _rollback_staged_file_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
            except _PartialLocationMutationError:
                raise
            raise
        raise
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
        if staging_root is not None:
            with contextlib.suppress(OSError):
                staging_root.rmdir()


def _rollback_staged_file_delete(
    staging_fd: int,
    staged_name: str,
    parent_fd: int,
    target_name: str,
    source_stat: os.stat_result,
) -> None:
    try:
        staged_stat = _entry_stat_no_follow_at(staging_fd, staged_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive staged file could not be verified before delete rollback.",
        ) from exc
    if not _same_stat_identity(source_stat, staged_stat):
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive staged file identity changed before delete rollback.",
        )
    try:
        _renameatx_excl_no_follow(staging_fd, staged_name, parent_fd, target_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "rollback_failed",
            "iCloud Drive file delete rollback could not restore the staged file.",
        ) from exc
    try:
        restored_stat = _entry_stat_no_follow_at(parent_fd, target_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "rollback_failed",
            "iCloud Drive file delete rollback could not verify restored file.",
        ) from exc
    if not _same_stat_identity(source_stat, restored_stat):
        raise _PartialLocationMutationError(
            "rollback_failed",
            "iCloud Drive file delete rollback restored a mismatched file.",
        )
    with contextlib.suppress(OSError):
        os.fsync(parent_fd)
    with contextlib.suppress(OSError):
        os.fsync(staging_fd)


def _move_text_file_to_trash(target: Path, *, expected_sha: str, root: Path) -> str:
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        raise _UnsafeTargetError()
    parent_fd = -1
    trash_fd = -1
    reserved_name = ""
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        existing_text = _decode_supported_text(_read_file_bytes_no_follow_at(parent_fd, target.name))
        current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()

        trash_root = _trash_root_for(root)
        trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if trash_root.is_symlink() or not _is_directory_no_follow(trash_root):
            raise _UnsafeTargetError()
        trash_fd = _open_directory_no_follow(trash_root)
        suffix = target.suffix
        stem = target.stem or "icloud-drive-item"
        for _ in range(20):
            candidate = f"local-apple-data-{secrets.token_hex(8)}-{stem}{suffix}"
            reservation_fd = -1
            try:
                reservation_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=trash_fd,
                )
            except FileExistsError:
                continue
            finally:
                if reservation_fd >= 0:
                    os.close(reservation_fd)
            reserved_name = candidate
            break
        if not reserved_name:
            raise OSError("trash reservation could not be created")
        swapped = False
        moved_verified = False
        _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
        swapped = True
        moved_text = _decode_supported_text(_read_file_bytes_no_follow_at(trash_fd, reserved_name))
        moved_sha = hashlib.sha256(moved_text.encode("utf-8")).hexdigest()
        if moved_sha != expected_sha:
            _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
            swapped = False
            raise _ContentChangedDuringReplaceError()
        moved_verified = True
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(trash_fd)
        with contextlib.suppress(OSError):
            os.unlink(target.name, dir_fd=parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        moved_name = reserved_name
        reserved_name = ""
        swapped = False
        return moved_name
    finally:
        if reserved_name and trash_fd >= 0:
            if "swapped" in locals() and swapped and not moved_verified and parent_fd >= 0:
                with contextlib.suppress(OSError):
                    _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
                    swapped = False
            if ("swapped" not in locals() or not swapped) and not moved_verified:
                with contextlib.suppress(OSError):
                    os.unlink(reserved_name, dir_fd=trash_fd)
        if trash_fd >= 0:
            os.close(trash_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _move_folder_to_trash(target: Path, *, expected_sha: str, root: Path) -> tuple[str, bool]:
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        raise _UnsafeTargetError()
    parent_fd = -1
    trash_fd = -1
    reserved_name = ""
    swapped = False
    moved_verified = False
    reservation_stat: os.stat_result | None = None
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        source_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        current_sha = _directory_metadata_sha256(target, root)
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()
        trash_root = _trash_root_for(root)
        trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if trash_root.is_symlink() or not _is_directory_no_follow(trash_root):
            raise _UnsafeTargetError()
        trash_fd = _open_directory_no_follow(trash_root)
        stem = target.name or "icloud-drive-folder"
        for _ in range(20):
            candidate = f"local-apple-data-{secrets.token_hex(8)}-{stem}"
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=trash_fd)
            except FileExistsError:
                continue
            reservation_stat = _entry_stat_no_follow_at(trash_fd, candidate)
            reserved_name = candidate
            break
        if not reserved_name:
            raise OSError("trash folder reservation could not be created")

        _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
        swapped = True
        moved_stat = _entry_stat_no_follow_at(trash_fd, reserved_name)
        if not _same_stat_identity(source_stat, moved_stat):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive trashed folder identity changed before read-back.",
            )
        empty_folder_confirmed = _directory_empty_no_follow_at(trash_fd, reserved_name)
        moved_verified = True
        if not _safe_rmdir_created_entry(parent_fd, target.name, reservation_stat):
            raise _PartialLocationMutationError(
                "cleanup_unverified",
                "iCloud Drive folder Trash cleanup could not verify the placeholder identity.",
            )
        swapped = False
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(trash_fd)
        moved_name = reserved_name
        reserved_name = ""
        return moved_name, empty_folder_confirmed
    finally:
        if reserved_name and trash_fd >= 0:
            if swapped and not moved_verified and parent_fd >= 0:
                with contextlib.suppress(OSError):
                    _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
                    swapped = False
            if not swapped and not moved_verified:
                with contextlib.suppress(OSError):
                    _safe_rmdir_created_entry(trash_fd, reserved_name, reservation_stat)
        if trash_fd >= 0:
            os.close(trash_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _move_regular_file_to_trash(target: Path, *, expected_metadata_sha: str, root: Path) -> str:
    if (
        target.suffix.lower() in TEXT_SUFFIXES
        or _has_package_component(target, root)
        or _has_symlink_component(target, root)
    ):
        raise _UnsafeTargetError()
    parent_fd = -1
    trash_fd = -1
    reserved_name = ""
    swapped = False
    moved_verified = False
    reservation_stat: os.stat_result | None = None
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        source_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not stat.S_ISREG(source_stat.st_mode):
            raise _UnsafeTargetError()
        if _file_metadata_sha256_from_stat(target, root, source_stat) != expected_metadata_sha:
            raise _ContentChangedDuringReplaceError()

        trash_root = _trash_root_for(root)
        trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if trash_root.is_symlink() or not _is_directory_no_follow(trash_root):
            raise _UnsafeTargetError()
        trash_fd = _open_directory_no_follow(trash_root)
        suffix = target.suffix
        stem = target.stem or "icloud-drive-file"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        for _ in range(20):
            candidate = f"local-apple-data-{secrets.token_hex(8)}-{stem}{suffix}"
            reservation_fd = -1
            try:
                reservation_fd = os.open(candidate, flags, 0o600, dir_fd=trash_fd)
            except FileExistsError:
                continue
            try:
                reservation_stat = os.fstat(reservation_fd)
            finally:
                os.close(reservation_fd)
            reserved_name = candidate
            break
        if not reserved_name:
            raise OSError("trash file reservation could not be created")

        pre_swap_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not _same_stat_snapshot(source_stat, pre_swap_stat):
            raise _ContentChangedDuringReplaceError()
        _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
        swapped = True
        moved_stat = _entry_stat_no_follow_at(trash_fd, reserved_name)
        if not stat.S_ISREG(moved_stat.st_mode) or not _same_stat_relocated_snapshot(pre_swap_stat, moved_stat):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive trashed regular-file identity changed before read-back.",
            )
        moved_verified = True
        if not _safe_unlink_created_entry(parent_fd, target.name, reservation_stat):
            raise _PartialLocationMutationError(
                "cleanup_unverified",
                "iCloud Drive regular-file Trash cleanup could not verify the placeholder identity.",
            )
        swapped = False
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(trash_fd)
        moved_name = reserved_name
        reserved_name = ""
        return moved_name
    finally:
        if reserved_name and trash_fd >= 0:
            if swapped and not moved_verified and parent_fd >= 0:
                with contextlib.suppress(OSError):
                    _renameatx_swap_no_follow(parent_fd, target.name, trash_fd, reserved_name)
                    swapped = False
            if not swapped and not moved_verified:
                with contextlib.suppress(OSError):
                    _safe_unlink_created_entry(trash_fd, reserved_name, reservation_stat)
        if trash_fd >= 0:
            os.close(trash_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _delete_regular_file_permanently(target: Path, *, expected_metadata_sha: str, root: Path) -> None:
    if (
        target.suffix.lower() in TEXT_SUFFIXES
        or _has_package_component(target, root)
        or _has_symlink_component(target, root)
    ):
        raise _UnsafeTargetError()
    parent_fd = -1
    staging_fd = -1
    staging_root: Path | None = None
    staged_name = ""
    moved_to_staging = False
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        source_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not stat.S_ISREG(source_stat.st_mode):
            raise _UnsafeTargetError()
        if _file_metadata_sha256_from_stat(target, root, source_stat) != expected_metadata_sha:
            raise _ContentChangedDuringReplaceError()
        pre_move_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not _same_stat_snapshot(source_stat, pre_move_stat):
            raise _ContentChangedDuringReplaceError()

        staging_root = _delete_staging_root_for(root)
        staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if staging_root.is_symlink() or not _is_directory_no_follow(staging_root):
            raise _UnsafeTargetError()
        staging_fd = _open_directory_no_follow(staging_root)
        stem = target.stem or "icloud-drive-file"
        suffix = target.suffix
        for _ in range(20):
            candidate = f"local-apple-data-delete-{secrets.token_hex(8)}-{stem}{suffix}"
            try:
                _renameatx_excl_no_follow(parent_fd, target.name, staging_fd, candidate)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    continue
                raise
            staged_name = candidate
            moved_to_staging = True
            break
        if not staged_name:
            raise OSError("delete staging name reservation failed")

        staged_stat = _entry_stat_no_follow_at(staging_fd, staged_name)
        if not stat.S_ISREG(staged_stat.st_mode) or not _same_stat_relocated_snapshot(pre_move_stat, staged_stat):
            _rollback_staged_file_delete(
                staging_fd,
                staged_name,
                parent_fd,
                target.name,
                source_stat,
            )
            moved_to_staging = False
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive staged regular-file identity changed before delete.",
            )
        os.unlink(staged_name, dir_fd=staging_fd)
        moved_to_staging = False
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(staging_fd)
    except _PartialLocationMutationError:
        raise
    except OSError:
        if moved_to_staging:
            try:
                _rollback_staged_file_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
            except _PartialLocationMutationError:
                raise
            raise
        raise
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
        if staging_root is not None:
            with contextlib.suppress(OSError):
                staging_root.rmdir()


def _delete_empty_folder_permanently(target: Path, *, expected_sha: str, root: Path) -> None:
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        raise _UnsafeTargetError()
    parent_fd = -1
    staging_fd = -1
    staging_root: Path | None = None
    staged_name = ""
    moved_to_staging = False
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        source_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not stat.S_ISDIR(source_stat.st_mode):
            raise _UnsafeTargetError()
        current_sha = _directory_metadata_sha256(target, root)
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()
        if not _directory_empty_no_follow_at(parent_fd, target.name):
            raise _FolderBecameNonEmptyAfterApplyError()

        staging_root = _delete_staging_root_for(root)
        staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if staging_root.is_symlink() or not _is_directory_no_follow(staging_root):
            raise _UnsafeTargetError()
        staging_fd = _open_directory_no_follow(staging_root)
        stem = target.name or "icloud-drive-folder"
        for _ in range(20):
            candidate = f"local-apple-data-delete-{secrets.token_hex(8)}-{stem}"
            try:
                _renameatx_excl_no_follow(parent_fd, target.name, staging_fd, candidate)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    continue
                raise
            staged_name = candidate
            moved_to_staging = True
            break
        if not staged_name:
            raise OSError("delete staging name reservation failed")

        staged_stat = _entry_stat_no_follow_at(staging_fd, staged_name)
        if not _same_stat_identity(source_stat, staged_stat):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive staged folder identity changed before delete.",
            )
        try:
            if not _directory_empty_no_follow_at(staging_fd, staged_name):
                _rollback_staged_directory_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
                raise _FolderBecameNonEmptyAfterApplyError()
            os.rmdir(staged_name, dir_fd=staging_fd)
            moved_to_staging = False
        except (_FolderBecameNonEmptyAfterApplyError, _PartialLocationMutationError):
            raise
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                _rollback_staged_directory_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
                raise
            _rollback_staged_directory_delete(
                staging_fd,
                staged_name,
                parent_fd,
                target.name,
                source_stat,
            )
            moved_to_staging = False
            raise _FolderBecameNonEmptyAfterApplyError() from exc
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(staging_fd)
    except _PartialLocationMutationError:
        raise
    except OSError as exc:
        if moved_to_staging:
            try:
                _rollback_staged_directory_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
            except _PartialLocationMutationError:
                raise
            raise
        raise
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
        if staging_root is not None:
            with contextlib.suppress(OSError):
                staging_root.rmdir()


def _delete_folder_tree_permanently(
    target: Path,
    *,
    expected_sha: str,
    expected_tree_sha: str,
    root: Path,
) -> bool:
    if _has_package_component(target, root) or _has_symlink_component(target, root):
        raise _UnsafeTargetError()
    parent_fd = -1
    staging_fd = -1
    staging_root: Path | None = None
    staged_name = ""
    moved_to_staging = False
    tree_delete_started = False
    source_stat: os.stat_result | None = None
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        source_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not stat.S_ISDIR(source_stat.st_mode):
            raise _UnsafeTargetError()
        current_sha = _directory_metadata_sha256_from_stat(target, root, source_stat)
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()
        snapshot_stat, entries = _folder_copy_tree_snapshot(
            target,
            root,
            max_entries=MAX_FOLDER_COPY_TREE_ENTRIES,
        )
        if not _same_stat_identity(source_stat, snapshot_stat):
            raise _ContentChangedDuringReplaceError()
        if _folder_copy_tree_sha256(target, root, snapshot_stat, entries) != expected_tree_sha:
            raise _ContentChangedDuringReplaceError()
        empty_folder_confirmed = not entries
        expected_entries = _folder_tree_entries_by_relative(entries)

        staging_root = _delete_staging_root_for(root)
        staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if staging_root.is_symlink() or not _is_directory_no_follow(staging_root):
            raise _UnsafeTargetError()
        staging_fd = _open_directory_no_follow(staging_root)
        stem = target.name or "icloud-drive-folder"
        for _ in range(20):
            candidate = f"local-apple-data-delete-{secrets.token_hex(8)}-{stem}"
            try:
                _renameatx_excl_no_follow(parent_fd, target.name, staging_fd, candidate)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    continue
                raise
            staged_name = candidate
            moved_to_staging = True
            break
        if not staged_name:
            raise OSError("delete staging name reservation failed")

        staged_stat = _entry_stat_no_follow_at(staging_fd, staged_name)
        if not _same_stat_identity(source_stat, staged_stat):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive staged folder identity changed before delete.",
            )
        staged_path = staging_root / staged_name
        if not _created_folder_tree_matches(staged_path, staged_stat, expected_entries):
            _rollback_staged_directory_delete(
                staging_fd,
                staged_name,
                parent_fd,
                target.name,
                source_stat,
            )
            moved_to_staging = False
            raise _ContentChangedDuringReplaceError()
        tree_delete_started = True
        if not _safe_remove_created_folder_tree(staged_path, staged_stat, expected_entries, root=root):
            raise _PartialLocationMutationError(
                "delete_unverified",
                "iCloud Drive staged folder tree could not be permanently deleted with bounded proof.",
            )
        moved_to_staging = False
        tree_delete_started = False
        with contextlib.suppress(OSError):
            os.fsync(parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(staging_fd)
        return empty_folder_confirmed
    except _PartialLocationMutationError:
        raise
    except OSError:
        if moved_to_staging and not tree_delete_started and source_stat is not None:
            try:
                _rollback_staged_directory_delete(
                    staging_fd,
                    staged_name,
                    parent_fd,
                    target.name,
                    source_stat,
                )
                moved_to_staging = False
            except _PartialLocationMutationError:
                raise
        if moved_to_staging and tree_delete_started:
            raise _PartialLocationMutationError(
                "delete_unverified",
                "iCloud Drive staged folder tree could not be permanently deleted with bounded proof.",
            )
        raise
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
        if staging_root is not None:
            with contextlib.suppress(OSError):
                staging_root.rmdir()


def _rollback_staged_directory_delete(
    staging_fd: int,
    staged_name: str,
    parent_fd: int,
    target_name: str,
    source_stat: os.stat_result,
) -> None:
    try:
        staged_stat = _entry_stat_no_follow_at(staging_fd, staged_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive staged folder could not be verified before delete rollback.",
        ) from exc
    if not _same_stat_identity(source_stat, staged_stat):
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive staged folder identity changed before delete rollback.",
        )
    try:
        _renameatx_excl_no_follow(staging_fd, staged_name, parent_fd, target_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "rollback_failed",
            "iCloud Drive folder delete rollback could not restore the staged folder.",
        ) from exc
    with contextlib.suppress(OSError):
        os.fsync(parent_fd)
    with contextlib.suppress(OSError):
        os.fsync(staging_fd)


def _folder_tree_entries_by_relative(entries: list[dict[str, Any]]) -> dict[str, tuple[str, os.stat_result]]:
    return {
        str(entry["relative_path"]): (str(entry["kind"]), entry["stat"])
        for entry in entries
    }


def _move_text_file(source: Path, target_parent: Path, target_name: str, *, expected_sha: str, root: Path) -> None:
    target = target_parent / target_name
    if (
        _has_package_component(source, root)
        or _has_symlink_component(source, root)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    reservation_stat: os.stat_result | None = None
    reservation_location = ""
    moved_verified = False
    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        source_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        existing_text = _decode_supported_text(_read_file_bytes_no_follow_at(source_parent_fd, source.name))
        current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        reservation_fd = os.open(target_name, flags, 0o600, dir_fd=target_parent_fd)
        try:
            reservation_stat = os.fstat(reservation_fd)
        finally:
            os.close(reservation_fd)
        reservation_location = "target"
        _renameatx_swap_no_follow(source_parent_fd, source.name, target_parent_fd, target_name)
        reservation_location = "source"
        target_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        try:
            moved_text = _decode_supported_text(_read_file_bytes_no_follow_at(target_parent_fd, target_name))
        except UnicodeDecodeError as exc:
            try:
                _rollback_location_swap(
                    source_parent_fd,
                    source.name,
                    target_parent_fd,
                    target_name,
                    target_stat,
                    reservation_stat,
                )
                reservation_location = ""
            except _PartialLocationMutationError:
                reservation_location = ""
                raise
            raise _ContentChangedDuringReplaceError() from exc
        moved_sha = hashlib.sha256(moved_text.encode("utf-8")).hexdigest()
        if not _same_stat_identity(source_stat, target_stat) or moved_sha != expected_sha:
            try:
                _rollback_location_swap(
                    source_parent_fd,
                    source.name,
                    target_parent_fd,
                    target_name,
                    target_stat,
                    reservation_stat,
                )
                reservation_location = ""
            except _PartialLocationMutationError:
                reservation_location = ""
                raise
            raise _ContentChangedDuringReplaceError()
        moved_verified = True
        if not _safe_unlink_created_entry(source_parent_fd, source.name, reservation_stat):
            raise _PartialLocationMutationError(
                "cleanup_unverified",
                "iCloud Drive relocation cleanup could not verify the placeholder identity.",
            )
        reservation_location = ""
        with contextlib.suppress(OSError):
            os.fsync(source_parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    except UnicodeDecodeError as exc:
        raise _UnsupportedTextContentError() from exc
    finally:
        if reservation_location == "target" and target_parent_fd >= 0:
            with contextlib.suppress(OSError):
                _safe_unlink_created_entry(target_parent_fd, target_name, reservation_stat)
        elif reservation_location == "source" and not moved_verified and source_parent_fd >= 0 and target_parent_fd >= 0:
            with contextlib.suppress(OSError):
                _renameatx_swap_no_follow(source_parent_fd, source.name, target_parent_fd, target_name)
                _safe_unlink_created_entry(target_parent_fd, target_name, reservation_stat)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _move_regular_file(
    source: Path,
    target_parent: Path,
    target_name: str,
    *,
    expected_metadata_sha: str,
    root: Path,
) -> None:
    target = target_parent / target_name
    if (
        source.suffix.lower() in TEXT_SUFFIXES
        or Path(target_name).suffix.lower() in TEXT_SUFFIXES
        or _has_package_component(source, root)
        or _has_symlink_component(source, root)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    reservation_stat: os.stat_result | None = None
    reservation_location = ""
    moved_verified = False
    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        source_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not stat.S_ISREG(source_stat.st_mode):
            raise _UnsafeTargetError()
        if _file_metadata_sha256_from_stat(source, root, source_stat) != expected_metadata_sha:
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        reservation_fd = os.open(target_name, flags, 0o600, dir_fd=target_parent_fd)
        try:
            reservation_stat = os.fstat(reservation_fd)
        finally:
            os.close(reservation_fd)
        reservation_location = "target"
        pre_swap_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not _same_stat_snapshot(source_stat, pre_swap_stat):
            raise _ContentChangedDuringReplaceError()
        _renameatx_swap_no_follow(source_parent_fd, source.name, target_parent_fd, target_name)
        reservation_location = "source"
        target_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        if not _same_stat_relocated_snapshot(pre_swap_stat, target_stat):
            try:
                _rollback_location_swap(
                    source_parent_fd,
                    source.name,
                    target_parent_fd,
                    target_name,
                    target_stat,
                    reservation_stat,
                )
                reservation_location = ""
            except _PartialLocationMutationError:
                reservation_location = ""
                raise
            raise _ContentChangedDuringReplaceError()
        moved_verified = True
        if not _safe_unlink_created_entry(source_parent_fd, source.name, reservation_stat):
            raise _PartialLocationMutationError(
                "cleanup_unverified",
                "iCloud Drive regular-file relocation cleanup could not verify the placeholder identity.",
            )
        reservation_location = ""
        with contextlib.suppress(OSError):
            os.fsync(source_parent_fd)
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    finally:
        if reservation_location == "target" and target_parent_fd >= 0:
            with contextlib.suppress(OSError):
                _safe_unlink_created_entry(target_parent_fd, target_name, reservation_stat)
        elif reservation_location == "source" and not moved_verified and source_parent_fd >= 0 and target_parent_fd >= 0:
            with contextlib.suppress(OSError):
                _renameatx_swap_no_follow(source_parent_fd, source.name, target_parent_fd, target_name)
                _safe_unlink_created_entry(target_parent_fd, target_name, reservation_stat)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _copy_text_file(source: Path, target_parent: Path, target_name: str, *, expected_sha: str, root: Path) -> None:
    target = target_parent / target_name
    if (
        _has_package_component(source, root)
        or _has_symlink_component(source, root)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    target_fd = -1
    target_created = False
    created_stat: os.stat_result | None = None
    verified = False
    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        source_bytes = _read_file_bytes_no_follow_at(source_parent_fd, source.name)
        existing_text = _decode_supported_text(source_bytes)
        current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        target_fd = os.open(target_name, flags, 0o600, dir_fd=target_parent_fd)
        target_created = True
        created_stat = os.fstat(target_fd)
        _write_all(target_fd, source_bytes)
        os.fsync(target_fd)
        os.close(target_fd)
        target_fd = -1
        copied_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        if not _same_stat_identity(created_stat, copied_stat):
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive copy target identity changed before read-back.",
            )
        copied_text = _decode_supported_text(_read_file_bytes_no_follow_at(target_parent_fd, target_name))
        copied_sha = hashlib.sha256(copied_text.encode("utf-8")).hexdigest()
        if copied_sha != expected_sha:
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive copied text hash did not match during read-back.",
            )
        try:
            source_after_text = _decode_supported_text(_read_file_bytes_no_follow_at(source_parent_fd, source.name))
        except (OSError, UnicodeDecodeError) as exc:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive copy cleanup could not verify the failed target identity.",
                ) from exc
            raise _ContentChangedDuringReplaceError() from exc
        source_after_sha = hashlib.sha256(source_after_text.encode("utf-8")).hexdigest()
        if source_after_sha != expected_sha:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive copy cleanup could not verify the failed target identity.",
                )
            raise _ContentChangedDuringReplaceError()
        verified = True
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    except _PartialLocationMutationError:
        raise
    except UnicodeDecodeError as exc:
        if target_created:
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive copied text could not be decoded during read-back.",
            ) from exc
        raise _UnsupportedTextContentError() from exc
    except OSError as exc:
        if target_created and not verified and target_parent_fd >= 0:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive copy cleanup could not verify the failed target identity.",
                ) from exc
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _copy_regular_file(
    source: Path,
    target_parent: Path,
    target_name: str,
    *,
    expected_metadata_sha: str,
    root: Path,
) -> None:
    target = target_parent / target_name
    if (
        source.suffix.lower() in TEXT_SUFFIXES
        or Path(target_name).suffix.lower() in TEXT_SUFFIXES
        or _has_package_component(source, root)
        or _has_symlink_component(source, root)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    target_fd = -1
    target_created = False
    created_stat: os.stat_result | None = None
    verified = False
    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        source_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not stat.S_ISREG(source_stat.st_mode):
            raise _UnsafeTargetError()
        if _file_metadata_sha256_from_stat(source, root, source_stat) != expected_metadata_sha:
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        target_fd = os.open(target_name, flags, 0o600, dir_fd=target_parent_fd)
        target_created = True
        created_stat = os.fstat(target_fd)
        source_digest = _copy_regular_file_stream_no_follow_at(
            source_parent_fd,
            source.name,
            target_fd,
            expected_stat=source_stat,
        )
        os.fsync(target_fd)
        os.close(target_fd)
        target_fd = -1
        copied_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        if not _same_stat_identity(created_stat, copied_stat) or copied_stat.st_size != source_stat.st_size:
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive regular-file copy target identity changed before read-back.",
            )
        copied_digest = _hash_regular_file_stream_no_follow_at(
            target_parent_fd,
            target_name,
            expected_stat=copied_stat,
        )
        if copied_digest != source_digest:
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive copied regular-file bytes did not match during read-back.",
            )
        try:
            source_after_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        except OSError as exc:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive regular-file copy cleanup could not verify the failed target identity.",
                ) from exc
            raise _ContentChangedDuringReplaceError() from exc
        if not _same_stat_snapshot(source_stat, source_after_stat):
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive regular-file copy cleanup could not verify the failed target identity.",
                )
            raise _ContentChangedDuringReplaceError()
        verified = True
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    except _PartialLocationMutationError:
        raise
    except OSError as exc:
        if target_created and not verified and target_parent_fd >= 0:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive regular-file copy cleanup could not verify the failed target identity.",
                ) from exc
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _folder_copy_tree_fingerprint(
    source: Path,
    root: Path,
    *,
    max_entries: int,
) -> tuple[str, bool]:
    source_stat, entries = _folder_copy_tree_snapshot(source, root, max_entries=max_entries)
    return _folder_copy_tree_sha256(source, root, source_stat, entries), not entries


def _folder_copy_tree_snapshot(
    source: Path,
    root: Path,
    *,
    max_entries: int,
) -> tuple[os.stat_result, list[dict[str, Any]]]:
    source_stat = source.lstat()
    if source.name.startswith(".") or not stat.S_ISDIR(source_stat.st_mode):
        raise _UnsafeTargetError()
    entries: list[dict[str, Any]] = []
    stack = [(source, source_stat)]
    total_bytes = 0
    while stack:
        directory, directory_stat = stack.pop()
        directory_fd = -1
        try:
            directory_fd = _open_resolved_directory_no_follow(directory, root, expected_stat=directory_stat)
            with os.scandir(directory_fd) as child_entries:
                names: list[str] = []
                for entry in child_entries:
                    if len(entries) + len(names) + 1 > max_entries:
                        raise _FolderCopyTooLargeError()
                    names.append(entry.name)
                names.sort(key=lambda value: (value.casefold(), value))
        except OSError:
            raise
        try:
            for name in names:
                if name.startswith("."):
                    raise _UnsafeTargetError()
                path = directory / name
                path_stat = _entry_stat_no_follow_at(directory_fd, name)
                if stat.S_ISLNK(path_stat.st_mode) or _has_package_component(path, root):
                    raise _UnsafeTargetError()
                try:
                    relative_path = path.relative_to(source).as_posix()
                except ValueError as exc:
                    raise _UnsafeTargetError() from exc
                if stat.S_ISDIR(path_stat.st_mode):
                    entries.append({"relative_path": relative_path, "kind": "directory", "stat": path_stat})
                    stack.append((path, path_stat))
                elif stat.S_ISREG(path_stat.st_mode):
                    total_bytes += path_stat.st_size
                    if total_bytes > MAX_FOLDER_COPY_TREE_BYTES:
                        raise _FolderCopyTooLargeError()
                    entries.append({"relative_path": relative_path, "kind": "file", "stat": path_stat})
                else:
                    raise _UnsafeTargetError()
                if len(entries) > max_entries:
                    raise _FolderCopyTooLargeError()
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)
    entries.sort(key=lambda entry: str(entry["relative_path"]))
    return source_stat, entries


def _folder_copy_tree_sha256(
    source: Path,
    root: Path,
    source_stat: os.stat_result,
    entries: list[dict[str, Any]],
) -> str:
    payload = {
        "source": _relative_path(source, root),
        "source_stat": _folder_copy_stat_payload(source_stat),
        "entries": [
            {
                "relative_path": str(entry["relative_path"]),
                "kind": str(entry["kind"]),
                "stat": _folder_copy_stat_payload(entry["stat"]),
            }
            for entry in entries
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _folder_copy_stat_payload(path_stat: os.stat_result) -> dict[str, int]:
    return {
        "mode": stat.S_IFMT(path_stat.st_mode),
        "size": path_stat.st_size,
        "mtime_ns": path_stat.st_mtime_ns,
        "ctime_ns": path_stat.st_ctime_ns,
        "dev": path_stat.st_dev,
        "ino": path_stat.st_ino,
    }


def _copy_folder_tree(
    source: Path,
    target_parent: Path,
    target_name: str,
    *,
    expected_metadata_sha: str,
    expected_tree_sha: str,
    root: Path,
) -> None:
    target = target_parent / target_name
    if (
        source.name.startswith(".")
        or target_name.startswith(".")
        or _has_package_component(source, root)
        or _has_symlink_component(source, root)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_stat, entries = _folder_copy_tree_snapshot(
        source,
        root,
        max_entries=MAX_FOLDER_COPY_TREE_ENTRIES,
    )
    if not stat.S_ISDIR(source_stat.st_mode):
        raise _UnsafeTargetError()
    if _directory_metadata_sha256_from_stat(source, root, source_stat) != expected_metadata_sha:
        raise _ContentChangedDuringReplaceError()
    if _folder_copy_tree_sha256(source, root, source_stat, entries) != expected_tree_sha:
        raise _ContentChangedDuringReplaceError()

    target_parent_fd = -1
    created_root_stat: os.stat_result | None = None
    created_entries: dict[str, tuple[str, os.stat_result]] = {}
    verified = False
    try:
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        os.mkdir(target_name, 0o700, dir_fd=target_parent_fd)
        created_root_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        if not stat.S_ISDIR(created_root_stat.st_mode):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive copied folder target could not be verified after apply.",
            )

        for entry in sorted(
            (item for item in entries if item["kind"] == "directory"),
            key=lambda item: (str(item["relative_path"]).count("/"), str(item["relative_path"])),
        ):
            relative_path = Path(str(entry["relative_path"]))
            child_stat = _mkdir_created_folder_entry(
                target,
                relative_path,
                created_root_stat,
                created_entries,
                root=root,
            )
            created_entries[relative_path.as_posix()] = ("directory", child_stat)

        for entry in sorted(
            (item for item in entries if item["kind"] == "file"),
            key=lambda item: str(item["relative_path"]),
        ):
            relative_path = Path(str(entry["relative_path"]))
            parent_relative = relative_path.parent
            if parent_relative == Path("."):
                expected_parent_stat = created_root_stat
            else:
                parent_entry = created_entries.get(parent_relative.as_posix())
                if parent_entry is None or parent_entry[0] != "directory":
                    raise _UnsafeTargetError()
                expected_parent_stat = parent_entry[1]
            copied_stat = _copy_folder_file_entry(
                source / relative_path,
                target / relative_path,
                root=root,
                expected_stat=entry["stat"],
                expected_target_parent_stat=expected_parent_stat,
            )
            created_entries[relative_path.as_posix()] = ("file", copied_stat)

        source_after_stat, entries_after = _folder_copy_tree_snapshot(
            source,
            root,
            max_entries=MAX_FOLDER_COPY_TREE_ENTRIES,
        )
        if not _same_stat_snapshot(source_stat, source_after_stat):
            raise _ContentChangedDuringReplaceError()
        if _folder_copy_tree_sha256(source, root, source_after_stat, entries_after) != expected_tree_sha:
            raise _ContentChangedDuringReplaceError()
        if not _created_folder_tree_matches(target, created_root_stat, created_entries):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive copied folder tree could not be verified after apply.",
            )
        verified = True
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    except Exception as exc:
        if created_root_stat is not None and not verified:
            cleaned = _safe_remove_created_folder_tree(target, created_root_stat, created_entries, root=root)
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive folder copy cleanup could not verify or remove the created target safely.",
                ) from exc
            if isinstance(exc, _PartialLocationMutationError):
                raise _FolderCopyCleanedError(exc.code, exc.safe_message) from exc
        raise
    finally:
        if target_parent_fd >= 0:
            os.close(target_parent_fd)


def _created_folder_parent_fd(
    target_root: Path,
    relative_path: Path,
    created_root_stat: os.stat_result,
    created_entries: dict[str, tuple[str, os.stat_result]],
) -> int:
    if relative_path.is_absolute() or not relative_path.parts or any(part in {"", ".", ".."} for part in relative_path.parts):
        raise _UnsafeTargetError()
    parent_relative = relative_path.parent
    if parent_relative == Path("."):
        parent = target_root
        parent_expected_stat = created_root_stat
    else:
        parent_key = parent_relative.as_posix()
        parent_entry = created_entries.get(parent_key)
        if parent_entry is None or parent_entry[0] != "directory":
            raise _UnsafeTargetError()
        parent = target_root / parent_relative
        parent_expected_stat = parent_entry[1]
    return _open_resolved_directory_no_follow(parent, target_root, expected_stat=parent_expected_stat)


def _mkdir_created_folder_entry(
    target_root: Path,
    relative_path: Path,
    created_root_stat: os.stat_result,
    created_entries: dict[str, tuple[str, os.stat_result]],
    *,
    root: Path,
) -> os.stat_result:
    target = target_root / relative_path
    if _has_package_component(target, root) or _has_symlink_parent_component(target, root):
        raise _UnsafeTargetError()
    parent_fd = _created_folder_parent_fd(target_root, relative_path, created_root_stat, created_entries)
    try:
        try:
            os.mkdir(relative_path.name, 0o700, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise _PartialLocationMutationError(
                    "read_back_mismatch",
                    "iCloud Drive copied folder target tree changed during apply.",
                ) from exc
            raise
        child_stat = _entry_stat_no_follow_at(parent_fd, relative_path.name)
        if not stat.S_ISDIR(child_stat.st_mode):
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive copied folder target directory could not be verified after apply.",
            )
        return child_stat
    finally:
        os.close(parent_fd)


def _copy_folder_file_entry(
    source: Path,
    target: Path,
    *,
    root: Path,
    expected_stat: os.stat_result,
    expected_target_parent_stat: os.stat_result,
) -> os.stat_result:
    if (
        _has_package_component(source, root)
        or _has_symlink_component(source, root)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    target_fd = -1
    created_stat: os.stat_result | None = None
    verified = False
    try:
        source_parent_fd = _open_resolved_directory_no_follow(source.parent, root)
        target_parent_fd = _open_resolved_directory_no_follow(
            target.parent,
            root,
            expected_stat=expected_target_parent_stat,
        )
        current_source_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not stat.S_ISREG(current_source_stat.st_mode) or not _same_stat_snapshot(expected_stat, current_source_stat):
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        target_fd = os.open(target.name, flags, 0o600, dir_fd=target_parent_fd)
        created_stat = os.fstat(target_fd)
        source_digest = _copy_regular_file_stream_no_follow_at(
            source_parent_fd,
            source.name,
            target_fd,
            expected_stat=current_source_stat,
        )
        os.fsync(target_fd)
        os.close(target_fd)
        target_fd = -1
        copied_stat = _entry_stat_no_follow_at(target_parent_fd, target.name)
        if not _same_stat_identity(created_stat, copied_stat) or copied_stat.st_size != current_source_stat.st_size:
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive folder file-copy target identity changed before read-back.",
            )
        copied_digest = _hash_regular_file_stream_no_follow_at(
            target_parent_fd,
            target.name,
            expected_stat=copied_stat,
        )
        if copied_digest != source_digest:
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive copied folder file bytes did not match during read-back.",
            )
        source_after_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not _same_stat_snapshot(current_source_stat, source_after_stat):
            raise _ContentChangedDuringReplaceError()
        verified = True
        return copied_stat
    except Exception:
        if created_stat is not None and not verified and target_parent_fd >= 0:
            if not _safe_unlink_created_entry(target_parent_fd, target.name, created_stat):
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive folder file-copy cleanup could not verify the failed target identity.",
                )
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _import_regular_file(
    source: Path,
    source_stat: os.stat_result,
    target_parent: Path,
    target_name: str,
    *,
    expected_source_content_sha256: str,
    root: Path,
) -> None:
    target = target_parent / target_name
    if (
        source.suffix.lower() in TEXT_SUFFIXES
        or Path(target_name).suffix.lower() in TEXT_SUFFIXES
        or _has_package_component_absolute(source)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    target_fd = -1
    target_created = False
    created_stat: os.stat_result | None = None
    verified = False
    try:
        source_parent_fd = _open_absolute_directory_no_follow(source.parent)
        target_parent_fd = _open_resolved_directory_no_follow(target_parent, root)
        current_source_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not stat.S_ISREG(current_source_stat.st_mode) or not _same_stat_snapshot(source_stat, current_source_stat):
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        target_fd = os.open(target_name, flags, 0o600, dir_fd=target_parent_fd)
        target_created = True
        created_stat = os.fstat(target_fd)
        source_digest = _copy_regular_file_stream_no_follow_at(
            source_parent_fd,
            source.name,
            target_fd,
            expected_stat=current_source_stat,
        )
        if source_digest.hex() != expected_source_content_sha256:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive import cleanup could not verify the failed target identity.",
                )
            raise _ContentChangedDuringReplaceError()
        os.fsync(target_fd)
        os.close(target_fd)
        target_fd = -1
        copied_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        if not _same_stat_identity(created_stat, copied_stat) or copied_stat.st_size != current_source_stat.st_size:
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive imported target identity changed before read-back.",
            )
        copied_digest = _hash_regular_file_stream_no_follow_at(
            target_parent_fd,
            target_name,
            expected_stat=copied_stat,
        )
        if copied_digest != source_digest:
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive imported bytes did not match during read-back.",
            )
        try:
            source_after_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        except OSError as exc:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive import cleanup could not verify the failed target identity.",
                ) from exc
            raise _ContentChangedDuringReplaceError() from exc
        if not _same_stat_snapshot(current_source_stat, source_after_stat):
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive import cleanup could not verify the failed target identity.",
                )
            raise _ContentChangedDuringReplaceError()
        verified = True
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    except _PartialLocationMutationError:
        raise
    except OSError as exc:
        if target_created and not verified and target_parent_fd >= 0:
            cleaned = _safe_unlink_created_entry(target_parent_fd, target_name, created_stat)
            target_created = not cleaned
            if not cleaned:
                raise _PartialLocationMutationError(
                    "cleanup_unverified",
                    "iCloud Drive import cleanup could not verify the failed target identity.",
                ) from exc
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _replace_regular_file_from_source(
    source: Path,
    source_stat: os.stat_result,
    target: Path,
    *,
    expected_target_metadata_sha: str,
    expected_source_content_sha256: str,
    root: Path,
) -> None:
    source_suffix = source.suffix.lower()
    target_suffix = target.suffix.lower()
    if (
        source_suffix in TEXT_SUFFIXES
        or target_suffix in TEXT_SUFFIXES
        or source_suffix != target_suffix
        or _has_package_component_absolute(source)
        or _has_package_component(target, root)
        or _has_symlink_parent_component(target, root)
    ):
        raise _UnsafeTargetError()
    source_parent_fd = -1
    target_parent_fd = -1
    temp_fd = -1
    temp_name = ""
    temp_stat: os.stat_result | None = None
    replaced = False
    try:
        source_parent_fd = _open_absolute_directory_no_follow(source.parent)
        target_parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        current_source_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not stat.S_ISREG(current_source_stat.st_mode) or not _same_stat_snapshot(source_stat, current_source_stat):
            raise _SourceFileChangedDuringReplaceError()
        current_target_stat = _entry_stat_no_follow_at(target_parent_fd, target.name)
        if not stat.S_ISREG(current_target_stat.st_mode):
            raise _UnsafeTargetError()
        if _file_metadata_sha256_from_stat(target, root, current_target_stat) != expected_target_metadata_sha:
            raise _ContentChangedDuringReplaceError()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        for _ in range(10):
            candidate = f".{target.name}.{secrets.token_hex(8)}.tmp"
            try:
                temp_fd = os.open(candidate, flags, 0o600, dir_fd=target_parent_fd)
            except FileExistsError:
                continue
            temp_name = candidate
            temp_stat = os.fstat(temp_fd)
            break
        if temp_fd < 0 or not temp_name:
            raise OSError("temporary file could not be created")
        try:
            source_digest = _copy_regular_file_stream_no_follow_at(
                source_parent_fd,
                source.name,
                temp_fd,
                expected_stat=current_source_stat,
            )
        except _ContentChangedDuringReplaceError as exc:
            raise _SourceFileChangedDuringReplaceError() from exc
        if source_digest.hex() != expected_source_content_sha256:
            raise _SourceFileChangedDuringReplaceError()
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = -1
        copied_stat = _entry_stat_no_follow_at(target_parent_fd, temp_name)
        if temp_stat is None or not _same_stat_identity(temp_stat, copied_stat) or copied_stat.st_size != current_source_stat.st_size:
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive replacement temporary file identity changed before apply.",
            )
        copied_digest = _hash_regular_file_stream_no_follow_at(
            target_parent_fd,
            temp_name,
            expected_stat=copied_stat,
        )
        if copied_digest != source_digest:
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive replacement bytes did not match before apply.",
            )
        source_after_stat = _entry_stat_no_follow_at(source_parent_fd, source.name)
        if not _same_stat_snapshot(current_source_stat, source_after_stat):
            raise _SourceFileChangedDuringReplaceError()
        target_after_stat = _entry_stat_no_follow_at(target_parent_fd, target.name)
        if not _same_stat_snapshot(current_target_stat, target_after_stat):
            raise _ContentChangedDuringReplaceError()
        os.replace(temp_name, target.name, src_dir_fd=target_parent_fd, dst_dir_fd=target_parent_fd)
        replaced = True
        temp_name = ""
        replaced_stat = _entry_stat_no_follow_at(target_parent_fd, target.name)
        if not _same_stat_identity(temp_stat, replaced_stat) or replaced_stat.st_size != current_source_stat.st_size:
            raise _PartialLocationMutationError(
                "read_back_unavailable",
                "iCloud Drive replaced target identity changed before read-back.",
            )
        replaced_digest = _hash_regular_file_stream_no_follow_at(
            target_parent_fd,
            target.name,
            expected_stat=replaced_stat,
        )
        if replaced_digest != source_digest:
            raise _PartialLocationMutationError(
                "read_back_mismatch",
                "iCloud Drive replaced target bytes did not match during read-back.",
            )
        with contextlib.suppress(OSError):
            os.fsync(target_parent_fd)
    except (_ContentChangedDuringReplaceError, _SourceFileChangedDuringReplaceError, _PartialLocationMutationError, _UnsafeTargetError):
        raise
    except OSError:
        raise
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if temp_name and not replaced and target_parent_fd >= 0:
            with contextlib.suppress(OSError):
                os.unlink(temp_name, dir_fd=target_parent_fd)
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if source_parent_fd >= 0:
            os.close(source_parent_fd)


def _trash_root_for(root: Path) -> Path:
    expanded_root = root.expanduser()
    configured_root = os.environ.get("LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT")
    if expanded_root == Path.home() / "Library/Mobile Documents/com~apple~CloudDocs":
        return Path.home() / ".Trash"
    if configured_root and expanded_root == Path(configured_root).expanduser():
        return expanded_root / ".Trash"
    return expanded_root / ".Trash"


def _delete_staging_root_for(root: Path) -> Path:
    return root.expanduser() / ".local-apple-data-delete-staging"


def _atomic_replace_bytes(target: Path, content: bytes, *, expected_sha: str, root: Path | None = None) -> None:
    temp_name = ""
    parent_fd = -1
    try:
        if root is not None and (_has_package_component(target, root) or _has_symlink_component(target, root)):
            raise _UnsafeTargetError()
        parent_fd = _open_directory_no_follow(target.parent)
        temp_fd = -1
        for _ in range(10):
            candidate = f".{target.name}.{secrets.token_hex(8)}.tmp"
            try:
                temp_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temp_name = candidate
            break
        if temp_fd < 0:
            raise OSError("temporary file could not be created")
        try:
            _write_all(temp_fd, content)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        if root is not None and (_has_package_component(target, root) or _has_symlink_component(target, root)):
            raise _UnsafeTargetError()
        existing_text = _decode_supported_text(_read_file_bytes_no_follow_at(parent_fd, target.name))
        current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
        if current_sha != expected_sha:
            raise _ContentChangedDuringReplaceError()
        os.replace(temp_name, target.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temp_name = ""
        os.fsync(parent_fd)
    finally:
        if temp_name:
            with contextlib.suppress(OSError):
                if parent_fd >= 0:
                    os.unlink(temp_name, dir_fd=parent_fd)
                else:
                    Path(target.parent / temp_name).unlink()
        if parent_fd >= 0:
            os.close(parent_fd)


class _ContentChangedDuringReplaceError(OSError):
    pass


class _ApprovedFileIdentityChangedError(OSError):
    pass


class _SourceFileChangedDuringReplaceError(OSError):
    pass


class _UnsafeTargetError(OSError):
    pass


class _UnsupportedTextContentError(OSError):
    pass


class _FolderBecameNonEmptyAfterApplyError(OSError):
    pass


class _FolderCopyTooLargeError(OSError):
    pass


class _FolderCopyCleanedError(OSError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class _PartialLocationMutationError(OSError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def _open_resolved_directory_no_follow(
    path: Path,
    root: Path,
    *,
    expected_stat: os.stat_result | None = None,
) -> int:
    expected = expected_stat if expected_stat is not None else path.lstat()
    relative = Path(_relative_path(path, root))
    fd = _open_directory_relative_no_follow(root.expanduser(), relative.parts)
    try:
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise _UnsafeTargetError()
        return fd
    except Exception:
        os.close(fd)
        raise


def _entry_stat_no_follow_at(parent_fd: int, name: str) -> os.stat_result:
    return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)


def _same_stat_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _same_stat_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        _same_stat_identity(left, right)
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
        and left.st_ctime_ns == right.st_ctime_ns
    )


def _same_stat_relocated_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        _same_stat_identity(left, right)
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _path_exists_no_follow(path: Path) -> bool:
    try:
        path.lstat()
    except OSError:
        return False
    return True


def _path_is_regular_file_no_follow(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode)


def _path_is_directory_no_follow(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISDIR(mode)


def _directory_empty_no_follow(path: Path, root: Path) -> bool:
    fd = _open_resolved_directory_no_follow(path, root)
    try:
        return _directory_fd_empty(fd)
    finally:
        os.close(fd)


def _directory_fd_empty(fd: int) -> bool:
    with os.scandir(fd) as entries:
        return next(entries, None) is None


def _directory_empty_no_follow_at(parent_fd: int, name: str) -> bool:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISDIR(mode):
            raise OSError("not a directory")
        return _directory_fd_empty(fd)
    finally:
        os.close(fd)


def _safe_unlink_created_entry(parent_fd: int, name: str, created_stat: os.stat_result | None) -> bool:
    if created_stat is None:
        return False
    try:
        current_stat = _entry_stat_no_follow_at(parent_fd, name)
    except OSError:
        return True
    if not _same_stat_identity(created_stat, current_stat):
        return False
    try:
        os.unlink(name, dir_fd=parent_fd)
    except OSError:
        return False
    return True


def _safe_rmdir_created_entry(parent_fd: int, name: str, created_stat: os.stat_result | None) -> bool:
    if created_stat is None:
        return False
    try:
        current_stat = _entry_stat_no_follow_at(parent_fd, name)
    except OSError:
        return True
    if not _same_stat_identity(created_stat, current_stat):
        return False
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        return False
    return True


def _safe_remove_created_folder_tree(
    target: Path,
    created_root_stat: os.stat_result,
    created_entries: dict[str, tuple[str, os.stat_result]],
    *,
    root: Path,
) -> bool:
    try:
        current_root_stat = target.lstat()
    except OSError:
        return True
    if not _same_stat_identity(created_root_stat, current_root_stat):
        return False
    if not _created_folder_tree_matches(target, created_root_stat, created_entries):
        return False
    for relative_path, (kind, expected_stat) in sorted(
        created_entries.items(),
        key=lambda item: item[0].count("/"),
        reverse=True,
    ):
        if not _remove_created_folder_entry(
            target,
            Path(relative_path),
            kind,
            expected_stat,
            created_root_stat,
            created_entries,
        ):
            return False
    parent_fd = -1
    try:
        parent_fd = _open_resolved_directory_no_follow(target.parent, root)
        current_root_stat = _entry_stat_no_follow_at(parent_fd, target.name)
        if not stat.S_ISDIR(current_root_stat.st_mode) or not _same_stat_identity(created_root_stat, current_root_stat):
            return False
        os.rmdir(target.name, dir_fd=parent_fd)
    except OSError:
        return False
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
    return True


def _remove_created_folder_entry(
    target_root: Path,
    relative_path: Path,
    kind: str,
    expected_stat: os.stat_result,
    created_root_stat: os.stat_result,
    created_entries: dict[str, tuple[str, os.stat_result]],
) -> bool:
    parent_fd = -1
    try:
        parent_fd = _created_folder_parent_fd(target_root, relative_path, created_root_stat, created_entries)
        current_stat = _entry_stat_no_follow_at(parent_fd, relative_path.name)
        if not _same_stat_identity(expected_stat, current_stat):
            return False
        if kind == "file":
            if not stat.S_ISREG(current_stat.st_mode):
                return False
            os.unlink(relative_path.name, dir_fd=parent_fd)
        else:
            if not stat.S_ISDIR(current_stat.st_mode):
                return False
            os.rmdir(relative_path.name, dir_fd=parent_fd)
        return True
    except OSError:
        return False
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def _created_folder_tree_matches(
    target: Path,
    created_root_stat: os.stat_result,
    created_entries: dict[str, tuple[str, os.stat_result]],
) -> bool:
    try:
        current_root_stat = target.lstat()
    except OSError:
        return False
    if not _same_stat_identity(created_root_stat, current_root_stat):
        return False
    children_by_parent: dict[str, set[str]] = {"": set()}
    for relative_path in created_entries:
        path = Path(relative_path)
        parent = "" if path.parent == Path(".") else path.parent.as_posix()
        children_by_parent.setdefault(parent, set()).add(path.name)
        if created_entries[relative_path][0] == "directory":
            children_by_parent.setdefault(relative_path, set())

    for parent_relative, expected_names in children_by_parent.items():
        if parent_relative:
            expected_parent = created_entries.get(parent_relative)
            if expected_parent is None or expected_parent[0] != "directory":
                return False
            parent = target / parent_relative
            parent_expected_stat = expected_parent[1]
        else:
            parent = target
            parent_expected_stat = created_root_stat
        parent_fd = -1
        try:
            parent_fd = _open_resolved_directory_no_follow(parent, target, expected_stat=parent_expected_stat)
            observed_names: set[str] = set()
            with os.scandir(parent_fd) as entries:
                for entry in entries:
                    if entry.name not in expected_names or entry.name in observed_names:
                        return False
                    relative_path = entry.name if not parent_relative else f"{parent_relative}/{entry.name}"
                    expected = created_entries.get(relative_path)
                    if expected is None:
                        return False
                    expected_kind, expected_stat = expected
                    path_stat = _entry_stat_no_follow_at(parent_fd, entry.name)
                    if not _same_stat_identity(expected_stat, path_stat):
                        return False
                    if expected_kind == "file" and not stat.S_ISREG(path_stat.st_mode):
                        return False
                    if expected_kind == "directory" and not stat.S_ISDIR(path_stat.st_mode):
                        return False
                    observed_names.add(entry.name)
                    if len(observed_names) > len(expected_names):
                        return False
            if observed_names != expected_names:
                return False
        except OSError:
            return False
        finally:
            if parent_fd >= 0:
                os.close(parent_fd)
    return True


def _rollback_location_swap(
    source_parent_fd: int,
    source_name: str,
    target_parent_fd: int,
    target_name: str,
    moved_stat: os.stat_result,
    reservation_stat: os.stat_result | None,
) -> None:
    if reservation_stat is None:
        raise _PartialLocationMutationError(
            "cleanup_unverified",
            "iCloud Drive relocation rollback could not verify the placeholder identity.",
        )
    try:
        current_target_stat = _entry_stat_no_follow_at(target_parent_fd, target_name)
        current_source_stat = _entry_stat_no_follow_at(source_parent_fd, source_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive relocated file could not be verified before rollback.",
        ) from exc
    if not _same_stat_identity(moved_stat, current_target_stat):
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive relocated file identity changed before rollback.",
        )
    if not _same_stat_identity(reservation_stat, current_source_stat):
        raise _PartialLocationMutationError(
            "cleanup_unverified",
            "iCloud Drive relocation placeholder identity changed before rollback.",
        )
    try:
        _renameatx_swap_no_follow(source_parent_fd, source_name, target_parent_fd, target_name)
    except OSError as exc:
        raise _PartialLocationMutationError(
            "read_back_mismatch",
            "iCloud Drive relocated file could not be rolled back after read-back mismatch.",
        ) from exc
    if not _safe_unlink_created_entry(target_parent_fd, target_name, reservation_stat):
        raise _PartialLocationMutationError(
            "cleanup_unverified",
            "iCloud Drive relocation cleanup could not verify the placeholder identity.",
        )


def _open_directory_relative_no_follow(root: Path, parts: tuple[str, ...]) -> int:
    current_fd = _open_directory_no_follow(root)
    for part in parts:
        next_fd = -1
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            next_fd = os.open(part, flags, dir_fd=current_fd)
            mode = os.fstat(next_fd).st_mode
            if not stat.S_ISDIR(mode):
                raise OSError("not a directory")
        except Exception:
            if next_fd >= 0:
                os.close(next_fd)
            os.close(current_fd)
            raise
        os.close(current_fd)
        current_fd = next_fd
    return current_fd


def _open_absolute_directory_no_follow(path: Path) -> int:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if not absolute.is_absolute():
        raise OSError("not an absolute path")
    current_fd = _open_directory_no_follow(Path(absolute.anchor))
    for part in absolute.parts[1:]:
        next_fd = -1
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            next_fd = os.open(part, flags, dir_fd=current_fd)
            mode = os.fstat(next_fd).st_mode
            if not stat.S_ISDIR(mode):
                raise OSError("not a directory")
        except Exception:
            if next_fd >= 0:
                os.close(next_fd)
            os.close(current_fd)
            raise
        os.close(current_fd)
        current_fd = next_fd
    return current_fd


def _renameatx_swap_no_follow(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
    _renameatx_np(from_fd, from_name, to_fd, to_name, RENAME_SWAP | RENAME_NOFOLLOW_ANY)


def _renameatx_excl_no_follow(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
    _renameatx_np(from_fd, from_name, to_fd, to_name, RENAME_EXCL | RENAME_NOFOLLOW_ANY)


def _renameatx_np(from_fd: int, from_name: str, to_fd: int, to_name: str, flags: int) -> None:
    try:
        renameatx_np = ctypes.CDLL(None, use_errno=True).renameatx_np
    except AttributeError as exc:
        raise OSError(errno.ENOTSUP, "renameatx_np unavailable") from exc
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        from_fd,
        os.fsencode(from_name),
        to_fd,
        os.fsencode(to_name),
        flags,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _plan_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": False,
        "preview": None,
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any] | None,
    status: str = "error",
    mutation_applied: bool = False,
    content_inspected: bool = False,
) -> dict[str, Any]:
    preview = plan.get("preview") if isinstance(plan, dict) else None
    normalized_preview = preview if isinstance(preview, dict) else None
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=content_inspected),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": normalized_preview is not None,
        "preview": normalized_preview,
        "read_back": None,
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    operation: str,
    mutation_applied: bool,
    expected_content_sha256: str = "",
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    metadata = _path_metadata(target, root)
    try:
        content_text = _read_supported_text(target, root=root)
    except (OSError, UnicodeDecodeError):
        content_text = ""
        warnings = warnings + [_warning("read_back_unavailable", "iCloud Drive read-back could not read created content.")]
    read_back = {
        **metadata,
        "content_chars": len(content_text),
        "content_sha256": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
    }
    status = "ok"
    if expected_content_sha256 and read_back["content_sha256"] != expected_content_sha256:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive read-back content hash did not match the approved mutation.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=True),
        "mode": "apply",
        "operation": operation,
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_directory_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    operation: str,
    mutation_applied: bool,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    read_back = _path_metadata(target, root)
    status = "ok"
    if read_back["kind"] != "directory":
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive read-back metadata did not match the approved folder create.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": operation,
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_folder_path_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    mutation_applied: bool,
    created_count: int,
    existing_count: int,
    component_count: int,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    read_back = {
        "name": target.name,
        "kind": "directory",
        "component_count": component_count,
        "created_count": created_count,
        "existing_count": existing_count,
        "final_folder_verified": False,
        "content_text_returned": False,
        "content_hash_returned": False,
    }
    status = "ok"
    try:
        metadata = _path_metadata(target, root)
        if metadata["kind"] != "directory":
            raise OSError("not a directory")
        read_back.update(
            {
                **metadata,
                "component_count": component_count,
                "created_count": created_count,
                "existing_count": existing_count,
                "final_folder_verified": True,
                "content_text_returned": False,
                "content_hash_returned": False,
            }
        )
    except OSError:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_unavailable",
                "iCloud Drive folder path read-back was unavailable after apply.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "create_folder_path",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_folder_path_partial(
    preview: dict[str, Any],
    *,
    approval_fingerprint: str,
    created_count: int,
    existing_count: int,
    component_count: int,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "partial",
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "create_folder_path",
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": {
            "kind": "directory_path",
            "component_count": component_count,
            "created_count": created_count,
            "existing_count": existing_count,
            "final_folder_verified": False,
            "content_text_returned": False,
            "content_hash_returned": False,
            "raw_path_returned": False,
        },
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_location_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    operation: str,
    mutation_applied: bool,
    expected_content_sha256: str,
    source_present: bool,
    expected_source_present: bool,
    target_present: bool,
    operation_flags: dict[str, bool],
    warnings: list[dict[str, str]],
    status: str = "ok",
) -> dict[str, Any]:
    read_back: dict[str, Any] = {
        "name": target.name,
        "kind": "file",
        "content_type": "text",
        "source_present": source_present,
        "target_present": target_present,
        "content_text_returned": False,
        **operation_flags,
    }
    with contextlib.suppress(ValueError):
        read_back["handle"] = make_opaque_handle("icloud:file", _relative_path(target, root))
    if target_present:
        try:
            metadata = _path_metadata(target, root)
            content_text = _read_supported_text(target, root=root)
            read_back.update(
                {
                    **metadata,
                    "content_chars": len(content_text),
                    "content_sha256": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
                    "source_present": source_present,
                    "target_present": target_present,
                    "content_text_returned": False,
                    **operation_flags,
                }
            )
        except (OSError, UnicodeDecodeError):
            status = "partial"
            warnings = warnings + [
                _warning(
                    "read_back_unavailable",
                    "iCloud Drive read-back could not read relocated content.",
                )
            ]
    else:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive target file was missing after apply.",
            )
        ]
    if read_back.get("content_sha256") and read_back["content_sha256"] != expected_content_sha256:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive read-back content hash did not match the approved mutation.",
            )
        ]
    if source_present != expected_source_present:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive source-handle presence did not match the approved mutation.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=True),
        "mode": "apply",
        "operation": operation,
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_regular_file_location_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    operation: str,
    mutation_applied: bool,
    source_present: bool,
    expected_source_present: bool,
    target_present: bool,
    operation_flags: dict[str, bool],
    warnings: list[dict[str, str]],
    status: str = "ok",
) -> dict[str, Any]:
    read_back: dict[str, Any] = {
        "name": target.name,
        "kind": "file",
        "content_type": "regular_file",
        "source_present": source_present,
        "target_present": target_present,
        "content_text_returned": False,
        "content_hash_returned": False,
        **operation_flags,
    }
    with contextlib.suppress(ValueError):
        read_back["handle"] = make_opaque_handle("icloud:file", _relative_path(target, root))
    if target_present:
        try:
            metadata = _path_metadata(target, root)
            if metadata["kind"] != "file":
                raise OSError("not a regular file")
            read_back.update(
                {
                    **metadata,
                    "content_type": "regular_file",
                    "source_present": source_present,
                    "target_present": target_present,
                    "content_text_returned": False,
                    "content_hash_returned": False,
                    **operation_flags,
                }
            )
        except OSError:
            status = "partial"
            warnings = warnings + [
                _warning(
                    "read_back_unavailable",
                    "iCloud Drive regular-file read-back was unavailable after apply.",
                )
            ]
    else:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive target regular file was missing after apply.",
            )
        ]
    if source_present != expected_source_present:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive source-handle presence did not match the approved mutation.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": operation,
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_import_file_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    mutation_applied: bool,
    imported: bool,
    warnings: list[dict[str, str]],
    status: str = "ok",
) -> dict[str, Any]:
    target_present = _path_is_regular_file_no_follow(target)
    read_back: dict[str, Any] = {
        "name": target.name,
        "kind": "file",
        "content_type": "regular_file",
        "target_present": target_present,
        "imported": imported,
        "source_path_returned": False,
        "source_hash_returned": False,
        "content_text_returned": False,
        "content_hash_returned": False,
    }
    with contextlib.suppress(ValueError):
        read_back["handle"] = make_opaque_handle("icloud:file", _relative_path(target, root))
    if target_present:
        try:
            metadata = _path_metadata(target, root)
            if metadata["kind"] != "file":
                raise OSError("not a regular file")
            read_back.update(
                {
                    **metadata,
                    "content_type": "regular_file",
                    "target_present": target_present,
                    "imported": imported,
                    "source_path_returned": False,
                    "source_hash_returned": False,
                    "content_text_returned": False,
                    "content_hash_returned": False,
                }
            )
        except OSError:
            status = "partial"
            warnings = warnings + [
                _warning(
                    "read_back_unavailable",
                    "iCloud Drive imported file read-back was unavailable after apply.",
                )
            ]
    else:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive imported file was missing after apply.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "import_file",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_replace_file_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    mutation_applied: bool,
    replaced: bool,
    warnings: list[dict[str, str]],
    status: str = "ok",
) -> dict[str, Any]:
    target_present = _path_is_regular_file_no_follow(target)
    read_back: dict[str, Any] = {
        "name": target.name,
        "kind": "file",
        "content_type": "regular_file",
        "target_present": target_present,
        "replaced": replaced,
        "source_path_returned": False,
        "source_hash_returned": False,
        "content_text_returned": False,
        "content_hash_returned": False,
    }
    with contextlib.suppress(ValueError):
        read_back["handle"] = make_opaque_handle("icloud:file", _relative_path(target, root))
    if target_present:
        try:
            metadata = _path_metadata(target, root)
            if metadata["kind"] != "file":
                raise OSError("not a regular file")
            read_back.update(
                {
                    **metadata,
                    "content_type": "regular_file",
                    "target_present": target_present,
                    "replaced": replaced,
                    "source_path_returned": False,
                    "source_hash_returned": False,
                    "content_text_returned": False,
                    "content_hash_returned": False,
                }
            )
        except OSError:
            status = "partial"
            warnings = warnings + [
                _warning(
                    "read_back_unavailable",
                    "iCloud Drive replaced file read-back was unavailable after apply.",
                )
            ]
    else:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive replaced file was missing after apply.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "replace_file",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_directory_unverified_target_partial(
    target: Path,
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    operation: str,
    mutation_applied: bool,
    source_present: bool,
    expected_source_present: bool,
    target_present: bool,
    operation_flags: dict[str, bool],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    read_back: dict[str, Any] = {
        "name": target.name,
        "kind": "directory",
        "source_present": source_present,
        "target_present": target_present,
        "content_text_returned": False,
        "content_hash_returned": False,
        **operation_flags,
    }
    if source_present != expected_source_present:
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive source-handle presence did not match the approved mutation.",
            )
        ]
    return {
        "schema_version": 1,
        "status": "partial",
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": operation,
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_directory_location_success(
    target: Path,
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    operation: str,
    mutation_applied: bool,
    source_present: bool,
    expected_source_present: bool,
    target_present: bool,
    operation_flags: dict[str, bool],
    warnings: list[dict[str, str]],
    status: str = "ok",
    require_empty_folder: bool = True,
) -> dict[str, Any]:
    read_back: dict[str, Any] = {
        "name": target.name,
        "kind": "directory",
        "source_present": source_present,
        "target_present": target_present,
        "content_text_returned": False,
        "content_hash_returned": False,
        **operation_flags,
    }
    with contextlib.suppress(ValueError):
        read_back["handle"] = make_opaque_handle("icloud:file", _relative_path(target, root))
    if target_present:
        try:
            metadata = _path_metadata(target, root)
            empty_folder_confirmed = _directory_empty_no_follow(target, root)
            read_back.update(
                {
                    **metadata,
                    "source_present": source_present,
                    "target_present": target_present,
                    "content_text_returned": False,
                    "content_hash_returned": False,
                    "empty_folder_confirmed": empty_folder_confirmed,
                    "non_empty_allowed": not require_empty_folder,
                    **operation_flags,
                }
            )
            if require_empty_folder and not empty_folder_confirmed:
                status = "partial"
                warnings = warnings + [
                    _warning(
                        "folder_not_empty_after_apply",
                        "iCloud Drive folder became non-empty during directory apply.",
                    )
                ]
        except OSError:
            status = "partial"
            warnings = warnings + [
                _warning(
                    "read_back_unavailable",
                    "iCloud Drive folder read-back was unavailable after apply.",
                )
            ]
    else:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive target folder was missing after apply.",
            )
        ]
    if source_present != expected_source_present:
        status = "partial"
        warnings = warnings + [
            _warning(
                "read_back_mismatch",
                "iCloud Drive source-handle presence did not match the approved mutation.",
            )
        ]
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": operation,
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_trash_success(
    preview: dict[str, Any],
    *,
    root: Path,
    idempotency_key: str,
    approval_fingerprint: str,
    original_name: str,
    trashed_name: str,
    content_sha256: str,
    original_present: bool,
    status: str,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=True),
        "mode": "apply",
        "operation": "trash_text",
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": preview["target"]["handle"],
            "name": original_name,
            "kind": "file",
            "content_type": "text",
            "content_sha256": content_sha256,
            "original_present": original_present,
            "trashed": True,
            "trash_name_sha256": hashlib.sha256(trashed_name.encode("utf-8")).hexdigest(),
            "trash_path_returned": False,
        },
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_delete_text_success(
    preview: dict[str, Any],
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    original_name: str,
    original_present: bool,
    status: str,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=True),
        "mode": "apply",
        "operation": "delete_text",
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": preview["target"]["handle"],
            "name": original_name,
            "kind": "file",
            "content_type": "text",
            "original_present": original_present,
            "verified_absent": status == "ok" and not original_present,
            "permanently_deleted": status == "ok" and not original_present,
            "trash_path_returned": False,
            "staging_path_returned": False,
            "content_text_returned": False,
            "content_hash_returned": False,
        },
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_trash_folder_success(
    preview: dict[str, Any],
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    original_name: str,
    trashed_name: str,
    original_present: bool,
    empty_folder_confirmed: bool,
    non_empty_allowed: bool,
    status: str,
    warnings: list[dict[str, str]],
    trashed: bool = True,
    mutation_applied: bool = True,
) -> dict[str, Any]:
    read_back = {
        "handle": preview["target"]["handle"],
        "name": original_name,
        "kind": "directory",
        "original_present": original_present,
        "trashed": trashed,
        "trash_path_returned": False,
        "content_text_returned": False,
        "content_hash_returned": False,
        "empty_folder_confirmed": empty_folder_confirmed,
        "non_empty_allowed": non_empty_allowed,
    }
    if trashed_name:
        read_back["trash_name_sha256"] = hashlib.sha256(trashed_name.encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "trash_folder",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_trash_file_success(
    preview: dict[str, Any],
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    original_name: str,
    trashed_name: str,
    original_present: bool,
    status: str,
    warnings: list[dict[str, str]],
    trashed: bool = True,
    mutation_applied: bool = True,
) -> dict[str, Any]:
    read_back = {
        "handle": preview["target"]["handle"],
        "name": original_name,
        "kind": "file",
        "content_type": "regular_file",
        "original_present": original_present,
        "trashed": trashed,
        "trash_path_returned": False,
        "content_text_returned": False,
        "content_hash_returned": False,
    }
    if trashed_name:
        read_back["trash_name_sha256"] = hashlib.sha256(trashed_name.encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "trash_file",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": read_back,
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_delete_folder_success(
    preview: dict[str, Any],
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    original_name: str,
    original_present: bool,
    empty_folder_confirmed: bool,
    non_empty_allowed: bool,
    status: str,
    warnings: list[dict[str, str]],
    mutation_applied: bool = True,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "delete_folder",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": preview["target"]["handle"],
            "name": original_name,
            "kind": "directory",
            "original_present": original_present,
            "verified_absent": status == "ok" and not original_present,
            "permanently_deleted": status == "ok" and not original_present,
            "trash_path_returned": False,
            "staging_path_returned": False,
            "content_text_returned": False,
            "content_hash_returned": False,
            "empty_folder_confirmed": empty_folder_confirmed,
            "non_empty_allowed": non_empty_allowed,
        },
        "result_count": 1,
        "warnings": warnings,
    }


def _apply_delete_file_success(
    preview: dict[str, Any],
    *,
    idempotency_key: str,
    approval_fingerprint: str,
    original_name: str,
    original_present: bool,
    mutation_applied: bool,
    status: str,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "operation": "delete_file",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "idempotency_key": idempotency_key,
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": {
            "handle": preview["target"]["handle"],
            "name": original_name,
            "kind": "file",
            "content_type": "regular_file",
            "original_present": original_present,
            "verified_absent": status == "ok" and not original_present,
            "permanently_deleted": status == "ok" and not original_present,
            "trash_path_returned": False,
            "staging_path_returned": False,
            "content_text_returned": False,
            "content_hash_returned": False,
        },
        "result_count": 1,
        "warnings": warnings,
    }


def _same_file_identity(left: Path, right: Path) -> bool:
    try:
        left_stat = left.lstat()
        right_stat = right.lstat()
    except OSError:
        return False
    return (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino)


def _safe_warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        payload,
        _warning,
        fallback_message="iCloud Drive warning detail was redacted.",
    )


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"icloud-drive-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

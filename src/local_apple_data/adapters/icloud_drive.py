from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_ICLOUD_DRIVE_ROOT = (
    Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
)
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_SCAN_ENTRIES = 20000
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
    root: Path = DEFAULT_ICLOUD_DRIVE_ROOT,
    limit: int = 20,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
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
    root: Path = DEFAULT_ICLOUD_DRIVE_ROOT,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
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


def get_icloud_drive_content(
    handle: str,
    *,
    root: Path = DEFAULT_ICLOUD_DRIVE_ROOT,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
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

    result = _path_metadata(path, root)
    result.update({"content_text": "", "content_chars": 0, "truncated": False})
    if result["kind"] != "file":
        return _content_unavailable(result, "unsupported_file_type")
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return _content_unavailable(result, "unsupported_file_type")

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    try:
        raw = path.read_bytes()
    except OSError:
        return _content_unavailable(result, "read_error")
    if b"\x00" in raw[:4096]:
        return _content_unavailable(result, "unsupported_file_type")

    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    truncated = len(text) > bounded_chars
    content_text = text[:bounded_chars] if truncated else text
    result.update(
        {
            "content_text": content_text,
            "content_chars": len(content_text),
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


def _root_available(root: Path) -> bool:
    try:
        return root.expanduser().is_dir() and os.access(root.expanduser(), os.R_OK)
    except OSError:
        return False


def _iter_entries(root: Path, *, max_entries: int):
    root = root.expanduser()
    yielded = 0
    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not dirname.startswith(".")
        ]
        current = Path(current_root)
        for dirname in dirnames:
            path = current / dirname
            if path.is_symlink():
                continue
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


def _path_metadata(path: Path, root: Path) -> dict[str, Any]:
    stat = path.stat()
    relative = _relative_path(path, root)
    return {
        "handle": make_opaque_handle("icloud:file", relative),
        "name": path.name,
        "extension": path.suffix.lower() or None,
        "kind": "file" if path.is_file() else "directory" if path.is_dir() else "other",
        "size": stat.st_size if path.is_file() else None,
        "modified": int(stat.st_mtime),
        "depth": len(Path(relative).parts),
    }


def _resolve_handle(handle: str, root: Path, *, max_scan_entries: int) -> Path | None:
    for path in _iter_entries(root, max_entries=max_scan_entries):
        relative = _relative_path(path, root)
        if opaque_handle_matches(handle, "icloud:file", relative):
            return path
    return None


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root.expanduser()).as_posix()

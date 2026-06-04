from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_ICLOUD_DRIVE_ROOT = (
    Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
)
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_PREVIEW_FILENAME_CHARS = 255
MAX_SCAN_ENTRIES = 20000
PLAN_OPERATIONS = {"create_text", "append_text"}
APPROVAL_TOKEN_PREFIX = "icloud-drive-apply:v1:"
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


def plan_icloud_drive_change(
    operation: str,
    *,
    parent_handle: str = "",
    handle: str = "",
    filename: str = "",
    content_text: str = "",
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation create_text or append_text."))

    normalized_parent_handle = parent_handle.strip()
    normalized_handle = handle.strip()
    if normalized_operation == "create_text" and not is_opaque_handle(
        normalized_parent_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_parent_handle",
                "Expected icloud:file:v1 opaque directory handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "append_text" and not is_opaque_handle(
        normalized_handle,
        "icloud:file",
    ):
        warnings.append(
            _warning(
                "invalid_handle",
                "Expected icloud:file:v1 opaque file handle from iCloud Drive search output.",
            )
        )
    if normalized_operation == "create_text" and normalized_handle:
        warnings.append(
            _warning(
                "unexpected_handle",
                "Create-text planning requires a parent handle, not a file handle.",
            )
        )
    if normalized_operation == "append_text" and (normalized_parent_handle or filename.strip()):
        warnings.append(
            _warning(
                "unexpected_create_target",
                "Append-text planning requires a file handle, not a parent handle or filename.",
            )
        )

    normalized_filename = ""
    if normalized_operation == "create_text":
        normalized_filename, filename_warning = _normalize_create_filename(filename)
        if filename_warning is not None:
            warnings.append(filename_warning)

    normalized_content, content_warning = _normalize_create_text(content_text)
    if content_warning is not None:
        warnings.append(content_warning)

    normalized_expected_sha = ""
    if normalized_operation == "append_text":
        normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
        if sha_warning is not None:
            warnings.append(sha_warning)

    if warnings:
        return _plan_error(warnings)

    if normalized_operation == "create_text":
        target = {
            "parent_handle": normalized_parent_handle,
            "filename": normalized_filename,
        }
        proposed = {
            "kind": "file",
            "content_type": "text",
            "content_chars": len(normalized_content),
            "extension": Path(normalized_filename).suffix.lower() or None,
        }
    else:
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
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target,
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
    return {
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


def apply_icloud_drive_change(
    operation: str,
    *,
    parent_handle: str = "",
    handle: str = "",
    filename: str = "",
    content_text: str = "",
    expected_current_sha256: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    root: Path = DEFAULT_ICLOUD_DRIVE_ROOT,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> dict[str, Any]:
    plan = plan_icloud_drive_change(
        operation,
        parent_handle=parent_handle,
        handle=handle,
        filename=filename,
        content_text=content_text,
        expected_current_sha256=expected_current_sha256,
    )
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

    parent = _resolve_handle(parent_handle.strip(), root, max_scan_entries=max_scan_entries)
    if parent is None or not parent.is_dir():
        return _apply_error(
            [_warning("target_parent_not_found", "iCloud Drive parent directory was not found.")],
            plan=plan,
            status="not_found",
        )
    target = parent / preview["target"]["filename"]
    try:
        target.relative_to(root.expanduser())
    except ValueError:
        return _apply_error(
            [_warning("target_outside_root", "iCloud Drive target escaped the configured root.")],
            plan=plan,
        )
    normalized_content, _ = _normalize_create_text(content_text)
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except OSError:
            existing = None
        if existing == normalized_content:
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
        )
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(normalized_content)
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


def _normalize_create_text(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: content_text.")
    if len(normalized) > MAX_CONTENT_CHARS:
        return "", _warning("input_too_large", "content_text exceeds maximum length.")
    if "\x00" in normalized:
        return "", _warning("unsupported_file_type", "Binary content is not supported.")
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
    if target is None or not target.is_file():
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
    try:
        raw = target.read_bytes()
    except OSError:
        return _apply_error(
            [_warning("read_error", "iCloud Drive target file could not be read before append.")],
            plan={"preview": preview},
        )
    if b"\x00" in raw[:4096]:
        return _apply_error(
            [_warning("unsupported_file_type", "Binary iCloud Drive files cannot be appended through this tool.")],
            plan={"preview": preview},
        )

    existing_text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    current_sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
    expected_sha = str(preview["target"]["expected_current_sha256"])
    if current_sha != expected_sha:
        return _apply_error(
            [_warning("current_content_changed", "iCloud Drive target content hash did not match the approved plan.")],
            plan={"preview": preview},
        )

    normalized_content, content_warning = _normalize_create_text(content_text)
    if content_warning is not None:
        return _apply_error([content_warning], plan={"preview": preview})
    try:
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(normalized_content)
    except OSError:
        return _apply_error(
            [_warning("append_error", "iCloud Drive text could not be appended safely.")],
            plan={"preview": preview},
        )
    return _apply_success(
        target,
        root=root,
        idempotency_key=preview["idempotency_key"],
        approval_fingerprint=approval_fingerprint,
        operation="append_text",
        mutation_applied=True,
        warnings=[],
    )


def _plan_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "icloud_drive",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
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
) -> dict[str, Any]:
    preview = plan.get("preview") if isinstance(plan, dict) else None
    return {
        "schema_version": 1,
        "status": status,
        "source": "icloud_drive",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": preview if isinstance(preview, dict) else None,
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
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    metadata = _path_metadata(target, root)
    try:
        content_text = target.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        content_text = ""
        warnings = warnings + [_warning("read_back_unavailable", "iCloud Drive read-back could not read created content.")]
    read_back = {
        **metadata,
        "content_chars": len(content_text),
        "content_sha256": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
    }
    return {
        "schema_version": 1,
        "status": "ok",
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


def _safe_warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    safe: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and isinstance(message, str):
            safe.append(_warning(code, message))
    return safe


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"icloud-drive-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

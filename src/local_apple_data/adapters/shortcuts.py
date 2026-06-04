from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_SCAN_ITEMS = 5000
DEFAULT_TIMEOUT_SECONDS = 10.0
HANDLE_PREFIX = "shortcuts:item"
UUID_RE = re.compile(r"^(?P<name>.+?)\s+\((?P<identifier>[A-Fa-f0-9-]{36})\)$")
BLOCKED_BROAD_QUERIES = {
    "all",
    "automation",
    "automations",
    "folder",
    "folders",
    "list",
    "run",
    "shortcut",
    "shortcuts",
    "sign",
    "view",
    "workflow",
    "workflows",
}


@dataclass(frozen=True)
class ShortcutCommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


ShortcutRunner = Callable[[list[str], float], ShortcutCommandResult]


@dataclass(frozen=True)
class ShortcutItem:
    item_key: str
    title: str
    kind: str
    identifier_present: bool


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
        "shortcut_body_returned": False,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "shortcuts",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Shortcuts search requires a non-empty shortcut or folder name query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "shortcuts",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Shortcuts search requires a specific shortcut or folder name term.",
            )
        ],
    }


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "shortcuts",
        "privacy": _privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected shortcuts:item:v1 opaque handle from search output.",
            )
        ],
    }


def _unavailable_result(
    *,
    detail: bool = False,
    code: str = "shortcuts_cli_unavailable",
) -> dict[str, Any]:
    messages = {
        "shortcuts_cli_unavailable": "Apple Shortcuts CLI is missing or unavailable.",
        "shortcuts_cli_error": "Apple Shortcuts CLI returned an error.",
        "shortcuts_parse_error": "Apple Shortcuts CLI output could not be parsed safely.",
    }
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "shortcuts",
        "privacy": _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [_warning(code, messages[code])],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def search_shortcuts_items(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    kind: str = "all",
    folder_name: str | None = None,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: ShortcutRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not _is_specific_query(query):
        return _broad_query_result()
    if folder_name:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "shortcuts",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "unsupported_folder_filter",
                    "Shortcuts folder filters are not exposed because exact handles must resolve from the global metadata flow.",
                )
            ],
        }

    normalized_kind = _normalize_kind(kind)
    if normalized_kind is None:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "shortcuts",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("invalid_kind", "Expected Shortcuts kind all, shortcut, or folder.")
            ],
        }

    loaded = _load_items(
        kind=normalized_kind,
        folder_name=folder_name,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _unavailable_result(code=loaded["warning_code"])

    lowered_query = query.casefold()
    bounded_limit = max(1, min(limit, MAX_LIMIT))
    results: list[dict[str, Any]] = []
    for item in loaded["items"]:
        if lowered_query not in item.title.casefold():
            continue
        results.append(_item_metadata(item, loaded["fingerprint"]))
        if len(results) >= bounded_limit:
            break

    warnings = []
    if loaded["truncated"]:
        warnings.append(
            _warning(
                "scan_truncated",
                "Shortcuts search stopped at the scan limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "shortcuts",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _privacy(),
        "query": {
            "scope": "shortcut_or_folder_name",
            "kind": normalized_kind,
            "folder_name_provided": bool(folder_name),
            "limit": bounded_limit,
            "max_scan_items": max_scan_items,
        },
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def get_shortcuts_item(
    handle: str,
    *,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: ShortcutRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, HANDLE_PREFIX):
        return _invalid_handle_result()

    loaded = _load_items(
        kind="all",
        folder_name=None,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _unavailable_result(detail=True, code=loaded["warning_code"])

    for item in loaded["items"]:
        if opaque_handle_matches(handle, HANDLE_PREFIX, loaded["fingerprint"], item.item_key):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "shortcuts",
                "store_fingerprint": loaded["fingerprint"],
                "privacy": _privacy(),
                "result": _item_metadata(item, loaded["fingerprint"]),
                "result_count": 1,
                "warnings": [],
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "shortcuts",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def _load_items(
    *,
    kind: str,
    folder_name: str | None,
    max_scan_items: int,
    runner: ShortcutRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    runner = runner or _default_runner
    outputs: list[tuple[str, str]] = []
    items: list[ShortcutItem] = []
    truncated = False
    commands = _commands_for_kind(kind, folder_name=folder_name)

    for item_kind, command in commands:
        result = runner(command, timeout_seconds)
        if result.returncode != 0:
            return {"status": "error", "warning_code": "shortcuts_cli_error"}
        outputs.append((item_kind, result.stdout))
        parsed = _parse_items(result.stdout, kind=item_kind, start_index=len(items))
        for item in parsed:
            if len(items) >= max_scan_items:
                truncated = True
                break
            items.append(item)
        if truncated:
            break

    fingerprint = _fingerprint(outputs)
    return {
        "status": "ok",
        "fingerprint": fingerprint,
        "items": items,
        "truncated": truncated,
    }


def _default_runner(command: list[str], timeout_seconds: float) -> ShortcutCommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return ShortcutCommandResult(returncode=127, stdout="", stderr="")
    return ShortcutCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _commands_for_kind(kind: str, *, folder_name: str | None) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    if kind in ("all", "shortcut"):
        command = ["shortcuts", "list", "--show-identifiers"]
        commands.append(("shortcut", command))
    if kind in ("all", "folder"):
        commands.append(("folder", ["shortcuts", "list", "--folders", "--show-identifiers"]))
    return commands


def _parse_items(output: str, *, kind: str, start_index: int) -> list[ShortcutItem]:
    items: list[ShortcutItem] = []
    for offset, raw_line in enumerate(output.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        match = UUID_RE.match(line)
        if match:
            title = _bounded_text(match.group("name").strip(), 200)
            identifier = match.group("identifier").upper()
            key_material = f"id:{identifier}"
            identifier_present = True
        else:
            title = _bounded_text(line, 200)
            key_material = f"name:{hashlib.sha256(title.encode('utf-8')).hexdigest()[:16]}"
            identifier_present = False
        if not title:
            continue
        item_key = f"{kind}:{key_material}:{start_index + offset}"
        items.append(
            ShortcutItem(
                item_key=item_key,
                title=title,
                kind=kind,
                identifier_present=identifier_present,
            )
        )
    return items


def _item_metadata(item: ShortcutItem, fingerprint: str) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(HANDLE_PREFIX, fingerprint, item.item_key),
        "title": item.title,
        "kind": item.kind,
        "identifier_present": item.identifier_present,
        "shortcut_body_returned": False,
    }


def _fingerprint(outputs: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for kind, output in outputs:
        digest.update(kind.encode("utf-8"))
        digest.update(b"\0")
        digest.update(output.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _normalize_kind(kind: str) -> str | None:
    normalized = kind.replace("-", "_").strip().casefold()
    if normalized in {"all", "shortcut", "folder"}:
        return normalized
    return None


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_SCAN_ITEMS = 5000
DEFAULT_TIMEOUT_SECONDS = 10.0
# Always invoke the OS Shortcuts CLI by its absolute path, never the bare name
# "shortcuts". This is a hard requirement for the arbitrary-execution run gate: a bare
# argv[0] resolves against the inherited PATH, so a PATH-planted "shortcuts" binary
# could be executed in place of the system tool. Every subprocess invocation (read and
# run) uses SHORTCUTS_BIN with shell=False / an argv list.
SHORTCUTS_BIN = "/usr/bin/shortcuts"
# Running a shortcut executes arbitrary user code, so the invocation is bound to a
# hard wall-clock timeout: a hung shortcut cannot block the caller indefinitely.
RUN_TIMEOUT_SECONDS = 60.0
MAX_RUN_INPUT_CHARS = 4000
MAX_RUN_OUTPUT_CHARS = 20000
HANDLE_PREFIX = "shortcuts:item"
UUID_RE = re.compile(r"^(?P<name>.+?)\s+\((?P<identifier>[A-Fa-f0-9-]{36})\)$")
# Only run operations are exposed; a run is resolved by exact identifier, never a
# raw caller-supplied name.
PLAN_OPERATIONS = {"run"}
APPROVAL_TOKEN_PREFIX = "shortcuts-apply:v1:"
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
    identifier: str | None


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
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: ShortcutRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not _is_specific_query(query):
        return _broad_query_result()

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
        resolved_folder_identifier=None,
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

    found = _find_item_by_handle(
        handle,
        kinds=("all", "shortcut", "folder"),
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if found["status"] == "error":
        return _unavailable_result(detail=True, code=found["warning_code"])
    if found["item"] is not None and found["loaded"] is not None:
        item = found["item"]
        loaded = found["loaded"]
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
        "store_fingerprint": found.get("store_fingerprint", ""),
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def list_shortcuts_folder_items(
    handle: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: ShortcutRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, HANDLE_PREFIX):
        payload = _invalid_handle_result()
        payload.update({"parent": None, "results": [], "result_count": 0})
        return payload

    found = _find_item_by_handle(
        handle,
        kinds=("all", "folder", "shortcut"),
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if found["status"] == "error":
        payload = _unavailable_result(code=found["warning_code"])
        payload.update({"parent": None})
        return payload
    if found["item"] is None or found["loaded"] is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "shortcuts",
            "store_fingerprint": found.get("store_fingerprint", ""),
            "privacy": _privacy(),
            "parent": None,
            "results": [],
            "result_count": 0,
            "warnings": [],
        }

    folder = found["item"]
    folder_loaded = found["loaded"]
    parent = _item_metadata(folder, folder_loaded["fingerprint"])
    if folder.kind != "folder":
        return {
            "schema_version": 1,
            "status": "error",
            "source": "shortcuts",
            "store_fingerprint": folder_loaded["fingerprint"],
            "privacy": _privacy(),
            "parent": parent,
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "unsupported_item_kind",
                    "Shortcuts folder item listing requires an exact folder handle.",
                )
            ],
        }
    if not folder.identifier:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "shortcuts",
            "store_fingerprint": folder_loaded["fingerprint"],
            "privacy": _privacy(),
            "parent": parent,
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "folder_identifier_unavailable",
                    "Shortcuts folder listing requires an identifier-backed folder handle.",
                )
            ],
        }

    folder_contents = _load_items(
        kind="shortcut",
        resolved_folder_identifier=folder.identifier,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if folder_contents["status"] != "ok":
        payload = _unavailable_result(code=folder_contents["warning_code"])
        payload.update({"parent": parent})
        return payload

    global_shortcuts = _load_items(
        kind="shortcut",
        resolved_folder_identifier=None,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if global_shortcuts["status"] != "ok":
        payload = _unavailable_result(code=global_shortcuts["warning_code"])
        payload.update({"parent": parent})
        return payload

    by_identifier = {
        item.identifier: item
        for item in global_shortcuts["items"]
        if item.identifier
    }
    bounded_limit = max(1, min(limit, MAX_LIMIT))
    results: list[dict[str, Any]] = []
    skipped_without_global_handle = False
    for item in folder_contents["items"]:
        if len(results) >= bounded_limit:
            break
        global_item = by_identifier.get(item.identifier or "")
        if global_item is None:
            skipped_without_global_handle = True
            continue
        results.append(_item_metadata(global_item, global_shortcuts["fingerprint"]))

    warnings = []
    if len(folder_contents["items"]) > bounded_limit:
        warnings.append(
            _warning(
                "result_truncated",
                "Shortcuts folder item listing was truncated to the requested limit.",
            )
        )
    if folder_contents["truncated"] or global_shortcuts["truncated"]:
        warnings.append(
            _warning(
                "scan_truncated",
                "Shortcuts folder item listing stopped at the scan limit.",
            )
        )
    if skipped_without_global_handle:
        warnings.append(
            _warning(
                "child_handle_unavailable",
                "One or more Shortcuts folder items lacked a stable global shortcut handle.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "shortcuts",
        "store_fingerprint": global_shortcuts["fingerprint"],
        "privacy": _privacy(),
        "query": {
            "scope": "folder_shortcuts",
            "limit": bounded_limit,
            "max_scan_items": max_scan_items,
        },
        "parent": parent,
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def _find_item_by_handle(
    handle: str,
    *,
    kinds: tuple[str, ...],
    max_scan_items: int,
    runner: ShortcutRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    first_warning_code = ""
    last_fingerprint = ""
    loaded_any = False
    for kind in kinds:
        loaded = _load_items(
            kind=kind,
            resolved_folder_identifier=None,
            max_scan_items=max_scan_items,
            runner=runner,
            timeout_seconds=timeout_seconds,
        )
        if loaded["status"] != "ok":
            first_warning_code = first_warning_code or loaded["warning_code"]
            continue
        loaded_any = True
        last_fingerprint = loaded["fingerprint"]
        for item in loaded["items"]:
            if opaque_handle_matches(handle, HANDLE_PREFIX, loaded["fingerprint"], item.item_key):
                return {"status": "ok", "item": item, "loaded": loaded}
    if not loaded_any:
        return {
            "status": "error",
            "warning_code": first_warning_code or "shortcuts_cli_unavailable",
            "item": None,
            "loaded": None,
            "store_fingerprint": "",
        }
    return {
        "status": "ok",
        "item": None,
        "loaded": None,
        "store_fingerprint": last_fingerprint,
    }


def _load_items(
    *,
    kind: str,
    resolved_folder_identifier: str | None,
    max_scan_items: int,
    runner: ShortcutRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    runner = runner or _default_runner
    outputs: list[tuple[str, str]] = []
    items: list[ShortcutItem] = []
    truncated = False
    commands = _commands_for_kind(kind, resolved_folder_identifier=resolved_folder_identifier)

    for item_kind, command in commands:
        try:
            result = runner(command, timeout_seconds)
        except (OSError, subprocess.SubprocessError):
            return {"status": "error", "warning_code": "shortcuts_cli_unavailable"}
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
    # `command` is always an argv list (never a shell string), so caller-supplied
    # input cannot inject shell metacharacters into the shortcuts invocation.
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        # The run gate relies on the hard timeout surfacing as a degraded apply
        # rather than a swallowed 127; reads catch it as a SubprocessError.
        raise
    except (OSError, subprocess.SubprocessError):
        return ShortcutCommandResult(returncode=127, stdout="", stderr="")
    return ShortcutCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _commands_for_kind(
    kind: str,
    *,
    resolved_folder_identifier: str | None,
) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    if kind in ("all", "shortcut"):
        command = [SHORTCUTS_BIN, "list"]
        if resolved_folder_identifier:
            command.extend(["--folder-name", resolved_folder_identifier])
        command.append("--show-identifiers")
        commands.append(("shortcut", command))
    if kind in ("all", "folder"):
        commands.append(("folder", [SHORTCUTS_BIN, "list", "--folders", "--show-identifiers"]))
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
            identifier = None
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
                identifier=identifier,
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


def plan_shortcuts_run(
    operation: str,
    *,
    handle: str = "",
    input_text: str = "",
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: ShortcutRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Plan an exact identifier-bound Shortcuts run without executing it.

    Running a shortcut can do anything the user can (run scripts, delete files,
    send messages), so this is gated like the most dangerous mutations: the plan
    resolves the shortcut by an exact metadata handle (never a raw name), binds the
    resolved identifier into the approval fingerprint, and states plainly that the
    effects are arbitrary and unverifiable by read-back.
    """

    normalized_operation, resolved, warnings = _prepare_run(
        operation,
        handle=handle,
        input_text=input_text,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if warnings:
        return _run_plan_error(warnings)
    assert resolved is not None
    if resolved.get("status") != "ok":
        return _run_resolve_result(resolved)

    return _build_run_plan(normalized_operation, resolved)


def apply_shortcuts_run(
    operation: str,
    *,
    handle: str = "",
    input_text: str = "",
    approval_token: str = "",
    confirm_apply: bool = False,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: ShortcutRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    run_timeout_seconds: float = RUN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Apply an approved exact identifier-bound Shortcuts run.

    The gate proves that the exact named shortcut was invoked with the exact bound
    input; it CANNOT prove what the shortcut did. Side effects are arbitrary and are
    not verifiable by read-back. Requires the matching approval token plus explicit
    confirm_apply=true. The shortcut is invoked by identifier through argv (never a
    shell string), so caller input cannot inject shell metacharacters, and a hard
    timeout guards against a hung shortcut.
    """

    plan = plan_shortcuts_run(
        operation,
        handle=handle,
        input_text=input_text,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if plan.get("status") != "ok":
        return _run_apply_error(_run_safe_warnings(plan), plan=plan)

    preview = plan["preview"]
    approval = preview["approval"]
    fingerprint = str(approval["approval_fingerprint"])
    expected_token = _approval_token(fingerprint)
    if not confirm_apply:
        return _run_apply_error(
            [_warning("missing_apply_confirmation", "Shortcuts run apply requires confirm_apply=true.")],
            plan=plan,
        )
    if approval_token.strip() != expected_token:
        return _run_apply_error(
            [_warning("invalid_approval_token", "Shortcuts run apply approval token did not match the plan.")],
            plan=plan,
        )

    identifier = str(preview["target"]["identifier"])
    normalized_input = str(preview["proposed"].get("input_text_full", ""))
    run_runner = runner or _default_runner
    input_file: tempfile._TemporaryFileWrapper | None = None
    try:
        command = [SHORTCUTS_BIN, "run", identifier]
        if normalized_input:
            # Input is written to a private temp file and passed by path via argv, so
            # nothing from the caller is ever interpolated into a shell string.
            input_file = tempfile.NamedTemporaryFile(  # noqa: SIM115
                mode="w", suffix=".shortcut-input.txt", delete=False, encoding="utf-8"
            )
            input_file.write(normalized_input)
            input_file.flush()
            input_file.close()
            command.extend(["--input-path", input_file.name])
        try:
            result = _invoke_run(
                run_runner,
                command,
                stdin_text=None,
                timeout_seconds=run_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _run_apply_error(
                [_warning("shortcuts_run_timeout", "Shortcuts run exceeded the hard execution timeout.")],
                plan=plan,
                status="degraded",
                mutation_applied=False,
            )
        except (OSError, subprocess.SubprocessError):
            return _run_apply_error(
                [_warning("shortcuts_run_error", "Shortcuts run could not be invoked safely.")],
                plan=plan,
            )
    finally:
        if input_file is not None:
            try:
                os.unlink(input_file.name)
            except OSError:
                pass

    if result.returncode != 0:
        return _run_apply_error(
            [_warning("shortcuts_run_nonzero_exit", "Shortcuts run reported a non-zero exit.")],
            plan=plan,
            status="partial",
            mutation_applied=True,
            output_preview=_bounded_text(result.stdout, MAX_RUN_OUTPUT_CHARS),
        )

    output_preview = _bounded_text(result.stdout, MAX_RUN_OUTPUT_CHARS)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "shortcuts",
        "privacy": _run_privacy(),
        "mode": "apply",
        "mutation_applied": True,
        "read_back": {
            # The gate proves invocation of the named shortcut, not its effects.
            "invocation_confirmed": True,
            "side_effects_verified": False,
            "shortcut_identifier": identifier,
            "shortcut_title": preview["target"]["title"],
            "exit_code": 0,
            "output_returned": True,
            "output_chars": len(output_preview),
            "output_preview": output_preview,
            "output_truncated": len(result.stdout) > MAX_RUN_OUTPUT_CHARS,
        },
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "result_count": 1,
        "warnings": [
            _warning(
                "side_effects_unverifiable",
                "Shortcuts run invocation is confirmed; the shortcut's side effects are arbitrary and not verifiable by read-back.",
            )
        ],
    }


def _prepare_run(
    operation: str,
    *,
    handle: str,
    input_text: str,
    max_scan_items: int,
    runner: ShortcutRunner | None,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any] | None, list[dict[str, str]]]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected Shortcuts operation run."))
    if not is_opaque_handle(handle, HANDLE_PREFIX):
        warnings.append(
            _warning("invalid_handle", "Shortcuts run planning requires a shortcuts:item:v1 handle.")
        )
    normalized_input, input_warning = _normalize_run_input(input_text)
    if input_warning is not None:
        warnings.append(input_warning)
    if warnings:
        return normalized_operation, None, warnings

    resolved = _resolve_run_target(
        handle,
        input_text=normalized_input,
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    return normalized_operation, resolved, []


def _resolve_run_target(
    handle: str,
    *,
    input_text: str,
    max_scan_items: int,
    runner: ShortcutRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    found = _find_item_by_handle(
        handle,
        # Include folder resolution so a folder handle produces the explicit
        # unsupported-kind refusal rather than a generic not-found.
        kinds=("all", "shortcut", "folder"),
        max_scan_items=max_scan_items,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if found["status"] == "error":
        return {"status": "error", "warning_code": found["warning_code"]}
    item = found["item"]
    loaded = found["loaded"]
    if item is None or loaded is None:
        return {"status": "not_found", "store_fingerprint": found.get("store_fingerprint", "")}
    if item.kind != "shortcut":
        return {"status": "unsupported_kind", "store_fingerprint": loaded["fingerprint"]}
    if not item.identifier:
        return {"status": "identifier_unavailable", "store_fingerprint": loaded["fingerprint"]}
    return {
        "status": "ok",
        "item": item,
        "fingerprint": loaded["fingerprint"],
        "input_text": input_text,
    }


def _build_run_plan(operation: str, resolved: dict[str, Any]) -> dict[str, Any]:
    item = resolved["item"]
    fingerprint = resolved["fingerprint"]
    input_text = resolved["input_text"]
    input_preview = _bounded_text(input_text, 200)
    target = {
        "handle": make_opaque_handle(HANDLE_PREFIX, fingerprint, item.item_key),
        "title": item.title,
        # The identifier is the anti-spoofing binding: apply resolves and runs this
        # exact identifier, not any caller-supplied name.
        "identifier": item.identifier,
        "kind": item.kind,
    }
    proposed = {
        "kind": "shortcuts_run",
        "shortcut_title": item.title,
        "shortcut_identifier": item.identifier,
        "input_present": bool(input_text),
        "input_chars": len(input_text),
        "input_preview": input_preview,
        "input_text_full": input_text,
        "effects_arbitrary": True,
        "effects_verifiable_by_read_back": False,
        "invocation_via_argv": True,
    }
    fingerprint_payload = {
        "operation": operation,
        "target": target,
        "proposed": {key: value for key, value in proposed.items() if key != "input_text_full"},
        "input_sha256": hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {**fingerprint_payload, "idempotency_key": idempotency_key}
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "shortcuts",
        "privacy": _run_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "warning": (
                "Applying will run the exact shortcut named above. A shortcut can do "
                "anything you can (run scripts, delete files, send messages); its "
                "effects are arbitrary and cannot be proven by read-back."
            ),
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": False,
        },
        "result_count": 1,
        "warnings": [
            _warning(
                "arbitrary_execution",
                "Running a shortcut executes arbitrary user-defined actions; effects are unverifiable.",
            )
        ],
    }


def _invoke_run(
    runner: ShortcutRunner,
    command: list[str],
    *,
    stdin_text: str | None,
    timeout_seconds: float,
) -> ShortcutCommandResult:
    # stdin_text is retained for interface symmetry; the run path passes input by
    # temp-file path via argv, so it is always None here.
    return runner(command, timeout_seconds)


def _normalize_run_input(input_text: str) -> tuple[str, dict[str, str] | None]:
    text = input_text or ""
    if not text:
        return "", None
    if len(text) > MAX_RUN_INPUT_CHARS:
        return "", _warning("input_too_large", f"Shortcuts run input exceeds {MAX_RUN_INPUT_CHARS} characters.")
    if "\x00" in text:
        return "", _warning("invalid_input", "Shortcuts run input may not contain NUL bytes.")
    return text, None


def _run_resolve_result(resolved: dict[str, Any]) -> dict[str, Any]:
    status = resolved.get("status")
    if status == "error":
        return _unavailable_result(detail=True, code=resolved["warning_code"])
    if status == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "shortcuts",
            "store_fingerprint": resolved.get("store_fingerprint", ""),
            "privacy": _run_privacy(),
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": False,
            "preview": None,
            "warnings": [],
        }
    code = {
        "unsupported_kind": ("unsupported_item_kind", "Shortcuts run requires an exact shortcut handle, not a folder."),
        "identifier_unavailable": (
            "shortcut_identifier_unavailable",
            "Shortcuts run requires an identifier-backed shortcut handle.",
        ),
    }.get(str(status), ("shortcuts_run_unresolved", "Shortcuts run target could not be resolved safely."))
    return _run_plan_error([_warning(*code)])


def _run_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "preview",
        "shortcut_body_returned": False,
    }


def _run_plan_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "shortcuts",
        "privacy": _run_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": False,
        "preview": None,
        "warnings": warnings,
    }


def _run_apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any],
    status: str = "error",
    mutation_applied: bool = False,
    output_preview: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "shortcuts",
        "privacy": _run_privacy(),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "read_back": None,
        "plan": plan,
        "result_count": 0,
        "warnings": warnings,
    }
    if output_preview is not None:
        payload["read_back"] = {
            "invocation_confirmed": True,
            "side_effects_verified": False,
            "output_preview": output_preview,
        }
    return payload


def _run_safe_warnings(plan: dict[str, Any]) -> list[dict[str, str]]:
    warnings = plan.get("warnings")
    if isinstance(warnings, list) and warnings:
        return [w for w in warnings if isinstance(w, dict)]
    return [_warning("plan_unavailable", "Shortcuts run plan was unavailable.")]


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"shortcuts-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _normalize_kind(kind: str) -> str | None:
    normalized = kind.replace("-", "_").strip().casefold()
    if normalized in {"all", "shortcut", "folder"}:
        return normalized
    return None


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."

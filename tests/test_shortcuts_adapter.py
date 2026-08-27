from __future__ import annotations

import inspect
import subprocess

from local_apple_data.adapters.shortcuts import (
    APPROVAL_TOKEN_PREFIX,
    SHORTCUTS_BIN,
    ShortcutCommandResult,
    apply_shortcuts_run,
    get_shortcuts_item,
    list_shortcuts_folder_items,
    plan_shortcuts_run,
    search_shortcuts_items,
)


_RUN_IDENTIFIER = "11111111-1111-1111-1111-111111111111"


def _run_runner(command: list[str], _timeout: float) -> ShortcutCommandResult:
    if command == [SHORTCUTS_BIN, "list", "--show-identifiers"]:
        return ShortcutCommandResult(0, f"Synthetic Packet ({_RUN_IDENTIFIER})\n")
    if command == [SHORTCUTS_BIN, "list", "--folders", "--show-identifiers"]:
        return ShortcutCommandResult(0, "Synthetic Folder (33333333-3333-3333-3333-333333333333)\n")
    if command[:3] == [SHORTCUTS_BIN, "run", _RUN_IDENTIFIER]:
        return ShortcutCommandResult(0, "synthetic-noop-output\n")
    return ShortcutCommandResult(1, "", "unexpected command")


def _shortcut_run_handle() -> str:
    search = search_shortcuts_items("Synthetic Packet", runner=_run_runner)
    return search["results"][0]["handle"]


def _folder_run_handle() -> str:
    folder = search_shortcuts_items("Synthetic Folder", kind="folder", runner=_run_runner)
    return folder["results"][0]["handle"]


def test_plan_shortcuts_run_binds_identifier_and_flags_unverifiable() -> None:
    handle = _shortcut_run_handle()
    plan = plan_shortcuts_run("run", handle=handle, input_text="hello", runner=_run_runner)

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["identifier"] == _RUN_IDENTIFIER
    assert plan["preview"]["proposed"]["effects_verifiable_by_read_back"] is False
    assert plan["preview"]["proposed"]["invocation_via_argv"] is True
    assert plan["preview"]["read_back_required_after_apply"] is False


def test_apply_shortcuts_run_proves_invocation_only() -> None:
    handle = _shortcut_run_handle()
    plan = plan_shortcuts_run("run", handle=handle, runner=_run_runner)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    result = apply_shortcuts_run(
        "run", handle=handle, approval_token=token, confirm_apply=True, runner=_run_runner
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["invocation_confirmed"] is True
    assert result["read_back"]["side_effects_verified"] is False
    assert result["read_back"]["output_preview"].strip() == "synthetic-noop-output"
    assert any(w["code"] == "side_effects_unverifiable" for w in result["warnings"])


def test_apply_shortcuts_run_requires_confirmation() -> None:
    handle = _shortcut_run_handle()
    plan = plan_shortcuts_run("run", handle=handle, runner=_run_runner)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    result = apply_shortcuts_run(
        "run", handle=handle, approval_token=token, confirm_apply=False, runner=_run_runner
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"
    assert result["mutation_applied"] is False


def test_apply_shortcuts_run_rejects_mismatched_token() -> None:
    handle = _shortcut_run_handle()

    result = apply_shortcuts_run(
        "run",
        handle=handle,
        approval_token="shortcuts-apply:v1:deadbeef",
        confirm_apply=True,
        runner=_run_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert result["mutation_applied"] is False


def test_plan_shortcuts_run_refuses_spoofed_handle() -> None:
    result = plan_shortcuts_run("run", handle="notes:note:v2:forged", runner=_run_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_shortcuts_run_refuses_folder_handle() -> None:
    result = plan_shortcuts_run("run", handle=_folder_run_handle(), runner=_run_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_item_kind"


def test_shortcuts_run_input_is_carried_as_inert_data_not_shell() -> None:
    handle = _shortcut_run_handle()
    injection = "; rm -rf ~ && echo pwned"
    captured: list[list[str]] = []

    def capturing_runner(command: list[str], _timeout: float) -> ShortcutCommandResult:
        if command[:3] == [SHORTCUTS_BIN, "run", _RUN_IDENTIFIER]:
            captured.append(command)
            return ShortcutCommandResult(0, "ok\n")
        return _run_runner(command, _timeout)

    plan = plan_shortcuts_run("run", handle=handle, input_text=injection, runner=capturing_runner)
    assert plan["preview"]["proposed"]["input_chars"] == len(injection)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]
    result = apply_shortcuts_run(
        "run", handle=handle, input_text=injection, approval_token=token, confirm_apply=True, runner=capturing_runner
    )
    assert result["status"] == "ok"
    # The run command is an argv list; the injection string never appears as a
    # command token (it is written to a temp file passed by --input-path).
    run_command = captured[0]
    assert run_command[0:3] == [SHORTCUTS_BIN, "run", _RUN_IDENTIFIER]
    assert injection not in run_command


def test_apply_shortcuts_run_hard_timeout_is_degraded() -> None:
    handle = _shortcut_run_handle()
    plan = plan_shortcuts_run("run", handle=handle, runner=_run_runner)
    token = APPROVAL_TOKEN_PREFIX + plan["preview"]["approval"]["approval_fingerprint"]

    def timeout_runner(command: list[str], _timeout: float) -> ShortcutCommandResult:
        if command[:3] == [SHORTCUTS_BIN, "run", _RUN_IDENTIFIER]:
            raise subprocess.TimeoutExpired("/usr/bin/shortcuts", 60)
        return _run_runner(command, _timeout)

    result = apply_shortcuts_run(
        "run", handle=handle, approval_token=token, confirm_apply=True, runner=timeout_runner
    )

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "shortcuts_run_timeout"
    assert result["mutation_applied"] is False


def _runner(command: list[str], _timeout: float) -> ShortcutCommandResult:
    if command == [SHORTCUTS_BIN, "list", "--show-identifiers"]:
        return ShortcutCommandResult(
            0,
            "Synthetic Packet (11111111-1111-1111-1111-111111111111)\n"
            "Quarterly Review (22222222-2222-2222-2222-222222222222)\n",
        )
    if command == [SHORTCUTS_BIN, "list", "--folders", "--show-identifiers"]:
        return ShortcutCommandResult(
            0,
            "Synthetic Folder (33333333-3333-3333-3333-333333333333)\n",
        )
    if command == [
        SHORTCUTS_BIN,
        "list",
        "--folder-name",
        "33333333-3333-3333-3333-333333333333",
        "--show-identifiers",
    ]:
        return ShortcutCommandResult(
            0,
            "Synthetic Packet (11111111-1111-1111-1111-111111111111)\n",
        )
    return ShortcutCommandResult(1, "", "unexpected command")


def test_search_shortcuts_items_returns_metadata_without_identifiers() -> None:
    result = search_shortcuts_items("Packet", runner=_runner)

    assert result["status"] == "ok"
    assert result["source"] == "shortcuts"
    assert result["result_count"] == 1
    item = result["results"][0]
    assert item["handle"].startswith("shortcuts:item:v1:")
    assert item["title"] == "Synthetic Packet"
    assert item["kind"] == "shortcut"
    assert item["identifier_present"] is True
    assert item["shortcut_body_returned"] is False
    assert "11111111-1111-1111-1111-111111111111" not in str(result)


def test_search_shortcuts_items_filters_folders() -> None:
    result = search_shortcuts_items("Synthetic", kind="folder", runner=_runner)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["kind"] == "folder"


def test_get_shortcuts_item_returns_exact_metadata_by_handle() -> None:
    handle = search_shortcuts_items("Packet", runner=_runner)["results"][0]["handle"]

    result = get_shortcuts_item(handle, runner=_runner)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Synthetic Packet"
    assert result["result"]["shortcut_body_returned"] is False
    assert "11111111-1111-1111-1111-111111111111" not in str(result)


def test_get_shortcuts_item_accepts_kind_specific_search_handles() -> None:
    shortcut_handle = search_shortcuts_items("Packet", kind="shortcut", runner=_runner)["results"][0][
        "handle"
    ]
    folder_handle = search_shortcuts_items("Synthetic", kind="folder", runner=_runner)["results"][0][
        "handle"
    ]

    shortcut = get_shortcuts_item(shortcut_handle, runner=_runner)
    folder = get_shortcuts_item(folder_handle, runner=_runner)

    assert shortcut["status"] == "ok"
    assert shortcut["result"]["title"] == "Synthetic Packet"
    assert folder["status"] == "ok"
    assert folder["result"]["title"] == "Synthetic Folder"
    assert "11111111-1111-1111-1111-111111111111" not in str(shortcut)
    assert "33333333-3333-3333-3333-333333333333" not in str(folder)


def test_list_shortcuts_folder_items_returns_exact_child_metadata() -> None:
    folder_handle = search_shortcuts_items("Synthetic", kind="folder", runner=_runner)["results"][0][
        "handle"
    ]

    result = list_shortcuts_folder_items(folder_handle, runner=_runner)

    assert result["status"] == "ok"
    assert result["parent"]["title"] == "Synthetic Folder"
    assert result["parent"]["kind"] == "folder"
    assert result["result_count"] == 1
    child = result["results"][0]
    assert child["handle"].startswith("shortcuts:item:v1:")
    assert child["title"] == "Synthetic Packet"
    assert child["kind"] == "shortcut"
    assert child["shortcut_body_returned"] is False
    detail = get_shortcuts_item(child["handle"], runner=_runner)
    assert detail["status"] == "ok"
    assert detail["result"]["title"] == "Synthetic Packet"
    assert "11111111-1111-1111-1111-111111111111" not in str(result)
    assert "33333333-3333-3333-3333-333333333333" not in str(result)


def test_list_shortcuts_folder_items_rejects_shortcut_handle() -> None:
    handle = search_shortcuts_items("Packet", runner=_runner)["results"][0]["handle"]
    shortcut_only_handle = search_shortcuts_items("Packet", kind="shortcut", runner=_runner)[
        "results"
    ][0]["handle"]

    result = list_shortcuts_folder_items(handle, runner=_runner)
    shortcut_only_result = list_shortcuts_folder_items(shortcut_only_handle, runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_item_kind"
    assert shortcut_only_result["status"] == "error"
    assert shortcut_only_result["warnings"][0]["code"] == "unsupported_item_kind"


def test_get_shortcuts_item_rejects_bad_handle() -> None:
    result = get_shortcuts_item("shortcuts:item:1", runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_shortcuts_items_rejects_empty_broad_and_exposes_no_folder_filter() -> None:
    empty = search_shortcuts_items(" ", runner=_runner)
    broad = search_shortcuts_items("Shortcuts", runner=_runner)

    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["warnings"][0]["code"] == "broad_query"
    assert "folder_name" not in inspect.signature(search_shortcuts_items).parameters


def test_search_shortcuts_items_reports_cli_errors() -> None:
    def failing_runner(_command: list[str], _timeout: float) -> ShortcutCommandResult:
        return ShortcutCommandResult(1, "", "synthetic failure")

    result = search_shortcuts_items("Packet", runner=failing_runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "shortcuts_cli_error"


def test_search_shortcuts_items_runner_os_errors_are_safe() -> None:
    def failing_runner(_command: list[str], _timeout: float) -> ShortcutCommandResult:
        raise OSError("permission denied for /private/local/shortcuts")

    result = search_shortcuts_items("Packet", runner=failing_runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "shortcuts_cli_unavailable"
    assert "permission denied" not in str(result)
    assert "/private/local/shortcuts" not in str(result)


def test_get_shortcuts_item_runner_timeouts_are_safe() -> None:
    handle = search_shortcuts_items("Packet", runner=_runner)["results"][0]["handle"]

    def failing_runner(_command: list[str], _timeout: float) -> ShortcutCommandResult:
        raise subprocess.TimeoutExpired("/private/local/shortcuts", 10)

    result = get_shortcuts_item(handle, runner=failing_runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "shortcuts_cli_unavailable"
    assert "/private/local/shortcuts" not in str(result)

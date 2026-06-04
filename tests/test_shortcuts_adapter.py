from __future__ import annotations

from local_apple_data.adapters.shortcuts import (
    ShortcutCommandResult,
    get_shortcuts_item,
    search_shortcuts_items,
)


def _runner(command: list[str], _timeout: float) -> ShortcutCommandResult:
    if command == ["shortcuts", "list", "--show-identifiers"]:
        return ShortcutCommandResult(
            0,
            "Synthetic Packet (11111111-1111-1111-1111-111111111111)\n"
            "Quarterly Review (22222222-2222-2222-2222-222222222222)\n",
        )
    if command == ["shortcuts", "list", "--folders", "--show-identifiers"]:
        return ShortcutCommandResult(
            0,
            "Synthetic Folder (33333333-3333-3333-3333-333333333333)\n",
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


def test_get_shortcuts_item_rejects_bad_handle() -> None:
    result = get_shortcuts_item("shortcuts:item:1", runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_shortcuts_items_rejects_empty_broad_and_folder_scoped_queries() -> None:
    empty = search_shortcuts_items(" ", runner=_runner)
    broad = search_shortcuts_items("Shortcuts", runner=_runner)
    folder = search_shortcuts_items("Packet", folder_name="Synthetic Folder", runner=_runner)

    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["warnings"][0]["code"] == "broad_query"
    assert folder["warnings"][0]["code"] == "unsupported_folder_filter"


def test_search_shortcuts_items_reports_cli_errors() -> None:
    def failing_runner(_command: list[str], _timeout: float) -> ShortcutCommandResult:
        return ShortcutCommandResult(1, "", "synthetic failure")

    result = search_shortcuts_items("Packet", runner=failing_runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "shortcuts_cli_error"

from __future__ import annotations

import builtins
import errno
import hashlib
import json
import os
from pathlib import Path

import pytest

import local_apple_data.adapters.icloud_drive as icloud_drive_adapter
from local_apple_data.adapters.icloud_drive import (
    apply_icloud_drive_change,
    export_icloud_drive_file,
    get_icloud_drive_content,
    get_icloud_drive_metadata,
    get_icloud_drive_root_metadata,
    list_icloud_drive_folder,
    list_icloud_drive_folder_tree,
    plan_icloud_drive_change,
    search_icloud_drive_metadata,
)
from local_apple_data.handles import make_opaque_handle


def _make_icloud_root(root: Path) -> None:
    (root / "Packets").mkdir(parents=True)
    (root / "Packets" / "review-packet.md").write_text(
        "# Synthetic Packet\nLine two\n",
        encoding="utf-8",
    )
    (root / "Packets" / "image.bin").write_bytes(b"\x00\x01")
    (root / ".hidden.md").write_text("hidden", encoding="utf-8")


def _make_plan_for_review_replace(root: Path, replacement: str = "# Replacement\n") -> tuple[str, str, dict]:
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
    )
    return handle, current_sha, plan


def _swap_root_to_external_on_symlink_check(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    external_root: Path,
    target: Path,
) -> dict[str, bool]:
    original = icloud_drive_adapter._has_symlink_component
    swapped = {"value": False}

    def swap(path: Path, check_root: Path) -> bool:
        if not swapped["value"] and path == target and check_root == root:
            swapped["value"] = True
            original_root = root.with_name(f"{root.name}-original")
            root.rename(original_root)
            root.symlink_to(external_root, target_is_directory=True)
            return False
        return original(path, check_root)

    monkeypatch.setattr(icloud_drive_adapter, "_has_symlink_component", swap)
    return swapped


def _replace_root_with_external_directory_on_symlink_check(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    external_root: Path,
    target: Path,
) -> dict[str, bool]:
    original = icloud_drive_adapter._has_symlink_component
    swapped = {"value": False}

    def swap(path: Path, check_root: Path) -> bool:
        if not swapped["value"] and path == target and check_root == root:
            swapped["value"] = True
            original_root = root.with_name(f"{root.name}-original")
            root.rename(original_root)
            external_root.rename(root)
            return False
        return original(path, check_root)

    monkeypatch.setattr(icloud_drive_adapter, "_has_symlink_component", swap)
    return swapped


def _replace_target_on_symlink_check(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    target: Path,
    replacement: bytes | str,
) -> dict[str, bool]:
    original = icloud_drive_adapter._has_symlink_component
    swapped = {"value": False}

    def swap(path: Path, check_root: Path) -> bool:
        if not swapped["value"] and path == target and check_root == root:
            swapped["value"] = True
            if isinstance(replacement, bytes):
                target.write_bytes(replacement)
            else:
                target.write_text(replacement, encoding="utf-8")
            return False
        return original(path, check_root)

    monkeypatch.setattr(icloud_drive_adapter, "_has_symlink_component", swap)
    return swapped


def test_search_icloud_drive_metadata_by_filename(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = search_icloud_drive_metadata("review", root=root, limit=10)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"]["scope"] == "filename"
    assert result["result_count"] == 1
    item = result["results"][0]
    assert item["handle"].startswith("icloud:file:v1:")
    assert item["name"] == "review-packet.md"
    assert item["extension"] == ".md"
    assert item["kind"] == "file"
    assert "Packets" not in item


def test_search_icloud_drive_includes_folders_as_metadata(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = search_icloud_drive_metadata("Packets", root=root)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["kind"] == "directory"
    assert result["results"][0]["size"] is None
    assert len(result["results"][0]["metadata_sha256"]) == 64
    assert "content_sha256" not in result["results"][0]


def test_search_icloud_drive_rejects_empty_and_broad_queries(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    empty = search_icloud_drive_metadata(" ", root=root)
    broad = search_icloud_drive_metadata("%", root=root)

    assert empty["status"] == "error"
    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["status"] == "error"
    assert broad["warnings"][0]["code"] == "broad_query"


def test_get_icloud_drive_metadata_by_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = get_icloud_drive_metadata(handle, root=root)

    assert result["status"] == "ok"
    assert result["result"]["name"] == "review-packet.md"
    assert "path" not in result["result"]


def test_get_icloud_drive_root_metadata_returns_resolvable_directory_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = get_icloud_drive_root_metadata(root=root)

    assert result["status"] == "ok"
    root_item = result["result"]
    assert root_item["handle"].startswith("icloud:file:v1:")
    assert root_item["kind"] == "directory"
    assert root_item["depth"] == 0
    assert root_item["is_root"] is True
    assert "path" not in root_item
    assert str(root) not in json.dumps(result)

    listing = list_icloud_drive_folder(root_item["handle"], root=root, limit=10)

    assert listing["status"] == "ok"
    assert listing["parent"]["is_root"] is True
    assert {item["name"] for item in listing["results"]} == {"Packets"}


def test_icloud_drive_root_handle_is_parent_only_for_mutations(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    root_item = get_icloud_drive_root_metadata(root=root)["result"]
    root_handle = root_item["handle"]
    root_sha = root_item["metadata_sha256"]

    create_plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=root_handle,
        filename="Top Level Synthetic",
        root=root,
    )

    assert create_plan["status"] == "ok"
    assert create_plan["preview"]["target"]["parent_handle"] == root_handle

    root_source_plans = [
        plan_icloud_drive_change(
            "rename_folder",
            handle=root_handle,
            filename="Renamed Root",
            expected_current_sha256=root_sha,
            root=root,
        ),
        plan_icloud_drive_change(
            "trash_folder",
            handle=root_handle,
            expected_current_sha256=root_sha,
            root=root,
        ),
        plan_icloud_drive_change(
            "delete_folder",
            handle=root_handle,
            expected_current_sha256=root_sha,
            root=root,
        ),
        plan_icloud_drive_change(
            "move_folder",
            handle=root_handle,
            parent_handle=root_handle,
            expected_current_sha256=root_sha,
            root=root,
        ),
        plan_icloud_drive_change(
            "copy_folder",
            handle=root_handle,
            parent_handle=root_handle,
            filename="Root Copy",
            expected_current_sha256=root_sha,
            root=root,
        ),
    ]

    for plan in root_source_plans:
        assert plan["status"] == "error"
        assert plan["warnings"][0]["code"] == "unsupported_file_type"

    apply_result = apply_icloud_drive_change(
        "trash_folder",
        handle=root_handle,
        expected_current_sha256=root_sha,
        approval_token="icloud-drive-apply:v1:invalid",
        confirm_apply=True,
        root=root,
    )

    assert apply_result["status"] == "error"
    assert apply_result["warnings"][0]["code"] == "unsupported_file_type"


def test_list_icloud_drive_folder_direct_children_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    (packets / "Nested").mkdir()
    (packets / "Nested" / "inside.txt").write_text("nested", encoding="utf-8")
    (packets / "Hidden.app").mkdir()
    (packets / ".hidden-child.txt").write_text("hidden", encoding="utf-8")
    (packets / "linked.txt").symlink_to(root / "synthetic-target.txt")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder(handle, root=root, limit=10)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"] == {"scope": "folder_children", "limit": 10, "recursive": False}
    assert result["parent"]["name"] == "Packets"
    assert result["parent"]["kind"] == "directory"
    names = {item["name"] for item in result["results"]}
    assert names == {"Nested", "image.bin", "review-packet.md"}
    assert "inside.txt" not in names
    raw = json.dumps(result)
    assert "content_text" not in raw
    assert str(root) not in raw


def test_list_icloud_drive_folder_truncates(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder(handle, root=root, limit=1)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["warnings"][0]["code"] == "result_truncated"


def test_list_icloud_drive_folder_rejects_file_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder(handle, root=root)

    assert result["status"] == "content_unavailable"
    assert result["parent"]["kind"] == "file"
    assert result["warnings"][0]["code"] == "unsupported_file_type"


def test_list_icloud_drive_folder_refuses_selected_folder_symlink_race(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    external = tmp_path / "External"
    external.mkdir()
    (external / "leak.txt").write_text("outside root", encoding="utf-8")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]
    original_scandir = os.scandir
    raced = False

    def racing_scandir(path: int | str | bytes | os.PathLike[str] | os.PathLike[bytes]):
        nonlocal raced
        entries = original_scandir(path)
        if isinstance(path, int) and not raced:
            os.rename(root / "Packets", root / "Packets-original")
            (root / "Packets").symlink_to(external, target_is_directory=True)
            raced = True
        return entries

    monkeypatch.setattr(os, "scandir", racing_scandir)

    result = list_icloud_drive_folder(handle, root=root, limit=10)

    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert "leak.txt" not in json.dumps(result)


def test_list_icloud_drive_folder_streams_with_child_scan_cap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    for index in range(5):
        (packets / f"scan-{index}.txt").write_text("packet", encoding="utf-8")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    def forbidden_listdir(_path):
        raise AssertionError("folder listing must stream through os.scandir")

    monkeypatch.setattr(os, "listdir", forbidden_listdir)

    result = list_icloud_drive_folder(
        handle,
        root=root,
        limit=10,
        max_child_scan_entries=2,
    )

    assert result["status"] == "ok"
    assert result["result_count"] <= 2
    assert result["warnings"][0]["code"] == "scan_truncated"
    assert "content_text" not in json.dumps(result)
    assert str(root) not in json.dumps(result)


def test_list_icloud_drive_folder_tree_returns_bounded_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    (packets / "Nested").mkdir()
    (packets / "Nested" / "inside.txt").write_text("nested", encoding="utf-8")
    (packets / "Nested" / "Deep").mkdir()
    (packets / "Nested" / "Deep" / "deep.txt").write_text("deep", encoding="utf-8")
    (packets / "Hidden.app").mkdir()
    (packets / ".hidden-child.txt").write_text("hidden", encoding="utf-8")
    (packets / "linked.txt").symlink_to(root / "synthetic-target.txt")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder_tree(handle, root=root, depth=2, limit=10)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"]["scope"] == "folder_tree"
    assert result["query"]["limit"] == 10
    assert result["query"]["max_depth"] == 2
    assert result["query"]["recursive"] is True
    assert result["parent"]["name"] == "Packets"
    names = {item["name"] for item in result["results"]}
    assert names == {"Deep", "Nested", "image.bin", "inside.txt", "review-packet.md"}
    nested = next(item for item in result["results"] if item["name"] == "inside.txt")
    assert nested["tree_depth"] == 2
    assert nested["parent_handle"].startswith("icloud:file:v1:")
    raw = json.dumps(result)
    assert "deep.txt" not in raw
    assert "Hidden" not in raw
    assert "linked.txt" not in raw
    assert "content_text" not in raw
    assert str(root) not in raw


def test_list_icloud_drive_folder_tree_rejects_file_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder_tree(handle, root=root)

    assert result["status"] == "content_unavailable"
    assert result["parent"]["kind"] == "file"
    assert result["warnings"][0]["code"] == "unsupported_file_type"


def test_list_icloud_drive_folder_tree_truncates_by_result_limit(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    (packets / "Nested").mkdir()
    (packets / "Nested" / "inside.txt").write_text("nested", encoding="utf-8")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder_tree(handle, root=root, depth=2, limit=1)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["warnings"][0]["code"] == "result_truncated"


def test_list_icloud_drive_folder_tree_streams_with_scan_caps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    for index in range(5):
        (packets / f"Folder-{index}").mkdir()
        (packets / f"Folder-{index}" / "inside.txt").write_text("packet", encoding="utf-8")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    def forbidden_listdir(_path):
        raise AssertionError("folder tree listing must stream through os.scandir")

    monkeypatch.setattr(os, "listdir", forbidden_listdir)

    result = list_icloud_drive_folder_tree(
        handle,
        root=root,
        depth=2,
        limit=20,
        max_child_scan_entries=2,
    )

    assert result["status"] == "ok"
    assert any(warning["code"] == "scan_truncated" for warning in result["warnings"])
    assert "content_text" not in json.dumps(result)
    assert str(root) not in json.dumps(result)


def test_list_icloud_drive_folder_tree_respects_total_scan_cap(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    for index in range(5):
        (packets / f"Folder-{index}").mkdir()
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    result = list_icloud_drive_folder_tree(
        handle,
        root=root,
        depth=2,
        limit=20,
        max_tree_scan_entries=1,
    )

    assert result["status"] == "ok"
    assert result["query"]["tree_scan_limit"] == 1
    assert any(warning["code"] == "scan_truncated" for warning in result["warnings"])


def test_list_icloud_drive_folder_tree_refuses_child_metadata_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    packets = root / "Packets"
    nested = packets / "Nested"
    nested.mkdir()
    (nested / "inside.txt").write_text("nested", encoding="utf-8")
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]
    original = icloud_drive_adapter._list_resolved_icloud_drive_folder
    original_open = icloud_drive_adapter._open_resolved_directory_no_follow
    calls = {"count": 0}
    replaced = {"value": False}

    def refuse_replaced_child_open(path: Path, *args: object, **kwargs: object) -> int:
        if path == nested and replaced["value"]:
            raise AssertionError("changed child must not be opened for recursive listing")
        return original_open(path, *args, **kwargs)

    def racing_list(path: Path, **kwargs: object) -> dict:
        result = original(path, **kwargs)
        if calls["count"] == 0:
            os.rename(nested, packets / "Nested-original")
            nested.mkdir()
            (nested / "replacement-secret.txt").write_text("replacement", encoding="utf-8")
            replaced["value"] = True
        calls["count"] += 1
        return result

    monkeypatch.setattr(icloud_drive_adapter, "_list_resolved_icloud_drive_folder", racing_list)
    monkeypatch.setattr(
        icloud_drive_adapter,
        "_open_resolved_directory_no_follow",
        refuse_replaced_child_open,
    )

    result = list_icloud_drive_folder_tree(handle, root=root, depth=2, limit=10)

    assert result["status"] == "ok"
    names = {item["name"] for item in result["results"]}
    assert "Nested" in names
    assert "inside.txt" not in names
    assert "replacement-secret.txt" not in names
    assert any(warning["code"] == "child_metadata_changed" for warning in result["warnings"])


def test_get_icloud_drive_content_by_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = get_icloud_drive_content(handle, root=root, max_chars=4000)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["content_text"] == "# Synthetic Packet\nLine two\n"
    assert result["result"]["content_chars"] == len(result["result"]["content_text"])
    assert result["result"]["content_sha256"] == _content_sha("# Synthetic Packet\nLine two\n")
    assert result["result"]["truncated"] is False


def test_get_icloud_drive_content_truncates(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = get_icloud_drive_content(handle, root=root, max_chars=5)

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "# Syn"
    assert result["result"]["truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"


def test_get_icloud_drive_content_rejects_unsupported_file_type(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]

    result = get_icloud_drive_content(handle, root=root)

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"


def test_get_icloud_drive_content_rejects_root_ancestor_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    external_root = tmp_path / "ExternalCloudDocs"
    _make_icloud_root(external_root)
    (external_root / "Packets" / "review-packet.md").write_text("external secret", encoding="utf-8")
    swapped = _swap_root_to_external_on_symlink_check(
        monkeypatch,
        root=root,
        external_root=external_root,
        target=root / "Packets" / "review-packet.md",
    )

    result = get_icloud_drive_content(handle, root=root)

    assert swapped["value"] is True
    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "read_error"
    assert "external secret" not in json.dumps(result)


def test_get_icloud_drive_content_rejects_real_directory_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    external_root = tmp_path / "ExternalCloudDocs"
    _make_icloud_root(external_root)
    (external_root / "Packets" / "review-packet.md").write_text("external secret", encoding="utf-8")
    swapped = _replace_root_with_external_directory_on_symlink_check(
        monkeypatch,
        root=root,
        external_root=external_root,
        target=root / "Packets" / "review-packet.md",
    )

    result = get_icloud_drive_content(handle, root=root)

    assert swapped["value"] is True
    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "read_error"
    assert "external secret" not in json.dumps(result)


def test_get_icloud_drive_content_rejects_selected_file_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    swapped = _replace_target_on_symlink_check(
        monkeypatch,
        root=root,
        target=root / "Packets" / "review-packet.md",
        replacement="replacement secret",
    )

    result = get_icloud_drive_content(handle, root=root)

    assert swapped["value"] is True
    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "read_error"
    assert "replacement secret" not in json.dumps(result)


def test_export_icloud_drive_file_writes_selected_binary_without_source_path(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]

    result = export_icloud_drive_file(
        handle,
        root=root,
        output_dir=tmp_path / "exports",
        filename="../review image.bin",
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_exported"] is True
    assert result["result"]["file_content_returned"] is False
    assert result["result"]["file_content_exported"] is True
    assert result["result"]["source_path_returned"] is False
    assert result["result"]["exported_filename"] == "review-image.bin"
    assert result["result"]["exported_bytes"] == 2
    assert Path(result["result"]["exported_path"]).read_bytes() == b"\x00\x01"
    assert str(root) not in json.dumps(result)


def test_export_icloud_drive_file_rejects_root_ancestor_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    external_root = tmp_path / "ExternalCloudDocs"
    _make_icloud_root(external_root)
    (external_root / "Packets" / "image.bin").write_bytes(b"outside-root")
    output_dir = tmp_path / "exports"
    swapped = _swap_root_to_external_on_symlink_check(
        monkeypatch,
        root=root,
        external_root=external_root,
        target=root / "Packets" / "image.bin",
    )

    result = export_icloud_drive_file(handle, root=root, output_dir=output_dir)

    assert swapped["value"] is True
    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "icloud_drive_export_failed"
    assert not output_dir.exists()


def test_export_icloud_drive_file_rejects_real_directory_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    external_root = tmp_path / "ExternalCloudDocs"
    _make_icloud_root(external_root)
    (external_root / "Packets" / "image.bin").write_bytes(b"outside-root")
    output_dir = tmp_path / "exports"
    swapped = _replace_root_with_external_directory_on_symlink_check(
        monkeypatch,
        root=root,
        external_root=external_root,
        target=root / "Packets" / "image.bin",
    )

    result = export_icloud_drive_file(handle, root=root, output_dir=output_dir)

    assert swapped["value"] is True
    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "icloud_drive_export_failed"
    assert not output_dir.exists()


def test_export_icloud_drive_file_rejects_selected_file_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    output_dir = tmp_path / "exports"
    swapped = _replace_target_on_symlink_check(
        monkeypatch,
        root=root,
        target=root / "Packets" / "image.bin",
        replacement=b"replacement-bytes",
    )

    result = export_icloud_drive_file(handle, root=root, output_dir=output_dir)

    assert swapped["value"] is True
    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "icloud_drive_export_failed"
    assert not output_dir.exists()


def test_export_icloud_drive_file_allows_regular_document_files(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Packets" / "proposal.docx").write_bytes(b"DOCX")
    handle = search_icloud_drive_metadata("proposal", root=root)["results"][0]["handle"]

    result = export_icloud_drive_file(handle, root=root, output_dir=tmp_path / "exports")

    assert result["status"] == "ok"
    assert result["result"]["exported_filename"] == "proposal.docx"
    assert Path(result["result"]["exported_path"]).read_bytes() == b"DOCX"


def test_export_icloud_drive_file_rejects_output_dir_inside_icloud_root(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]

    result = export_icloud_drive_file(handle, root=root, output_dir=root / "Exports")

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "output_dir_in_icloud_root"
    assert not (root / "Exports").exists()


def test_export_icloud_drive_file_rejects_output_dir_symlink_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    real_parent = tmp_path / "real-output"
    real_parent.mkdir()
    symlink_parent = tmp_path / "output-link"
    symlink_parent.symlink_to(real_parent, target_is_directory=True)

    result = export_icloud_drive_file(handle, root=root, output_dir=symlink_parent / "exports")

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "invalid_output_dir"
    assert not (real_parent / "exports").exists()


def test_export_icloud_drive_file_rejects_deep_output_dir_symlink_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    real_parent = tmp_path / "real-output"
    real_parent.mkdir()
    symlink_parent = tmp_path / "output-link"
    symlink_parent.symlink_to(real_parent, target_is_directory=True)

    result = export_icloud_drive_file(handle, root=root, output_dir=symlink_parent / "nested" / "exports")

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "invalid_output_dir"
    assert not (real_parent / "nested").exists()


def test_export_icloud_drive_file_rejects_nested_output_symlink_into_root(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    (output_parent / "icloud-link").symlink_to(root, target_is_directory=True)

    result = export_icloud_drive_file(
        handle,
        root=root,
        output_dir=output_parent / "icloud-link" / "Exports",
    )

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "output_dir_in_icloud_root"
    assert not (root / "Exports").exists()


def test_export_icloud_drive_file_allows_macos_var_temp_alias(tmp_path: Path) -> None:
    canonical_tmp = tmp_path.resolve()
    private_var = Path("/private/var")
    if not Path("/var").is_symlink():
        pytest.skip("/var is not a symlink on this host")
    try:
        relative_tmp = canonical_tmp.relative_to(private_var)
    except ValueError:
        pytest.skip("pytest temp root is not under /private/var on this host")
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]

    result = export_icloud_drive_file(
        handle,
        root=root,
        output_dir=Path("/var") / relative_tmp / "exports",
    )

    assert result["status"] == "ok"
    assert Path(result["result"]["exported_path"]).read_bytes() == b"\x00\x01"
    assert str(result["result"]["exported_path"]).startswith(str(canonical_tmp))


def test_export_icloud_drive_file_rejects_invalid_byte_cap(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]

    result = export_icloud_drive_file(
        handle,
        root=root,
        output_dir=tmp_path / "exports",
        max_bytes="large",  # type: ignore[arg-type]
    )

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "invalid_byte_limit"
    assert not (tmp_path / "exports").exists()

    zero_result = export_icloud_drive_file(
        handle,
        root=root,
        output_dir=tmp_path / "zero-exports",
        max_bytes=0,
    )

    assert zero_result["status"] == "export_unavailable"
    assert zero_result["warnings"][0]["code"] == "invalid_byte_limit"
    assert not (tmp_path / "zero-exports").exists()


def test_export_icloud_drive_file_rejects_oversized_file(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    output_dir = tmp_path / "exports"

    result = export_icloud_drive_file(handle, root=root, output_dir=output_dir, max_bytes=1)

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "file_too_large"
    assert not output_dir.exists()


def test_export_icloud_drive_file_rejects_symlink_output_dir(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    output_dir = tmp_path / "exports-link"
    output_dir.symlink_to(real_dir)

    result = export_icloud_drive_file(handle, root=root, output_dir=output_dir)

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "invalid_output_dir"


def test_export_icloud_drive_file_uses_unique_filename_without_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    existing = output_dir / "review-image.bin"
    existing.write_bytes(b"keep")

    result = export_icloud_drive_file(
        handle,
        root=root,
        output_dir=output_dir,
        filename="review image.bin",
    )

    assert result["status"] == "ok"
    assert result["result"]["exported_filename"] == "review-image-1.bin"
    assert existing.read_bytes() == b"keep"
    assert (output_dir / "review-image-1.bin").read_bytes() == b"\x00\x01"


def test_export_icloud_drive_file_cleans_up_path_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    output_dir = tmp_path / "exports"
    target = output_dir / "image.bin"
    impostor = tmp_path / "impostor.bin"
    impostor.write_bytes(b"impostor")
    original_lstat = Path.lstat

    def mismatched_lstat(path: Path) -> os.stat_result:
        if path == target:
            return original_lstat(impostor)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", mismatched_lstat)

    result = export_icloud_drive_file(handle, root=root, output_dir=output_dir)

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "icloud_drive_export_failed"
    assert not target.exists()
    assert impostor.read_bytes() == b"impostor"


def test_export_icloud_drive_file_rejects_package_internal_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Draft.pages"
    package.mkdir()
    (package / "index.pdf").write_bytes(b"PDF")
    handle = make_opaque_handle("icloud:file", "Draft.pages/index.pdf")

    result = export_icloud_drive_file(handle, root=root, output_dir=tmp_path / "exports")

    assert result["status"] == "not_found"
    assert not (tmp_path / "exports").exists()


def test_export_icloud_drive_file_rejects_directory_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]

    result = export_icloud_drive_file(handle, root=root, output_dir=tmp_path / "exports")

    assert result["status"] == "export_unavailable"
    assert result["warnings"][0]["code"] == "unsupported_file_type"


def test_get_icloud_drive_content_rejects_invalid_utf8_text_file(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    invalid = root / "Packets" / "invalid.md"
    invalid.write_bytes(b"valid prefix\xff")
    handle = search_icloud_drive_metadata("invalid", root=root)["results"][0]["handle"]

    result = get_icloud_drive_content(handle, root=root)

    assert result["status"] == "content_unavailable"
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert "content_text" not in str(result["warnings"])


def test_search_icloud_drive_skips_package_contents(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Draft.pages"
    package.mkdir()
    (package / "index.md").write_text("Package internals\n", encoding="utf-8")

    result = search_icloud_drive_metadata("index", root=root)

    assert result["status"] == "ok"
    assert result["result_count"] == 0


def test_get_icloud_drive_content_rejects_old_package_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Draft.pages"
    package.mkdir()
    (package / "index.md").write_text("Package internals\n", encoding="utf-8")
    handle = make_opaque_handle("icloud:file", "Draft.pages/index.md")

    result = get_icloud_drive_content(handle, root=root)

    assert result["status"] == "not_found"


def test_get_icloud_drive_content_rejects_bad_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = get_icloud_drive_content("icloud:file:Packets/review-packet.md", root=root)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_icloud_drive_reports_unavailable_root(tmp_path: Path) -> None:
    result = search_icloud_drive_metadata("packet", root=tmp_path / "missing")

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "icloud_drive_unavailable"


def _parent_handle(root: Path) -> str:
    return search_icloud_drive_metadata("Packets", root=root)["results"][0]["handle"]


def _parent_identity_sha256(root: Path) -> str:
    return icloud_drive_adapter._directory_identity_sha256(root / "Packets", root)


def _approval_token(plan: dict) -> str:
    fingerprint = plan["preview"]["approval"]["approval_fingerprint"]
    return f"icloud-drive-apply:v1:{fingerprint}"


def _content_sha(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _delete_staging_entries(root: Path) -> list[Path]:
    staging_root = root / ".local-apple-data-delete-staging"
    if not staging_root.exists():
        return []
    return list(staging_root.iterdir())


def test_plan_icloud_drive_change_create_text_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)

    result = plan_icloud_drive_change(
        "create-text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic iCloud text.",
        root=root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "create_text"
    assert preview["target"] == {
        "parent_handle": parent_handle,
        "expected_parent_identity_sha256": _parent_identity_sha256(root),
        "filename": "new-note.md",
    }
    assert preview["proposed"]["content_chars"] == 22
    assert preview["idempotency_key"].startswith("icloud-drive-plan:v1:")
    assert preview["approval"]["approval_token_format"] == (
        "icloud-drive-apply:v1:<approval_fingerprint>"
    )


def test_plan_icloud_drive_change_create_folder_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)

    result = plan_icloud_drive_change(
        "create-folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    preview = result["preview"]
    assert preview["operation"] == "create_folder"
    assert preview["target"] == {
        "parent_handle": parent_handle,
        "expected_parent_identity_sha256": _parent_identity_sha256(root),
        "filename": "Project Notes",
    }
    assert preview["proposed"] == {
        "kind": "directory",
        "content": "blocked",
        "overwrite": "blocked",
        "delete": "blocked",
    }
    assert preview["idempotency_key"].startswith("icloud-drive-plan:v1:")


def test_plan_icloud_drive_change_create_folder_path_returns_component_preview(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)

    result = plan_icloud_drive_change(
        "create-folder-path",
        parent_handle=parent_handle,
        folder_components=["Client", "2026", "Drafts"],
        root=root,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "create_folder_path"
    assert preview["target"] == {
        "parent_handle": parent_handle,
        "expected_parent_identity_sha256": _parent_identity_sha256(root),
        "folder_components": ["Client", "2026", "Drafts"],
    }
    assert preview["proposed"] == {
        "kind": "directory_path",
        "component_count": 3,
        "existing_directories": "allowed",
        "content": "blocked",
        "overwrite": "blocked",
        "delete": "blocked",
    }
    assert "Client/2026/Drafts" not in json.dumps(preview)


def test_plan_icloud_drive_change_create_folder_path_rejects_unsafe_components(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    cases = [
        (["One", "Two", "Three", "Four"], "input_too_large"),
        (["Client/Raw"], "invalid_filename"),
        ([".hidden"], "invalid_filename"),
        (["Draft.pages"], "unsupported_file_type"),
        (["Draft."], "invalid_filename"),
        (["Draft "], "invalid_filename"),
    ]

    for components, code in cases:
        result = plan_icloud_drive_change(
            "create_folder_path",
            parent_handle=_parent_handle(root),
            folder_components=components,
            root=root,
        )
        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == code
        assert "approval" not in result


def test_plan_icloud_drive_change_create_folder_path_rejects_expected_sha(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=_parent_handle(root),
        folder_components=["Client", "Drafts"],
        expected_current_sha256="a" * 64,
        root=root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unexpected_expected_current_sha256"
    assert "approval" not in result


def test_plan_icloud_drive_change_rename_folder_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("Packets", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "rename-folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Packets",
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "rename_folder"
    assert preview["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
        "filename": "Renamed Packets",
    }
    assert preview["proposed"] == {
        "kind": "directory",
        "rename_to": "Renamed Packets",
        "empty_folder_required": False,
        "non_empty_allowed": True,
        "overwrite": "blocked",
        "recursive_content_read": "blocked",
        "content_return": "blocked",
    }


def test_plan_icloud_drive_change_trash_folder_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("Packets", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "trash-folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    preview = result["preview"]
    assert preview["operation"] == "trash_folder"
    assert preview["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
    }
    assert preview["proposed"] == {
        "kind": "directory",
        "move_to_trash": True,
        "empty_folder_required": False,
        "non_empty_allowed": True,
        "permanent_delete": "blocked",
        "recursive_delete": "blocked",
        "recursive_content_read": "blocked",
        "content_return": "blocked",
    }


def test_plan_icloud_drive_change_delete_folder_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "delete-folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    preview = result["preview"]
    assert preview["operation"] == "delete_folder"
    assert preview["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
    }
    assert preview["proposed"] == {
        "kind": "directory",
        "permanent_delete": True,
        "empty_folder_required": False,
        "non_empty_allowed": True,
        "recursive_delete": "bounded_private_tree",
        "source_tree_binding": "private",
        "trash_fallback": "blocked",
        "content_return": "blocked",
    }


def test_plan_icloud_drive_change_move_folder_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    result = plan_icloud_drive_change(
        "move-folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    preview = result["preview"]
    assert preview["operation"] == "move_folder"
    assert preview["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
        "parent_handle": parent_handle,
        "filename": "Moved Folder",
    }
    assert preview["proposed"] == {
        "kind": "directory",
        "move_to_parent": "exact_handle",
        "move_to_name": "Moved Folder",
        "empty_folder_required": False,
        "non_empty_allowed": True,
        "overwrite": "blocked",
        "recursive_content_read": "blocked",
        "content_return": "blocked",
    }


def test_plan_icloud_drive_change_copy_folder_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    result = plan_icloud_drive_change(
        "copy-folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    preview = result["preview"]
    assert preview["operation"] == "copy_folder"
    assert preview["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
        "parent_handle": parent_handle,
        "filename": "Copied Folder",
    }
    assert preview["proposed"] == {
        "kind": "directory",
        "copy_to_parent": "exact_handle",
        "copy_to_name": "Copied Folder",
        "empty_folder_required": False,
        "non_empty_allowed": True,
        "overwrite": "blocked",
        "recursive_copy": "bounded_private_tree",
        "source_tree_binding": "private",
        "source_mutation": "blocked",
        "content_return": "blocked",
    }


def test_plan_icloud_drive_change_append_text_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    result = plan_icloud_drive_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "append_text"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"]["append_chars"] == 26
    assert preview["proposed"]["append_content_sha256"] == _content_sha("\nAppended synthetic note.\n")
    assert preview["proposed"]["overwrite"] == "blocked"
    assert preview["idempotency_key"].startswith("icloud-drive-plan:v1:")


def test_plan_icloud_drive_change_replace_text_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    result = plan_icloud_drive_change(
        "replace-text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replaced Packet\n",
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "replace_text"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"]["replace_chars"] == 18
    assert preview["proposed"]["replace_content_sha256"] == _content_sha("# Replaced Packet\n")
    assert preview["proposed"]["append"] == "blocked"
    assert preview["proposed"]["delete"] == "blocked"
    assert preview["idempotency_key"].startswith("icloud-drive-plan:v1:")


def test_plan_icloud_drive_change_trash_text_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    result = plan_icloud_drive_change(
        "trash-text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "trash_text"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"] == {
        "kind": "file",
        "content_type": "text",
        "move_to_trash": True,
        "permanent_delete": "blocked",
        "folder_delete": "blocked",
        "content_return": "blocked",
    }
    assert preview["idempotency_key"].startswith("icloud-drive-plan:v1:")


def test_plan_icloud_drive_change_delete_text_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    result = plan_icloud_drive_change(
        "delete-text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "delete_text"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_current_sha256"] == current_sha
    assert len(preview["target"]["expected_file_identity_sha256"]) == 64
    assert "dev" not in preview["target"]
    assert "ino" not in preview["target"]
    assert "mtime_ns" not in preview["target"]
    assert "ctime_ns" not in preview["target"]
    assert preview["proposed"] == {
        "kind": "file",
        "content_type": "text",
        "permanent_delete": True,
        "trash_fallback": "blocked",
        "folder_delete": "blocked",
        "content_return": "blocked",
    }
    assert preview["idempotency_key"].startswith("icloud-drive-plan:v1:")


def test_plan_icloud_drive_change_delete_text_rejects_unsupported_target_without_approval(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()

    result = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    assert result["status"] == "error"
    assert result["preview"] is None
    assert result["apply_available"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert "approval" not in result


def test_plan_icloud_drive_change_rename_copy_move_text_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    rename = plan_icloud_drive_change(
        "rename-text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    copy = plan_icloud_drive_change(
        "copy-text",
        handle=handle,
        expected_current_sha256=current_sha,
        parent_handle=parent_handle,
        filename="review-copy.md",
    )
    move = plan_icloud_drive_change(
        "move-text",
        handle=handle,
        expected_current_sha256=current_sha,
        parent_handle=parent_handle,
    )

    assert rename["status"] == "ok"
    assert rename["preview"]["operation"] == "rename_text"
    assert rename["preview"]["target"]["filename"] == "review-renamed.md"
    assert rename["preview"]["proposed"]["overwrite"] == "blocked"
    assert copy["status"] == "ok"
    assert copy["preview"]["operation"] == "copy_text"
    assert copy["preview"]["target"]["parent_handle"] == parent_handle
    assert copy["preview"]["proposed"]["source_mutation"] == "blocked"
    assert move["status"] == "ok"
    assert move["preview"]["operation"] == "move_text"
    assert move["preview"]["target"]["filename"] is None
    assert move["preview"]["proposed"]["move_to_parent"] == "exact_handle"


def test_plan_icloud_drive_change_rename_copy_move_file_returns_preview_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    rename = plan_icloud_drive_change(
        "rename-file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-renamed.bin",
    )
    copy = plan_icloud_drive_change(
        "copy-file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        parent_handle=parent_handle,
        filename="image-copy.bin",
    )
    move = plan_icloud_drive_change(
        "move-file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        parent_handle=parent_handle,
    )
    trash = plan_icloud_drive_change(
        "trash-file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )
    delete = plan_icloud_drive_change(
        "delete-file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )

    assert rename["status"] == "ok"
    assert rename["privacy"]["content_inspected"] is False
    assert rename["preview"]["operation"] == "rename_file"
    assert rename["preview"]["target"]["filename"] == "image-renamed.bin"
    assert rename["preview"]["proposed"]["content_type"] == "regular_file"
    assert rename["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert copy["status"] == "ok"
    assert copy["preview"]["operation"] == "copy_file"
    assert copy["preview"]["target"]["parent_handle"] == parent_handle
    assert copy["preview"]["proposed"]["source_mutation"] == "blocked"
    assert move["status"] == "ok"
    assert move["preview"]["operation"] == "move_file"
    assert move["preview"]["target"]["filename"] is None
    assert move["preview"]["proposed"]["move_to_parent"] == "exact_handle"
    assert trash["status"] == "ok"
    assert trash["preview"]["operation"] == "trash_file"
    assert trash["preview"]["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
    }
    assert trash["preview"]["proposed"]["content_type"] == "regular_file"
    assert trash["preview"]["proposed"]["move_to_trash"] is True
    assert trash["preview"]["proposed"]["permanent_delete"] == "blocked"
    assert trash["preview"]["proposed"]["content_hash_return"] == "blocked"
    assert delete["status"] == "ok"
    assert delete["preview"]["operation"] == "delete_file"
    assert delete["preview"]["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
    }
    assert delete["preview"]["proposed"]["content_type"] == "regular_file"
    assert delete["preview"]["proposed"]["permanent_delete"] is True
    assert delete["preview"]["proposed"]["recoverable_trash"] == "blocked"
    assert delete["preview"]["proposed"]["content_hash_return"] == "blocked"


def test_plan_icloud_drive_change_import_file_returns_preview_without_path_or_hash(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-import.bin"
    source.write_bytes(b"\x00\x01imported")

    result = plan_icloud_drive_change(
        "import-file",
        parent_handle=_parent_handle(root),
        source_file=source,
        root=root,
    )

    assert result["status"] == "ok"
    json.dumps(result)
    assert result["preview"]["operation"] == "import_file"
    assert result["preview"]["target"] == {
        "parent_handle": _parent_handle(root),
        "expected_parent_identity_sha256": _parent_identity_sha256(root),
        "filename": "packet-import.bin",
    }
    proposed = result["preview"]["proposed"]
    assert proposed["content_type"] == "regular_file"
    assert proposed["source_filename"] == "packet-import.bin"
    assert proposed["source_size_bytes"] == len(b"\x00\x01imported")
    assert proposed["source_path_returned"] is False
    assert proposed["source_hash_returned"] is False
    assert proposed["content_hash_return"] == "blocked"
    assert "source_identity_sha256" not in result["preview"]["target"]
    assert "source_content_sha256" not in result["preview"]["target"]


def test_plan_icloud_drive_change_import_file_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-import.bin"
    source.write_bytes(b"\x00\x01imported")
    file_handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = plan_icloud_drive_change(
        "import_file",
        parent_handle="icloud:file:v1:not-a-real-handle",
        handle=file_handle,
        source_file=source,
        filename="packet-target.bin",
        content_text="unexpected text",
        expected_current_sha256="0" * 64,
        root=root,
    )
    non_import_result = plan_icloud_drive_change(
        "copy_file",
        handle=file_handle,
        parent_handle=_parent_handle(root),
        filename="copy-target.bin",
        expected_current_sha256=search_icloud_drive_metadata("review", root=root)["results"][0][
            "metadata_sha256"
        ],
        source_file=source,
        root=root,
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "invalid_parent_handle" in codes
    assert "unexpected_handle" in codes
    assert "unexpected_content_text" in codes
    assert "unexpected_expected_current_sha256" in codes
    assert non_import_result["status"] == "error"
    assert non_import_result["warnings"][0]["code"] == "unexpected_source_file"


def test_apply_icloud_drive_change_import_file_copies_to_exact_parent(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-import.bin"
    payload = b"\x00\x01imported"
    source.write_bytes(payload)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=source,
        filename="packet-target.bin",
        root=root,
    )

    result = apply_icloud_drive_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=source,
        filename="packet-target.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    target = root / "Packets" / "packet-target.bin"
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert target.read_bytes() == payload
    read_back = result["read_back"]
    assert read_back["name"] == "packet-target.bin"
    assert read_back["content_type"] == "regular_file"
    assert read_back["target_present"] is True
    assert read_back["imported"] is True
    assert read_back["source_path_returned"] is False
    assert read_back["source_hash_returned"] is False
    assert read_back["content_text_returned"] is False
    assert read_back["content_hash_returned"] is False
    assert str(source) not in json.dumps(result)


def test_apply_icloud_drive_change_import_file_rejects_stale_source_token(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-import.bin"
    source.write_bytes(b"before")
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=source,
        root=root,
    )
    source.write_bytes(b"after")

    result = apply_icloud_drive_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=source,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert not (root / "Packets" / "packet-import.bin").exists()


def test_plan_icloud_drive_change_import_file_rejects_unsafe_sources(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    inside = root / "Packets" / "image.bin"
    text_source = tmp_path / "packet.txt"
    text_source.write_text("text", encoding="utf-8")
    package = tmp_path / "Packet.pages"
    package.mkdir()
    package_source = package / "preview.bin"
    package_source.write_bytes(b"package")
    symlink_target = tmp_path / "packet-symlink-target.bin"
    symlink_target.write_bytes(b"symlink")
    symlink_source = tmp_path / "packet-symlink.bin"
    symlink_source.symlink_to(symlink_target)

    inside_result = plan_icloud_drive_change(
        "import_file",
        parent_handle=_parent_handle(root),
        source_file=inside,
        root=root,
    )
    text_result = plan_icloud_drive_change(
        "import_file",
        parent_handle=_parent_handle(root),
        source_file=text_source,
        root=root,
    )
    missing_result = plan_icloud_drive_change(
        "import_file",
        parent_handle=_parent_handle(root),
        source_file=tmp_path / "missing.bin",
        root=root,
    )
    package_result = plan_icloud_drive_change(
        "import_file",
        parent_handle=_parent_handle(root),
        source_file=package_source,
        root=root,
    )
    symlink_result = plan_icloud_drive_change(
        "import_file",
        parent_handle=_parent_handle(root),
        source_file=symlink_source,
        root=root,
    )

    assert inside_result["status"] == "error"
    assert inside_result["warnings"][0]["code"] == "source_inside_icloud_root"
    assert text_result["status"] == "error"
    assert text_result["warnings"][0]["code"] == "unsupported_file_type"
    assert missing_result["status"] == "error"
    assert missing_result["warnings"][0]["code"] == "source_file_unavailable"
    assert package_result["status"] == "error"
    assert package_result["warnings"][0]["code"] == "unsupported_file_type"
    assert symlink_result["status"] == "error"
    assert symlink_result["warnings"][0]["code"] == "symlink_source_blocked"


def test_apply_icloud_drive_change_import_file_refuses_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-import.bin"
    payload = b"\x00\x01imported"
    source.write_bytes(payload)
    target = root / "Packets" / "packet-target.bin"
    target.write_bytes(b"existing")
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=source,
        filename="packet-target.bin",
        root=root,
    )

    result = apply_icloud_drive_change(
        "import_file",
        parent_handle=parent_handle,
        source_file=source,
        filename="packet-target.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert target.read_bytes() == b"existing"
    assert source.read_bytes() == payload


def test_plan_icloud_drive_change_replace_file_returns_preview_without_path_or_hash(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.bin"
    source.write_bytes(b"\x10\x11replacement")
    item = search_icloud_drive_metadata("image", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "replace-file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        root=root,
    )

    assert result["status"] == "ok"
    json.dumps(result)
    assert result["preview"]["operation"] == "replace_file"
    assert result["preview"]["target"] == {
        "handle": item["handle"],
        "expected_current_sha256": item["metadata_sha256"],
    }
    proposed = result["preview"]["proposed"]
    assert proposed["content_type"] == "regular_file"
    assert proposed["replace_from_source_filename"] == "packet-replacement.bin"
    assert proposed["source_size_bytes"] == len(b"\x10\x11replacement")
    assert proposed["source_path_returned"] is False
    assert proposed["source_hash_returned"] is False
    assert proposed["target_name_preserved"] is True
    assert proposed["content_hash_return"] == "blocked"
    assert "source_identity_sha256" not in result["preview"]["target"]
    assert "source_content_sha256" not in result["preview"]["target"]
    assert str(source) not in json.dumps(result)


def test_plan_icloud_drive_change_replace_file_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.bin"
    source.write_bytes(b"\x10\x11replacement")
    item = search_icloud_drive_metadata("image", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        parent_handle=_parent_handle(root),
        filename="unexpected.bin",
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        content_text="unexpected",
        root=root,
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "unexpected_create_target" in codes
    assert "unexpected_content_text" in codes


def test_plan_icloud_drive_change_replace_file_rejects_unsafe_sources(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target_item = search_icloud_drive_metadata("image", root=root)["results"][0]
    inside = root / "Packets" / "image.bin"
    text_source = tmp_path / "packet.txt"
    text_source.write_text("text", encoding="utf-8")
    package = tmp_path / "Packet.pages"
    package.mkdir()
    package_source = package / "preview.bin"
    package_source.write_bytes(b"package")
    symlink_target = tmp_path / "packet-symlink-target.bin"
    symlink_target.write_bytes(b"symlink")
    symlink_source = tmp_path / "packet-symlink.bin"
    symlink_source.symlink_to(symlink_target)

    kwargs = {
        "handle": target_item["handle"],
        "expected_current_sha256": target_item["metadata_sha256"],
        "root": root,
    }
    inside_result = plan_icloud_drive_change("replace_file", source_file=inside, **kwargs)
    text_result = plan_icloud_drive_change("replace_file", source_file=text_source, **kwargs)
    missing_result = plan_icloud_drive_change("replace_file", source_file=tmp_path / "missing.bin", **kwargs)
    package_result = plan_icloud_drive_change("replace_file", source_file=package_source, **kwargs)
    symlink_result = plan_icloud_drive_change("replace_file", source_file=symlink_source, **kwargs)
    bad_handle_result = plan_icloud_drive_change(
        "replace_file",
        handle="icloud:file:v1:bad",
        expected_current_sha256=target_item["metadata_sha256"],
        source_file=tmp_path / "missing.bin",
        root=root,
    )

    assert inside_result["status"] == "error"
    assert inside_result["warnings"][0]["code"] == "source_inside_icloud_root"
    assert text_result["status"] == "error"
    assert text_result["warnings"][0]["code"] == "unsupported_file_type"
    assert missing_result["status"] == "error"
    assert missing_result["warnings"][0]["code"] == "source_file_unavailable"
    assert package_result["status"] == "error"
    assert package_result["warnings"][0]["code"] == "unsupported_file_type"
    assert symlink_result["status"] == "error"
    assert symlink_result["warnings"][0]["code"] == "symlink_source_blocked"
    assert bad_handle_result["status"] == "error"
    assert bad_handle_result["warnings"][0]["code"] == "invalid_handle"


def test_apply_icloud_drive_change_replace_file_replaces_exact_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.bin"
    payload = b"\x10\x11replacement"
    source.write_bytes(payload)
    target = root / "Packets" / "image.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        root=root,
    )

    result = apply_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert target.read_bytes() == payload
    assert source.read_bytes() == payload
    read_back = result["read_back"]
    assert read_back["name"] == "image.bin"
    assert read_back["content_type"] == "regular_file"
    assert read_back["target_present"] is True
    assert read_back["replaced"] is True
    assert read_back["source_path_returned"] is False
    assert read_back["source_hash_returned"] is False
    assert read_back["content_text_returned"] is False
    assert read_back["content_hash_returned"] is False
    assert "content_sha256" not in read_back
    assert str(source) not in json.dumps(result)


def test_apply_icloud_drive_change_replace_file_rejects_stale_source_token(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.bin"
    source.write_bytes(b"before")
    target = root / "Packets" / "image.bin"
    original_target = target.read_bytes()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        root=root,
    )
    source.write_bytes(b"after")

    result = apply_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert target.read_bytes() == original_target


def test_apply_icloud_drive_change_replace_file_reports_source_drift_during_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.bin"
    source.write_bytes(b"\x10\x11replacement")
    target = root / "Packets" / "image.bin"
    original_target = target.read_bytes()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        root=root,
    )

    def changed_during_stream(*args: object, **kwargs: object) -> bytes:
        raise icloud_drive_adapter._ContentChangedDuringReplaceError()

    monkeypatch.setattr(
        icloud_drive_adapter,
        "_copy_regular_file_stream_no_follow_at",
        changed_during_stream,
    )

    result = apply_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "source_file_changed"
    assert target.read_bytes() == original_target


def test_apply_icloud_drive_change_replace_file_rejects_stale_target_metadata(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.bin"
    payload = b"\x10\x11replacement"
    source.write_bytes(payload)
    target = root / "Packets" / "image.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        root=root,
    )
    target.write_bytes(b"target changed")

    result = apply_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert target.read_bytes() == b"target changed"
    assert source.read_bytes() == payload


def test_apply_icloud_drive_change_replace_file_rejects_extension_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = tmp_path / "packet-replacement.dat"
    source.write_bytes(b"\x10\x11replacement")
    target = root / "Packets" / "image.bin"
    original_target = target.read_bytes()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        root=root,
    )

    result = apply_icloud_drive_change(
        "replace_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        source_file=source,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert target.read_bytes() == original_target


def test_apply_icloud_drive_change_trash_file_moves_exact_regular_file_to_trash(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    original_payload = target.read_bytes()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert target.exists() is False
    trashed_files = [path for path in (root / ".Trash").iterdir() if path.is_file()]
    assert len(trashed_files) == 1
    assert trashed_files[0].read_bytes() == original_payload
    read_back = result["read_back"]
    assert read_back["name"] == "image.bin"
    assert read_back["content_type"] == "regular_file"
    assert read_back["original_present"] is False
    assert read_back["trashed"] is True
    assert read_back["trash_path_returned"] is False
    assert read_back["content_text_returned"] is False
    assert read_back["content_hash_returned"] is False
    assert "content_sha256" not in read_back
    assert str(root) not in json.dumps(result)


def test_apply_icloud_drive_change_trash_file_rejects_stale_metadata(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    target.write_bytes(b"\x02\x03changed")

    result = apply_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert target.read_bytes() == b"\x02\x03changed"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_trash_file_rollback_does_not_claim_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    original_payload = target.read_bytes()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    original_same_stat_relocated_snapshot = icloud_drive_adapter._same_stat_relocated_snapshot
    checks = 0

    def mismatch_once(*args: object, **kwargs: object) -> bool:
        nonlocal checks
        checks += 1
        if checks == 1:
            return False
        return original_same_stat_relocated_snapshot(*args, **kwargs)

    monkeypatch.setattr(icloud_drive_adapter, "_same_stat_relocated_snapshot", mismatch_once)

    result = apply_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["original_present"] is True
    assert result["read_back"]["trashed"] is False
    assert target.read_bytes() == original_payload
    with os.scandir(root / ".Trash") as entries:
        trash_entries = [root / ".Trash" / entry.name for entry in entries]
    assert trash_entries == []


def test_apply_icloud_drive_change_trash_file_rejects_text_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    item = search_icloud_drive_metadata("review", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "trash_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert "Use the text-file operations" in result["warnings"][0]["message"]
    assert target.exists()
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_trash_file_rejects_symlink_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    symlink = root / "Packets" / "image-link.bin"
    symlink.symlink_to(outside)
    handle = make_opaque_handle("icloud:file", "Packets/image-link.bin")
    expected_sha = "0" * 64
    plan = plan_icloud_drive_change(
        "trash_file",
        handle=handle,
        expected_current_sha256=expected_sha,
        root=root,
    )

    result = apply_icloud_drive_change(
        "trash_file",
        handle=handle,
        expected_current_sha256=expected_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_file_not_found"
    assert symlink.is_symlink()
    assert outside.read_bytes() == b"outside"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_delete_file_removes_exact_regular_file(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert target.exists() is False
    assert not (root / ".local-apple-data-delete-staging").exists()
    read_back = result["read_back"]
    assert read_back["name"] == "image.bin"
    assert read_back["content_type"] == "regular_file"
    assert read_back["original_present"] is False
    assert read_back["verified_absent"] is True
    assert read_back["permanently_deleted"] is True
    assert read_back["trash_path_returned"] is False
    assert read_back["staging_path_returned"] is False
    assert read_back["content_text_returned"] is False
    assert read_back["content_hash_returned"] is False
    assert "content_sha256" not in read_back
    assert str(root) not in json.dumps(result)


def test_apply_icloud_drive_change_delete_file_rejects_stale_metadata(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    target.write_bytes(b"\x02\x03changed")

    result = apply_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert target.read_bytes() == b"\x02\x03changed"
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_file_rechecks_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    original_entry_stat = icloud_drive_adapter._entry_stat_no_follow_at
    target_stats = 0

    def mutate_on_pre_move(parent_fd: int, name: str) -> os.stat_result:
        nonlocal target_stats
        if name == target.name:
            target_stats += 1
            if target_stats == 2:
                target.write_bytes(b"\x02\x03changed-before-staging")
        return original_entry_stat(parent_fd, name)

    monkeypatch.setattr(icloud_drive_adapter, "_entry_stat_no_follow_at", mutate_on_pre_move)

    result = apply_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert target.read_bytes() == b"\x02\x03changed-before-staging"
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_file_rollback_does_not_claim_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    original_payload = target.read_bytes()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    original_same_stat_relocated_snapshot = icloud_drive_adapter._same_stat_relocated_snapshot
    checks = 0

    def mismatch_once(*args: object, **kwargs: object) -> bool:
        nonlocal checks
        checks += 1
        if checks == 1:
            return False
        return original_same_stat_relocated_snapshot(*args, **kwargs)

    monkeypatch.setattr(icloud_drive_adapter, "_same_stat_relocated_snapshot", mismatch_once)

    result = apply_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["original_present"] is True
    assert result["read_back"]["permanently_deleted"] is False
    assert target.read_bytes() == original_payload
    staging = root / ".local-apple-data-delete-staging"
    assert not staging.exists() or list(staging.iterdir()) == []


def test_apply_icloud_drive_change_delete_file_rejects_text_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    item = search_icloud_drive_metadata("review", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert "Use the text-file operations" in result["warnings"][0]["message"]
    assert target.exists()


def test_apply_icloud_drive_change_delete_file_rejects_symlink_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    symlink = root / "Packets" / "image-link.bin"
    symlink.symlink_to(outside)
    handle = make_opaque_handle("icloud:file", "Packets/image-link.bin")
    expected_sha = "0" * 64
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=handle,
        expected_current_sha256=expected_sha,
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_file",
        handle=handle,
        expected_current_sha256=expected_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_file_not_found"
    assert symlink.is_symlink()
    assert outside.read_bytes() == b"outside"


def test_apply_icloud_drive_change_delete_file_rejects_package_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Draft.pages"
    package.mkdir()
    member = package / "image.bin"
    member.write_bytes(b"\x00\x02")
    handle = make_opaque_handle("icloud:file", "Draft.pages/image.bin")
    metadata_sha = icloud_drive_adapter._file_metadata_sha256(member, root)
    original_resolve_handle = icloud_drive_adapter._resolve_handle

    def resolve_package_member(candidate: str, root: Path, *, max_scan_entries: int) -> Path | None:
        if candidate == handle:
            return member
        return original_resolve_handle(candidate, root, max_scan_entries=max_scan_entries)

    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", resolve_package_member)
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=handle,
        expected_current_sha256=metadata_sha,
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_file",
        handle=handle,
        expected_current_sha256=metadata_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert member.read_bytes() == b"\x00\x02"
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_file_rejects_non_regular_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    directory = root / "Packets"
    item = search_icloud_drive_metadata("Packets", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_file_not_found"
    assert directory.is_dir()
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_plan_icloud_drive_change_rejects_raw_path_filename(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = plan_icloud_drive_change(
        "create_text",
        parent_handle=_parent_handle(root),
        filename="Nested/bad.md",
        content_text="Synthetic text.",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_filename"


def test_plan_icloud_drive_change_create_folder_rejects_content_and_packages(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    result = plan_icloud_drive_change(
        "create_folder",
        parent_handle=_parent_handle(root),
        filename="Bad.app",
        content_text="Synthetic text.",
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "unsupported_file_type" in codes
    assert "unexpected_content_text" in codes


def test_plan_icloud_drive_change_append_replace_trash_or_delete_text_requires_hash_and_file_handle(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)

    for operation in ("append_text", "replace_text", "trash_text", "delete_text"):
        result = plan_icloud_drive_change(
            operation,
            parent_handle=_parent_handle(root),
            filename="bad.md",
            content_text="Synthetic text.",
        )

        codes = {warning["code"] for warning in result["warnings"]}
        assert result["status"] == "error"
        assert "invalid_handle" in codes
        assert "unexpected_create_target" in codes
        assert "missing_required_field" in codes


def test_plan_icloud_drive_change_trash_or_delete_text_rejects_content_text(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    for operation in ("trash_text", "delete_text"):
        result = plan_icloud_drive_change(
            operation,
            handle=handle,
            expected_current_sha256=_content_sha("# Synthetic Packet\nLine two\n"),
            content_text="delete this too",
        )

        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "unexpected_content_text"


def test_plan_icloud_drive_change_rename_copy_move_reject_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    rename = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        parent_handle=_parent_handle(root),
        expected_current_sha256=current_sha,
        filename="renamed.md",
        content_text="blocked",
    )
    copy = plan_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="copy.bin",
    )
    move = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    rename_codes = {warning["code"] for warning in rename["warnings"]}
    copy_codes = {warning["code"] for warning in copy["warnings"]}
    move_codes = {warning["code"] for warning in move["warnings"]}
    assert rename["status"] == "error"
    assert "unexpected_parent_handle" in rename_codes
    assert "unexpected_content_text" in rename_codes
    assert copy["status"] == "error"
    assert "unsupported_file_type" in copy_codes
    assert move["status"] == "error"
    assert "invalid_parent_handle" in move_codes


def test_plan_icloud_drive_change_rename_copy_move_file_reject_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    rename = plan_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="renamed.bin",
        content_text="blocked",
    )
    copy = plan_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="copy.md",
    )
    move = plan_icloud_drive_change(
        "move_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )

    rename_codes = {warning["code"] for warning in rename["warnings"]}
    copy_codes = {warning["code"] for warning in copy["warnings"]}
    move_codes = {warning["code"] for warning in move["warnings"]}
    assert rename["status"] == "error"
    assert "unexpected_parent_handle" in rename_codes
    assert "unexpected_content_text" in rename_codes
    assert copy["status"] == "error"
    assert "unsupported_file_type" in copy_codes
    assert move["status"] == "error"
    assert "invalid_parent_handle" in move_codes


def test_plan_icloud_drive_change_rename_folder_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("Packets", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        parent_handle=_parent_handle(root),
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Packets",
        content_text="blocked",
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "unexpected_parent_handle" in codes
    assert "unexpected_content_text" in codes


def test_plan_icloud_drive_change_trash_folder_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("Packets", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        parent_handle=_parent_handle(root),
        expected_current_sha256=item["metadata_sha256"],
        filename="Blocked",
        content_text="blocked",
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "unexpected_create_target" in codes
    assert "unexpected_content_text" in codes


def test_plan_icloud_drive_change_delete_folder_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("Packets", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        parent_handle=_parent_handle(root),
        expected_current_sha256=item["metadata_sha256"],
        filename="Blocked",
        content_text="blocked",
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "unexpected_create_target" in codes
    assert "unexpected_content_text" in codes

    missing_sha_result = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
    )
    assert missing_sha_result["status"] == "error"
    assert "missing_required_field" in {warning["code"] for warning in missing_sha_result["warnings"]}

    invalid_sha_result = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256="not-a-sha",
    )
    assert invalid_sha_result["status"] == "error"
    assert "invalid_expected_sha256" in {warning["code"] for warning in invalid_sha_result["warnings"]}

    malformed_handle_result = plan_icloud_drive_change(
        "delete_folder",
        handle="not-an-opaque-handle",
        expected_current_sha256=item["metadata_sha256"],
    )
    assert malformed_handle_result["status"] == "error"
    assert "invalid_handle" in {warning["code"] for warning in malformed_handle_result["warnings"]}


def test_plan_icloud_drive_change_move_folder_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        content_text="blocked",
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "invalid_parent_handle" in codes
    assert "unexpected_content_text" in codes


def test_plan_icloud_drive_change_copy_folder_rejects_wrong_inputs(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Copy Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        content_text="blocked",
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "error"
    assert "invalid_parent_handle" in codes
    assert "unexpected_content_text" in codes

    invalid_name_cases = [
        ("Nested/Folder", "invalid_filename"),
        (".Hidden Folder", "invalid_filename"),
        ("Blocked.app", "unsupported_file_type"),
        ("Bad Folder.", "invalid_filename"),
    ]
    for filename, warning_code in invalid_name_cases:
        bad_name_result = plan_icloud_drive_change(
            "copy_folder",
            handle=item["handle"],
            parent_handle=_parent_handle(root),
            expected_current_sha256=item["metadata_sha256"],
            filename=filename,
        )
        assert bad_name_result["status"] == "error"
        assert warning_code in {warning["code"] for warning in bad_name_result["warnings"]}

    missing_sha_result = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=_parent_handle(root),
        filename="Copied Folder",
    )
    assert missing_sha_result["status"] == "error"
    assert "missing_required_field" in {warning["code"] for warning in missing_sha_result["warnings"]}

    invalid_sha_result = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=_parent_handle(root),
        expected_current_sha256="not-a-sha",
        filename="Copied Folder",
    )
    assert invalid_sha_result["status"] == "error"
    assert "invalid_expected_sha256" in {warning["code"] for warning in invalid_sha_result["warnings"]}


def test_plan_and_apply_icloud_drive_change_reject_non_utf8_content_text(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    bad_text = "Synthetic " + chr(0xD800)

    create_plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="bad-note.md",
        content_text=bad_text,
    )
    append_plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=bad_text,
    )
    replace_plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=bad_text,
    )

    for result in (create_plan, append_plan, replace_plan):
        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "unsupported_file_type"

    apply_result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=bad_text,
        approval_token="icloud-drive-apply:v1:not-used",
        confirm_apply=True,
        root=root,
    )

    assert apply_result["status"] == "error"
    assert apply_result["warnings"][0]["code"] == "unsupported_file_type"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == (
        "# Synthetic Packet\nLine two\n"
    )


def test_apply_icloud_drive_change_requires_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=_approval_token(plan),
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"
    assert not (root / "Packets" / "new-note.md").exists()


def test_apply_icloud_drive_change_rejects_wrong_approval_token(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token="icloud-drive-apply:v1:not-the-plan",
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert not (root / "Packets" / "new-note.md").exists()


def test_apply_icloud_drive_change_creates_file_and_reads_back(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"].startswith("icloud:file:v1:")
    assert result["read_back"]["name"] == "new-note.md"
    assert result["read_back"]["content_chars"] == 15
    assert (root / "Packets" / "new-note.md").read_text(encoding="utf-8") == "Synthetic text."
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_creates_folder_and_reads_back_metadata(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "create_folder"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["handle"].startswith("icloud:file:v1:")
    assert result["read_back"]["name"] == "Project Notes"
    assert result["read_back"]["kind"] == "directory"
    assert "content_sha256" not in result["read_back"]
    assert (root / "Packets" / "Project Notes").is_dir()
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_creates_bounded_folder_path(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "2026", "Drafts"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "2026", "Drafts"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "create_folder_path"
    assert result["mutation_applied"] is True
    assert result["read_back"]["name"] == "Drafts"
    assert result["read_back"]["kind"] == "directory"
    assert result["read_back"]["component_count"] == 3
    assert result["read_back"]["created_count"] == 3
    assert result["read_back"]["existing_count"] == 0
    assert result["read_back"]["final_folder_verified"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in result["read_back"]
    assert (root / "Packets" / "Client" / "2026" / "Drafts").is_dir()
    assert "Client/2026/Drafts" not in str(result["read_back"])


def test_apply_icloud_drive_change_create_folder_same_token_retry_after_success(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )
    token = _approval_token(plan)

    first = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=token,
        confirm_apply=True,
        root=root,
    )
    retry = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=token,
        confirm_apply=True,
        root=root,
    )

    assert first["status"] == "ok"
    assert first["mutation_applied"] is True
    assert retry["status"] == "ok"
    assert retry["mutation_applied"] is False
    assert retry["warnings"][0]["code"] == "already_applied"


def test_apply_icloud_drive_change_create_folder_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    (root / "Packets" / "Project Notes").mkdir()
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["kind"] == "directory"


def test_apply_icloud_drive_change_create_folder_path_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Packets" / "Client" / "2026").mkdir(parents=True)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "2026"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "2026"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["existing_count"] == 2
    assert result["read_back"]["created_count"] == 0


def test_apply_icloud_drive_change_create_folder_path_same_token_retry_after_success(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        root=root,
    )
    token = _approval_token(plan)

    first = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        approval_token=token,
        confirm_apply=True,
        root=root,
    )
    retry = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        approval_token=token,
        confirm_apply=True,
        root=root,
    )

    assert first["status"] == "ok"
    assert first["mutation_applied"] is True
    assert retry["status"] == "ok"
    assert retry["mutation_applied"] is False
    assert retry["warnings"][0]["code"] == "already_applied"
    assert retry["read_back"]["existing_count"] == 2
    assert retry["read_back"]["created_count"] == 0


def test_apply_icloud_drive_change_create_folder_path_reports_partial_after_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        root=root,
    )
    original_mkdir = icloud_drive_adapter.os.mkdir

    def flaky_mkdir(path, mode=0o777, *, dir_fd=None):
        if path == "Drafts":
            raise OSError("synthetic failure")
        return original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(icloud_drive_adapter.os, "mkdir", flaky_mkdir)

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["read_back"]["created_count"] == 1
    assert result["read_back"]["existing_count"] == 0
    assert result["read_back"]["component_count"] == 2
    assert result["read_back"]["final_folder_verified"] is False
    assert result["read_back"]["raw_path_returned"] is False
    assert result["warnings"][0]["code"] == "write_error"
    assert (root / "Packets" / "Client").is_dir()
    assert not (root / "Packets" / "Client" / "Drafts").exists()


def test_apply_icloud_drive_change_create_folder_path_rejects_stale_parent_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        root=root,
    )
    stale_parent = root / "Packets"
    stale_parent.rename(root / "Old Packets")
    stale_parent.mkdir()

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert not (root / "Packets" / "Client").exists()


def test_apply_icloud_drive_change_create_folder_path_handles_parent_identity_stat_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        root=root,
    )

    expected_parent_identity = plan["preview"]["target"]["expected_parent_identity_sha256"]
    calls = 0

    def racing_parent_identity(path: Path, configured_root: Path) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return expected_parent_identity
        raise OSError("synthetic parent stat race")

    monkeypatch.setattr(
        icloud_drive_adapter,
        "_directory_identity_sha256",
        racing_parent_identity,
    )

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "parent_identity_changed"
    assert calls == 2
    assert "synthetic parent stat race" not in json.dumps(result)
    assert not (root / "Packets" / "Client").exists()


def test_apply_icloud_drive_change_create_folder_path_rejects_changed_components_token(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Drafts"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["Client", "Final"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert not (root / "Packets" / "Client").exists()


def test_apply_icloud_drive_change_create_folder_path_rejects_existing_file_component(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["review-packet.md", "Drafts"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder_path",
        parent_handle=parent_handle,
        folder_components=["review-packet.md", "Drafts"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert not (root / "Packets" / "review-packet.md" / "Drafts").exists()


def test_apply_icloud_drive_change_renames_folder_and_preserves_child(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Non Empty Folder"
    source.mkdir()
    child = source / "child.txt"
    child.write_text("child", encoding="utf-8")
    item = search_icloud_drive_metadata("Non Empty Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
    )

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "rename_folder"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["name"] == "Renamed Folder"
    assert result["read_back"]["kind"] == "directory"
    assert result["read_back"]["renamed"] is True
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert result["warnings"] == []
    assert "content_sha256" not in result["read_back"]
    assert len(result["read_back"]["metadata_sha256"]) == 64
    assert not source.exists()
    assert (root / "Packets" / "Renamed Folder" / "child.txt").read_text(encoding="utf-8") == "child"
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_rename_folder_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Empty Folder",
    )

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Empty Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["renamed"] is False
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert source.is_dir()


def test_apply_icloud_drive_change_rename_folder_rejects_stale_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
    )
    (source / "later.txt").write_text("Synthetic drift.", encoding="utf-8")

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.is_dir()
    assert not (root / "Packets" / "Renamed Folder").exists()


def test_apply_icloud_drive_change_rename_folder_allows_non_empty_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Non Empty Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    item = search_icloud_drive_metadata("Non Empty Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
    )

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    target = root / "Packets" / "Renamed Folder"
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert result["read_back"]["renamed"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert not source.exists()
    assert (target / "child.txt").is_file()


def test_apply_icloud_drive_change_non_empty_folder_probe_does_not_list_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    rename_source = root / "Packets" / "Large Rename Folder"
    move_source = root / "Packets" / "Large Move Folder"
    trash_source = root / "Packets" / "Large Trash Folder"
    move_parent = root / "Packets" / "Move Parent"
    rename_source.mkdir()
    move_source.mkdir()
    trash_source.mkdir()
    move_parent.mkdir()
    for index in range(64):
        (rename_source / f"rename-child-{index}.txt").write_text("child", encoding="utf-8")
        (move_source / f"move-child-{index}.txt").write_text("child", encoding="utf-8")
        (trash_source / f"trash-child-{index}.txt").write_text("child", encoding="utf-8")
    rename_item = search_icloud_drive_metadata("Large Rename Folder", root=root)["results"][0]
    move_item = search_icloud_drive_metadata("Large Move Folder", root=root)["results"][0]
    trash_item = search_icloud_drive_metadata("Large Trash Folder", root=root)["results"][0]
    parent_item = search_icloud_drive_metadata("Move Parent", root=root)["results"][0]
    rename_plan = plan_icloud_drive_change(
        "rename_folder",
        handle=rename_item["handle"],
        expected_current_sha256=rename_item["metadata_sha256"],
        filename="Large Renamed Folder",
    )
    move_plan = plan_icloud_drive_change(
        "move_folder",
        handle=move_item["handle"],
        parent_handle=parent_item["handle"],
        expected_current_sha256=move_item["metadata_sha256"],
        filename="Large Moved Folder",
    )
    trash_plan = plan_icloud_drive_change(
        "trash_folder",
        handle=trash_item["handle"],
        expected_current_sha256=trash_item["metadata_sha256"],
    )

    def fail_listdir(_path):
        raise AssertionError("folder emptiness probe must not materialize child names")

    monkeypatch.setattr(icloud_drive_adapter.os, "listdir", fail_listdir)

    rename_result = apply_icloud_drive_change(
        "rename_folder",
        handle=rename_item["handle"],
        expected_current_sha256=rename_item["metadata_sha256"],
        filename="Large Renamed Folder",
        approval_token=_approval_token(rename_plan),
        confirm_apply=True,
        root=root,
    )
    move_result = apply_icloud_drive_change(
        "move_folder",
        handle=move_item["handle"],
        parent_handle=parent_item["handle"],
        expected_current_sha256=move_item["metadata_sha256"],
        filename="Large Moved Folder",
        approval_token=_approval_token(move_plan),
        confirm_apply=True,
        root=root,
    )
    trash_result = apply_icloud_drive_change(
        "trash_folder",
        handle=trash_item["handle"],
        expected_current_sha256=trash_item["metadata_sha256"],
        approval_token=_approval_token(trash_plan),
        confirm_apply=True,
        root=root,
    )

    assert rename_result["status"] == "ok"
    assert rename_result["read_back"]["empty_folder_confirmed"] is False
    assert rename_result["read_back"]["non_empty_allowed"] is True
    assert move_result["status"] == "ok"
    assert move_result["read_back"]["empty_folder_confirmed"] is False
    assert move_result["read_back"]["non_empty_allowed"] is True
    assert trash_result["status"] == "ok"
    assert trash_result["read_back"]["empty_folder_confirmed"] is False
    assert trash_result["read_back"]["non_empty_allowed"] is True
    assert (root / "Packets" / "Large Renamed Folder" / "rename-child-63.txt").is_file()
    assert (move_parent / "Large Moved Folder" / "move-child-63.txt").is_file()
    with os.scandir(root / ".Trash") as entries:
        trash_entries = [root / ".Trash" / entry.name for entry in entries]
    assert len(trash_entries) == 1
    assert (trash_entries[0] / "trash-child-63.txt").is_file()


def test_apply_icloud_drive_change_rename_folder_reports_partial_if_folder_changes_during_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
    )
    original = icloud_drive_adapter._renameatx_excl_no_follow
    first_call = True

    def racing_rename(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal first_call
        if not first_call:
            original(from_fd, from_name, to_fd, to_name)
            return
        first_call = False
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        source_fd = os.open(from_name, flags, dir_fd=from_fd)
        try:
            child_fd = os.open(
                "late-child.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=source_fd,
            )
            try:
                os.write(child_fd, b"late")
            finally:
                os.close(child_fd)
        finally:
            os.close(source_fd)
        original(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", racing_rename)

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Renamed Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    warning_codes = [warning["code"] for warning in result["warnings"]]
    assert "read_back_mismatch" in warning_codes
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert not source.exists()
    assert (root / "Packets" / "Renamed Folder" / "late-child.txt").is_file()


def test_apply_icloud_drive_change_rename_folder_refuses_existing_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Folder"
    source.mkdir()
    (root / "Packets" / "Existing Folder").mkdir()
    item = search_icloud_drive_metadata("Empty Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Existing Folder",
    )

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Existing Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert source.is_dir()
    assert (root / "Packets" / "Existing Folder").is_dir()


def test_apply_icloud_drive_change_rename_folder_rejects_file_handle(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = "a" * 64
    plan = plan_icloud_drive_change(
        "rename_folder",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="Renamed Folder",
    )

    result = apply_icloud_drive_change(
        "rename_folder",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="Renamed Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert not (root / "Packets" / "Renamed Folder").exists()


def test_apply_icloud_drive_change_trashes_empty_folder_and_reads_back_absence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Trash Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Trash Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "trash_folder"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["kind"] == "directory"
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["trashed"] is True
    assert result["read_back"]["trash_path_returned"] is False
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert result["read_back"]["empty_folder_confirmed"] is True
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["warnings"] == []
    assert len(result["read_back"]["trash_name_sha256"]) == 64
    assert not source.exists()
    assert len(list((root / ".Trash").iterdir())) == 1
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_trash_folder_rejects_stale_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Trash Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Trash Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )
    (source / "later.txt").write_text("Synthetic drift.", encoding="utf-8")

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.is_dir()
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_trash_folder_allows_non_empty_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Non Empty Trash Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    item = search_icloud_drive_metadata("Non Empty Trash Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    trash_entries = list((root / ".Trash").iterdir())
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert result["read_back"]["trashed"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert not source.exists()
    assert len(trash_entries) == 1
    assert (trash_entries[0] / "child.txt").read_text(encoding="utf-8") == "Synthetic child."


def test_apply_icloud_drive_change_trash_folder_allows_apply_time_non_empty_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Trash Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Trash Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )
    original = icloud_drive_adapter._renameatx_swap_no_follow
    first_call = True

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal first_call
        if first_call:
            first_call = False
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            source_fd = os.open(from_name, flags, dir_fd=from_fd)
            try:
                child_fd = os.open(
                    "late-child.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=source_fd,
                )
                try:
                    os.write(child_fd, b"late")
                finally:
                    os.close(child_fd)
            finally:
                os.close(source_fd)
        original(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    trash_entries = list((root / ".Trash").iterdir())
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert not source.exists()
    assert len(trash_entries) == 1
    assert (trash_entries[0] / "late-child.txt").is_file()


def test_apply_icloud_drive_change_trash_folder_reports_partial_if_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Trash Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Trash Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )
    original = icloud_drive_adapter._renameatx_swap_no_follow
    call_count = 0

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal call_count
        call_count += 1
        original(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)
    monkeypatch.setattr(icloud_drive_adapter, "_safe_rmdir_created_entry", lambda *_args: False)

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "cleanup_unverified"
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["original_present"] is True
    assert source.is_dir()
    with os.scandir(root / ".Trash") as entries:
        trash_entries = [root / ".Trash" / entry.name for entry in entries]
    assert len(trash_entries) == 1


def test_apply_icloud_drive_change_trash_folder_rollback_does_not_claim_trash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Trash Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Trash Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
    )
    original_same_stat_identity = icloud_drive_adapter._same_stat_identity
    calls = 0

    def mismatch_once(left: os.stat_result, right: os.stat_result) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            return False
        return original_same_stat_identity(left, right)

    monkeypatch.setattr(icloud_drive_adapter, "_same_stat_identity", mismatch_once)

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["trashed"] is False
    assert result["read_back"]["original_present"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert source.is_dir()
    assert list((root / ".Trash").iterdir()) == []


def test_apply_icloud_drive_change_trash_folder_rejects_file_handle(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = "a" * 64
    plan = plan_icloud_drive_change(
        "trash_folder",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    result = apply_icloud_drive_change(
        "trash_folder",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_deletes_empty_folder_and_reads_back_absence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "delete_folder"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["kind"] == "directory"
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True
    assert result["read_back"]["trash_path_returned"] is False
    assert result["read_back"]["staging_path_returned"] is False
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert not (root / ".local-apple-data-delete-staging").exists()
    assert result["read_back"]["empty_folder_confirmed"] is True
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["warnings"] == []
    assert not source.exists()
    assert not (root / ".Trash").exists()
    assert search_icloud_drive_metadata("local-apple-data-delete", root=root)["result_count"] == 0
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_delete_folder_rejects_stale_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    (source / "later.txt").write_text("Synthetic drift.", encoding="utf-8")

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert source.is_dir()
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_folder_allows_non_empty_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Non Empty Delete Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    item = search_icloud_drive_metadata("Non Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert "child.txt" not in json.dumps(result)
    assert not source.exists()
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_folder_rolls_back_if_folder_races_non_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    original = icloud_drive_adapter._renameatx_excl_no_follow
    first_call = True

    def racing_stage(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal first_call
        original(from_fd, from_name, to_fd, to_name)
        if first_call:
            first_call = False
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            staged_fd = os.open(to_name, flags, dir_fd=to_fd)
            try:
                child_fd = os.open(
                    "late-child.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=staged_fd,
                )
                try:
                    os.write(child_fd, b"late")
                finally:
                    os.close(child_fd)
            finally:
                os.close(staged_fd)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", racing_stage)

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.is_dir()
    assert (source / "late-child.txt").is_file()


def test_apply_icloud_drive_change_delete_folder_reports_partial_if_race_rollback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    original = icloud_drive_adapter._renameatx_excl_no_follow
    call_count = 0

    def failing_rollback(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise OSError("synthetic rollback failure")
        original(from_fd, from_name, to_fd, to_name)
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        staged_fd = os.open(to_name, flags, dir_fd=to_fd)
        try:
            child_fd = os.open(
                "late-child.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=staged_fd,
            )
            try:
                os.write(child_fd, b"late")
            finally:
                os.close(child_fd)
        finally:
            os.close(staged_fd)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", failing_rollback)

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "rollback_failed"
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["verified_absent"] is False
    assert result["read_back"]["permanently_deleted"] is False
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["staging_path_returned"] is False
    assert not source.exists()
    assert len(_delete_staging_entries(root)) == 1
    assert search_icloud_drive_metadata("local-apple-data-delete", root=root)["result_count"] == 0


def test_apply_icloud_drive_change_delete_folder_rolls_back_after_staged_rmdir_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    original_rmdir = icloud_drive_adapter.os.rmdir
    failed_once = False

    def failing_staged_rmdir(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *args: object, dir_fd: int | None = None) -> None:
        nonlocal failed_once
        if (
            dir_fd is not None
            and isinstance(path, str)
            and path.startswith("local-apple-data-delete-")
            and not failed_once
        ):
            failed_once = True
            raise OSError(errno.EIO, "synthetic staged rmdir failure")
        original_rmdir(path, *args, dir_fd=dir_fd)

    monkeypatch.setattr(icloud_drive_adapter.os, "rmdir", failing_staged_rmdir)

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "delete_unverified"
    assert result["read_back"]["permanently_deleted"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert not source.exists()
    assert len(_delete_staging_entries(root)) == 1


def test_apply_icloud_drive_change_delete_folder_reports_partial_if_staged_rmdir_rollback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )
    original_rmdir = icloud_drive_adapter.os.rmdir
    failed_once = False

    def failing_staged_rmdir(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *args: object, dir_fd: int | None = None) -> None:
        nonlocal failed_once
        if (
            dir_fd is not None
            and isinstance(path, str)
            and path.startswith("local-apple-data-delete-")
            and not failed_once
        ):
            failed_once = True
            raise OSError(errno.EIO, "synthetic staged rmdir failure")
        original_rmdir(path, *args, dir_fd=dir_fd)

    original_rename = icloud_drive_adapter._renameatx_excl_no_follow
    rename_call_count = 0

    def failing_rollback_rename(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal rename_call_count
        rename_call_count += 1
        if rename_call_count > 1:
            raise OSError("synthetic rollback failure")
        original_rename(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter.os, "rmdir", failing_staged_rmdir)
    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", failing_rollback_rename)

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "delete_unverified"
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["verified_absent"] is False
    assert result["read_back"]["permanently_deleted"] is False
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["staging_path_returned"] is False
    assert not source.exists()
    assert len(_delete_staging_entries(root)) == 1


def test_apply_icloud_drive_change_delete_folder_rejects_file_handle(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = "a" * 64
    result = plan_icloud_drive_change(
        "delete_folder",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_folder_rejects_fabricated_handle(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = make_opaque_handle("icloud:file", "Packets/Fabricated Empty Delete Folder")
    current_sha = "a" * 64
    result = plan_icloud_drive_change(
        "delete_folder",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_not_found"
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_folder_rejects_symlink_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    symlink = root / "Packets" / "Linked Delete Folder"
    symlink.symlink_to(source, target_is_directory=True)
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    def resolve_to_symlink(handle: str, root: Path, *, max_scan_entries: int) -> Path | None:
        return symlink

    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", resolve_to_symlink)

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert source.is_dir()
    assert symlink.is_symlink()
    assert not (root / ".local-apple-data-delete-staging").exists()


def test_apply_icloud_drive_change_delete_folder_rejects_package_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Delete Folder"
    source.mkdir()
    package_child = root / "Synthetic.app" / "Nested Delete Folder"
    package_child.mkdir(parents=True)
    item = search_icloud_drive_metadata("Empty Delete Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    def resolve_to_package_child(handle: str, root: Path, *, max_scan_entries: int) -> Path | None:
        return package_child

    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", resolve_to_package_child)

    result = apply_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert package_child.is_dir()
    assert not (root / ".local-apple-data-delete-staging").exists()


@pytest.mark.parametrize(
    ("child_kind", "warning_code"),
    [
        ("hidden", "unsupported_file_type"),
        ("package", "unsupported_file_type"),
        ("symlink", "unsupported_file_type"),
        ("too_many", "folder_tree_too_large"),
    ],
)
def test_plan_icloud_drive_change_delete_folder_rejects_unsafe_or_too_large_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    child_kind: str,
    warning_code: str,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Unsafe Delete Folder"
    source.mkdir()
    if child_kind == "hidden":
        (source / ".secret.txt").write_text("hidden", encoding="utf-8")
    elif child_kind == "package":
        (source / "Blocked.app").mkdir()
    elif child_kind == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (source / "linked").symlink_to(outside, target_is_directory=True)
    else:
        (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
        monkeypatch.setattr(icloud_drive_adapter, "MAX_FOLDER_COPY_TREE_ENTRIES", 0)
    item = search_icloud_drive_metadata("Unsafe Delete Folder", root=root)["results"][0]

    result = plan_icloud_drive_change(
        "delete_folder",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == warning_code
    assert source.exists()


def test_apply_icloud_drive_change_moves_folder_and_preserves_child(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Non Empty Move Folder"
    source.mkdir()
    child = source / "child.txt"
    child.write_text("child", encoding="utf-8")
    item = search_icloud_drive_metadata("Non Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "move_folder"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["kind"] == "directory"
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["moved"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert result["warnings"] == []
    assert len(result["read_back"]["metadata_sha256"]) == 64
    assert not source.exists()
    assert (root / "Archive" / "Moved Folder" / "child.txt").read_text(encoding="utf-8") == "child"


def test_apply_icloud_drive_change_move_folder_rejects_stale_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )
    (source / "later.txt").write_text("Synthetic drift.", encoding="utf-8")

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.is_dir()
    assert not (root / "Archive" / "Moved Folder").exists()


def test_apply_icloud_drive_change_move_folder_allows_non_empty_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Non Empty Move Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    item = search_icloud_drive_metadata("Non Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    target = root / "Archive" / "Moved Folder"
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert result["read_back"]["moved"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert not source.exists()
    assert (target / "child.txt").is_file()


def test_apply_icloud_drive_change_move_folder_refuses_existing_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    (root / "Archive" / "Moved Folder").mkdir()
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert source.is_dir()


def test_apply_icloud_drive_change_move_folder_rejects_self_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_parent_handle"
    assert source.is_dir()


def test_apply_icloud_drive_change_move_folder_rejects_descendant_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Non Empty Move Folder"
    nested = source / "Nested"
    nested.mkdir(parents=True)
    item = search_icloud_drive_metadata("Non Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Nested", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_parent_handle"
    assert nested.is_dir()


def test_apply_icloud_drive_change_move_folder_reports_partial_if_folder_changes_during_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )
    original = icloud_drive_adapter._renameatx_excl_no_follow
    first_call = True

    def racing_rename(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal first_call
        if first_call:
            first_call = False
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            source_fd = os.open(from_name, flags, dir_fd=from_fd)
            try:
                child_fd = os.open(
                    "late-child.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=source_fd,
                )
                try:
                    os.write(child_fd, b"late")
                finally:
                    os.close(child_fd)
            finally:
                os.close(source_fd)
        original(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", racing_rename)

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    warning_codes = [warning["code"] for warning in result["warnings"]]
    assert "read_back_mismatch" in warning_codes
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert not source.exists()
    assert (root / "Archive" / "Moved Folder" / "late-child.txt").is_file()


def test_apply_icloud_drive_change_move_folder_reports_partial_on_identity_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )
    original = icloud_drive_adapter._renameatx_excl_no_follow

    def racing_replace(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        original(from_fd, from_name, to_fd, to_name)
        os.rmdir(to_name, dir_fd=to_fd)
        os.mkdir(to_name, mode=0o700, dir_fd=to_fd)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", racing_replace)

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert (root / "Archive" / "Moved Folder").is_dir()


def test_apply_icloud_drive_change_move_folder_reports_partial_on_readback_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Move Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Move Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
    )
    def flaky_empty(path: Path, root_arg: Path) -> bool:
        raise OSError(errno.EIO, "synthetic read-back failure")

    monkeypatch.setattr(icloud_drive_adapter, "_directory_empty_no_follow", flaky_empty)

    result = apply_icloud_drive_change(
        "move_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Moved Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert (root / "Archive" / "Moved Folder").is_dir()


def test_apply_icloud_drive_change_copies_empty_folder_and_reads_back_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "copy_folder"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["kind"] == "directory"
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["copied"] is True
    assert result["read_back"]["empty_folder_confirmed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert result["warnings"] == []
    assert len(result["read_back"]["metadata_sha256"]) == 64
    assert source.is_dir()
    assert (root / "Archive" / "Copied Folder").is_dir()


def test_apply_icloud_drive_change_copy_folder_rejects_stale_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )
    (source / "later.txt").write_text("Synthetic drift.", encoding="utf-8")

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert source.is_dir()
    assert not (root / "Archive" / "Copied Folder").exists()


def test_apply_icloud_drive_change_copy_folder_allows_non_empty_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Non Empty Copy Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    nested = source / "Nested"
    nested.mkdir()
    (nested / "nested.txt").write_text("Nested child.", encoding="utf-8")
    (source / "image.bin").write_bytes(b"\x00\x01")
    item = search_icloud_drive_metadata("Non Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    target = root / "Archive" / "Copied Folder"
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["warnings"] == []
    assert result["read_back"]["copied"] is True
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["empty_folder_confirmed"] is False
    assert result["read_back"]["non_empty_allowed"] is True
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert "child.txt" not in json.dumps(result)
    assert "nested.txt" not in json.dumps(result)
    assert "image.bin" not in json.dumps(result)
    assert source.is_dir()
    assert (target / "child.txt").read_text(encoding="utf-8") == "Synthetic child."
    assert (target / "Nested" / "nested.txt").read_text(encoding="utf-8") == "Nested child."
    assert (target / "image.bin").read_bytes() == b"\x00\x01"


def test_copy_folder_tree_and_cleanup_do_not_use_unbounded_os_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target_parent = root / "Archive"
    target_parent.mkdir()
    source = root / "Packets" / "Walkless Copy Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    nested = source / "Nested"
    nested.mkdir()
    (nested / "nested.txt").write_text("Nested child.", encoding="utf-8")
    source_stat, entries = icloud_drive_adapter._folder_copy_tree_snapshot(
        source,
        root,
        max_entries=icloud_drive_adapter.MAX_FOLDER_COPY_TREE_ENTRIES,
    )
    expected_metadata_sha = icloud_drive_adapter._directory_metadata_sha256_from_stat(source, root, source_stat)
    expected_tree_sha = icloud_drive_adapter._folder_copy_tree_sha256(source, root, source_stat, entries)

    def fail_walk(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("folder copy must not use os.walk")

    monkeypatch.setattr(icloud_drive_adapter.os, "walk", fail_walk)

    icloud_drive_adapter._copy_folder_tree(
        source,
        target_parent,
        "Copied Folder",
        expected_metadata_sha=expected_metadata_sha,
        expected_tree_sha=expected_tree_sha,
        root=root,
    )

    target = target_parent / "Copied Folder"
    assert (target / "child.txt").read_text(encoding="utf-8") == "Synthetic child."
    assert (target / "Nested" / "nested.txt").read_text(encoding="utf-8") == "Nested child."
    created_root_stat = target.lstat()
    created_entries = {
        "Nested": ("directory", (target / "Nested").lstat()),
        "child.txt": ("file", (target / "child.txt").lstat()),
        "Nested/nested.txt": ("file", (target / "Nested" / "nested.txt").lstat()),
    }
    assert icloud_drive_adapter._created_folder_tree_matches(target, created_root_stat, created_entries) is True
    assert (
        icloud_drive_adapter._safe_remove_created_folder_tree(
            target,
            created_root_stat,
            created_entries,
            root=root,
        )
        is True
    )
    assert not target.exists()


def test_copy_folder_tree_cleanup_refuses_unexpected_target_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Archive" / "Copied Folder"
    target.mkdir(parents=True)
    child = target / "child.txt"
    child.write_text("Synthetic child.", encoding="utf-8")
    unexpected = target / "unexpected.txt"
    unexpected.write_text("Synthetic unexpected.", encoding="utf-8")
    created_root_stat = target.lstat()
    created_entries = {"child.txt": ("file", child.lstat())}

    def fail_walk(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("folder cleanup must not use os.walk")

    monkeypatch.setattr(icloud_drive_adapter.os, "walk", fail_walk)

    assert icloud_drive_adapter._created_folder_tree_matches(target, created_root_stat, created_entries) is False
    assert (
        icloud_drive_adapter._safe_remove_created_folder_tree(
            target,
            created_root_stat,
            created_entries,
            root=root,
        )
        is False
    )
    assert child.is_file()
    assert unexpected.is_file()


def test_folder_copy_tree_snapshot_sorts_bounded_names_without_builtin_sorted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Bounded Copy Folder"
    source.mkdir()
    (source / "b.txt").write_text("b", encoding="utf-8")
    (source / "a.txt").write_text("a", encoding="utf-8")

    def fail_sorted(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("folder copy snapshot must not materialize scandir with sorted()")

    monkeypatch.setattr(builtins, "sorted", fail_sorted)

    _source_stat, entries = icloud_drive_adapter._folder_copy_tree_snapshot(
        source,
        root,
        max_entries=icloud_drive_adapter.MAX_FOLDER_COPY_TREE_ENTRIES,
    )

    assert [entry["relative_path"] for entry in entries] == ["a.txt", "b.txt"]


def test_apply_icloud_drive_change_copy_folder_rejects_swapped_child_directory_before_file_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Nested Copy Folder"
    nested = source / "Nested"
    nested.mkdir(parents=True)
    (nested / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    target = root / "Archive" / "Copied Folder"
    item = search_icloud_drive_metadata("Nested Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )
    original_open = icloud_drive_adapter._open_resolved_directory_no_follow
    swapped = False

    def swap_nested_target_parent(path: Path, root_arg: Path, **kwargs: object) -> int:
        nonlocal swapped
        if not swapped and path == target / "Nested":
            swapped = True
            path.rmdir()
            path.mkdir()
        return original_open(path, root_arg, **kwargs)

    monkeypatch.setattr(icloud_drive_adapter, "_open_resolved_directory_no_follow", swap_nested_target_parent)

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert swapped is True
    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "cleanup_unverified"
    assert target.is_dir()
    assert (target / "Nested").is_dir()
    assert not (target / "Nested" / "child.txt").exists()


def test_apply_icloud_drive_change_copy_folder_refuses_existing_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    (root / "Archive" / "Copied Folder").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert source.is_dir()


def test_apply_icloud_drive_change_copy_folder_rejects_self_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Empty Copy Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_parent_handle"
    assert source.is_dir()


def test_apply_icloud_drive_change_copy_folder_rejects_descendant_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "Non Empty Copy Folder"
    nested = source / "Nested"
    nested.mkdir(parents=True)
    item = search_icloud_drive_metadata("Non Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Nested", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_parent_handle"
    assert not (nested / "Copied Folder").exists()


@pytest.mark.parametrize(
    ("child_kind", "warning_code"),
    [
        ("hidden", "unsupported_file_type"),
        ("package", "unsupported_file_type"),
        ("symlink", "unsupported_file_type"),
        ("too_many", "folder_tree_too_large"),
    ],
)
def test_plan_icloud_drive_change_copy_folder_rejects_unsafe_or_too_large_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    child_kind: str,
    warning_code: str,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Unsafe Copy Folder"
    source.mkdir()
    if child_kind == "hidden":
        (source / ".secret.txt").write_text("hidden", encoding="utf-8")
    elif child_kind == "package":
        (source / "Blocked.app").mkdir()
    elif child_kind == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (source / "linked").symlink_to(outside, target_is_directory=True)
    else:
        (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
        monkeypatch.setattr(icloud_drive_adapter, "MAX_FOLDER_COPY_TREE_ENTRIES", 0)
    item = search_icloud_drive_metadata("Unsafe Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    result = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == warning_code
    assert not (root / "Archive" / "Copied Folder").exists()


def test_apply_icloud_drive_change_copy_folder_rolls_back_if_source_races_after_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    target = root / "Archive" / "Copied Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )
    original_copy = icloud_drive_adapter._copy_folder_file_entry

    def racing_copy(source_path: Path, target_path: Path, **kwargs: object) -> os.stat_result:
        copied_stat = original_copy(source_path, target_path, **kwargs)
        (source / "late-child.txt").write_text("late", encoding="utf-8")
        return copied_stat

    monkeypatch.setattr(icloud_drive_adapter, "_copy_folder_file_entry", racing_copy)

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert [warning["code"] for warning in result["warnings"]] == ["current_metadata_changed"]
    assert source.is_dir()
    assert (source / "late-child.txt").is_file()
    assert not target.exists()


def test_apply_icloud_drive_change_copy_folder_reports_partial_if_race_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    target = root / "Archive" / "Copied Folder"
    source.mkdir()
    (source / "child.txt").write_text("Synthetic child.", encoding="utf-8")
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )
    original_copy = icloud_drive_adapter._copy_folder_file_entry

    def racing_copy(source_path: Path, target_path: Path, **kwargs: object) -> os.stat_result:
        copied_stat = original_copy(source_path, target_path, **kwargs)
        (source / "late-child.txt").write_text("late", encoding="utf-8")
        return copied_stat

    monkeypatch.setattr(icloud_drive_adapter, "_copy_folder_file_entry", racing_copy)
    monkeypatch.setattr(icloud_drive_adapter, "_safe_remove_created_folder_tree", lambda *_args, **_kwargs: False)

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert [warning["code"] for warning in result["warnings"]] == ["cleanup_unverified"]
    assert result["read_back"]["copied"] is False
    assert result["read_back"]["target_identity_verified"] is False
    assert "handle" not in result["read_back"]
    assert "metadata_sha256" not in result["read_back"]
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert source.is_dir()
    assert (source / "late-child.txt").is_file()
    assert target.is_dir()


def test_apply_icloud_drive_change_copy_folder_reports_error_after_cleaned_target_identity_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    source = root / "Packets" / "Empty Copy Folder"
    target = root / "Archive" / "Copied Folder"
    source.mkdir()
    item = search_icloud_drive_metadata("Empty Copy Folder", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        root=root,
    )
    match_calls = 0

    def fail_first_tree_match(*_args: object) -> bool:
        nonlocal match_calls
        match_calls += 1
        return match_calls != 1

    monkeypatch.setattr(icloud_drive_adapter, "_created_folder_tree_matches", fail_first_tree_match)

    result = apply_icloud_drive_change(
        "copy_folder",
        handle=item["handle"],
        parent_handle=parent_handle,
        expected_current_sha256=item["metadata_sha256"],
        filename="Copied Folder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"] is None
    assert not target.exists()


def test_apply_icloud_drive_change_create_folder_rejects_existing_file(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    (root / "Packets" / "Project Notes").write_text("Synthetic file.", encoding="utf-8")
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert (root / "Packets" / "Project Notes").is_file()


def test_apply_icloud_drive_change_create_folder_rejects_matching_target_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "Packets" / "Project Notes").symlink_to(outside, target_is_directory=True)
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert outside.exists()


def test_apply_icloud_drive_change_create_rejects_parent_symlink_after_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        root=root,
    )
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    symlink_parent = root / "Packets-link"
    symlink_parent.symlink_to(outside_dir, target_is_directory=True)
    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", lambda *args, **kwargs: symlink_parent)

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_parent_not_found"
    assert not (outside_dir / "new-note.md").exists()


def test_apply_icloud_drive_change_create_folder_rejects_parent_symlink_after_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    symlink_parent = root / "Packets-link"
    symlink_parent.symlink_to(outside_dir, target_is_directory=True)
    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", lambda *args, **kwargs: symlink_parent)

    result = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_parent_not_found"
    assert not (outside_dir / "Project Notes").exists()


def test_apply_icloud_drive_change_create_folder_reports_read_back_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        root=root,
    )
    original_create_directory = icloud_drive_adapter.os.mkdir

    def bad_mkdir(name: str, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        original_create_directory(name, mode, dir_fd=dir_fd)
        os.rmdir(name, dir_fd=dir_fd)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dir_fd)
        os.close(fd)

    monkeypatch.setattr(icloud_drive_adapter.os, "mkdir", bad_mkdir)

    result = apply_icloud_drive_change(
        "create_folder",
        parent_handle=parent_handle,
        filename="Project Notes",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["kind"] == "file"


def test_apply_icloud_drive_change_create_rejects_matching_target_symlink(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    outside = tmp_path / "outside.md"
    outside.write_text("Synthetic text.", encoding="utf-8")
    (root / "Packets" / "new-note.md").symlink_to(outside)
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert outside.read_text(encoding="utf-8") == "Synthetic text."


def test_apply_icloud_drive_change_appends_text_and_reads_back(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    append_text = "\nAppended synthetic note.\n"
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=append_text,
    )

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=append_text,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    expected = "# Synthetic Packet\nLine two\n\nAppended synthetic note.\n"
    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "append_text"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"].startswith("icloud:file:v1:")
    assert result["read_back"]["name"] == "review-packet.md"
    assert result["read_back"]["content_chars"] == len(expected)
    assert result["read_back"]["content_sha256"] == _content_sha(expected)
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == expected
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_append_text_preserves_existing_line_endings(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "crlf-packet.md"
    target.write_bytes(b"A\r\nB\r\n")
    handle = search_icloud_drive_metadata("crlf", root=root)["results"][0]["handle"]
    current_sha = _content_sha("A\r\nB\r\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="C\r\n",
    )

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="C\r\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert target.read_bytes() == b"A\r\nB\r\nC\n"
    assert result["read_back"]["content_sha256"] == _content_sha("A\nB\nC\n")


def test_apply_icloud_drive_change_replaces_text_and_reads_back(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    replacement = "# Replaced Packet\nLine three\n"
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
    )

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "replace_text"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"].startswith("icloud:file:v1:")
    assert result["read_back"]["name"] == "review-packet.md"
    assert result["read_back"]["content_chars"] == len(replacement)
    assert result["read_back"]["content_sha256"] == _content_sha(replacement)
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == replacement
    assert "content_text" not in result["read_back"]
    assert "Packets" not in str(result["read_back"])


def test_apply_icloud_drive_change_trashes_text_and_reads_back_absence(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "trash_text"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is True
    assert result["read_back"]["handle"] == handle
    assert result["read_back"]["name"] == "review-packet.md"
    assert result["read_back"]["content_sha256"] == current_sha
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["trashed"] is True
    assert result["read_back"]["trash_path_returned"] is False
    assert "content_text" not in result["read_back"]
    assert "Packets" not in str(result["read_back"])
    assert not target.exists()
    trash_files = list((root / ".Trash").iterdir())
    assert len(trash_files) == 1
    assert trash_files[0].read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert get_icloud_drive_metadata(handle, root=root)["status"] == "not_found"


def test_apply_icloud_drive_change_deletes_text_and_reads_back_absence(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["operation"] == "delete_text"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is True
    assert result["read_back"]["handle"] == handle
    assert result["read_back"]["name"] == "review-packet.md"
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["permanently_deleted"] is True
    assert result["read_back"]["trash_path_returned"] is False
    assert result["read_back"]["staging_path_returned"] is False
    assert result["read_back"]["content_text_returned"] is False
    assert result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in result["read_back"]
    assert "content_text" not in result["read_back"]
    assert "Packets" not in str(result["read_back"])
    assert not target.exists()
    assert not (root / ".Trash").exists()
    assert _delete_staging_entries(root) == []
    assert get_icloud_drive_metadata(handle, root=root)["status"] == "not_found"


def test_apply_icloud_drive_change_renames_text_and_reads_back_absence(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )

    result = apply_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "rename_text"
    assert result["mutation_applied"] is True
    assert result["read_back"]["renamed"] is True
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["name"] == "review-renamed.md"
    assert result["read_back"]["content_sha256"] == current_sha
    assert "content_text" not in result["read_back"]
    assert "Packets" not in str(result["read_back"])
    assert not (root / "Packets" / "review-packet.md").exists()
    assert (root / "Packets" / "review-renamed.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert get_icloud_drive_metadata(handle, root=root)["status"] == "not_found"


def test_apply_icloud_drive_change_copies_text_and_preserves_source(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )

    result = apply_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "copy_text"
    assert result["mutation_applied"] is True
    assert result["read_back"]["copied"] is True
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["content_sha256"] == current_sha
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert (root / "Packets" / "review-copy.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"


def test_apply_icloud_drive_change_moves_text_to_exact_parent(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        expected_current_sha256=current_sha,
        parent_handle=parent_handle,
    )

    result = apply_icloud_drive_change(
        "move_text",
        handle=handle,
        expected_current_sha256=current_sha,
        parent_handle=parent_handle,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "move_text"
    assert result["mutation_applied"] is True
    assert result["read_back"]["moved"] is True
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["content_sha256"] == current_sha
    assert not (root / "Packets" / "review-packet.md").exists()
    assert (root / "Archive" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert get_icloud_drive_metadata(handle, root=root)["status"] == "not_found"


def test_apply_icloud_drive_change_renames_file_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-renamed.bin",
    )

    result = apply_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-renamed.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "rename_file"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["renamed"] is True
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["name"] == "image-renamed.bin"
    assert result["read_back"]["content_type"] == "regular_file"
    assert result["read_back"]["content_hash_returned"] is False
    assert result["read_back"]["content_text_returned"] is False
    assert "content_sha256" not in result["read_back"]
    assert "content_text" not in result["read_back"]
    assert len(result["read_back"]["metadata_sha256"]) == 64
    assert not (root / "Packets" / "image.bin").exists()
    assert (root / "Packets" / "image-renamed.bin").read_bytes() == b"\x00\x01"
    assert get_icloud_drive_metadata(item["handle"], root=root)["status"] == "not_found"


def test_apply_icloud_drive_change_copies_file_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
    )

    result = apply_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "copy_file"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["copied"] is True
    assert result["read_back"]["source_present"] is True
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in result["read_back"]
    assert (root / "Packets" / "image.bin").read_bytes() == b"\x00\x01"
    assert (root / "Packets" / "image-copy.bin").read_bytes() == b"\x00\x01"


def test_apply_icloud_drive_change_moves_file_to_exact_parent_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        parent_handle=parent_handle,
        filename="image-moved.bin",
    )

    result = apply_icloud_drive_change(
        "move_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        parent_handle=parent_handle,
        filename="image-moved.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "move_file"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["read_back"]["moved"] is True
    assert result["read_back"]["source_present"] is False
    assert result["read_back"]["target_present"] is True
    assert result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in result["read_back"]
    assert not (root / "Packets" / "image.bin").exists()
    assert (root / "Archive" / "image-moved.bin").read_bytes() == b"\x00\x01"
    assert get_icloud_drive_metadata(item["handle"], root=root)["status"] == "not_found"


def test_apply_icloud_drive_change_append_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
    )
    (root / "Packets" / "review-packet.md").write_text(
        "Changed synthetic content.\n",
        encoding="utf-8",
    )

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is True
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "Changed synthetic content.\n"


def test_apply_icloud_drive_change_replace_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replacement\n",
    )
    (root / "Packets" / "review-packet.md").write_text(
        "Changed synthetic content.\n",
        encoding="utf-8",
    )

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replacement\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is True
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "Changed synthetic content.\n"


def test_apply_icloud_drive_change_trash_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    target.write_text("Changed synthetic content.\n", encoding="utf-8")

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is True
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_delete_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )
    target.write_text("Changed synthetic content.\n", encoding="utf-8")

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_delete_text_refuses_content_drift_after_identity_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    original_text = "# Synthetic Packet\nLine two\n"
    current_sha = _content_sha(original_text)
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )
    approved_identity = plan["preview"]["target"]["expected_file_identity_sha256"]

    def stable_identity(*args: object, **kwargs: object) -> str:
        return approved_identity

    monkeypatch.setattr(
        icloud_drive_adapter,
        "_delete_text_identity_sha256_from_stat",
        stable_identity,
    )
    target.write_text("Changed synthetic content.\n", encoding="utf-8")

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is True
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_delete_text_rejects_recreated_same_content_with_stale_token(
    tmp_path: Path,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    original_text = "# Synthetic Packet\nLine two\n"
    current_sha = _content_sha(original_text)
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    first = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )
    assert first["status"] == "ok"
    assert not target.exists()
    target.write_text(original_text, encoding="utf-8")

    replay = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert replay["status"] == "error"
    assert replay["mutation_applied"] is False
    assert replay["privacy"]["content_inspected"] is False
    assert replay["warnings"][0]["code"] == "invalid_approval_token"
    assert target.read_text(encoding="utf-8") == original_text
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_delete_text_rejects_same_content_identity_race_after_token_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    original_text = "# Synthetic Packet\nLine two\n"
    current_sha = _content_sha(original_text)
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )
    original_resolve = icloud_drive_adapter._resolve_handle
    replaced_once = False
    resolve_calls = 0

    def replacing_resolve(*args: object, **kwargs: object) -> object:
        nonlocal replaced_once, resolve_calls
        resolved = original_resolve(*args, **kwargs)
        resolve_calls += 1
        if not replaced_once and resolve_calls >= 2 and isinstance(resolved, Path):
            replaced_once = True
            target.unlink()
            target.write_text(original_text, encoding="utf-8")
        return resolved

    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", replacing_resolve)

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert target.read_text(encoding="utf-8") == original_text
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_delete_text_rolls_back_after_staged_unlink_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )
    original_unlink = icloud_drive_adapter.os.unlink
    failed_once = False

    def failing_staged_unlink(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *args: object, dir_fd: int | None = None) -> None:
        nonlocal failed_once
        if (
            dir_fd is not None
            and isinstance(path, str)
            and path.startswith("local-apple-data-delete-")
            and not failed_once
        ):
            failed_once = True
            raise OSError(errno.EIO, "synthetic staged unlink failure")
        original_unlink(path, *args, dir_fd=dir_fd)

    monkeypatch.setattr(icloud_drive_adapter.os, "unlink", failing_staged_unlink)

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "delete_error"
    assert target.read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_delete_text_reports_partial_if_staged_unlink_rollback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )
    original_unlink = icloud_drive_adapter.os.unlink
    failed_once = False

    def failing_staged_unlink(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *args: object, dir_fd: int | None = None) -> None:
        nonlocal failed_once
        if (
            dir_fd is not None
            and isinstance(path, str)
            and path.startswith("local-apple-data-delete-")
            and not failed_once
        ):
            failed_once = True
            raise OSError(errno.EIO, "synthetic staged unlink failure")
        original_unlink(path, *args, dir_fd=dir_fd)

    original_rename = icloud_drive_adapter._renameatx_excl_no_follow
    rename_call_count = 0

    def failing_rollback_rename(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal rename_call_count
        rename_call_count += 1
        if rename_call_count > 1:
            raise OSError("synthetic rollback failure")
        original_rename(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter.os, "unlink", failing_staged_unlink)
    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_excl_no_follow", failing_rollback_rename)

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "rollback_failed"
    assert result["read_back"]["original_present"] is False
    assert result["read_back"]["verified_absent"] is False
    assert result["read_back"]["permanently_deleted"] is False
    assert result["read_back"]["staging_path_returned"] is False
    assert not target.exists()
    staging_entries = _delete_staging_entries(root)
    assert len(staging_entries) == 1
    assert target.stem not in staging_entries[0].name
    assert target.suffix not in staging_entries[0].name


def test_apply_icloud_drive_change_rename_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    target.write_text("Changed synthetic content.\n", encoding="utf-8")

    result = apply_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"
    assert not (root / "Packets" / "review-renamed.md").exists()


def test_apply_icloud_drive_change_copy_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    copy_target = root / "Packets" / "review-copy.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )
    target.write_text("Changed synthetic content.\n", encoding="utf-8")

    result = apply_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"
    assert not copy_target.exists()


def test_apply_icloud_drive_change_move_text_refuses_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    archive = root / "Archive"
    archive.mkdir()
    target = root / "Packets" / "review-packet.md"
    move_target = archive / "review-moved.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
    )
    target.write_text("Changed synthetic content.\n", encoding="utf-8")

    result = apply_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"
    assert not move_target.exists()


def test_apply_icloud_drive_change_copy_file_refuses_metadata_drift(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "image.bin"
    copy_target = root / "Packets" / "image-copy.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
    )
    target.write_bytes(b"\x02\x03\x04")

    result = apply_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert target.read_bytes() == b"\x02\x03\x04"
    assert not copy_target.exists()


def test_apply_icloud_drive_change_rename_file_rechecks_after_swap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "image.bin"
    target = root / "Packets" / "image-renamed.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-renamed.bin",
    )
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            source.write_bytes(b"\x00\xff")
        swaps += 1
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)

    result = apply_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-renamed.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.read_bytes() == b"\x00\xff"
    assert not target.exists()


def test_apply_icloud_drive_change_move_file_rechecks_after_swap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    archive = root / "Archive"
    archive.mkdir()
    source = root / "Packets" / "image.bin"
    target = archive / "image-moved.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    plan = plan_icloud_drive_change(
        "move_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        parent_handle=parent_handle,
        filename="image-moved.bin",
    )
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            source.write_bytes(b"\x00\xff")
        swaps += 1
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)

    result = apply_icloud_drive_change(
        "move_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        parent_handle=parent_handle,
        filename="image-moved.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.read_bytes() == b"\x00\xff"
    assert not target.exists()


def test_apply_icloud_drive_change_copy_file_rechecks_target_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "image.bin"
    target = root / "Packets" / "image-copy.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
    )
    original_write_all = icloud_drive_adapter._write_all
    writes = 0

    def racing_write(fd: int, data: bytes) -> None:
        nonlocal writes
        original_write_all(fd, data)
        if writes == 0:
            os.lseek(fd, 0, os.SEEK_SET)
            original_write_all(fd, b"\xff" + data[1:])
        writes += 1

    monkeypatch.setattr(icloud_drive_adapter, "_write_all", racing_write)

    result = apply_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert source.read_bytes() == b"\x00\x01"
    assert target.read_bytes() == b"\xff\x01"
    assert result["read_back"]["content_hash_returned"] is False
    assert "content_sha256" not in result["read_back"]


def test_apply_icloud_drive_change_copy_file_streams_without_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "large.bin"
    source.write_bytes(b"a" * (icloud_drive_adapter.REGULAR_FILE_COPY_CHUNK_BYTES + 17))
    item = search_icloud_drive_metadata("large", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="large-copy.bin",
    )

    def fail_full_read(*args, **kwargs):
        raise AssertionError("_read_file_bytes_no_follow_at must not be used for regular-file copy")

    monkeypatch.setattr(icloud_drive_adapter, "_read_file_bytes_no_follow_at", fail_full_read)

    result = apply_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="large-copy.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert (root / "Packets" / "large-copy.bin").read_bytes() == source.read_bytes()


def test_apply_icloud_drive_change_copy_file_rechecks_source_after_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "image.bin"
    target = root / "Packets" / "image-copy.bin"
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
    )
    original_write_all = icloud_drive_adapter._write_all
    writes = 0

    def racing_write(fd: int, data: bytes) -> None:
        nonlocal writes
        original_write_all(fd, data)
        if writes == 0:
            source.write_bytes(b"\x00\xff")
        writes += 1

    monkeypatch.setattr(icloud_drive_adapter, "_write_all", racing_write)

    result = apply_icloud_drive_change(
        "copy_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="image-copy.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_metadata_changed"
    assert source.read_bytes() == b"\x00\xff"
    assert not target.exists()


def test_apply_icloud_drive_change_file_operations_reject_text_source(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    item = search_icloud_drive_metadata("review", root=root)["results"][0]
    plan = plan_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="review-renamed.bin",
    )

    result = apply_icloud_drive_change(
        "rename_file",
        handle=item["handle"],
        expected_current_sha256=item["metadata_sha256"],
        filename="review-renamed.bin",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert (root / "Packets" / "review-packet.md").exists()
    assert not (root / "Packets" / "review-renamed.bin").exists()


def test_apply_icloud_drive_change_rename_text_rechecks_after_swap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "review-packet.md"
    target = root / "Packets" / "review-renamed.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            source.write_text("Concurrent rewrite before swap.\n", encoding="utf-8")
        swaps += 1
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)

    result = apply_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert source.read_text(encoding="utf-8") == "Concurrent rewrite before swap.\n"
    assert not target.exists()


def test_apply_icloud_drive_change_copy_text_rechecks_source_after_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    source = root / "Packets" / "review-packet.md"
    target = root / "Packets" / "review-copy.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )
    original_write_all = icloud_drive_adapter._write_all
    writes = 0

    def racing_write(fd: int, data: bytes) -> None:
        nonlocal writes
        if writes == 0:
            source.write_text("Concurrent rewrite before copy success.\n", encoding="utf-8")
        writes += 1
        original_write_all(fd, data)

    monkeypatch.setattr(icloud_drive_adapter, "_write_all", racing_write)

    result = apply_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert source.read_text(encoding="utf-8") == "Concurrent rewrite before copy success.\n"
    assert not target.exists()


def test_apply_icloud_drive_change_move_text_rechecks_after_swap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    archive = root / "Archive"
    archive.mkdir()
    source = root / "Packets" / "review-packet.md"
    target = archive / "review-moved.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
    )
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            source.write_text("Concurrent rewrite before swap.\n", encoding="utf-8")
        swaps += 1
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)

    result = apply_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert source.read_text(encoding="utf-8") == "Concurrent rewrite before swap.\n"
    assert not target.exists()


def test_apply_icloud_drive_change_copy_text_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    (root / "Packets" / "review-copy.md").write_text("Existing target.\n", encoding="utf-8")
    plan = plan_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )

    result = apply_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert (root / "Packets" / "review-copy.md").read_text(encoding="utf-8") == "Existing target.\n"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"


def test_apply_icloud_drive_change_rename_text_refuses_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Packets" / "review-renamed.md").write_text("Existing target.\n", encoding="utf-8")
    handle = search_icloud_drive_metadata("review-packet", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )

    result = apply_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert (root / "Packets" / "review-renamed.md").read_text(encoding="utf-8") == "Existing target.\n"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"


def test_apply_icloud_drive_change_move_text_refuses_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    (root / "Archive" / "occupied.md").write_text("Existing target.\n", encoding="utf-8")
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        expected_current_sha256=current_sha,
        parent_handle=parent_handle,
        filename="occupied.md",
    )

    result = apply_icloud_drive_change(
        "move_text",
        handle=handle,
        expected_current_sha256=current_sha,
        parent_handle=parent_handle,
        filename="occupied.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "target_exists"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert (root / "Archive" / "occupied.md").read_text(encoding="utf-8") == "Existing target.\n"


def test_apply_icloud_drive_change_rename_copy_move_file_refuses_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    (root / "Packets" / "occupied.bin").write_bytes(b"existing")
    (root / "Archive" / "occupied.bin").write_bytes(b"existing")
    item = search_icloud_drive_metadata("image", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    attempts = [
        ("rename_file", {"filename": "occupied.bin"}),
        ("copy_file", {"filename": "occupied.bin"}),
        ("move_file", {"parent_handle": parent_handle, "filename": "occupied.bin"}),
    ]
    for operation, kwargs in attempts:
        plan = plan_icloud_drive_change(
            operation,
            handle=item["handle"],
            expected_current_sha256=item["metadata_sha256"],
            **kwargs,
        )

        result = apply_icloud_drive_change(
            operation,
            handle=item["handle"],
            expected_current_sha256=item["metadata_sha256"],
            approval_token=_approval_token(plan),
            confirm_apply=True,
            root=root,
            **kwargs,
        )

        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == "target_exists"
        assert (root / "Packets" / "image.bin").read_bytes() == b"\x00\x01"


def test_apply_icloud_drive_change_rename_copy_move_refuse_symlink_targets(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("Outside target.\n", encoding="utf-8")
    (root / "Packets" / "review-link.md").symlink_to(outside)
    (root / "Archive" / "review-link.md").symlink_to(outside)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    attempts = [
        ("rename_text", {"filename": "review-link.md"}),
        ("copy_text", {"filename": "review-link.md"}),
        ("move_text", {"parent_handle": parent_handle, "filename": "review-link.md"}),
    ]
    for operation, kwargs in attempts:
        plan = plan_icloud_drive_change(
            operation,
            handle=handle,
            expected_current_sha256=current_sha,
            **kwargs,
        )

        result = apply_icloud_drive_change(
            operation,
            handle=handle,
            expected_current_sha256=current_sha,
            approval_token=_approval_token(plan),
            confirm_apply=True,
            root=root,
            **kwargs,
        )

        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == "target_exists"
        assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
        assert (root / "Packets" / "review-link.md").is_symlink()
        assert (root / "Archive" / "review-link.md").is_symlink()


def test_apply_icloud_drive_change_rename_copy_move_file_refuse_symlink_targets(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (root / "Packets" / "image-link.bin").symlink_to(outside)
    (root / "Archive" / "image-link.bin").symlink_to(outside)
    item = search_icloud_drive_metadata("image.bin", root=root)["results"][0]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]

    attempts = [
        ("rename_file", {"filename": "image-link.bin"}),
        ("copy_file", {"filename": "image-link.bin"}),
        ("move_file", {"parent_handle": parent_handle, "filename": "image-link.bin"}),
    ]
    for operation, kwargs in attempts:
        plan = plan_icloud_drive_change(
            operation,
            handle=item["handle"],
            expected_current_sha256=item["metadata_sha256"],
            **kwargs,
        )

        result = apply_icloud_drive_change(
            operation,
            handle=item["handle"],
            expected_current_sha256=item["metadata_sha256"],
            approval_token=_approval_token(plan),
            confirm_apply=True,
            root=root,
            **kwargs,
        )

        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == "target_exists"
        assert (root / "Packets" / "image.bin").read_bytes() == b"\x00\x01"
        assert (root / "Packets" / "image-link.bin").is_symlink()
        assert (root / "Archive" / "image-link.bin").is_symlink()


def test_apply_icloud_drive_change_rename_copy_move_file_refuse_package_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    (root / "Archive").mkdir()
    package = root / "Draft.pages"
    package.mkdir()
    member = package / "image.bin"
    member.write_bytes(b"\x00\x02")
    handle = make_opaque_handle("icloud:file", "Draft.pages/image.bin")
    metadata_sha = icloud_drive_adapter._file_metadata_sha256(member, root)
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    original_resolve_handle = icloud_drive_adapter._resolve_handle

    def resolve_package_member(candidate: str, root: Path, *, max_scan_entries: int) -> Path | None:
        if candidate == handle:
            return member
        return original_resolve_handle(candidate, root, max_scan_entries=max_scan_entries)

    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", resolve_package_member)

    attempts = [
        ("rename_file", {"filename": "image-renamed.bin"}, root / "Draft.pages" / "image-renamed.bin"),
        ("copy_file", {"filename": "image-copy.bin"}, root / "Draft.pages" / "image-copy.bin"),
        ("move_file", {"parent_handle": parent_handle, "filename": "image-moved.bin"}, root / "Archive" / "image-moved.bin"),
        ("trash_file", {}, root / ".Trash"),
        ("delete_file", {}, root / ".local-apple-data-delete-staging"),
    ]
    for operation, kwargs, target in attempts:
        plan = plan_icloud_drive_change(
            operation,
            handle=handle,
            expected_current_sha256=metadata_sha,
            **kwargs,
        )

        result = apply_icloud_drive_change(
            operation,
            handle=handle,
            expected_current_sha256=metadata_sha,
            approval_token=_approval_token(plan),
            confirm_apply=True,
            root=root,
            **kwargs,
        )

        assert result["status"] == "error"
        assert result["mutation_applied"] is False
        assert result["warnings"][0]["code"] == "unsupported_file_type"
        assert member.read_bytes() == b"\x00\x02"
        assert not target.exists()


def test_apply_icloud_drive_change_copy_cleanup_preserves_racing_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
    )
    target = root / "Packets" / "review-copy.md"
    outside = tmp_path / "outside.md"
    outside.write_text("Racing replacement.\n", encoding="utf-8")
    original_write_all = icloud_drive_adapter._write_all

    def racing_write(fd: int, data: bytes) -> None:
        original_write_all(fd, b"partial")
        target.unlink()
        target.symlink_to(outside)
        raise OSError(errno.EIO, "synthetic write failure")

    monkeypatch.setattr(icloud_drive_adapter, "_write_all", racing_write)

    result = apply_icloud_drive_change(
        "copy_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-copy.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert {warning["code"] for warning in result["warnings"]} >= {
        "cleanup_unverified",
        "read_back_mismatch",
    }
    assert target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "Racing replacement.\n"
    assert (root / "Packets" / "review-packet.md").read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"


def test_apply_icloud_drive_change_rename_reports_partial_when_rollback_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    source = root / "Packets" / "review-packet.md"
    target = root / "Packets" / "review-renamed.md"
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def fail_rollback_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            source.write_text("Changed synthetic content.\n", encoding="utf-8")
        swaps += 1
        if swaps == 2:
            raise OSError(errno.EEXIST, "synthetic rollback failure")
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", fail_rollback_swap)

    result = apply_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert source.exists()
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"


def test_apply_icloud_drive_change_move_reports_partial_when_rollback_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    archive = root / "Archive"
    archive.mkdir()
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
    )
    source = root / "Packets" / "review-packet.md"
    target = archive / "review-moved.md"
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def fail_rollback_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            source.write_text("Changed synthetic content.\n", encoding="utf-8")
        swaps += 1
        if swaps == 2:
            raise OSError(errno.EEXIST, "synthetic rollback failure")
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", fail_rollback_swap)

    result = apply_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert source.exists()
    assert target.read_text(encoding="utf-8") == "Changed synthetic content.\n"


def test_apply_icloud_drive_change_rename_preserves_verified_target_when_source_cleanup_races(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
    )
    source = root / "Packets" / "review-packet.md"
    target = root / "Packets" / "review-renamed.md"
    original_unlink = icloud_drive_adapter._safe_unlink_created_entry
    calls = 0

    def racing_unlink(parent_fd: int, name: str, created_stat: os.stat_result | None) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            source.unlink()
            source.write_text("Racing replacement after target proof.\n", encoding="utf-8")
            return False
        return original_unlink(parent_fd, name, created_stat)

    monkeypatch.setattr(icloud_drive_adapter, "_safe_unlink_created_entry", racing_unlink)

    result = apply_icloud_drive_change(
        "rename_text",
        handle=handle,
        expected_current_sha256=current_sha,
        filename="review-renamed.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "cleanup_unverified"
    assert target.read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert source.read_text(encoding="utf-8") == "Racing replacement after target proof.\n"


def test_apply_icloud_drive_change_move_preserves_verified_target_when_source_cleanup_races(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    archive = root / "Archive"
    archive.mkdir()
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    parent_handle = search_icloud_drive_metadata("Archive", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
    )
    source = root / "Packets" / "review-packet.md"
    target = archive / "review-moved.md"
    original_unlink = icloud_drive_adapter._safe_unlink_created_entry
    calls = 0

    def racing_unlink(parent_fd: int, name: str, created_stat: os.stat_result | None) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            source.unlink()
            source.write_text("Racing replacement after target proof.\n", encoding="utf-8")
            return False
        return original_unlink(parent_fd, name, created_stat)

    monkeypatch.setattr(icloud_drive_adapter, "_safe_unlink_created_entry", racing_unlink)

    result = apply_icloud_drive_change(
        "move_text",
        handle=handle,
        parent_handle=parent_handle,
        expected_current_sha256=current_sha,
        filename="review-moved.md",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "cleanup_unverified"
    assert target.read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert source.read_text(encoding="utf-8") == "Racing replacement after target proof.\n"


def test_apply_icloud_drive_change_append_text_rejects_unsupported_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
    )

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_file_type"


def test_apply_icloud_drive_change_append_text_rejects_invalid_utf8_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    invalid = root / "Packets" / "invalid.md"
    invalid.write_bytes(b"valid prefix\xff")
    handle = search_icloud_drive_metadata("invalid", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"valid prefix\xff").hexdigest()
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
    )

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert invalid.read_bytes() == b"valid prefix\xff"


def test_apply_icloud_drive_change_append_text_rejects_old_package_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Draft.pages"
    package.mkdir()
    (package / "index.md").write_text("Package internals\n", encoding="utf-8")
    handle = make_opaque_handle("icloud:file", "Draft.pages/index.md")
    current_sha = _content_sha("Package internals\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
    )

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert (package / "index.md").read_text(encoding="utf-8") == "Package internals\n"


def test_apply_icloud_drive_change_append_text_rejects_symlink_target_after_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
    )
    outside = tmp_path / "outside.md"
    outside.write_text("Outside\n", encoding="utf-8")
    symlink = root / "Packets" / "swapped.md"
    symlink.symlink_to(outside)
    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", lambda *args, **kwargs: symlink)

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppended synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert outside.read_text(encoding="utf-8") == "Outside\n"


def test_apply_icloud_drive_change_replace_text_rejects_unsupported_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="Replacement synthetic note.\n",
    )

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="Replacement synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_file_type"


def test_apply_icloud_drive_change_trash_text_rejects_unsupported_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert (root / "Packets" / "image.bin").exists()


def test_apply_icloud_drive_change_delete_text_rejects_unsupported_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("image", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\x00\x01").hexdigest()
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )
    assert plan["status"] == "error"
    assert plan["apply_available"] is False
    assert plan["preview"] is None
    assert plan["warnings"][0]["code"] == "unsupported_file_type"

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token="icloud-drive-apply:v1:fabricated",
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert result["apply_available"] is False
    assert result["preview"] is None
    assert result["privacy"]["content_inspected"] is False
    assert (root / "Packets" / "image.bin").exists()
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_trash_text_rejects_invalid_utf8_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "bad-utf8.md"
    target.write_bytes(b"\xff\xfe")
    handle = search_icloud_drive_metadata("bad-utf8", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\xff\xfe").hexdigest()
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert target.exists()
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_delete_text_rejects_invalid_utf8_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "bad-utf8.md"
    target.write_bytes(b"\xff\xfe")
    handle = search_icloud_drive_metadata("bad-utf8", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"\xff\xfe").hexdigest()
    plan = plan_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        root=root,
    )

    result = apply_icloud_drive_change(
        "delete_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert target.exists()
    assert _delete_staging_entries(root) == []


def test_apply_icloud_drive_change_replace_text_rejects_invalid_utf8_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    invalid = root / "Packets" / "invalid.md"
    invalid.write_bytes(b"valid prefix\xff")
    handle = search_icloud_drive_metadata("invalid", root=root)["results"][0]["handle"]
    current_sha = hashlib.sha256(b"valid prefix\xff").hexdigest()
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="Replacement synthetic note.\n",
    )

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="Replacement synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert invalid.read_bytes() == b"valid prefix\xff"


def test_apply_icloud_drive_change_replace_text_rejects_old_package_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Draft.pages"
    package.mkdir()
    (package / "index.md").write_text("Package internals\n", encoding="utf-8")
    handle = make_opaque_handle("icloud:file", "Draft.pages/index.md")
    current_sha = _content_sha("Package internals\n")
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="Replacement synthetic note.\n",
    )

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="Replacement synthetic note.\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert (package / "index.md").read_text(encoding="utf-8") == "Package internals\n"


def test_apply_icloud_drive_change_trash_text_rejects_package_member_after_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    package = root / "Packets.pages"
    package.mkdir()
    member = package / "index.md"
    member.write_text("Package internals\n", encoding="utf-8")
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", lambda *args, **kwargs: member)

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_file_type"
    assert member.read_text(encoding="utf-8") == "Package internals\n"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_replace_text_rejects_symlink_target_after_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle, current_sha, plan = _make_plan_for_review_replace(root)
    outside = tmp_path / "outside.md"
    outside.write_text("Outside\n", encoding="utf-8")
    symlink = root / "Packets" / "swapped.md"
    symlink.symlink_to(outside)
    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", lambda *args, **kwargs: symlink)

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replacement\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert outside.read_text(encoding="utf-8") == "Outside\n"


def test_apply_icloud_drive_change_trash_text_rejects_symlink_target_after_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    outside = tmp_path / "outside.md"
    outside.write_text("Outside\n", encoding="utf-8")
    symlink = root / "Packets" / "swapped.md"
    symlink.symlink_to(outside)
    monkeypatch.setattr(icloud_drive_adapter, "_resolve_handle", lambda *args, **kwargs: symlink)

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "not_found"
    assert result["mutation_applied"] is False
    assert outside.read_text(encoding="utf-8") == "Outside\n"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_trash_text_rejects_unsafe_parent_reopen(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )

    def bad_reopen(_path: Path, _root: Path) -> int:
        raise icloud_drive_adapter._UnsafeTargetError()

    monkeypatch.setattr(icloud_drive_adapter, "_open_resolved_directory_no_follow", bad_reopen)

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "read_error"
    assert target.read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert not (root / ".Trash").exists()


def test_apply_icloud_drive_change_trash_text_rechecks_after_swap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    original_swap = icloud_drive_adapter._renameatx_swap_no_follow
    swaps = 0

    def racing_swap(from_fd: int, from_name: str, to_fd: int, to_name: str) -> None:
        nonlocal swaps
        if swaps == 0:
            target.write_text("Concurrent rewrite before swap.\n", encoding="utf-8")
        swaps += 1
        original_swap(from_fd, from_name, to_fd, to_name)

    monkeypatch.setattr(icloud_drive_adapter, "_renameatx_swap_no_follow", racing_swap)

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Concurrent rewrite before swap.\n"
    assert list((root / ".Trash").iterdir()) == []


def test_apply_icloud_drive_change_trash_text_reports_partial_after_cleanup_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
    )
    original_unlink = icloud_drive_adapter.os.unlink

    def failing_source_cleanup(path, *args, **kwargs) -> None:
        if path == target.name and kwargs.get("dir_fd") is not None:
            raise OSError("synthetic cleanup failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(icloud_drive_adapter.os, "unlink", failing_source_cleanup)

    result = apply_icloud_drive_change(
        "trash_text",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["original_present"] is True
    assert result["read_back"]["trashed"] is True
    assert result["read_back"]["trash_path_returned"] is False
    assert target.read_bytes() == b""
    trashed_items = list((root / ".Trash").iterdir())
    assert len(trashed_items) == 1
    assert trashed_items[0].read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"


def test_trash_root_for_configured_default_uses_home_trash(monkeypatch) -> None:
    default_root = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
    monkeypatch.setenv("LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT", str(default_root))

    assert icloud_drive_adapter._trash_root_for(default_root) == Path.home() / ".Trash"

    synthetic_root = Path("/tmp/local-apple-data-synthetic-cloud")
    monkeypatch.setenv("LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT", str(synthetic_root))

    assert icloud_drive_adapter._trash_root_for(synthetic_root) == synthetic_root / ".Trash"


def test_apply_icloud_drive_change_append_text_reports_read_back_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppend\n",
    )

    def bad_replace(target: Path, content: bytes, *, expected_sha: str, root: Path | None = None) -> None:
        assert expected_sha == current_sha
        target.write_text("Different on disk.\n", encoding="utf-8")

    monkeypatch.setattr(icloud_drive_adapter, "_atomic_replace_bytes", bad_replace)

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppend\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["content_sha256"] == _content_sha("Different on disk.\n")


def test_apply_icloud_drive_change_append_text_reports_unreadable_read_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppend\n",
    )

    def bad_replace(target: Path, content: bytes, *, expected_sha: str, root: Path | None = None) -> None:
        assert expected_sha == current_sha
        target.write_bytes(b"\xff")

    monkeypatch.setattr(icloud_drive_adapter, "_atomic_replace_bytes", bad_replace)

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppend\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert "read_back_unavailable" in codes
    assert "read_back_mismatch" in codes


def test_apply_icloud_drive_change_replace_text_is_idempotent_after_success(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    replacement = "# Replacement\n"
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
    )
    (root / "Packets" / "review-packet.md").write_text(replacement, encoding="utf-8")

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["operation"] == "replace_text"
    assert result["warnings"][0]["code"] == "already_applied"


def test_apply_icloud_drive_change_replace_text_reports_read_back_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    replacement = "# Replacement\n"
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
    )

    def bad_replace(target: Path, content: str, *, expected_sha: str, root: Path | None = None) -> None:
        assert expected_sha == current_sha
        target.write_text("Different on disk.\n", encoding="utf-8")

    monkeypatch.setattr(icloud_drive_adapter, "_atomic_replace_text", bad_replace)

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text=replacement,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_mismatch"
    assert result["read_back"]["content_sha256"] == _content_sha("Different on disk.\n")


def test_apply_icloud_drive_change_replace_text_reports_unreadable_read_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle, current_sha, plan = _make_plan_for_review_replace(root)

    def bad_replace(target: Path, content: str, *, expected_sha: str, root: Path | None = None) -> None:
        assert expected_sha == current_sha
        target.write_bytes(b"\xff")

    monkeypatch.setattr(icloud_drive_adapter, "_atomic_replace_text", bad_replace)

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replacement\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert "read_back_unavailable" in codes
    assert "read_back_mismatch" in codes


def test_apply_icloud_drive_change_replace_text_rechecks_content_before_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replacement\n",
    )
    original_read_bytes_at = icloud_drive_adapter._read_file_bytes_no_follow_at

    reads = 0

    def drifting_read_at(parent_fd: int, name: str) -> bytes:
        nonlocal reads
        if name == target.name:
            reads += 1
            if reads == 1:
                target.write_text("Concurrent edit.\n", encoding="utf-8")
                monkeypatch.setattr(
                    icloud_drive_adapter,
                    "_read_file_bytes_no_follow_at",
                    original_read_bytes_at,
                )
        return original_read_bytes_at(parent_fd, name)

    monkeypatch.setattr(icloud_drive_adapter, "_read_file_bytes_no_follow_at", drifting_read_at)

    result = apply_icloud_drive_change(
        "replace_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="# Replacement\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Concurrent edit.\n"
    assert list(target.parent.glob(".review-packet.md.*.tmp")) == []


def test_apply_icloud_drive_change_append_text_rechecks_content_before_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")
    plan = plan_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppend\n",
    )
    original_read_bytes_at = icloud_drive_adapter._read_file_bytes_no_follow_at

    reads = 0

    def drifting_read_at(parent_fd: int, name: str) -> bytes:
        nonlocal reads
        if name == target.name:
            reads += 1
            if reads == 2:
                target.write_text("Concurrent edit.\n", encoding="utf-8")
                monkeypatch.setattr(
                    icloud_drive_adapter,
                    "_read_file_bytes_no_follow_at",
                    original_read_bytes_at,
                )
        return original_read_bytes_at(parent_fd, name)

    monkeypatch.setattr(icloud_drive_adapter, "_read_file_bytes_no_follow_at", drifting_read_at)

    result = apply_icloud_drive_change(
        "append_text",
        handle=handle,
        expected_current_sha256=current_sha,
        content_text="\nAppend\n",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["privacy"]["content_inspected"] is True
    assert result["warnings"][0]["code"] == "current_content_changed"
    assert target.read_text(encoding="utf-8") == "Concurrent edit.\n"
    assert list(target.parent.glob(".review-packet.md.*.tmp")) == []


def test_atomic_replace_text_removes_temp_file_after_write_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "review-packet.md"
    current_sha = _content_sha("# Synthetic Packet\nLine two\n")

    def fail_fsync(_fileno: int) -> None:
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError):
        icloud_drive_adapter._atomic_replace_text(
            target,
            "# Replacement\n",
            expected_sha=current_sha,
        )

    assert target.read_text(encoding="utf-8") == "# Synthetic Packet\nLine two\n"
    assert list(target.parent.glob(".review-packet.md.*.tmp")) == []


def test_create_text_no_follow_does_not_unlink_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    target = root / "Packets" / "existing.md"
    target.write_text("Existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        icloud_drive_adapter._create_text_no_follow(
            root / "Packets",
            "existing.md",
            "Replacement\n",
        )

    assert target.read_text(encoding="utf-8") == "Existing\n"


def test_apply_icloud_drive_change_is_idempotent_for_matching_existing_file(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    (root / "Packets" / "new-note.md").write_text("Synthetic text.", encoding="utf-8")
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"


def test_apply_icloud_drive_change_create_text_same_token_retry_after_success(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        root=root,
    )
    token = _approval_token(plan)

    first = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=token,
        confirm_apply=True,
        root=root,
    )
    retry = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="new-note.md",
        content_text="Synthetic text.",
        approval_token=token,
        confirm_apply=True,
        root=root,
    )

    assert first["status"] == "ok"
    assert first["mutation_applied"] is True
    assert retry["status"] == "ok"
    assert retry["mutation_applied"] is False
    assert retry["warnings"][0]["code"] == "already_applied"


def test_apply_icloud_drive_change_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    parent_handle = _parent_handle(root)
    plan = plan_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="review-packet.md",
        content_text="Different synthetic text.",
        root=root,
    )

    result = apply_icloud_drive_change(
        "create_text",
        parent_handle=parent_handle,
        filename="review-packet.md",
        content_text="Different synthetic text.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        root=root,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "target_exists"

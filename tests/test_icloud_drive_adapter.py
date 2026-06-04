from __future__ import annotations

from pathlib import Path

from local_apple_data.adapters.icloud_drive import (
    get_icloud_drive_content,
    get_icloud_drive_metadata,
    search_icloud_drive_metadata,
)


def _make_icloud_root(root: Path) -> None:
    (root / "Packets").mkdir(parents=True)
    (root / "Packets" / "review-packet.md").write_text(
        "# Synthetic Packet\nLine two\n",
        encoding="utf-8",
    )
    (root / "Packets" / "image.bin").write_bytes(b"\x00\x01")
    (root / ".hidden.md").write_text("hidden", encoding="utf-8")


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


def test_get_icloud_drive_content_by_handle(tmp_path: Path) -> None:
    root = tmp_path / "CloudDocs"
    _make_icloud_root(root)
    handle = search_icloud_drive_metadata("review", root=root)["results"][0]["handle"]

    result = get_icloud_drive_content(handle, root=root, max_chars=4000)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["content_text"] == "# Synthetic Packet\nLine two\n"
    assert result["result"]["content_chars"] == len(result["result"]["content_text"])
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

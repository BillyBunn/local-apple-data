from __future__ import annotations

import plistlib
from datetime import datetime
from pathlib import Path

from local_apple_data.adapters.safari import (
    get_safari_folder,
    get_safari_item,
    list_safari_folder_items,
    search_safari_folders,
    search_safari_items,
)


def _write_bookmarks(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Title": "Bookmarks",
        "WebBookmarkFileVersion": 1,
        "WebBookmarkType": "WebBookmarkTypeList",
        "Children": [
            {
                "Title": "Favorites",
                "WebBookmarkType": "WebBookmarkTypeList",
                "Children": [
                    {
                        "WebBookmarkType": "WebBookmarkTypeLeaf",
                        "URIDictionary": {"title": "Synthetic Packet"},
                        "URLString": "https://example.com/private/packet?example=1",
                    },
                    {
                        "WebBookmarkType": "WebBookmarkTypeLeaf",
                        "URIDictionary": {"title": "Synthetic Search"},
                        "URLString": "https://search.example.net/",
                    },
                    {
                        "Title": "Synthetic Folder",
                        "WebBookmarkType": "WebBookmarkTypeList",
                        "Children": [
                            {
                                "WebBookmarkType": "WebBookmarkTypeLeaf",
                                "URIDictionary": {"title": "Nested Packet"},
                                "URLString": "https://nested.example.com/private/path?secret=1",
                            },
                            {
                                "Title": "Synthetic Child Folder",
                                "WebBookmarkType": "WebBookmarkTypeList",
                                "Children": [
                                    {
                                        "WebBookmarkType": "WebBookmarkTypeLeaf",
                                        "URIDictionary": {"title": "Grandchild Packet"},
                                        "URLString": "https://grandchild.example.com/",
                                    }
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                "Title": "com.apple.ReadingList",
                "WebBookmarkType": "WebBookmarkTypeList",
                "Children": [
                    {
                        "WebBookmarkType": "WebBookmarkTypeLeaf",
                        "URIDictionary": {"title": "Synthetic Reading"},
                        "URLString": "https://reading.example.org/article",
                        "ReadingList": {"DateAdded": datetime(2026, 6, 4, 12, 0, 0)},
                    }
                ],
            },
        ],
    }
    path.write_bytes(plistlib.dumps(payload, sort_keys=True))


def test_search_safari_items_returns_metadata_without_full_url(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    result = search_safari_items("Synthetic Packet", bookmarks_path=bookmarks_path)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["privacy"]["content_inspected"] is False
    assert result["result_count"] == 1
    item = result["results"][0]
    assert item["handle"].startswith("safari:item:v1:")
    assert item["title"] == "Synthetic Packet"
    assert item["kind"] == "bookmark"
    assert item["url_domain"] == "example.com"
    assert item["url_has_query"] is True
    assert "URLString" not in item
    assert "https://example.com/private/packet?example=1" not in str(result)


def test_search_safari_items_filters_reading_list(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    result = search_safari_items("Synthetic", bookmarks_path=bookmarks_path, kind="reading-list")

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["kind"] == "reading_list"
    assert result["results"][0]["date_added"] is not None


def test_get_safari_item_returns_exact_url_by_handle(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)
    handle = search_safari_items("Synthetic Packet", bookmarks_path=bookmarks_path)["results"][0][
        "handle"
    ]

    result = get_safari_item(handle, bookmarks_path=bookmarks_path)

    assert result["status"] == "ok"
    assert result["privacy"]["url_returned"] is True
    assert result["result"]["title"] == "Synthetic Packet"
    assert result["result"]["url"] == "https://example.com/private/packet?example=1"


def test_get_safari_item_rejects_bad_handle(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    result = get_safari_item("safari:item:1", bookmarks_path=bookmarks_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_safari_items_rejects_empty_and_broad_queries(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    empty = search_safari_items(" ", bookmarks_path=bookmarks_path)
    broad = search_safari_items("Safari", bookmarks_path=bookmarks_path)

    assert empty["status"] == "error"
    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["status"] == "error"
    assert broad["warnings"][0]["code"] == "broad_query"


def test_search_safari_items_reports_unavailable_and_parse_errors(tmp_path: Path) -> None:
    missing = search_safari_items("Packet", bookmarks_path=tmp_path / "missing.plist")
    malformed_path = tmp_path / "Bookmarks.plist"
    malformed_path.write_text("not a plist", encoding="utf-8")
    malformed = search_safari_items("Packet", bookmarks_path=malformed_path)

    assert missing["status"] == "degraded"
    assert missing["warnings"][0]["code"] == "safari_store_unavailable"
    assert malformed["status"] == "degraded"
    assert malformed["warnings"][0]["code"] == "safari_parse_error"


def test_search_safari_folders_returns_metadata_only(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    result = search_safari_folders("Synthetic Folder", bookmarks_path=bookmarks_path)

    assert result["status"] == "ok"
    assert result["source"] == "safari_folders"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["result_count"] == 1
    folder = result["results"][0]
    assert folder["handle"].startswith("safari:folder:v1:")
    assert folder["title"] == "Synthetic Folder"
    assert folder["child_item_count"] == 1
    assert folder["child_folder_count"] == 1
    assert "URLString" not in str(result)
    assert "https://nested.example.com/private/path?secret=1" not in str(result)


def test_get_safari_folder_returns_exact_metadata_by_handle(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)
    handle = search_safari_folders("Synthetic Folder", bookmarks_path=bookmarks_path)["results"][0][
        "handle"
    ]

    result = get_safari_folder(handle, bookmarks_path=bookmarks_path)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Synthetic Folder"
    assert result["result"]["child_item_count"] == 1
    assert result["result"]["child_folder_count"] == 1
    assert "URLString" not in str(result)


def test_list_safari_folder_items_returns_direct_metadata_only(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)
    handle = search_safari_folders("Synthetic Folder", bookmarks_path=bookmarks_path)["results"][0][
        "handle"
    ]

    result = list_safari_folder_items(handle, bookmarks_path=bookmarks_path)

    assert result["status"] == "ok"
    assert result["source"] == "safari_folder_items"
    assert result["folder"]["title"] == "Synthetic Folder"
    assert result["result_count"] == 1
    assert result["child_folder_count"] == 1
    assert result["results"][0]["title"] == "Nested Packet"
    assert result["results"][0]["url_domain"] == "nested.example.com"
    assert result["child_folders"][0]["title"] == "Synthetic Child Folder"
    assert "url" not in result["results"][0]
    assert "Grandchild Packet" not in str(result)
    assert "https://nested.example.com/private/path?secret=1" not in str(result)


def test_list_safari_folder_items_caps_combined_direct_children(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)
    handle = search_safari_folders("Synthetic Folder", bookmarks_path=bookmarks_path)["results"][0][
        "handle"
    ]

    result = list_safari_folder_items(handle, bookmarks_path=bookmarks_path, limit=1)

    assert result["status"] == "ok"
    assert result["query"]["limit"] == 1
    assert result["result_count"] + result["child_folder_count"] == 1
    assert result["results"][0]["title"] == "Nested Packet"


def test_safari_folder_paths_reject_bad_handles(tmp_path: Path) -> None:
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    detail = get_safari_folder("safari:folder:1", bookmarks_path=bookmarks_path)
    listing = list_safari_folder_items("bad-handle", bookmarks_path=bookmarks_path)

    assert detail["status"] == "error"
    assert detail["warnings"][0]["code"] == "invalid_handle"
    assert listing["status"] == "error"
    assert listing["source"] == "safari_folder_items"

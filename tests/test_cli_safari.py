from __future__ import annotations

import json
import plistlib
from pathlib import Path

from local_apple_data.cli import main


def _write_bookmarks(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        plistlib.dumps(
            {
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
                                "URIDictionary": {"title": "Synthetic CLI Packet"},
                                "URLString": "https://cli.example.com/private?example=1",
                            }
                        ],
                    }
                ],
            },
            sort_keys=True,
        )
    )


def test_cli_safari_search_uses_synthetic_bookmarks(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)

    exit_code = main(
        [
            "safari",
            "search",
            "--json",
            "--query",
            "Packet",
            "--bookmarks-path",
            str(bookmarks_path),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "safari"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("safari:item:v1:")
    assert parsed["results"][0]["url_domain"] == "cli.example.com"
    assert "https://cli.example.com/private?example=1" not in str(parsed)


def test_cli_safari_get_uses_synthetic_bookmarks(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    bookmarks_path = tmp_path / "Bookmarks.plist"
    _write_bookmarks(bookmarks_path)
    search_exit = main(
        [
            "safari",
            "search",
            "--json",
            "--query",
            "Packet",
            "--bookmarks-path",
            str(bookmarks_path),
        ]
    )
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "safari",
            "get",
            "--json",
            "--handle",
            handle,
            "--bookmarks-path",
            str(bookmarks_path),
        ]
    )

    assert search_exit == 0
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["url"] == "https://cli.example.com/private?example=1"

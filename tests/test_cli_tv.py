from __future__ import annotations

import json

from local_apple_data.cli import main


def _item_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "tv",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "video_content_returned": False,
            "file_path_returned": False,
            "raw_identifier_returned": False,
            "artwork_returned": False,
            "description_returned": False,
            "playback_state_returned": False,
            "watched_state_returned": False,
        },
        "results": [
            {
                "handle": "tv:item:v1:11111111111111111111111111111111",
                "title": "Synthetic CLI Episode",
                "show": "Synthetic Show",
                "artist": "Synthetic Studio",
                "genre": "Synthetic Genre",
                "video_kind": "TV show",
                "file_path_returned": False,
                "video_content_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def _playlist_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "tv_playlists",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "video_content_returned": False,
            "file_path_returned": False,
            "raw_identifier_returned": False,
            "playlist_items_returned": False,
        },
        "results": [
            {
                "handle": "tv:playlist:v1:22222222222222222222222222222222",
                "title": "Synthetic CLI TV Playlist",
                "kind": "user",
                "item_count": 4,
                "playlist_items_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def _playlist_items_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "tv_playlist_items",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "video_content_returned": False,
            "file_path_returned": False,
            "raw_identifier_returned": False,
            "artwork_returned": False,
            "description_returned": False,
            "playback_state_returned": False,
            "watched_state_returned": False,
            "rating_returned": False,
            "playlist_items_returned": True,
        },
        "playlist": _playlist_payload()["results"][0],
        "results": [_item_payload()["results"][0]],
        "result_count": 1,
        "warnings": [],
    }


def test_cli_tv_search_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _item_payload()

    monkeypatch.setattr("local_apple_data.cli.search_tv_items", fake_search)

    exit_code = main(
        [
            "tv",
            "search",
            "--json",
            "--query",
            "CLI",
            "--limit",
            "5",
            "--max-scan-items",
            "25",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "tv"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 5, "max_scan_items": 25}


def test_cli_tv_get_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "tv:item:v1:11111111111111111111111111111111"
        assert kwargs == {"max_scan_items": 5000}
        payload = _item_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_tv_item", fake_get)

    exit_code = main(
        [
            "tv",
            "get",
            "--json",
            "--handle",
            "tv:item:v1:11111111111111111111111111111111",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI Episode"


def test_cli_tv_playlists_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _playlist_payload()

    monkeypatch.setattr("local_apple_data.cli.search_tv_playlists", fake_search)

    exit_code = main(
        [
            "tv",
            "playlists",
            "--json",
            "--query",
            "CLI",
            "--limit",
            "2",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "tv_playlists"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 2, "max_scan_items": 5000}


def test_cli_tv_playlist_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "tv:playlist:v1:22222222222222222222222222222222"
        assert kwargs == {"max_scan_items": 5000}
        payload = _playlist_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_tv_playlist", fake_get)

    exit_code = main(
        [
            "tv",
            "playlist",
            "--json",
            "--handle",
            "tv:playlist:v1:22222222222222222222222222222222",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI TV Playlist"


def test_cli_tv_playlist_items_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_list(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return _playlist_items_payload()

    monkeypatch.setattr("local_apple_data.cli.list_tv_playlist_items", fake_list)

    exit_code = main(
        [
            "tv",
            "playlist-items",
            "--json",
            "--handle",
            "tv:playlist:v1:22222222222222222222222222222222",
            "--limit",
            "3",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "tv_playlist_items"
    assert parsed["result_count"] == 1
    assert seen["handle"] == "tv:playlist:v1:22222222222222222222222222222222"
    assert seen["kwargs"] == {"limit": 3, "max_scan_items": 5000}

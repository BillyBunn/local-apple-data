from __future__ import annotations

import json

from local_apple_data.cli import main


def _track_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "music",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "audio_content_returned": False,
            "lyrics_returned": False,
            "file_path_returned": False,
            "raw_identifier_returned": False,
            "play_history_returned": False,
        },
        "results": [
            {
                "handle": "music:track:v1:11111111111111111111111111111111",
                "title": "Synthetic CLI Track",
                "artist": "Synthetic Artist",
                "album": "Synthetic Album",
                "genre": "Synthetic Genre",
                "file_path_returned": False,
                "audio_content_returned": False,
                "lyrics_returned": False,
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
        "source": "music_playlists",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "audio_content_returned": False,
            "lyrics_returned": False,
            "file_path_returned": False,
            "raw_identifier_returned": False,
            "play_history_returned": False,
        },
        "results": [
            {
                "handle": "music:playlist:v1:22222222222222222222222222222222",
                "title": "Synthetic CLI Playlist",
                "kind": "user",
                "track_count": 4,
                "playlist_tracks_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def _playlist_tracks_payload() -> dict:
    track_payload = _track_payload()
    playlist_payload = _playlist_payload()
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "music_playlist_tracks",
        "privacy": {
            **track_payload["privacy"],
            "playlist_tracks_returned": True,
        },
        "playlist": playlist_payload["results"][0],
        "results": track_payload["results"],
        "result_count": 1,
        "warnings": [],
    }


def test_cli_music_search_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _track_payload()

    monkeypatch.setattr("local_apple_data.cli.search_music_tracks", fake_search)

    exit_code = main(
        [
            "music",
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
    assert parsed["source"] == "music"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 5, "max_scan_items": 25}


def test_cli_music_get_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "music:track:v1:11111111111111111111111111111111"
        assert kwargs == {"max_scan_items": 5000}
        payload = _track_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_music_track", fake_get)

    exit_code = main(
        [
            "music",
            "get",
            "--json",
            "--handle",
            "music:track:v1:11111111111111111111111111111111",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI Track"


def test_cli_music_playlists_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _playlist_payload()

    monkeypatch.setattr("local_apple_data.cli.search_music_playlists", fake_search)

    exit_code = main(
        [
            "music",
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
    assert parsed["source"] == "music_playlists"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 2, "max_scan_items": 5000}


def test_cli_music_playlist_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "music:playlist:v1:22222222222222222222222222222222"
        assert kwargs == {"max_scan_items": 5000}
        payload = _playlist_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_music_playlist", fake_get)

    exit_code = main(
        [
            "music",
            "playlist",
            "--json",
            "--handle",
            "music:playlist:v1:22222222222222222222222222222222",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI Playlist"


def test_cli_music_playlist_tracks_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_list(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return _playlist_tracks_payload()

    monkeypatch.setattr("local_apple_data.cli.list_music_playlist_tracks", fake_list)

    exit_code = main(
        [
            "music",
            "playlist-tracks",
            "--json",
            "--handle",
            "music:playlist:v1:22222222222222222222222222222222",
            "--limit",
            "3",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["source"] == "music_playlist_tracks"
    assert parsed["result_count"] == 1
    assert seen["handle"] == "music:playlist:v1:22222222222222222222222222222222"
    assert seen["kwargs"] == {"limit": 3, "max_scan_items": 5000}

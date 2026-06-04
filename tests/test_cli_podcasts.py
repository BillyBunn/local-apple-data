from __future__ import annotations

import json

from local_apple_data.cli import main


def _search_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "podcasts",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
        },
        "results": [
            {
                "handle": "podcasts:show:v1:11111111111111111111111111111111",
                "title": "Synthetic CLI Show",
                "author": "Synthetic Host",
                "category": "Technology",
                "episode_count": 2,
                "feed_url_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def test_cli_podcasts_search_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _search_payload()

    monkeypatch.setattr("local_apple_data.cli.search_podcasts", fake_search)

    exit_code = main(
        [
            "podcasts",
            "search",
            "--json",
            "--query",
            "CLI",
            "--limit",
            "5",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "podcasts"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 5}


def test_cli_podcasts_get_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "podcasts:show:v1:11111111111111111111111111111111"
        assert kwargs == {}
        payload = _search_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_podcast_show", fake_get)

    exit_code = main(
        [
            "podcasts",
            "get",
            "--json",
            "--handle",
            "podcasts:show:v1:11111111111111111111111111111111",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI Show"


def test_cli_podcasts_episodes_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_episodes(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "podcasts",
            "privacy": {
                "content_inspected": False,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "metadata",
            },
            "result": {
                "handle": "podcasts:show:v1:11111111111111111111111111111111",
                "title": "Synthetic CLI Show",
                "episodes": [
                    {
                        "handle": "podcasts:episode:v1:22222222222222222222222222222222",
                        "title": "Synthetic CLI Episode",
                        "description_returned": False,
                        "transcript_text_returned": False,
                        "audio_content_returned": False,
                    }
                ],
                "episodes_returned": 1,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.list_podcast_episodes", fake_episodes)

    exit_code = main(
        [
            "podcasts",
            "episodes",
            "--json",
            "--handle",
            "podcasts:show:v1:11111111111111111111111111111111",
            "--limit",
            "3",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["episodes_returned"] == 1
    assert seen["handle"] == "podcasts:show:v1:11111111111111111111111111111111"
    assert seen["kwargs"] == {"limit": 3}


def test_cli_podcasts_episode_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_episode(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "podcasts",
            "privacy": {
                "content_inspected": True,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "content",
                "episode_description_returned": True,
                "transcript_text_returned": False,
                "audio_content_returned": False,
            },
            "result": {
                "handle": "podcasts:episode:v1:22222222222222222222222222222222",
                "title": "Synthetic CLI Episode",
                "description": "Synthetic description.",
                "description_chars": 22,
                "description_truncated": False,
                "transcript_text_returned": False,
                "audio_content_returned": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.get_podcast_episode", fake_episode)

    exit_code = main(
        [
            "podcasts",
            "episode",
            "--json",
            "--handle",
            "podcasts:episode:v1:22222222222222222222222222222222",
            "--max-chars",
            "100",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["description"] == "Synthetic description."
    assert seen["handle"] == "podcasts:episode:v1:22222222222222222222222222222222"
    assert seen["kwargs"] == {"max_chars": 100}

from __future__ import annotations

import json

from local_apple_data.cli import main


def _search_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "shortcuts",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "shortcut_body_returned": False,
        },
        "results": [
            {
                "handle": "shortcuts:item:v1:11111111111111111111111111111111",
                "title": "Synthetic CLI Shortcut",
                "kind": "shortcut",
                "identifier_present": True,
                "shortcut_body_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def test_cli_shortcuts_search_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _search_payload()

    monkeypatch.setattr("local_apple_data.cli.search_shortcuts_items", fake_search)

    exit_code = main(
        [
            "shortcuts",
            "search",
            "--json",
            "--query",
            "CLI",
            "--kind",
            "shortcut",
            "--limit",
            "5",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "shortcuts"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 5, "kind": "shortcut", "max_scan_items": 5000}


def test_cli_shortcuts_get_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "shortcuts:item:v1:11111111111111111111111111111111"
        assert kwargs == {"max_scan_items": 5000}
        payload = _search_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_shortcuts_item", fake_get)

    exit_code = main(
        [
            "shortcuts",
            "get",
            "--json",
            "--handle",
            "shortcuts:item:v1:11111111111111111111111111111111",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI Shortcut"

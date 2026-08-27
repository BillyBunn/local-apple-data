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


def test_cli_shortcuts_folder_items_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_list(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        payload = _search_payload()
        return {
            **payload,
            "parent": {
                "handle": "shortcuts:item:v1:folder",
                "title": "Synthetic CLI Folder",
                "kind": "folder",
                "identifier_present": True,
                "shortcut_body_returned": False,
            },
        }

    monkeypatch.setattr("local_apple_data.cli.list_shortcuts_folder_items", fake_list)

    exit_code = main(
        [
            "shortcuts",
            "folder-items",
            "--json",
            "--handle",
            "shortcuts:item:v1:folder",
            "--limit",
            "7",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["parent"]["title"] == "Synthetic CLI Folder"
    assert seen["handle"] == "shortcuts:item:v1:folder"
    assert seen["kwargs"] == {"limit": 7, "max_scan_items": 5000}


def test_cli_shortcuts_plan_forwards_args(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_plan(operation: str, **kwargs):
        seen["operation"] = operation
        seen["kwargs"] = kwargs
        return {"schema_version": 1, "status": "ok", "source": "shortcuts", "mode": "plan", "preview": {}, "warnings": []}

    monkeypatch.setattr("local_apple_data.cli.plan_shortcuts_run", fake_plan)

    exit_code = main(
        [
            "shortcuts",
            "plan",
            "--json",
            "--operation",
            "run",
            "--handle",
            "shortcuts:item:v1:11111111111111111111111111111111",
            "--input-text",
            "hi",
        ]
    )

    assert exit_code == 0
    assert seen["operation"] == "run"
    assert seen["kwargs"] == {
        "handle": "shortcuts:item:v1:11111111111111111111111111111111",
        "input_text": "hi",
        "max_scan_items": 5000,
    }


def test_cli_shortcuts_apply_forwards_gate_args(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_apply(operation: str, **kwargs):
        seen["operation"] = operation
        seen["kwargs"] = kwargs
        return {"schema_version": 1, "status": "ok", "source": "shortcuts", "mode": "apply", "warnings": []}

    monkeypatch.setattr("local_apple_data.cli.apply_shortcuts_run", fake_apply)

    exit_code = main(
        [
            "shortcuts",
            "apply",
            "--json",
            "--operation",
            "run",
            "--handle",
            "shortcuts:item:v1:11111111111111111111111111111111",
            "--approval-token",
            "shortcuts-apply:v1:abc123",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    assert seen["operation"] == "run"
    assert seen["kwargs"] == {
        "handle": "shortcuts:item:v1:11111111111111111111111111111111",
        "input_text": "",
        "approval_token": "shortcuts-apply:v1:abc123",
        "confirm_apply": True,
        "max_scan_items": 5000,
    }

from __future__ import annotations

import json

from local_apple_data.cli import main


def _boards_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "board_content_returned": False,
            "asset_content_returned": False,
        },
        "results": [
            {
                "handle": "freeform:board:v1:11111111111111111111111111111111",
                "title_status": "unavailable_without_blob_decode",
                "board_title_returned": False,
                "item_count": 3,
                "asset_reference_count": 1,
                "board_items_returned": False,
                "board_content_returned": False,
                "asset_content_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def _folders_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "board_content_returned": False,
            "asset_content_returned": False,
        },
        "results": [
            {
                "handle": "freeform:folder:v1:22222222222222222222222222222222",
                "title": "Synthetic CLI Folder",
                "board_count": 2,
                "folder_blob_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def _folder_boards_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform_folder_boards",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "board_content_returned": False,
            "asset_content_returned": False,
        },
        "folder": _folders_payload()["results"][0],
        "results": _boards_payload()["results"],
        "result_count": 1,
        "warnings": [],
    }


def _child_folders_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "freeform_child_folders",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
            "board_content_returned": False,
            "asset_content_returned": False,
        },
        "folder": _folders_payload()["results"][0],
        "results": [
            {
                "handle": "freeform:folder:v1:55555555555555555555555555555555",
                "title": "Synthetic CLI Child Folder",
                "board_count": 0,
                "folder_blob_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def test_cli_freeform_boards_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_boards(**kwargs):
        seen["kwargs"] = kwargs
        return _boards_payload()

    monkeypatch.setattr("local_apple_data.cli.list_freeform_boards", fake_boards)

    exit_code = main(["freeform", "boards", "--json", "--limit", "5"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "freeform"
    assert parsed["result_count"] == 1
    assert seen["kwargs"] == {"limit": 5}


def test_cli_freeform_get_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "freeform:board:v1:11111111111111111111111111111111"
        assert kwargs == {}
        payload = _boards_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "results": None,
            "result_count": 1,
        }

    monkeypatch.setattr("local_apple_data.cli.get_freeform_board", fake_get)

    exit_code = main(
        [
            "freeform",
            "get",
            "--json",
            "--handle",
            "freeform:board:v1:11111111111111111111111111111111",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["board_content_returned"] is False


def test_cli_freeform_folders_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_folders(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _folders_payload()

    monkeypatch.setattr("local_apple_data.cli.search_freeform_folders", fake_folders)

    exit_code = main(
        [
            "freeform",
            "folders",
            "--json",
            "--query",
            "CLI",
            "--limit",
            "7",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 7}


def test_cli_freeform_folder_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_folder(handle: str, **kwargs):
        assert handle == "freeform:folder:v1:22222222222222222222222222222222"
        assert kwargs == {}
        payload = _folders_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "results": None,
            "result_count": 1,
        }

    monkeypatch.setattr("local_apple_data.cli.get_freeform_folder", fake_folder)

    exit_code = main(
        [
            "freeform",
            "folder",
            "--json",
            "--handle",
            "freeform:folder:v1:22222222222222222222222222222222",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["title"] == "Synthetic CLI Folder"


def test_cli_freeform_folder_boards_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_folder_boards(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return _folder_boards_payload()

    monkeypatch.setattr(
        "local_apple_data.cli.list_freeform_folder_boards",
        fake_folder_boards,
    )

    exit_code = main(
        [
            "freeform",
            "folder-boards",
            "--json",
            "--handle",
            "freeform:folder:v1:22222222222222222222222222222222",
            "--limit",
            "3",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "freeform_folder_boards"
    assert parsed["result_count"] == 1
    assert seen["handle"] == "freeform:folder:v1:22222222222222222222222222222222"
    assert seen["kwargs"] == {"limit": 3}


def test_cli_freeform_child_folders_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_child_folders(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return _child_folders_payload()

    monkeypatch.setattr(
        "local_apple_data.cli.list_freeform_child_folders",
        fake_child_folders,
    )

    exit_code = main(
        [
            "freeform",
            "child-folders",
            "--json",
            "--handle",
            "freeform:folder:v1:22222222222222222222222222222222",
            "--limit",
            "4",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "freeform_child_folders"
    assert parsed["result_count"] == 1
    assert seen["handle"] == "freeform:folder:v1:22222222222222222222222222222222"
    assert seen["kwargs"] == {"limit": 4}

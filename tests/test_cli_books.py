from __future__ import annotations

import json

from local_apple_data.cli import main


def _search_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "books",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "metadata",
        },
        "results": [
            {
                "handle": "books:book:v1:11111111111111111111111111111111",
                "title": "Synthetic CLI Book",
                "author": "Synthetic Author",
                "genre": "Engineering",
                "annotation_count": 2,
                "book_text_returned": False,
                "raw_identifier_returned": False,
            }
        ],
        "result_count": 1,
        "warnings": [],
    }


def test_cli_books_search_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_search(query: str, **kwargs):
        seen["query"] = query
        seen["kwargs"] = kwargs
        return _search_payload()

    monkeypatch.setattr("local_apple_data.cli.search_books", fake_search)

    exit_code = main(
        [
            "books",
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
    assert parsed["source"] == "books"
    assert parsed["result_count"] == 1
    assert seen["query"] == "CLI"
    assert seen["kwargs"] == {"limit": 5}


def test_cli_books_get_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    def fake_get(handle: str, **kwargs):
        assert handle == "books:book:v1:11111111111111111111111111111111"
        assert kwargs == {}
        payload = _search_payload()
        return {
            **payload,
            "result": payload["results"][0],
            "result_count": 1,
            "results": None,
        }

    monkeypatch.setattr("local_apple_data.cli.get_book", fake_get)

    exit_code = main(
        [
            "books",
            "get",
            "--json",
            "--handle",
            "books:book:v1:11111111111111111111111111111111",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["title"] == "Synthetic CLI Book"


def test_cli_books_annotations_outputs_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    seen: dict[str, object] = {}

    def fake_annotations(handle: str, **kwargs):
        seen["handle"] = handle
        seen["kwargs"] = kwargs
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "books",
            "privacy": {
                "content_inspected": True,
                "raw_rows_inspected": False,
                "credentials_inspected": False,
                "output_tier": "content",
                "annotation_text_returned": True,
                "book_text_returned": False,
            },
            "result": {
                "title": "Synthetic CLI Book",
                "book_text_returned": False,
                "annotations": [
                    {
                        "handle": "books:annotation:v1:22222222222222222222222222222222",
                        "selected_text": "Synthetic highlight.",
                        "note_text": "Synthetic note.",
                    }
                ],
                "annotations_returned": 1,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.list_book_annotations", fake_annotations)

    exit_code = main(
        [
            "books",
            "annotations",
            "--json",
            "--handle",
            "books:book:v1:11111111111111111111111111111111",
            "--limit",
            "3",
            "--max-chars",
            "100",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["annotations_returned"] == 1
    assert seen["handle"] == "books:book:v1:11111111111111111111111111111111"
    assert seen["kwargs"] == {"limit": 3, "max_chars": 100}

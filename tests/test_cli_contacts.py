from __future__ import annotations

import json

from local_apple_data.cli import main


def test_cli_contacts_search(monkeypatch, capsys) -> None:
    def fake_search(query: str, *, limit: int, max_scan_contacts: int) -> dict:
        assert query == "Synthetic"
        assert limit == 6
        assert max_scan_contacts == 123
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [
                {
                    "handle": "contacts:contact:v1:0123456789abcdef0123456789abcdef",
                    "display_name": "Synthetic Contact",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_contacts", fake_search)

    exit_code = main(
        [
            "contacts",
            "search",
            "--json",
            "--query",
            "Synthetic",
            "--limit",
            "6",
            "--max-scan-contacts",
            "123",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "contacts"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("contacts:contact:v1:")


def test_cli_contacts_get(monkeypatch, capsys) -> None:
    def fake_get(handle: str, *, max_chars: int, max_scan_contacts: int) -> dict:
        assert handle == "contacts:contact:v1:0123456789abcdef0123456789abcdef"
        assert max_chars == 50
        assert max_scan_contacts == 321
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": True, "output_tier": "content"},
            "result": {
                "handle": handle,
                "display_name": "Synthetic Contact",
                "email_addresses": [{"label": "work", "value": "synthetic@example.invalid"}],
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.get_contact", fake_get)

    exit_code = main(
        [
            "contacts",
            "get",
            "--json",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--max-chars",
            "50",
            "--max-scan-contacts",
            "321",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["email_addresses"][0]["value"] == "synthetic@example.invalid"

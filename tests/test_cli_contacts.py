from __future__ import annotations

import json

import pytest

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


def test_cli_contacts_groups(monkeypatch, capsys) -> None:
    def fake_groups(query: str, *, limit: int) -> dict:
        assert query == "Synthetic"
        assert limit == 4
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "results": [{"handle": "contacts:group:v1:abc", "name": "Synthetic Group"}],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_contact_groups", fake_groups)

    exit_code = main(
        ["contacts", "groups", "--json", "--query", "Synthetic", "--limit", "4"]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["results"][0]["handle"].startswith("contacts:group:v1:")


def test_cli_contacts_group(monkeypatch, capsys) -> None:
    def fake_group(handle: str) -> dict:
        assert handle == "contacts:group:v1:abc"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "result": {"handle": handle, "group_safe_sha256": "0" * 64},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.get_contact_group", fake_group)

    exit_code = main(["contacts", "group", "--json", "--handle", "contacts:group:v1:abc"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["group_safe_sha256"] == "0" * 64


def test_cli_contacts_group_members(monkeypatch, capsys) -> None:
    def fake_group_members(handle: str, *, limit: int) -> dict:
        assert handle == "contacts:group:v1:abc"
        assert limit == 3
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "results": [{"handle": "contacts:contact:v1:def", "display_name": "Synthetic Member"}],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.list_contact_group_members", fake_group_members)

    exit_code = main(
        ["contacts", "group-members", "--json", "--handle", "contacts:group:v1:abc", "--limit", "3"]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["results"][0]["handle"].startswith("contacts:contact:v1:")


def test_cli_contacts_count(monkeypatch, capsys) -> None:
    def fake_count(*, max_contacts: int) -> dict:
        assert max_contacts == 77
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "result": {"live_count": 3, "count_complete": True},
            "result_count": 3,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.count_contacts", fake_count)

    exit_code = main(["contacts", "count", "--json", "--max-contacts", "77"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["live_count"] == 3


def test_cli_contacts_export(monkeypatch, capsys, tmp_path) -> None:
    def fake_export(*, output_dir, filename_prefix: str, max_contacts: int) -> dict:
        assert output_dir == tmp_path / "backup"
        assert filename_prefix == "phase0"
        assert max_contacts == 88
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": {"content_inspected": True, "output_tier": "export"},
            "result": {"archive_verified": True, "live_count": 3, "counts_match": True},
            "result_count": 3,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.export_contacts_archive", fake_export)

    exit_code = main(
        [
            "contacts",
            "export",
            "--json",
            "--output-dir",
            str(tmp_path / "backup"),
            "--filename-prefix",
            "phase0",
            "--max-contacts",
            "88",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["archive_verified"] is True


def test_cli_contacts_update_omitted_methods_preserve(monkeypatch, capsys) -> None:
    def fake_plan(operation: str, **kwargs) -> dict:
        assert operation == "update"
        assert kwargs["email_addresses"] is None
        assert kwargs["phone_numbers"] is None
        assert kwargs["url_addresses"] is None
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_contact_change", fake_plan)

    exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--given-name",
            "Updated",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_append_note_forwards_exact_text(monkeypatch, capsys) -> None:
    def fake_plan(operation: str, **kwargs) -> dict:
        assert operation == "append-note"
        assert kwargs["handle"] == "contacts:contact:v1:0123456789abcdef0123456789abcdef"
        assert kwargs["expected_current_sha256"] == "0" * 64
        assert kwargs["note_text"] == "\n\nSynthetic context."
        assert kwargs["email_addresses"] is None
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_contact_change", fake_plan)

    exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "append-note",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--note-text",
            "\n\nSynthetic context.",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_set_note_forwards_exact_text(monkeypatch, capsys) -> None:
    def fake_apply(operation: str, **kwargs) -> dict:
        assert operation == "set-note"
        assert kwargs["note_text"] == "Replacement context."
        assert kwargs["approval_token"] == "contacts-apply:v1:0123456789abcdef0123456789abcdef"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_contact_change", fake_apply)

    exit_code = main(
        [
            "contacts",
            "apply",
            "--json",
            "--operation",
            "set-note",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--note-text",
            "Replacement context.",
            "--approval-token",
            "contacts-apply:v1:0123456789abcdef0123456789abcdef",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_group_member_forwards_exact_group_binding(monkeypatch, capsys) -> None:
    def fake_apply(operation: str, **kwargs) -> dict:
        assert operation == "add-group-member"
        assert kwargs["handle"] == "contacts:contact:v1:0123456789abcdef0123456789abcdef"
        assert kwargs["expected_current_sha256"] == "0" * 64
        assert kwargs["group_handle"] == "contacts:group:v1:abcdef0123456789abcdef0123456789"
        assert kwargs["expected_group_sha256"] == "1" * 64
        assert kwargs["approval_token"] == "contacts-apply:v1:0123456789abcdef0123456789abcdef"
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_contact_change", fake_apply)

    exit_code = main(
        [
            "contacts",
            "apply",
            "--json",
            "--operation",
            "add-group-member",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--group-handle",
            "contacts:group:v1:abcdef0123456789abcdef0123456789",
            "--expected-group-sha256",
            "1" * 64,
            "--approval-token",
            "contacts-apply:v1:0123456789abcdef0123456789abcdef",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_batch_forwards_exact_items(monkeypatch, capsys) -> None:
    items = [
        {
            "operation": "append_note",
            "handle": "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "expected_current_sha256": "0" * 64,
            "note_text": "\n\nBatch context.",
        }
    ]

    def fake_plan(operation: str, **kwargs) -> dict:
        assert operation == "batch"
        assert kwargs["batch_items"] == items
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_contact_change", fake_plan)

    exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "batch",
            "--batch-items-json",
            json.dumps(items),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_containers_forwards_query(monkeypatch, capsys) -> None:
    def fake_containers(query: str, *, limit: int) -> dict:
        assert query == "iCloud"
        assert limit == 3
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.cli.search_contact_containers", fake_containers)

    exit_code = main(["contacts", "containers", "--json", "--query", "iCloud", "--limit", "3"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_create_group_forwards_container(monkeypatch, capsys) -> None:
    def fake_plan(operation: str, **kwargs) -> dict:
        assert operation == "create-group"
        assert kwargs["group_name"] == "Friends"
        assert kwargs["container_handle"] == "contacts:container:v1:fixture"
        assert kwargs["expected_container_sha256"] == "0" * 64
        return {"schema_version": 1, "status": "ok", "source": "contacts", "warnings": []}

    monkeypatch.setattr("local_apple_data.cli.plan_contact_change", fake_plan)

    exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "create-group",
            "--group-name",
            "Friends",
            "--container-handle",
            "contacts:container:v1:fixture",
            "--expected-container-sha256",
            "0" * 64,
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_update_rich_json_and_image(monkeypatch, capsys, tmp_path) -> None:
    image_path = tmp_path / "avatar.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage")

    def fake_plan(operation: str, **kwargs) -> dict:
        assert operation == "update"
        assert kwargs["postal_addresses"] == [
            {"label": "home", "street": "2 New Way", "city": "Example"}
        ]
        assert kwargs["birthday"] == {"month": 1, "day": 2}
        assert kwargs["dates"] == [{"label": "anniversary", "date": {"month": 3, "day": 4}}]
        assert kwargs["social_profiles"] == [
            {"label": "work", "service": "LinkedIn", "username": "fixture"}
        ]
        assert kwargs["instant_message_addresses"] == [
            {"label": "home", "service": "Signal", "username": "fixture"}
        ]
        assert kwargs["contact_relations"] == [{"label": "assistant", "name": "Fixture Friend"}]
        assert kwargs["image_path"] == str(image_path)
        assert kwargs["clear_image"] is False
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_contact_change", fake_plan)

    exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--postal-addresses-json",
            '[{"label":"home","street":"2 New Way","city":"Example"}]',
            "--birthday-json",
            '{"month":1,"day":2}',
            "--dates-json",
            '[{"label":"anniversary","date":{"month":3,"day":4}}]',
            "--social-profiles-json",
            '[{"label":"work","service":"LinkedIn","username":"fixture"}]',
            "--instant-message-addresses-json",
            '[{"label":"home","service":"Signal","username":"fixture"}]',
            "--contact-relations-json",
            '[{"label":"assistant","name":"Fixture Friend"}]',
            "--image-path",
            str(image_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_update_method_replacements(monkeypatch, capsys) -> None:
    def fake_apply(operation: str, **kwargs) -> dict:
        assert operation == "update"
        assert kwargs["email_addresses"] == []
        assert kwargs["phone_numbers"] == [{"label": "work", "value": "+1 555 0102"}]
        assert kwargs["url_addresses"] == [{"label": "home", "value": "https://example.invalid"}]
        assert kwargs["confirm_apply"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_contact_change", fake_apply)

    exit_code = main(
        [
            "contacts",
            "apply",
            "--json",
            "--operation",
            "update",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--clear-emails",
            "--phone",
            "work=+1 555 0102",
            "--url",
            "home=https://example.invalid",
            "--approval-token",
            "contacts-apply:v1:0123456789abcdef0123456789abcdef",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_update_clear_method_arrays(monkeypatch, capsys) -> None:
    def fake_plan(operation: str, **kwargs) -> dict:
        assert operation == "update"
        assert kwargs["email_addresses"] is None
        assert kwargs["phone_numbers"] == []
        assert kwargs["url_addresses"] == []
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_contact_change", fake_plan)

    exit_code = main(
        [
            "contacts",
            "plan",
            "--json",
            "--operation",
            "update",
            "--handle",
            "contacts:contact:v1:0123456789abcdef0123456789abcdef",
            "--expected-current-sha256",
            "0" * 64,
            "--clear-phones",
            "--clear-urls",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_contacts_update_rejects_clear_and_replacement_conflict(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "contacts",
                "plan",
                "--json",
                "--operation",
                "update",
                "--handle",
                "contacts:contact:v1:0123456789abcdef0123456789abcdef",
                "--expected-current-sha256",
                "0" * 64,
                "--phone",
                "work=+1 555 0102",
                "--clear-phones",
            ]
        )

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err

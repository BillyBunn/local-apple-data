from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from local_apple_data.cli import main


def _store(store_dir: Path) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store_dir / "Data-local.sqlite") as connection:
        connection.executescript(
            """
            CREATE TABLE ZREMCDBASELIST (Z_PK INTEGER PRIMARY KEY, ZNAME VARCHAR);
            CREATE TABLE ZREMCDREMINDER (
                Z_PK INTEGER PRIMARY KEY,
                ZTITLE VARCHAR,
                ZNOTES VARCHAR,
                ZDUEDATE TIMESTAMP,
                ZDISPLAYDATEDATE TIMESTAMP,
                ZCREATIONDATE TIMESTAMP,
                ZCOMPLETED INTEGER,
                ZFLAGGED INTEGER,
                ZPRIORITY INTEGER,
                ZMARKEDFORDELETION INTEGER,
                ZLIST INTEGER
            );
            INSERT INTO ZREMCDBASELIST VALUES (1, 'Synthetic List');
            INSERT INTO ZREMCDREMINDER VALUES
              (33, 'Synthetic CLI reminder', '', 802310400, 802310400, 802300000, 0, 0, 0, 0, 1);
            """
        )


def test_cli_reminders_search_uses_synthetic_store(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    _store(tmp_path)

    exit_code = main(
        [
            "reminders",
            "search",
            "--json",
            "--query",
            "CLI",
            "--store-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "reminders"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("reminders:reminder:v1:")
    assert "Data-local" not in str(parsed["results"][0])


def test_cli_reminders_eventkit_search(monkeypatch, capsys) -> None:
    def fake_search(query: str, *, limit: int, include_completed: bool) -> dict:
        assert query == "CLI"
        assert limit == 7
        assert include_completed is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [
                {
                    "handle": "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef",
                    "title": "Synthetic CLI EventKit reminder",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_reminders_eventkit", fake_search)

    exit_code = main(
        [
            "reminders",
            "eventkit-search",
            "--json",
            "--query",
            "CLI",
            "--limit",
            "7",
            "--include-completed",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "reminders"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("reminders:reminder:eventkit:v1:")


def test_cli_reminders_request_access(monkeypatch, capsys) -> None:
    def fake_request() -> dict:
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "authorization_status": "full_access",
            "request_result": "granted",
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.request_reminders_full_access", fake_request)

    exit_code = main(["reminders", "request-access", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "reminders"
    assert parsed["authorization_status"] == "full_access"
    assert parsed["request_result"] == "granted"


def test_cli_reminders_content(monkeypatch, capsys) -> None:
    def fake_content(handle: str, *, max_chars: int) -> dict:
        assert handle == "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
        assert max_chars == 12
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": True, "output_tier": "content"},
            "result": {
                "handle": handle,
                "title": "Synthetic CLI EventKit reminder",
                "notes_text": "Synthetic no",
                "notes_chars": 12,
                "notes_truncated": True,
            },
            "result_count": 1,
            "warnings": [{"code": "content_truncated", "message": "Synthetic truncation."}],
        }

    monkeypatch.setattr("local_apple_data.cli.get_reminder_content", fake_content)

    exit_code = main(
        [
            "reminders",
            "content",
            "--json",
            "--handle",
            "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef",
            "--max-chars",
            "12",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["notes_chars"] == 12


def test_cli_reminders_lists_and_list(monkeypatch, capsys) -> None:
    def fake_lists(query: str, *, limit: int) -> dict:
        assert query == "Target"
        assert limit == 3
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [
                {
                    "handle": "reminders:list:eventkit:v1:0123456789abcdef0123456789abcdef",
                    "title": "Synthetic Target List",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    def fake_list(handle: str) -> dict:
        assert handle == "reminders:list:eventkit:v1:0123456789abcdef0123456789abcdef"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "result": {"handle": handle, "title": "Synthetic Target List"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_reminder_lists", fake_lists)
    monkeypatch.setattr("local_apple_data.cli.get_reminder_list", fake_list)

    exit_code = main(
        ["reminders", "lists", "--json", "--query", "Target", "--limit", "3"]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["results"][0]["handle"].startswith("reminders:list:eventkit:v1:")

    exit_code = main(
        [
            "reminders",
            "list",
            "--json",
            "--handle",
            "reminders:list:eventkit:v1:0123456789abcdef0123456789abcdef",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"]["title"] == "Synthetic Target List"


def test_cli_reminders_lists_without_query_enumerates_all(monkeypatch, capsys) -> None:
    def fake_list_lists(*, limit: int) -> dict:
        assert limit == 30
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "query": {"scope": "eventkit_all_lists", "limit": limit},
            "results": [
                {
                    "handle": "reminders:list:eventkit:v1:0123456789abcdef0123456789abcdef",
                    "title": "Family reminders",
                    "is_shared": True,
                    "sharee_count": 1,
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.list_reminder_lists", fake_list_lists)

    exit_code = main(["reminders", "lists", "--json", "--limit", "30"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["query"]["scope"] == "eventkit_all_lists"
    assert parsed["results"][0]["is_shared"] is True


def test_cli_reminders_list_items(monkeypatch, capsys) -> None:
    handle = "reminders:list:eventkit:v1:0123456789abcdef0123456789abcdef"

    def fake_list_items(
        list_handle: str,
        *,
        limit: int,
        include_completed: bool,
    ) -> dict:
        assert list_handle == handle
        assert limit == 4
        assert include_completed is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders_list_items",
            "privacy": {
                "content_inspected": False,
                "output_tier": "metadata",
                "list_items_returned": True,
            },
            "list": {"handle": handle, "title": "Synthetic Target List"},
            "results": [
                {
                    "handle": "reminders:reminder:eventkit:v1:fedcba9876543210fedcba9876543210",
                    "title": "Synthetic selected-list reminder",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.list_reminder_items", fake_list_items)

    exit_code = main(
        [
            "reminders",
            "list-items",
            "--json",
            "--handle",
            handle,
            "--limit",
            "4",
            "--include-completed",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "reminders_list_items"
    assert parsed["result_count"] == 1
    assert parsed["list"]["handle"] == handle


def test_cli_reminders_plan_and_apply_list(monkeypatch, capsys) -> None:
    source_handle = "reminders:list:eventkit:v1:0123456789abcdef0123456789abcdef"

    def fake_plan(
        operation: str,
        *,
        source_list_handle: str,
        list_handle: str,
        target_list_handle: str,
        list_title: str,
        new_list_title: str,
    ) -> dict:
        assert operation == "create_list"
        assert source_list_handle == source_handle
        assert list_handle == ""
        assert target_list_handle == ""
        assert list_title == "Project CLI"
        assert new_list_title == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "operation": "create_list",
                "proposed": {"list_title": "Project CLI"},
                "approval": {"approval_fingerprint": "exact-list"},
            },
            "result_count": 1,
            "warnings": [],
        }

    def fake_apply(
        operation: str,
        *,
        source_list_handle: str,
        list_handle: str,
        target_list_handle: str,
        list_title: str,
        new_list_title: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "create_list"
        assert source_list_handle == source_handle
        assert list_handle == ""
        assert target_list_handle == ""
        assert list_title == "Project CLI"
        assert new_list_title == ""
        assert approval_token == "reminders-apply:v1:exact-list"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "create_list",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"title": "Project CLI", "source_list_verified": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_reminder_list_change", fake_plan)
    monkeypatch.setattr("local_apple_data.cli.apply_reminder_list_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "plan-list",
            "--json",
            "--operation",
            "create-list",
            "--source-list-handle",
            source_handle,
            "--list-title",
            "Project CLI",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "create_list"

    exit_code = main(
        [
            "reminders",
            "apply-list",
            "--json",
            "--operation",
            "create-list",
            "--source-list-handle",
            source_handle,
            "--list-title",
            "Project CLI",
            "--approval-token",
            "reminders-apply:v1:exact-list",
            "--confirm-apply",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "create_list"
    assert parsed["read_back"]["source_list_verified"] is True


def test_cli_reminders_plan_list_delete_with_migration(monkeypatch, capsys) -> None:
    source_handle = "reminders:list:eventkit:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    target_handle = "reminders:list:eventkit:v1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    def fake_plan(
        operation: str,
        *,
        source_list_handle: str,
        list_handle: str,
        target_list_handle: str,
        list_title: str,
        new_list_title: str,
    ) -> dict:
        assert operation == "delete_list_with_migration"
        assert source_list_handle == ""
        assert list_handle == source_handle
        assert target_list_handle == target_handle
        assert list_title == ""
        assert new_list_title == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "mode": "plan",
            "preview": {"operation": "delete_list_with_migration"},
            "warnings": [],
        }

    def fake_apply(
        operation: str,
        *,
        source_list_handle: str,
        list_handle: str,
        target_list_handle: str,
        list_title: str,
        new_list_title: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "delete_list_with_migration"
        assert source_list_handle == ""
        assert list_handle == source_handle
        assert target_list_handle == target_handle
        assert list_title == ""
        assert new_list_title == ""
        assert approval_token == "reminders-apply:v1:migrate-delete"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "mode": "apply",
            "operation": "delete_list_with_migration",
            "mutation_applied": True,
            "read_back": {
                "migrated_count": 2,
                "target_count_after": 2,
                "list_absent_verified": True,
            },
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_reminder_list_change", fake_plan)
    monkeypatch.setattr("local_apple_data.cli.apply_reminder_list_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "plan-list",
            "--json",
            "--operation",
            "delete-list-with-migration",
            "--list-handle",
            source_handle,
            "--target-list-handle",
            target_handle,
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "delete_list_with_migration"

    exit_code = main(
        [
            "reminders",
            "apply-list",
            "--json",
            "--operation",
            "delete-list-with-migration",
            "--list-handle",
            source_handle,
            "--target-list-handle",
            target_handle,
            "--approval-token",
            "reminders-apply:v1:migrate-delete",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "delete_list_with_migration"
    assert parsed["read_back"]["list_absent_verified"] is True


def test_cli_reminders_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic CLI planned reminder",
            "--list-name",
            "Synthetic List",
            "--due-date",
            "2026-06-04",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "plan"
    assert parsed["mutation_applied"] is False
    assert parsed["apply_available"] is True
    assert parsed["preview"]["operation"] == "create"
    assert parsed["preview"]["proposed"]["title"] == "Synthetic CLI planned reminder"


def test_cli_reminders_apply(monkeypatch, capsys) -> None:
    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "create"
        assert title == "Synthetic CLI planned reminder"
        assert list_name == "Synthetic List"
        assert due_date == "2026-06-04"
        assert notes == "Synthetic notes."
        assert handle == ""
        assert expected_title == ""
        assert expected_completed is None
        assert expected_list_name == ""
        assert expected_list_handle == ""
        assert target_list_handle == ""
        assert expected_priority is None
        assert expected_notes_sha256 == ""
        assert priority is None
        assert url == ""
        assert expected_url_present is None
        assert expected_url_sha256 == ""
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"title": "Synthetic CLI planned reminder"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "create",
            "--title",
            "Synthetic CLI planned reminder",
            "--list-name",
            "Synthetic List",
            "--due-date",
            "2026-06-04",
            "--notes",
            "Synthetic notes.",
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["mutation_applied"] is True


def test_cli_reminders_plan_delete(capsys) -> None:
    current_hash = "0" * 64

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "delete",
            "--handle",
            "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef",
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-priority",
            "5",
            "--expected-notes-sha256",
            current_hash,
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "delete"
    assert parsed["preview"]["target"]["expected_priority"] == 5
    assert parsed["preview"]["target"]["expected_notes_sha256"] == current_hash
    assert parsed["preview"]["proposed"]["delete"] is True


def test_cli_reminders_plan_and_apply_update_url(monkeypatch, capsys) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
    url = "https://reminders.example.invalid/task"

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "update-url",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-url-present",
            "false",
            "--expected-url-sha256",
            "",
            "--url",
            url,
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "update_url"
    assert parsed["preview"]["proposed"]["url_requested"] is True
    assert parsed["preview"]["proposed"]["url_safe_sha256"]
    assert url not in str(parsed)

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "update_url"
        assert title == ""
        assert list_name == ""
        assert due_date == ""
        assert notes is None
        assert handle == reminder_handle
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert expected_list_name == ""
        assert expected_list_handle == ""
        assert target_list_handle == ""
        assert expected_priority is None
        assert expected_notes_sha256 == ""
        assert priority is None
        assert url == "https://reminders.example.invalid/task"
        assert expected_url_present == "false"
        assert expected_url_sha256 == ""
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "update_url",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"url_present": True, "url_verified": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "update-url",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-url-present",
            "false",
            "--expected-url-sha256",
            "",
            "--url",
            url,
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "update_url"
    assert parsed["read_back"]["url_verified"] is True


def test_cli_reminders_plan_and_apply_clear_url(monkeypatch, capsys) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
    current_hash = "a" * 64

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "clear-url",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-url-present",
            "true",
            "--expected-url-sha256",
            current_hash,
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "clear_url"
    assert parsed["preview"]["proposed"]["url_clear_requested"] is True

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "clear_url"
        assert title == ""
        assert list_name == ""
        assert due_date == ""
        assert notes is None
        assert handle == reminder_handle
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert expected_list_name == ""
        assert expected_list_handle == ""
        assert target_list_handle == ""
        assert expected_priority is None
        assert expected_notes_sha256 == ""
        assert priority is None
        assert url == ""
        assert expected_url_present == "true"
        assert expected_url_sha256 == current_hash
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "clear_url",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"url_present": False, "url_absent_verified": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "clear-url",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-url-present",
            "true",
            "--expected-url-sha256",
            current_hash,
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "clear_url"
    assert parsed["read_back"]["url_absent_verified"] is True


def test_cli_reminders_plan_and_apply_absolute_display_alarm(monkeypatch, capsys) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
    current_hash = "b" * 64

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "set-absolute-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "0",
            "--alarm-absolute-dates",
            "2026-06-05T16:45:00Z",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "set_absolute_display_alarm"
    assert parsed["preview"]["proposed"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "clear_display_alarm"
        assert title == ""
        assert list_name == ""
        assert due_date == ""
        assert notes is None
        assert handle == reminder_handle
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert expected_list_name == ""
        assert expected_list_handle == ""
        assert target_list_handle == ""
        assert expected_priority is None
        assert expected_notes_sha256 == ""
        assert priority is None
        assert url == ""
        assert expected_url_present is None
        assert expected_url_sha256 == ""
        assert alarm_absolute_dates is None
        assert alarm_offsets_minutes is None
        assert expected_alarms_count == 1
        assert expected_alarms_sha256 == current_hash
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "clear_display_alarm",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"alarms_count": 0, "display_alarm_cleared_verified": True},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "clear-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "1",
            "--expected-alarms-sha256",
            current_hash,
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "clear_display_alarm"
    assert parsed["read_back"]["display_alarm_cleared_verified"] is True


def test_cli_reminders_plan_and_apply_relative_display_alarm(monkeypatch, capsys) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "set-relative-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "0",
            "--alarm-offsets-minutes=-30,0",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "set_relative_display_alarm"
    assert parsed["preview"]["proposed"]["alarm_offsets_minutes"] == [-30, 0]

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "set_relative_display_alarm"
        assert handle == reminder_handle
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert alarm_absolute_dates is None
        assert alarm_offsets_minutes == [-30, 0]
        assert expected_alarms_count == 0
        assert expected_alarms_sha256 == ""
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "set_relative_display_alarm",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "alarm_offsets_minutes": [-30, 0],
                "display_alarm_verified": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "set-relative-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "0",
            "--alarm-offsets-minutes=-30,0",
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["operation"] == "set_relative_display_alarm"
    assert parsed["read_back"]["display_alarm_verified"] is True


def test_cli_reminders_plan_and_apply_mixed_display_alarm(monkeypatch, capsys) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
    current_hash = "d" * 64

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "set-mixed-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "0",
            "--alarm-offsets-minutes=-10",
            "--alarm-absolute-dates",
            "2026-06-05T16:45:00Z",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "set_mixed_display_alarm"
    assert parsed["preview"]["proposed"]["alarm_offsets_minutes"] == [-10]
    assert parsed["preview"]["proposed"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]

    apply_operations: list[str] = []

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        apply_operations.append(operation)
        assert handle == reminder_handle
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        if operation == "set_mixed_display_alarm":
            assert alarm_offsets_minutes == [-10]
            assert alarm_absolute_dates == ["2026-06-05T16:45:00Z"]
            assert expected_alarms_count == 0
            assert expected_alarms_sha256 == ""
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "privacy": {"content_inspected": False, "output_tier": "mutation"},
                "mode": "apply",
                "operation": "set_mixed_display_alarm",
                "mutation_applied": True,
                "apply_available": True,
                "read_back": {
                    "alarm_offsets_minutes": [-10],
                    "alarm_absolute_dates": ["2026-06-05T16:45:00Z"],
                    "display_alarm_verified": True,
                },
                "alarm_state_raw_returned": False,
                "result_count": 1,
                "warnings": [],
            }
        assert operation == "clear_display_alarm"
        assert alarm_offsets_minutes is None
        assert alarm_absolute_dates is None
        assert expected_alarms_count == 2
        assert expected_alarms_sha256 == current_hash
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "clear_display_alarm",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {"alarms_count": 0, "display_alarm_cleared_verified": True},
            "alarm_state_raw_returned": False,
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "set-mixed-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "0",
            "--alarm-offsets-minutes=-10",
            "--alarm-absolute-dates",
            "2026-06-05T16:45:00Z",
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["operation"] == "set_mixed_display_alarm"
    assert parsed["read_back"]["display_alarm_verified"] is True
    assert parsed["read_back"]["alarm_offsets_minutes"] == [-10]
    assert parsed["read_back"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "clear-display-alarm",
            "--handle",
            reminder_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-alarms-count",
            "2",
            "--expected-alarms-sha256",
            current_hash,
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["operation"] == "clear_display_alarm"
    assert parsed["read_back"]["display_alarm_cleared_verified"] is True
    assert apply_operations == ["set_mixed_display_alarm", "clear_display_alarm"]


def test_cli_reminders_plan_and_apply_move_to_list(monkeypatch, capsys) -> None:
    reminder_handle = "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
    current_list_handle = "reminders:list:eventkit:v1:00112233445566778899aabbccddeeff"
    target_list_handle = "reminders:list:eventkit:v1:fedcba9876543210fedcba9876543210"

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "move-to-list",
            "--handle",
            reminder_handle,
            "--target-list-handle",
            target_list_handle,
            "--expected-list-handle",
            current_list_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-list-name",
            "Inbox",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["preview"]["operation"] == "move_to_list"
    assert parsed["preview"]["target"]["expected_list_handle"] == current_list_handle
    assert parsed["preview"]["target"]["target_list_handle"] == target_list_handle
    assert parsed["preview"]["target"]["expected_list_name"] == "Inbox"
    assert parsed["preview"]["proposed"]["list_change"] is True

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "move_to_list"
        assert title == ""
        assert list_name == ""
        assert due_date == ""
        assert notes is None
        assert handle == reminder_handle
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert expected_list_name == "Inbox"
        assert expected_list_handle == current_list_handle
        assert target_list_handle == target_list_handle_arg
        assert expected_priority is None
        assert expected_notes_sha256 == ""
        assert priority is None
        assert url == ""
        assert expected_url_present is None
        assert expected_url_sha256 == ""
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "move_to_list",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "list_name": "Synthetic Target List",
                "target_list_verified": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    target_list_handle_arg = target_list_handle
    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "move-to-list",
            "--handle",
            reminder_handle,
            "--target-list-handle",
            target_list_handle,
            "--expected-list-handle",
            current_list_handle,
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-list-name",
            "Inbox",
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "move_to_list"
    assert parsed["read_back"]["list_name"] == "Synthetic Target List"
    assert parsed["read_back"]["target_list_verified"] is True


def test_cli_reminders_apply_delete(monkeypatch, capsys) -> None:
    current_hash = "1" * 64

    def fake_apply(
        operation: str,
        *,
        title: str,
        list_name: str,
        due_date: str,
        notes: str | None,
        handle: str,
        expected_title: str,
        expected_completed: str | None,
        expected_list_name: str,
        expected_list_handle: str,
        target_list_handle: str,
        expected_priority: int | None,
        expected_notes_sha256: str,
        priority: int | None,
        url: str,
        expected_url_present: str | None,
        expected_url_sha256: str,
        alarm_absolute_dates: list[str] | None,
        alarm_offsets_minutes: list[int] | None,
        expected_alarms_count: int | None,
        expected_alarms_sha256: str,
        approval_token: str,
        confirm_apply: bool,
        start_date: str = "",
        expected_start_date: str = "",
        **_recurrence_extra: object,
    ) -> dict:
        assert operation == "delete"
        assert title == ""
        assert list_name == ""
        assert due_date == ""
        assert notes is None
        assert handle == "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef"
        assert expected_title == "Synthetic CLI reminder"
        assert expected_completed == "false"
        assert expected_list_name == ""
        assert expected_list_handle == ""
        assert target_list_handle == ""
        assert expected_priority == 5
        assert expected_notes_sha256 == current_hash
        assert priority is None
        assert url == ""
        assert expected_url_present is None
        assert expected_url_sha256 == ""
        assert approval_token == "reminders-apply:v1:synthetic"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "operation": "delete",
            "mutation_applied": True,
            "apply_available": True,
            "read_back": {
                "handle": handle,
                "deleted": True,
                "verified_absent": True,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "delete",
            "--handle",
            "reminders:reminder:eventkit:v1:0123456789abcdef0123456789abcdef",
            "--expected-title",
            "Synthetic CLI reminder",
            "--expected-completed",
            "false",
            "--expected-priority",
            "5",
            "--expected-notes-sha256",
            current_hash,
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["operation"] == "delete"
    assert parsed["read_back"]["verified_absent"] is True


def test_cli_reminders_plan_create_with_start_date(monkeypatch, capsys) -> None:
    captured: dict = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "mode": "plan",
            "preview": {"operation": operation, "proposed": {"start_date": kwargs.get("start_date")}},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_reminder_change", fake_plan)

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "create-with-start-date",
            "--title",
            "Runtime start reminder",
            "--list-name",
            "Synthetic List",
            "--due-date",
            "2026-06-04",
            "--start-date",
            "2026-06-02",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "create_with_start_date"
    assert captured["start_date"] == "2026-06-02"


def test_cli_reminders_apply_update_start_date_clear(monkeypatch, capsys) -> None:
    captured: dict = {}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "mode": "apply",
            "operation": operation,
            "mutation_applied": True,
            "read_back": {"start_date_absent_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "update-start-date",
            "--handle",
            "reminders:reminder:eventkit:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--expected-title",
            "Synthetic runtime reminder",
            "--expected-start-date",
            "2026-06-02",
            "--start-date",
            "",
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "update_start_date"
    assert captured["expected_start_date"] == "2026-06-02"
    assert captured["start_date"] == ""


def test_cli_reminders_plan_create_with_recurrence(monkeypatch, capsys) -> None:
    captured: dict = {}

    def fake_plan(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "mode": "plan",
            "preview": {"operation": operation},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_reminder_change", fake_plan)

    exit_code = main(
        [
            "reminders",
            "plan",
            "--json",
            "--operation",
            "create-with-recurrence",
            "--title",
            "Runtime recurring reminder",
            "--list-name",
            "Synthetic List",
            "--due-date",
            "2026-06-04",
            "--recurrence-frequency",
            "weekly",
            "--recurrence-count",
            "4",
            "--recurrence-weekdays",
            "monday,thursday",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "create_with_recurrence"
    assert captured["recurrence_frequency"] == "weekly"
    assert captured["recurrence_count"] == 4
    assert captured["recurrence_weekdays"] == ["monday", "thursday"]


def test_cli_reminders_apply_update_recurrence_clear(monkeypatch, capsys) -> None:
    captured: dict = {}

    def fake_apply(operation: str, **kwargs: object) -> dict:
        captured["operation"] = operation
        captured.update(kwargs)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "mode": "apply",
            "operation": operation,
            "mutation_applied": True,
            "read_back": {"recurrence_cleared_verified": True},
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_reminder_change", fake_apply)

    exit_code = main(
        [
            "reminders",
            "apply",
            "--json",
            "--operation",
            "update-recurrence",
            "--handle",
            "reminders:reminder:eventkit:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--expected-title",
            "Synthetic runtime reminder",
            "--expected-recurrence-present",
            "true",
            "--expected-recurrence",
            '{"frequency": "daily", "interval": 2, "count": 6, "recurrence_present": true}',
            "--clear-recurrence",
            "--approval-token",
            "reminders-apply:v1:synthetic",
            "--confirm-apply",
        ]
    )
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert captured["operation"] == "update_recurrence"
    assert captured["clear_recurrence"] is True
    assert captured["expected_recurrence"] == {
        "frequency": "daily",
        "interval": 2,
        "count": 6,
        "recurrence_present": True,
    }

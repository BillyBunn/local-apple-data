from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from local_apple_data.adapters.reminders import (
    apply_reminder_change,
    check_reminders_schema,
    due_reminders_metadata,
    get_reminder_content,
    plan_reminder_change,
    search_reminders_eventkit,
    search_reminders_metadata,
)


def _make_reminders_store(store_dir: Path) -> Path:
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = store_dir / "Data-local.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZREMCDBASELIST (
                Z_PK INTEGER PRIMARY KEY,
                ZNAME VARCHAR
            );
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
              (30, 'Synthetic planning reminder', '', 802310400, 802310400, 802300000, 0, 1, 5, 0, 1),
              (31, 'Completed planning reminder', '', 802310401, 802310401, 802300000, 1, 0, 0, 0, 1),
              (32, 'Deleted planning reminder', '', 802310402, 802310402, 802300000, 0, 0, 0, 1, 1);
            """
        )
    return db_path


def test_check_reminders_schema(tmp_path: Path) -> None:
    _make_reminders_store(tmp_path)

    result = check_reminders_schema(store_dir=tmp_path)

    assert result["status"] == "ok"
    assert result["stores"][0]["store_ref"].startswith("reminders-store:")
    assert "Data-local" not in str(result["stores"][0])


def test_search_reminders_metadata_excludes_completed_and_deleted(tmp_path: Path) -> None:
    _make_reminders_store(tmp_path)

    result = search_reminders_metadata("planning", store_dir=tmp_path, limit=200)

    assert result["status"] == "ok"
    assert result["query"]["limit"] == 50
    assert result["result_count"] == 1
    assert result["results"][0]["handle"].startswith("reminders:reminder:v1:")
    assert result["results"][0]["store_ref"].startswith("reminders-store:")
    assert "Data-local" not in str(result["results"][0])
    assert result["results"][0]["title"] == "Synthetic planning reminder"


def test_search_reminders_metadata_rejects_empty_query(tmp_path: Path) -> None:
    _make_reminders_store(tmp_path)

    result = search_reminders_metadata("\t", store_dir=tmp_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "empty_query"


def test_search_reminders_metadata_rejects_low_quality_query(tmp_path: Path) -> None:
    _make_reminders_store(tmp_path)

    result = search_reminders_metadata("%", store_dir=tmp_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "broad_query"


def test_check_reminders_schema_degrades_without_stores(tmp_path: Path) -> None:
    result = check_reminders_schema(store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "reminders_store_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_reminders_schema_warning_does_not_expose_store_filename(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(tmp_path / "Data-local.sqlite") as connection:
        connection.execute("CREATE TABLE ZREMCDREMINDER (Z_PK INTEGER PRIMARY KEY)")

    result = check_reminders_schema(store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "reminders_schema_unavailable"
    assert "Data-local" not in result["warnings"][0]["message"]
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_due_reminders_metadata_uses_bounded_window(tmp_path: Path) -> None:
    _make_reminders_store(tmp_path)

    result = due_reminders_metadata(
        store_dir=tmp_path,
        days=14,
        now=datetime(2026, 6, 6, tzinfo=UTC),
    )

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "due"
    assert result["result_count"] == 1
    assert result["results"][0]["title"] == "Synthetic planning reminder"


def test_due_reminders_metadata_caps_window_and_limit(tmp_path: Path) -> None:
    _make_reminders_store(tmp_path)

    result = due_reminders_metadata(
        store_dir=tmp_path,
        days=365,
        limit=200,
        now=datetime(2026, 6, 6, tzinfo=UTC),
    )

    assert result["query"]["days"] == 31
    assert result["query"]["limit"] == 50


def _eventkit_runner(payload: dict, _timeout: float) -> dict:
    if payload["command"] == "reminders":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminders": [
                {
                    "reminder_id": "runtime-reminder-1",
                    "title": "Synthetic runtime reminder",
                    "list_name": "Synthetic List",
                    "due_date": "2026-06-04T17:00:00.000Z",
                    "start_date": "",
                    "completed": False,
                    "priority": 5,
                    "notes_present": True,
                    "url_present": False,
                    "alarms_count": 1,
                    "notes": "Search must not expose this note body.",
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "reminder_by_id":
        assert payload["reminder_id"] == "runtime-reminder-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "notes": "Synthetic reminder notes.",
            },
            "warnings": [],
        }
    raise AssertionError(f"unexpected EventKit command: {payload['command']}")


def test_search_reminders_eventkit_returns_metadata_only() -> None:
    result = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "eventkit_title"
    assert result["result_count"] == 1
    reminder = result["results"][0]
    assert reminder["handle"].startswith("reminders:reminder:eventkit:v1:")
    assert reminder["notes_present"] is True
    assert "runtime-reminder-1" not in str(result)
    assert "Search must not expose" not in str(result)


def test_search_reminders_eventkit_rejects_broad_query_without_runner() -> None:
    called = False

    def runner(_payload: dict, _timeout: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = search_reminders_eventkit("%", eventkit_runner=runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"
    assert called is False


def test_get_reminder_content_returns_exact_notes_and_truncates() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = get_reminder_content(
        handle,
        max_chars=10,
        eventkit_runner=_eventkit_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["notes_text"] == "Synthetic "
    assert result["result"]["notes_chars"] == 10
    assert result["result"]["notes_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"
    assert "runtime-reminder-1" not in str(result)


def test_get_reminder_content_rejects_raw_or_sqlite_handles() -> None:
    result = get_reminder_content("reminders:reminder:v1:0123456789abcdef0123456789abcdef")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_reminders_eventkit_degrades_without_access() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "authorization_status": "denied",
            "reminders": [],
            "warnings": [
                {
                    "code": "reminders_access_unavailable",
                    "message": "Reminders access is not authorized for this process.",
                }
            ],
        }

    result = search_reminders_eventkit("runtime", eventkit_runner=runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "reminders_access_unavailable"


def test_plan_reminder_change_create_returns_preview_only() -> None:
    result = plan_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
        due_date="2026-06-04T17:00:00-07:00",
        notes="Synthetic note text.",
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "create"
    assert preview["target"] == {"list_name": "Synthetic List"}
    assert preview["proposed"]["title"] == "Synthetic planned reminder"
    assert preview["proposed"]["due_date"] == "2026-06-05T00:00:00Z"
    assert preview["proposed"]["notes_chars"] == 20
    assert preview["idempotency_key"].startswith("reminders-plan:v1:")
    assert preview["approval"]["required_for_apply"] is True
    assert preview["approval"]["apply_tool_available"] is True
    assert preview["approval"]["approval_token_format"] == (
        "reminders-apply:v1:<approval_fingerprint>"
    )


def test_plan_reminder_change_complete_requires_eventkit_handle() -> None:
    result = plan_reminder_change(
        "complete",
        handle="reminders:reminder:v1:0123456789abcdef0123456789abcdef",
        expected_title="Synthetic planned reminder",
        expected_completed=False,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_reminder_change_update_due_date_uses_exact_handle() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "update-due-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        due_date="2026-06-06",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "update_due_date"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_title"] == "Synthetic runtime reminder"
    assert preview["target"]["expected_completed"] is False
    assert preview["proposed"]["due_date"] == "2026-06-06"


def test_plan_reminder_change_rejects_oversized_notes() -> None:
    result = plan_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
        notes="x" * 12001,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "input_too_large"


def _approval_token(plan: dict) -> str:
    fingerprint = plan["preview"]["approval"]["approval_fingerprint"]
    return f"reminders-apply:v1:{fingerprint}"


def test_apply_reminder_change_requires_confirmation_before_runner() -> None:
    called = False
    plan = plan_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
    )

    def runner(_payload: dict, _timeout: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = apply_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
        approval_token=_approval_token(plan),
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"
    assert called is False


def test_apply_reminder_change_rejects_wrong_approval_token() -> None:
    called = False

    def runner(_payload: dict, _timeout: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = apply_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
        approval_token="reminders-apply:v1:not-the-plan",
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert called is False


def test_apply_reminder_change_create_calls_eventkit_and_reads_back() -> None:
    plan = plan_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        notes="Synthetic notes.",
    )

    def runner(payload: dict, _timeout: float) -> dict:
        assert payload == {
            "command": "reminder_apply_change",
            "operation": "create",
            "title": "Synthetic planned reminder",
            "list_name": "Synthetic List",
            "due_date": "2026-06-04",
            "notes": "Synthetic notes.",
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": "created-reminder-1",
                "title": "Synthetic planned reminder",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T00:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 0,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 0,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "create",
        title="Synthetic planned reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        notes="Synthetic notes.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["handle"].startswith("reminders:reminder:eventkit:v1:")
    assert result["read_back"]["title"] == "Synthetic planned reminder"
    assert "created-reminder-1" not in str(result)


def test_apply_reminder_change_complete_resolves_exact_handle_and_applies() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "complete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "complete"
        assert payload["reminder_id"] == "runtime-reminder-1"
        assert payload["expected_title"] == "Synthetic runtime reminder"
        assert payload["expected_completed"] is False
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": True,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "complete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["completed"] is True
    assert calls == ["reminders", "reminder_apply_change"]
    assert "runtime-reminder-1" not in str(result)


def test_apply_reminder_change_update_due_date_propagates_helper_warning() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "update_due_date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        due_date="2026-06-06",
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        assert payload["operation"] == "update_due_date"
        assert payload["due_date"] == "2026-06-06"
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": None,
            "warnings": [
                {
                    "code": "expected_state_mismatch",
                    "message": "Reminder due date did not match expected state.",
                }
            ],
        }

    result = apply_reminder_change(
        "update_due_date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        due_date="2026-06-06",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"

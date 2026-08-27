from __future__ import annotations

import sqlite3
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import local_apple_data.adapters.reminders as reminders_adapter
from local_apple_data.adapters.reminders import (
    apply_reminder_list_change,
    apply_reminder_change,
    check_reminders_schema,
    due_reminders_metadata,
    get_reminder_content,
    get_reminder_list,
    list_reminder_items,
    list_reminder_lists,
    plan_reminder_list_change,
    plan_reminder_change,
    request_reminders_full_access,
    search_reminder_lists,
    search_reminders_eventkit,
    search_reminders_metadata,
)
from local_apple_data.handles import make_opaque_handle


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


def test_request_reminders_full_access_uses_eventkit_helper() -> None:
    recorded: dict[str, Any] = {}

    def request_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        recorded["payload"] = payload
        recorded["timeout"] = timeout
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "full_access",
            "request_result": "granted",
            "warnings": [],
        }

    result = request_reminders_full_access(eventkit_runner=request_runner)

    assert recorded["payload"] == {"command": "request_reminders_full_access"}
    assert recorded["timeout"] == 190.0
    assert result["status"] == "ok"
    assert result["authorization_status"] == "full_access"
    assert result["request_result"] == "granted"
    assert result["privacy"]["content_inspected"] is False


def test_request_reminders_full_access_returns_safe_error_on_helper_failure() -> None:
    def failed_runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        raise ValueError("raw helper path HOME/private/EventKitHelper.app failed")

    result = request_reminders_full_access(eventkit_runner=failed_runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "unavailable"
    assert result["warnings"][0]["code"] == "eventkit_unavailable"
    assert "HOME/private" not in str(result)


def test_request_reminders_full_access_returns_safe_timeout() -> None:
    def timeout_runner(_payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        raise subprocess.TimeoutExpired(["open"], timeout)

    result = request_reminders_full_access(eventkit_runner=timeout_runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "timeout"
    assert result["warnings"][0]["code"] == "reminders_access_request_timeout"


def test_request_reminders_full_access_provisions_only_on_real_path(monkeypatch) -> None:
    # With a mocked runner the signing prepare hook must NOT fire — it runs only
    # on the real eventkit_runner=None path. Guards against dropping the
    # `if eventkit_runner is None` gate (which would provision/rebuild/block on a
    # prompt from an ordinary call).
    monkeypatch.setattr(
        reminders_adapter,
        "_prepare_eventkit_helper_signing",
        lambda: (_ for _ in ()).throw(
            AssertionError("prepare fired with a mocked runner")
        ),
    )

    def _runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {"status": "ok", "authorization_status": "full_access", "warnings": []}

    result = request_reminders_full_access(eventkit_runner=_runner)

    assert result["status"] == "ok"


def test_reminders_read_path_never_provisions(monkeypatch) -> None:
    # A Reminders read must never reach the signing provision/prepare hooks.
    monkeypatch.setattr(
        reminders_adapter,
        "_prepare_eventkit_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("read path prepared signing")),
    )

    def _runner(_payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {"status": "ok", "results": [], "warnings": []}

    result = search_reminders_eventkit("groceries", eventkit_runner=_runner)

    assert result["status"] in {"ok", "degraded", "error"}


def test_reminders_eventkit_runner_uses_stable_helper_app(monkeypatch) -> None:
    recorded: dict[str, Any] = {}

    def app_runner(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        recorded["payload"] = payload
        recorded["timeout"] = timeout
        return {"status": "ok"}

    monkeypatch.setattr(reminders_adapter, "_run_eventkit_helper_app", app_runner)

    result = reminders_adapter._run_eventkit_helper({"command": "reminder_lists"}, 3.0)

    assert result == {"status": "ok"}
    assert recorded["payload"] == {"command": "reminder_lists"}
    assert recorded["timeout"] == 3.0


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
    assert (
        result["warnings"][0]["message"]
        == "Reminders local store is unavailable or unreadable."
    )
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_reminders_schema_warning_does_not_expose_store_filename(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(tmp_path / "Data-local.sqlite") as connection:
        connection.execute("CREATE TABLE ZREMCDREMINDER (Z_PK INTEGER PRIMARY KEY)")

    result = check_reminders_schema(store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "reminders_schema_unavailable"
    assert result["warnings"][0]["message"] == (
        f"{reminders_adapter._store_ref('Data-local.sqlite')}: "
        "Reminders schema is unavailable or unsupported."
    )
    assert "Data-local" not in result["warnings"][0]["message"]
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_search_reminders_metadata_store_warning_uses_generic_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_store_paths(_store_dir: Path) -> list[Path]:
        raise reminders_adapter.StoreUnavailableError(
            f"permission denied for {tmp_path / 'Stores'}"
        )

    monkeypatch.setattr(reminders_adapter, "_store_paths", fail_store_paths)

    result = search_reminders_metadata("planning", store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "reminders_store_unavailable",
            "message": "Reminders local store is unavailable or unreadable.",
        }
    ]


def test_search_reminders_metadata_query_warning_uses_generic_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_reminders_store(tmp_path)

    def fail_query_store(
        _path: Path,
        _sql: str,
        _params: tuple[object, ...],
        _limit: int,
    ) -> list[dict]:
        raise reminders_adapter.StoreUnavailableError(
            f"permission denied for {tmp_path / 'Data-local.sqlite'}"
        )

    monkeypatch.setattr(reminders_adapter, "_query_store", fail_query_store)

    result = search_reminders_metadata("planning", store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "reminders_store_query_failed",
            "message": (
                f"{reminders_adapter._store_ref('Data-local.sqlite')}: "
                "Reminders local store could not be queried safely."
            ),
        }
    ]


def test_due_reminders_metadata_store_warning_uses_generic_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_store_paths(_store_dir: Path) -> list[Path]:
        raise reminders_adapter.StoreUnavailableError(
            f"permission denied for {tmp_path / 'Stores'}"
        )

    monkeypatch.setattr(reminders_adapter, "_store_paths", fail_store_paths)

    result = due_reminders_metadata(store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "reminders_store_unavailable",
            "message": "Reminders local store is unavailable or unreadable.",
        }
    ]


def test_due_reminders_metadata_query_warning_uses_generic_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_reminders_store(tmp_path)

    def fail_query_store(
        _path: Path,
        _sql: str,
        _params: tuple[object, ...],
        _limit: int,
    ) -> list[dict]:
        raise reminders_adapter.StoreUnavailableError(
            f"permission denied for {tmp_path / 'Data-local.sqlite'}"
        )

    monkeypatch.setattr(reminders_adapter, "_query_store", fail_query_store)

    result = due_reminders_metadata(store_dir=tmp_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "reminders_store_query_failed",
            "message": (
                f"{reminders_adapter._store_ref('Data-local.sqlite')}: "
                "Reminders local store could not be queried safely."
            ),
        }
    ]


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
    if payload["command"] == "reminder_lists":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "lists": [
                {
                    "list_id": "synthetic-list-1",
                    "title": "Synthetic List",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["reminder"],
                    "reminder_count": 1 if payload.get("include_counts") else 0,
                },
                {
                    "list_id": "synthetic-list-2",
                    "title": "Synthetic Target List",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["reminder"],
                    "reminder_count": 0,
                },
                {
                    "list_id": "synthetic-list-test",
                    "title": "Project Old",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["reminder"],
                    "reminder_count": 0,
                },
                {
                    "list_id": "synthetic-list-busy",
                    "title": "Project Busy",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["reminder"],
                    "reminder_count": 2 if payload.get("include_counts") else 0,
                },
            ],
            "warnings": [],
        }
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
                    "list_id": "synthetic-list-1",
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
    if payload["command"] == "reminders_for_list":
        assert payload["list_id"] in {"synthetic-list-1", "synthetic-list-2"}
        reminders = [
            {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": payload["list_id"],
                "list_name": "Synthetic List"
                if payload["list_id"] == "synthetic-list-1"
                else "Synthetic Target List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": True,
                "url_safe_sha256": "raw-url-proof-must-not-return",
                "alarms_count": 1,
                "alarm_absolute_dates": ["2026-06-04T16:30:00.000Z"],
                "notes": "List-items must not expose this note body.",
            },
            {
                "reminder_id": "runtime-reminder-2",
                "title": "Completed runtime reminder",
                "list_id": payload["list_id"],
                "list_name": "Synthetic List"
                if payload["list_id"] == "synthetic-list-1"
                else "Synthetic Target List",
                "due_date": "2026-06-05T17:00:00.000Z",
                "start_date": "",
                "completed": True,
                "priority": 0,
                "notes_present": False,
                "url_present": False,
                "alarms_count": 0,
            },
        ]
        if not payload.get("include_completed"):
            reminders = [item for item in reminders if not item["completed"]]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "list": {
                "list_id": payload["list_id"],
                "title": "Synthetic List"
                if payload["list_id"] == "synthetic-list-1"
                else "Synthetic Target List",
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "local",
                "source_id": "source-1",
                "source_type": "local",
                "allowed_entity_types": ["reminder"],
                "reminder_count": len(reminders),
            },
            "reminders": reminders[: payload["limit"]],
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
                "list_id": "synthetic-list-1",
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
            "target_list_verified": True,
            "warnings": [],
        }
    raise AssertionError(f"unexpected EventKit command: {payload['command']}")


def test_search_reminder_lists_returns_opaque_handles_without_ids() -> None:
    result = search_reminder_lists("Synthetic", eventkit_runner=_eventkit_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "eventkit_list_title"
    assert result["result_count"] == 4
    reminder_list = result["results"][0]
    assert reminder_list["handle"].startswith("reminders:list:eventkit:v1:")
    assert reminder_list["title"] == "Synthetic List"
    assert "synthetic-list-1" not in str(result)
    assert "list_id" not in str(result)


def _sharing_eventkit_runner(payload: dict, _timeout: float) -> dict:
    # Mirrors the helper contract: is_shared always present when detection
    # works; sharee_count only when positive.
    response = _eventkit_runner(payload, _timeout)
    for item in response.get("lists", []):
        shared = item["title"] == "Synthetic List"
        item["is_shared"] = shared
        if shared:
            item["sharee_count"] = 1
    return response


def test_list_reminder_lists_enumerates_all_lists_without_query() -> None:
    result = list_reminder_lists(eventkit_runner=_eventkit_runner)

    assert result["status"] == "ok"
    assert result["query"] == {"scope": "eventkit_all_lists", "limit": 20}
    assert result["result_count"] == 4
    assert {item["title"] for item in result["results"]} == {
        "Synthetic List",
        "Synthetic Target List",
        "Project Old",
        "Project Busy",
    }
    for item in result["results"]:
        assert item["handle"].startswith("reminders:list:eventkit:v1:")
    assert "synthetic-list-1" not in str(result)
    assert "list_id" not in str(result)
    assert result["warnings"] == []


def test_list_reminder_lists_caps_limit_and_flags_truncation() -> None:
    truncated = list_reminder_lists(limit=2, eventkit_runner=_eventkit_runner)

    assert truncated["status"] == "ok"
    assert truncated["result_count"] == 2
    assert truncated["warnings"][0]["code"] == "results_truncated"

    capped = list_reminder_lists(limit=200, eventkit_runner=_eventkit_runner)

    assert capped["query"]["limit"] == 50
    assert capped["warnings"] == []


def test_list_reminder_lists_degrades_safely_without_eventkit() -> None:
    def failing_runner(_payload: dict, _timeout: float) -> dict:
        raise ValueError("raw helper path HOME/private/EventKitHelper.app failed")

    result = list_reminder_lists(eventkit_runner=failing_runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "eventkit_unavailable"
    assert "HOME/private" not in str(result)


def test_reminder_list_metadata_exposes_sharing_state() -> None:
    result = list_reminder_lists(eventkit_runner=_sharing_eventkit_runner)
    by_title = {item["title"]: item for item in result["results"]}

    assert by_title["Synthetic List"]["is_shared"] is True
    assert by_title["Synthetic List"]["sharee_count"] == 1
    assert by_title["Synthetic Target List"]["is_shared"] is False
    assert "sharee_count" not in by_title["Synthetic Target List"]

    search = search_reminder_lists("Synthetic", eventkit_runner=_sharing_eventkit_runner)
    search_by_title = {item["title"]: item for item in search["results"]}
    assert search_by_title["Synthetic List"]["is_shared"] is True

    detail = get_reminder_list(
        by_title["Synthetic List"]["handle"],
        eventkit_runner=_sharing_eventkit_runner,
    )
    assert detail["result"]["is_shared"] is True
    assert detail["result"]["sharee_count"] == 1


def test_reminder_list_metadata_sharing_unknown_when_helper_omits_it() -> None:
    # An older helper payload without sharing keys must read back as unknown
    # (None), never as a false "not shared".
    result = list_reminder_lists(eventkit_runner=_eventkit_runner)

    assert all(item["is_shared"] is None for item in result["results"])
    assert all("sharee_count" not in item for item in result["results"])


def test_get_reminder_list_returns_exact_metadata() -> None:
    search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    handle = next(
        item["handle"]
        for item in search["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = get_reminder_list(handle, eventkit_runner=_eventkit_runner)

    assert result["status"] == "ok"
    assert result["result"]["handle"] == handle
    assert result["result"]["title"] == "Synthetic Target List"
    assert "synthetic-list-2" not in str(result)


def test_list_reminder_items_requires_list_handle() -> None:
    result = list_reminder_items("reminders:reminder:eventkit:v1:bad", eventkit_runner=_eventkit_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"
    assert result["result_count"] == 0


def test_list_reminder_items_returns_selected_list_metadata_only() -> None:
    search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    handle = next(
        item["handle"]
        for item in search["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = list_reminder_items(handle, limit=1, eventkit_runner=_eventkit_runner)

    assert result["status"] == "ok"
    assert result["source"] == "reminders_list_items"
    assert result["privacy"]["list_items_returned"] is True
    assert result["privacy"]["reminder_notes_returned"] is False
    assert result["privacy"]["raw_identifier_returned"] is False
    assert result["privacy"]["reminder_url_returned"] is False
    assert result["privacy"]["reminder_alarm_details_returned"] is False
    assert result["query"] == {
        "scope": "selected_list_items",
        "limit": 1,
        "include_completed": False,
    }
    assert result["list"]["handle"] == handle
    assert result["list"]["title"] == "Synthetic Target List"
    assert result["result_count"] == 1
    assert result["results"][0]["title"] == "Synthetic runtime reminder"
    assert result["results"][0]["handle"].startswith("reminders:reminder:eventkit:v1:")
    assert result["results"][0]["list_handle"] == handle
    assert "List-items must not expose" not in str(result)
    assert "raw-url-proof-must-not-return" not in str(result)
    assert "alarm_absolute_dates" not in str(result)
    assert "synthetic-list-2" not in str(result)
    assert "runtime-reminder-1" not in str(result)


def test_list_reminder_items_resolves_handle_without_broad_count_scan() -> None:
    handle = make_opaque_handle("reminders:list:eventkit", "synthetic-list-2")
    payloads: list[dict[str, Any]] = []

    def recording_runner(payload: dict, timeout: float) -> dict:
        payloads.append(dict(payload))
        return _eventkit_runner(payload, timeout)

    result = list_reminder_items(handle, eventkit_runner=recording_runner)

    assert result["status"] == "ok"
    assert payloads[0] == {
        "command": "reminder_lists",
        "query": "",
        "limit": reminders_adapter.DEFAULT_EVENTKIT_SCAN_LIMIT,
        "include_counts": False,
    }
    assert payloads[1]["command"] == "reminders_for_list"
    assert payloads[1]["list_id"] == "synthetic-list-2"


def test_list_reminder_items_can_include_completed_when_explicit() -> None:
    search = search_reminder_lists("Synthetic List", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = list_reminder_items(
        handle,
        include_completed=True,
        eventkit_runner=_eventkit_runner,
    )

    assert result["status"] == "ok"
    assert result["result_count"] == 2
    assert [item["completed"] for item in result["results"]] == [False, True]


def test_plan_reminder_list_create_binds_source_and_list_title() -> None:
    source_handle = search_reminder_lists("Synthetic", eventkit_runner=_eventkit_runner)["results"][0]["handle"]

    result = plan_reminder_list_change(
        "create-list",
        source_list_handle=source_handle,
        list_title="Project New",
        eventkit_runner=_eventkit_runner,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "create_list"
    assert preview["target"]["source_list_handle"] == source_handle
    assert preview["proposed"]["list_title"] == "Project New"
    assert preview["approval"]["approval_token_format"] == "reminders-apply:v1:<approval_fingerprint>"
    assert "source-1" not in str(result)


def test_plan_reminder_list_create_refuses_non_reminder_source() -> None:
    source_handle = make_opaque_handle("reminders:list:eventkit", "mixed-source-list")

    def runner(payload: dict, _timeout: float) -> dict:
        assert payload["command"] == "reminder_lists"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "lists": [
                {
                    "list_id": "mixed-source-list",
                    "title": "Mixed Source",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["event", "reminder"],
                }
            ],
            "warnings": [],
        }

    result = plan_reminder_list_change(
        "create-list",
        source_list_handle=source_handle,
        list_title="Project New",
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_list_source"


def test_plan_reminder_list_rename_requires_exact_empty_list() -> None:
    handle = next(
        item["handle"]
        for item in search_reminder_lists("Project Old", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Project Old"
    )

    result = plan_reminder_list_change(
        "rename-list",
        list_handle=handle,
        new_list_title="Project New",
        eventkit_runner=_eventkit_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["target"]["list_handle"] == handle
    assert result["preview"]["target"]["reminder_count"] == 0
    assert result["preview"]["proposed"]["new_list_title"] == "Project New"
    assert "synthetic-list-test" not in str(result)


def test_plan_reminder_list_delete_refuses_non_empty() -> None:
    handle = next(
        item["handle"]
        for item in search_reminder_lists("Project Busy", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Project Busy"
    )

    result = plan_reminder_list_change(
        "delete-list",
        list_handle=handle,
        eventkit_runner=_eventkit_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "list_not_empty"


def test_plan_reminder_list_delete_with_migration_binds_same_source_target() -> None:
    source_handle = next(
        item["handle"]
        for item in search_reminder_lists("Project Busy", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Project Busy"
    )
    target_handle = next(
        item["handle"]
        for item in search_reminder_lists("Target", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = plan_reminder_list_change(
        "delete-list-with-migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        eventkit_runner=_eventkit_runner,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "delete_list_with_migration"
    assert preview["target"]["list_handle"] == source_handle
    assert preview["target"]["reminder_count"] == 2
    assert preview["proposed"]["target_list_handle"] == target_handle
    assert preview["proposed"]["target_list_title"] == "Synthetic Target List"
    assert preview["proposed"]["migrated_reminder_count"] == 2
    assert preview["proposed"]["target_reminder_count"] == 0
    assert "synthetic-list-busy" not in str(result)
    assert "synthetic-list-2" not in str(result)


def test_plan_reminder_list_delete_with_migration_refuses_cross_source() -> None:
    source_handle = make_opaque_handle("reminders:list:eventkit", "source-list")
    target_handle = make_opaque_handle("reminders:list:eventkit", "target-list")

    def runner(payload: dict, _timeout: float) -> dict:
        assert payload["command"] == "reminder_lists"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "lists": [
                {
                    "list_id": "source-list",
                    "title": "Source",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-1",
                    "source_type": "local",
                    "allowed_entity_types": ["reminder"],
                    "reminder_count": 1,
                },
                {
                    "list_id": "target-list",
                    "title": "Target",
                    "allows_content_modifications": True,
                    "is_subscribed": False,
                    "is_immutable": False,
                    "calendar_type": "local",
                    "source_id": "source-2",
                    "source_type": "local",
                    "allowed_entity_types": ["reminder"],
                    "reminder_count": 0,
                },
            ],
            "warnings": [],
        }

    result = plan_reminder_list_change(
        "delete-list-with-migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "cross_source_list_migration_refused"


def test_apply_reminder_list_create_calls_eventkit_and_reads_back() -> None:
    source_handle = search_reminder_lists("Synthetic", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_list_change(
        "create-list",
        source_list_handle=source_handle,
        list_title="Project New",
        eventkit_runner=_eventkit_runner,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminder_lists":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_list_apply_change"
        assert payload["operation"] == "create_list"
        assert payload["source_list_id"] == "synthetic-list-1"
        assert payload["list_title"] == "Project New"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "list": {
                "list_id": "created-list",
                "title": "Project New",
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "local",
                "source_id": "source-1",
                "source_type": "local",
                "allowed_entity_types": ["reminder"],
                "reminder_count": 0,
            },
            "read_back": {"source_list_verified": True, "list_empty_verified": True},
            "warnings": [],
        }

    result = apply_reminder_list_change(
        "create-list",
        source_list_handle=source_handle,
        list_title="Project New",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "create_list"
    assert result["read_back"]["title"] == "Project New"
    assert result["read_back"]["source_list_verified"] is True
    assert calls == ["reminder_lists", "reminder_lists", "reminder_list_apply_change"]
    assert "created-list" not in str(result)


def test_apply_reminder_list_create_requires_source_read_back_match() -> None:
    source_handle = search_reminder_lists("Synthetic", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_list_change(
        "create-list",
        source_list_handle=source_handle,
        list_title="Project New",
        eventkit_runner=_eventkit_runner,
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminder_lists":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_list_apply_change"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "list": {
                "list_id": "created-list",
                "title": "Project New",
                "allows_content_modifications": True,
                "is_subscribed": False,
                "is_immutable": False,
                "calendar_type": "local",
                "source_id": "unexpected-source",
                "source_type": "local",
                "allowed_entity_types": ["reminder"],
                "reminder_count": 0,
            },
            "read_back": {"source_list_verified": True, "list_empty_verified": True},
            "warnings": [],
        }

    result = apply_reminder_list_change(
        "create-list",
        source_list_handle=source_handle,
        list_title="Project New",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "list_create_read_back_mismatch"


def test_apply_reminder_list_delete_requires_absence_proof() -> None:
    handle = next(
        item["handle"]
        for item in search_reminder_lists("Project Old", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Project Old"
    )
    plan = plan_reminder_list_change(
        "delete-list",
        list_handle=handle,
        eventkit_runner=_eventkit_runner,
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminder_lists":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_list_apply_change"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "list": None,
            "read_back": {
                "list_deleted_verified": True,
                "list_absent_verified": False,
                "list_empty_verified": True,
            },
            "warnings": [],
        }

    result = apply_reminder_list_change(
        "delete-list",
        list_handle=handle,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "list_delete_read_back_mismatch"


def test_apply_reminder_list_delete_with_migration_calls_eventkit_and_reads_back() -> None:
    source_handle = next(
        item["handle"]
        for item in search_reminder_lists("Project Busy", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Project Busy"
    )
    target_handle = next(
        item["handle"]
        for item in search_reminder_lists("Target", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_list_change(
        "delete-list-with-migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        eventkit_runner=_eventkit_runner,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminder_lists":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_list_apply_change"
        assert payload["operation"] == "delete_list_with_migration"
        assert payload["list_id"] == "synthetic-list-busy"
        assert payload["target_list_id"] == "synthetic-list-2"
        assert payload["expected_list_title"] == "Project Busy"
        assert payload["expected_target_list_title"] == "Synthetic Target List"
        assert payload["expected_migration_count"] == 2
        assert payload["expected_target_count"] == 0
        assert payload["migrate_before_delete"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "list": None,
            "read_back": {
                "list_migrated_verified": True,
                "migrated_count": 2,
                "target_count_before": 0,
                "target_count_after": 2,
                "source_list_empty_verified": True,
                "target_list_verified": True,
                "list_deleted_verified": True,
                "list_absent_verified": True,
            },
            "warnings": [],
        }

    result = apply_reminder_list_change(
        "delete-list-with-migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "delete_list_with_migration"
    assert result["read_back"]["migrated_count"] == 2
    assert result["read_back"]["target_count_after"] == 2
    assert result["read_back"]["list_absent_verified"] is True
    assert calls == [
        "reminder_lists",
        "reminder_lists",
        "reminder_lists",
        "reminder_lists",
        "reminder_list_apply_change",
    ]
    assert "synthetic-list-busy" not in str(result)
    assert "synthetic-list-2" not in str(result)


def test_apply_reminder_list_delete_with_migration_requires_migration_proof() -> None:
    source_handle = next(
        item["handle"]
        for item in search_reminder_lists("Project Busy", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Project Busy"
    )
    target_handle = next(
        item["handle"]
        for item in search_reminder_lists("Target", eventkit_runner=_eventkit_runner)["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_list_change(
        "delete-list-with-migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        eventkit_runner=_eventkit_runner,
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminder_lists":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_list_apply_change"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "list": None,
            "read_back": {
                "list_migrated_verified": True,
                "migrated_count": 1,
                "target_count_before": 0,
                "target_count_after": 1,
                "source_list_empty_verified": True,
                "target_list_verified": True,
                "list_deleted_verified": True,
                "list_absent_verified": True,
            },
            "warnings": [],
        }

    result = apply_reminder_list_change(
        "delete-list-with-migration",
        list_handle=source_handle,
        target_list_handle=target_handle,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "list_delete_read_back_mismatch"


def test_get_reminder_list_rejects_reminder_handle() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)

    result = get_reminder_list(search["results"][0]["handle"], eventkit_runner=_eventkit_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_reminders_eventkit_returns_metadata_only() -> None:
    result = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "eventkit_title"
    assert result["result_count"] == 1
    reminder = result["results"][0]
    assert reminder["handle"].startswith("reminders:reminder:eventkit:v1:")
    assert reminder["list_handle"].startswith("reminders:list:eventkit:v1:")
    assert reminder["notes_present"] is True
    assert "runtime-reminder-1" not in str(result)
    assert "synthetic-list-1" not in str(result)
    assert "list_id" not in str(result)
    assert "Search must not expose" not in str(result)
    assert "url_safe_sha256" not in reminder


def test_search_reminders_eventkit_strips_url_hash_from_metadata() -> None:
    def runner(payload, timeout_seconds):
        assert timeout_seconds > 0
        assert payload["command"] == "reminders"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminders": [
                {
                    "reminder_id": "runtime-reminder-url",
                    "title": "Synthetic runtime reminder URL",
                    "list_id": "synthetic-list-url",
                    "list_name": "Synthetic List",
                    "due_date": "",
                    "start_date": "",
                    "completed": False,
                    "priority": 0,
                    "notes_present": False,
                    "url_present": True,
                    "url_safe_sha256": "a" * 64,
                    "alarms_count": 0,
                }
            ],
            "warnings": [],
        }

    result = search_reminders_eventkit("runtime", eventkit_runner=runner)

    assert result["status"] == "ok"
    reminder = result["results"][0]
    assert reminder["url_present"] is True
    assert "url_safe_sha256" not in reminder


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

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is True
        return _eventkit_runner(payload, timeout)

    result = get_reminder_content(
        handle,
        max_chars=10,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["notes_text"] == "Synthetic "
    assert result["result"]["notes_chars"] == 10
    assert result["result"]["notes_truncated"] is True
    assert result["result"]["notes_sha256"] == hashlib.sha256(
        "Synthetic reminder notes.".encode("utf-8")
    ).hexdigest()
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


def test_plan_reminder_change_update_title_uses_exact_handle() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "update-title",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        title="Synthetic renamed reminder",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "update_title"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_title"] == "Synthetic runtime reminder"
    assert preview["target"]["expected_completed"] is False
    assert preview["proposed"]["title"] == "Synthetic renamed reminder"


def test_plan_reminder_change_update_notes_requires_expected_hash() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "update-notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        notes="Replacement synthetic notes.",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"


def test_plan_reminder_change_update_notes_binds_replacement_hash() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = hashlib.sha256("Synthetic reminder notes.".encode("utf-8")).hexdigest()

    result = plan_reminder_change(
        "update_notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_notes_sha256=current_hash,
        notes="Replacement synthetic notes.",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "update_notes"
    assert preview["target"]["expected_notes_sha256"] == current_hash
    assert preview["proposed"]["notes_chars"] == 28
    assert preview["proposed"]["notes_sha256"] == hashlib.sha256(
        "Replacement synthetic notes.".encode("utf-8")
    ).hexdigest()


def test_plan_reminder_change_update_notes_allows_clearing_notes() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = hashlib.sha256("Synthetic reminder notes.".encode("utf-8")).hexdigest()

    result = plan_reminder_change(
        "update_notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_notes_sha256=current_hash,
        notes="",
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["notes_text"] == ""
    assert result["preview"]["proposed"]["notes_present"] is False


def test_plan_reminder_change_update_priority_requires_expected_priority() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "update_priority",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        priority=1,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"


def test_plan_reminder_change_update_priority_binds_expected_priority() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "update_priority",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        priority=1,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "update_priority"
    assert preview["target"]["expected_priority"] == 5
    assert preview["proposed"]["priority"] == 1


def test_plan_reminder_change_update_url_binds_hash_without_raw_url() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    url = "https://reminders.example.invalid/task"

    result = plan_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "update_url"
    assert preview["target"]["expected_url_present"] is False
    assert preview["target"]["expected_url_sha256"] == ""
    assert preview["proposed"]["url_requested"] is True
    assert preview["proposed"]["url_scheme"] == "https"
    assert preview["proposed"]["url_domain"] == "reminders.example.invalid"
    assert preview["proposed"]["url_safe_sha256"] == hashlib.sha256(url.encode("utf-8")).hexdigest()
    assert url not in str(result)


def test_plan_reminder_change_update_url_rejects_unsafe_shapes() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    for url in [
        "file:///tmp/private",
        "https://user:pass@example.invalid/task",
        " https://example.invalid/task",
        "https://example.invalid/task ",
        "https://example.invalid/has space",
        "https://example.invalid/\x01",
        "https://example.invalid/\x7f",
        "https://éxample.invalid/ü",
        "https://example.invalid:99999/task",
        "mailto:user%40example.invalid",
        "mailto:first@example.invalid,second@example.invalid",
    ]:
        result = plan_reminder_change(
            "update_url",
            handle=handle,
            expected_title="Synthetic runtime reminder",
            expected_completed=False,
            expected_url_present=False,
            url=url,
        )
        assert result["status"] == "error"
        assert result["warnings"][0]["code"] == "invalid_url"

    overlong = plan_reminder_change(
        "update_url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url="https://example.invalid/" + ("a" * 2049),
    )
    assert overlong["status"] == "error"
    assert overlong["warnings"][0]["code"] == "input_too_large"


def test_plan_reminder_change_clear_url_requires_expected_url_hash() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    missing = plan_reminder_change(
        "clear-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=True,
    )
    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_required_field"

    result = plan_reminder_change(
        "clear-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=True,
        expected_url_sha256="a" * 64,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "clear_url"
    assert result["preview"]["target"]["expected_url_present"] is True
    assert result["preview"]["target"]["expected_url_sha256"] == "a" * 64
    assert result["preview"]["proposed"]["url_clear_requested"] is True


def test_plan_reminder_change_url_requires_expected_completed() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = hashlib.sha256(b"https://reminders.example.invalid/task").hexdigest()

    update = plan_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_url_present=False,
        url="https://reminders.example.invalid/task",
    )
    clear = plan_reminder_change(
        "clear-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_url_present=True,
        expected_url_sha256=current_hash,
    )

    assert update["status"] == "error"
    assert update["warnings"][0]["code"] == "missing_required_field"
    assert "expected_completed" in update["warnings"][0]["message"]
    assert clear["status"] == "error"
    assert clear["warnings"][0]["code"] == "missing_required_field"
    assert "expected_completed" in clear["warnings"][0]["message"]


def test_plan_reminder_change_set_absolute_display_alarm_binds_dates() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z", "2026-06-05T16:45:00+00:00"],
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "set_absolute_display_alarm"
    assert preview["target"]["expected_alarms_count"] == 0
    assert preview["target"]["expected_alarms_sha256"] == ""
    assert preview["proposed"]["alarm_kind"] == "absolute"
    assert preview["proposed"]["alarm_action"] == "display"
    assert preview["proposed"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
    assert preview["proposed"]["alarms_count"] == 1


def test_plan_reminder_change_absolute_display_alarm_rejects_invalid_dates() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    missing = plan_reminder_change(
        "set_absolute_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
    )
    naive = plan_reminder_change(
        "set_absolute_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00"],
    )
    overlong = plan_reminder_change(
        "set_absolute_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=[f"2026-06-05T16:{minute:02d}:00Z" for minute in range(9)],
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_required_field"
    assert naive["status"] == "error"
    assert naive["warnings"][0]["code"] == "invalid_alarm_absolute_dates"
    assert overlong["status"] == "error"
    assert overlong["warnings"][0]["code"] == "too_many_alarm_absolute_dates"


def test_plan_reminder_change_set_relative_display_alarm_binds_offsets() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "set-relative-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[0, -10, -10],
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "set_relative_display_alarm"
    assert preview["target"]["expected_alarms_count"] == 0
    assert preview["target"]["expected_alarms_sha256"] == ""
    assert preview["proposed"]["alarm_kind"] == "relative"
    assert preview["proposed"]["alarm_action"] == "display"
    assert preview["proposed"]["alarm_offsets_minutes"] == [-10, 0]
    assert preview["proposed"]["alarms_count"] == 2


def test_plan_reminder_change_relative_display_alarm_rejects_invalid_offsets() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    missing = plan_reminder_change(
        "set_relative_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
    )
    non_integer = plan_reminder_change(
        "set_relative_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-10, True],
    )
    out_of_range = plan_reminder_change(
        "set_relative_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[40321],
    )
    overlong = plan_reminder_change(
        "set_relative_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=list(range(9)),
    )
    absolute_dates = plan_reminder_change(
        "set_relative_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        alarm_offsets_minutes=[-10],
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_required_field"
    assert non_integer["status"] == "error"
    assert non_integer["warnings"][0]["code"] == "invalid_alarm_offsets"
    assert out_of_range["status"] == "error"
    assert out_of_range["warnings"][0]["code"] == "invalid_alarm_offset_range"
    assert overlong["status"] == "error"
    assert overlong["warnings"][0]["code"] == "too_many_alarm_offsets"
    assert absolute_dates["status"] == "error"
    assert absolute_dates["warnings"][0]["code"] == "unsupported_alarm_dates_for_operation"


def test_plan_reminder_change_set_mixed_display_alarm_binds_offsets_and_dates() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[0, -10, -10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z", "2026-06-05T16:45:00+00:00"],
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "set_mixed_display_alarm"
    assert preview["target"]["expected_alarms_count"] == 0
    assert preview["target"]["expected_alarms_sha256"] == ""
    assert preview["proposed"]["alarm_kind"] == "mixed"
    assert preview["proposed"]["alarm_action"] == "display"
    assert preview["proposed"]["alarm_offsets_minutes"] == [-10, 0]
    assert preview["proposed"]["alarm_absolute_dates"] == ["2026-06-05T16:45:00Z"]
    assert preview["proposed"]["alarms_count"] == 3


def test_plan_reminder_change_mixed_display_alarm_rejects_invalid_shapes() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    missing_offsets = plan_reminder_change(
        "set_mixed_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )
    missing_dates = plan_reminder_change(
        "set_mixed_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-10],
    )
    combined_overlong = plan_reminder_change(
        "set_mixed_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-50, -40, -30, -20, -10],
        alarm_absolute_dates=[f"2026-06-05T16:{minute:02d}:00Z" for minute in range(4)],
    )
    missing_proof = plan_reminder_change(
        "set_mixed_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        alarm_offsets_minutes=[-10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )

    assert missing_offsets["status"] == "error"
    assert missing_offsets["warnings"][0]["code"] == "missing_required_field"
    assert missing_dates["status"] == "error"
    assert missing_dates["warnings"][0]["code"] == "missing_required_field"
    assert combined_overlong["status"] == "error"
    assert combined_overlong["warnings"][0]["code"] == "too_many_alarms"
    assert missing_proof["status"] == "error"
    assert missing_proof["warnings"][0]["code"] == "missing_required_field"


def test_plan_reminder_change_single_kind_display_alarm_shapes_unchanged() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    absolute_plan = plan_reminder_change(
        "set_absolute_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )
    relative_plan = plan_reminder_change(
        "set_relative_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-30, 0],
    )
    absolute_with_offsets = plan_reminder_change(
        "set_absolute_display_alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        alarm_offsets_minutes=[-10],
    )

    assert absolute_plan["status"] == "ok"
    assert absolute_plan["preview"]["proposed"]["alarm_kind"] == "absolute"
    assert "alarm_offsets_minutes" not in absolute_plan["preview"]["proposed"]
    assert relative_plan["status"] == "ok"
    assert relative_plan["preview"]["proposed"]["alarm_kind"] == "relative"
    assert "alarm_absolute_dates" not in relative_plan["preview"]["proposed"]
    assert absolute_with_offsets["status"] == "error"
    assert absolute_with_offsets["warnings"][0]["code"] == "unsupported_alarm_offsets_for_operation"


def test_plan_reminder_change_clear_display_alarm_requires_expected_hash() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    missing = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=1,
    )
    zero = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
    )
    result = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=1,
        expected_alarms_sha256="a" * 64,
    )

    assert missing["status"] == "error"
    assert missing["warnings"][0]["code"] == "missing_required_field"
    assert zero["status"] == "error"
    assert zero["warnings"][0]["code"] == "missing_required_field"
    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "clear_display_alarm"
    assert result["preview"]["target"]["expected_alarms_count"] == 1
    assert result["preview"]["target"]["expected_alarms_sha256"] == "a" * 64
    assert result["preview"]["proposed"]["alarm_clear_requested"] is True


def test_plan_reminder_change_move_to_list_binds_exact_handles() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = plan_reminder_change(
        "move-to-list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "move_to_list"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_list_handle"] == current_list_handle
    assert preview["target"]["target_list_handle"] == target_list_handle
    assert preview["target"]["expected_list_name"] == "Synthetic List"
    assert preview["proposed"]["list_change"] is True


def test_plan_reminder_change_move_to_list_requires_exact_list_handle() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    current_list_handle = search["results"][0]["list_handle"]

    result = plan_reminder_change(
        "move_to_list",
        handle=search["results"][0]["handle"],
        expected_list_handle=current_list_handle,
        target_list_handle="Synthetic Target List",
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_target_handle"


def test_plan_reminder_change_move_to_list_requires_exact_current_list_handle() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = plan_reminder_change(
        "move_to_list",
        handle=search["results"][0]["handle"],
        expected_list_handle="Synthetic List",
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_expected_list_handle"


def test_plan_reminder_change_move_to_list_requires_expected_completed() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = plan_reminder_change(
        "move_to_list",
        handle=search["results"][0]["handle"],
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_list_name="Synthetic List",
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"


def test_plan_reminder_change_update_priority_rejects_out_of_range_priority() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "update_priority",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_priority=5,
        priority=10,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_priority"


def test_plan_reminder_change_delete_requires_exact_expected_state() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    missing = plan_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
    )

    assert missing["status"] == "error"
    assert {warning["code"] for warning in missing["warnings"]} == {"missing_required_field"}

    result = plan_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=hashlib.sha256(
            "Synthetic reminder notes.".encode("utf-8")
        ).hexdigest(),
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "delete"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_title"] == "Synthetic runtime reminder"
    assert preview["target"]["expected_completed"] is False
    assert preview["target"]["expected_priority"] == 5
    assert preview["proposed"]["delete"] is True


def test_plan_reminder_change_delete_rejects_raw_identifier() -> None:
    result = plan_reminder_change(
        "delete",
        handle="runtime-reminder-1",
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=hashlib.sha256(
            "Synthetic reminder notes.".encode("utf-8")
        ).hexdigest(),
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_reminder_change_uncomplete_uses_exact_handle() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]

    result = plan_reminder_change(
        "uncomplete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=True,
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "uncomplete"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["expected_title"] == "Synthetic runtime reminder"
    assert preview["target"]["expected_completed"] is True
    assert preview["proposed"]["completed"] is False


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
    assert result["preview"] is None
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"
    assert "approval_fingerprint" not in str(result)
    assert "approval_token_format" not in str(result)
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
    assert result["preview"] is None
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert "approval_fingerprint" not in str(result)
    assert "approval_token_format" not in str(result)
    assert called is False


def test_apply_reminder_change_move_to_list_invalid_token_hides_plan_target_fields() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )

    result = apply_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
        approval_token="reminders-apply:v1:not-the-plan",
        confirm_apply=True,
        eventkit_runner=_eventkit_runner,
    )

    serialized = str(result)
    assert result["status"] == "error"
    assert result["preview"] is None
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert "approval_fingerprint" not in serialized
    assert "approval_token_format" not in serialized
    assert handle not in serialized
    assert current_list_handle not in serialized
    assert target_list_handle not in serialized
    assert "Synthetic runtime reminder" not in serialized
    assert "Synthetic List" not in serialized
    assert "Synthetic Target List" not in serialized


def test_apply_reminder_change_update_url_invalid_token_hides_url() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    url = "https://reminders.example.invalid/private-token"

    result = apply_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
        approval_token="reminders-apply:v1:not-the-plan",
        confirm_apply=True,
        eventkit_runner=_eventkit_runner,
    )

    serialized = str(result)
    assert result["status"] == "error"
    assert result["preview"] is None
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"
    assert "approval_fingerprint" not in serialized
    assert "approval_token_format" not in serialized
    assert url not in serialized
    assert "reminders.example.invalid" not in serialized
    assert handle not in serialized
    assert "Synthetic runtime reminder" not in serialized


def test_apply_reminder_change_updates_url_with_hash_read_back() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    url = "mailto:task@example.invalid"
    plan = plan_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
    )
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_url_proof"] is True
            return _eventkit_runner(payload, timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "update_url"
        assert payload["url"] == url
        assert payload["expected_url_present"] is False
        assert payload["expected_url_sha256"] == ""
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": True,
                "url_safe_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "update_url"
    assert result["url_raw_returned"] is False
    assert result["read_back"]["url_present"] is True
    assert result["read_back"]["url_verified"] is True
    assert result["read_back"]["url_safe_sha256"] == hashlib.sha256(url.encode("utf-8")).hexdigest()
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]
    assert url not in str(result)


def test_apply_reminder_change_clears_url_with_absence_proof() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_url = "https://reminders.example.invalid/task"
    current_hash = hashlib.sha256(current_url.encode("utf-8")).hexdigest()
    plan = plan_reminder_change(
        "clear-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=True,
        expected_url_sha256=current_hash,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_url_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["url_present"] = True
            response["reminder"]["url_safe_sha256"] = current_hash
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "clear_url"
        assert payload["expected_url_present"] is True
        assert payload["expected_url_sha256"] == current_hash
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "clear-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=True,
        expected_url_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "clear_url"
    assert result["url_raw_returned"] is False
    assert result["read_back"]["url_present"] is False
    assert result["read_back"]["url_absent_verified"] is True


def test_apply_reminder_change_update_url_refuses_stale_current_url() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    url = "https://reminders.example.invalid/task"
    plan = plan_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
    )
    apply_called = False

    def runner(payload: dict, timeout: float) -> dict:
        nonlocal apply_called
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["url_present"] = True
            response["reminder"]["url_safe_sha256"] = "b" * 64
            return response
        apply_called = True
        return {}

    result = apply_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"
    assert apply_called is False


def test_apply_reminder_change_update_url_mismatch_is_apply_unknown() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    url = "https://reminders.example.invalid/task"
    plan = plan_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_url_proof"] is True
            return _eventkit_runner(payload, timeout)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": True,
                "url_safe_sha256": "c" * 64,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "update-url",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_url_present=False,
        url=url,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "url_read_back_mismatch"


def test_apply_reminder_change_sets_absolute_display_alarm_with_read_back() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    alarm_dates = ["2026-06-05T16:45:00Z"]
    plan = plan_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=alarm_dates,
    )
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 0
            response["reminder"]["alarms_safe_sha256"] = ""
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "set_absolute_display_alarm"
        assert payload["expected_alarms_count"] == 0
        assert payload["expected_alarms_sha256"] == ""
        assert payload["alarm_absolute_dates"] == alarm_dates
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "alarms_safe_sha256": "b" * 64,
                "alarm_absolute_dates": ["2026-06-05T16:45:00.000Z"],
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=alarm_dates,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "set_absolute_display_alarm"
    assert result["alarm_state_raw_returned"] is False
    assert result["read_back"]["alarm_absolute_dates"] == alarm_dates
    assert result["read_back"]["display_alarm_verified"] is True
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]


def test_apply_reminder_change_sets_relative_display_alarm_with_read_back() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    alarm_offsets = [-30, 0]
    plan = plan_reminder_change(
        "set-relative-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=alarm_offsets,
    )
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 0
            response["reminder"]["alarms_safe_sha256"] = ""
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "set_relative_display_alarm"
        assert payload["expected_alarms_count"] == 0
        assert payload["expected_alarms_sha256"] == ""
        assert payload["alarm_offsets_minutes"] == alarm_offsets
        assert "alarm_absolute_dates" not in payload
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 2,
                "alarms_safe_sha256": "f" * 64,
                "alarm_offsets_minutes": alarm_offsets,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-relative-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=alarm_offsets,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "set_relative_display_alarm"
    assert result["alarm_state_raw_returned"] is False
    assert result["read_back"]["alarm_offsets_minutes"] == alarm_offsets
    assert result["read_back"]["display_alarm_verified"] is True
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]


def test_apply_reminder_change_clears_display_alarm_with_absence_proof() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = "c" * 64
    plan = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=1,
        expected_alarms_sha256=current_hash,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 1
            response["reminder"]["alarms_safe_sha256"] = current_hash
            response["reminder"]["alarm_absolute_dates"] = ["2026-06-05T16:45:00Z"]
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "clear_display_alarm"
        assert payload["expected_alarms_count"] == 1
        assert payload["expected_alarms_sha256"] == current_hash
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 0,
                "alarms_safe_sha256": "",
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=1,
        expected_alarms_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "clear_display_alarm"
    assert result["read_back"]["alarms_count"] == 0
    assert result["read_back"]["display_alarm_cleared_verified"] is True


def test_apply_reminder_change_clears_relative_display_alarm_with_absence_proof() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = "a" * 64
    plan = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        expected_alarms_sha256=current_hash,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 2
            response["reminder"]["alarms_safe_sha256"] = current_hash
            response["reminder"]["alarm_offsets_minutes"] = [-30, 0]
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "clear_display_alarm"
        assert payload["expected_alarms_count"] == 2
        assert payload["expected_alarms_sha256"] == current_hash
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 0,
                "alarms_safe_sha256": "",
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        expected_alarms_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "clear_display_alarm"
    assert result["read_back"]["alarms_count"] == 0
    assert result["read_back"]["display_alarm_cleared_verified"] is True


def test_apply_reminder_change_sets_mixed_display_alarm_with_read_back() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    alarm_offsets = [-10]
    alarm_dates = ["2026-06-05T16:45:00Z"]
    plan = plan_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=alarm_offsets,
        alarm_absolute_dates=alarm_dates,
    )
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 0
            response["reminder"]["alarms_safe_sha256"] = ""
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "set_mixed_display_alarm"
        assert payload["expected_alarms_count"] == 0
        assert payload["expected_alarms_sha256"] == ""
        assert payload["alarm_offsets_minutes"] == alarm_offsets
        assert payload["alarm_absolute_dates"] == alarm_dates
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 2,
                "alarms_safe_sha256": "b" * 64,
                "alarm_offsets_minutes": alarm_offsets,
                "alarm_absolute_dates": ["2026-06-05T16:45:00.000Z"],
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=alarm_offsets,
        alarm_absolute_dates=alarm_dates,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "set_mixed_display_alarm"
    assert result["alarm_state_raw_returned"] is False
    assert result["read_back"]["alarm_offsets_minutes"] == alarm_offsets
    assert result["read_back"]["alarm_absolute_dates"] == alarm_dates
    assert result["read_back"]["display_alarm_verified"] is True
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]


def test_apply_reminder_change_sets_mixed_display_alarm_from_absolute_state() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = "f" * 64
    alarm_offsets = [-10]
    alarm_dates = ["2026-06-05T16:45:00Z"]
    plan = plan_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=1,
        expected_alarms_sha256=current_hash,
        alarm_offsets_minutes=alarm_offsets,
        alarm_absolute_dates=alarm_dates,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 1
            response["reminder"]["alarms_safe_sha256"] = current_hash
            response["reminder"]["alarm_absolute_dates"] = ["2026-06-05T16:45:00Z"]
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "set_mixed_display_alarm"
        assert payload["expected_alarms_count"] == 1
        assert payload["expected_alarms_sha256"] == current_hash
        assert payload["alarm_offsets_minutes"] == alarm_offsets
        assert payload["alarm_absolute_dates"] == alarm_dates
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 2,
                "alarms_safe_sha256": "c" * 64,
                "alarm_offsets_minutes": alarm_offsets,
                "alarm_absolute_dates": alarm_dates,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=1,
        expected_alarms_sha256=current_hash,
        alarm_offsets_minutes=alarm_offsets,
        alarm_absolute_dates=alarm_dates,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "set_mixed_display_alarm"
    assert result["alarm_state_raw_returned"] is False
    assert result["read_back"]["alarm_offsets_minutes"] == alarm_offsets
    assert result["read_back"]["alarm_absolute_dates"] == alarm_dates
    assert result["read_back"]["display_alarm_verified"] is True


def test_apply_reminder_change_clears_mixed_display_alarm_with_absence_proof() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = "d" * 64
    plan = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        expected_alarms_sha256=current_hash,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 2
            response["reminder"]["alarms_safe_sha256"] = current_hash
            response["reminder"]["alarm_offsets_minutes"] = [-10]
            response["reminder"]["alarm_absolute_dates"] = ["2026-06-05T16:45:00Z"]
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "clear_display_alarm"
        assert payload["expected_alarms_count"] == 2
        assert payload["expected_alarms_sha256"] == current_hash
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 0,
                "alarms_safe_sha256": "",
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        expected_alarms_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "clear_display_alarm"
    assert result["read_back"]["alarms_count"] == 0
    assert result["read_back"]["display_alarm_cleared_verified"] is True


def test_apply_reminder_change_mixed_alarm_refuses_stale_current_state() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )
    apply_called = False

    def runner(payload: dict, timeout: float) -> dict:
        nonlocal apply_called
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 1
            response["reminder"]["alarms_safe_sha256"] = "e" * 64
            return response
        apply_called = True
        return {}

    result = apply_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"
    assert apply_called is False


def test_apply_reminder_change_mixed_alarm_mismatch_is_apply_unknown() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 0
            response["reminder"]["alarms_safe_sha256"] = ""
            return response
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 2,
                "alarms_safe_sha256": "a" * 64,
                "alarm_offsets_minutes": [-30],
                "alarm_absolute_dates": ["2026-06-05T16:45:00Z"],
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-mixed-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-10],
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "alarm_read_back_mismatch"


def test_apply_reminder_change_clear_display_alarm_refuses_unsupported_alarm_state() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = "b" * 64
    plan = plan_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        expected_alarms_sha256=current_hash,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 2
            response["reminder"]["alarms_safe_sha256"] = current_hash
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "clear_display_alarm"
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": False,
            "warnings": [
                {
                    "code": "unsupported_alarm_state",
                    "message": "Reminder alarm state is not a supported display-alarm state.",
                }
            ],
        }

    result = apply_reminder_change(
        "clear-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=2,
        expected_alarms_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "unsupported_alarm_state"


def test_apply_reminder_change_alarm_refuses_stale_current_state() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )
    apply_called = False

    def runner(payload: dict, timeout: float) -> dict:
        nonlocal apply_called
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            assert payload["include_alarm_proof"] is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 1
            response["reminder"]["alarms_safe_sha256"] = "d" * 64
            return response
        apply_called = True
        return {}

    result = apply_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"
    assert apply_called is False


def test_apply_reminder_change_alarm_mismatch_is_apply_unknown() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 0
            response["reminder"]["alarms_safe_sha256"] = ""
            return response
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "alarms_safe_sha256": "e" * 64,
                "alarm_absolute_dates": ["2026-06-05T17:45:00Z"],
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-absolute-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_absolute_dates=["2026-06-05T16:45:00Z"],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "alarm_read_back_mismatch"


def test_apply_reminder_change_relative_alarm_mismatch_is_apply_unknown() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "set-relative-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-30],
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["alarms_count"] = 0
            response["reminder"]["alarms_safe_sha256"] = ""
            return response
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": True,
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
                "alarms_safe_sha256": "f" * 64,
                "alarm_offsets_minutes": [-10],
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "set-relative-display-alarm",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_alarms_count=0,
        alarm_offsets_minutes=[-30],
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "alarm_read_back_mismatch"


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


def test_apply_reminder_change_uncomplete_resolves_exact_handle_and_applies() -> None:
    def completed_eventkit_runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminders":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": "authorized",
                "reminders": [
                    {
                        "reminder_id": "runtime-reminder-2",
                        "title": "Synthetic completed runtime reminder",
                        "list_name": "Synthetic List",
                        "due_date": "2026-06-04T17:00:00.000Z",
                        "start_date": "",
                        "completed": True,
                        "priority": 5,
                        "notes_present": True,
                        "url_present": False,
                        "alarms_count": 1,
                    }
                ],
                "warnings": [],
            }
        raise AssertionError(f"unexpected EventKit command: {payload['command']}")

    search = search_reminders_eventkit(
        "completed runtime",
        eventkit_runner=completed_eventkit_runner,
    )
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "uncomplete",
        handle=handle,
        expected_title="Synthetic completed runtime reminder",
        expected_completed=True,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return completed_eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "uncomplete"
        assert payload["reminder_id"] == "runtime-reminder-2"
        assert payload["expected_title"] == "Synthetic completed runtime reminder"
        assert payload["expected_completed"] is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": "runtime-reminder-2",
                "title": "Synthetic completed runtime reminder",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "uncomplete",
        handle=handle,
        expected_title="Synthetic completed runtime reminder",
        expected_completed=True,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["completed"] is False
    assert calls == ["reminders", "reminder_apply_change"]
    assert "runtime-reminder-2" not in str(result)


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


def test_apply_reminder_change_update_title_resolves_exact_handle_and_applies() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "update_title",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        title="Synthetic renamed reminder",
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "update_title"
        assert payload["reminder_id"] == "runtime-reminder-1"
        assert payload["expected_title"] == "Synthetic runtime reminder"
        assert payload["expected_completed"] is False
        assert payload["title"] == "Synthetic renamed reminder"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic renamed reminder",
                "list_name": "Synthetic List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "update_title",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        title="Synthetic renamed reminder",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["title"] == "Synthetic renamed reminder"
    assert calls == ["reminders", "reminder_apply_change"]
    assert "runtime-reminder-1" not in str(result)


def test_apply_reminder_change_update_notes_checks_current_hash_and_applies() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = hashlib.sha256("Synthetic reminder notes.".encode("utf-8")).hexdigest()
    plan = plan_reminder_change(
        "update_notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_notes_sha256=current_hash,
        notes="Replacement synthetic notes.",
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is True
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "update_notes"
        assert payload["reminder_id"] == "runtime-reminder-1"
        assert payload["expected_title"] == "Synthetic runtime reminder"
        assert payload["expected_completed"] is False
        assert payload["notes"] == "Replacement synthetic notes."
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
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "update_notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_notes_sha256=current_hash,
        notes="Replacement synthetic notes.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["notes_present"] is True
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]
    assert "runtime-reminder-1" not in str(result)
    assert "Replacement synthetic notes." not in str(result["read_back"])


def test_apply_reminder_change_update_notes_refuses_changed_current_hash() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    stale_hash = hashlib.sha256("Different synthetic notes.".encode("utf-8")).hexdigest()
    plan = plan_reminder_change(
        "update_notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_notes_sha256=stale_hash,
        notes="Replacement synthetic notes.",
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is True
            return _eventkit_runner(payload, _timeout)
        raise AssertionError("apply should not run after note hash mismatch")

    result = apply_reminder_change(
        "update_notes",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_notes_sha256=stale_hash,
        notes="Replacement synthetic notes.",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_notes_changed"
    assert calls == ["reminders", "reminder_by_id"]


def test_apply_reminder_change_update_priority_resolves_exact_handle_and_applies() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    plan = plan_reminder_change(
        "update_priority",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        priority=1,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "update_priority"
        assert payload["reminder_id"] == "runtime-reminder-1"
        assert payload["expected_title"] == "Synthetic runtime reminder"
        assert payload["expected_completed"] is False
        assert payload["expected_priority"] == 5
        assert payload["priority"] == 1
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
                "completed": False,
                "priority": 1,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "update_priority",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        priority=1,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["priority"] == 1
    assert calls == ["reminders", "reminder_apply_change"]
    assert "runtime-reminder-1" not in str(result)


def test_apply_reminder_change_move_to_list_resolves_exact_handles_and_applies() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] in {"reminders", "reminder_lists"}:
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "move_to_list"
        assert payload["reminder_id"] == "runtime-reminder-1"
        assert payload["expected_list_id"] == "synthetic-list-1"
        assert payload["target_list_id"] == "synthetic-list-2"
        assert payload["target_list_title"] == "Synthetic Target List"
        assert payload["expected_title"] == "Synthetic runtime reminder"
        assert payload["expected_completed"] is False
        assert payload["expected_list_name"] == "Synthetic List"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-2",
                "list_name": "Synthetic Target List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "target_list_verified": True,
            "warnings": [],
        }

    result = apply_reminder_change(
        "move-to-list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "move_to_list"
    assert result["read_back"]["list_name"] == "Synthetic Target List"
    assert result["read_back"]["target_list_verified"] is True
    assert calls == ["reminders", "reminder_lists", "reminder_apply_change"]
    assert "runtime-reminder-1" not in str(result)
    assert "synthetic-list-2" not in str(result)


def test_apply_reminder_change_move_to_list_rejects_unverified_target_identity() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] in {"reminders", "reminder_lists"}:
            return _eventkit_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "reminder": {
                "reminder_id": "runtime-reminder-1",
                "title": "Synthetic runtime reminder",
                "list_id": "synthetic-list-1",
                "list_name": "Synthetic Target List",
                "due_date": "2026-06-04T17:00:00.000Z",
                "start_date": "",
                "completed": False,
                "priority": 5,
                "notes_present": True,
                "url_present": False,
                "alarms_count": 1,
            },
            "target_list_verified": False,
            "warnings": [],
        }

    result = apply_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_target_mismatch"


def _apply_move_with_failing_helper(base_runner) -> dict:
    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] in {"reminders", "reminder_lists"}:
            return base_runner(payload, _timeout)
        assert payload["command"] == "reminder_apply_change"
        return {
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "authorization_status": "authorized",
            "mutation_applied": False,
            "warnings": [],
        }

    search = search_reminders_eventkit("runtime", eventkit_runner=runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )
    return apply_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )


def test_apply_reminder_change_move_from_shared_list_returns_specific_warning() -> None:
    result = _apply_move_with_failing_helper(_sharing_eventkit_runner)

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "shared_list_move_unsupported"
    assert "shared list" in result["warnings"][0]["message"]
    assert "delete" in result["warnings"][0]["message"]


def test_apply_reminder_change_move_failure_stays_generic_when_source_not_shared() -> None:
    result = _apply_move_with_failing_helper(_eventkit_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "eventkit_apply_failed"
    assert all(
        warning["code"] != "shared_list_move_unsupported"
        for warning in result["warnings"]
    )


def test_apply_reminder_change_move_to_list_rejects_missing_target_before_helper() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    list_search = search_reminder_lists("Target", eventkit_runner=_eventkit_runner)
    target_list_handle = next(
        item["handle"]
        for item in list_search["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_lists":
            response = _eventkit_runner(payload, _timeout)
            response["lists"] = [
                item for item in response["lists"] if item["list_id"] != "synthetic-list-2"
            ]
            return response
        raise AssertionError(f"unexpected command {payload['command']}")

    result = apply_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"] == [
        {
            "code": "target_list_not_found",
            "message": "Reminder target list was not found through EventKit.",
        }
    ]


def test_apply_reminder_change_move_to_list_rejects_same_title_wrong_current_list() -> None:
    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_lists":
            lists = [
                {
                    "list_id": "synthetic-list-1",
                    "title": "Synthetic List",
                },
                {
                    "list_id": "synthetic-list-2",
                    "title": "Synthetic Target List",
                },
                {
                    "list_id": "synthetic-list-3",
                    "title": "Synthetic List",
                },
            ]
            query = str(payload.get("query") or "").casefold()
            if query:
                lists = [item for item in lists if query in item["title"].casefold()]
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": "authorized",
                "lists": lists,
                "warnings": [],
            }
        if payload["command"] == "reminder_apply_change":
            assert payload["operation"] == "move_to_list"
            assert payload["expected_list_id"] == "synthetic-list-3"
            assert payload["target_list_id"] == "synthetic-list-2"
            assert payload["expected_list_name"] == "Synthetic List"
            return {
                "schema_version": 1,
                "status": "error",
                "source": "reminders",
                "authorization_status": "authorized",
                "warnings": [
                    {
                        "code": "expected_state_mismatch",
                        "message": "Reminder list did not match expected state.",
                    }
                ],
            }
        raise AssertionError(f"unexpected command {payload['command']}")

    search = search_reminders_eventkit("runtime", eventkit_runner=runner)
    handle = search["results"][0]["handle"]
    current_list_handle = search["results"][0]["list_handle"]
    same_title_lists = search_reminder_lists("Synthetic List", eventkit_runner=runner)
    wrong_current_list_handle = next(
        item["handle"]
        for item in same_title_lists["results"]
        if item["handle"] != current_list_handle
    )
    target_list_handle = next(
        item["handle"]
        for item in search_reminder_lists("Target", eventkit_runner=runner)["results"]
        if item["title"] == "Synthetic Target List"
    )
    plan = plan_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=wrong_current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
    )

    result = apply_reminder_change(
        "move_to_list",
        handle=handle,
        expected_list_handle=wrong_current_list_handle,
        target_list_handle=target_list_handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_list_name="Synthetic List",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


def test_eventkit_helper_rejects_cross_account_list_move() -> None:
    helper_text = Path("scripts/eventkit_helper.swift").read_text(encoding="utf-8")

    assert "cross_account_list_move" in helper_text
    assert "reminder.calendar.source.sourceIdentifier != targetList.source.sourceIdentifier" in helper_text
    assert "target_list_verified" in helper_text
    assert "let expectedListId = stringValue(request, \"expected_list_id\")" in helper_text
    assert "reminder.calendar.calendarIdentifier != expectedListId" in helper_text
    assert "guard let expectedCompleted = boolValue(request, \"expected_completed\")" in helper_text
    assert "Reminder list-move read-back did not return the changed reminder." in helper_text
    assert "refreshed.calendar.calendarIdentifier == targetListId" in helper_text
    assert "var readBackReminder = reminder" not in helper_text


def test_eventkit_helper_checks_expected_list_before_already_applied() -> None:
    helper_text = Path("scripts/eventkit_helper.swift").read_text(encoding="utf-8")
    expected_check = helper_text.index("Reminder list did not match expected state.")
    already_applied = helper_text.index("Reminder already belongs to the target list.")

    assert expected_check < already_applied


def test_eventkit_helper_rejects_non_ascii_reminder_url_before_apply() -> None:
    helper_text = Path("scripts/eventkit_helper.swift").read_text(encoding="utf-8")
    url_helper = helper_text[helper_text.index("func normalizedReminderURLOrError") :]
    apply_block = url_helper[: url_helper.index("func doubleValue")]

    assert "value.utf8.contains(where: { $0 < 0x21 || $0 > 0x7E })" in apply_block
    assert "must contain only bounded ASCII URL characters without whitespace" in apply_block
    assert apply_block.index("value.utf8.contains") < apply_block.index("URLComponents(string: value)")


def test_eventkit_helper_migration_save_failure_is_apply_unknown_with_mutation() -> None:
    helper_text = Path("scripts/eventkit_helper.swift").read_text(encoding="utf-8")
    migration_block = helper_text[
        helper_text.index('if operation == "delete_list_with_migration"') :
        helper_text.index('if operation == "rename_list" || operation == "delete_list"')
    ]

    assert "try store.save(reminder, commit: true)" in migration_block
    assert (
        'emitReminderListManagementError("apply_unknown", "eventkit_apply_failed", '
        '"Reminder list migration failed while moving reminders.", mutationApplied: true)'
    ) in migration_block
    assert "mutationApplied: movedCount > 0" not in migration_block


def test_apply_reminder_change_delete_requires_notes_hash_and_proves_absence() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = hashlib.sha256("Synthetic reminder notes.".encode("utf-8")).hexdigest()
    plan = plan_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=current_hash,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is True
            return _eventkit_runner(payload, _timeout)
        assert payload == {
            "command": "reminder_apply_change",
            "operation": "delete",
            "expected_title": "Synthetic runtime reminder",
            "expected_completed": False,
            "expected_priority": 5,
            "reminder_id": "runtime-reminder-1",
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "deleted": True,
            "read_back": {
                "deleted": True,
                "verified_absent": True,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "delete"
    assert result["mutation_applied"] is True
    assert result["read_back"] == {
        "handle": handle,
        "deleted": True,
        "verified_absent": True,
    }
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]
    assert "runtime-reminder-1" not in str(result)


def test_apply_reminder_change_delete_refuses_changed_current_hash() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    stale_hash = hashlib.sha256("Different synthetic notes.".encode("utf-8")).hexdigest()
    plan = plan_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=stale_hash,
    )
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is True
            return _eventkit_runner(payload, _timeout)
        raise AssertionError("delete should not run after note hash mismatch")

    result = apply_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=stale_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_notes_changed"
    assert calls == ["reminders", "reminder_by_id"]


def test_apply_reminder_change_delete_requires_absence_proof() -> None:
    search = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)
    handle = search["results"][0]["handle"]
    current_hash = hashlib.sha256("Synthetic reminder notes.".encode("utf-8")).hexdigest()
    plan = plan_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=current_hash,
    )

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, _timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is True
            return _eventkit_runner(payload, _timeout)
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": "authorized",
            "deleted": True,
            "read_back": {
                "deleted": True,
                "verified_absent": False,
            },
            "warnings": [],
        }

    result = apply_reminder_change(
        "delete",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_completed=False,
        expected_priority=5,
        expected_notes_sha256=current_hash,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


# v1.177 Reminders start-date and recurrence tranche.


def _reminder_apply_response(**over: Any) -> dict:
    reminder = {
        "reminder_id": "runtime-reminder-1",
        "title": "Synthetic runtime reminder",
        "list_id": "synthetic-list-1",
        "list_name": "Synthetic List",
        "due_date": "2026-06-04T17:00:00.000Z",
        "start_date": "",
        "completed": False,
        "priority": 5,
        "notes_present": True,
        "url_present": False,
        "alarms_count": 0,
    }
    reminder.update(over)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "authorization_status": "authorized",
        "mutation_applied": True,
        "reminder": reminder,
        "warnings": [],
    }


def test_plan_reminder_change_create_with_start_date_binds_start() -> None:
    plan = plan_reminder_change(
        "create-with-start-date",
        title="Runtime start reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        start_date="2026-06-02",
    )
    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["start_date"] == "2026-06-02"
    assert proposed["start_date_requested"] is True


def test_plan_reminder_change_create_with_start_date_rejects_start_after_due() -> None:
    plan = plan_reminder_change(
        "create-with-start-date",
        title="Runtime start reminder",
        list_name="Synthetic List",
        due_date="2026-06-01",
        start_date="2026-06-05",
    )
    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "invalid_start_date"


def test_plan_reminder_change_update_start_date_clear_allows_empty() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="2026-06-02",
        start_date="",
    )
    assert plan["status"] == "ok"
    proposed = plan["preview"]["proposed"]
    assert proposed["start_date"] == ""
    assert proposed["start_date_present"] is False


def test_apply_reminder_change_creates_with_start_date_read_back() -> None:
    plan = plan_reminder_change(
        "create-with-start-date",
        title="Runtime start reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        start_date="2026-06-02",
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "create_with_start_date"
        assert payload["start_date"] == "2026-06-02"
        return _reminder_apply_response(start_date="2026-06-02")

    result = apply_reminder_change(
        "create-with-start-date",
        title="Runtime start reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        start_date="2026-06-02",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["operation"] == "create_with_start_date"
    assert result["read_back"]["start_date"] == "2026-06-02"
    assert result["read_back"]["start_date_verified"] is True


def test_apply_reminder_change_update_start_date_set_read_back() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="",
        start_date="2026-06-02",
    )
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload["include_content"] is False
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["start_date"] = ""
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "update_start_date"
        assert payload["expected_start_date"] == ""
        assert payload["start_date"] == "2026-06-02"
        return _reminder_apply_response(start_date="2026-06-02")

    result = apply_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="",
        start_date="2026-06-02",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["read_back"]["start_date_verified"] is True
    assert calls == ["reminders", "reminder_by_id", "reminder_apply_change"]


def test_apply_reminder_change_update_start_date_clear_absence_proof() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="2026-06-02",
        start_date="",
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["start_date"] = "2026-06-02"
            return response
        assert payload["operation"] == "update_start_date"
        assert payload["start_date"] == ""
        return _reminder_apply_response(start_date="")

    result = apply_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="2026-06-02",
        start_date="",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["read_back"]["start_date_absent_verified"] is True


def test_apply_reminder_change_update_start_date_refuses_stale_state() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="",
        start_date="2026-06-02",
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["start_date"] = "2026-06-01"
            return response
        raise AssertionError("apply must not run when current start state is stale")

    result = apply_reminder_change(
        "update-start-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_start_date="",
        start_date="2026-06-02",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


_WEEKLY_RECURRENCE = {
    "frequency": "weekly",
    "interval": 1,
    "count": 4,
    "recurrence_present": True,
    "weekdays": ["monday", "thursday"],
}
_DAILY_RECURRENCE = {
    "frequency": "daily",
    "interval": 2,
    "count": 6,
    "recurrence_present": True,
}
_EMPTY_RECURRENCE = {
    "frequency": "",
    "interval": 0,
    "count": 0,
    "recurrence_present": False,
}


def test_plan_reminder_change_create_with_recurrence_binds_shape() -> None:
    plan = plan_reminder_change(
        "create-with-recurrence",
        title="Runtime recurring reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
    )
    assert plan["status"] == "ok"
    assert plan["preview"]["proposed"]["recurrence"] == _WEEKLY_RECURRENCE


def test_plan_reminder_change_create_with_recurrence_requires_due_date_anchor() -> None:
    plan = plan_reminder_change(
        "create-with-recurrence",
        title="Runtime recurring reminder",
        list_name="Synthetic List",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
    )
    assert plan["status"] == "error"
    warning = plan["warnings"][0]
    assert warning["code"] == "missing_required_field"
    assert "due date anchor" in warning["message"]


def test_plan_reminder_change_create_with_recurrence_rejects_start_date_only_anchor() -> None:
    # start_date is never a valid recurrence anchor and recurrence ops never
    # carry a start_date; supplying one is rejected before the anchor gate.
    plan = plan_reminder_change(
        "create-with-recurrence",
        title="Runtime recurring reminder",
        list_name="Synthetic List",
        start_date="2026-06-02",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
    )
    assert plan["status"] == "error"
    codes = {w["code"] for w in plan["warnings"]}
    assert "unsupported_start_date_for_operation" in codes
    # And with the start_date removed there is still no due-date anchor.
    anchor_plan = plan_reminder_change(
        "create-with-recurrence",
        title="Runtime recurring reminder",
        list_name="Synthetic List",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
    )
    assert anchor_plan["status"] == "error"
    assert anchor_plan["warnings"][0]["code"] == "missing_required_field"
    assert "due date anchor" in anchor_plan["warnings"][0]["message"]


def test_plan_reminder_change_update_recurrence_rejects_conflicting_clear() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=False,
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
        clear_recurrence=True,
    )
    assert plan["status"] == "error"
    assert plan["warnings"][0]["code"] == "conflicting_recurrence_fields"


def test_apply_reminder_change_creates_with_recurrence_read_back() -> None:
    plan = plan_reminder_change(
        "create-with-recurrence",
        title="Runtime recurring reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "create_with_recurrence"
        assert payload["recurrence"] == _WEEKLY_RECURRENCE
        return _reminder_apply_response(
            recurrence_present=True,
            recurrence=_WEEKLY_RECURRENCE,
        )

    result = apply_reminder_change(
        "create-with-recurrence",
        title="Runtime recurring reminder",
        list_name="Synthetic List",
        due_date="2026-06-04",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["operation"] == "create_with_recurrence"
    assert result["read_back"]["recurrence"] == _WEEKLY_RECURRENCE
    assert result["read_back"]["recurrence_verified"] is True


def _recurrence_state_runner(current: dict, expected_new: dict | None):
    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            assert payload.get("include_recurrence_proof") is True
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["recurrence_present"] = current.get(
                "recurrence_present", False
            )
            response["reminder"]["recurrence"] = current
            return response
        assert payload["command"] == "reminder_apply_change"
        assert payload["operation"] == "update_recurrence"
        if expected_new is None:
            assert payload["clear_recurrence"] is True
            return _reminder_apply_response(
                recurrence_present=False,
                recurrence=_EMPTY_RECURRENCE,
            )
        assert payload["recurrence"] == expected_new
        return _reminder_apply_response(
            recurrence_present=True,
            recurrence=expected_new,
        )

    return runner


def test_apply_reminder_change_update_recurrence_add_read_back() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=False,
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
    )
    result = apply_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=False,
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday,thursday",
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurrence_state_runner(_EMPTY_RECURRENCE, _WEEKLY_RECURRENCE),
    )
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == _WEEKLY_RECURRENCE
    assert result["read_back"]["recurrence_verified"] is True


def test_apply_reminder_change_update_recurrence_replace_read_back() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=True,
        expected_recurrence=_WEEKLY_RECURRENCE,
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_count=6,
    )
    result = apply_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=True,
        expected_recurrence=_WEEKLY_RECURRENCE,
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_count=6,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurrence_state_runner(_WEEKLY_RECURRENCE, _DAILY_RECURRENCE),
    )
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence"] == _DAILY_RECURRENCE
    assert result["read_back"]["recurrence_verified"] is True


def test_apply_reminder_change_update_recurrence_clear_absence_proof() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=True,
        expected_recurrence=_DAILY_RECURRENCE,
        clear_recurrence=True,
    )
    result = apply_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=True,
        expected_recurrence=_DAILY_RECURRENCE,
        clear_recurrence=True,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=_recurrence_state_runner(_DAILY_RECURRENCE, None),
    )
    assert result["status"] == "ok"
    assert result["read_back"]["recurrence_cleared_verified"] is True


def test_apply_reminder_change_update_recurrence_refuses_stale_state() -> None:
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=True,
        expected_recurrence=_WEEKLY_RECURRENCE,
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_count=6,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "reminders":
            return _eventkit_runner(payload, timeout)
        if payload["command"] == "reminder_by_id":
            response = _eventkit_runner(payload, timeout)
            response["reminder"]["recurrence_present"] = True
            response["reminder"]["recurrence"] = _DAILY_RECURRENCE
            return response
        raise AssertionError("apply must not run when current recurrence is stale")

    result = apply_reminder_change(
        "update-recurrence",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        expected_recurrence_present=True,
        expected_recurrence=_WEEKLY_RECURRENCE,
        recurrence_frequency="daily",
        recurrence_interval=2,
        recurrence_count=6,
        approval_token=_approval_token(plan),
        confirm_apply=True,
        eventkit_runner=runner,
    )
    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "stale_recurrence_state"


def test_existing_reminder_operations_unchanged_by_new_fields() -> None:
    # Regression: existing operations still reject start-date/recurrence input.
    handle = search_reminders_eventkit("runtime", eventkit_runner=_eventkit_runner)["results"][0]["handle"]
    plan = plan_reminder_change(
        "update-due-date",
        handle=handle,
        expected_title="Synthetic runtime reminder",
        due_date="2026-06-05",
        start_date="2026-06-02",
    )
    assert plan["status"] == "error"
    codes = {w["code"] for w in plan["warnings"]}
    assert "unsupported_start_date_for_operation" in codes

    recurrence_plan = plan_reminder_change(
        "update-title",
        handle=handle,
        title="Renamed",
        expected_title="Synthetic runtime reminder",
        recurrence_frequency="weekly",
        recurrence_count=4,
        recurrence_weekdays="monday",
    )
    assert recurrence_plan["status"] == "error"
    recurrence_codes = {w["code"] for w in recurrence_plan["warnings"]}
    assert "unsupported_recurrence_for_operation" in recurrence_codes

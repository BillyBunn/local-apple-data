from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path

from local_apple_data.handles import make_int_handle
from local_apple_data.adapters.notes import (
    apply_notes_change,
    check_notes_schema,
    get_notes_content,
    get_notes_metadata,
    plan_notes_change,
    search_notes_metadata,
)


def _make_notes_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZICCLOUDSYNCINGOBJECT (
                Z_PK INTEGER PRIMARY KEY,
                ZTITLE1 VARCHAR,
                ZTITLE VARCHAR,
                ZSNIPPET VARCHAR,
                ZCREATIONDATE1 TIMESTAMP,
                ZMODIFICATIONDATE1 TIMESTAMP,
                ZISPASSWORDPROTECTED INTEGER,
                ZMARKEDFORDELETION INTEGER,
                ZNOTEDATA INTEGER
            );
            CREATE TABLE Z_METADATA (Z_UUID VARCHAR);
            INSERT INTO Z_METADATA VALUES ('11111111-2222-3333-4444-555555555555');
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA)
              VALUES
              (20, 'Project Alpha note', 'Alpha fallback', 'Synthetic snippet', 100, 200, 0, 0, 1),
              (21, 'Locked Alpha note', 'Locked fallback', 'Synthetic locked snippet', 100, 201, 1, 0, 2),
              (22, 'Deleted Alpha note', 'Deleted fallback', 'Synthetic deleted snippet', 100, 202, 0, 1, 3);
            """
        )


def test_search_notes_metadata_excludes_locked_and_deleted(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_metadata("Alpha", db_path=db_path, limit=100)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["query"]["limit"] == 50
    assert result["result_count"] == 1
    assert result["results"][0]["handle"].startswith("notes:note:v2:")
    assert result["results"][0]["handle"] != "notes:note:20"
    assert result["results"][0]["title"] == "Project Alpha note"


def test_search_notes_metadata_rejects_empty_query(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_metadata(" ", db_path=db_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "empty_query"


def test_search_notes_metadata_rejects_low_quality_query(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = search_notes_metadata("%", db_path=db_path)

    assert result["status"] == "error"
    assert result["result_count"] == 0
    assert result["warnings"][0]["code"] == "broad_query"


def test_get_notes_metadata_by_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_metadata(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Project Alpha note"
    assert result["result"]["password_protected"] is False


def test_get_notes_metadata_does_not_return_locked_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = make_int_handle("notes:note", 21)

    result = get_notes_metadata(handle, db_path=db_path)

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_get_notes_metadata_does_not_return_deleted_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = make_int_handle("notes:note", 22)

    result = get_notes_metadata(handle, db_path=db_path)

    assert result["status"] == "not_found"
    assert result["result"] is None


def test_get_notes_metadata_rejects_guessable_legacy_id(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = get_notes_metadata("notes:note:20", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_notes_content_by_handle_strips_html_and_bounds(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    def runner(script: str, timeout: float) -> str:
        assert "x-coredata://" in script
        assert "ICNote/p20" in script
        assert timeout == 10.0
        return "<html><body><h1>Project Alpha note</h1><p>Line one<br>Line two</p></body></html>"

    result = get_notes_content(handle, db_path=db_path, max_chars=4000, script_runner=runner)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "content"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["content_text"] == "Project Alpha note\nLine one\nLine two"
    assert result["result"]["content_chars"] == len(result["result"]["content_text"])
    assert result["result"]["content_offset"] == 0
    assert result["result"]["content_total_chars"] == len(result["result"]["content_text"])
    assert result["result"]["next_offset"] is None
    assert result["result"]["truncated"] is False


def test_get_notes_content_truncates(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=8,
        script_runner=lambda _script, _timeout: "<p>abcdefghijklmnop</p>",
    )

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "abcdefgh"
    assert result["result"]["content_sha256"] == hashlib.sha256(
        "abcdefghijklmnop".encode("utf-8")
    ).hexdigest()
    assert result["result"]["content_offset"] == 0
    assert result["result"]["content_total_chars"] == 16
    assert result["result"]["next_offset"] == 8
    assert result["result"]["truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"


def test_get_notes_content_supports_offset_for_long_notes(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        max_chars=5,
        offset=5,
        script_runner=lambda _script, _timeout: "<p>abcdefghijklmnop</p>",
    )

    assert result["status"] == "ok"
    assert result["result"]["content_text"] == "fghij"
    assert result["result"]["content_chars"] == 5
    assert result["result"]["content_offset"] == 5
    assert result["result"]["content_total_chars"] == 16
    assert result["result"]["next_offset"] == 10
    assert result["result"]["truncated"] is True


def _notes_token(plan: dict) -> str:
    return "notes-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


def test_plan_notes_change_create_returns_preview_only() -> None:
    result = plan_notes_change(
        "create",
        title="Synthetic planning note",
        body_text="Line one\nLine two",
    )

    assert result["status"] == "ok"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "create"
    assert preview["target"] == {"account": "default", "folder": "default"}
    assert preview["proposed"]["title"] == "Synthetic planning note"
    assert preview["proposed"]["body_chars"] == 17
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_append_text_returns_exact_handle_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256("Project Alpha note\nExisting body".encode("utf-8")).hexdigest()

    result = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )

    assert result["status"] == "ok"
    preview = result["preview"]
    assert preview["operation"] == "append_text"
    assert preview["target"] == {
        "handle": handle,
        "expected_current_sha256": current_sha,
    }
    assert preview["proposed"]["append_chars"] == 13
    assert preview["proposed"]["overwrite"] == "blocked"
    assert preview["approval"]["approval_token_format"].startswith("notes-apply:v1:")


def test_plan_notes_change_requires_title() -> None:
    result = plan_notes_change("create", title=" ", body_text="Body")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_title"


def test_plan_notes_change_append_text_requires_hash_and_handle() -> None:
    result = plan_notes_change("append-text", body_text="Body")

    assert result["status"] == "error"
    assert {warning["code"] for warning in result["warnings"]} == {
        "invalid_handle",
        "missing_required_field",
    }


def test_apply_notes_change_requires_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change("create", title="Synthetic create note", body_text="Body")

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Body",
        approval_token=_notes_token(plan),
        confirm_apply=False,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_notes_change_rejects_wrong_approval_token(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Body",
        approval_token="notes-apply:v1:bad",
        confirm_apply=True,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_notes_change_creates_note_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    plan = plan_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Created body",
    )

    def runner(script: str, timeout: float) -> str:
        assert timeout == 10.0
        if "make new note" in script:
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO ZICCLOUDSYNCINGOBJECT
                      (Z_PK, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
                       ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA)
                      VALUES (30, 'Synthetic create note', 'Synthetic create note',
                              'Created body', 300, 300, 0, 0, 4)
                    """
                )
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p30"
        assert "ICNote/p30" in script
        return "<h1>Synthetic create note</h1><p>Created body</p>"

    result = apply_notes_change(
        "create",
        title="Synthetic create note",
        body_text="Created body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["title"] == "Synthetic create note"
    assert result["read_back"]["content_text"] == "Synthetic create note\nCreated body"


def test_apply_notes_change_is_idempotent_for_matching_existing_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZNOTEDATA)
              VALUES (30, 'Synthetic existing note', 'Synthetic existing note',
                      'Existing body', 300, 300, 0, 0, 4)
            """
        )
    plan = plan_notes_change(
        "create",
        title="Synthetic existing note",
        body_text="Existing body",
    )

    def runner(script: str, _timeout: float) -> str:
        assert "make new note" not in script
        assert "ICNote/p30" in script
        return "<h1>Synthetic existing note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "create",
        title="Synthetic existing note",
        body_text="Existing body",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "already_applied"
    assert result["read_back"]["content_text"] == "Synthetic existing note\nExisting body"


def test_apply_notes_change_appends_text_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_text = "Project Alpha note\nExisting body"
    current_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )
    body_html = "<h1>Project Alpha note</h1><p>Existing body</p>"

    def runner(script: str, timeout: float) -> str:
        nonlocal body_html
        assert timeout == 10.0
        assert "ICNote/p20" in script
        if "set body of targetNote" in script:
            assert "password protected of targetNote" in script
            assert "shared of targetNote" in script
            body_html = body_html + "<p>Appended line</p>"
            return "x-coredata://11111111-2222-3333-4444-555555555555/ICNote/p20"
        return body_html

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["content_text"] == "Project Alpha note\nExisting body\nAppended line"


def test_apply_notes_change_append_rejects_stale_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    approved_sha = hashlib.sha256("Different content".encode("utf-8")).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=approved_sha,
        body_text="Appended line",
    )

    def runner(script: str, _timeout: float) -> str:
        assert "set body of targetNote" not in script
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=approved_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "current_content_changed"


def test_apply_notes_change_append_rejects_shared_note(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]
    current_sha = hashlib.sha256(
        "Project Alpha note\nExisting body".encode("utf-8")
    ).hexdigest()
    plan = plan_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
    )

    def runner(script: str, _timeout: float) -> str:
        if "set body of targetNote" in script:
            return "__LOCAL_APPLE_DATA_ERROR__:shared_note"
        return "<h1>Project Alpha note</h1><p>Existing body</p>"

    result = apply_notes_change(
        "append-text",
        handle=handle,
        expected_current_sha256=current_sha,
        body_text="Appended line",
        approval_token=_notes_token(plan),
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "shared_note_mutation_blocked"


def test_get_notes_content_rejects_bad_handle(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    result = get_notes_content("notes:note:20", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_notes_content_does_not_return_locked_or_deleted_notes(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    locked = get_notes_content(make_int_handle("notes:note", 21), db_path=db_path)
    deleted = get_notes_content(make_int_handle("notes:note", 22), db_path=db_path)

    assert locked["status"] == "not_found"
    assert locked["result"] is None
    assert deleted["status"] == "not_found"
    assert deleted["result"] is None


def test_get_notes_content_reports_missing_store_uuid(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM Z_METADATA")
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    result = get_notes_content(
        handle,
        db_path=db_path,
        script_runner=lambda _script, _timeout: "<p>should not run</p>",
    )

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "content_unavailable"


def test_get_notes_content_reports_automation_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = search_notes_metadata("Alpha", db_path=db_path)["results"][0]["handle"]

    def runner(_script: str, timeout: float) -> str:
        raise subprocess.TimeoutExpired("osascript", timeout)

    result = get_notes_content(handle, db_path=db_path, script_runner=runner)

    assert result["status"] == "content_unavailable"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"][0]["code"] == "automation_timeout"


def test_notes_schema_warning_does_not_expose_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.sqlite"

    result = check_notes_schema(db_path=missing_path)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "notes_schema_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]

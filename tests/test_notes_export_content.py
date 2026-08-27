"""v1.182 Notes folder content export: bounded, paged, date-bounded, confirm-gated."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from local_apple_data.adapters.notes import (
    export_notes_folder_content,
    search_notes_folders,
)


def _make_notes_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZICCLOUDSYNCINGOBJECT (
                Z_PK INTEGER PRIMARY KEY,
                Z_ENT INTEGER,
                ZTITLE1 VARCHAR,
                ZTITLE VARCHAR,
                ZSNIPPET VARCHAR,
                ZCREATIONDATE1 TIMESTAMP,
                ZMODIFICATIONDATE1 TIMESTAMP,
                ZISPASSWORDPROTECTED INTEGER,
                ZMARKEDFORDELETION INTEGER,
                ZFOLDER INTEGER,
                ZNOTEDATA INTEGER,
                ZACCOUNT8 INTEGER,
                ZPARENT INTEGER,
                ZFOLDERTYPE INTEGER,
                ZFOLDERMODIFICATIONDATE TIMESTAMP,
                ZSMARTFOLDERQUERYJSON VARCHAR,
                ZTITLE2 VARCHAR,
                ZNAME VARCHAR,
                ZACCOUNTNAMEFORACCOUNTLISTSORTING VARCHAR,
                ZNOTE INTEGER
            );
            CREATE TABLE Z_METADATA (Z_UUID VARCHAR);
            INSERT INTO Z_METADATA VALUES ('11111111-2222-3333-4444-555555555555');
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZNAME, ZACCOUNTNAMEFORACCOUNTLISTSORTING, ZMARKEDFORDELETION)
              VALUES (39, 14, 'Synthetic Account', 'Synthetic Account', 0);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE2, ZACCOUNT8, ZPARENT, ZFOLDERTYPE,
               ZFOLDERMODIFICATIONDATE, ZSMARTFOLDERQUERYJSON, ZMARKEDFORDELETION)
              VALUES
              (40, 15, 'Synthetic Projects', 39, NULL, 0, 400, NULL, 0),
              (41, 15, 'Synthetic Smart Folder', 39, NULL, 0, 401, '{"scope":"all"}', 0);
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, Z_ENT, ZTITLE1, ZTITLE, ZSNIPPET, ZCREATIONDATE1, ZMODIFICATIONDATE1,
               ZISPASSWORDPROTECTED, ZMARKEDFORDELETION, ZFOLDER, ZNOTEDATA)
              VALUES
              (20, 12, 'Synthetic older note', 'Older fallback', 'Synthetic snippet', 100, 200, 0, 0, 40, 1),
              (21, 12, 'Synthetic locked note', 'Locked fallback', 'Synthetic locked snippet', 100, 201, 1, 0, 40, 2),
              (22, 12, 'Synthetic deleted note', 'Deleted fallback', 'Synthetic deleted snippet', 100, 202, 0, 1, 40, 3),
              (23, 12, 'Synthetic newer note', 'Newer fallback', 'Synthetic newer snippet', 100, 5000, 0, 0, 40, 4);
            """
        )


def _folder_handle(db_path: Path, title: str = "Synthetic Projects") -> str:
    result = search_notes_folders(title, db_path=db_path)
    assert result["status"] == "ok" and result["results"], result
    return result["results"][0]["handle"]


def _runner(script: str, _timeout: float) -> str:
    if "/ICNote/p20" in script:
        return "<p>older synthetic body</p>"
    if "/ICNote/p23" in script:
        return "<p>newer synthetic body</p>"
    raise AssertionError("unexpected note requested")


def test_export_requires_confirm_bulk(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    result = export_notes_folder_content(
        _folder_handle(db_path), "2001-01-01", db_path=db_path, script_runner=_runner
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "bulk_export_not_confirmed"
    assert result["results"] == []


def test_export_requires_parseable_modified_after(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    result = export_notes_folder_content(
        _folder_handle(db_path),
        "not-a-date",
        db_path=db_path,
        confirm_bulk=True,
        script_runner=_runner,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_modified_after"


def test_export_returns_bounded_text_and_excludes_locked_deleted(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    result = export_notes_folder_content(
        _folder_handle(db_path),
        "2001-01-01",
        db_path=db_path,
        confirm_bulk=True,
        script_runner=_runner,
    )
    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "content"
    assert result["privacy"]["bulk_content_returned"] is True
    titles = [item["title"] for item in result["results"]]
    assert titles == ["Synthetic older note", "Synthetic newer note"]
    assert result["exported_count"] == 2
    assert result["skipped_count"] == 0
    assert result["next_cursor"] is None
    older = result["results"][0]
    assert older["content_status"] == "ok"
    assert older["content_text"] == "older synthetic body"
    assert older["content_sha256"]
    assert older["truncated"] is False


def test_export_date_bound_filters_older_notes(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    # 3000 Apple-epoch seconds = 2001-01-01T00:50:00Z; only the mod-5000 note passes.
    result = export_notes_folder_content(
        _folder_handle(db_path),
        "2001-01-01T00:50:00+00:00",
        db_path=db_path,
        confirm_bulk=True,
        script_runner=_runner,
    )
    assert result["status"] == "ok"
    assert [item["title"] for item in result["results"]] == ["Synthetic newer note"]


def test_export_paginates_with_next_cursor(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    handle = _folder_handle(db_path)
    first = export_notes_folder_content(
        handle,
        "2001-01-01",
        db_path=db_path,
        limit=1,
        confirm_bulk=True,
        script_runner=_runner,
    )
    assert first["status"] == "ok"
    assert [item["title"] for item in first["results"]] == ["Synthetic older note"]
    assert first["next_cursor"] == 1
    second = export_notes_folder_content(
        handle,
        "2001-01-01",
        db_path=db_path,
        cursor=first["next_cursor"],
        limit=1,
        confirm_bulk=True,
        script_runner=_runner,
    )
    assert [item["title"] for item in second["results"]] == ["Synthetic newer note"]
    assert second["next_cursor"] is None


def test_export_skips_timed_out_note_and_continues(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)

    def runner(script: str, _timeout: float) -> str:
        if "/ICNote/p20" in script:
            raise subprocess.TimeoutExpired(cmd="osascript", timeout=10)
        return "<p>newer synthetic body</p>"

    result = export_notes_folder_content(
        _folder_handle(db_path),
        "2001-01-01",
        db_path=db_path,
        confirm_bulk=True,
        script_runner=runner,
    )
    assert result["status"] == "ok"
    assert result["exported_count"] == 1
    assert result["skipped_count"] == 1
    skipped = result["results"][0]
    assert skipped["content_status"] == "skipped"
    assert skipped["skip_reason"] == "automation_timeout"
    assert "content_text" not in skipped
    assert any(w["code"] == "note_content_skipped" for w in result["warnings"])


def test_export_rejects_smart_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "notes.sqlite"
    _make_notes_db(db_path)
    result = export_notes_folder_content(
        _folder_handle(db_path, "Synthetic Smart Folder"),
        "2001-01-01",
        db_path=db_path,
        confirm_bulk=True,
        script_runner=_runner,
    )
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_smart_folder"

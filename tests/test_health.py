from __future__ import annotations

import json
from pathlib import Path

from local_apple_data.cli import main
from local_apple_data.doctor import build_doctor
from local_apple_data.health import DEFAULT_STORE_PATHS, build_health, health_json


def _fake_which(name: str) -> str | None:
    if name in {"uv", "swift", "sqlite3", "shortcuts", "osascript"}:
        return f"/fake/bin/{name}"
    return None


def _make_schema_stores(
    tmp_path: Path,
    *,
    mail_relative_path: Path = DEFAULT_STORE_PATHS["mail_envelope_index"],
) -> None:
    import sqlite3

    mail = tmp_path / mail_relative_path
    mail.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(mail) as connection:
        connection.executescript(
            """
            CREATE TABLE messages (
                ROWID INTEGER PRIMARY KEY,
                subject INTEGER NOT NULL,
                mailbox INTEGER NOT NULL,
                date_received INTEGER,
                date_sent INTEGER,
                read INTEGER,
                flagged INTEGER,
                deleted INTEGER,
                size INTEGER
            );
            CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY, subject TEXT NOT NULL);
            CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY, url TEXT NOT NULL);
            """
        )

    notes = tmp_path / DEFAULT_STORE_PATHS["notes_store"]
    notes.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(notes) as connection:
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
            """
        )

    reminders = tmp_path / DEFAULT_STORE_PATHS["reminders_stores"]
    reminders.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(reminders / "Data-local.sqlite") as connection:
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
            """
        )

    messages = tmp_path / DEFAULT_STORE_PATHS["messages_store"]
    messages.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(messages) as connection:
        connection.executescript(
            """
            CREATE TABLE chat (
                ROWID INTEGER PRIMARY KEY,
                guid TEXT,
                display_name TEXT,
                service_name TEXT
            );
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT,
                date INTEGER,
                is_from_me INTEGER,
                handle_id INTEGER,
                service TEXT
            );
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
            CREATE TABLE handle (
                ROWID INTEGER PRIMARY KEY,
                id TEXT,
                service TEXT
            );
            CREATE TABLE attachment (
                ROWID INTEGER PRIMARY KEY,
                filename TEXT,
                transfer_name TEXT,
                mime_type TEXT,
                uti TEXT,
                total_bytes INTEGER,
                created_date INTEGER,
                start_date INTEGER
            );
            CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
            """
        )

    voice_memos = tmp_path / DEFAULT_STORE_PATHS["voice_memos_store"]
    voice_memos.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(voice_memos) as connection:
        connection.executescript(
            """
            CREATE TABLE ZCLOUDRECORDING (
                Z_PK INTEGER PRIMARY KEY,
                ZCUSTOMLABEL VARCHAR,
                ZDATE TIMESTAMP,
                ZDURATION REAL,
                ZPATH VARCHAR,
                ZUNIQUEID VARCHAR
            );
            """
        )

    safari = tmp_path / DEFAULT_STORE_PATHS["safari_bookmarks"]
    safari.parent.mkdir(parents=True, exist_ok=True)
    safari.write_bytes(b"bplist00")

    books_library = tmp_path / DEFAULT_STORE_PATHS["books_library_store"]
    books_library.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(books_library) as connection:
        connection.executescript(
            """
            CREATE TABLE ZBKLIBRARYASSET (
                Z_PK INTEGER PRIMARY KEY,
                ZASSETID TEXT,
                ZASSETGUID TEXT,
                ZSTOREID TEXT,
                ZTITLE TEXT,
                ZAUTHOR TEXT,
                ZGENRE TEXT,
                ZKIND TEXT,
                ZCONTENTTYPE INTEGER,
                ZISFINISHED INTEGER,
                ZREADINGPROGRESS REAL,
                ZLASTOPENDATE REAL,
                ZPATH TEXT
            );
            """
        )

    books_annotations = tmp_path / DEFAULT_STORE_PATHS["books_annotations_store"]
    books_annotations.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(books_annotations) as connection:
        connection.executescript(
            """
            CREATE TABLE ZAEANNOTATION (
                Z_PK INTEGER PRIMARY KEY,
                ZANNOTATIONASSETID TEXT,
                ZANNOTATIONDELETED INTEGER,
                ZANNOTATIONTYPE INTEGER,
                ZANNOTATIONSTYLE INTEGER,
                ZANNOTATIONCREATIONDATE REAL,
                ZANNOTATIONMODIFICATIONDATE REAL,
                ZANNOTATIONNOTE TEXT,
                ZANNOTATIONREPRESENTATIVETEXT TEXT,
                ZANNOTATIONSELECTEDTEXT TEXT,
                ZANNOTATIONUUID TEXT
            );
            """
        )

    podcasts = tmp_path / DEFAULT_STORE_PATHS["podcasts_store"]
    podcasts.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(podcasts) as connection:
        connection.executescript(
            """
            CREATE TABLE ZMTPODCAST (
                Z_PK INTEGER PRIMARY KEY,
                ZTITLE TEXT,
                ZAUTHOR TEXT,
                ZCATEGORY TEXT,
                ZPROVIDER TEXT,
                ZSUBSCRIBED INTEGER,
                ZHIDDEN INTEGER,
                ZLIBRARYEPISODESCOUNT INTEGER,
                ZDOWNLOADEDEPISODESCOUNT INTEGER,
                ZSAVEDEPISODESCOUNT INTEGER,
                ZNEWEPISODESCOUNT INTEGER,
                ZLASTDATEPLAYED REAL,
                ZUPDATEDDATE REAL,
                ZUUID TEXT,
                ZSTORECOLLECTIONID TEXT,
                ZFEEDURL TEXT,
                ZWEBPAGEURL TEXT
            );
            CREATE TABLE ZMTEPISODE (
                Z_PK INTEGER PRIMARY KEY,
                ZPODCAST INTEGER,
                ZTITLE TEXT,
                ZITUNESTITLE TEXT,
                ZCLEANEDTITLE TEXT,
                ZAUTHOR TEXT,
                ZDURATION REAL,
                ZPUBDATE REAL,
                ZLASTDATEPLAYED REAL,
                ZPLAYHEAD REAL,
                ZHASBEENPLAYED INTEGER,
                ZPLAYCOUNT INTEGER,
                ZSAVED INTEGER,
                ZDOWNLOADPATH TEXT,
                ZASSETURL TEXT,
                ZEXPLICIT INTEGER,
                ZAUDIO INTEGER,
                ZVIDEO INTEGER,
                ZUUID TEXT,
                ZGUID TEXT,
                ZSTORETRACKID TEXT,
                ZITEMDESCRIPTION TEXT,
                ZITEMDESCRIPTIONWITHOUTHTML TEXT,
                ZTRANSCRIPTIDENTIFIER TEXT,
                ZFREETRANSCRIPTIDENTIFIER TEXT,
                ZENTITLEDTRANSCRIPTIDENTIFIER TEXT,
                ZWEBPAGEURL TEXT,
                ZVISIBLE INTEGER,
                ZUSERDELETED INTEGER,
                ZFEEDDELETED INTEGER
            );
            """
        )

    music = tmp_path / DEFAULT_STORE_PATHS["music_library_store"]
    music.parent.mkdir(parents=True, exist_ok=True)
    music.write_bytes(b"synthetic musicdb placeholder")

    tv = tmp_path / DEFAULT_STORE_PATHS["tv_library_store"]
    tv.parent.mkdir(parents=True, exist_ok=True)
    tv.write_bytes(b"synthetic tvdb placeholder")

    icloud_drive = tmp_path / DEFAULT_STORE_PATHS["icloud_drive_root"]
    icloud_drive.mkdir(parents=True, exist_ok=True)


def test_build_health_is_redacted_and_ok_for_present_stores(tmp_path: Path) -> None:
    _make_schema_stores(tmp_path)

    health = build_health(home=tmp_path, which=_fake_which)

    assert health["status"] == "ok"
    assert health["privacy"]["content_inspected"] is False
    assert health["privacy"]["raw_rows_inspected"] is False
    assert health["privacy"]["credentials_inspected"] is False
    assert all(store["present"] for store in health["stores"])
    assert all(store["path"].startswith("~/") for store in health["stores"])
    assert all(tool["path"] == "<redacted>" for tool in health["tools"]["required"])
    assert "/fake/bin" not in str(health)
    assert health["schema_checks"]["mail"]["status"] == "ok"
    assert health["schema_checks"]["messages"]["status"] == "ok"
    assert health["schema_checks"]["voice_memos"]["status"] == "ok"
    assert health["schema_checks"]["notes"]["status"] == "ok"
    assert health["schema_checks"]["reminders"]["status"] == "ok"
    assert health["surfaces"]["mail"]["content_status_supported"] is True
    assert health["surfaces"]["hide_my_email"]["authoritative_inventory"] is False
    assert health["surfaces"]["safari"]["status"] == "ok"
    assert health["surfaces"]["safari"]["schema_check"] == "not_applicable"
    assert health["surfaces"]["shortcuts"]["status"] == "available"
    assert health["surfaces"]["shortcuts"]["tool_check"] == "shortcuts_cli"
    assert health["surfaces"]["books"]["status"] == "ok"
    assert health["surfaces"]["books"]["schema_check"] == "ok"
    assert health["surfaces"]["podcasts"]["status"] == "ok"
    assert health["surfaces"]["podcasts"]["schema_check"] == "ok"
    assert health["surfaces"]["music"]["status"] == "available"
    assert health["surfaces"]["music"]["store_status"] == "ok"
    assert health["surfaces"]["music"]["schema_check"] == "not_applicable"
    assert health["surfaces"]["music"]["tool_check"] == "osascript"
    assert health["surfaces"]["tv"]["status"] == "available"
    assert health["surfaces"]["tv"]["store_status"] == "ok"
    assert health["surfaces"]["tv"]["schema_check"] == "not_applicable"
    assert health["surfaces"]["tv"]["tool_check"] == "osascript"
    assert health["surfaces"]["icloud_drive"]["status"] == "ok"
    assert health["surfaces"]["calendar"]["status"] == "checked_on_tool_call"
    assert health["surfaces"]["calendar"]["prompts"] is False
    assert any(
        requirement["surface"] == "messages"
        and requirement["permission_class"] == "Full Disk Access and Automation may be required"
        and requirement["check_mode"] == "schema_only_without_automation_probe"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "photos"
        and requirement["check_mode"] == "non_prompting_photokit"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "safari"
        and requirement["check_mode"] == "plist_readability"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "shortcuts"
        and requirement["check_mode"] == "cli_availability_without_listing"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "books"
        and requirement["check_mode"] == "schema_only"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "podcasts"
        and requirement["check_mode"] == "schema_only"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "music"
        and requirement["check_mode"] == "app_and_osascript_availability_without_automation_probe"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert any(
        requirement["surface"] == "tv"
        and requirement["check_mode"] == "app_and_osascript_availability_without_automation_probe"
        and requirement["prompts"] is False
        for requirement in health["access_requirements"]
    )
    assert "warnings" in health


def test_build_health_degrades_for_missing_store(tmp_path: Path) -> None:
    health = build_health(home=tmp_path, which=_fake_which)

    assert health["status"] == "degraded"
    assert {warning["code"] for warning in health["warnings"]} == {"store_missing"}


def test_build_health_converts_schema_exceptions_to_safe_warnings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_schema_stores(tmp_path)

    def fail_schema(**_kwargs):
        raise RuntimeError("raw local schema failure")

    monkeypatch.setattr("local_apple_data.health.check_voice_memos_schema", fail_schema)

    health = build_health(home=tmp_path, which=_fake_which)

    assert health["status"] == "degraded"
    assert health["schema_checks"]["voice_memos"]["status"] == "degraded"
    assert health["schema_checks"]["voice_memos"]["warnings"][0]["code"] == (
        "voice_memos_schema_unavailable"
    )
    assert "raw local schema failure" not in str(health)


def test_build_health_discovers_latest_mail_store(tmp_path: Path) -> None:
    _make_schema_stores(
        tmp_path,
        mail_relative_path=Path("Library/Mail/V12/MailData/Envelope Index"),
    )

    health = build_health(home=tmp_path, which=_fake_which)

    mail_store = next(
        store for store in health["stores"] if store["name"] == "mail_envelope_index"
    )
    assert mail_store["path"] == "~/Library/Mail/V12/MailData/Envelope Index"
    assert health["schema_checks"]["mail"]["status"] == "ok"


def test_health_json_is_valid_json(tmp_path: Path) -> None:
    parsed = json.loads(health_json(home=tmp_path, which=_fake_which))

    assert parsed["schema_version"] == 1
    assert parsed["privacy"]["output_tier"] == "health"


def test_cli_health_outputs_json(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    _make_schema_stores(tmp_path)
    monkeypatch.setattr(
        "local_apple_data.cli.build_health",
        lambda: build_health(home=tmp_path, which=_fake_which),
    )

    exit_code = main(["health", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["schema_version"] == 1
    assert parsed["privacy"]["content_inspected"] is False


def test_build_doctor_returns_redacted_guidance(tmp_path: Path) -> None:
    doctor = build_doctor(home=tmp_path, which=_fake_which)

    assert doctor["schema_version"] == 1
    assert doctor["source"] == "doctor"
    assert doctor["status"] == "degraded"
    assert doctor["privacy"]["content_inspected"] is False
    assert doctor["remediation_mode"] == "non_mutating"
    assert doctor["warnings"][0]["code"] == "store_missing"
    assert "surfaces" in doctor["summary"]
    assert "access_requirements" in doctor["summary"]
    assert str(tmp_path) not in str(doctor)


def test_cli_doctor_outputs_json(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    _make_schema_stores(tmp_path)
    monkeypatch.setattr(
        "local_apple_data.cli.build_doctor",
        lambda: build_doctor(home=tmp_path, which=_fake_which),
    )

    exit_code = main(["doctor", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "doctor"
    assert parsed["remediation_mode"] == "non_mutating"

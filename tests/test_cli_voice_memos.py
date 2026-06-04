from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

from local_apple_data.cli import main


def _atom(name: str, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + name.encode("ascii") + payload


def _write_m4a(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    transcript = json.dumps(
        {"attributedString": ["Synthetic CLI transcript.", {"timeRange": [0, 1.0]}]},
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(_atom("moov", _atom("trak", _atom("udta", _atom("tsrp", transcript)))))


def _make_voice_memos_db(path: Path, recordings_dir: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZCLOUDRECORDING (
                Z_PK INTEGER PRIMARY KEY,
                ZCUSTOMLABEL TEXT,
                ZDATE REAL,
                ZDURATION REAL,
                ZPATH TEXT,
                ZUNIQUEID TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO ZCLOUDRECORDING
              (Z_PK, ZCUSTOMLABEL, ZDATE, ZDURATION, ZPATH, ZUNIQUEID)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "Synthetic CLI Memo",
                802310400.0,
                10.0,
                "synthetic-cli.m4a",
                "synthetic-cli-uuid",
            ),
        )
    _write_m4a(recordings_dir / "synthetic-cli.m4a")


def test_cli_voice_memos_search_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)

    exit_code = main(
        [
            "voice-memos",
            "search",
            "--json",
            "--query",
            "CLI",
            "--db",
            str(db_path),
            "--recordings-dir",
            str(recordings_dir),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "voice_memos"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("voice_memos:recording:v1:")
    assert "synthetic-cli.m4a" not in str(parsed)
    assert "synthetic-cli-uuid" not in str(parsed)
    assert "Synthetic CLI transcript" not in str(parsed)


def test_cli_voice_memos_get_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search_exit = main(
        [
            "voice-memos",
            "search",
            "--json",
            "--query",
            "CLI",
            "--db",
            str(db_path),
            "--recordings-dir",
            str(recordings_dir),
        ]
    )
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "voice-memos",
            "get",
            "--json",
            "--handle",
            handle,
            "--max-chars",
            "4000",
            "--db",
            str(db_path),
            "--recordings-dir",
            str(recordings_dir),
        ]
    )

    assert search_exit == 0
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["transcript_status"] == "available"
    assert parsed["result"]["transcript_text"] == "Synthetic CLI transcript."
    assert parsed["result"]["audio_content_returned"] is False
    assert "synthetic-cli.m4a" not in str(parsed)
    assert "synthetic-cli-uuid" not in str(parsed)


def test_cli_voice_memos_export_uses_synthetic_db(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    recordings_dir = tmp_path / "Recordings"
    output_dir = tmp_path / "exports"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search_exit = main(
        [
            "voice-memos",
            "search",
            "--json",
            "--query",
            "CLI",
            "--db",
            str(db_path),
            "--recordings-dir",
            str(recordings_dir),
        ]
    )
    handle = json.loads(capsys.readouterr().out)["results"][0]["handle"]

    exit_code = main(
        [
            "voice-memos",
            "export",
            "--json",
            "--handle",
            handle,
            "--output-dir",
            str(output_dir),
            "--filename",
            "memo-export",
            "--db",
            str(db_path),
            "--recordings-dir",
            str(recordings_dir),
        ]
    )

    assert search_exit == 0
    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["audio_content_exported"] is True
    assert parsed["result"]["audio_content_returned"] is False
    exported_path = Path(parsed["result"]["exported_path"])
    assert exported_path == output_dir / "memo-export.m4a"
    assert exported_path.is_file()
    assert "synthetic-cli.m4a" not in str(parsed)
    assert "synthetic-cli-uuid" not in str(parsed)

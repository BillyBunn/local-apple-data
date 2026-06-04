from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

from local_apple_data.adapters.voice_memos import (
    export_voice_memo_audio,
    get_voice_memo_recording,
    search_voice_memos,
)


def _atom(name: str, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + name.encode("ascii") + payload


def _write_m4a(path: Path, transcript_text: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b""
    if transcript_text is not None:
        payload = _atom(
            "moov",
            _atom(
                "trak",
                _atom(
                    "udta",
                    _atom(
                        "tsrp",
                        json.dumps(
                            {
                                "attributedString": [
                                    transcript_text,
                                    {"timeRange": [0, 1.0]},
                                ]
                            },
                            separators=(",", ":"),
                        ).encode("utf-8"),
                    ),
                ),
            ),
        )
    else:
        payload = _atom("moov", _atom("trak", _atom("udta", b"")))
    path.write_bytes(payload)


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
                "Synthetic Planning Memo",
                802310400.0,
                12.5,
                "synthetic-planning.m4a",
                "synthetic-voice-memo-uuid",
            ),
        )
        connection.execute(
            """
            INSERT INTO ZCLOUDRECORDING
              (Z_PK, ZCUSTOMLABEL, ZDATE, ZDURATION, ZPATH, ZUNIQUEID)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                2,
                "Synthetic Empty Transcript Memo",
                802310500.0,
                8.25,
                "synthetic-empty.m4a",
                "synthetic-empty-uuid",
            ),
        )
    _write_m4a(recordings_dir / "synthetic-planning.m4a", "Synthetic transcript text.")
    _write_m4a(recordings_dir / "synthetic-empty.m4a", None)


def test_search_voice_memos_returns_metadata_only(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)

    result = search_voice_memos("Planning", db_path=db_path, recordings_dir=recordings_dir)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "title_or_filename"
    assert result["result_count"] == 1
    memo = result["results"][0]
    assert memo["handle"].startswith("voice_memos:recording:v1:")
    assert memo["title"] == "Synthetic Planning Memo"
    assert memo["duration_seconds"] == 12.5
    assert memo["audio_status"] == "available"
    assert "synthetic-planning.m4a" not in str(result)
    assert "synthetic-voice-memo-uuid" not in str(result)
    assert "Synthetic transcript text" not in str(result)
    assert str(tmp_path) not in str(result)


def test_search_voice_memos_rejects_broad_query_without_db(tmp_path: Path) -> None:
    result = search_voice_memos("%", db_path=tmp_path / "missing.db")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_get_voice_memo_recording_returns_exact_transcript(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search = search_voice_memos("Planning", db_path=db_path, recordings_dir=recordings_dir)
    handle = search["results"][0]["handle"]

    result = get_voice_memo_recording(
        handle,
        db_path=db_path,
        recordings_dir=recordings_dir,
        max_chars=4000,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["transcript_status"] == "available"
    assert result["result"]["transcript_text"] == "Synthetic transcript text."
    assert result["result"]["transcript_chars"] == 26
    assert result["result"]["audio_content_returned"] is False
    assert result["warnings"] == []
    assert "synthetic-planning.m4a" not in str(result)
    assert "synthetic-voice-memo-uuid" not in str(result)
    assert str(tmp_path) not in str(result)


def test_get_voice_memo_recording_truncates_transcript(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search = search_voice_memos("Planning", db_path=db_path, recordings_dir=recordings_dir)
    handle = search["results"][0]["handle"]

    result = get_voice_memo_recording(
        handle,
        db_path=db_path,
        recordings_dir=recordings_dir,
        max_chars=9,
    )

    assert result["status"] == "ok"
    assert result["result"]["transcript_text"] == "Synthetic"
    assert result["result"]["transcript_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"


def test_get_voice_memo_recording_reports_missing_transcript(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search = search_voice_memos("Empty", db_path=db_path, recordings_dir=recordings_dir)
    handle = search["results"][0]["handle"]

    result = get_voice_memo_recording(handle, db_path=db_path, recordings_dir=recordings_dir)

    assert result["status"] == "ok"
    assert result["result"]["transcript_status"] == "unavailable"
    assert result["result"]["transcript_text"] == ""
    assert result["warnings"][0]["code"] == "transcript_unavailable"


def test_get_voice_memo_recording_rejects_invalid_handle() -> None:
    result = get_voice_memo_recording("voice_memos:recording:1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_export_voice_memo_audio_copies_exact_recording(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    recordings_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search = search_voice_memos("Planning", db_path=db_path, recordings_dir=recordings_dir)
    handle = search["results"][0]["handle"]
    output_dir = tmp_path / "exports"

    result = export_voice_memo_audio(
        handle,
        output_dir=output_dir,
        db_path=db_path,
        recordings_dir=recordings_dir,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "export"
    assert result["privacy"]["content_exported"] is True
    assert result["result"]["audio_content_returned"] is False
    assert result["result"]["audio_content_exported"] is True
    exported_path = Path(result["result"]["exported_path"])
    assert exported_path.is_file()
    assert exported_path.parent == output_dir
    assert exported_path.suffix == ".m4a"
    assert result["result"]["exported_bytes"] == exported_path.stat().st_size
    assert "synthetic-planning.m4a" not in str(result)
    assert "synthetic-voice-memo-uuid" not in str(result)
    assert str(recordings_dir) not in str(result)


def test_export_voice_memo_audio_uses_unique_destination(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "Recordings"
    db_path = recordings_dir / "CloudRecordings.db"
    output_dir = tmp_path / "exports"
    recordings_dir.mkdir()
    output_dir.mkdir()
    _make_voice_memos_db(db_path, recordings_dir)
    search = search_voice_memos("Planning", db_path=db_path, recordings_dir=recordings_dir)
    handle = search["results"][0]["handle"]
    output_dir.joinpath("memo.m4a").write_bytes(b"existing")

    result = export_voice_memo_audio(
        handle,
        output_dir=output_dir,
        filename="memo.m4a",
        db_path=db_path,
        recordings_dir=recordings_dir,
    )

    assert result["status"] == "ok"
    assert result["result"]["exported_filename"] == "memo-1.m4a"
    assert output_dir.joinpath("memo.m4a").read_bytes() == b"existing"


def test_export_voice_memo_audio_rejects_invalid_handle(tmp_path: Path) -> None:
    result = export_voice_memo_audio("voice_memos:recording:1", output_dir=tmp_path)

    assert result["status"] == "error"
    assert result["privacy"]["output_tier"] == "export"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_voice_memos_degrades_without_store(tmp_path: Path) -> None:
    result = search_voice_memos("Planning", db_path=tmp_path / "missing.db")

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "voice_memos_store_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]

from __future__ import annotations

import json
import re
import shutil
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


DEFAULT_RECORDINGS_DIR = (
    Path.home() / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"
)
DEFAULT_VOICE_MEMOS_DB = DEFAULT_RECORDINGS_DIR / "CloudRecordings.db"
VOICE_MEMOS_TABLES = ["ZCLOUDRECORDING"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_LIMIT = 20
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
MAX_TRANSCRIPT_ATOM_BYTES = 2_000_000
RECORDING_HANDLE_PREFIX = "voice_memos:recording"


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _content_privacy(*, content_inspected: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
    }


def _export_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "content_exported": True,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "export",
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _check_schema(connection) -> str:
    require_columns(
        connection,
        "ZCLOUDRECORDING",
        {"Z_PK", "ZCUSTOMLABEL", "ZDATE", "ZDURATION", "ZPATH", "ZUNIQUEID"},
    )
    return schema_fingerprint(connection, VOICE_MEMOS_TABLES)


def check_voice_memos_schema(*, db_path: Path = DEFAULT_VOICE_MEMOS_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "voice_memos",
            "schema_fingerprint": None,
            "tables_checked": VOICE_MEMOS_TABLES,
            "warnings": [
                {
                    "code": "voice_memos_schema_unavailable",
                    "message": "Voice Memos local schema could not be checked.",
                }
            ],
        }
    return {
        "status": "ok",
        "source": "voice_memos",
        "schema_fingerprint": fingerprint,
        "tables_checked": VOICE_MEMOS_TABLES,
        "warnings": [],
    }


def search_voice_memos(
    query: str,
    *,
    db_path: Path = DEFAULT_VOICE_MEMOS_DB,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    Z_PK AS recording_id,
                    ZCUSTOMLABEL AS custom_label,
                    ZDATE AS recorded_at,
                    ZDURATION AS duration_seconds,
                    ZPATH AS asset_path,
                    ZUNIQUEID AS unique_id
                FROM ZCLOUDRECORDING
                WHERE COALESCE(ZPATH, '') != ''
                  AND (
                    COALESCE(ZCUSTOMLABEL, '') LIKE ? ESCAPE '\\'
                    OR COALESCE(ZPATH, '') LIKE ? ESCAPE '\\'
                  )
                ORDER BY COALESCE(ZDATE, 0) DESC
                LIMIT ?
                """,
                (
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    bounded_limit,
                ),
            ).fetchall()
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, content=False)

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "voice_memos",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "title_or_filename", "limit": bounded_limit},
        "results": [
            _recording_metadata(row, fingerprint, recordings_dir=recordings_dir)
            for row in rows
        ],
        "result_count": len(rows),
        "warnings": [],
    }


def get_voice_memo_recording(
    handle: str,
    *,
    db_path: Path = DEFAULT_VOICE_MEMOS_DB,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
    max_chars: int = DEFAULT_CONTENT_CHARS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, RECORDING_HANDLE_PREFIX):
        return _invalid_handle_result()

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            recording_id = _resolve_recording_id(connection, fingerprint, handle)
            if recording_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "voice_memos",
                    "schema_fingerprint": fingerprint,
                    "privacy": _content_privacy(content_inspected=False),
                    "result": None,
                    "warnings": [],
                }
            row = _select_recording(connection, recording_id)
    except StoreUnavailableError as exc:
        return _store_degraded_export_result(exc)

    result = _recording_metadata(row, fingerprint, recordings_dir=recordings_dir)
    result.update(
        {
            "audio_content_returned": False,
            "transcript_text": "",
            "transcript_chars": 0,
            "transcript_truncated": False,
            "transcript_status": "unavailable",
        }
    )
    audio_path = _recording_path(row["asset_path"], recordings_dir)
    if audio_path is None or not audio_path.is_file():
        return _content_unavailable_result(
            result,
            "voice_memos_audio_unavailable",
            content_inspected=False,
        )

    transcript = _extract_transcript(audio_path, max_chars=bounded_chars)
    result.update(transcript["result"])
    warnings = transcript["warnings"]

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "voice_memos",
        "schema_fingerprint": fingerprint,
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": warnings,
    }


def export_voice_memo_audio(
    handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    db_path: Path = DEFAULT_VOICE_MEMOS_DB,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, RECORDING_HANDLE_PREFIX):
        return _invalid_export_handle_result()

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            recording_id = _resolve_recording_id(connection, fingerprint, handle)
            if recording_id is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "voice_memos",
                    "schema_fingerprint": fingerprint,
                    "privacy": _export_privacy(),
                    "result": None,
                    "warnings": [],
                }
            row = _select_recording(connection, recording_id)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, content=True)

    result = _recording_metadata(row, fingerprint, recordings_dir=recordings_dir)
    result.update(
        {
            "audio_content_returned": False,
            "audio_content_exported": False,
            "exported_path": "",
            "exported_filename": "",
            "exported_bytes": 0,
        }
    )
    audio_path = _recording_path(row["asset_path"], recordings_dir)
    if audio_path is None or not audio_path.is_file():
        return _export_unavailable_result(result, "voice_memos_audio_unavailable")

    target_dir = output_dir.expanduser()
    if target_dir.exists() and not target_dir.is_dir():
        return _export_unavailable_result(result, "invalid_output_dir")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_output_path(
            target_dir,
            _export_filename(filename, result["title"], suffix=".m4a"),
        )
        shutil.copy2(audio_path, target)
        exported_bytes = target.stat().st_size
    except OSError:
        return _export_unavailable_result(result, "voice_memos_export_failed")

    result.update(
        {
            "audio_content_exported": True,
            "exported_path": str(target),
            "exported_filename": target.name,
            "exported_bytes": exported_bytes,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "voice_memos",
        "schema_fingerprint": fingerprint,
        "privacy": _export_privacy(),
        "result": result,
        "result_count": 1,
        "warnings": [],
    }


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "voice_memos",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Voice Memos search requires a non-empty title or filename query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "voice_memos",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Voice Memos search requires at least two letters or digits.",
            )
        ],
    }


def _select_recording(connection, recording_id: int):
    row = connection.execute(
        """
        SELECT
            Z_PK AS recording_id,
            ZCUSTOMLABEL AS custom_label,
            ZDATE AS recorded_at,
            ZDURATION AS duration_seconds,
            ZPATH AS asset_path,
            ZUNIQUEID AS unique_id
        FROM ZCLOUDRECORDING
        WHERE Z_PK = ?
        LIMIT 1
        """,
        (recording_id,),
    ).fetchone()
    if row is None:
        raise StoreUnavailableError("Voice Memos recording could not be selected.")
    return row


def _resolve_recording_id(connection, fingerprint: str, handle: str) -> int | None:
    rows = connection.execute("SELECT Z_PK AS recording_id FROM ZCLOUDRECORDING").fetchall()
    for row in rows:
        recording_id = int(row["recording_id"])
        if opaque_handle_matches(handle, RECORDING_HANDLE_PREFIX, fingerprint, recording_id):
            return recording_id
    return None


def _recording_metadata(
    row,
    fingerprint: str,
    *,
    recordings_dir: Path,
) -> dict[str, Any]:
    recording_id = int(row["recording_id"])
    title = _recording_title(row["custom_label"], row["asset_path"], row["recorded_at"])
    audio_path = _recording_path(row["asset_path"], recordings_dir)
    return {
        "handle": make_opaque_handle(RECORDING_HANDLE_PREFIX, fingerprint, recording_id),
        "title": _bounded_string(title, 500),
        "recorded_at": _apple_date(row["recorded_at"]),
        "duration_seconds": _duration(row["duration_seconds"]),
        "audio_status": "available" if audio_path is not None and audio_path.is_file() else "unavailable",
    }


def _recording_title(custom_label: Any, asset_path: Any, recorded_at: Any) -> str:
    label = _bounded_string(custom_label, 500).strip()
    if label:
        return label
    filename = Path(_bounded_string(asset_path, 500)).stem
    if filename:
        return filename
    recorded = _apple_date(recorded_at)
    return recorded or "Untitled Voice Memo"


def _recording_path(asset_path: Any, recordings_dir: Path) -> Path | None:
    value = _bounded_string(asset_path, 2000).strip()
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = recordings_dir / candidate
    try:
        resolved_candidate = candidate.expanduser().resolve(strict=False)
        resolved_root = recordings_dir.expanduser().resolve(strict=False)
    except OSError:
        return None
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    if resolved_candidate.suffix.lower() != ".m4a":
        return None
    return resolved_candidate


def _extract_transcript(path: Path, *, max_chars: int) -> dict[str, Any]:
    try:
        with path.open("rb") as audio:
            payload = _read_tsrp_payload(audio)
    except OSError:
        return _transcript_unavailable("voice_memos_audio_unavailable")
    except _TranscriptUnavailable as exc:
        return _transcript_unavailable(exc.code)

    try:
        transcript_json = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _transcript_unavailable("transcript_parse_error")

    text = _transcript_text(transcript_json).replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return _transcript_unavailable("transcript_unavailable")
    truncated = len(text) > max_chars
    transcript_text = text[:max_chars] if truncated else text
    warnings = []
    if truncated:
        warnings.append(
            _warning(
                "content_truncated",
                "Voice Memos transcript was truncated to the requested limit.",
            )
        )
    return {
        "result": {
            "transcript_status": "available",
            "transcript_text": transcript_text,
            "transcript_chars": len(transcript_text),
            "transcript_truncated": truncated,
            "audio_content_returned": False,
        },
        "warnings": warnings,
    }


class _TranscriptUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _read_atom_header(file: BinaryIO) -> tuple[str | None, int, int]:
    header = file.read(8)
    if len(header) < 8:
        return None, 0, 0
    size = struct.unpack(">I", header[:4])[0]
    atom_type = header[4:8].decode("ascii", errors="ignore")
    if size == 1:
        extended = file.read(8)
        if len(extended) < 8:
            return None, 0, 0
        return atom_type, struct.unpack(">Q", extended)[0], 16
    return atom_type, size, 8


def _find_atom(file: BinaryIO, end_pos: int, target_type: str) -> tuple[int, int]:
    while file.tell() < end_pos:
        current_pos = file.tell()
        atom_type, atom_size, header_size = _read_atom_header(file)
        if atom_type is None or atom_size < header_size:
            break
        atom_end = current_pos + atom_size
        if atom_end > end_pos:
            break
        if atom_type == target_type:
            return atom_end, header_size
        file.seek(atom_end)
    raise _TranscriptUnavailable("transcript_unavailable")


def _read_tsrp_payload(file: BinaryIO) -> bytes:
    file_size = file.seek(0, 2)
    file.seek(0)
    moov_end, _ = _find_atom(file, file_size, "moov")
    trak_end, _ = _find_atom(file, moov_end, "trak")
    udta_end, _ = _find_atom(file, trak_end, "udta")
    tsrp_end, _ = _find_atom(file, udta_end, "tsrp")
    current_pos = file.tell()
    data_size = tsrp_end - current_pos
    if data_size <= 0 or data_size > MAX_TRANSCRIPT_ATOM_BYTES:
        raise _TranscriptUnavailable("transcript_unavailable")
    return file.read(data_size)


def _transcript_text(payload: Any) -> str:
    attributed = payload.get("attributedString") if isinstance(payload, dict) else None
    if isinstance(attributed, list):
        return "".join(item for item in attributed if isinstance(item, str))
    if isinstance(attributed, dict):
        runs = attributed.get("runs")
        if isinstance(runs, list):
            return "".join(item for item in runs if isinstance(item, str))
    return ""


def _transcript_unavailable(code: str) -> dict[str, Any]:
    return {
        "result": {
            "transcript_status": "unavailable",
            "transcript_text": "",
            "transcript_chars": 0,
            "transcript_truncated": False,
            "audio_content_returned": False,
        },
        "warnings": [_warning(code, "Voice Memos transcript is unavailable.")],
    }


def _content_unavailable_result(
    result: dict[str, Any],
    warning_code: str,
    *,
    content_inspected: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "voice_memos",
        "privacy": _content_privacy(content_inspected=content_inspected),
        "result": result,
        "result_count": 1,
        "warnings": [
            _warning(
                warning_code,
                "Voice Memos local audio or transcript is unavailable.",
            )
        ],
    }


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "voice_memos",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected voice_memos:recording:v1 opaque handle from search output.",
            )
        ],
    }


def _invalid_export_handle_result() -> dict[str, Any]:
    result = _invalid_handle_result()
    result["privacy"] = _export_privacy()
    return result


def _export_unavailable_result(result: dict[str, Any], warning_code: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "export_unavailable",
        "source": "voice_memos",
        "privacy": _export_privacy(),
        "result": result,
        "result_count": 1,
        "warnings": [
            _warning(
                warning_code,
                "Voice Memos audio could not be exported safely.",
            )
        ],
    }


def _store_degraded_result(exc: StoreUnavailableError, *, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "voice_memos",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": [_warning("voice_memos_store_unavailable", str(exc))],
    }


def _store_degraded_export_result(exc: StoreUnavailableError) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "voice_memos",
        "privacy": _export_privacy(),
        "result": None,
        "result_count": 0,
        "warnings": [_warning("voice_memos_store_unavailable", str(exc))],
    }


def _apple_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return (APPLE_EPOCH + timedelta(seconds=raw)).isoformat()
    except OverflowError:
        return None


def _duration(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _bounded_string(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text[: max(1, min(max_chars, MAX_CONTENT_CHARS))]


def _export_filename(value: str | None, fallback_title: str, *, suffix: str) -> str:
    candidate = _bounded_string(value, 200).strip() if value else ""
    if not candidate:
        candidate = _bounded_string(fallback_title, 200).strip() or "voice-memo"
    name = Path(candidate).name
    if not name.lower().endswith(suffix):
        name = f"{name}{suffix}"
    stem = Path(name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    if not safe_stem:
        safe_stem = "voice-memo"
    return f"{safe_stem[:120]}{suffix}"


def _unique_output_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise OSError("could not allocate unique export path")

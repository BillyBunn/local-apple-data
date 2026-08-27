from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_LOG_DIR = Path.home() / ".local/state/local-apple-data"


def _log_dir() -> Path:
    configured = os.environ.get("LOCAL_APPLE_DATA_LOG_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_LOG_DIR


def _warning_codes(payload: dict[str, Any]) -> list[str]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    codes: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict) and isinstance(warning.get("code"), str):
            codes.append(warning["code"])
    return codes


def event_from_result(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "command": command,
        "source": payload.get("source", "system"),
        "status": payload.get("status"),
        "schema_version": payload.get("schema_version"),
        "result_count": payload.get("result_count"),
        "warning_codes": _warning_codes(payload),
        "privacy": {
            "output_tier": privacy.get("output_tier"),
            "content_inspected": privacy.get("content_inspected"),
            "raw_rows_inspected": privacy.get("raw_rows_inspected"),
            "credentials_inspected": privacy.get("credentials_inspected"),
        },
    }


def _log_dir_is_default(directory: Path) -> bool:
    return directory.expanduser() == DEFAULT_LOG_DIR


def write_event(event: dict[str, Any]) -> None:
    directory = _log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    # The event log holds no content, but it is a per-second record of which surfaces
    # were touched and when, so at the default location it is operator-private like its
    # siblings handle-secret.key and mail-fts.sqlite, which are both 0600.
    #
    # Gated on the default path, matching _connect_mail_fts_index in adapters/mail.py.
    # LOCAL_APPLE_DATA_LOG_DIR is an operator/test override, and forcing modes on a
    # directory the operator chose would be overreach: it would silently re-widen a
    # deliberately sealed directory and clobber, say, a group-readable log kept that way
    # on purpose. We own the default location; we do not own theirs.
    is_default = _log_dir_is_default(directory)
    if is_default:
        try:
            directory.chmod(0o700)
        except OSError:
            pass
    path = directory / "events.jsonl"
    # chmod follows symlinks, so a symlinked log would have its target's mode rewritten.
    # icloud_drive and the Mail FTS index guard the same way before touching a path.
    fix_mode = is_default and not path.is_symlink()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    if fix_mode:
        try:
            path.chmod(0o600)
        except OSError:
            pass


def log_result(command: str, payload: dict[str, Any]) -> None:
    try:
        write_event(event_from_result(command, payload))
    except OSError:
        # Logging must never break the data access command.
        return


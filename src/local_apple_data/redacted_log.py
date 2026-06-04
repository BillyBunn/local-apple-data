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


def write_event(event: dict[str, Any]) -> None:
    directory = _log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def log_result(command: str, payload: dict[str, Any]) -> None:
    try:
        write_event(event_from_result(command, payload))
    except OSError:
        # Logging must never break the data access command.
        return


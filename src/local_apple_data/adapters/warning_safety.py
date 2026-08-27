from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


WarningFactory = Callable[[str, str], dict[str, str]]

MAX_WARNING_MESSAGE_CHARS = 240
UNSAFE_WARNING_MESSAGE_PATTERNS = (
    re.compile(
        r"(?i)(?:file://|smb://|afp://|nfs://|cifs://|~/|"
        r"/(?:Users|private|var|tmp|Library|Volumes|Applications|System|opt|usr|etc|Network)"
        r"(?:/|\b))"
    ),
    re.compile(
        r"(?i)\b(?:traceback|exception|stack trace|permission denied|no such file|"
        r"operation couldn['’`]t be completed|error domain|nserror|nserrordomain|ekerrordomain|"
        r"cnerrordomain|phphotoserrordomain|nsurlerrordomain|cferrordomain\w*|"
        r"kclerrordomain|urlerror|osstatus|sqlite|database)\b"
    ),
    re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"),
    re.compile(r"\+?\d[\d .()/-]{7,}\d"),
    re.compile(
        r"\b(?:books:annotation|books:book|calendar:event|contacts:contact|"
        r"freeform:board|freeform:folder|hide_my_email:alias|icloud:file|"
        r"mail:attachment|mail:mailbox|mail:message|messages:attachment|messages:chat|"
        r"music:playlist|music:track|notes:attachment|notes:note|photos:asset|"
        r"podcasts:episode|podcasts:show|reminders:reminder(?::eventkit)?|"
        r"safari:item|shortcuts:item|tv:item|tv:playlist|voice_memos:recording):v\d:"
    ),
)


def safe_warning_message(message: str, *, fallback_message: str) -> str:
    normalized = message.strip().replace("\r\n", "\n").replace("\r", "\n")
    if not normalized or len(normalized) > MAX_WARNING_MESSAGE_CHARS:
        return fallback_message
    if any(pattern.search(normalized) for pattern in UNSAFE_WARNING_MESSAGE_PATTERNS):
        return fallback_message
    return normalized


def safe_warning_payloads(
    payload: dict[str, Any],
    warning_factory: WarningFactory,
    *,
    fallback_message: str,
) -> list[dict[str, str]]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []

    safe: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and isinstance(message, str):
            safe.append(
                warning_factory(
                    code,
                    safe_warning_message(message, fallback_message=fallback_message),
                )
            )
    return safe

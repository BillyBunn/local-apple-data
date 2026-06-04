from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .adapters.books import check_books_schema
from .adapters.mail import check_mail_schema, mail_db_relative_path
from .adapters.messages import check_messages_schema
from .adapters.notes import check_notes_schema
from .adapters.podcasts import check_podcasts_schema
from .adapters.reminders import check_reminders_schema
from .adapters.voice_memos import check_voice_memos_schema


DEFAULT_STORE_PATHS = {
    "mail_envelope_index": Path("Library/Mail/V10/MailData/Envelope Index"),
    "messages_store": Path("Library/Messages/chat.db"),
    "voice_memos_store": Path(
        "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/CloudRecordings.db"
    ),
    "safari_bookmarks": Path("Library/Safari/Bookmarks.plist"),
    "books_library_store": Path(
        "Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/"
        "BKLibrary-1-091020131601.sqlite"
    ),
    "books_annotations_store": Path(
        "Library/Containers/com.apple.iBooksX/Data/Documents/AEAnnotation/"
        "AEAnnotation_v10312011_1727_local.sqlite"
    ),
    "podcasts_store": Path(
        "Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/"
        "MTLibrary.sqlite"
    ),
    "music_library_store": Path("Music/Music/Music Library.musiclibrary/Library.musicdb"),
    "tv_library_store": Path("Movies/TV/TV Library.tvlibrary/Library.tvdb"),
    "notes_store": Path("Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"),
    "reminders_stores": Path(
        "Library/Group Containers/group.com.apple.reminders/Container_v1/Stores"
    ),
    "icloud_drive_root": Path("Library/Mobile Documents/com~apple~CloudDocs"),
}

REQUIRED_TOOLS = ("uv", "swift", "sqlite3")
OPTIONAL_TOOLS = ("node", "npm", "shortcuts", "osascript")

ACCESS_REQUIREMENTS = [
    {
        "surface": "mail",
        "permission_class": "Full Disk Access and Automation may be required",
        "status": "covered_by_store_check",
        "check_mode": "schema_only_without_automation_probe",
        "prompts": False,
    },
    {
        "surface": "messages",
        "permission_class": "Full Disk Access and Automation may be required",
        "status": "covered_by_store_check",
        "check_mode": "schema_only_without_automation_probe",
        "prompts": False,
    },
    {
        "surface": "hide_my_email",
        "permission_class": "Full Disk Access may be required",
        "status": "covered_by_mail_store_check",
        "check_mode": "inferred_from_mail_metadata",
        "prompts": False,
    },
    {
        "surface": "voice_memos",
        "permission_class": "Full Disk Access may be required",
        "status": "covered_by_store_check",
        "check_mode": "schema_only",
        "prompts": False,
    },
    {
        "surface": "safari",
        "permission_class": "Full Disk Access may be required",
        "status": "covered_by_store_check",
        "check_mode": "plist_readability",
        "prompts": False,
    },
    {
        "surface": "shortcuts",
        "permission_class": "Shortcuts CLI",
        "status": "covered_by_tool_check",
        "check_mode": "cli_availability_without_listing",
        "prompts": False,
    },
    {
        "surface": "books",
        "permission_class": "Full Disk Access may be required",
        "status": "covered_by_store_check",
        "check_mode": "schema_only",
        "prompts": False,
    },
    {
        "surface": "podcasts",
        "permission_class": "Full Disk Access may be required",
        "status": "covered_by_store_check",
        "check_mode": "schema_only",
        "prompts": False,
    },
    {
        "surface": "music",
        "permission_class": "Automation permission may be required",
        "status": "covered_by_tool_and_app_check",
        "check_mode": "app_and_osascript_availability_without_automation_probe",
        "prompts": False,
    },
    {
        "surface": "tv",
        "permission_class": "Automation permission may be required",
        "status": "covered_by_tool_and_app_check",
        "check_mode": "app_and_osascript_availability_without_automation_probe",
        "prompts": False,
    },
    {
        "surface": "notes",
        "permission_class": "Full Disk Access and Automation may be required",
        "status": "partially_covered_by_store_check",
        "check_mode": "schema_only_without_automation_probe",
        "prompts": False,
    },
    {
        "surface": "calendar",
        "permission_class": "Calendar",
        "status": "checked_on_tool_call",
        "check_mode": "non_prompting_eventkit",
        "prompts": False,
    },
    {
        "surface": "reminders",
        "permission_class": "Reminders",
        "status": "partially_covered_by_store_check",
        "check_mode": "schema_only_and_non_prompting_eventkit_on_tool_call",
        "prompts": False,
    },
    {
        "surface": "contacts",
        "permission_class": "Contacts",
        "status": "checked_on_tool_call",
        "check_mode": "non_prompting_contacts_framework",
        "prompts": False,
    },
    {
        "surface": "photos",
        "permission_class": "Photos",
        "status": "checked_on_tool_call",
        "check_mode": "non_prompting_photokit",
        "prompts": False,
    },
    {
        "surface": "icloud_drive",
        "permission_class": "Local file access",
        "status": "covered_by_store_check",
        "check_mode": "root_readability",
        "prompts": False,
    },
]


def _run_text(command: list[str], timeout: float = 2.0) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _sw_vers() -> dict[str, str | None]:
    output = _run_text(["sw_vers"])
    result: dict[str, str | None] = {
        "product_name": None,
        "product_version": None,
        "build_version": None,
    }
    if not output:
        return result
    key_map = {
        "ProductName": "product_name",
        "ProductVersion": "product_version",
        "BuildVersion": "build_version",
    }
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapped = key_map.get(key.strip())
        if mapped:
            result[mapped] = value.strip()
    return result


def _tool_check(name: str, which: Callable[[str], str | None]) -> dict[str, Any]:
    path = which(name)
    return {
        "name": name,
        "available": path is not None,
        "path": "<redacted>" if path is not None else None,
    }


def _store_check(name: str, path: Path, home: Path) -> dict[str, Any]:
    absolute = home / path
    exists = absolute.exists()
    return {
        "name": name,
        "path": f"~/{path.as_posix()}",
        "present": exists,
        "readable": exists and os.access(absolute, os.R_OK),
        "kind": "directory" if absolute.is_dir() else "file" if absolute.is_file() else "missing",
    }


def _skipped_schema_check(source: str, code: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "source": source,
        "schema_fingerprint": None,
        "tables_checked": [],
        "warnings": [{"code": code, "message": "Store is missing or unreadable."}],
    }


def _schema_error_check(source: str, code: str, tables: list[str]) -> dict[str, Any]:
    return {
        "status": "degraded",
        "source": source,
        "schema_fingerprint": None,
        "tables_checked": tables,
        "warnings": [{"code": code, "message": "Schema check failed safely."}],
    }


def _safe_schema_check(
    source: str,
    code: str,
    tables: list[str],
    check: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return check()
    except Exception:
        return _schema_error_check(source, code, tables)


def _store_by_name(stores: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for store in stores:
        if store["name"] == name:
            return store
    return None


def _store_available(stores: list[dict[str, Any]], name: str) -> bool:
    store = _store_by_name(stores, name)
    return bool(store and store["present"] and store["readable"])


def _store_status(stores: list[dict[str, Any]], name: str) -> str:
    store = _store_by_name(stores, name)
    if store is None:
        return "not_checked"
    if not store["present"]:
        return "missing"
    if not store["readable"]:
        return "unreadable"
    return "ok"


def _tool_available(tools: list[dict[str, Any]], name: str) -> bool:
    return any(tool["name"] == name and tool["available"] for tool in tools)


def _schema_status(schema_checks: dict[str, dict[str, Any]], source: str) -> str:
    check = schema_checks.get(source)
    return str(check.get("status", "unknown")) if check else "not_checked"


def _surface_summary(
    stores: list[dict[str, Any]],
    schema_checks: dict[str, dict[str, Any]],
    optional_tools: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mail_status = _schema_status(schema_checks, "mail")
    return {
        "mail": {
            "status": mail_status,
            "store_status": _store_status(stores, "mail_envelope_index"),
            "schema_check": mail_status,
            "content_status_supported": True,
        },
        "messages": {
            "status": _schema_status(schema_checks, "messages"),
            "store_status": _store_status(stores, "messages_store"),
            "schema_check": _schema_status(schema_checks, "messages"),
        },
        "hide_my_email": {
            "status": mail_status,
            "store_status": _store_status(stores, "mail_envelope_index"),
            "depends_on": "mail",
            "authoritative_inventory": False,
        },
        "voice_memos": {
            "status": _schema_status(schema_checks, "voice_memos"),
            "store_status": _store_status(stores, "voice_memos_store"),
            "schema_check": _schema_status(schema_checks, "voice_memos"),
        },
        "safari": {
            "status": _store_status(stores, "safari_bookmarks"),
            "store_status": _store_status(stores, "safari_bookmarks"),
            "schema_check": "not_applicable",
        },
        "shortcuts": {
            "status": "available" if _tool_available(optional_tools, "shortcuts") else "missing",
            "tool_check": "shortcuts_cli",
            "schema_check": "not_applicable",
            "prompts": False,
        },
        "books": {
            "status": _schema_status(schema_checks, "books"),
            "library_store_status": _store_status(stores, "books_library_store"),
            "annotations_store_status": _store_status(stores, "books_annotations_store"),
            "schema_check": _schema_status(schema_checks, "books"),
        },
        "podcasts": {
            "status": _schema_status(schema_checks, "podcasts"),
            "store_status": _store_status(stores, "podcasts_store"),
            "schema_check": _schema_status(schema_checks, "podcasts"),
        },
        "music": {
            "status": "available"
            if _tool_available(optional_tools, "osascript")
            else "missing",
            "store_status": _store_status(stores, "music_library_store"),
            "tool_check": "osascript",
            "app_check": "music_app_exists",
            "schema_check": "not_applicable",
            "automation_check": "on_exact_tool_call",
            "prompts": False,
        },
        "tv": {
            "status": "available"
            if _tool_available(optional_tools, "osascript")
            else "missing",
            "store_status": _store_status(stores, "tv_library_store"),
            "tool_check": "osascript",
            "app_check": "tv_app_exists",
            "schema_check": "not_applicable",
            "automation_check": "on_exact_tool_call",
            "prompts": False,
        },
        "notes": {
            "status": _schema_status(schema_checks, "notes"),
            "store_status": _store_status(stores, "notes_store"),
            "schema_check": _schema_status(schema_checks, "notes"),
            "automation_check": "on_exact_content_call",
        },
        "calendar": {
            "status": "checked_on_tool_call",
            "permission_check": "non_prompting_eventkit",
            "prompts": False,
        },
        "reminders": {
            "status": _schema_status(schema_checks, "reminders"),
            "store_status": _store_status(stores, "reminders_stores"),
            "schema_check": _schema_status(schema_checks, "reminders"),
            "eventkit_check": "on_tool_call",
        },
        "contacts": {
            "status": "checked_on_tool_call",
            "permission_check": "non_prompting_contacts_framework",
            "prompts": False,
        },
        "photos": {
            "status": "checked_on_tool_call",
            "permission_check": "non_prompting_photokit",
            "prompts": False,
        },
        "icloud_drive": {
            "status": _store_status(stores, "icloud_drive_root"),
            "store_status": _store_status(stores, "icloud_drive_root"),
            "schema_check": "not_applicable",
        },
    }


def build_health(
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    store_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    home = home or Path.home()
    if store_paths is None:
        store_paths = dict(DEFAULT_STORE_PATHS)
        store_paths["mail_envelope_index"] = mail_db_relative_path(home=home)

    required_tools = [_tool_check(name, which) for name in REQUIRED_TOOLS]
    optional_tools = [_tool_check(name, which) for name in OPTIONAL_TOOLS]
    stores = [
        _store_check(name, relative_path, home)
        for name, relative_path in store_paths.items()
    ]
    schema_checks = {
        "mail": _safe_schema_check(
            "mail",
            "mail_schema_unavailable",
            ["messages", "subjects", "mailboxes"],
            lambda: check_mail_schema(db_path=home / store_paths["mail_envelope_index"]),
        )
        if "mail_envelope_index" in store_paths and _store_available(stores, "mail_envelope_index")
        else _skipped_schema_check("mail", "mail_schema_skipped"),
        "messages": _safe_schema_check(
            "messages",
            "messages_schema_unavailable",
            [
                "chat",
                "message",
                "chat_message_join",
                "chat_handle_join",
                "handle",
                "attachment",
                "message_attachment_join",
            ],
            lambda: check_messages_schema(db_path=home / store_paths["messages_store"]),
        )
        if "messages_store" in store_paths and _store_available(stores, "messages_store")
        else _skipped_schema_check("messages", "messages_schema_skipped"),
        "voice_memos": _safe_schema_check(
            "voice_memos",
            "voice_memos_schema_unavailable",
            ["ZCLOUDRECORDING"],
            lambda: check_voice_memos_schema(db_path=home / store_paths["voice_memos_store"]),
        )
        if "voice_memos_store" in store_paths and _store_available(stores, "voice_memos_store")
        else _skipped_schema_check("voice_memos", "voice_memos_schema_skipped"),
        "books": _safe_schema_check(
            "books",
            "books_schema_unavailable",
            ["ZBKLIBRARYASSET", "ZAEANNOTATION"],
            lambda: check_books_schema(
                library_db_path=home / store_paths["books_library_store"],
                annotations_db_path=home / store_paths["books_annotations_store"],
            ),
        )
        if (
            "books_library_store" in store_paths
            and "books_annotations_store" in store_paths
            and _store_available(stores, "books_library_store")
            and _store_available(stores, "books_annotations_store")
        )
        else _skipped_schema_check("books", "books_schema_skipped"),
        "podcasts": _safe_schema_check(
            "podcasts",
            "podcasts_schema_unavailable",
            ["ZMTPODCAST", "ZMTEPISODE"],
            lambda: check_podcasts_schema(db_path=home / store_paths["podcasts_store"]),
        )
        if "podcasts_store" in store_paths and _store_available(stores, "podcasts_store")
        else _skipped_schema_check("podcasts", "podcasts_schema_skipped"),
        "notes": _safe_schema_check(
            "notes",
            "notes_schema_unavailable",
            ["ZICCLOUDSYNCINGOBJECT"],
            lambda: check_notes_schema(db_path=home / store_paths["notes_store"]),
        )
        if "notes_store" in store_paths and _store_available(stores, "notes_store")
        else _skipped_schema_check("notes", "notes_schema_skipped"),
        "reminders": _safe_schema_check(
            "reminders",
            "reminders_schema_unavailable",
            ["ZREMCDREMINDER", "ZREMCDBASELIST"],
            lambda: check_reminders_schema(store_dir=home / store_paths["reminders_stores"]),
        )
        if "reminders_stores" in store_paths and _store_available(stores, "reminders_stores")
        else _skipped_schema_check("reminders", "reminders_schema_skipped"),
    }

    warnings: list[dict[str, str]] = []
    for tool in required_tools:
        if not tool["available"]:
            warnings.append(
                {
                    "code": "required_tool_missing",
                    "message": f"Required tool unavailable: {tool['name']}",
                }
            )
    for store in stores:
        if not store["present"]:
            warnings.append(
                {
                    "code": "store_missing",
                    "message": f"Expected local store is missing: {store['name']}",
                }
            )
        elif not store["readable"]:
            warnings.append(
                {
                    "code": "store_unreadable",
                    "message": f"Expected local store is not readable: {store['name']}",
                }
            )
    for source, schema_check in schema_checks.items():
        if schema_check["status"] == "degraded":
            for warning in schema_check["warnings"]:
                warnings.append(
                    {
                        "code": warning["code"],
                        "message": f"{source}: {warning['message']}",
                    }
                )

    return {
        "schema_version": 1,
        "package_version": __version__,
        "status": "ok" if not warnings else "degraded",
        "privacy": {
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
            "output_tier": "health",
        },
        "macos": _sw_vers(),
        "tools": {
            "required": required_tools,
            "optional": optional_tools,
        },
        "surfaces": _surface_summary(stores, schema_checks, optional_tools),
        "stores": stores,
        "schema_checks": schema_checks,
        "access_requirements": ACCESS_REQUIREMENTS,
        "warnings": warnings,
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }


def health_json(**kwargs: Any) -> str:
    return json.dumps(build_health(**kwargs), indent=2, sort_keys=True)

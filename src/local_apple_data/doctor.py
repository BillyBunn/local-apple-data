from __future__ import annotations

from pathlib import Path
from typing import Any

from .health import build_health


GUIDANCE_BY_CODE = {
    "required_tool_missing": "Install or repair the missing local command-line tool, then rerun health.",
    "store_missing": "Open and sync the relevant Apple app locally, then rerun health.",
    "store_unreadable": "Grant Codex terminal access through macOS privacy settings, then rerun health.",
    "mail_schema_skipped": "Mail schema check was skipped because the local store is missing or unreadable.",
    "messages_schema_skipped": "Messages schema check was skipped because the local store is missing or unreadable.",
    "voice_memos_schema_skipped": "Voice Memos schema check was skipped because the local store is missing or unreadable.",
    "notes_schema_skipped": "Notes schema check was skipped because the local store is missing or unreadable.",
    "reminders_schema_skipped": "Reminders schema check was skipped because the local store is missing or unreadable.",
    "mail_schema_unavailable": "Mail local schema could not be checked. Reopen Mail, allow sync to settle, then rerun health.",
    "messages_schema_unavailable": "Messages local schema could not be checked. Reopen Messages, allow sync to settle, then rerun health.",
    "voice_memos_schema_unavailable": "Voice Memos local schema could not be checked. Reopen Voice Memos, allow sync to settle, then rerun health.",
    "notes_schema_unavailable": "Notes local schema could not be checked. Reopen Notes, allow sync to settle, then rerun health.",
    "reminders_schema_unavailable": "Reminders local schema could not be checked. Reopen Reminders, allow sync to settle, then rerun health.",
    "reminders_store_unavailable": "Reminders local store could not be found or opened. Reopen Reminders, then rerun health.",
    "reminders_store_query_failed": "One Reminders store failed a schema/query check. Keep using healthy stores and rerun health after Reminders sync settles.",
}


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "health",
    }


def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for warning in warnings:
        code = warning.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        deduped.append(
            {
                "code": code,
                "message": GUIDANCE_BY_CODE.get(code, "Review the redacted health output and rerun health after fixing the local condition."),
            }
        )
    return deduped


def _store_summary(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": store["name"],
            "present": store["present"],
            "readable": store["readable"],
            "kind": store["kind"],
        }
        for store in stores
    ]


def _schema_summary(schema_checks: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        source: check.get("status", "unknown")
        for source, check in schema_checks.items()
    }


def build_doctor(
    *,
    home: Path | None = None,
    which=None,
    store_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if home is not None:
        kwargs["home"] = home
    if which is not None:
        kwargs["which"] = which
    if store_paths is not None:
        kwargs["store_paths"] = store_paths
    health = build_health(**kwargs)

    recommendations = _dedupe_warnings(health["warnings"])
    return {
        "schema_version": 1,
        "package_version": health["package_version"],
        "status": health["status"],
        "source": "doctor",
        "privacy": _privacy(),
        "summary": {
            "required_tools_available": all(
                tool["available"] for tool in health["tools"]["required"]
            ),
            "stores": _store_summary(health["stores"]),
            "schema_checks": _schema_summary(health["schema_checks"]),
            "surfaces": health["surfaces"],
            "access_requirements": health["access_requirements"],
        },
        "warnings": recommendations,
        "remediation_mode": "non_mutating",
    }

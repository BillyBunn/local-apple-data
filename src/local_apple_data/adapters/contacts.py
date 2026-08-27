from __future__ import annotations

import base64
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from . import _signing
from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality
from .warning_safety import safe_warning_payloads


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTACTS_HELPER = PROJECT_ROOT / "scripts/contacts_helper.swift"
CONTACTS_HELPER_BUNDLE_ID = "com.local-apple-data.contacts-helper"
CONTACTS_TIMEOUT_SECONDS = 10.0
CONTACTS_REQUEST_ACCESS_TIMEOUT_SECONDS = 190.0
CONTACTS_ARCHIVE_TIMEOUT_SECONDS = 30.0
DEFAULT_LIMIT = 20
DEFAULT_MAX_SCAN_CONTACTS = 10000
DEFAULT_MAX_EXPORT_CONTACTS = 50000
MAX_EXPORT_CONTACTS = 100000
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
CONTACT_HANDLE_PREFIX = "contacts:contact"
CONTACT_GROUP_HANDLE_PREFIX = "contacts:group"
CONTACT_CONTAINER_HANDLE_PREFIX = "contacts:container"
MAX_PREVIEW_FIELD_CHARS = 512
MAX_CONTACT_GROUP_NAME_CHARS = 200
MAX_CONTACT_NOTE_APPEND_CHARS = 4000
MAX_CONTACT_NOTE_SET_CHARS = 12000
MAX_CONTACT_METHODS = 5
MAX_CONTACT_RICH_VALUES = 5
MAX_CONTACT_IMAGE_BYTES = 2_000_000
MAX_CONTACT_BATCH_ITEMS = 10
# Free-form custom labels are preserved verbatim (no lowercasing / space->underscore
# normalization) up to this finite bound. Contacts.framework CNLabeledValue accepts
# arbitrary label strings; only control characters and newlines are rejected.
MAX_LABEL_CHARS = 255
PLAN_OPERATIONS = {
    "batch",
    "create",
    "update",
    "delete",
    "append_note",
    "set_note",
    "replace_note",
    "overwrite_note",
    "clear_note",
    "delete_note",
    "merge_note",
    "add_group_member",
    "remove_group_member",
    "create_group",
    "rename_group",
    "delete_group",
}
NOTE_SET_OPERATIONS = {"set_note", "replace_note", "overwrite_note", "clear_note", "delete_note", "merge_note"}
CONTACT_TYPES = {"person", "organization"}
APPROVAL_TOKEN_PREFIX = "contacts-apply:v1:"
ContactsRunner = Callable[[dict[str, Any], float], dict[str, Any]]
CONTACTS_AUTHORIZATION_STATUSES = {
    "authorized",
    "denied",
    "limited",
    "not_determined",
    "restricted",
    "unknown",
}
CONTACTS_REQUEST_RESULTS = {
    "already_authorized",
    "failed",
    "granted",
    "limited",
    "not_granted",
    "timeout",
    "unavailable",
}
UPDATE_SCALAR_FIELDS = (
    "given_name",
    "family_name",
    "organization_name",
    "department_name",
    "job_title",
    "nickname",
)
UPDATE_METHOD_FIELDS = (
    "email_addresses",
    "phone_numbers",
    "url_addresses",
)
UPDATE_RICH_FIELDS = (
    "postal_addresses",
    "birthday",
    "dates",
    "social_profiles",
    "instant_message_addresses",
    "contact_relations",
)
UPDATE_IMAGE_FIELDS = (
    "image_available",
    "image_sha256",
    "image_bytes",
)
ALL_UPDATE_FIELDS = (*UPDATE_SCALAR_FIELDS, *UPDATE_METHOD_FIELDS, *UPDATE_RICH_FIELDS, *UPDATE_IMAGE_FIELDS)


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


def request_contacts_access(
    *,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    """Prompt explicitly for Contacts access without fetching contact records."""

    if contacts_runner is None:
        try:
            _prepare_contacts_helper_signing()
            app_root = _ensure_contacts_helper_app()
            expected_identity = _signing.signing_identity()
            authority = _signing.app_signing_authority(app_root)
        except (OSError, ValueError, subprocess.SubprocessError):
            return _contacts_request_unavailable(
                "contacts_unavailable",
                "Contacts access request is unavailable through the local Contacts helper.",
            )
        if not authority or (expected_identity and authority != expected_identity):
            return _contacts_request_unavailable(
                "contacts_stable_signing_unavailable",
                "Contacts access requires a stably signed local helper app.",
            )
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "request_contacts_access"},
            CONTACTS_REQUEST_ACCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "timeout",
            "warnings": [
                _warning(
                    "contacts_access_request_timeout",
                    "Contacts access prompt did not complete before timeout.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "unavailable",
            "warnings": [
                _warning(
                    "contacts_unavailable",
                    "Contacts access request is unavailable through the local Contacts helper.",
                )
            ],
        }
    status = str(response.get("status") or "degraded")
    if status not in {"ok", "degraded"}:
        status = "degraded"
    authorization_status = str(response.get("authorization_status") or "unknown")
    if authorization_status not in CONTACTS_AUTHORIZATION_STATUSES:
        authorization_status = "unknown"
    request_result = str(response.get("request_result") or "unavailable")
    if request_result not in CONTACTS_REQUEST_RESULTS:
        request_result = "unavailable"
    if status == "ok" and authorization_status != "authorized":
        status = "degraded"
    return {
        "schema_version": 1,
        "status": status,
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": authorization_status,
        "request_result": request_result,
        "warnings": _safe_warnings(response),
    }


def _contacts_request_unavailable(code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": "unknown",
        "request_result": "unavailable",
        "warnings": [_warning(code, message)],
    }


def _export_privacy(*, contact_data_exported: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": contact_data_exported,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "export",
        "contact_data_exported": contact_data_exported,
    }


def _preview_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "preview",
    }


def _mutation_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "mutation",
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "contacts",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Contacts search requires a non-empty name or organization query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "contacts",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Contacts search requires at least two letters or digits.",
            )
        ],
    }


def search_contacts(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_contacts: int = DEFAULT_MAX_SCAN_CONTACTS,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    response = _contacts_response(
        query=query,
        limit=bounded_limit,
        max_scan_contacts=max_scan_contacts,
        contacts_runner=contacts_runner,
    )
    if response.get("status") != "ok":
        return _contacts_degraded_result(response, content=False)

    results = [_contact_metadata(contact) for contact in response.get("contacts", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "name_or_organization",
            "limit": bounded_limit,
            "max_scan_contacts": _bounded_max_scan(max_scan_contacts),
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def search_contact_groups(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("empty_query", "Contacts group search requires a non-empty group-name query.")
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [_warning("broad_query", "Contacts group search requires at least two letters or digits.")],
        }
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "contact_groups", "query": query, "limit": max(1, min(limit, 50))},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _contacts_degraded_result(
            {"warnings": [_warning("contacts_unavailable", "Contacts groups are unavailable.")]},
            content=False,
        )
    if response.get("status") != "ok":
        return _contacts_degraded_result(response, content=False)
    groups = [_contact_group_metadata(group) for group in response.get("groups", []) if isinstance(group, dict)]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {"scope": "group_name", "limit": max(1, min(limit, 50))},
        "results": groups,
        "result_count": len(groups),
        "warnings": _safe_warnings(response),
    }


def search_contact_containers(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("empty_query", "Contacts container search requires a non-empty container query.")
            ],
        }
    if not has_minimum_query_quality(query):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning("broad_query", "Contacts container search requires at least two letters or digits.")
            ],
        }
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "contact_containers", "query": query, "limit": max(1, min(limit, 50))},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _contacts_degraded_result(
            {"warnings": [_warning("contacts_unavailable", "Contacts containers are unavailable.")]},
            content=False,
        )
    if response.get("status") != "ok":
        return _contacts_degraded_result(response, content=False)
    containers = [
        _contact_container_metadata(container)
        for container in response.get("containers", [])
        if isinstance(container, dict)
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {"scope": "container_name_or_type", "limit": max(1, min(limit, 50))},
        "results": containers,
        "result_count": len(containers),
        "warnings": _safe_warnings(response),
    }


def get_contact_container(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CONTACT_CONTAINER_HANDLE_PREFIX):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [_warning("invalid_handle", "Expected contacts:container:v1 opaque handle.")],
        }
    container_id, container, error = _resolve_container_for_handle(handle, contacts_runner=contacts_runner)
    if error is not None:
        return error
    assert container_id is not None and container is not None
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=True),
        "result": _contact_container_detail(container),
        "result_count": 1,
        "warnings": [],
    }


def list_contact_container_members(
    handle: str,
    *,
    limit: int = DEFAULT_LIMIT,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CONTACT_CONTAINER_HANDLE_PREFIX):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _privacy(),
            "container": None,
            "results": [],
            "result_count": 0,
            "warnings": [_warning("invalid_handle", "Expected contacts:container:v1 opaque handle.")],
        }
    container_id, container, error = _resolve_container_for_handle(handle, contacts_runner=contacts_runner)
    if error is not None:
        if error.get("status") == "not_found":
            return {
                "schema_version": 1,
                "status": "not_found",
                "source": "contacts",
                "privacy": _privacy(),
                "query": {
                    "scope": "selected_container_members",
                    "limit": max(1, min(limit, 50)),
                    "truncated": False,
                },
                "container": None,
                "results": [],
                "result_count": 0,
                "content_returned": False,
                "raw_identifier_returned": False,
                "contact_details_returned": False,
                "warnings": _safe_warnings(error),
            }
        warnings = _safe_warnings(error) or [
            _warning("contacts_unavailable", "Contacts container members are unavailable.")
        ]
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "privacy": _privacy(),
            "authorization_status": error.get("authorization_status"),
            "query": {
                "scope": "selected_container_members",
                "limit": max(1, min(limit, 50)),
                "truncated": False,
            },
            "container": None,
            "results": [],
            "result_count": 0,
            "content_returned": False,
            "raw_identifier_returned": False,
            "contact_details_returned": False,
            "warnings": warnings,
        }
    assert container_id is not None and container is not None
    bounded_limit = max(1, min(limit, 50))
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "contact_container_members", "container_id": container_id, "limit": bounded_limit},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _contacts_container_members_unavailable(container, bounded_limit)
    if response.get("status") != "ok":
        return _contacts_container_members_unavailable(
            container,
            bounded_limit,
            authorization_status=response.get("authorization_status"),
            warnings=_safe_warnings(response),
        )
    raw_contacts = [contact for contact in response.get("contacts", []) if isinstance(contact, dict)]
    contacts = [_contact_metadata(contact) for contact in raw_contacts[:bounded_limit]]
    response_container = response.get("container")
    safe_container = response_container if isinstance(response_container, dict) else container
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "selected_container_members",
            "limit": bounded_limit,
            "truncated": bool(response.get("truncated")) or len(raw_contacts) > bounded_limit,
        },
        "container": _contact_container_metadata(safe_container),
        "results": contacts,
        "result_count": len(contacts),
        "content_returned": False,
        "raw_identifier_returned": False,
        "contact_details_returned": False,
        "warnings": _safe_warnings(response),
    }


def get_contact_group(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CONTACT_GROUP_HANDLE_PREFIX):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [_warning("invalid_handle", "Expected contacts:group:v1 opaque handle.")],
        }
    group_id, group, error = _resolve_group_for_handle(handle, contacts_runner=contacts_runner)
    if error is not None:
        return error
    assert group_id is not None and group is not None
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=True),
        "result": _contact_group_detail(group),
        "result_count": 1,
        "warnings": [],
    }


def list_contact_group_members(
    handle: str,
    *,
    limit: int = DEFAULT_LIMIT,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CONTACT_GROUP_HANDLE_PREFIX):
        return {
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "privacy": _privacy(),
            "group": None,
            "results": [],
            "result_count": 0,
            "warnings": [_warning("invalid_handle", "Expected contacts:group:v1 opaque handle.")],
        }
    group_id, group, error = _resolve_group_for_handle(handle, contacts_runner=contacts_runner)
    if error is not None:
        return {
            **error,
            "group": None,
            "results": [],
            "result_count": 0,
        }
    assert group_id is not None and group is not None
    bounded_limit = max(1, min(limit, 50))
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "contact_group_members", "group_id": group_id, "limit": bounded_limit},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _contacts_group_members_unavailable(group, bounded_limit)
    if response.get("status") != "ok":
        return _contacts_group_members_unavailable(
            group,
            bounded_limit,
            authorization_status=response.get("authorization_status"),
            warnings=_safe_warnings(response),
        )
    raw_contacts = [contact for contact in response.get("contacts", []) if isinstance(contact, dict)]
    contacts = [
        _contact_metadata(contact)
        for contact in raw_contacts[:bounded_limit]
    ]
    response_group = response.get("group")
    safe_group = response_group if isinstance(response_group, dict) else group
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "selected_group_members",
            "limit": bounded_limit,
            "truncated": bool(response.get("truncated")) or len(raw_contacts) > bounded_limit,
        },
        "group": _contact_group_metadata(safe_group),
        "results": contacts,
        "result_count": len(contacts),
        "content_returned": False,
        "raw_identifier_returned": False,
        "contact_details_returned": False,
        "warnings": _safe_warnings(response),
    }


def get_contact(
    handle: str,
    *,
    max_chars: int = DEFAULT_CONTENT_CHARS,
    max_scan_contacts: int = DEFAULT_MAX_SCAN_CONTACTS,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, CONTACT_HANDLE_PREFIX):
        return _invalid_handle_result()

    response = _contacts_response(
        query="",
        limit=_bounded_max_scan(max_scan_contacts),
        max_scan_contacts=max_scan_contacts,
        contacts_runner=contacts_runner,
    )
    if response.get("status") != "ok":
        return _contacts_degraded_result(response, content=True)

    contact_id = _resolve_contact_id(handle, response.get("contacts", []))
    if contact_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = contacts_runner or _run_contacts_helper
    try:
        detail = runner(
            {"command": "contact_by_id", "contact_id": contact_id},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _content_unavailable_result()

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _contacts_degraded_result(detail, content=True)

    contact = detail.get("contact")
    if not isinstance(contact, dict):
        return _content_unavailable_result()

    result = _contact_detail(contact, max_chars=max_chars)
    note_detail_warnings: list[dict[str, str]] = []
    try:
        note_detail = runner(
            {"command": "contact_note_state_by_id", "contact_id": contact_id},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        note_detail = {}
        note_detail_warnings = [
            _warning("contacts_note_unavailable", "Contact note state could not be read safely.")
        ]
    if note_detail.get("status") == "ok" and isinstance(note_detail.get("contact"), dict):
        result.update(_contact_note_public_state(note_detail["contact"]))
    elif note_detail:
        note_detail_warnings = _safe_warnings(note_detail)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": _safe_warnings(response) + _safe_warnings(detail) + note_detail_warnings,
    }


def count_contacts(
    *,
    max_contacts: int = DEFAULT_MAX_EXPORT_CONTACTS,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    runner = contacts_runner or _run_contacts_helper
    bounded_max = _bounded_max_export(max_contacts)
    try:
        response = runner(
            {"command": "contacts_count", "max_contacts": bounded_max},
            CONTACTS_ARCHIVE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _contacts_count_unavailable_result(
            [_warning("contacts_timeout", "Contacts count timed out through the local Contacts helper.")]
        )
    except (OSError, ValueError):
        return _contacts_count_unavailable_result(
            [_warning("contacts_unavailable", "Contacts count is unavailable through the local Contacts helper.")]
        )

    if response.get("status") != "ok":
        return _contacts_count_unavailable_result(
            _safe_warnings(response)
            or [_warning("contacts_count_failed", "Contacts count could not be completed safely.")],
            authorization_status=response.get("authorization_status"),
        )

    live_count = _int_value(response.get("contact_count"))
    scan_truncated = bool(response.get("scan_truncated"))
    warnings = _safe_warnings(response)
    if scan_truncated:
        warnings.append(
            _warning("scan_truncated", "Contacts count stopped at the max_contacts limit.")
        )
    return {
        "schema_version": 1,
        "status": "degraded" if scan_truncated else "ok",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "result": {
            "live_count": live_count,
            "count_complete": not scan_truncated,
            "max_contacts": bounded_max,
        },
        "result_count": live_count,
        "warnings": warnings,
    }


def export_contacts_archive(
    *,
    output_dir: str | Path,
    filename_prefix: str = "contacts",
    max_contacts: int = DEFAULT_MAX_EXPORT_CONTACTS,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    target_dir = Path(output_dir).expanduser()
    if target_dir.exists() and not target_dir.is_dir():
        return _contacts_archive_error(
            [_warning("invalid_output_dir", "Contacts archive output path was not a directory.")]
        )

    runner = contacts_runner or _run_contacts_helper
    bounded_max = _bounded_max_export(max_contacts)
    try:
        response = runner(
            {"command": "contacts_archive", "max_contacts": bounded_max},
            CONTACTS_ARCHIVE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _contacts_archive_error(
            [_warning("contacts_timeout", "Contacts archive timed out through the local Contacts helper.")]
        )
    except (OSError, ValueError):
        return _contacts_archive_error(
            [_warning("contacts_unavailable", "Contacts archive is unavailable through the local Contacts helper.")]
        )

    if response.get("status") != "ok":
        return _contacts_archive_error(
            _safe_warnings(response)
            or [_warning("contacts_archive_failed", "Contacts archive could not be generated safely.")],
            authorization_status=response.get("authorization_status"),
        )

    contacts = response.get("contacts")
    vcard_text = response.get("vcard_text")
    if not isinstance(contacts, list) or not isinstance(vcard_text, str):
        return _contacts_archive_error(
            [_warning("contacts_archive_failed", "Contacts archive helper returned an invalid payload.")],
            authorization_status=response.get("authorization_status"),
        )

    live_count = _int_value(response.get("contact_count"))
    json_contact_count = len(contacts)
    vcard_contact_count = vcard_text.count("BEGIN:VCARD")
    scan_truncated = bool(response.get("scan_truncated"))
    counts_match = (
        not scan_truncated
        and live_count == json_contact_count
        and live_count == vcard_contact_count
    )
    warnings = _safe_warnings(response)
    if scan_truncated:
        warnings.append(
            _warning("scan_truncated", "Contacts archive stopped at the max_contacts limit.")
        )
    if not counts_match:
        warnings.append(
            _warning(
                "archive_count_mismatch",
                "Contacts archive count did not match the live count and is not verified.",
            )
        )

    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    snapshot = {
        "schema_version": 1,
        "archive_schema_version": 1,
        "source": "contacts",
        "created_at": created_at,
        "scope": "local_contacts_unified_store",
        "contact_count": json_contact_count,
        "live_count": live_count,
        "contacts": contacts,
        "warnings": warnings,
    }
    manifest = {
        "schema_version": 1,
        "source": "contacts",
        "created_at": created_at,
        "archive_verified": counts_match,
        "counts_match": counts_match,
        "live_count": live_count,
        "json_contact_count": json_contact_count,
        "vcard_contact_count": vcard_contact_count,
        "scan_truncated": scan_truncated,
        "max_contacts": bounded_max,
        "notes_exported": bool(response.get("notes_exported")),
        "contact_data_returned": False,
        "contact_data_exported": True,
    }

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = _unique_archive_stem(target_dir, _safe_archive_prefix(filename_prefix))
        json_path = target_dir / f"{stem}.json"
        vcard_path = target_dir / f"{stem}.vcf"
        manifest_path = target_dir / f"{stem}-manifest.json"
        json_bytes = json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        vcard_bytes = vcard_text.encode("utf-8")
        manifest.update(
            {
                "json_path": str(json_path),
                "vcard_path": str(vcard_path),
                "manifest_path": str(manifest_path),
                "json_bytes": len(json_bytes),
                "vcard_bytes": len(vcard_bytes),
                "json_sha256": hashlib.sha256(json_bytes).hexdigest(),
                "vcard_sha256": hashlib.sha256(vcard_bytes).hexdigest(),
            }
        )
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        manifest_bytes_len = len(manifest_bytes)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        json_path.write_bytes(json_bytes)
        vcard_path.write_bytes(vcard_bytes)
        manifest_path.write_bytes(manifest_bytes)
    except OSError:
        return _contacts_archive_error(
            [_warning("contacts_archive_write_failed", "Contacts archive files could not be written.")],
            authorization_status=response.get("authorization_status"),
        )

    result = {
        **manifest,
        "manifest_bytes": manifest_bytes_len,
        "manifest_sha256": manifest_sha256,
    }
    return {
        "schema_version": 1,
        "status": "ok" if counts_match else "error",
        "source": "contacts",
        "privacy": _export_privacy(contact_data_exported=True),
        "authorization_status": response.get("authorization_status"),
        "result": result,
        "result_count": live_count,
        "warnings": warnings,
    }


def plan_contact_change(
    operation: str,
    *,
    handle: str = "",
    expected_current_sha256: str = "",
    group_handle: str = "",
    expected_group_sha256: str = "",
    container_handle: str = "",
    expected_container_sha256: str = "",
    group_name: str | None = None,
    contact_type: str = "person",
    given_name: str | None = None,
    family_name: str | None = None,
    organization_name: str | None = None,
    department_name: str | None = None,
    job_title: str | None = None,
    nickname: str | None = None,
    email_addresses: list[Any] | None = None,
    phone_numbers: list[Any] | None = None,
    url_addresses: list[Any] | None = None,
    note_text: str | None = None,
    postal_addresses: list[Any] | None = None,
    birthday: dict[str, Any] | None = None,
    dates: list[Any] | None = None,
    social_profiles: list[Any] | None = None,
    instant_message_addresses: list[Any] | None = None,
    contact_relations: list[Any] | None = None,
    image_path: str | None = None,
    clear_image: bool = False,
    batch_items: list[Any] | None = None,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(
            _warning(
                "invalid_operation",
                "Expected operation batch, create, update, delete, append_note, set_note, clear_note, merge_note, add_group_member, remove_group_member, create_group, rename_group, or delete_group.",
            )
        )
        return _preview_error(warnings)
    if normalized_operation == "batch":
        return _plan_contact_batch(batch_items=batch_items, contacts_runner=contacts_runner)
    if normalized_operation in {"create_group", "rename_group", "delete_group"}:
        return _plan_contact_group_change(
            operation=normalized_operation,
            group_handle=group_handle,
            expected_group_sha256=expected_group_sha256,
            container_handle=container_handle,
            expected_container_sha256=expected_container_sha256,
            group_name=group_name,
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            contact_type=contact_type,
            given_name=given_name,
            family_name=family_name,
            organization_name=organization_name,
            department_name=department_name,
            job_title=job_title,
            nickname=nickname,
            email_addresses=email_addresses,
            phone_numbers=phone_numbers,
            url_addresses=url_addresses,
            note_text=note_text,
            postal_addresses=postal_addresses,
            birthday=birthday,
            dates=dates,
            social_profiles=social_profiles,
            instant_message_addresses=instant_message_addresses,
            contact_relations=contact_relations,
            image_path=image_path,
            clear_image=clear_image,
            contacts_runner=contacts_runner,
        )
    if normalized_operation == "delete":
        if (
            group_handle.strip()
            or expected_group_sha256.strip()
            or container_handle.strip()
            or expected_container_sha256.strip()
            or group_name is not None
            or given_name is not None
            or family_name is not None
            or organization_name is not None
            or department_name is not None
            or job_title is not None
            or nickname is not None
            or email_addresses is not None
            or phone_numbers is not None
            or url_addresses is not None
            or note_text is not None
            or postal_addresses is not None
            or birthday is not None
            or dates is not None
            or social_profiles is not None
            or instant_message_addresses is not None
            or contact_relations is not None
            or image_path is not None
            or clear_image
        ):
            return _preview_error(
                [
                    _warning(
                        "unexpected_delete_field",
                        "Contacts delete accepts only handle and expected_current_sha256.",
                    )
                ]
            )
        return _plan_contact_delete(
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            contacts_runner=contacts_runner,
        )
    if normalized_operation in {"add_group_member", "remove_group_member"}:
        unexpected = any(
            value is not None
            for value in (
                given_name,
                family_name,
                organization_name,
                department_name,
                job_title,
                nickname,
                email_addresses,
                phone_numbers,
                url_addresses,
                note_text,
                postal_addresses,
                birthday,
                dates,
                social_profiles,
                instant_message_addresses,
                contact_relations,
                image_path,
            )
        ) or clear_image or container_handle.strip() or expected_container_sha256.strip() or group_name is not None
        if unexpected:
            return _preview_error(
                [
                    _warning(
                        "unexpected_group_member_field",
                        "Contacts group membership accepts only contact handle/hash and group handle/hash.",
                    )
                ]
            )
        return _plan_contact_group_membership(
            operation=normalized_operation,
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            group_handle=group_handle,
            expected_group_sha256=expected_group_sha256,
            contacts_runner=contacts_runner,
        )
    if normalized_operation in {"append_note", *NOTE_SET_OPERATIONS}:
        if (
            group_handle.strip()
            or expected_group_sha256.strip()
            or container_handle.strip()
            or expected_container_sha256.strip()
            or group_name is not None
            or given_name is not None
            or family_name is not None
            or organization_name is not None
            or department_name is not None
            or job_title is not None
            or nickname is not None
            or email_addresses is not None
            or phone_numbers is not None
            or url_addresses is not None
            or postal_addresses is not None
            or birthday is not None
            or dates is not None
            or social_profiles is not None
            or instant_message_addresses is not None
            or contact_relations is not None
            or image_path is not None
            or clear_image
        ):
            return _preview_error(
                [
                    _warning(
                        "unexpected_append_note_field",
                        "Contacts note operations accept only handle, expected_current_sha256, and note_text.",
                    )
                ]
            )
        if normalized_operation in NOTE_SET_OPERATIONS:
            return _plan_contact_note_set(
                operation=normalized_operation,
                handle=handle,
                expected_current_sha256=expected_current_sha256,
                note_text=note_text,
                contacts_runner=contacts_runner,
            )
        return _plan_contact_note_append(
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            note_text=note_text,
            contacts_runner=contacts_runner,
        )
    if note_text is not None:
        return _preview_error(
            [_warning("unexpected_note_text_field", "Contacts note_text is only valid for append_note.")]
        )
    if normalized_operation == "update":
        if group_handle.strip() or expected_group_sha256.strip() or container_handle.strip() or expected_container_sha256.strip() or group_name is not None:
            return _preview_error(
                [_warning("unexpected_update_target", "Contacts update accepts only contact target fields.")]
            )
        return _plan_contact_update(
            handle=handle,
            expected_current_sha256=expected_current_sha256,
            given_name=given_name,
            family_name=family_name,
            organization_name=organization_name,
            department_name=department_name,
            job_title=job_title,
            nickname=nickname,
            email_addresses=email_addresses,
            phone_numbers=phone_numbers,
            url_addresses=url_addresses,
            postal_addresses=postal_addresses,
            birthday=birthday,
            dates=dates,
            social_profiles=social_profiles,
            instant_message_addresses=instant_message_addresses,
            contact_relations=contact_relations,
            image_path=image_path,
            clear_image=clear_image,
            contacts_runner=contacts_runner,
        )
    if (
        handle.strip()
        or expected_current_sha256.strip()
        or group_handle.strip()
        or expected_group_sha256.strip()
        or group_name is not None
        or postal_addresses is not None
        or birthday is not None
        or dates is not None
        or social_profiles is not None
        or instant_message_addresses is not None
        or contact_relations is not None
        or image_path is not None
        or clear_image
    ):
        return _preview_error(
            [
                _warning(
                    "unexpected_target",
                    "Contacts create planning does not accept contact/group target, group name, rich-field update, or image fields.",
                )
            ]
        )

    normalized_type = contact_type.strip().lower()
    if normalized_type not in CONTACT_TYPES:
        warnings.append(_warning("invalid_contact_type", "Expected contact_type person or organization."))

    fields: dict[str, str] = {}
    for field, value in {
        "given_name": given_name,
        "family_name": family_name,
        "organization_name": organization_name,
        "department_name": department_name,
        "job_title": job_title,
        "nickname": nickname,
    }.items():
        normalized, warning = _bounded_preview_value(
            value or "",
            field=field,
            max_chars=MAX_PREVIEW_FIELD_CHARS,
        )
        fields[field] = normalized
        if warning is not None:
            warnings.append(warning)

    if normalized_type == "person" and not (fields["given_name"] or fields["family_name"]):
        warnings.append(
            _warning("missing_required_field", "Person contact create requires given_name or family_name.")
        )
    if normalized_type == "organization" and not fields["organization_name"]:
        warnings.append(
            _warning("missing_required_field", "Organization contact create requires organization_name.")
        )

    normalized_emails, email_warnings = _normalize_labeled_values(
        email_addresses, field="email_addresses"
    )
    normalized_phones, phone_warnings = _normalize_labeled_values(
        phone_numbers, field="phone_numbers"
    )
    normalized_urls, url_warnings = _normalize_labeled_values(url_addresses, field="url_addresses")
    warnings.extend(email_warnings)
    warnings.extend(phone_warnings)
    warnings.extend(url_warnings)

    if warnings:
        return _preview_error(warnings)

    proposed = {
        "contact_type": normalized_type,
        "given_name": fields["given_name"],
        "family_name": fields["family_name"],
        "organization_name": fields["organization_name"],
        "department_name": fields["department_name"],
        "job_title": fields["job_title"],
        "nickname": fields["nickname"],
        "email_addresses": normalized_emails,
        "phone_numbers": normalized_phones,
        "url_addresses": normalized_urls,
        "email_count": len(normalized_emails),
        "phone_count": len(normalized_phones),
        "url_count": len(normalized_urls),
        "note_status": "blocked",
        "image_data": "blocked",
    }
    target = _contact_create_target(
        container_handle=container_handle,
        expected_container_sha256=expected_container_sha256,
        contacts_runner=contacts_runner,
    )
    if target.get("status") == "error":
        return _preview_error(_safe_warnings(target))

    fingerprint_payload = {
        "operation": normalized_operation,
        "target": target["target"],
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "target": target["target"],
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def apply_contact_change(
    operation: str,
    *,
    handle: str = "",
    expected_current_sha256: str = "",
    group_handle: str = "",
    expected_group_sha256: str = "",
    container_handle: str = "",
    expected_container_sha256: str = "",
    group_name: str | None = None,
    contact_type: str = "person",
    given_name: str | None = None,
    family_name: str | None = None,
    organization_name: str | None = None,
    department_name: str | None = None,
    job_title: str | None = None,
    nickname: str | None = None,
    email_addresses: list[Any] | None = None,
    phone_numbers: list[Any] | None = None,
    url_addresses: list[Any] | None = None,
    note_text: str | None = None,
    postal_addresses: list[Any] | None = None,
    birthday: dict[str, Any] | None = None,
    dates: list[Any] | None = None,
    social_profiles: list[Any] | None = None,
    instant_message_addresses: list[Any] | None = None,
    contact_relations: list[Any] | None = None,
    image_path: str | None = None,
    clear_image: bool = False,
    batch_items: list[Any] | None = None,
    approval_token: str = "",
    confirm_apply: bool = False,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    plan = plan_contact_change(
        operation,
        handle=handle,
        expected_current_sha256=expected_current_sha256,
        group_handle=group_handle,
        expected_group_sha256=expected_group_sha256,
        container_handle=container_handle,
        expected_container_sha256=expected_container_sha256,
        group_name=group_name,
        contact_type=contact_type,
        given_name=given_name,
        family_name=family_name,
        organization_name=organization_name,
        department_name=department_name,
        job_title=job_title,
        nickname=nickname,
        email_addresses=email_addresses,
        phone_numbers=phone_numbers,
        url_addresses=url_addresses,
        note_text=note_text,
        postal_addresses=postal_addresses,
        birthday=birthday,
        dates=dates,
        social_profiles=social_profiles,
        instant_message_addresses=instant_message_addresses,
        contact_relations=contact_relations,
        image_path=image_path,
        clear_image=clear_image,
        batch_items=batch_items,
        contacts_runner=contacts_runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Contacts apply requires a valid plan preview.")],
            plan=plan,
        )
    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Contacts apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Contacts apply approval token did not match the plan.")],
            plan=plan,
        )
    if str(preview.get("operation") or "") == "batch":
        return _apply_contact_batch(
            plan=plan,
            batch_items=batch_items,
            approval_fingerprint=str(fingerprint or ""),
            contacts_runner=contacts_runner,
        )

    runner = contacts_runner or _run_contacts_helper
    try:
        helper_payload = _apply_helper_payload(
            preview,
            handle=handle,
            image_path=image_path,
            contacts_runner=contacts_runner,
        )
        if helper_payload.get("status") == "error":
            return _apply_error(_safe_warnings(helper_payload), plan=plan)
        applied = runner(helper_payload, CONTACTS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("contacts_timeout", "Contacts apply timed out through the local Contacts helper.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("contacts_unavailable", "Contacts apply is unavailable through the local Contacts helper.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("contacts_apply_failed", "Contact change could not be applied safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            authorization_status=applied.get("authorization_status"),
        )

    if str(preview["operation"]) == "delete_group":
        if bool(applied.get("deleted")) and bool(applied.get("verified_absent")):
            target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "privacy": _mutation_privacy(content_inspected=False),
                "authorization_status": applied.get("authorization_status"),
                "mode": "apply",
                "operation": "delete_group",
                "mutation_applied": True,
                "apply_available": True,
                "idempotency_key": preview["idempotency_key"],
                "approval": {
                    "approval_fingerprint": fingerprint,
                    "approval_token_verified": True,
                },
                "read_back": {
                    "group_handle": target.get("group_handle"),
                    "deleted": True,
                    "verified_absent": True,
                    "contacts_deleted": False,
                },
                "result_count": 0,
                "warnings": _safe_warnings(applied),
            }
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("read_back_unavailable", "Contacts group delete absence proof was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=bool(applied.get("deleted")),
            authorization_status=applied.get("authorization_status"),
        )

    if str(preview["operation"]) in {"create_group", "rename_group"}:
        group = applied.get("group")
        if not isinstance(group, dict):
            return _apply_error(
                [_warning("read_back_unavailable", "Contacts group read-back was unavailable.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": _mutation_privacy(content_inspected=True),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": _contact_group_detail(group),
            "result_count": 1,
            "warnings": _safe_warnings(applied),
        }

    if str(preview["operation"]) == "delete":
        if bool(applied.get("deleted")) and bool(applied.get("verified_absent")):
            target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "privacy": _mutation_privacy(content_inspected=False),
                "authorization_status": applied.get("authorization_status"),
                "mode": "apply",
                "operation": "delete",
                "mutation_applied": True,
                "apply_available": True,
                "idempotency_key": preview["idempotency_key"],
                "approval": {
                    "approval_fingerprint": fingerprint,
                    "approval_token_verified": True,
                },
                "read_back": {
                    "handle": target.get("handle") or handle.strip(),
                    "deleted": True,
                    "verified_absent": True,
                },
                "result_count": 0,
                "warnings": _safe_warnings(applied),
            }
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("read_back_unavailable", "Contacts delete read-back absence proof was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=bool(applied.get("deleted")),
            authorization_status=applied.get("authorization_status"),
        )

    if str(preview["operation"]) in {"add_group_member", "remove_group_member"}:
        group = applied.get("group")
        if not isinstance(group, dict) or not bool(applied.get("membership_verified")):
            return _apply_error(
                [_warning("read_back_unavailable", "Contacts group membership read-back was unavailable.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=bool(applied.get("membership_changed")),
                authorization_status=applied.get("authorization_status"),
            )
        target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
        read_back = {
            "handle": target.get("handle") or handle.strip(),
            "group_handle": target.get("group_handle"),
            "group_name": _bounded_string(group.get("name"), 500),
            "member_count": _int_value(group.get("member_count")),
            "membership_verified": True,
        }
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": _mutation_privacy(content_inspected=True),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": read_back,
            "result_count": 1,
            "warnings": _safe_warnings(applied),
        }

    if str(preview["operation"]) in {"append_note", "set_note"}:
        contact = applied.get("contact")
        if not isinstance(contact, dict):
            return _apply_error(
                [_warning("read_back_unavailable", "Contacts note update succeeded but read-back was unavailable.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
        proposed = preview.get("proposed") if isinstance(preview.get("proposed"), dict) else {}
        read_back = {
            "handle": target.get("handle") or handle.strip(),
            **_contact_note_public_state(contact),
        }
        if str(preview["operation"]) == "append_note":
            read_back["appended_note_chars"] = _int_value(proposed.get("append_chars"))
        else:
            read_back["set_note_chars"] = _int_value(proposed.get("resulting_note_chars"))
            read_back["operation_alias"] = preview.get("operation_alias") or "set_note"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "privacy": _mutation_privacy(content_inspected=True),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "operation_alias": preview.get("operation_alias") if str(preview["operation"]) == "set_note" else None,
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": read_back,
            "result_count": 1,
            "warnings": _safe_warnings(applied),
        }

    contact = applied.get("contact")
    if not isinstance(contact, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Contacts apply succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _mutation_privacy(content_inspected=True),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": str(preview["operation"]),
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": _contact_detail(contact, max_chars=MAX_CONTENT_CHARS),
        "result_count": 1,
        "warnings": _safe_warnings(applied),
    }


def _contacts_response(
    *,
    query: str,
    limit: int,
    max_scan_contacts: int,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    runner = contacts_runner or _run_contacts_helper
    try:
        return runner(
            {
                "command": "contacts",
                "query": query,
                "limit": max(1, min(limit, DEFAULT_MAX_SCAN_CONTACTS)),
                "max_contacts": _bounded_max_scan(max_scan_contacts),
            },
            CONTACTS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "contacts_timeout",
                    "Contacts access timed out through the local Contacts helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "contacts_unavailable",
                    "Contacts access is unavailable through the local Contacts helper.",
                )
            ],
        }


def _contacts_helper_app_root() -> Path:
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "local-apple-data"
        / "ContactsHelper.app"
    )


def _contacts_helper_source_digest() -> str:
    return hashlib.sha256(CONTACTS_HELPER.read_bytes()).hexdigest()


def _contacts_helper_info_plist() -> dict[str, Any]:
    return {
        "CFBundleExecutable": "contacts_helper",
        "CFBundleIdentifier": CONTACTS_HELPER_BUNDLE_ID,
        "CFBundleName": "Local Apple Data Contacts Helper",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "14.0",
        "NSContactsUsageDescription": (
            "Allow local-apple-data to read and write local Contacts only when explicitly requested."
        ),
    }


def _contacts_helper_entitlements() -> dict[str, bool]:
    # `com.apple.developer.contacts.notes` requires an Apple provisioning
    # profile and makes a locally self-signed helper unlaunchable. Keep the
    # ordinary read/write Contacts entitlement here; note access remains
    # capability-detected and fails closed when unavailable.
    return {"com.apple.security.personal-information.addressbook": True}


def _prepare_contacts_helper_signing() -> None:
    try:
        identity = _signing.provision_local_signing_identity()
        _signing.invalidate_app_if_signing_mismatch(
            _contacts_helper_app_root(), identity
        )
    except (OSError, ValueError):
        return


def _ensure_contacts_helper_app() -> Path:
    app_root = _contacts_helper_app_root()
    digest = _contacts_helper_source_digest()
    if _contacts_helper_app_valid(app_root, digest):
        return app_root

    swiftc = shutil.which("swiftc")
    codesign = shutil.which("codesign")
    if not swiftc or not codesign:
        raise ValueError("Contacts helper build tools unavailable.")

    parent = app_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    staging_root = Path(tempfile.mkdtemp(prefix=".ContactsHelper.", dir=parent))
    staged_app = staging_root / "ContactsHelper.app"
    contents = staged_app / "Contents"
    executable = contents / "MacOS" / "contacts_helper"
    digest_file = contents / "Resources" / "source.sha256"
    entitlements_file = contents / "Resources" / "entitlements.plist"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(_contacts_helper_info_plist(), handle)
    with entitlements_file.open("wb") as handle:
        plistlib.dump(_contacts_helper_entitlements(), handle)
    digest_file.write_text(digest)
    built = subprocess.run(
        [swiftc, str(CONTACTS_HELPER), "-o", str(executable)],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if built.returncode != 0:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ValueError("Contacts helper app build failed.")
    signed = _signing.sign_helper_app(codesign, entitlements_file, staged_app)
    if signed.returncode != 0 or not _contacts_helper_app_valid(staged_app, digest):
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ValueError("Contacts helper app signing failed.")

    if app_root.is_symlink() or app_root.is_file():
        app_root.unlink()
    elif app_root.exists():
        shutil.rmtree(app_root)
    staged_app.rename(app_root)
    shutil.rmtree(staging_root, ignore_errors=True)
    return app_root


def _contacts_helper_app_valid(app_root: Path, digest: str) -> bool:
    contents = app_root / "Contents"
    executable = contents / "MacOS" / "contacts_helper"
    digest_file = contents / "Resources" / "source.sha256"
    info_plist = contents / "Info.plist"
    entitlements_file = contents / "Resources" / "entitlements.plist"
    if not all(path.is_file() for path in (executable, digest_file, info_plist, entitlements_file)):
        return False
    try:
        if digest_file.read_text().strip() != digest:
            return False
        with info_plist.open("rb") as handle:
            if plistlib.load(handle) != _contacts_helper_info_plist():
                return False
        with entitlements_file.open("rb") as handle:
            if plistlib.load(handle) != _contacts_helper_entitlements():
                return False
    except (OSError, plistlib.InvalidFileException):
        return False
    codesign = shutil.which("codesign")
    if not codesign:
        return False
    try:
        verified = subprocess.run(
            [codesign, "--verify", "--deep", "--strict", str(app_root)],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if verified.returncode != 0:
            return False
        entitlements = subprocess.run(
            [codesign, "-d", "--entitlements", ":-", str(app_root)],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if entitlements.returncode != 0:
            return False
        try:
            signed_entitlements = plistlib.loads(
                (entitlements.stdout or "").encode("utf-8")
            )
        except plistlib.InvalidFileException:
            return False
        if not isinstance(signed_entitlements, dict):
            return False
        if (
            signed_entitlements.get(
                "com.apple.security.personal-information.addressbook"
            )
            is not True
            or "com.apple.developer.contacts.notes" in signed_entitlements
        ):
            return False
        signature = subprocess.run(
            [codesign, "-dvv", str(app_root)],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if signature.returncode != 0:
        return False
    signature_output = (signature.stdout or "") + (signature.stderr or "")
    identifiers = [
        line.strip().removeprefix("Identifier=")
        for line in signature_output.splitlines()
        if line.strip().startswith("Identifier=")
    ]
    return identifiers == [CONTACTS_HELPER_BUNDLE_ID]


def _run_contacts_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    app_root = _ensure_contacts_helper_app()
    opener = shutil.which("open") or "/usr/bin/open"
    with tempfile.TemporaryDirectory(prefix="local-apple-data-contacts-") as directory:
        os.chmod(directory, 0o700)
        input_path = Path(directory) / "input.json"
        output_path = Path(directory) / "output.json"
        input_fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(input_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
        output_fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(output_fd)
        completed = subprocess.run(
            [
                opener,
                "-W",
                "-n",
                str(app_root),
                "--args",
                "--input-json-file",
                str(input_path),
                "--output-json-file",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError("Contacts helper app failed.")
        output_text = output_path.read_text()
        if not output_text:
            raise ValueError("Contacts helper app returned no output.")
        parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("Contacts helper returned invalid JSON.")
    return parsed


def _contact_metadata(contact: dict[str, Any]) -> dict[str, Any]:
    contact_id = str(contact.get("contact_id") or "")
    return {
        "handle": make_opaque_handle(CONTACT_HANDLE_PREFIX, contact_id),
        "display_name": _bounded_string(contact.get("display_name"), 500),
        "contact_type": contact.get("contact_type"),
        "given_name": _bounded_string(contact.get("given_name"), 200),
        "family_name": _bounded_string(contact.get("family_name"), 200),
        "nickname": _bounded_string(contact.get("nickname"), 200),
        "organization_name": _bounded_string(contact.get("organization_name"), 500),
        "department_name": _bounded_string(contact.get("department_name"), 500),
        "job_title": _bounded_string(contact.get("job_title"), 500),
        "email_count": _int_value(contact.get("email_count")),
        "phone_count": _int_value(contact.get("phone_count")),
        "postal_address_count": _int_value(contact.get("postal_address_count")),
        "url_count": _int_value(contact.get("url_count")),
        "social_profile_count": _int_value(contact.get("social_profile_count")),
        "instant_message_count": _int_value(contact.get("instant_message_count")),
        "relation_count": _int_value(contact.get("relation_count")),
        "dates_count": _int_value(contact.get("dates_count")),
        "birthday_present": bool(contact.get("birthday_present")),
        "image_available": bool(contact.get("image_available")),
        "note_status": contact.get("note_status") or "requires_entitlement",
    }


def _contact_group_metadata(group: dict[str, Any]) -> dict[str, Any]:
    group_id = str(group.get("group_id") or "")
    return {
        "handle": make_opaque_handle(CONTACT_GROUP_HANDLE_PREFIX, group_id),
        "name": _bounded_string(group.get("name"), 500),
        "member_count": _int_value(group.get("member_count")),
    }


def _contact_group_detail(group: dict[str, Any]) -> dict[str, Any]:
    result = _contact_group_metadata(group)
    result["group_safe_sha256"] = _contact_group_sha256(group)
    return result


def _contact_container_metadata(container: dict[str, Any]) -> dict[str, Any]:
    container_id = str(container.get("container_id") or "")
    return {
        "handle": make_opaque_handle(CONTACT_CONTAINER_HANDLE_PREFIX, container_id),
        "name": _bounded_string(container.get("name"), 500),
        "type": _bounded_string(container.get("type"), 100),
    }


def _contact_container_detail(container: dict[str, Any]) -> dict[str, Any]:
    result = _contact_container_metadata(container)
    result["container_safe_sha256"] = _contact_container_sha256(container)
    return result


def _contact_container_state(container: dict[str, Any]) -> dict[str, str]:
    return {
        "name": _state_string(container.get("name")),
        "type": _state_string(container.get("type")),
    }


def _contact_container_sha256(container: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _contact_container_state(container),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _contact_group_state(group: dict[str, Any]) -> dict[str, str]:
    return {
        "name": _state_string(group.get("name")),
        "member_count": _canonical_state_value(_int_value(group.get("member_count"))),
        "member_ids": _canonical_state_value(sorted(str(item) for item in group.get("member_ids", []) or [])),
    }


def _contact_group_sha256(group: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _contact_group_state(group),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _contact_detail(contact: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    result = _contact_metadata(contact)
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    result.update(
        {
            "update_safe_sha256": _contact_update_sha256(contact),
            "delete_safe_sha256": _contact_delete_sha256(contact),
            "name_prefix": _bounded_string(contact.get("name_prefix"), 200),
            "middle_name": _bounded_string(contact.get("middle_name"), 200),
            "previous_family_name": _bounded_string(
                contact.get("previous_family_name"),
                200,
            ),
            "name_suffix": _bounded_string(contact.get("name_suffix"), 200),
            "email_addresses": _bounded_payload(contact.get("email_addresses"), bounded_chars),
            "phone_numbers": _bounded_payload(contact.get("phone_numbers"), bounded_chars),
            "postal_addresses": _bounded_payload(contact.get("postal_addresses"), bounded_chars),
            "url_addresses": _bounded_payload(contact.get("url_addresses"), bounded_chars),
            "birthday": _bounded_payload(contact.get("birthday"), bounded_chars),
            "dates": _bounded_payload(contact.get("dates"), bounded_chars),
            "social_profiles": _bounded_payload(contact.get("social_profiles"), bounded_chars),
            "instant_message_addresses": _bounded_payload(
                contact.get("instant_message_addresses"),
                bounded_chars,
            ),
            "contact_relations": _bounded_payload(
                contact.get("contact_relations"),
                bounded_chars,
            ),
            "image_bytes": _int_value(contact.get("image_bytes")),
            "image_sha256": _bounded_string(contact.get("image_sha256"), 128),
        }
    )
    return result


def _resolve_contact_id(handle: str, contacts: Any) -> str | None:
    if not isinstance(contacts, list):
        return None
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        contact_id = str(contact.get("contact_id") or "")
        if contact_id and opaque_handle_matches(handle, CONTACT_HANDLE_PREFIX, contact_id):
            return contact_id
    return None


def _resolve_contact_for_handle(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    response = _contacts_response(
        query="",
        limit=DEFAULT_MAX_SCAN_CONTACTS,
        max_scan_contacts=DEFAULT_MAX_SCAN_CONTACTS,
        contacts_runner=contacts_runner,
    )
    if response.get("status") != "ok":
        return None, None, _contacts_degraded_result(response, content=True)
    contact_id = _resolve_contact_id(handle, response.get("contacts", []))
    if contact_id is None:
        return None, None, {
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [],
        }
    runner = contacts_runner or _run_contacts_helper
    try:
        detail = runner(
            {"command": "contact_by_id", "contact_id": contact_id},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None, None, _content_unavailable_result()
    if detail.get("status") != "ok":
        return None, None, _contacts_degraded_result(detail, content=True)
    contact = detail.get("contact")
    if not isinstance(contact, dict):
        return None, None, _content_unavailable_result()
    return contact_id, contact, None


def _resolve_contact_update_state_for_handle(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    response = _contacts_response(
        query="",
        limit=DEFAULT_MAX_SCAN_CONTACTS,
        max_scan_contacts=DEFAULT_MAX_SCAN_CONTACTS,
        contacts_runner=contacts_runner,
    )
    if response.get("status") != "ok":
        return None, None, _contacts_degraded_result(response, content=True)
    contact_id = _resolve_contact_id(handle, response.get("contacts", []))
    if contact_id is None:
        return None, None, {
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [],
        }
    runner = contacts_runner or _run_contacts_helper
    try:
        detail = runner(
            {"command": "contact_update_state_by_id", "contact_id": contact_id},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None, None, _content_unavailable_result()
    if detail.get("status") != "ok":
        return None, None, _contacts_degraded_result(detail, content=True)
    contact = detail.get("contact")
    if not isinstance(contact, dict):
        return None, None, _content_unavailable_result()
    return contact_id, contact, None


def _resolve_contact_note_state_for_handle(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    response = _contacts_response(
        query="",
        limit=DEFAULT_MAX_SCAN_CONTACTS,
        max_scan_contacts=DEFAULT_MAX_SCAN_CONTACTS,
        contacts_runner=contacts_runner,
    )
    if response.get("status") != "ok":
        return None, None, _contacts_degraded_result(response, content=True)
    contact_id = _resolve_contact_id(handle, response.get("contacts", []))
    if contact_id is None:
        return None, None, {
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "privacy": _content_privacy(content_inspected=False),
            "result": None,
            "warnings": [],
        }
    runner = contacts_runner or _run_contacts_helper
    try:
        detail = runner(
            {"command": "contact_note_state_by_id", "contact_id": contact_id},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None, None, _content_unavailable_result()
    if detail.get("status") != "ok":
        return None, None, _contacts_degraded_result(detail, content=True)
    contact = detail.get("contact")
    if not isinstance(contact, dict):
        return None, None, _content_unavailable_result()
    return contact_id, contact, None


def _resolve_container_for_handle(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "contact_containers", "query": "", "limit": 100},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None, None, _contacts_degraded_result(
            {"warnings": [_warning("contacts_unavailable", "Contacts containers are unavailable.")]},
            content=True,
        )
    if response.get("status") != "ok":
        return None, None, _contacts_degraded_result(response, content=True)
    for container in response.get("containers", []):
        if not isinstance(container, dict):
            continue
        container_id = str(container.get("container_id") or "")
        if container_id and opaque_handle_matches(handle, CONTACT_CONTAINER_HANDLE_PREFIX, container_id):
            try:
                detail = runner(
                    {"command": "contact_container_by_id", "container_id": container_id},
                    CONTACTS_TIMEOUT_SECONDS,
                )
            except (subprocess.TimeoutExpired, OSError, ValueError):
                return None, None, _content_unavailable_result()
            if detail.get("status") != "ok":
                return None, None, _contacts_degraded_result(detail, content=True)
            exact_container = detail.get("container")
            if not isinstance(exact_container, dict):
                return None, None, _content_unavailable_result()
            return container_id, exact_container, None
    return None, None, {
        "schema_version": 1,
        "status": "not_found",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [],
    }


def _resolve_group_for_handle(
    handle: str,
    *,
    contacts_runner: ContactsRunner | None,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    runner = contacts_runner or _run_contacts_helper
    try:
        response = runner(
            {"command": "contact_groups", "query": "", "limit": DEFAULT_MAX_SCAN_CONTACTS},
            CONTACTS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None, None, _contacts_degraded_result(
            {"warnings": [_warning("contacts_unavailable", "Contacts groups are unavailable.")]},
            content=True,
        )
    if response.get("status") != "ok":
        return None, None, _contacts_degraded_result(response, content=True)
    for group in response.get("groups", []):
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id") or "")
        if group_id and opaque_handle_matches(handle, CONTACT_GROUP_HANDLE_PREFIX, group_id):
            try:
                detail = runner(
                    {"command": "contact_group_by_id", "group_id": group_id},
                    CONTACTS_TIMEOUT_SECONDS,
                )
            except (subprocess.TimeoutExpired, OSError, ValueError):
                return None, None, _content_unavailable_result()
            if detail.get("status") != "ok":
                return None, None, _contacts_degraded_result(detail, content=True)
            exact_group = detail.get("group")
            if not isinstance(exact_group, dict):
                return None, None, _content_unavailable_result()
            return group_id, exact_group, None
    return None, None, {
        "schema_version": 1,
        "status": "not_found",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [],
    }


def _contact_update_state(contact: dict[str, Any]) -> dict[str, str]:
    image_available = contact.get("image_available")
    image_bytes = contact.get("image_bytes")
    return {
        "contact_type": _state_string(contact.get("contact_type")),
        "given_name": _state_string(contact.get("given_name")),
        "family_name": _state_string(contact.get("family_name")),
        "organization_name": _state_string(contact.get("organization_name")),
        "department_name": _state_string(contact.get("department_name")),
        "job_title": _state_string(contact.get("job_title")),
        "nickname": _state_string(contact.get("nickname")),
        "email_addresses": _canonical_json_state_value(contact.get("email_addresses")),
        "phone_numbers": _canonical_json_state_value(contact.get("phone_numbers")),
        "url_addresses": _canonical_json_state_value(contact.get("url_addresses")),
        "postal_addresses": _canonical_json_state_value(contact.get("postal_addresses")),
        "birthday": _canonical_json_state_value(contact.get("birthday")),
        "dates": _canonical_json_state_value(contact.get("dates")),
        "social_profiles": _canonical_json_state_value(contact.get("social_profiles")),
        "instant_message_addresses": _canonical_json_state_value(contact.get("instant_message_addresses")),
        "contact_relations": _canonical_json_state_value(contact.get("contact_relations")),
        "image_available": (
            _state_string(image_available)
            if isinstance(image_available, str)
            else _canonical_state_value(bool(image_available))
        ),
        "image_sha256": _state_string(contact.get("image_sha256")),
        "image_bytes": (
            _state_string(image_bytes)
            if isinstance(image_bytes, str)
            else _canonical_state_value(_int_value(image_bytes))
        ),
    }


def _contact_update_sha256(contact: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _contact_update_state(contact),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _contact_delete_state(contact: dict[str, Any]) -> dict[str, str]:
    fields = {
        "display_name": contact.get("display_name"),
        "contact_type": contact.get("contact_type"),
        "given_name": contact.get("given_name"),
        "family_name": contact.get("family_name"),
        "nickname": contact.get("nickname"),
        "organization_name": contact.get("organization_name"),
        "department_name": contact.get("department_name"),
        "job_title": contact.get("job_title"),
        "email_count": _int_value(contact.get("email_count")),
        "phone_count": _int_value(contact.get("phone_count")),
        "postal_address_count": _int_value(contact.get("postal_address_count")),
        "url_count": _int_value(contact.get("url_count")),
        "social_profile_count": _int_value(contact.get("social_profile_count")),
        "instant_message_count": _int_value(contact.get("instant_message_count")),
        "relation_count": _int_value(contact.get("relation_count")),
        "dates_count": _int_value(contact.get("dates_count")),
        "birthday_present": bool(contact.get("birthday_present")),
        "image_available": bool(contact.get("image_available")),
        "note_status": contact.get("note_status") or "requires_entitlement",
        "name_prefix": contact.get("name_prefix"),
        "middle_name": contact.get("middle_name"),
        "previous_family_name": contact.get("previous_family_name"),
        "name_suffix": contact.get("name_suffix"),
        "email_addresses": contact.get("email_addresses"),
        "phone_numbers": contact.get("phone_numbers"),
        "postal_addresses": contact.get("postal_addresses"),
        "url_addresses": contact.get("url_addresses"),
        "birthday": contact.get("birthday"),
        "dates": contact.get("dates"),
        "social_profiles": contact.get("social_profiles"),
        "instant_message_addresses": contact.get("instant_message_addresses"),
        "contact_relations": contact.get("contact_relations"),
    }
    return {field: _canonical_state_value(value) for field, value in fields.items()}


def _contact_delete_sha256(contact: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _contact_delete_state(contact),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _contact_note_text(contact: dict[str, Any]) -> str:
    return _state_string(contact.get("note_text"))


def _contact_note_sha256(note_text: str) -> str:
    return hashlib.sha256(_state_string(note_text).encode("utf-8")).hexdigest()


def _contact_note_public_state(contact: dict[str, Any]) -> dict[str, Any]:
    note_text = _contact_note_text(contact)
    return {
        "note_status": contact.get("note_status") or "available",
        "note_chars": len(note_text),
        "note_safe_sha256": _contact_note_sha256(note_text),
    }


def _canonical_state_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _state_string(value)
    if isinstance(value, bool | int | float | list | dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _state_string(value)


def _canonical_json_state_value(value: Any) -> str:
    if isinstance(value, str):
        text = _state_string(value)
        if text.startswith(("[", "{")):
            try:
                return _canonical_state_value(json.loads(text))
            except json.JSONDecodeError:
                return text
        return text
    return _canonical_state_value(value)


def _normalize_sha256(value: str) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().lower()
    if not normalized:
        return "", _warning("missing_required_field", "Missing required field: expected_current_sha256.")
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        return "", _warning(
            "invalid_expected_sha256",
            "expected_current_sha256 must be a 64-character SHA-256 hex digest.",
        )
    return normalized, None


def _provided_update_fields(
    values: dict[str, str | None],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    provided: dict[str, str] = {}
    warnings: list[dict[str, str]] = []
    for field, value in values.items():
        if value is None:
            continue
        normalized, warning = _bounded_preview_value(
            value,
            field=field,
            max_chars=MAX_PREVIEW_FIELD_CHARS,
        )
        if warning is not None:
            warnings.append(warning)
            continue
        provided[field] = normalized
    return provided, warnings


def _contact_create_target(
    *,
    container_handle: str,
    expected_container_sha256: str,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_container_handle = container_handle.strip()
    if not normalized_container_handle:
        if expected_container_sha256.strip():
            return {
                "status": "error",
                "warnings": [
                    _warning(
                        "unexpected_container_hash",
                        "Contacts default-container create does not accept expected_container_sha256.",
                    )
                ],
            }
        return {"status": "ok", "target": {"container": "default_contacts_container"}}
    if not is_opaque_handle(normalized_container_handle, CONTACT_CONTAINER_HANDLE_PREFIX):
        return {
            "status": "error",
            "warnings": [
                _warning("invalid_container_handle", "Expected contacts:container:v1 opaque handle.")
            ],
        }
    normalized_container_sha, sha_warning = _normalize_sha256(expected_container_sha256)
    if sha_warning is not None:
        message = (
            "Missing required field: expected_container_sha256."
            if sha_warning["code"] == "missing_required_field"
            else "expected_container_sha256 must be a 64-character SHA-256 hex digest."
        )
        sha_warning = {**sha_warning, "message": message}
        return {"status": "error", "warnings": [sha_warning]}
    _container_id, container, error = _resolve_container_for_handle(
        normalized_container_handle,
        contacts_runner=contacts_runner,
    )
    if error is not None:
        return {
            "status": "error",
            "warnings": _safe_warnings(error)
            or [_warning("invalid_container_handle", "Contacts container was not found.")],
        }
    assert container is not None
    if _contact_container_sha256(container) != normalized_container_sha:
        return {
            "status": "error",
            "warnings": [
                _warning("current_container_changed", "Contacts container state did not match the expected hash.")
            ],
        }
    return {
        "status": "ok",
        "target": {
            "container_handle": normalized_container_handle,
            "expected_container_sha256": normalized_container_sha,
            "container_name": _bounded_string(container.get("name"), 500),
            "container_type": _bounded_string(container.get("type"), 100),
        },
    }


def _unexpected_group_change_field(
    *,
    handle: str,
    expected_current_sha256: str,
    contact_type: str,
    given_name: str | None,
    family_name: str | None,
    organization_name: str | None,
    department_name: str | None,
    job_title: str | None,
    nickname: str | None,
    email_addresses: list[Any] | None,
    phone_numbers: list[Any] | None,
    url_addresses: list[Any] | None,
    note_text: str | None,
    postal_addresses: list[Any] | None,
    birthday: dict[str, Any] | None,
    dates: list[Any] | None,
    social_profiles: list[Any] | None,
    instant_message_addresses: list[Any] | None,
    contact_relations: list[Any] | None,
    image_path: str | None,
    clear_image: bool,
) -> bool:
    return (
        bool(handle.strip())
        or bool(expected_current_sha256.strip())
        or contact_type.strip().lower() != "person"
        or given_name is not None
        or family_name is not None
        or organization_name is not None
        or department_name is not None
        or job_title is not None
        or nickname is not None
        or email_addresses is not None
        or phone_numbers is not None
        or url_addresses is not None
        or note_text is not None
        or postal_addresses is not None
        or birthday is not None
        or dates is not None
        or social_profiles is not None
        or instant_message_addresses is not None
        or contact_relations is not None
        or image_path is not None
        or clear_image
    )


def _plan_contact_group_change(
    *,
    operation: str,
    group_handle: str,
    expected_group_sha256: str,
    container_handle: str,
    expected_container_sha256: str,
    group_name: str | None,
    handle: str,
    expected_current_sha256: str,
    contact_type: str,
    given_name: str | None,
    family_name: str | None,
    organization_name: str | None,
    department_name: str | None,
    job_title: str | None,
    nickname: str | None,
    email_addresses: list[Any] | None,
    phone_numbers: list[Any] | None,
    url_addresses: list[Any] | None,
    note_text: str | None,
    postal_addresses: list[Any] | None,
    birthday: dict[str, Any] | None,
    dates: list[Any] | None,
    social_profiles: list[Any] | None,
    instant_message_addresses: list[Any] | None,
    contact_relations: list[Any] | None,
    image_path: str | None,
    clear_image: bool,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    if _unexpected_group_change_field(
        handle=handle,
        expected_current_sha256=expected_current_sha256,
        contact_type=contact_type,
        given_name=given_name,
        family_name=family_name,
        organization_name=organization_name,
        department_name=department_name,
        job_title=job_title,
        nickname=nickname,
        email_addresses=email_addresses,
        phone_numbers=phone_numbers,
        url_addresses=url_addresses,
        note_text=note_text,
        postal_addresses=postal_addresses,
        birthday=birthday,
        dates=dates,
        social_profiles=social_profiles,
        instant_message_addresses=instant_message_addresses,
        contact_relations=contact_relations,
        image_path=image_path,
        clear_image=clear_image,
    ):
        return _preview_error(
            [_warning("unexpected_group_field", "Contacts group changes accept only group/container fields.")]
        )

    normalized_group_name = ""
    if operation in {"create_group", "rename_group"}:
        normalized_group_name, name_warning = _bounded_preview_value(
            group_name or "",
            field="group_name",
            max_chars=MAX_CONTACT_GROUP_NAME_CHARS,
        )
        if name_warning is not None:
            return _preview_error([name_warning])
        if not normalized_group_name.strip():
            return _preview_error([_warning("missing_required_field", "Contacts group name is required.")])
    elif group_name is not None:
        return _preview_error([_warning("unexpected_group_name", "Contacts group delete does not accept group_name.")])

    target: dict[str, Any]
    proposed: dict[str, Any]
    if operation == "create_group":
        if group_handle.strip() or expected_group_sha256.strip():
            return _preview_error(
                [_warning("unexpected_group_handle", "Contacts group create does not accept group_handle.")]
            )
        create_target = _contact_create_target(
            container_handle=container_handle,
            expected_container_sha256=expected_container_sha256,
            contacts_runner=contacts_runner,
        )
        if create_target.get("status") == "error":
            return _preview_error(_safe_warnings(create_target))
        target = create_target["target"]
        proposed = {
            "effect": "create_contact_group",
            "group_name": normalized_group_name,
            "member_count_after": 0,
        }
    else:
        if container_handle.strip() or expected_container_sha256.strip():
            return _preview_error(
                [_warning("unexpected_container", "Contacts group rename/delete target an exact group only.")]
            )
        normalized_group_handle = group_handle.strip()
        if not is_opaque_handle(normalized_group_handle, CONTACT_GROUP_HANDLE_PREFIX):
            return _preview_error([_warning("invalid_group_handle", "Expected contacts:group:v1 opaque handle.")])
        normalized_group_sha, group_sha_warning = _normalize_sha256(expected_group_sha256)
        if group_sha_warning is not None:
            return _preview_error([group_sha_warning])
        group_id, group, group_error = _resolve_group_for_handle(
            normalized_group_handle,
            contacts_runner=contacts_runner,
        )
        if group_error is not None:
            return _preview_error(
                _safe_warnings(group_error) or [_warning("invalid_group_handle", "Contacts group was not found.")]
            )
        assert group_id is not None and group is not None
        if _contact_group_sha256(group) != normalized_group_sha:
            return _preview_error(
                [_warning("current_group_changed", "Contacts group state did not match the expected hash.")]
            )
        current_name = _bounded_string(group.get("name"), 500)
        member_count = _int_value(group.get("member_count"))
        target = {
            "group_handle": normalized_group_handle,
            "expected_group_sha256": normalized_group_sha,
            "current_group_name": current_name,
            "member_count": member_count,
        }
        if operation == "rename_group":
            if normalized_group_name == current_name:
                return _preview_error([_warning("already_applied", "Contacts group already has that name.")])
            proposed = {
                "effect": "rename_contact_group",
                "current_group_name": current_name,
                "group_name": normalized_group_name,
                "member_count": member_count,
            }
        else:
            proposed = {
                "effect": "delete_contact_group",
                "current_group_name": current_name,
                "member_count_before": member_count,
                "contacts_deleted": False,
            }

    fingerprint_payload = {
        "operation": operation,
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "destructive": operation == "delete_group",
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_contact_update(
    *,
    handle: str,
    expected_current_sha256: str,
    given_name: str | None,
    family_name: str | None,
    organization_name: str | None,
    department_name: str | None,
    job_title: str | None,
    nickname: str | None,
    email_addresses: list[Any] | None,
    phone_numbers: list[Any] | None,
    url_addresses: list[Any] | None,
    postal_addresses: list[Any] | None,
    birthday: dict[str, Any] | None,
    dates: list[Any] | None,
    social_profiles: list[Any] | None,
    instant_message_addresses: list[Any] | None,
    contact_relations: list[Any] | None,
    image_path: str | None,
    clear_image: bool,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, CONTACT_HANDLE_PREFIX):
        return _preview_error(
            [
                _warning(
                    "invalid_handle",
                    "Contacts update planning requires a contacts:contact:v1 handle.",
                )
            ]
        )
    normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
    if sha_warning is not None:
        return _preview_error([sha_warning])
    provided, field_warnings = _provided_update_fields(
        {
            "given_name": given_name,
            "family_name": family_name,
            "organization_name": organization_name,
            "department_name": department_name,
            "job_title": job_title,
            "nickname": nickname,
        }
    )
    if field_warnings:
        return _preview_error(field_warnings)

    normalized_methods: dict[str, list[dict[str, Any]] | None] = {}
    method_warnings: list[dict[str, str]] = []
    for field, values in {
        "email_addresses": email_addresses,
        "phone_numbers": phone_numbers,
        "url_addresses": url_addresses,
    }.items():
        if values is None:
            normalized_methods[field] = None
            continue
        normalized, warnings = _normalize_labeled_values(values, field=field)
        normalized_methods[field] = normalized
        method_warnings.extend(warnings)
    if method_warnings:
        return _preview_error(method_warnings)

    normalized_rich: dict[str, Any] = {}
    rich_warnings: list[dict[str, str]] = []
    for field, values, normalizer in (
        ("postal_addresses", postal_addresses, _normalize_postal_addresses),
        ("dates", dates, _normalize_dated_values),
        ("social_profiles", social_profiles, _normalize_social_profiles),
        ("instant_message_addresses", instant_message_addresses, _normalize_instant_messages),
        ("contact_relations", contact_relations, _normalize_contact_relations),
    ):
        if values is None:
            normalized_rich[field] = None
            continue
        normalized, warnings = normalizer(values, field=field)
        normalized_rich[field] = normalized
        rich_warnings.extend(warnings)
    if birthday is None:
        normalized_rich["birthday"] = None
    else:
        normalized_birthday, birthday_warning = _normalize_date_components(birthday, field="birthday")
        normalized_rich["birthday"] = normalized_birthday
        if birthday_warning is not None:
            rich_warnings.append(birthday_warning)
    if rich_warnings:
        return _preview_error(rich_warnings)

    image_replacement, image_warning = _normalize_image_replacement(
        image_path=image_path,
        clear_image=clear_image,
    )
    if image_warning is not None:
        return _preview_error([image_warning])

    if (
        not provided
        and all(value is None for value in normalized_methods.values())
        and all(value is None for value in normalized_rich.values())
        and image_replacement is None
    ):
        return _preview_error(
            [_warning("missing_update_field", "Contacts update requires at least one replacement field.")]
        )
    _contact_id, contact, error = _resolve_contact_update_state_for_handle(
        normalized_handle,
        contacts_runner=contacts_runner,
    )
    if error is not None:
        return _preview_error(_safe_warnings(error) or [_warning("invalid_handle", "Contact was not found.")])
    assert contact is not None
    current_sha = _contact_update_sha256(contact)
    if current_sha != normalized_expected_sha:
        return _preview_error(
            [_warning("current_contact_changed", "Contacts target state did not match the expected hash.")]
        )
    current_state = _contact_update_state(contact)
    proposed_state = {**current_state, **provided}
    for field, values in normalized_methods.items():
        if values is not None:
            proposed_state[field] = _canonical_state_value(values)
    for field, values in normalized_rich.items():
        if values is not None:
            proposed_state[field] = _canonical_state_value(values)
    if image_replacement is not None:
        if image_replacement["action"] == "clear":
            proposed_state["image_available"] = _canonical_state_value(False)
            proposed_state["image_sha256"] = ""
            proposed_state["image_bytes"] = _canonical_state_value(0)
        else:
            proposed_state["image_available"] = _canonical_state_value(True)
            proposed_state["image_sha256"] = str(image_replacement["image_sha256"])
            proposed_state["image_bytes"] = _canonical_state_value(_int_value(image_replacement["image_bytes"]))
    contact_type = proposed_state["contact_type"]
    if contact_type == "person" and not (proposed_state["given_name"] or proposed_state["family_name"]):
        return _preview_error(
            [_warning("missing_required_field", "Person contact update requires given_name or family_name.")]
        )
    if contact_type == "organization" and not proposed_state["organization_name"]:
        return _preview_error(
            [_warning("missing_required_field", "Organization contact update requires organization_name.")]
        )
    changed_fields = [
        field
        for field in ALL_UPDATE_FIELDS
        if proposed_state[field] != current_state[field]
    ]
    if not changed_fields:
        return _preview_error(
            [_warning("already_applied", "Contacts update fields already match the current contact.")]
        )
    proposed = {
        "contact_type": contact_type,
        "updated_fields": changed_fields,
        "updated_field_count": len(changed_fields),
        **{field: proposed_state[field] for field in UPDATE_SCALAR_FIELDS},
        "email_addresses": (
            normalized_methods["email_addresses"]
            if normalized_methods["email_addresses"] is not None
            else "preserved"
        ),
        "phone_numbers": (
            normalized_methods["phone_numbers"]
            if normalized_methods["phone_numbers"] is not None
            else "preserved"
        ),
        "url_addresses": (
            normalized_methods["url_addresses"]
            if normalized_methods["url_addresses"] is not None
            else "preserved"
        ),
        "email_count": (
            len(normalized_methods["email_addresses"])
            if normalized_methods["email_addresses"] is not None
            else "preserved"
        ),
        "phone_count": (
            len(normalized_methods["phone_numbers"])
            if normalized_methods["phone_numbers"] is not None
            else "preserved"
        ),
        "url_count": (
            len(normalized_methods["url_addresses"])
            if normalized_methods["url_addresses"] is not None
            else "preserved"
        ),
        "postal_addresses": (
            normalized_rich["postal_addresses"]
            if normalized_rich["postal_addresses"] is not None
            else "preserved"
        ),
        "postal_address_count": (
            len(normalized_rich["postal_addresses"])
            if isinstance(normalized_rich["postal_addresses"], list)
            else "preserved"
        ),
        "birthday": (
            normalized_rich["birthday"]
            if normalized_rich["birthday"] is not None
            else "preserved"
        ),
        "dates": normalized_rich["dates"] if normalized_rich["dates"] is not None else "preserved",
        "dates_count": (
            len(normalized_rich["dates"]) if isinstance(normalized_rich["dates"], list) else "preserved"
        ),
        "social_profiles": (
            normalized_rich["social_profiles"]
            if normalized_rich["social_profiles"] is not None
            else "preserved"
        ),
        "social_profile_count": (
            len(normalized_rich["social_profiles"])
            if isinstance(normalized_rich["social_profiles"], list)
            else "preserved"
        ),
        "instant_message_addresses": (
            normalized_rich["instant_message_addresses"]
            if normalized_rich["instant_message_addresses"] is not None
            else "preserved"
        ),
        "instant_message_count": (
            len(normalized_rich["instant_message_addresses"])
            if isinstance(normalized_rich["instant_message_addresses"], list)
            else "preserved"
        ),
        "contact_relations": (
            normalized_rich["contact_relations"]
            if normalized_rich["contact_relations"] is not None
            else "preserved"
        ),
        "relation_count": (
            len(normalized_rich["contact_relations"])
            if isinstance(normalized_rich["contact_relations"], list)
            else "preserved"
        ),
        "image": image_replacement if image_replacement is not None else "preserved",
        "note_status": "preserved",
    }
    fingerprint_payload = {
        "operation": "update",
        "target": {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "current_contact_type": contact_type,
        },
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "update",
            "target": {
                "handle": normalized_handle,
                "expected_current_sha256": normalized_expected_sha,
                "current_contact_type": contact_type,
            },
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_contact_delete(
    *,
    handle: str,
    expected_current_sha256: str,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, CONTACT_HANDLE_PREFIX):
        return _preview_error(
            [
                _warning(
                    "invalid_handle",
                    "Contacts delete planning requires a contacts:contact:v1 handle.",
                )
            ]
        )
    normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
    if sha_warning is not None:
        return _preview_error([sha_warning])
    _contact_id, contact, error = _resolve_contact_for_handle(
        normalized_handle,
        contacts_runner=contacts_runner,
    )
    if error is not None:
        return _preview_error(_safe_warnings(error) or [_warning("invalid_handle", "Contact was not found.")])
    assert contact is not None
    current_sha = _contact_delete_sha256(contact)
    if current_sha != normalized_expected_sha:
        return _preview_error(
            [_warning("current_contact_changed", "Contacts target state did not match the expected hash.")]
        )
    current_state = _contact_delete_state(contact)
    proposed = {
        "effect": "delete_exact_contact",
        "destructive": True,
        "contact_type": current_state["contact_type"],
        "email_addresses": "removed",
        "phone_numbers": "removed",
        "url_addresses": "removed",
        "note_status": "removed",
        "image_data": "removed",
    }
    fingerprint_payload = {
        "operation": "delete",
        "target": {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "current_contact_type": current_state["contact_type"],
        },
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "delete",
            "target": {
                "handle": normalized_handle,
                "expected_current_sha256": normalized_expected_sha,
                "current_contact_type": current_state["contact_type"],
            },
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "destructive": True,
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_contact_group_membership(
    *,
    operation: str,
    handle: str,
    expected_current_sha256: str,
    group_handle: str,
    expected_group_sha256: str,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    normalized_group_handle = group_handle.strip()
    if not is_opaque_handle(normalized_handle, CONTACT_HANDLE_PREFIX):
        return _preview_error(
            [_warning("invalid_handle", "Contacts group membership requires a contacts:contact:v1 handle.")]
        )
    if not is_opaque_handle(normalized_group_handle, CONTACT_GROUP_HANDLE_PREFIX):
        return _preview_error(
            [_warning("invalid_group_handle", "Contacts group membership requires a contacts:group:v1 handle.")]
        )
    normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
    if sha_warning is not None:
        return _preview_error([sha_warning])
    normalized_group_sha, group_sha_warning = _normalize_sha256(expected_group_sha256)
    if group_sha_warning is not None:
        return _preview_error([group_sha_warning])

    contact_id, contact, contact_error = _resolve_contact_update_state_for_handle(
        normalized_handle,
        contacts_runner=contacts_runner,
    )
    if contact_error is not None:
        return _preview_error(
            _safe_warnings(contact_error) or [_warning("invalid_handle", "Contact was not found.")]
        )
    group_id, group, group_error = _resolve_group_for_handle(
        normalized_group_handle,
        contacts_runner=contacts_runner,
    )
    if group_error is not None:
        return _preview_error(
            _safe_warnings(group_error) or [_warning("invalid_group_handle", "Contacts group was not found.")]
        )
    assert contact_id is not None and contact is not None and group_id is not None and group is not None
    if _contact_update_sha256(contact) != normalized_expected_sha:
        return _preview_error(
            [_warning("current_contact_changed", "Contacts target state did not match the expected hash.")]
        )
    if _contact_group_sha256(group) != normalized_group_sha:
        return _preview_error(
            [_warning("current_group_changed", "Contacts group state did not match the expected hash.")]
        )
    member_ids = {str(item) for item in group.get("member_ids", []) or []}
    is_member = contact_id in member_ids
    if operation == "add_group_member" and is_member:
        return _preview_error(
            [_warning("already_applied", "Contact is already a member of the selected group.")]
        )
    if operation == "remove_group_member" and not is_member:
        return _preview_error(
            [_warning("already_applied", "Contact is already absent from the selected group.")]
        )

    effect = "add_contact_to_group" if operation == "add_group_member" else "remove_contact_from_group"
    proposed = {
        "effect": effect,
        "group_name": _bounded_string(group.get("name"), 500),
        "member_count_before": _int_value(group.get("member_count")),
        "member_count_after": _int_value(group.get("member_count")) + (1 if operation == "add_group_member" else -1),
    }
    fingerprint_payload = {
        "operation": operation,
        "target": {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "group_handle": normalized_group_handle,
            "expected_group_sha256": normalized_group_sha,
        },
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
            "target": {
                "handle": normalized_handle,
                "expected_current_sha256": normalized_expected_sha,
                "group_handle": normalized_group_handle,
                "expected_group_sha256": normalized_group_sha,
            },
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _normalize_batch_items(batch_items: list[Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not isinstance(batch_items, list) or not batch_items:
        return [], [_warning("missing_required_field", "Contacts batch requires one or more exact item objects.")]
    if len(batch_items) > MAX_CONTACT_BATCH_ITEMS:
        return [], [_warning("batch_too_large", f"Contacts batch is capped at {MAX_CONTACT_BATCH_ITEMS} items.")]
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(batch_items):
        if not isinstance(item, dict):
            return [], [_warning("invalid_batch_item", f"Contacts batch item {index} must be an object.")]
        operation = str(item.get("operation") or "").strip().replace("-", "_")
        if operation in {"", "batch", "create", "create_group", "rename_group", "delete_group"}:
            return [], [_warning("invalid_batch_item", f"Contacts batch item {index} must be an exact existing-contact operation.")]
        if operation not in PLAN_OPERATIONS:
            return [], [_warning("invalid_batch_item", f"Contacts batch item {index} has an unsupported operation.")]
        normalized.append({**item, "operation": operation})
    return normalized, []


def _batch_item_kwargs(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": str(item.get("handle") or ""),
        "expected_current_sha256": str(item.get("expected_current_sha256") or ""),
        "group_handle": str(item.get("group_handle") or ""),
        "expected_group_sha256": str(item.get("expected_group_sha256") or ""),
        "contact_type": str(item.get("contact_type") or "person"),
        "given_name": item.get("given_name") if "given_name" in item else None,
        "family_name": item.get("family_name") if "family_name" in item else None,
        "organization_name": item.get("organization_name") if "organization_name" in item else None,
        "department_name": item.get("department_name") if "department_name" in item else None,
        "job_title": item.get("job_title") if "job_title" in item else None,
        "nickname": item.get("nickname") if "nickname" in item else None,
        "email_addresses": item.get("email_addresses") if "email_addresses" in item else None,
        "phone_numbers": item.get("phone_numbers") if "phone_numbers" in item else None,
        "url_addresses": item.get("url_addresses") if "url_addresses" in item else None,
        "note_text": item.get("note_text") if "note_text" in item else None,
        "postal_addresses": item.get("postal_addresses") if "postal_addresses" in item else None,
        "birthday": item.get("birthday") if "birthday" in item else None,
        "dates": item.get("dates") if "dates" in item else None,
        "social_profiles": item.get("social_profiles") if "social_profiles" in item else None,
        "instant_message_addresses": item.get("instant_message_addresses") if "instant_message_addresses" in item else None,
        "contact_relations": item.get("contact_relations") if "contact_relations" in item else None,
        "image_path": item.get("image_path") if "image_path" in item else None,
        "clear_image": bool(item.get("clear_image", False)),
    }


def _plan_contact_batch(
    *,
    batch_items: list[Any] | None,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_items, warnings = _normalize_batch_items(batch_items)
    if warnings:
        return _preview_error(warnings)

    child_previews: list[dict[str, Any]] = []
    fingerprint_items: list[dict[str, Any]] = []
    destructive = False
    content_inspected = False
    for index, item in enumerate(normalized_items):
        child_plan = plan_contact_change(
            str(item["operation"]),
            **_batch_item_kwargs(item),
            contacts_runner=contacts_runner,
        )
        if child_plan.get("status") != "ok":
            return _preview_error(
                [
                    _warning(
                        "batch_item_failed",
                        f"Contacts batch item {index} could not be planned.",
                    ),
                    *_safe_warnings(child_plan),
                ]
            )
        preview = child_plan.get("preview") if isinstance(child_plan.get("preview"), dict) else {}
        approval = preview.get("approval") if isinstance(preview.get("approval"), dict) else {}
        child_fingerprint = str(approval.get("approval_fingerprint") or "")
        destructive = destructive or bool(preview.get("destructive"))
        privacy = child_plan.get("privacy") if isinstance(child_plan.get("privacy"), dict) else {}
        content_inspected = content_inspected or bool(privacy.get("content_inspected"))
        child_previews.append(
            {
                "index": index,
                "operation": preview.get("operation"),
                "target": preview.get("target"),
                "proposed": preview.get("proposed"),
                "destructive": bool(preview.get("destructive")),
            }
        )
        fingerprint_items.append(
            {
                "index": index,
                "operation": preview.get("operation"),
                "idempotency_key": preview.get("idempotency_key"),
                "approval_fingerprint": child_fingerprint,
            }
        )

    fingerprint_payload = {
        "operation": "batch",
        "item_count": len(child_previews),
        "items": fingerprint_items,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(content_inspected=content_inspected),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "batch",
            "item_count": len(child_previews),
            "items": child_previews,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "destructive": destructive,
            "read_back_required_after_apply": True,
        },
        "result_count": len(child_previews),
        "warnings": [],
    }


def _apply_contact_batch(
    *,
    plan: dict[str, Any],
    batch_items: list[Any] | None,
    approval_fingerprint: str,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_items, warnings = _normalize_batch_items(batch_items)
    if warnings:
        return _apply_error(warnings, plan=plan)

    child_plans: list[dict[str, Any]] = []
    for index, item in enumerate(normalized_items):
        child_plan = plan_contact_change(
            str(item["operation"]),
            **_batch_item_kwargs(item),
            contacts_runner=contacts_runner,
        )
        if child_plan.get("status") != "ok":
            return _apply_error(
                [
                    _warning("batch_item_failed", f"Contacts batch item {index} no longer plans cleanly."),
                    *_safe_warnings(child_plan),
                ],
                plan=plan,
            )
        child_plans.append(child_plan)

    results: list[dict[str, Any]] = []
    applied_count = 0
    for index, (item, child_plan) in enumerate(zip(normalized_items, child_plans, strict=True)):
        preview = child_plan.get("preview") if isinstance(child_plan.get("preview"), dict) else {}
        approval = preview.get("approval") if isinstance(preview.get("approval"), dict) else {}
        child_token = _approval_token(str(approval.get("approval_fingerprint") or ""))
        child_result = apply_contact_change(
            str(item["operation"]),
            **_batch_item_kwargs(item),
            approval_token=child_token,
            confirm_apply=True,
            contacts_runner=contacts_runner,
        )
        item_result = {
            "index": index,
            "operation": str(item["operation"]),
            "status": child_result.get("status"),
            "mutation_applied": bool(child_result.get("mutation_applied")),
            "read_back": child_result.get("read_back"),
            "warnings": _safe_warnings(child_result),
        }
        results.append(item_result)
        if bool(child_result.get("mutation_applied")):
            applied_count += 1
        if child_result.get("status") != "ok":
            return {
                "schema_version": 1,
                "status": "partial" if applied_count else "error",
                "source": "contacts",
                "privacy": _mutation_privacy(content_inspected=True),
                "mode": "apply",
                "operation": "batch",
                "mutation_applied": applied_count > 0,
                "apply_available": True,
                "idempotency_key": plan["preview"]["idempotency_key"],
                "approval": {
                    "approval_fingerprint": approval_fingerprint,
                    "approval_token_verified": True,
                },
                "read_back": {
                    "item_count": len(normalized_items),
                    "applied_count": applied_count,
                    "items": results,
                },
                "result_count": applied_count,
                "warnings": [
                    _warning("batch_item_failed", f"Contacts batch stopped at item {index}."),
                    *_safe_warnings(child_result),
                ],
            }

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _mutation_privacy(content_inspected=True),
        "mode": "apply",
        "operation": "batch",
        "mutation_applied": applied_count > 0,
        "apply_available": True,
        "idempotency_key": plan["preview"]["idempotency_key"],
        "approval": {
            "approval_fingerprint": approval_fingerprint,
            "approval_token_verified": True,
        },
        "read_back": {
            "item_count": len(normalized_items),
            "applied_count": applied_count,
            "items": results,
        },
        "result_count": applied_count,
        "warnings": [],
    }


def _plan_contact_note_append(
    *,
    handle: str,
    expected_current_sha256: str,
    note_text: str | None,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, CONTACT_HANDLE_PREFIX):
        return _preview_error(
            [
                _warning(
                    "invalid_handle",
                    "Contacts note append planning requires a contacts:contact:v1 handle.",
                )
            ]
        )
    normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
    if sha_warning is not None:
        return _preview_error([sha_warning])
    if note_text is None:
        return _preview_error(
            [_warning("missing_required_field", "Contacts note append requires note_text.")]
        )
    normalized_note, note_warning = _bounded_note_text(
        note_text,
        field="note_text",
        max_chars=MAX_CONTACT_NOTE_APPEND_CHARS,
    )
    if note_warning is not None:
        return _preview_error([note_warning])
    if not normalized_note:
        return _preview_error(
            [_warning("missing_required_field", "Contacts note append requires non-empty note_text.")]
        )

    _contact_id, contact, error = _resolve_contact_note_state_for_handle(
        normalized_handle,
        contacts_runner=contacts_runner,
    )
    if error is not None:
        return _preview_error(
            _safe_warnings(error) or [_warning("contacts_note_unavailable", "Contact note state was unavailable.")]
        )
    assert contact is not None
    current_note = _contact_note_text(contact)
    current_sha = _contact_note_sha256(current_note)
    if current_sha != normalized_expected_sha:
        return _preview_error(
            [_warning("current_contact_changed", "Contacts note state did not match the expected hash.")]
        )

    proposed_note = current_note + normalized_note
    if proposed_note == current_note:
        return _preview_error(
            [_warning("already_applied", "Contacts note append text already matches the current note state.")]
        )
    append_preview, append_preview_truncated = _bounded_note_preview(normalized_note)
    proposed = {
        "effect": "append_contact_note",
        "append_chars": len(normalized_note),
        "append_preview_text": append_preview,
        "append_preview_chars": len(append_preview),
        "append_preview_truncated": append_preview_truncated,
        "resulting_note_chars": len(proposed_note),
        "resulting_note_sha256": _contact_note_sha256(proposed_note),
        "overwrite": "blocked",
        "delete": "blocked",
    }
    fingerprint_payload = {
        "operation": "append_note",
        "target": {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "current_note_chars": len(current_note),
        },
        "proposed": {
            **proposed,
            "append_note_sha256": _contact_note_sha256(normalized_note),
            "append_text": normalized_note,
        },
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "append_note",
            "target": {
                "handle": normalized_handle,
                "expected_current_sha256": normalized_expected_sha,
                "current_note_chars": len(current_note),
            },
            "proposed": {
                **proposed,
                "append_text": normalized_note,
            },
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_contact_note_set(
    *,
    operation: str,
    handle: str,
    expected_current_sha256: str,
    note_text: str | None,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    normalized_handle = handle.strip()
    if not is_opaque_handle(normalized_handle, CONTACT_HANDLE_PREFIX):
        return _preview_error(
            [
                _warning(
                    "invalid_handle",
                    "Contacts note planning requires a contacts:contact:v1 handle.",
                )
            ]
        )
    normalized_expected_sha, sha_warning = _normalize_sha256(expected_current_sha256)
    if sha_warning is not None:
        return _preview_error([sha_warning])

    _contact_id, contact, error = _resolve_contact_note_state_for_handle(
        normalized_handle,
        contacts_runner=contacts_runner,
    )
    if error is not None:
        return _preview_error(
            _safe_warnings(error) or [_warning("contacts_note_unavailable", "Contact note state was unavailable.")]
        )
    assert contact is not None
    current_note = _contact_note_text(contact)
    current_sha = _contact_note_sha256(current_note)
    if current_sha != normalized_expected_sha:
        return _preview_error(
            [_warning("current_contact_changed", "Contacts note state did not match the expected hash.")]
        )

    if operation in {"clear_note", "delete_note"}:
        normalized_note = ""
        effect = "clear_contact_note"
        supplied_note_hash = ""
    elif operation == "merge_note":
        if note_text is None:
            return _preview_error([_warning("missing_required_field", "Contacts note merge requires note_text.")])
        merge_text, note_warning = _bounded_note_text(
            note_text,
            field="note_text",
            max_chars=MAX_CONTACT_NOTE_APPEND_CHARS,
        )
        if note_warning is not None:
            return _preview_error([note_warning])
        if not merge_text:
            return _preview_error(
                [_warning("missing_required_field", "Contacts note merge requires non-empty note_text.")]
            )
        if merge_text in current_note:
            return _preview_error(
                [_warning("already_applied", "Contacts note already contains the merge text.")]
            )
        separator = "\n\n" if current_note and not current_note.endswith("\n") else ""
        normalized_note = f"{current_note}{separator}{merge_text}"
        effect = "merge_contact_note"
        supplied_note_hash = _contact_note_sha256(merge_text)
    else:
        if note_text is None:
            return _preview_error([_warning("missing_required_field", "Contacts note set requires note_text.")])
        normalized_note, note_warning = _bounded_note_text(
            note_text,
            field="note_text",
            max_chars=MAX_CONTACT_NOTE_SET_CHARS,
        )
        if note_warning is not None:
            return _preview_error([note_warning])
        effect = "set_contact_note"
        supplied_note_hash = _contact_note_sha256(normalized_note)

    if normalized_note == current_note:
        return _preview_error(
            [_warning("already_applied", "Contacts note already matches the requested state.")]
        )

    supplied_preview = ""
    supplied_preview_truncated = False
    if operation not in {"clear_note", "delete_note"} and note_text is not None:
        supplied_preview, supplied_preview_truncated = _bounded_note_preview(note_text)
    proposed = {
        "effect": effect,
        "operation_alias": operation,
        "supplied_note_chars": len(note_text or ""),
        "supplied_note_sha256": supplied_note_hash,
        "supplied_note_preview_text": supplied_preview,
        "supplied_note_preview_chars": len(supplied_preview),
        "supplied_note_preview_truncated": supplied_preview_truncated,
        "resulting_note_chars": len(normalized_note),
        "resulting_note_sha256": _contact_note_sha256(normalized_note),
        "existing_note_returned": False,
        "resulting_note_returned": operation not in {"merge_note"},
        "destructive": operation in {"set_note", "replace_note", "overwrite_note", "clear_note", "delete_note"},
    }
    fingerprint_payload = {
        "operation": "set_note",
        "operation_alias": operation,
        "target": {
            "handle": normalized_handle,
            "expected_current_sha256": normalized_expected_sha,
            "current_note_chars": len(current_note),
        },
        "proposed": {
            **proposed,
            "resulting_note_sha256": _contact_note_sha256(normalized_note),
            "set_note_text": normalized_note,
        },
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    public_proposed = dict(proposed)
    if operation != "merge_note":
        public_proposed["set_note_text"] = normalized_note
    else:
        public_proposed["merge_text"] = note_text or ""
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _preview_privacy(content_inspected=True),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "set_note",
            "operation_alias": operation,
            "target": {
                "handle": normalized_handle,
                "expected_current_sha256": normalized_expected_sha,
                "current_note_chars": len(current_note),
            },
            "proposed": public_proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "destructive": bool(proposed["destructive"]),
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected contacts:contact:v1 opaque handle from search output.",
            )
        ],
    }


def _preview_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "contacts",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": None,
        "result_count": 0,
        "warnings": warnings,
    }


def _apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any] | None,
    status: str = "error",
    mutation_applied: bool = False,
    authorization_status: Any = None,
) -> dict[str, Any]:
    preview = plan.get("preview") if isinstance(plan, dict) else None
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "contacts",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": preview if isinstance(preview, dict) else None,
        "read_back": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _contacts_degraded_result(response: dict[str, Any], *, content: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=False) if content else _privacy(),
        "authorization_status": response.get("authorization_status"),
        "results": [] if not content else None,
        "result": None if content else None,
        "result_count": 0 if not content else None,
        "warnings": _safe_warnings(response),
    }


def _contacts_group_members_unavailable(
    group: dict[str, Any],
    limit: int,
    *,
    authorization_status: Any = None,
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": authorization_status,
        "query": {
            "scope": "selected_group_members",
            "limit": max(1, min(limit, 50)),
            "truncated": False,
        },
        "group": _contact_group_metadata(group),
        "results": [],
        "result_count": 0,
        "content_returned": False,
        "raw_identifier_returned": False,
        "contact_details_returned": False,
        "warnings": warnings
        or [_warning("contacts_unavailable", "Contacts group members are unavailable.")],
    }


def _contacts_container_members_unavailable(
    container: dict[str, Any],
    limit: int,
    *,
    authorization_status: Any = None,
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "contacts",
        "privacy": _privacy(),
        "authorization_status": authorization_status,
        "query": {
            "scope": "selected_container_members",
            "limit": max(1, min(limit, 50)),
            "truncated": False,
        },
        "container": _contact_container_metadata(container),
        "results": [],
        "result_count": 0,
        "content_returned": False,
        "raw_identifier_returned": False,
        "contact_details_returned": False,
        "warnings": warnings
        or [_warning("contacts_unavailable", "Contacts container members are unavailable.")],
    }


def _contacts_count_unavailable_result(
    warnings: list[dict[str, str]],
    *,
    authorization_status: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "degraded",
        "source": "contacts",
        "privacy": _privacy(),
        "result": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _contacts_archive_error(
    warnings: list[dict[str, str]],
    *,
    authorization_status: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "source": "contacts",
        "privacy": _export_privacy(contact_data_exported=False),
        "result": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _content_unavailable_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "content_unavailable",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=False),
        "result": None,
        "warnings": [
            _warning(
                "contacts_read_error",
                "Contact details could not be read safely.",
            )
        ],
    }


def _safe_warnings(response: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        response,
        _warning,
        fallback_message="Contacts warning detail was redacted.",
    )


def _bounded_max_scan(value: int) -> int:
    return max(1, min(value, DEFAULT_MAX_SCAN_CONTACTS))


def _bounded_max_export(value: int) -> int:
    return max(1, min(value, MAX_EXPORT_CONTACTS))


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _bounded_string(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text[: max(1, min(max_chars, MAX_CONTENT_CHARS))]


def _state_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _bounded_payload(value: Any, max_chars: int) -> Any:
    string_limit = max(1, min(max_chars, MAX_CONTENT_CHARS))
    if isinstance(value, str):
        return _bounded_string(value, string_limit)
    if isinstance(value, list):
        return [_bounded_payload(item, string_limit) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key)[:100]: _bounded_payload(item, string_limit)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, bool | int | float) or value is None:
        return value
    return _bounded_string(value, string_limit)


def _bounded_note_preview(value: str) -> tuple[str, bool]:
    preview = _bounded_string(value, MAX_PREVIEW_FIELD_CHARS)
    return preview, len(preview) < len(value)


def _safe_archive_prefix(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())[:80].strip(".-_")
    return normalized or "contacts"


def _unique_archive_stem(target_dir: Path, prefix: str) -> str:
    candidate = prefix
    index = 2
    while any(
        (target_dir / f"{candidate}{suffix}").exists()
        for suffix in (".json", ".vcf", "-manifest.json")
    ):
        candidate = f"{prefix}-{index}"
        index += 1
    return candidate


def _bounded_preview_value(
    value: str,
    *,
    field: str,
    max_chars: int,
) -> tuple[str, dict[str, str] | None]:
    normalized = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) > max_chars:
        return "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    return normalized, None


def _bounded_note_text(
    value: str,
    *,
    field: str,
    max_chars: int,
) -> tuple[str, dict[str, str] | None]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) > max_chars:
        return "", _warning("input_too_large", f"Field exceeds maximum length: {field}.")
    return normalized, None


def _normalize_labeled_values(
    values: list[Any] | None,
    *,
    field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if values is None:
        return [], []
    if not isinstance(values, list):
        return [], [_warning("invalid_labeled_values", f"{field} must be a list.")]
    if len(values) > MAX_CONTACT_METHODS:
        return [], [_warning("too_many_values", f"{field} is capped at {MAX_CONTACT_METHODS} entries.")]

    normalized: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for index, item in enumerate(values):
        label = "other"
        value = ""
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            label = str(item.get("label") or "other")
            value = str(item.get("value") or "")
        else:
            warnings.append(_warning("invalid_labeled_value", f"{field}[{index}] must be an object."))
            continue

        normalized_label, label_warning = _normalize_freeform_label(label, field=f"{field}[{index}].label")
        if label_warning is not None:
            warnings.append(label_warning)
            continue
        normalized_value = value.strip().replace("\r\n", "\n").replace("\r", "\n")
        if not normalized_value:
            warnings.append(_warning("missing_required_field", f"{field}[{index}].value is required."))
            continue
        if len(normalized_value) > MAX_PREVIEW_FIELD_CHARS:
            warnings.append(_warning("input_too_large", f"{field}[{index}].value exceeds maximum length."))
            continue
        normalized.append({"label": normalized_label, "value": normalized_value})
    return normalized, warnings


def _normalize_freeform_label(value: Any, *, field: str) -> tuple[str, dict[str, str] | None]:
    """Preserve a caller-supplied custom label verbatim (exact case, spaces, and
    punctuation) up to MAX_LABEL_CHARS. Empty labels default to "other". Control
    characters (including newlines/tab) are rejected rather than silently stripped,
    and labels beyond the finite bound are rejected rather than truncated."""

    text = "" if value is None else str(value)
    stripped = text.strip()
    if not stripped:
        return "other", None
    # Reject before length check on control chars so a huge control-only string is
    # reported as invalid rather than merely oversized; either way it is refused.
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in stripped):
        return "", _warning("invalid_label", f"{field} may not contain control characters or newlines.")
    if len(stripped) > MAX_LABEL_CHARS:
        return "", _warning("label_too_large", f"{field} exceeds the {MAX_LABEL_CHARS}-character label bound.")
    return stripped, None


def _normalize_postal_addresses(
    values: list[Any] | None,
    *,
    field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if values is None:
        return [], []
    if not isinstance(values, list):
        return [], [_warning("invalid_postal_addresses", f"{field} must be a list.")]
    if len(values) > MAX_CONTACT_RICH_VALUES:
        return [], [_warning("too_many_values", f"{field} is capped at {MAX_CONTACT_RICH_VALUES} entries.")]
    normalized: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    keys = ("street", "city", "state", "postal_code", "country", "iso_country_code")
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            warnings.append(_warning("invalid_postal_address", f"{field}[{index}] must be an object."))
            continue
        label, label_warning = _normalize_freeform_label(item.get("label"), field=f"{field}[{index}].label")
        if label_warning is not None:
            warnings.append(label_warning)
            continue
        entry = {"label": label}
        has_value = False
        for key in keys:
            text = _state_string(item.get(key)).strip()
            if len(text) > MAX_PREVIEW_FIELD_CHARS:
                warnings.append(_warning("input_too_large", f"{field}[{index}].{key} exceeds maximum length."))
                continue
            entry[key] = text
            has_value = has_value or bool(text)
        if not has_value:
            warnings.append(_warning("missing_required_field", f"{field}[{index}] requires address text."))
            continue
        normalized.append(entry)
    return normalized, warnings


def _normalize_date_components(
    value: dict[str, Any] | None,
    *,
    field: str,
) -> tuple[dict[str, int], dict[str, str] | None]:
    if value is None:
        return {}, None
    if not isinstance(value, dict):
        return {}, _warning("invalid_date", f"{field} must be an object.")
    if not value:
        return {}, None
    payload: dict[str, int] = {}
    for key in ("year", "month", "day"):
        raw = value.get(key)
        if raw is None or raw == "":
            continue
        if isinstance(raw, bool) or not isinstance(raw, int):
            return {}, _warning("invalid_date", f"{field}.{key} must be an integer.")
        payload[key] = raw
    month = payload.get("month")
    day = payload.get("day")
    year = payload.get("year")
    if month is None or day is None:
        return {}, _warning("missing_required_field", f"{field} requires month and day.")
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return {}, _warning("invalid_date", f"{field} month/day is outside the accepted range.")
    if year is not None and not (1 <= year <= 9999):
        return {}, _warning("invalid_date", f"{field}.year is outside the accepted range.")
    return payload, None


def _normalize_dated_values(
    values: list[Any] | None,
    *,
    field: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if values is None:
        return [], []
    if not isinstance(values, list):
        return [], [_warning("invalid_dates", f"{field} must be a list.")]
    if len(values) > MAX_CONTACT_RICH_VALUES:
        return [], [_warning("too_many_values", f"{field} is capped at {MAX_CONTACT_RICH_VALUES} entries.")]
    normalized: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            warnings.append(_warning("invalid_date_entry", f"{field}[{index}] must be an object."))
            continue
        date_payload, warning = _normalize_date_components(item.get("date"), field=f"{field}[{index}].date")
        if warning is not None:
            warnings.append(warning)
            continue
        label, label_warning = _normalize_freeform_label(item.get("label"), field=f"{field}[{index}].label")
        if label_warning is not None:
            warnings.append(label_warning)
            continue
        normalized.append({"label": label, "date": date_payload})
    return normalized, warnings


def _normalize_social_profiles(
    values: list[Any] | None,
    *,
    field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return _normalize_labeled_text_maps(
        values,
        field=field,
        keys=("service", "username", "url"),
        required_any=("username", "url"),
    )


def _normalize_instant_messages(
    values: list[Any] | None,
    *,
    field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return _normalize_labeled_text_maps(
        values,
        field=field,
        keys=("service", "username"),
        required_any=("username",),
    )


def _normalize_contact_relations(
    values: list[Any] | None,
    *,
    field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return _normalize_labeled_text_maps(
        values,
        field=field,
        keys=("name",),
        required_any=("name",),
    )


def _normalize_labeled_text_maps(
    values: list[Any] | None,
    *,
    field: str,
    keys: tuple[str, ...],
    required_any: tuple[str, ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if values is None:
        return [], []
    if not isinstance(values, list):
        return [], [_warning("invalid_labeled_values", f"{field} must be a list.")]
    if len(values) > MAX_CONTACT_RICH_VALUES:
        return [], [_warning("too_many_values", f"{field} is capped at {MAX_CONTACT_RICH_VALUES} entries.")]
    normalized: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            warnings.append(_warning("invalid_labeled_value", f"{field}[{index}] must be an object."))
            continue
        label, label_warning = _normalize_freeform_label(item.get("label"), field=f"{field}[{index}].label")
        if label_warning is not None:
            warnings.append(label_warning)
            continue
        entry = {"label": label}
        for key in keys:
            text = _state_string(item.get(key)).strip()
            if len(text) > MAX_PREVIEW_FIELD_CHARS:
                warnings.append(_warning("input_too_large", f"{field}[{index}].{key} exceeds maximum length."))
                text = ""
            entry[key] = text
        if not any(entry.get(key) for key in required_any):
            warnings.append(_warning("missing_required_field", f"{field}[{index}] is missing required text."))
            continue
        normalized.append(entry)
    return normalized, warnings


def _normalize_image_replacement(
    *,
    image_path: str | None,
    clear_image: bool,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    path_text = _state_string(image_path).strip()
    if clear_image and path_text:
        return None, _warning("conflicting_image_fields", "Use image_path or clear_image, not both.")
    if clear_image:
        return {"action": "clear", "image_available": False, "image_bytes": 0, "image_sha256": ""}, None
    if not path_text:
        return None, None
    try:
        path = Path(path_text).expanduser()
        if not path.is_file():
            return None, _warning("invalid_image_path", "Contact image source must be an existing file.")
        data = path.read_bytes()
    except OSError:
        return None, _warning("invalid_image_path", "Contact image source could not be read.")
    if not data:
        return None, _warning("invalid_image_file", "Contact image source was empty.")
    if len(data) > MAX_CONTACT_IMAGE_BYTES:
        return None, _warning("image_too_large", "Contact image source exceeds the maximum size.")
    if not _looks_like_image(data):
        return None, _warning("unsupported_image_file", "Contact image source must look like PNG, JPEG, GIF, TIFF, or HEIC.")
    return {
        "action": "set",
        "image_available": True,
        "image_bytes": len(data),
        "image_sha256": hashlib.sha256(data).hexdigest(),
    }, None


def _image_payload_for_apply(image_path: str | None, expected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str] | None]:
    path_text = _state_string(image_path).strip()
    if not path_text:
        return {}, _warning("missing_required_field", "Contact image apply requires the same image_path used for planning.")
    try:
        data = Path(path_text).expanduser().read_bytes()
    except OSError:
        return {}, _warning("invalid_image_path", "Contact image source could not be read.")
    expected_sha = str(expected.get("image_sha256") or "")
    expected_bytes = _int_value(expected.get("image_bytes"))
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha or len(data) != expected_bytes:
        return {}, _warning("current_image_source_changed", "Contact image source no longer matches the approved plan.")
    return {"image_data_base64": base64.b64encode(data).decode("ascii")}, None


def _looks_like_image(data: bytes) -> bool:
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"GIF87a")
        or data.startswith(b"GIF89a")
        or data.startswith(b"II*\x00")
        or data.startswith(b"MM\x00*")
        or data[4:12] in {b"ftypheic", b"ftypheix", b"ftyphevc", b"ftyphevx", b"ftypmif1"}
    )


def _apply_helper_payload(
    preview: dict[str, Any],
    *,
    handle: str,
    image_path: str | None,
    contacts_runner: ContactsRunner | None,
) -> dict[str, Any]:
    operation = str(preview.get("operation") or "")
    payload: dict[str, Any] = {
        "command": "contacts_apply_change",
        "operation": operation,
    }
    proposed = preview["proposed"]
    if operation == "create":
        target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
        container_handle = str(target.get("container_handle") or "")
        if container_handle:
            container_id, container, error = _resolve_container_for_handle(
                container_handle,
                contacts_runner=contacts_runner,
            )
            if error is not None:
                return {
                    "status": "error",
                    "warnings": _safe_warnings(error)
                    or [_warning("invalid_container_handle", "Container was not found.")],
                }
            assert container_id is not None and container is not None
            if _contact_container_sha256(container) != str(target.get("expected_container_sha256") or ""):
                return {
                    "status": "error",
                    "warnings": [
                        _warning("current_container_changed", "Contacts container state changed before apply.")
                    ],
                }
            payload["container_id"] = container_id
            payload["expected_container"] = _contact_container_state(container)
        payload.update(
            {
                "contact_type": proposed["contact_type"],
                "given_name": proposed["given_name"],
                "family_name": proposed["family_name"],
                "organization_name": proposed["organization_name"],
                "department_name": proposed["department_name"],
                "job_title": proposed["job_title"],
                "nickname": proposed["nickname"],
            }
        )
        payload["email_addresses"] = proposed["email_addresses"]
        payload["phone_numbers"] = proposed["phone_numbers"]
        payload["url_addresses"] = proposed["url_addresses"]
        return payload
    if operation == "create_group":
        target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
        container_handle = str(target.get("container_handle") or "")
        if container_handle:
            container_id, container, error = _resolve_container_for_handle(
                container_handle,
                contacts_runner=contacts_runner,
            )
            if error is not None:
                return {
                    "status": "error",
                    "warnings": _safe_warnings(error)
                    or [_warning("invalid_container_handle", "Container was not found.")],
                }
            assert container_id is not None and container is not None
            if _contact_container_sha256(container) != str(target.get("expected_container_sha256") or ""):
                return {
                    "status": "error",
                    "warnings": [
                        _warning("current_container_changed", "Contacts container state changed before apply.")
                    ],
                }
            payload["container_id"] = container_id
            payload["expected_container"] = _contact_container_state(container)
        payload["group_name"] = str(proposed.get("group_name") or "")
        return payload
    if operation in {"rename_group", "delete_group"}:
        target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
        group_handle = str(target.get("group_handle") or "")
        expected_group_sha = str(target.get("expected_group_sha256") or "")
        group_id, group, error = _resolve_group_for_handle(group_handle, contacts_runner=contacts_runner)
        if error is not None:
            return {
                "status": "error",
                "warnings": _safe_warnings(error) or [_warning("invalid_group_handle", "Group was not found.")],
            }
        assert group_id is not None and group is not None
        if _contact_group_sha256(group) != expected_group_sha:
            return {
                "status": "error",
                "warnings": [_warning("current_group_changed", "Contacts group state changed before apply.")],
            }
        payload["group_id"] = group_id
        payload["expected_group"] = _contact_group_state(group)
        if operation == "rename_group":
            payload["group_name"] = str(proposed.get("group_name") or "")
        return payload
    if operation not in {"update", "delete", "append_note", "set_note", "add_group_member", "remove_group_member"}:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "invalid_operation",
                    "Contacts apply requires create, update, delete, note, group membership, or group CRUD operation.",
                )
            ],
        }
    target = preview.get("target")
    if not isinstance(target, dict):
        return {
            "status": "error",
            "warnings": [_warning("invalid_plan", "Contacts apply requires a valid target.")],
        }
    if operation == "delete":
        contact_id, contact, error = _resolve_contact_for_handle(
            handle,
            contacts_runner=contacts_runner,
        )
    elif operation in {"add_group_member", "remove_group_member"}:
        contact_id, contact, error = _resolve_contact_update_state_for_handle(
            handle,
            contacts_runner=contacts_runner,
        )
    elif operation in {"append_note", "set_note"}:
        contact_id, contact, error = _resolve_contact_note_state_for_handle(
            handle,
            contacts_runner=contacts_runner,
        )
    else:
        contact_id, contact, error = _resolve_contact_update_state_for_handle(
            handle,
            contacts_runner=contacts_runner,
        )
    if error is not None:
        return {
            "status": "error",
            "warnings": _safe_warnings(error) or [_warning("invalid_handle", "Contact was not found.")],
        }
    assert contact_id is not None and contact is not None
    expected_sha = str(target.get("expected_current_sha256") or "")
    if operation == "delete":
        current_sha = _contact_delete_sha256(contact)
    elif operation in {"append_note", "set_note"}:
        current_sha = _contact_note_sha256(_contact_note_text(contact))
    else:
        current_sha = _contact_update_sha256(contact)
    if current_sha != expected_sha:
        return {
            "status": "error",
            "warnings": [
                _warning(
                    "current_contact_changed",
                    "Contacts target state did not match the approved plan.",
                )
            ],
        }
    payload["contact_id"] = contact_id
    if operation in {"add_group_member", "remove_group_member"}:
        group_handle = str(target.get("group_handle") or "")
        expected_group_sha = str(target.get("expected_group_sha256") or "")
        group_id, group, group_error = _resolve_group_for_handle(
            group_handle,
            contacts_runner=contacts_runner,
        )
        if group_error is not None:
            return {
                "status": "error",
                "warnings": _safe_warnings(group_error) or [_warning("invalid_group_handle", "Group was not found.")],
            }
        assert group_id is not None and group is not None
        if _contact_group_sha256(group) != expected_group_sha:
            return {
                "status": "error",
                "warnings": [_warning("current_group_changed", "Contacts group state changed before apply.")],
            }
        payload["group_id"] = group_id
        payload["expected_current"] = _contact_update_state(contact)
        payload["expected_group"] = _contact_group_state(group)
        return payload
    payload["expected_current"] = (
        _contact_delete_state(contact)
        if operation == "delete"
        else _contact_update_state(contact)
    )
    if operation == "delete":
        return payload
    if operation == "append_note":
        append_text = str(proposed.get("append_text") or "")
        payload["expected_current_note_text"] = _contact_note_text(contact)
        payload["note_text"] = append_text
        payload.pop("expected_current", None)
        return payload
    if operation == "set_note":
        current_note = _contact_note_text(contact)
        if str(preview.get("operation_alias") or "") == "merge_note":
            merge_text = str(proposed.get("merge_text") or "")
            separator = "\n\n" if current_note and not current_note.endswith("\n") else ""
            note_text = current_note if merge_text in current_note else f"{current_note}{separator}{merge_text}"
        else:
            note_text = str(proposed.get("set_note_text") or "")
        payload["expected_current_note_text"] = current_note
        payload["note_text"] = note_text
        payload.pop("expected_current", None)
        return payload
    payload.update(
        {
            "contact_type": proposed["contact_type"],
            "given_name": proposed["given_name"],
            "family_name": proposed["family_name"],
            "organization_name": proposed["organization_name"],
            "department_name": proposed["department_name"],
            "job_title": proposed["job_title"],
            "nickname": proposed["nickname"],
        }
    )
    for field, flag in {
        "email_addresses": "replace_email_addresses",
        "phone_numbers": "replace_phone_numbers",
        "url_addresses": "replace_url_addresses",
        "postal_addresses": "replace_postal_addresses",
        "dates": "replace_dates",
        "social_profiles": "replace_social_profiles",
        "instant_message_addresses": "replace_instant_message_addresses",
        "contact_relations": "replace_contact_relations",
    }.items():
        value = proposed.get(field)
        if isinstance(value, list):
            payload[flag] = True
            payload[field] = value
        else:
            payload[flag] = False
    birthday = proposed.get("birthday")
    payload["replace_birthday"] = isinstance(birthday, dict)
    if isinstance(birthday, dict):
        payload["birthday"] = birthday
    image = proposed.get("image")
    payload["image_action"] = "preserve"
    if isinstance(image, dict) and image.get("action") == "clear":
        payload["image_action"] = "clear"
    elif isinstance(image, dict) and image.get("action") == "set":
        image_payload, image_warning = _image_payload_for_apply(image_path, image)
        if image_warning is not None:
            return {"status": "error", "warnings": [image_warning]}
        payload["image_action"] = "set"
        payload.update(image_payload)
    return payload


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"contacts-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

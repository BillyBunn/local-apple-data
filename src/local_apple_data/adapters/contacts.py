from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTACTS_HELPER = PROJECT_ROOT / "scripts/contacts_helper.swift"
CONTACTS_TIMEOUT_SECONDS = 10.0
DEFAULT_LIMIT = 20
DEFAULT_MAX_SCAN_CONTACTS = 10000
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
CONTACT_HANDLE_PREFIX = "contacts:contact"
ContactsRunner = Callable[[dict[str, Any], float], dict[str, Any]]


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
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "privacy": _content_privacy(content_inspected=True),
        "result": result,
        "result_count": 1,
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
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


def _run_contacts_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        ["swift", str(CONTACTS_HELPER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("Contacts helper failed.")
    parsed = json.loads(completed.stdout)
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


def _contact_detail(contact: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    result = _contact_metadata(contact)
    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    result.update(
        {
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
    warnings = response.get("warnings")
    if not isinstance(warnings, list):
        return []
    safe: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and isinstance(message, str):
            safe.append(_warning(code, message))
    return safe


def _bounded_max_scan(value: int) -> int:
    return max(1, min(value, DEFAULT_MAX_SCAN_CONTACTS))


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

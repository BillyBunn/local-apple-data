from __future__ import annotations

import hashlib
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
MAX_PREVIEW_FIELD_CHARS = 512
MAX_CONTACT_METHODS = 5
MAX_LABEL_CHARS = 64
PLAN_OPERATIONS = {"create"}
CONTACT_TYPES = {"person", "organization"}
APPROVAL_TOKEN_PREFIX = "contacts-apply:v1:"
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


def _preview_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
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


def plan_contact_change(
    operation: str,
    *,
    contact_type: str = "person",
    given_name: str = "",
    family_name: str = "",
    organization_name: str = "",
    department_name: str = "",
    job_title: str = "",
    nickname: str = "",
    email_addresses: list[Any] | None = None,
    phone_numbers: list[Any] | None = None,
    url_addresses: list[Any] | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation create."))
        return _preview_error(warnings)

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
        normalized, warning = _bounded_preview_value(value, field=field, max_chars=MAX_PREVIEW_FIELD_CHARS)
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
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": {"container": "default_contacts_container"},
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
            "target": {"container": "default_contacts_container"},
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
    contact_type: str = "person",
    given_name: str = "",
    family_name: str = "",
    organization_name: str = "",
    department_name: str = "",
    job_title: str = "",
    nickname: str = "",
    email_addresses: list[Any] | None = None,
    phone_numbers: list[Any] | None = None,
    url_addresses: list[Any] | None = None,
    approval_token: str = "",
    confirm_apply: bool = False,
    contacts_runner: ContactsRunner | None = None,
) -> dict[str, Any]:
    plan = plan_contact_change(
        operation,
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

    runner = contacts_runner or _run_contacts_helper
    try:
        applied = runner(_apply_helper_payload(preview), CONTACTS_TIMEOUT_SECONDS)
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
            or [_warning("contacts_apply_failed", "Contact could not be created safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            authorization_status=applied.get("authorization_status"),
        )

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

        normalized_label = label.strip().lower().replace(" ", "_")[:MAX_LABEL_CHARS] or "other"
        normalized_value = value.strip().replace("\r\n", "\n").replace("\r", "\n")
        if not normalized_value:
            warnings.append(_warning("missing_required_field", f"{field}[{index}].value is required."))
            continue
        if len(normalized_value) > MAX_PREVIEW_FIELD_CHARS:
            warnings.append(_warning("input_too_large", f"{field}[{index}].value exceeds maximum length."))
            continue
        normalized.append({"label": normalized_label, "value": normalized_value})
    return normalized, warnings


def _apply_helper_payload(preview: dict[str, Any]) -> dict[str, Any]:
    proposed = preview["proposed"]
    return {
        "command": "contacts_apply_change",
        "operation": preview["operation"],
        "contact_type": proposed["contact_type"],
        "given_name": proposed["given_name"],
        "family_name": proposed["family_name"],
        "organization_name": proposed["organization_name"],
        "department_name": proposed["department_name"],
        "job_title": proposed["job_title"],
        "nickname": proposed["nickname"],
        "email_addresses": proposed["email_addresses"],
        "phone_numbers": proposed["phone_numbers"],
        "url_addresses": proposed["url_addresses"],
    }


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"contacts-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

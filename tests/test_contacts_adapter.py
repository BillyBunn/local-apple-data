from __future__ import annotations

from local_apple_data.adapters.contacts import (
    apply_contact_change,
    get_contact,
    plan_contact_change,
    search_contacts,
)


def _contacts_runner(payload: dict, _timeout: float) -> dict:
    if payload["command"] == "contacts":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contacts": [
                {
                    "contact_id": "runtime-contact-1",
                    "display_name": "Synthetic Contact",
                    "contact_type": "person",
                    "given_name": "Synthetic",
                    "family_name": "Contact",
                    "nickname": "Fixture",
                    "organization_name": "Example Org",
                    "department_name": "Research",
                    "job_title": "Tester",
                    "email_count": 1,
                    "phone_count": 1,
                    "postal_address_count": 1,
                    "url_count": 1,
                    "social_profile_count": 1,
                    "instant_message_count": 1,
                    "relation_count": 1,
                    "dates_count": 1,
                    "birthday_present": True,
                    "image_available": False,
                    "note_status": "requires_entitlement",
                    "email_addresses": [{"label": "home", "value": "hidden@example.invalid"}],
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "contact_by_id":
        assert payload["contact_id"] == "runtime-contact-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "contact": {
                "contact_id": "runtime-contact-1",
                "display_name": "Synthetic Contact",
                "contact_type": "person",
                "given_name": "Synthetic",
                "family_name": "Contact",
                "nickname": "Fixture",
                "organization_name": "Example Org",
                "department_name": "Research",
                "job_title": "Tester",
                "email_count": 1,
                "phone_count": 1,
                "postal_address_count": 1,
                "url_count": 1,
                "social_profile_count": 1,
                "instant_message_count": 1,
                "relation_count": 1,
                "dates_count": 1,
                "birthday_present": True,
                "image_available": False,
                "note_status": "requires_entitlement",
                "name_prefix": "",
                "middle_name": "",
                "previous_family_name": "",
                "name_suffix": "",
                "email_addresses": [{"label": "home", "value": "synthetic@example.invalid"}],
                "phone_numbers": [{"label": "mobile", "value": "+1 555 0100"}],
                "postal_addresses": [
                    {
                        "label": "work",
                        "street": "1 Synthetic Way",
                        "city": "Example",
                        "state": "CA",
                        "postal_code": "94000",
                        "country": "United States",
                        "iso_country_code": "US",
                    }
                ],
                "url_addresses": [{"label": "work", "value": "https://example.invalid"}],
                "birthday": {"month": 6, "day": 4},
                "dates": [{"label": "anniversary", "date": {"year": 2026, "month": 6, "day": 4}}],
                "social_profiles": [
                    {"label": "work", "service": "Synthetic", "username": "fixture", "url": ""}
                ],
                "instant_message_addresses": [
                    {"label": "work", "service": "SyntheticIM", "username": "fixture"}
                ],
                "contact_relations": [{"label": "assistant", "name": "Synthetic Helper"}],
            },
            "warnings": [],
        }
    if payload["command"] == "contacts_apply_change":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contact": {
                "contact_id": "created-contact-1",
                "display_name": "Synthetic Created",
                "contact_type": payload["contact_type"],
                "given_name": payload["given_name"],
                "family_name": payload["family_name"],
                "nickname": payload["nickname"],
                "organization_name": payload["organization_name"],
                "department_name": payload["department_name"],
                "job_title": payload["job_title"],
                "email_count": len(payload["email_addresses"]),
                "phone_count": len(payload["phone_numbers"]),
                "postal_address_count": 0,
                "url_count": len(payload["url_addresses"]),
                "social_profile_count": 0,
                "instant_message_count": 0,
                "relation_count": 0,
                "dates_count": 0,
                "birthday_present": False,
                "image_available": False,
                "note_status": "requires_entitlement",
                "name_prefix": "",
                "middle_name": "",
                "previous_family_name": "",
                "name_suffix": "",
                "email_addresses": payload["email_addresses"],
                "phone_numbers": payload["phone_numbers"],
                "postal_addresses": [],
                "url_addresses": payload["url_addresses"],
                "birthday": {},
                "dates": [],
                "social_profiles": [],
                "instant_message_addresses": [],
                "contact_relations": [],
            },
            "warnings": [],
        }
    raise AssertionError(f"unexpected Contacts command: {payload['command']}")


def test_search_contacts_returns_metadata_only() -> None:
    result = search_contacts("Synthetic", contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "name_or_organization"
    assert result["result_count"] == 1
    contact = result["results"][0]
    assert contact["handle"].startswith("contacts:contact:v1:")
    assert contact["display_name"] == "Synthetic Contact"
    assert contact["email_count"] == 1
    assert contact["note_status"] == "requires_entitlement"
    assert "runtime-contact-1" not in str(result)
    assert "hidden@example.invalid" not in str(result)


def test_search_contacts_rejects_broad_query_without_runner() -> None:
    called = False

    def runner(_payload: dict, _timeout: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = search_contacts("%", contacts_runner=runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"
    assert called is False


def test_get_contact_returns_exact_details() -> None:
    search = search_contacts("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = get_contact(handle, contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["email_addresses"][0]["value"] == "synthetic@example.invalid"
    assert result["result"]["phone_numbers"][0]["value"] == "+1 555 0100"
    assert result["result"]["note_status"] == "requires_entitlement"
    assert "runtime-contact-1" not in str(result)


def test_get_contact_rejects_invalid_handle() -> None:
    result = get_contact("contacts:contact:runtime-contact-1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_contacts_degrades_without_access() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": "denied",
            "contacts": [],
            "warnings": [
                {
                    "code": "contacts_access_unavailable",
                    "message": "Contacts access is not authorized for this process.",
                }
            ],
        }

    result = search_contacts("Synthetic", contacts_runner=runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "contacts_access_unavailable"


def _contact_plan() -> dict:
    return plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Created",
        organization_name="Example Org",
        job_title="Tester",
        email_addresses=[{"label": "work", "value": "synthetic@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0101"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/contact"}],
    )


def _contacts_token(plan: dict) -> str:
    return "contacts-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


def test_plan_contact_change_create_returns_preview_only() -> None:
    result = _contact_plan()

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    assert result["preview"]["idempotency_key"].startswith("contacts-plan:v1:")
    assert result["preview"]["approval"]["approval_token_format"].startswith(
        "contacts-apply:v1:"
    )
    assert result["preview"]["proposed"]["given_name"] == "Synthetic"
    assert result["preview"]["proposed"]["email_count"] == 1
    assert result["preview"]["proposed"]["note_status"] == "blocked"


def test_plan_contact_change_requires_identity() -> None:
    result = plan_contact_change("create", contact_type="person")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"


def test_plan_contact_change_rejects_too_many_emails() -> None:
    result = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        email_addresses=[{"label": "work", "value": f"{index}@example.invalid"} for index in range(6)],
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "too_many_values"


def test_apply_contact_change_requires_confirmation() -> None:
    plan = _contact_plan()

    result = apply_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Created",
        organization_name="Example Org",
        job_title="Tester",
        email_addresses=[{"label": "work", "value": "synthetic@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0101"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/contact"}],
        approval_token=_contacts_token(plan),
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_contact_change_rejects_wrong_approval_token() -> None:
    result = apply_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Created",
        approval_token="contacts-apply:v1:bad",
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_contact_change_creates_contact_and_reads_back() -> None:
    plan = _contact_plan()

    result = apply_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Created",
        organization_name="Example Org",
        job_title="Tester",
        email_addresses=[{"label": "work", "value": "synthetic@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0101"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/contact"}],
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "mutation"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["handle"].startswith("contacts:contact:v1:")
    assert result["read_back"]["given_name"] == "Synthetic"
    assert result["read_back"]["email_addresses"][0]["value"] == "synthetic@example.invalid"


def test_apply_contact_change_surfaces_contacts_warning() -> None:
    def denied_runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": "denied",
            "contact": None,
            "warnings": [
                {
                    "code": "contacts_access_unavailable",
                    "message": "Contacts access is not authorized for this process.",
                }
            ],
        }

    plan = _contact_plan()
    result = apply_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Created",
        organization_name="Example Org",
        job_title="Tester",
        email_addresses=[{"label": "work", "value": "synthetic@example.invalid"}],
        phone_numbers=[{"label": "mobile", "value": "+1 555 0101"}],
        url_addresses=[{"label": "work", "value": "https://example.invalid/contact"}],
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=denied_runner,
    )

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "contacts_access_unavailable"

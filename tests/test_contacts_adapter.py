from __future__ import annotations

import json
import plistlib
import subprocess
from pathlib import Path

from local_apple_data.adapters import contacts as contacts_adapter
from local_apple_data.adapters.contacts import (
    CONTACTS_HELPER,
    apply_contact_change,
    count_contacts,
    export_contacts_archive,
    get_contact,
    get_contact_container,
    get_contact_group,
    list_contact_container_members,
    list_contact_group_members,
    plan_contact_change,
    request_contacts_access,
    search_contact_containers,
    search_contact_groups,
    search_contacts,
)


def test_request_contacts_access_is_explicit_and_metadata_only() -> None:
    seen: dict[str, object] = {}

    def runner(payload: dict, timeout: float) -> dict:
        seen["payload"] = payload
        seen["timeout"] = timeout
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "request_result": "granted",
            "warnings": [],
        }

    result = request_contacts_access(contacts_runner=runner)

    assert seen["payload"] == {"command": "request_contacts_access"}
    assert float(seen["timeout"]) >= 180
    assert result["status"] == "ok"
    assert result["authorization_status"] == "authorized"
    assert result["request_result"] == "granted"
    assert result["privacy"]["content_inspected"] is False
    assert result["warnings"] == []


def test_request_contacts_access_returns_safe_timeout() -> None:
    def runner(_payload: dict, timeout: float) -> dict:
        raise subprocess.TimeoutExpired(["open"], timeout)

    result = request_contacts_access(contacts_runner=runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "timeout"
    assert result["warnings"][0]["code"] == "contacts_access_request_timeout"


def test_request_contacts_access_returns_safe_error() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        raise ValueError("raw sensitive-helper-detail failure")

    result = request_contacts_access(contacts_runner=runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "unavailable"
    assert result["warnings"][0]["code"] == "contacts_unavailable"
    assert "sensitive-helper-detail" not in str(result)


def test_request_contacts_access_rejects_unexpected_helper_contract() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "status": "raw/private/status",
            "authorization_status": "raw/private/auth",
            "request_result": "raw/private/result",
            "warnings": [],
        }

    result = request_contacts_access(contacts_runner=runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "unknown"
    assert result["request_result"] == "unavailable"
    assert "raw/private" not in str(result)


def test_request_contacts_access_does_not_prepare_with_mocked_runner(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        contacts_adapter,
        "_prepare_contacts_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("prepare fired")),
    )

    result = request_contacts_access(
        contacts_runner=lambda _payload, _timeout: {
            "status": "ok",
            "authorization_status": "authorized",
            "request_result": "already_authorized",
            "warnings": [],
        }
    )

    assert result["status"] == "ok"


def test_request_contacts_access_fails_closed_without_stable_signature(
    monkeypatch,
) -> None:
    app_root = Path("/synthetic/ContactsHelper.app")
    monkeypatch.setattr(
        contacts_adapter,
        "_prepare_contacts_helper_signing",
        lambda: None,
    )
    monkeypatch.setattr(
        contacts_adapter,
        "_ensure_contacts_helper_app",
        lambda: app_root,
    )
    monkeypatch.setattr(
        contacts_adapter._signing,
        "signing_identity",
        lambda: "Local Apple Data Signing",
    )
    monkeypatch.setattr(
        contacts_adapter._signing,
        "app_signing_authority",
        lambda _app: "",
    )
    monkeypatch.setattr(
        contacts_adapter,
        "_run_contacts_helper",
        lambda _payload, _timeout: (_ for _ in ()).throw(
            AssertionError("unstable helper was launched")
        ),
    )

    result = request_contacts_access()

    assert result["status"] == "degraded"
    assert result["request_result"] == "unavailable"
    assert result["warnings"][0]["code"] == "contacts_stable_signing_unavailable"


def test_request_contacts_access_fails_closed_on_prepare_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        contacts_adapter,
        "_prepare_contacts_helper_signing",
        lambda: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(["security"], 15)
        ),
    )

    result = request_contacts_access()

    assert result["status"] == "degraded"
    assert result["request_result"] == "unavailable"
    assert result["warnings"][0]["code"] == "contacts_unavailable"


def test_request_contacts_access_fails_closed_on_authority_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(contacts_adapter, "_prepare_contacts_helper_signing", lambda: None)
    monkeypatch.setattr(
        contacts_adapter,
        "_ensure_contacts_helper_app",
        lambda: Path("/synthetic/ContactsHelper.app"),
    )
    monkeypatch.setattr(
        contacts_adapter._signing,
        "signing_identity",
        lambda: "Local Apple Data Signing",
    )
    monkeypatch.setattr(
        contacts_adapter._signing,
        "app_signing_authority",
        lambda _app: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(["codesign"], 15)
        ),
    )

    result = request_contacts_access()

    assert result["status"] == "degraded"
    assert result["request_result"] == "unavailable"
    assert result["warnings"][0]["code"] == "contacts_unavailable"


def test_prepare_contacts_helper_signing_provisions_and_invalidates(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        contacts_adapter._signing,
        "provision_local_signing_identity",
        lambda: "Local Apple Data Signing",
    )

    def invalidate(app_root, identity):
        calls["app_root"] = app_root
        calls["identity"] = identity
        return True

    monkeypatch.setattr(
        contacts_adapter._signing,
        "invalidate_app_if_signing_mismatch",
        invalidate,
    )

    contacts_adapter._prepare_contacts_helper_signing()

    assert calls["identity"] == "Local Apple Data Signing"
    assert calls["app_root"] == contacts_adapter._contacts_helper_app_root()


def test_contacts_read_path_never_prepares_signing(monkeypatch) -> None:
    monkeypatch.setattr(
        contacts_adapter,
        "_prepare_contacts_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("read path prepared signing")),
    )

    result = search_contacts("fixture", contacts_runner=_contacts_runner)

    assert result["status"] in {"ok", "degraded", "error"}


def test_contacts_helper_declares_stable_identity_and_usage_string() -> None:
    plist = contacts_adapter._contacts_helper_info_plist()

    assert plist["CFBundleIdentifier"] == "com.local-apple-data.contacts-helper"
    assert plist["CFBundleExecutable"] == "contacts_helper"
    assert "NSContactsUsageDescription" in plist
    assert contacts_adapter._contacts_helper_entitlements() == {
        "com.apple.security.personal-information.addressbook": True
    }


def test_contacts_helper_app_validation_checks_plist_digest_and_signature(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app_root = tmp_path / "ContactsHelper.app"
    contents = app_root / "Contents"
    resources = contents / "Resources"
    executable = contents / "MacOS" / "contacts_helper"
    resources.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    executable.write_text("binary")
    (resources / "source.sha256").write_text("digest")
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(contacts_adapter._contacts_helper_info_plist(), handle)
    with (resources / "entitlements.plist").open("wb") as handle:
        plistlib.dump(contacts_adapter._contacts_helper_entitlements(), handle)

    monkeypatch.setattr(
        contacts_adapter.shutil,
        "which",
        lambda _name: "/usr/bin/codesign",
    )
    def fake_run(args, **_kwargs):
        if "--entitlements" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                plistlib.dumps(
                    {
                        "com.apple.security.personal-information.addressbook": True,
                    }
                ).decode("utf-8"),
                "",
            )
        if "-dvv" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                "",
                "Identifier=com.local-apple-data.contacts-helper\n",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(contacts_adapter.subprocess, "run", fake_run)

    assert contacts_adapter._contacts_helper_app_valid(app_root, "digest") is True
    (resources / "source.sha256").write_text("changed")
    assert contacts_adapter._contacts_helper_app_valid(app_root, "digest") is False


def test_contacts_helper_app_validation_rejects_wrong_signed_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app_root = tmp_path / "ContactsHelper.app"
    contents = app_root / "Contents"
    resources = contents / "Resources"
    executable = contents / "MacOS" / "contacts_helper"
    resources.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    executable.write_text("binary")
    (resources / "source.sha256").write_text("digest")
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(contacts_adapter._contacts_helper_info_plist(), handle)
    with (resources / "entitlements.plist").open("wb") as handle:
        plistlib.dump(contacts_adapter._contacts_helper_entitlements(), handle)

    monkeypatch.setattr(
        contacts_adapter.shutil,
        "which",
        lambda _name: "/usr/bin/codesign",
    )

    def fake_run(args, **_kwargs):
        if "--entitlements" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                plistlib.dumps(
                    {
                        "com.apple.security.personal-information.addressbook": False,
                        "com.apple.developer.contacts.notes": True,
                    }
                ).decode("utf-8"),
                "",
            )
        if "-dvv" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                "",
                "Identifier=com.local-apple-data.contacts-helper.suffix\n",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(contacts_adapter.subprocess, "run", fake_run)

    assert contacts_adapter._contacts_helper_app_valid(app_root, "digest") is False


def test_contacts_helper_app_validation_fails_closed_on_codesign_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app_root = tmp_path / "ContactsHelper.app"
    contents = app_root / "Contents"
    resources = contents / "Resources"
    executable = contents / "MacOS" / "contacts_helper"
    resources.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    executable.write_text("binary")
    (resources / "source.sha256").write_text("digest")
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(contacts_adapter._contacts_helper_info_plist(), handle)
    with (resources / "entitlements.plist").open("wb") as handle:
        plistlib.dump(contacts_adapter._contacts_helper_entitlements(), handle)

    monkeypatch.setattr(
        contacts_adapter.shutil,
        "which",
        lambda _name: "/usr/bin/codesign",
    )
    monkeypatch.setattr(
        contacts_adapter.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(["codesign"], 15)
        ),
    )

    assert contacts_adapter._contacts_helper_app_valid(app_root, "digest") is False


def test_contacts_helper_has_cli_only_request_access_command() -> None:
    source = Path("scripts/contacts_helper.swift").read_text(encoding="utf-8")
    mcp_source = Path("src/local_apple_data/mcp_server.py").read_text(encoding="utf-8")

    assert 'commandLineOptionValue("--input-json-file")' in source
    assert 'commandLineOptionValue("--output-json-file")' in source
    assert 'if command == "request_contacts_access"' in source
    assert "store.requestAccess(for: .contacts)" in source
    assert '"contacts_access_request_timeout"' in source
    assert 'status.rawValue == 4' in source
    assert 'authorizationName(finalStatus) == "limited"' in source
    assert '"contacts_full_access_required"' in source
    assert "request_contacts_access" not in mcp_source


def test_contacts_helper_archive_retries_without_note_entitlement() -> None:
    source = Path("scripts/contacts_helper.swift").read_text(encoding="utf-8")

    assert "archiveKeysWithNotes" in source
    assert "archiveKeysWithoutNotes" in source
    assert "let archiveKeysWithoutNotes: [CNKeyDescriptor] = detailKeys" in source
    assert "if !notesExported" in source
    assert '"notes_exported": notesExported' in source
    assert '"contacts_notes_unavailable"' in source
    assert '"contacts_vcard_export_failed"' in source
    assert '"contacts_note_unavailable"' in source


def _contacts_runner(payload: dict, _timeout: float) -> dict:
    if payload["command"] == "contacts_count":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contact_count": 1,
            "scan_truncated": False,
            "warnings": [],
        }
    if payload["command"] == "contacts_archive":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contact_count": 1,
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
                    "postal_address_count": 0,
                    "url_count": 1,
                    "social_profile_count": 0,
                    "instant_message_count": 0,
                    "relation_count": 0,
                    "dates_count": 0,
                    "birthday_present": False,
                    "image_available": False,
                    "note_status": "available",
                    "note_text": "Existing note.",
                    "name_prefix": "",
                    "middle_name": "",
                    "previous_family_name": "",
                    "name_suffix": "",
                    "email_addresses": [{"label": "home", "value": "synthetic@example.invalid"}],
                    "phone_numbers": [{"label": "mobile", "value": "+1 555 0100"}],
                    "postal_addresses": [],
                    "url_addresses": [{"label": "work", "value": "https://example.invalid"}],
                    "birthday": {},
                    "dates": [],
                    "social_profiles": [],
                    "instant_message_addresses": [],
                    "contact_relations": [],
                }
            ],
            "vcard_text": "BEGIN:VCARD\nVERSION:3.0\nFN:Synthetic Contact\nEND:VCARD\n",
            "notes_exported": True,
            "scan_truncated": False,
            "warnings": [],
        }
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
    if payload["command"] == "contact_groups":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "groups": [
                {
                    "group_id": "runtime-group-1",
                    "name": "Synthetic Group",
                    "member_count": 1,
                    "member_ids": ["runtime-member-1"],
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "contact_containers":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "containers": [
                {
                    "container_id": "runtime-container-1",
                    "name": "iCloud",
                    "type": "carddav",
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "contact_container_by_id":
        assert payload["container_id"] == "runtime-container-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "container": {
                "container_id": "runtime-container-1",
                "name": "iCloud",
                "type": "carddav",
            },
            "warnings": [],
        }
    if payload["command"] == "contact_container_members":
        assert payload["container_id"] == "runtime-container-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "container": {
                "container_id": "runtime-container-1",
                "name": "iCloud",
                "type": "carddav",
            },
            "contacts": [
                {
                    "contact_id": "runtime-container-member-1",
                    "display_name": "Synthetic Container Member",
                    "contact_type": "person",
                    "given_name": "Synthetic",
                    "family_name": "Container",
                    "nickname": "",
                    "organization_name": "Example Org",
                    "department_name": "",
                    "job_title": "",
                    "email_count": 1,
                    "phone_count": 0,
                    "postal_address_count": 0,
                    "url_count": 0,
                    "social_profile_count": 0,
                    "instant_message_count": 0,
                    "relation_count": 0,
                    "dates_count": 0,
                    "birthday_present": False,
                    "image_available": False,
                    "note_status": "requires_entitlement",
                    "email_addresses": [{"label": "home", "value": "hidden-container@example.invalid"}],
                }
            ],
            "truncated": False,
            "warnings": [],
        }
    if payload["command"] == "contact_group_by_id":
        assert payload["group_id"] == "runtime-group-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "group": {
                "group_id": "runtime-group-1",
                "name": "Synthetic Group",
                "member_count": 1,
                "member_ids": ["runtime-member-1"],
            },
            "warnings": [],
        }
    if payload["command"] == "contact_group_members":
        assert payload["group_id"] == "runtime-group-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "group": {
                "group_id": "runtime-group-1",
                "name": "Synthetic Group",
                "member_count": 1,
                "member_ids": ["runtime-member-1"],
            },
            "contacts": [
                {
                    "contact_id": "runtime-member-1",
                    "display_name": "Synthetic Member",
                    "contact_type": "person",
                    "given_name": "Synthetic",
                    "family_name": "Member",
                    "nickname": "",
                    "organization_name": "Example Org",
                    "department_name": "",
                    "job_title": "",
                    "email_count": 1,
                    "phone_count": 0,
                    "postal_address_count": 0,
                    "url_count": 0,
                    "social_profile_count": 0,
                    "instant_message_count": 0,
                    "relation_count": 0,
                    "dates_count": 0,
                    "birthday_present": False,
                    "image_available": False,
                    "note_status": "requires_entitlement",
                    "email_addresses": [{"label": "home", "value": "hidden@example.invalid"}],
                }
            ],
            "truncated": False,
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
    if payload["command"] == "contact_note_state_by_id":
        assert payload["contact_id"] == "runtime-contact-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "contact": {
                "contact_id": "runtime-contact-1",
                "note_status": "available",
                "note_text": "Existing note.",
                "note_chars": 14,
            },
            "warnings": [],
        }
    if payload["command"] == "contact_update_state_by_id":
        assert payload["contact_id"] == "runtime-contact-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "contact": {
                "contact_id": "runtime-contact-1",
                "contact_type": "person",
                "given_name": "Synthetic",
                "family_name": "Contact",
                "nickname": "Fixture",
                "organization_name": "Example Org",
                "department_name": "Research",
                "job_title": "Tester",
                "email_addresses": '[{"label":"home","value":"synthetic@example.invalid"}]',
                "phone_numbers": '[{"label":"mobile","value":"+1 555 0100"}]',
                "url_addresses": '[{"label":"work","value":"https://example.invalid"}]',
                "postal_addresses": (
                    '[{"city":"Example","country":"United States","iso_country_code":"US",'
                    '"label":"work","postal_code":"94000","state":"CA","street":"1 Synthetic Way"}]'
                ),
                "birthday": '{"day":4,"month":6}',
                "dates": '[{"date":{"day":4,"month":6,"year":2026},"label":"anniversary"}]',
                "social_profiles": (
                    '[{"label":"work","service":"Synthetic","url":"","username":"fixture"}]'
                ),
                "instant_message_addresses": (
                    '[{"label":"work","service":"SyntheticIM","username":"fixture"}]'
                ),
                "contact_relations": '[{"label":"assistant","name":"Synthetic Helper"}]',
                "image_available": "false",
                "image_sha256": "",
                "image_bytes": "0",
            },
            "warnings": [],
        }
    if payload["command"] == "contacts_apply_change":
        if payload["operation"] == "delete":
            assert payload["contact_id"] == "runtime-contact-1"
            assert payload["expected_current"]["given_name"] == "Synthetic"
            assert payload["expected_current"]["email_count"] == "1"
            assert "synthetic@example.invalid" in payload["expected_current"]["email_addresses"]
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "contact": None,
                "deleted": True,
                "verified_absent": True,
                "warnings": [],
            }
        if payload["operation"] == "update":
            assert payload["contact_id"] == "runtime-contact-1"
            assert payload["expected_current"]["given_name"] == "Synthetic"
            assert "synthetic@example.invalid" in payload["expected_current"]["email_addresses"]
            email_addresses = (
                payload["email_addresses"]
                if payload.get("replace_email_addresses")
                else [{"label": "home", "value": "synthetic@example.invalid"}]
            )
            phone_numbers = (
                payload["phone_numbers"]
                if payload.get("replace_phone_numbers")
                else [{"label": "mobile", "value": "+1 555 0100"}]
            )
            url_addresses = (
                payload["url_addresses"]
                if payload.get("replace_url_addresses")
                else [{"label": "work", "value": "https://example.invalid"}]
            )
            postal_addresses = (
                payload["postal_addresses"]
                if payload.get("replace_postal_addresses")
                else [
                    {
                        "label": "work",
                        "street": "1 Synthetic Way",
                        "city": "Example",
                        "state": "CA",
                        "postal_code": "94000",
                        "country": "United States",
                        "iso_country_code": "US",
                    }
                ]
            )
            birthday = payload["birthday"] if payload.get("replace_birthday") else {"month": 6, "day": 4}
            dates = (
                payload["dates"]
                if payload.get("replace_dates")
                else [{"label": "anniversary", "date": {"year": 2026, "month": 6, "day": 4}}]
            )
            social_profiles = (
                payload["social_profiles"]
                if payload.get("replace_social_profiles")
                else [{"label": "work", "service": "Synthetic", "username": "fixture", "url": ""}]
            )
            instant_messages = (
                payload["instant_message_addresses"]
                if payload.get("replace_instant_message_addresses")
                else [{"label": "work", "service": "SyntheticIM", "username": "fixture"}]
            )
            relations = (
                payload["contact_relations"]
                if payload.get("replace_contact_relations")
                else [{"label": "assistant", "name": "Synthetic Helper"}]
            )
            if payload.get("image_action") == "set":
                assert payload["image_data_base64"]
                image_available = True
                image_bytes = 67
                image_sha256 = "image-sha"
            elif payload.get("image_action") == "clear":
                image_available = False
                image_bytes = 0
                image_sha256 = ""
            else:
                image_available = False
                image_bytes = 0
                image_sha256 = ""
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "contact": {
                    "contact_id": "runtime-contact-1",
                    "display_name": "Renamed Contact",
                    "contact_type": "person",
                    "given_name": payload["given_name"],
                    "family_name": payload["family_name"],
                    "nickname": payload["nickname"],
                    "organization_name": payload["organization_name"],
                    "department_name": payload["department_name"],
                    "job_title": payload["job_title"],
                    "email_count": len(email_addresses),
                    "phone_count": len(phone_numbers),
                    "postal_address_count": len(postal_addresses),
                    "url_count": len(url_addresses),
                    "social_profile_count": len(social_profiles),
                    "instant_message_count": len(instant_messages),
                    "relation_count": len(relations),
                    "dates_count": len(dates),
                    "birthday_present": bool(birthday),
                    "image_available": image_available,
                    "note_status": "requires_entitlement",
                    "name_prefix": "",
                    "middle_name": "",
                    "previous_family_name": "",
                    "name_suffix": "",
                    "email_addresses": email_addresses,
                    "phone_numbers": phone_numbers,
                    "postal_addresses": postal_addresses,
                    "url_addresses": url_addresses,
                    "birthday": birthday,
                    "dates": dates,
                    "social_profiles": social_profiles,
                    "instant_message_addresses": instant_messages,
                    "contact_relations": relations,
                    "image_bytes": image_bytes,
                    "image_sha256": image_sha256,
                },
                "warnings": [],
            }
        if payload["operation"] == "append_note":
            assert payload["contact_id"] == "runtime-contact-1"
            assert payload["expected_current_note_text"] == "Existing note."
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "contact": {
                    "contact_id": "runtime-contact-1",
                    "note_status": "available",
                    "note_text": "Existing note." + payload["note_text"],
                    "note_chars": len("Existing note." + payload["note_text"]),
                },
                "warnings": [],
            }
        if payload["operation"] == "set_note":
            assert payload["contact_id"] == "runtime-contact-1"
            assert payload["expected_current_note_text"] == "Existing note."
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "contact": {
                    "contact_id": "runtime-contact-1",
                    "note_status": "available",
                    "note_text": payload["note_text"],
                    "note_chars": len(payload["note_text"]),
                },
                "warnings": [],
            }
        if payload["operation"] == "add_group_member":
            assert payload["contact_id"] == "runtime-contact-1"
            assert payload["group_id"] == "runtime-group-1"
            assert payload["expected_group"]["member_count"] == "1"
            assert payload["expected_group"]["member_ids"] == '["runtime-member-1"]'
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "group": {
                    "group_id": "runtime-group-1",
                    "name": "Synthetic Group",
                    "member_count": 2,
                    "member_ids": ["runtime-contact-1", "runtime-member-1"],
                },
                "membership_changed": True,
                "membership_verified": True,
                "warnings": [],
            }
        if payload["operation"] == "create_group":
            assert payload["group_name"] == "Friends"
            assert payload["container_id"] == "runtime-container-1"
            assert payload["expected_container"]["name"] == "iCloud"
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "group": {
                    "group_id": "runtime-group-2",
                    "name": "Friends",
                    "member_count": 0,
                    "member_ids": [],
                },
                "warnings": [],
            }
        if payload["operation"] == "rename_group":
            assert payload["group_id"] == "runtime-group-1"
            assert payload["group_name"] == "Renamed Group"
            assert payload["expected_group"]["name"] == "Synthetic Group"
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "group": {
                    "group_id": "runtime-group-1",
                    "name": "Renamed Group",
                    "member_count": 0,
                    "member_ids": [],
                },
                "warnings": [],
            }
        if payload["operation"] == "delete_group":
            assert payload["group_id"] == "runtime-group-1"
            assert payload["expected_group"]["name"] == "Synthetic Group"
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "group": None,
                "deleted": True,
                "verified_absent": True,
                "warnings": [],
            }
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
    assert result["result"]["note_status"] == "available"
    assert result["result"]["note_chars"] == len("Existing note.")
    assert len(result["result"]["note_safe_sha256"]) == 64
    assert "Existing note." not in str(result)
    assert len(result["result"]["update_safe_sha256"]) == 64
    assert len(result["result"]["delete_safe_sha256"]) == 64
    assert "runtime-contact-1" not in str(result)


def test_search_contact_groups_returns_metadata_only() -> None:
    result = search_contact_groups("Synthetic", contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "group_name"
    assert result["result_count"] == 1
    group = result["results"][0]
    assert group["handle"].startswith("contacts:group:v1:")
    assert group["name"] == "Synthetic Group"
    assert group["member_count"] == 1
    assert "runtime-group-1" not in str(result)


def test_get_contact_group_returns_safe_hash_without_raw_id() -> None:
    search = search_contact_groups("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = get_contact_group(handle, contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["result"]["handle"] == handle
    assert len(result["result"]["group_safe_sha256"]) == 64
    assert result["result"]["member_count"] == 1
    assert "runtime-group-1" not in str(result)


def test_list_contact_group_members_returns_metadata_only() -> None:
    search = search_contact_groups("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = list_contact_group_members(handle, limit=5, contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["query"]["scope"] == "selected_group_members"
    assert result["query"]["limit"] == 5
    assert result["group"]["handle"] == handle
    assert result["result_count"] == 1
    member = result["results"][0]
    assert member["handle"].startswith("contacts:contact:v1:")
    assert member["display_name"] == "Synthetic Member"
    assert member["email_count"] == 1
    assert result["content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert result["contact_details_returned"] is False
    assert "runtime-member-1" not in str(result)
    assert "hidden@example.invalid" not in str(result)


def test_list_contact_group_members_degraded_keeps_safe_shape() -> None:
    def degraded_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_group_members":
            return {
                "schema_version": 1,
                "status": "degraded",
                "source": "contacts",
                "authorization_status": "denied",
                "contacts": [],
                "warnings": [{"code": "contacts_access_unavailable", "message": "unavailable"}],
            }
        return _contacts_runner(payload, timeout)

    search = search_contact_groups("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = list_contact_group_members(handle, limit=5, contacts_runner=degraded_runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["query"]["scope"] == "selected_group_members"
    assert result["group"]["handle"] == handle
    assert result["results"] == []
    assert result["result_count"] == 0
    assert result["content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert result["contact_details_returned"] is False
    assert result["warnings"][0]["code"] == "contacts_access_unavailable"


def test_list_contact_group_members_enforces_adapter_cap() -> None:
    def overrun_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_group_members":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "group": {
                    "group_id": "runtime-group-1",
                    "name": "Synthetic Group",
                    "member_count": 60,
                    "member_ids": [f"runtime-member-{index}" for index in range(60)],
                },
                "contacts": [
                    {
                        "contact_id": f"runtime-member-{index}",
                        "display_name": f"Synthetic Member {index:02d}",
                        "contact_type": "person",
                        "given_name": "Synthetic",
                        "family_name": f"Member {index:02d}",
                        "nickname": "",
                        "organization_name": "Example Org",
                        "department_name": "",
                        "job_title": "",
                        "email_count": 1,
                        "phone_count": 0,
                        "postal_address_count": 0,
                        "url_count": 0,
                        "social_profile_count": 0,
                        "instant_message_count": 0,
                        "relation_count": 0,
                        "dates_count": 0,
                        "birthday_present": False,
                        "image_available": False,
                        "note_status": "requires_entitlement",
                        "email_addresses": [{"label": "home", "value": f"hidden{index}@example.invalid"}],
                    }
                    for index in range(60)
                ],
                "truncated": False,
                "warnings": [],
            }
        return _contacts_runner(payload, timeout)

    search = search_contact_groups("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = list_contact_group_members(handle, limit=5, contacts_runner=overrun_runner)

    assert result["status"] == "ok"
    assert result["query"]["limit"] == 5
    assert result["query"]["truncated"] is True
    assert result["result_count"] == 5
    assert len(result["results"]) == 5
    assert "runtime-member-59" not in str(result)
    assert "hidden59@example.invalid" not in str(result)


def test_list_contact_group_members_rejects_bad_handle() -> None:
    result = list_contact_group_members("contacts:contact:v1:not-a-group")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"
    assert result["results"] == []


def test_count_contacts_returns_live_count_without_details() -> None:
    result = count_contacts(contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["result"]["live_count"] == 1
    assert result["result"]["count_complete"] is True
    assert "Synthetic Contact" not in str(result)
    assert "Existing note." not in str(result)


def test_export_contacts_archive_writes_verified_json_and_vcard(tmp_path) -> None:
    result = export_contacts_archive(
        output_dir=tmp_path / "backup",
        filename_prefix="../contacts backup",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["contact_data_exported"] is True
    assert result["result"]["archive_verified"] is True
    assert result["result"]["counts_match"] is True
    assert result["result"]["live_count"] == 1
    assert result["result"]["json_contact_count"] == 1
    assert result["result"]["vcard_contact_count"] == 1
    assert "Synthetic Contact" not in json.dumps(result)
    assert "Existing note." not in json.dumps(result)
    json_path = tmp_path / "backup" / "contacts-backup.json"
    vcard_path = tmp_path / "backup" / "contacts-backup.vcf"
    manifest_path = tmp_path / "backup" / "contacts-backup-manifest.json"
    assert json_path.exists()
    assert vcard_path.exists()
    assert manifest_path.exists()
    snapshot = json.loads(json_path.read_text(encoding="utf-8"))
    assert snapshot["contact_count"] == 1
    assert snapshot["contacts"][0]["note_text"] == "Existing note."
    assert "BEGIN:VCARD" in vcard_path.read_text(encoding="utf-8")


def test_export_contacts_archive_retains_json_when_vcard_is_unavailable(
    tmp_path,
) -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": "authorized",
            "contact_count": 1,
            "contacts": [
                {
                    "contact_id": "synthetic-fallback-1",
                    "display_name": "Synthetic Fallback Contact",
                }
            ],
            "vcard_text": "",
            "notes_exported": False,
            "scan_truncated": False,
            "warnings": [
                {
                    "code": "contacts_notes_unavailable",
                    "message": "Contact notes were omitted.",
                },
                {
                    "code": "contacts_vcard_export_failed",
                    "message": "vCard output was unavailable.",
                },
            ],
        }

    result = export_contacts_archive(
        output_dir=tmp_path / "backup",
        filename_prefix="fallback",
        contacts_runner=runner,
    )

    assert result["status"] == "error"
    assert result["result"]["archive_verified"] is False
    assert result["result"]["json_contact_count"] == 1
    assert result["result"]["vcard_contact_count"] == 0
    assert result["result"]["notes_exported"] is False
    assert "Synthetic Fallback Contact" not in json.dumps(result)
    snapshot = json.loads(
        (tmp_path / "backup" / "fallback.json").read_text(encoding="utf-8")
    )
    assert snapshot["contacts"][0]["display_name"] == "Synthetic Fallback Contact"


def test_contacts_helper_fetches_formatter_required_keys() -> None:
    helper_source = CONTACTS_HELPER.read_text(encoding="utf-8")

    assert "CNContactFormatter.descriptorForRequiredKeys(for: .fullName)" in helper_source
    assert "CNContactVCardSerialization.descriptorForRequiredKeys()" in helper_source
    assert "let updateStateKeys: [CNKeyDescriptor] = detailKeys" in helper_source
    assert "if let bool = value as? Bool" in helper_source
    assert "if let int = value as? Int" in helper_source
    assert ".withoutEscapingSlashes" in helper_source


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


def _contact_handle_and_update_sha() -> tuple[str, str]:
    search = search_contacts("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]
    detail = get_contact(handle, contacts_runner=_contacts_runner)
    return handle, detail["result"]["update_safe_sha256"]


def _contact_handle_and_delete_sha() -> tuple[str, str]:
    search = search_contacts("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]
    detail = get_contact(handle, contacts_runner=_contacts_runner)
    return handle, detail["result"]["delete_safe_sha256"]


def _contact_handle_and_note_sha() -> tuple[str, str]:
    search = search_contacts("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]
    detail = get_contact(handle, contacts_runner=_contacts_runner)
    return handle, detail["result"]["note_safe_sha256"]


def _group_handle_and_sha() -> tuple[str, str]:
    search = search_contact_groups("Synthetic", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]
    detail = get_contact_group(handle, contacts_runner=_contacts_runner)
    return handle, detail["result"]["group_safe_sha256"]


def _container_handle_and_sha() -> tuple[str, str]:
    search = search_contact_containers("iCloud", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]
    detail = get_contact_container(handle, contacts_runner=_contacts_runner)
    return handle, detail["result"]["container_safe_sha256"]


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


def test_plan_contact_change_update_returns_exact_handle_preview() -> None:
    handle, current_sha = _contact_handle_and_update_sha()

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Renamed",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "update"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["expected_current_sha256"] == current_sha
    assert result["preview"]["proposed"]["given_name"] == "Renamed"
    assert result["preview"]["proposed"]["family_name"] == "Contact"
    assert result["preview"]["proposed"]["updated_fields"] == ["given_name"]
    assert result["preview"]["proposed"]["email_addresses"] == "preserved"
    assert result["preview"]["proposed"]["email_count"] == "preserved"


def test_plan_contact_change_update_uses_scalar_state_only() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    commands: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        commands.append(payload["command"])
        if payload["command"] == "contact_by_id":
            raise AssertionError("update planning must not fetch full contact details")
        return _contacts_runner(payload, timeout)

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Renamed",
        contacts_runner=runner,
    )

    assert result["status"] == "ok"
    assert "contact_update_state_by_id" in commands
    assert "contact_by_id" not in commands


def test_plan_contact_change_update_requires_hash_and_handle() -> None:
    result = plan_contact_change("update", given_name="Renamed", contacts_runner=_contacts_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_contact_change_update_rejects_stale_hash() -> None:
    handle, _current_sha = _contact_handle_and_update_sha()

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256="0" * 64,
        given_name="Renamed",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "current_contact_changed"


def test_plan_contact_change_update_rejects_noop() -> None:
    handle, current_sha = _contact_handle_and_update_sha()

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Synthetic",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "already_applied"


def test_plan_contact_change_update_replaces_contact_methods() -> None:
    handle, current_sha = _contact_handle_and_update_sha()

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        email_addresses=[{"label": "work", "value": "new@example.invalid"}],
        phone_numbers=[{"label": "work", "value": "+1 555 0102"}],
        url_addresses=[{"label": "home", "value": "https://new.example.invalid"}],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["updated_fields"] == [
        "email_addresses",
        "phone_numbers",
        "url_addresses",
    ]
    assert result["preview"]["proposed"]["email_addresses"] == [
        {"label": "work", "value": "new@example.invalid"}
    ]
    assert result["preview"]["proposed"]["phone_count"] == 1
    assert result["preview"]["proposed"]["url_count"] == 1


def test_plan_contact_change_update_replaces_rich_contact_fields() -> None:
    handle, current_sha = _contact_handle_and_update_sha()

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        postal_addresses=[
            {
                "label": "home",
                "street": "2 New Way",
                "city": "Example",
                "state": "CA",
                "postal_code": "94001",
                "country": "United States",
                "iso_country_code": "US",
            }
        ],
        birthday={"year": 1990, "month": 1, "day": 2},
        dates=[{"label": "anniversary", "date": {"month": 3, "day": 4}}],
        social_profiles=[
            {"label": "work", "service": "LinkedIn", "username": "synthetic-contact", "url": ""}
        ],
        instant_message_addresses=[
            {"label": "home", "service": "Signal", "username": "synthetic"}
        ],
        contact_relations=[{"label": "assistant", "name": "Fixture Friend"}],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["updated_fields"] == [
        "postal_addresses",
        "birthday",
        "dates",
        "social_profiles",
        "instant_message_addresses",
        "contact_relations",
    ]
    assert result["preview"]["proposed"]["postal_address_count"] == 1
    assert result["preview"]["proposed"]["birthday"] == {"year": 1990, "month": 1, "day": 2}
    assert result["preview"]["proposed"]["relation_count"] == 1


def test_plan_contact_change_update_can_clear_contact_methods() -> None:
    handle, current_sha = _contact_handle_and_update_sha()

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        email_addresses=[],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["updated_fields"] == ["email_addresses"]
    assert result["preview"]["proposed"]["email_addresses"] == []
    assert result["preview"]["proposed"]["email_count"] == 0


def test_plan_contact_change_update_can_set_and_clear_image(tmp_path) -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    image_path = tmp_path / "avatar.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        image_path=str(image_path),
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["updated_fields"] == [
        "image_available",
        "image_sha256",
        "image_bytes",
    ]
    assert result["preview"]["proposed"]["image"]["action"] == "set"
    assert result["preview"]["proposed"]["image"]["image_bytes"] == image_path.stat().st_size
    assert str(image_path) not in str(result)

    clear_result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        clear_image=True,
        contacts_runner=_contacts_runner,
    )
    assert clear_result["status"] == "error"
    assert clear_result["warnings"][0]["code"] == "already_applied"


def test_plan_contact_change_delete_returns_exact_destructive_preview() -> None:
    handle, current_sha = _contact_handle_and_delete_sha()

    result = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["preview"]["operation"] == "delete"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["expected_current_sha256"] == current_sha
    assert result["preview"]["destructive"] is True
    assert result["preview"]["proposed"]["effect"] == "delete_exact_contact"
    assert result["preview"]["proposed"]["email_addresses"] == "removed"


def test_plan_contact_change_delete_uses_exact_detail_state() -> None:
    handle, current_sha = _contact_handle_and_delete_sha()
    commands: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        commands.append(payload["command"])
        return _contacts_runner(payload, timeout)

    result = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        contacts_runner=runner,
    )

    assert result["status"] == "ok"
    assert "contact_by_id" in commands


def test_plan_contact_change_delete_rejects_stale_hash() -> None:
    handle, _current_sha = _contact_handle_and_delete_sha()

    result = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256="0" * 64,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "current_contact_changed"


def test_plan_contact_change_delete_rejects_missing_hash() -> None:
    handle, _current_sha = _contact_handle_and_delete_sha()

    result = plan_contact_change(
        "delete",
        handle=handle,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_required_field"


def test_plan_contact_change_delete_rejects_invalid_hash() -> None:
    handle, _current_sha = _contact_handle_and_delete_sha()

    result = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256="not-a-sha",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_expected_sha256"


def test_plan_contact_change_delete_rejects_invalid_handle() -> None:
    result = plan_contact_change(
        "delete",
        handle="raw-contact-id",
        expected_current_sha256="0" * 64,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_plan_contact_change_delete_rejects_extra_fields() -> None:
    handle, current_sha = _contact_handle_and_delete_sha()

    result = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Nope",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unexpected_delete_field"


def test_plan_contact_change_adds_group_member_with_exact_hashes() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    group_handle, group_sha = _group_handle_and_sha()

    result = plan_contact_change(
        "add_group_member",
        handle=handle,
        expected_current_sha256=current_sha,
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "add_group_member"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["group_handle"] == group_handle
    assert result["preview"]["target"]["expected_group_sha256"] == group_sha
    assert result["preview"]["proposed"]["effect"] == "add_contact_to_group"
    assert result["preview"]["proposed"]["member_count_after"] == 2
    assert "runtime-group-1" not in str(result)
    assert "runtime-contact-1" not in str(result)


def test_apply_contact_change_adds_group_member_and_verifies() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    group_handle, group_sha = _group_handle_and_sha()
    plan = plan_contact_change(
        "add_group_member",
        handle=handle,
        expected_current_sha256=current_sha,
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "add_group_member",
        handle=handle,
        expected_current_sha256=current_sha,
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "add_group_member"
    assert result["mutation_applied"] is True
    assert result["read_back"]["group_handle"] == group_handle
    assert result["read_back"]["member_count"] == 2
    assert result["read_back"]["membership_verified"] is True
    assert "runtime-group-1" not in str(result)


def test_search_contact_containers_returns_opaque_handles() -> None:
    result = search_contact_containers("iCloud", contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["results"][0]["handle"].startswith("contacts:container:v1:")
    assert result["results"][0]["name"] == "iCloud"
    assert "runtime-container-1" not in str(result)


def test_get_contact_container_returns_safe_hash() -> None:
    handle, container_sha = _container_handle_and_sha()

    result = get_contact_container(handle, contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["result"]["container_safe_sha256"] == container_sha
    assert "runtime-container-1" not in str(result)


def test_list_contact_container_members_returns_metadata_only() -> None:
    search = search_contact_containers("iCloud", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = list_contact_container_members(handle, limit=5, contacts_runner=_contacts_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["query"]["scope"] == "selected_container_members"
    assert result["query"]["limit"] == 5
    assert result["container"]["handle"] == handle
    assert result["result_count"] == 1
    member = result["results"][0]
    assert member["handle"].startswith("contacts:contact:v1:")
    assert member["display_name"] == "Synthetic Container Member"
    assert member["email_count"] == 1
    assert result["content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert result["contact_details_returned"] is False
    assert "runtime-container-member-1" not in str(result)
    assert "hidden-container@example.invalid" not in str(result)


def test_list_contact_container_members_degraded_keeps_safe_shape() -> None:
    def degraded_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_container_members":
            return {
                "schema_version": 1,
                "status": "degraded",
                "source": "contacts",
                "authorization_status": "denied",
                "contacts": [],
                "warnings": [{"code": "contacts_access_unavailable", "message": "unavailable"}],
            }
        return _contacts_runner(payload, timeout)

    search = search_contact_containers("iCloud", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = list_contact_container_members(handle, limit=5, contacts_runner=degraded_runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["query"]["scope"] == "selected_container_members"
    assert result["container"]["handle"] == handle
    assert result["results"] == []
    assert result["result_count"] == 0
    assert result["content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert result["contact_details_returned"] is False
    assert result["warnings"][0]["code"] == "contacts_access_unavailable"


def test_list_contact_container_members_resolve_failure_keeps_metadata_shape() -> None:
    def degraded_resolver(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_containers":
            return {
                "schema_version": 1,
                "status": "degraded",
                "source": "contacts",
                "authorization_status": "denied",
                "warnings": [{"code": "contacts_access_unavailable", "message": "unavailable"}],
            }
        return _contacts_runner(payload, timeout)

    handle = search_contact_containers("iCloud", contacts_runner=_contacts_runner)["results"][0]["handle"]

    result = list_contact_container_members(handle, limit=5, contacts_runner=degraded_resolver)

    assert result["status"] == "degraded"
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["query"]["scope"] == "selected_container_members"
    assert result["container"] is None
    assert result["results"] == []
    assert result["result_count"] == 0
    assert result["content_returned"] is False
    assert result["raw_identifier_returned"] is False
    assert result["contact_details_returned"] is False
    assert result["warnings"][0]["code"] == "contacts_access_unavailable"


def test_list_contact_container_members_enforces_adapter_cap() -> None:
    def overrun_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_container_members":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": "authorized",
                "container": {
                    "container_id": "runtime-container-1",
                    "name": "iCloud",
                    "type": "carddav",
                },
                "contacts": [
                    {
                        "contact_id": f"runtime-container-member-{index}",
                        "display_name": f"Synthetic Container Member {index:02d}",
                        "contact_type": "person",
                        "given_name": "Synthetic",
                        "family_name": f"Container {index:02d}",
                        "nickname": "",
                        "organization_name": "Example Org",
                        "department_name": "",
                        "job_title": "",
                        "email_count": 1,
                        "phone_count": 0,
                        "postal_address_count": 0,
                        "url_count": 0,
                        "social_profile_count": 0,
                        "instant_message_count": 0,
                        "relation_count": 0,
                        "dates_count": 0,
                        "birthday_present": False,
                        "image_available": False,
                        "note_status": "requires_entitlement",
                        "email_addresses": [{"label": "home", "value": f"hidden-container{index}@example.invalid"}],
                    }
                    for index in range(60)
                ],
                "truncated": False,
                "warnings": [],
            }
        return _contacts_runner(payload, timeout)

    search = search_contact_containers("iCloud", contacts_runner=_contacts_runner)
    handle = search["results"][0]["handle"]

    result = list_contact_container_members(handle, limit=5, contacts_runner=overrun_runner)

    assert result["status"] == "ok"
    assert result["query"]["limit"] == 5
    assert result["query"]["truncated"] is True
    assert result["result_count"] == 5
    assert len(result["results"]) == 5
    assert "runtime-container-member-59" not in str(result)
    assert "hidden-container59@example.invalid" not in str(result)


def test_list_contact_container_members_rejects_bad_handle() -> None:
    result = list_contact_container_members("contacts:contact:v1:not-a-container")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"
    assert result["results"] == []


def test_plan_contact_change_create_group_binds_container() -> None:
    container_handle, container_sha = _container_handle_and_sha()

    result = plan_contact_change(
        "create_group",
        group_name="Friends",
        container_handle=container_handle,
        expected_container_sha256=container_sha,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "create_group"
    assert result["preview"]["target"]["container_handle"] == container_handle
    assert result["preview"]["target"]["expected_container_sha256"] == container_sha
    assert result["preview"]["proposed"]["group_name"] == "Friends"
    assert "runtime-container-1" not in str(result)


def test_apply_contact_change_create_group_verifies_read_back() -> None:
    container_handle, container_sha = _container_handle_and_sha()
    plan = plan_contact_change(
        "create_group",
        group_name="Friends",
        container_handle=container_handle,
        expected_container_sha256=container_sha,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "create_group",
        group_name="Friends",
        container_handle=container_handle,
        expected_container_sha256=container_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "create_group"
    assert result["read_back"]["handle"].startswith("contacts:group:v1:")
    assert result["read_back"]["name"] == "Friends"
    assert result["read_back"]["member_count"] == 0
    assert "runtime-group-2" not in str(result)


def test_plan_contact_change_rename_group_binds_group_hash() -> None:
    group_handle, group_sha = _group_handle_and_sha()

    result = plan_contact_change(
        "rename_group",
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        group_name="Renamed Group",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "rename_group"
    assert result["preview"]["target"]["group_handle"] == group_handle
    assert result["preview"]["proposed"]["group_name"] == "Renamed Group"
    assert "runtime-group-1" not in str(result)


def test_apply_contact_change_rename_group_returns_metadata() -> None:
    group_handle, group_sha = _group_handle_and_sha()
    plan = plan_contact_change(
        "rename_group",
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        group_name="Renamed Group",
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "rename_group",
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        group_name="Renamed Group",
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "rename_group"
    assert result["read_back"]["name"] == "Renamed Group"
    assert result["read_back"]["group_safe_sha256"]


def test_apply_contact_change_delete_group_proves_absent_without_contact_delete() -> None:
    group_handle, group_sha = _group_handle_and_sha()
    plan = plan_contact_change(
        "delete_group",
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "delete_group",
        group_handle=group_handle,
        expected_group_sha256=group_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "delete_group"
    assert result["read_back"]["deleted"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["contacts_deleted"] is False


def test_plan_contact_change_batch_binds_child_fingerprints() -> None:
    handle, note_sha = _contact_handle_and_note_sha()
    _handle, update_sha = _contact_handle_and_update_sha()
    group_handle, group_sha = _group_handle_and_sha()

    result = plan_contact_change(
        "batch",
        batch_items=[
            {
                "operation": "append_note",
                "handle": handle,
                "expected_current_sha256": note_sha,
                "note_text": "\n\nBatch context.",
            },
            {
                "operation": "add_group_member",
                "handle": handle,
                "expected_current_sha256": update_sha,
                "group_handle": group_handle,
                "expected_group_sha256": group_sha,
            },
        ],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "batch"
    assert result["preview"]["item_count"] == 2
    assert result["preview"]["items"][0]["operation"] == "append_note"
    assert result["preview"]["items"][1]["operation"] == "add_group_member"
    assert "runtime-contact-1" not in str(result)
    assert "runtime-group-1" not in str(result)


def test_apply_contact_change_batch_runs_exact_items() -> None:
    handle, note_sha = _contact_handle_and_note_sha()
    _handle, update_sha = _contact_handle_and_update_sha()
    group_handle, group_sha = _group_handle_and_sha()
    items = [
        {
            "operation": "append_note",
            "handle": handle,
            "expected_current_sha256": note_sha,
            "note_text": "\n\nBatch context.",
        },
        {
            "operation": "add_group_member",
            "handle": handle,
            "expected_current_sha256": update_sha,
            "group_handle": group_handle,
            "expected_group_sha256": group_sha,
        },
    ]
    plan = plan_contact_change("batch", batch_items=items, contacts_runner=_contacts_runner)

    result = apply_contact_change(
        "batch",
        batch_items=items,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "batch"
    assert result["mutation_applied"] is True
    assert result["read_back"]["item_count"] == 2
    assert result["read_back"]["applied_count"] == 2
    assert result["read_back"]["items"][0]["operation"] == "append_note"
    assert result["read_back"]["items"][1]["operation"] == "add_group_member"
    assert "runtime-contact-1" not in str(result)
    assert "runtime-group-1" not in str(result)


def test_plan_contact_change_append_note_returns_exact_preview() -> None:
    handle, current_sha = _contact_handle_and_note_sha()

    result = plan_contact_change(
        "append_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text="\n\nMet through synthetic fixture.",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["preview"]["operation"] == "append_note"
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["expected_current_sha256"] == current_sha
    assert result["preview"]["proposed"]["effect"] == "append_contact_note"
    assert result["preview"]["proposed"]["append_text"] == "\n\nMet through synthetic fixture."
    assert result["preview"]["proposed"]["resulting_note_chars"] == len(
        "Existing note.\n\nMet through synthetic fixture."
    )
    assert "Existing note." not in str(result)


def test_plan_contact_change_append_note_rejects_stale_hash() -> None:
    handle, _current_sha = _contact_handle_and_note_sha()

    result = plan_contact_change(
        "append_note",
        handle=handle,
        expected_current_sha256="0" * 64,
        note_text="New synthetic context.",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "current_contact_changed"


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


def test_apply_contact_change_updates_exact_contact_and_reads_back() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    plan = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Renamed",
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Renamed",
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "update"
    assert result["mutation_applied"] is True
    assert result["read_back"]["given_name"] == "Renamed"
    assert result["read_back"]["family_name"] == "Contact"
    assert result["read_back"]["email_addresses"][0]["value"] == "synthetic@example.invalid"


def test_apply_contact_change_replaces_contact_methods_and_reads_back() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    plan = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        email_addresses=[{"label": "work", "value": "new@example.invalid"}],
        phone_numbers=[{"label": "work", "value": "+1 555 0102"}],
        url_addresses=[],
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        email_addresses=[{"label": "work", "value": "new@example.invalid"}],
        phone_numbers=[{"label": "work", "value": "+1 555 0102"}],
        url_addresses=[],
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "update"
    assert result["mutation_applied"] is True
    assert result["read_back"]["email_addresses"] == [
        {"label": "work", "value": "new@example.invalid"}
    ]
    assert result["read_back"]["phone_numbers"] == [
        {"label": "work", "value": "+1 555 0102"}
    ]
    assert result["read_back"]["url_addresses"] == []


def test_apply_contact_change_replaces_rich_fields_and_reads_back() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    postal = [
        {
            "label": "home",
            "street": "2 New Way",
            "city": "Example",
            "state": "CA",
            "postal_code": "94001",
            "country": "United States",
            "iso_country_code": "US",
        }
    ]
    birthday = {"year": 1990, "month": 1, "day": 2}
    relations = [{"label": "assistant", "name": "Fixture Friend"}]
    plan = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        postal_addresses=postal,
        birthday=birthday,
        contact_relations=relations,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        postal_addresses=postal,
        birthday=birthday,
        contact_relations=relations,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["postal_addresses"] == postal
    assert result["read_back"]["birthday"] == birthday
    assert result["read_back"]["contact_relations"] == relations


def test_apply_contact_change_sets_image_with_source_recheck(tmp_path) -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    image_path = tmp_path / "avatar.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    plan = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        image_path=str(image_path),
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        image_path=str(image_path),
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["read_back"]["image_available"] is True
    assert result["read_back"]["image_bytes"] == 67
    assert result["read_back"]["image_sha256"] == "image-sha"
    assert str(image_path) not in str(result)


def test_apply_contact_change_rejects_changed_image_source(tmp_path) -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    image_path = tmp_path / "avatar.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    plan = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        image_path=str(image_path),
        contacts_runner=_contacts_runner,
    )
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nchanged")

    result = apply_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        image_path=str(image_path),
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_contact_change_update_rejects_changed_current_state() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    plan = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Renamed",
        contacts_runner=_contacts_runner,
    )

    def changed_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_update_state_by_id":
            detail = _contacts_runner(payload, timeout)
            detail["contact"]["given_name"] = "Changed"
            return detail
        return _contacts_runner(payload, timeout)

    result = apply_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        given_name="Renamed",
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=changed_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "current_contact_changed"


def test_apply_contact_change_deletes_exact_contact_and_verifies_absence() -> None:
    handle, current_sha = _contact_handle_and_delete_sha()
    plan = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "delete"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"] == handle
    assert result["read_back"]["deleted"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["result_count"] == 0


def test_apply_contact_change_appends_note_and_reads_back_hash_only() -> None:
    handle, current_sha = _contact_handle_and_note_sha()
    note_text = "\n\nMet through synthetic fixture."
    plan = plan_contact_change(
        "append_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text=note_text,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "append_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text=note_text,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "append_note"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"] == handle
    assert result["read_back"]["note_chars"] == len("Existing note." + note_text)
    assert len(result["read_back"]["note_safe_sha256"]) == 64
    assert result["read_back"]["appended_note_chars"] == len(note_text)
    assert "Existing note." not in str(result)


def test_plan_contact_change_set_note_returns_exact_preview_without_existing_note() -> None:
    handle, current_sha = _contact_handle_and_note_sha()

    result = plan_contact_change(
        "set_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text="Replacement context.",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "set_note"
    assert result["preview"]["operation_alias"] == "set_note"
    assert result["preview"]["proposed"]["effect"] == "set_contact_note"
    assert result["preview"]["proposed"]["set_note_text"] == "Replacement context."
    assert result["preview"]["proposed"]["existing_note_returned"] is False
    assert "Existing note." not in str(result)


def test_apply_contact_change_set_note_reads_back_hash_only() -> None:
    handle, current_sha = _contact_handle_and_note_sha()
    plan = plan_contact_change(
        "set_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text="Replacement context.",
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "set_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text="Replacement context.",
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "set_note"
    assert result["operation_alias"] == "set_note"
    assert result["read_back"]["note_chars"] == len("Replacement context.")
    assert result["read_back"]["set_note_chars"] == len("Replacement context.")
    assert "Replacement context." not in str(result["read_back"])
    assert "Existing note." not in str(result)


def test_apply_contact_change_clear_note() -> None:
    handle, current_sha = _contact_handle_and_note_sha()
    plan = plan_contact_change(
        "clear_note",
        handle=handle,
        expected_current_sha256=current_sha,
        contacts_runner=_contacts_runner,
    )

    result = apply_contact_change(
        "clear_note",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "set_note"
    assert result["operation_alias"] == "clear_note"
    assert result["read_back"]["note_chars"] == 0


def test_plan_contact_change_merge_note_does_not_return_resulting_existing_note() -> None:
    handle, current_sha = _contact_handle_and_note_sha()

    result = plan_contact_change(
        "merge_note",
        handle=handle,
        expected_current_sha256=current_sha,
        note_text="New context line.",
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["operation"] == "set_note"
    assert result["preview"]["operation_alias"] == "merge_note"
    assert result["preview"]["proposed"]["effect"] == "merge_contact_note"
    assert result["preview"]["proposed"]["merge_text"] == "New context line."
    assert result["preview"]["proposed"]["resulting_note_returned"] is False
    assert "Existing note." not in str(result)


def test_apply_contact_change_delete_requires_absence_proof() -> None:
    handle, current_sha = _contact_handle_and_delete_sha()
    plan = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        contacts_runner=_contacts_runner,
    )

    def weak_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contacts_apply_change" and payload["operation"] == "delete":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "contact": None,
                "deleted": True,
                "verified_absent": False,
                "warnings": [],
            }
        return _contacts_runner(payload, timeout)

    result = apply_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=weak_runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_unavailable"


def test_apply_contact_change_delete_rejects_changed_current_state() -> None:
    handle, current_sha = _contact_handle_and_delete_sha()
    plan = plan_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        contacts_runner=_contacts_runner,
    )

    def changed_runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "contact_by_id":
            detail = _contacts_runner(payload, timeout)
            detail["contact"]["given_name"] = "Changed"
            return detail
        return _contacts_runner(payload, timeout)

    result = apply_contact_change(
        "delete",
        handle=handle,
        expected_current_sha256=current_sha,
        approval_token=_contacts_token(plan),
        confirm_apply=True,
        contacts_runner=changed_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "current_contact_changed"


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


def test_plan_contact_change_preserves_freeform_custom_label_verbatim() -> None:
    # A label with spaces, mixed case, and punctuation round-trips exactly: no
    # lowercasing and no space->underscore normalization (v1.180 free-form labels).
    freeform = "My Custom Label (2nd)!"

    result = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Label",
        email_addresses=[{"label": freeform, "value": "synthetic@example.invalid"}],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["email_addresses"] == [
        {"label": freeform, "value": "synthetic@example.invalid"}
    ]


def test_plan_contact_change_preserves_freeform_label_on_rich_fields() -> None:
    handle, current_sha = _contact_handle_and_update_sha()
    freeform = "Summer House / Beach"

    result = plan_contact_change(
        "update",
        handle=handle,
        expected_current_sha256=current_sha,
        postal_addresses=[
            {
                "label": freeform,
                "street": "3 Sandy Way",
                "city": "Example",
                "state": "CA",
                "postal_code": "94002",
                "country": "United States",
                "iso_country_code": "US",
            }
        ],
        social_profiles=[
            {"label": freeform, "service": "LinkedIn", "username": "synthetic", "url": ""}
        ],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["postal_addresses"][0]["label"] == freeform
    assert result["preview"]["proposed"]["social_profiles"][0]["label"] == freeform


def test_plan_contact_change_allows_255_char_label() -> None:
    label = "L" + "a" * 253 + "z"  # exactly 255 chars
    assert len(label) == 255

    result = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Boundary",
        phone_numbers=[{"label": label, "value": "+1 555 0100"}],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["phone_numbers"][0]["label"] == label


def test_plan_contact_change_rejects_oversize_label() -> None:
    label = "x" * 256  # one past the 255-char bound

    result = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Oversize",
        email_addresses=[{"label": label, "value": "synthetic@example.invalid"}],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "error"
    codes = {warning["code"] for warning in result["warnings"]}
    assert "label_too_large" in codes


def test_plan_contact_change_rejects_control_char_label() -> None:
    for bad_label in ("Line\nBreak", "Tab\tLabel", "Null\x00Byte"):
        result = plan_contact_change(
            "create",
            contact_type="person",
            given_name="Synthetic",
            family_name="Control",
            email_addresses=[{"label": bad_label, "value": "synthetic@example.invalid"}],
            contacts_runner=_contacts_runner,
        )

        assert result["status"] == "error"
        codes = {warning["code"] for warning in result["warnings"]}
        assert "invalid_label" in codes


def test_plan_contact_change_defaults_empty_label_to_other() -> None:
    result = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Empty",
        email_addresses=[{"label": "   ", "value": "synthetic@example.invalid"}],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["email_addresses"][0]["label"] == "other"


def test_plan_contact_change_case_and_space_labels_are_distinct_verbatim() -> None:
    # Two labels differing only in case/spacing must be preserved as distinct verbatim
    # strings (the Python side of the Swift labelsMatchVerbatim create-idempotency
    # consistency): "Work Phone" and "work_phone" are NOT collapsed to one label.
    result = plan_contact_change(
        "create",
        contact_type="person",
        given_name="Synthetic",
        family_name="Cased",
        phone_numbers=[
            {"label": "Work Phone", "value": "+1 555 0101"},
            {"label": "work_phone", "value": "+1 555 0102"},
        ],
        contacts_runner=_contacts_runner,
    )

    assert result["status"] == "ok"
    labels = [entry["label"] for entry in result["preview"]["proposed"]["phone_numbers"]]
    assert labels == ["Work Phone", "work_phone"]
    assert labels[0] != labels[1]

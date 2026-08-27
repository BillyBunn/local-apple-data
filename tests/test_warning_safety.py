from __future__ import annotations

from collections.abc import Callable

from local_apple_data.adapters import (
    calendar,
    contacts,
    icloud_drive,
    mail,
    messages,
    notes,
    photos,
    reminders,
)
from local_apple_data.adapters.warning_safety import safe_warning_message


SafeWarnings = Callable[[dict], list[dict[str, str]]]


ADAPTER_WARNING_HELPERS: tuple[tuple[SafeWarnings, str], ...] = (
    (calendar._safe_warnings, "Calendar warning detail was redacted."),
    (contacts._safe_warnings, "Contacts warning detail was redacted."),
    (icloud_drive._safe_warnings, "iCloud Drive warning detail was redacted."),
    (mail._safe_warnings, "Mail warning detail was redacted."),
    (messages._safe_warnings, "Messages warning detail was redacted."),
    (notes._safe_warnings, "Notes warning detail was redacted."),
    (photos._safe_warnings, "Photos warning detail was redacted."),
    (reminders._safe_warnings, "Reminders warning detail was redacted."),
)

FALLBACK = "Warning detail was redacted."


def test_mail_messages_notes_warning_factories_preserve_legacy_shape() -> None:
    for module in (mail, messages, notes):
        assert module._warning("synthetic_warning", "Synthetic safe warning.") == {
            "code": "synthetic_warning",
            "message": "Synthetic safe warning.",
        }


def test_safe_warning_message_preserves_safe_text() -> None:
    assert (
        safe_warning_message("Synthetic safe warning.", fallback_message=FALLBACK)
        == "Synthetic safe warning."
    )


def test_safe_warning_message_redacts_path_and_url_variants() -> None:
    unsafe_messages = [
        "Error:/Users/synthetic/Library/Mail/Envelope Index",
        "at/Users/synthetic/Library/Mail/Envelope Index",
        "path=>/private/tmp/local-apple-data.db",
        "(/Library/Application Support/Synthetic/store)",
        "[/Applications/Synthetic.app]",
        "`/System/Library/PrivateFrameworks`",
        "smb://synthetic.example.invalid/share",
    ]

    for message in unsafe_messages:
        assert safe_warning_message(message, fallback_message=FALLBACK) == FALLBACK


def test_safe_warning_message_redacts_exception_and_framework_text() -> None:
    unsafe_messages = [
        "Traceback while reading local helper output.",
        "The operation couldn't be completed. EKErrorDomain code 1.",
        "SQLite database is locked.",
        "NSErrorDomain failure.",
        "NSURLErrorDomain failure.",
        "CFErrorDomainLaunchd failure.",
        "kCLErrorDomain failure.",
        "URLError cannot load resource.",
        "OSStatus -54.",
    ]

    for message in unsafe_messages:
        assert safe_warning_message(message, fallback_message=FALLBACK) == FALLBACK


def test_safe_warning_message_redacts_pii_shapes_and_handles() -> None:
    unsafe_messages = [
        "Failed to look up synthetic@example.invalid.",
        "No Messages chat for +1 (415) 555-0101.",
        "Unable to read mail:message:v2:abcdef.",
        "Unable to read mail:mailbox:v1:abcdef.",
        "Unable to read voice_memos:recording:v1:abcdef.",
        "Unable to read freeform:board:v1:abcdef.",
        "Unable to read reminders:reminder:eventkit:v1:abcdef.",
    ]

    for message in unsafe_messages:
        assert safe_warning_message(message, fallback_message=FALLBACK) == FALLBACK


def test_safe_warning_message_redacts_empty_and_long_text() -> None:
    assert safe_warning_message("   ", fallback_message=FALLBACK) == FALLBACK
    assert safe_warning_message("x" * 241, fallback_message=FALLBACK) == FALLBACK
    assert safe_warning_message("safe\r\ntext", fallback_message=FALLBACK) == "safe\ntext"


def test_safe_warnings_preserve_safe_warning_messages() -> None:
    payload = {"warnings": [{"code": "synthetic_warning", "message": "Synthetic safe warning."}]}

    for safe_warnings, _fallback in ADAPTER_WARNING_HELPERS:
        assert safe_warnings(payload) == [
            {"code": "synthetic_warning", "message": "Synthetic safe warning."}
        ]


def test_safe_warnings_redact_path_bearing_warning_messages() -> None:
    payload = {
        "warnings": [
            {
                "code": "synthetic_warning",
                "message": "permission denied for /Users/synthetic/Library/Mail/Envelope Index",
            }
        ]
    }

    for safe_warnings, fallback in ADAPTER_WARNING_HELPERS:
        warnings = safe_warnings(payload)

        assert warnings == [{"code": "synthetic_warning", "message": fallback}]
        assert "/Users/" not in str(warnings)
        assert "permission denied" not in str(warnings)


def test_safe_warnings_handle_mixed_and_malformed_warning_entries() -> None:
    payload = {
        "warnings": [
            {"code": "safe_warning", "message": "Synthetic safe warning."},
            {"code": "unsafe_warning", "message": "Failed for synthetic@example.invalid."},
            "not-a-warning",
            {"code": "missing-message"},
            {"message": "missing code"},
            {"code": "non-string-message", "message": 123},
        ]
    }

    for safe_warnings, fallback in ADAPTER_WARNING_HELPERS:
        assert safe_warnings(payload) == [
            {"code": "safe_warning", "message": "Synthetic safe warning."},
            {"code": "unsafe_warning", "message": fallback},
        ]


def test_safe_warnings_accept_missing_or_non_list_warnings() -> None:
    for safe_warnings, _fallback in ADAPTER_WARNING_HELPERS:
        assert safe_warnings({}) == []
        assert safe_warnings({"warnings": "not-a-list"}) == []

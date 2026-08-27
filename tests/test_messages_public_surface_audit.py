from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_messages_public_surface.py"
SPEC = importlib.util.spec_from_file_location("audit_messages_public_surface", SCRIPT_PATH)
assert SPEC is not None
audit_messages_public_surface = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_messages_public_surface"] = audit_messages_public_surface
SPEC.loader.exec_module(audit_messages_public_surface)


CURRENT_LIKE_SDEF = """\
<?xml version="1.0" encoding="UTF-8"?>
<dictionary>
  <suite name="Messages Suite">
    <command name="send">
      <direct-parameter>
        <type type="file"/>
        <type type="text"/>
      </direct-parameter>
      <parameter name="to">
        <type type="participant"/>
        <type type="chat"/>
      </parameter>
    </command>
    <command name="login"/>
    <command name="logout"/>
    <class-extension extends="application">
      <element type="participant" access="r"/>
      <element type="account" access="r"/>
      <element type="file transfer" access="r"/>
      <element type="chat" access="r"/>
    </class-extension>
    <class name="participant">
      <property name="id" access="r"/>
      <property name="handle" access="r"/>
    </class>
    <class name="account">
      <property name="enabled"/>
      <element type="chat" access="r"/>
      <element type="participant" access="r"/>
    </class>
    <class name="chat">
      <property name="id" access="r"/>
      <element type="participant" access="r"/>
    </class>
    <class name="file transfer">
      <property name="file path" access="r"/>
    </class>
  </suite>
</dictionary>
"""


def test_current_project_messages_public_surface_audit_passes() -> None:
    payload = audit_messages_public_surface.audit_messages_public_surface()

    assert payload["status"] == "ok"
    assert payload["messages_public_surface_reviewed"] is True
    assert payload["commands"] == ["login", "logout", "send"]
    assert payload["send_direct_types"] == ["file", "text"]
    assert payload["send_target_types"] == ["chat", "participant"]
    assert payload["finding_count"] == 0
    assert "message delete" in payload["blocked_risky_operations"]
    assert "account.enabled" in payload["known_non_readonly_properties"]


def test_messages_public_surface_audit_accepts_current_like_sdef(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(CURRENT_LIKE_SDEF, encoding="utf-8")

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "ok"
    assert payload["commands"] == ["login", "logout", "send"]
    assert payload["read_only_elements"] == [
        {"access": "r", "owner": "account", "type": "chat"},
        {"access": "r", "owner": "account", "type": "participant"},
        {"access": "r", "owner": "application", "type": "account"},
        {"access": "r", "owner": "application", "type": "chat"},
        {"access": "r", "owner": "application", "type": "file transfer"},
        {"access": "r", "owner": "application", "type": "participant"},
        {"access": "r", "owner": "chat", "type": "participant"},
    ]


def test_messages_public_surface_audit_fails_on_unreviewed_command(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(
        CURRENT_LIKE_SDEF.replace('<command name="logout"/>', '<command name="delete"/>'),
        encoding="utf-8",
    )

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "error"
    assert _finding(payload, "messages_expected_command_missing", "logout")
    assert _finding(payload, "messages_unreviewed_public_command", "delete")
    assert _finding(payload, "messages_risky_public_command", "delete")


def test_messages_public_surface_audit_fails_on_extra_risky_command(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(
        CURRENT_LIKE_SDEF.replace(
            '<command name="logout"/>',
            '<command name="logout"/>\n    <command name="mark read"/>',
        ),
        encoding="utf-8",
    )

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "error"
    assert _finding(payload, "messages_unreviewed_public_command", "mark read")
    assert _finding(payload, "messages_risky_public_command", "mark read")


def test_messages_public_surface_audit_fails_on_camel_risky_command(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(
        CURRENT_LIKE_SDEF.replace(
            '<command name="logout"/>',
            '<command name="logout"/>\n    <command name="deleteMessage"/>',
        ),
        encoding="utf-8",
    )

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "error"
    assert _finding(payload, "messages_unreviewed_public_command", "deleteMessage")
    assert _finding(payload, "messages_risky_public_command", "deleteMessage")


def test_messages_public_surface_audit_fails_on_send_signature_drift(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(CURRENT_LIKE_SDEF.replace('<type type="chat"/>', ""), encoding="utf-8")

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "error"
    assert _finding(payload, "messages_send_signature_changed", "send")


def test_messages_public_surface_audit_fails_on_unreviewed_writable_property(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(
        CURRENT_LIKE_SDEF.replace(
            '<property name="id" access="r"/>',
            '<property name="read status"/>',
            1,
        ),
        encoding="utf-8",
    )

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "error"
    assert _finding(payload, "messages_unreviewed_non_readonly_property", "participant.read status")


def test_messages_public_surface_audit_fails_on_class_extension_writable_property(tmp_path: Path) -> None:
    path = tmp_path / "Messages.sdef"
    path.write_text(
        CURRENT_LIKE_SDEF.replace(
            '<element type="participant" access="r"/>',
            '<property name="frontmost"/>\n      <element type="participant" access="r"/>',
            1,
        ),
        encoding="utf-8",
    )

    payload = audit_messages_public_surface.audit_messages_public_surface(path)

    assert payload["status"] == "error"
    assert _finding(payload, "messages_unreviewed_non_readonly_property", "application.frontmost")


def _finding(payload: dict, kind: str, name: str) -> bool:
    return any(
        finding["kind"] == kind and finding["name"] == name
        for finding in payload["findings"]
    )

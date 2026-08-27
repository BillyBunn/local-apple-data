#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MESSAGES_SDEF = Path(
    "/System/Applications/Messages.app/Contents/Resources/Messages.sdef"
)
EXPECTED_COMMANDS = frozenset({"send", "login", "logout"})
RISKY_COMMAND_TERMS = frozenset(
    {
        "create",
        "delete",
        "edit",
        "make",
        "mark",
        "move",
        "new",
        "react",
        "reaction",
        "read",
        "reply",
        "tapback",
        "unsend",
    }
)
KNOWN_NON_READONLY_PROPERTIES = frozenset({("account", "enabled")})
BLOCKED_RISKY_OPERATIONS = (
    "direct-recipient send",
    "new-chat creation",
    "SMS/RCS/iMessage fallback selection",
    "outgoing-account selection",
    "message edit",
    "message unsend",
    "message delete",
    "reaction/tapback",
    "mark read",
    "group management",
)


@dataclass(frozen=True)
class Finding:
    kind: str
    name: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"kind": self.kind, "name": self.name, "message": self.message}


def audit_messages_public_surface(
    sdef_path: Path = DEFAULT_MESSAGES_SDEF,
) -> dict[str, Any]:
    path = sdef_path.expanduser()
    findings: list[Finding] = []

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        findings.append(
            Finding("messages_sdef_parse_error", path.as_posix(), type(exc).__name__)
        )
        return _payload(path, findings=findings)
    except OSError as exc:
        findings.append(
            Finding("messages_sdef_unreadable", path.as_posix(), type(exc).__name__)
        )
        return _payload(path, findings=findings)

    commands = sorted(
        _attr(command, "name")
        for command in root.findall(".//command")
        if _attr(command, "name")
    )
    command_set = set(commands)
    if command_set != EXPECTED_COMMANDS:
        missing = sorted(EXPECTED_COMMANDS - command_set)
        unexpected = sorted(command_set - EXPECTED_COMMANDS)
        if missing:
            findings.append(
                Finding(
                    "messages_expected_command_missing",
                    ",".join(missing),
                    "Messages public scripting commands changed; source review is stale.",
                )
            )
        if unexpected:
            findings.append(
                Finding(
                    "messages_unreviewed_public_command",
                    ",".join(unexpected),
                    "Messages exposes an unreviewed public scripting command.",
                )
            )

    risky_commands = [
        name for name in commands if any(term in _normalized(name) for term in RISKY_COMMAND_TERMS)
    ]
    if risky_commands:
        findings.append(
            Finding(
                "messages_risky_public_command",
                ",".join(risky_commands),
                "Messages exposes a command that may change risky mutation status.",
            )
        )

    send = next(
        (
            command
            for command in root.findall(".//command")
            if _attr(command, "name") == "send"
        ),
        None,
    )
    send_direct_types = _send_direct_types(send)
    send_target_types = _send_target_types(send)
    if send_direct_types != ["file", "text"] or send_target_types != ["chat", "participant"]:
        findings.append(
            Finding(
                "messages_send_signature_changed",
                "send",
                "Messages send command signature no longer matches the reviewed surface.",
            )
        )

    class_names = sorted(
        _attr(cls, "name") for cls in root.findall(".//class") if _attr(cls, "name")
    )
    element_access = _element_access(root)
    non_readonly_elements = [
        item for item in element_access if item["access"] not in {"r", "read-only"}
    ]
    if non_readonly_elements:
        findings.append(
            Finding(
                "messages_non_readonly_element",
                ",".join(
                    f"{item['owner']}.{item['type']}" for item in non_readonly_elements
                ),
                "Messages exposes non-read-only elements; source review must be updated.",
            )
        )

    property_access = _property_access(root)
    non_readonly_properties = [
        item
        for item in property_access
        if item["access"] not in {"r", "read-only"}
        and (item["owner"], item["name"]) not in KNOWN_NON_READONLY_PROPERTIES
    ]
    if non_readonly_properties:
        findings.append(
            Finding(
                "messages_unreviewed_non_readonly_property",
                ",".join(
                    f"{item['owner']}.{item['name']}" for item in non_readonly_properties
                ),
                "Messages exposes an unreviewed writable property.",
            )
        )

    payload = _payload(
        path,
        findings=findings,
        commands=commands,
        class_names=class_names,
        send_direct_types=send_direct_types,
        send_target_types=send_target_types,
        read_only_elements=element_access,
        known_non_readonly_properties=[
            f"{owner}.{name}" for owner, name in sorted(KNOWN_NON_READONLY_PROPERTIES)
        ],
    )
    return payload


def _payload(
    path: Path,
    *,
    findings: list[Finding],
    commands: list[str] | None = None,
    class_names: list[str] | None = None,
    send_direct_types: list[str] | None = None,
    send_target_types: list[str] | None = None,
    read_only_elements: list[dict[str, str]] | None = None,
    known_non_readonly_properties: list[str] | None = None,
) -> dict[str, Any]:
    status = "error" if findings else "ok"
    return {
        "status": status,
        "messages_public_surface_reviewed": status == "ok",
        "sdef_path": path.as_posix(),
        "commands": commands or [],
        "expected_commands": sorted(EXPECTED_COMMANDS),
        "classes": class_names or [],
        "send_direct_types": send_direct_types or [],
        "send_target_types": send_target_types or [],
        "read_only_elements": read_only_elements or [],
        "known_non_readonly_properties": known_non_readonly_properties or [],
        "blocked_risky_operations": list(BLOCKED_RISKY_OPERATIONS),
        "finding_count": len(findings),
        "findings": [finding.to_json() for finding in findings],
    }


def _send_direct_types(command: ET.Element | None) -> list[str]:
    if command is None:
        return []
    parameter = command.find("direct-parameter")
    if parameter is None:
        return []
    return sorted(
        _attr(type_node, "type")
        for type_node in parameter.findall("type")
        if _attr(type_node, "type")
    )


def _send_target_types(command: ET.Element | None) -> list[str]:
    if command is None:
        return []
    target = next(
        (
            parameter
            for parameter in command.findall("parameter")
            if _attr(parameter, "name") == "to"
        ),
        None,
    )
    if target is None:
        return []
    return sorted(
        _attr(type_node, "type")
        for type_node in target.findall("type")
        if _attr(type_node, "type")
    )


def _element_access(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for owner in list(root.findall(".//class")) + list(root.findall(".//class-extension")):
        owner_name = _attr(owner, "name") or _attr(owner, "extends") or "<unknown>"
        for element in owner.findall("element"):
            rows.append(
                {
                    "owner": owner_name,
                    "type": _attr(element, "type") or "<unknown>",
                    "access": _attr(element, "access") or "",
                }
            )
    return sorted(rows, key=lambda item: (item["owner"], item["type"], item["access"]))


def _property_access(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for owner in list(root.findall(".//class")) + list(root.findall(".//class-extension")):
        owner_name = _attr(owner, "name") or _attr(owner, "extends") or "<unknown>"
        for prop in owner.findall("property"):
            rows.append(
                {
                    "owner": owner_name,
                    "name": _attr(prop, "name") or "<unknown>",
                    "access": _attr(prop, "access") or "",
                }
            )
    return sorted(rows, key=lambda item: (item["owner"], item["name"], item["access"]))


def _normalized(value: str) -> str:
    return value.lower().replace("-", " ").replace("_", " ")


def _attr(element: ET.Element, name: str) -> str:
    value = element.attrib.get(name, "")
    return value.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the public Messages scripting surface for risky mutation drift."
    )
    parser.add_argument(
        "--sdef-path",
        type=Path,
        default=DEFAULT_MESSAGES_SDEF,
        help="Path to Messages.sdef. Defaults to the system Messages application bundle.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON. Default is JSON.")
    args = parser.parse_args(argv)

    payload = audit_messages_public_surface(args.sdef_path)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

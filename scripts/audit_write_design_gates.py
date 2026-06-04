#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_mutation_gates import audit_mutation_gates


APPROVED_WRITE_TOOLS: tuple[str, ...] = (
    "icloud_drive_apply",
    "icloud_drive_apply_change",
    "reminders_apply",
    "reminders_apply_change",
)
APPROVED_PREVIEW_TOOLS: tuple[str, ...] = (
    "icloud_drive_plan",
    "icloud_drive_plan_change",
    "reminders_plan_change",
)
REQUIRED_MUTATION_GATE_TEXT = {
    "README.md": "The only apply-capable mutation surfaces are Reminders apply and iCloud Drive create-text apply",
    "docs/MUTATION_GATES.md": "Approved write tools: `reminders apply`, `reminders_apply_change`, `icloud-drive apply`, and `icloud_drive_apply_change`",
    "docs/WRITE_TOOL_ROADMAP.md": "Reminders apply and iCloud Drive create-text apply are the only approved write surfaces",
}
REQUIRED_DESIGN_DOCS = {
    "reminders_write_v1": {
        "path": "docs/V1_11_REMINDERS_WRITE_DESIGN.md",
        "phrases": (
            "Status: Apply-capable implementation.",
            "Approved write tools: `local-apple-data reminders apply` and `reminders_apply_change`.",
            "`local-apple-data reminders plan` and `reminders_plan_change`",
            "No other mutating CLI or MCP tools are approved or exposed by this document.",
            "preview",
            "apply",
            "read_back",
            "mutation_applied:false",
            "approval token",
            "EventKit",
            "exact opaque `reminders:reminder:eventkit:v1:` handle",
            "idempotency",
            "redaction",
            "Synthetic Tests Required",
            "This document allows only this Reminders apply surface.",
        ),
    },
    "icloud_drive_write_v1": {
        "path": "docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md",
        "phrases": (
            "Status: Apply-capable implementation.",
            "Approved write tools: `local-apple-data icloud-drive apply` and `icloud_drive_apply_change`.",
            "`local-apple-data icloud-drive plan` and `icloud_drive_plan_change`",
            "No other mutating CLI or MCP tools are approved or exposed by this document.",
            "preview",
            "apply",
            "read_back",
            "mutation_applied:false",
            "approval token",
            "exact opaque `icloud:file:v1:` parent folder handle",
            "exclusive create",
            "idempotency",
            "redaction",
            "Synthetic Tests Required",
            "The current release allows only this iCloud Drive create-text apply surface.",
        ),
    },
}
WRITE_PHASE_TERMS = {"apply", "preview", "write"}


@dataclass(frozen=True)
class Finding:
    kind: str
    path: Path
    line: int
    name: str
    message: str

    def to_json(self, root: Path) -> dict[str, Any]:
        try:
            relative = self.path.relative_to(root)
        except ValueError:
            relative = self.path
        return {
            "kind": self.kind,
            "path": relative.as_posix(),
            "line": self.line,
            "name": self.name,
            "message": self.message,
        }


@dataclass(frozen=True)
class ExposedName:
    name: str
    path: Path
    line: int


def audit_write_design_gates(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    findings: list[Finding] = []

    design_docs_checked = _check_design_docs(root, findings)
    _check_mutation_contract(root, findings)
    _check_no_write_phase_tools(root, findings)
    _check_mutation_gate(root, findings)

    return {
        "approved_preview_tools": list(APPROVED_PREVIEW_TOOLS),
        "approved_write_tools": list(APPROVED_WRITE_TOOLS),
        "design_docs_checked": design_docs_checked,
        "findings": [finding.to_json(root) for finding in findings],
        "status": "ok" if not findings else "error",
        "write_design_gate": not findings,
    }


def _check_design_docs(root: Path, findings: list[Finding]) -> int:
    checked = 0
    for name, contract in REQUIRED_DESIGN_DOCS.items():
        relative = str(contract["path"])
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                Finding(
                    "write_design_doc_missing",
                    path,
                    0,
                    name,
                    f"Required write design doc is unreadable: {type(exc).__name__}",
                )
            )
            continue

        checked += 1
        for phrase in contract["phrases"]:
            if phrase in text:
                continue
            findings.append(
                Finding(
                    "write_design_doc_contract_missing",
                    path,
                    0,
                    name,
                    f"Missing required design-gate text: {phrase}",
                )
            )
    return checked


def _check_mutation_contract(root: Path, findings: list[Finding]) -> None:
    for relative, required_text in REQUIRED_MUTATION_GATE_TEXT.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                Finding(
                    "read_only_contract_missing",
                    path,
                    0,
                    relative,
                    f"Required mutation-gate contract file is unreadable: {type(exc).__name__}",
                )
            )
            continue
        if required_text not in text:
            findings.append(
                Finding(
                    "read_only_contract_missing",
                    path,
                    0,
                    relative,
                    f"Missing required mutation-gate contract text: {required_text}",
                )
            )


def _check_no_write_phase_tools(root: Path, findings: list[Finding]) -> None:
    for exposed in _mcp_tools(root / "src/local_apple_data/mcp_server.py", findings):
        terms = _write_phase_terms(exposed.name)
        if terms and exposed.name not in APPROVED_WRITE_TOOLS:
            findings.append(
                Finding(
                    "write_phase_mcp_tool",
                    exposed.path,
                    exposed.line,
                    exposed.name,
                    f"Exposed MCP tool name contains write-design term(s): {', '.join(terms)}",
                )
            )

    for exposed in _cli_handlers(root / "src/local_apple_data/cli.py", findings):
        name = exposed.name.removesuffix("_command").removeprefix("_")
        terms = _write_phase_terms(name)
        if terms and name not in APPROVED_WRITE_TOOLS:
            findings.append(
                Finding(
                    "write_phase_cli_handler",
                    exposed.path,
                    exposed.line,
                    exposed.name,
                    f"Exposed CLI handler contains write-design term(s): {', '.join(terms)}",
                )
            )


def _check_mutation_gate(root: Path, findings: list[Finding]) -> None:
    payload = audit_mutation_gates(root)
    if payload["status"] == "ok":
        return
    first = payload["findings"][0] if payload["findings"] else {}
    findings.append(
        Finding(
            "mutation_gate_failed",
            root / str(first.get("path", "scripts/audit_mutation_gates.py")),
            int(first.get("line", 0) or 0),
            str(first.get("name", "mutation_gate")),
            "Mutation-gate audit must pass before write design gates can pass.",
        )
    )


def _mcp_tools(path: Path, findings: list[Finding]) -> list[ExposedName]:
    tree = _parse_python(path, findings)
    if tree is None:
        return []
    tools: list[ExposedName] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if _mcp_tool_decorator(node.decorator_list) is None:
            continue
        tools.append(ExposedName(name=node.name, path=path, line=node.lineno))
    return tools


def _cli_handlers(path: Path, findings: list[Finding]) -> list[ExposedName]:
    tree = _parse_python(path, findings)
    if tree is None:
        return []
    handlers: list[ExposedName] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_") and node.name.endswith("_command"):
            handlers.append(ExposedName(name=node.name, path=path, line=node.lineno))
    return handlers


def _parse_python(path: Path, findings: list[Finding]) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except OSError as exc:
        findings.append(
            Finding(
                "source_unreadable",
                path,
                0,
                path.name,
                f"Could not read source file: {type(exc).__name__}",
            )
        )
    except SyntaxError as exc:
        findings.append(
            Finding(
                "source_syntax_error",
                path,
                exc.lineno or 0,
                path.name,
                "Could not parse source file.",
            )
        )
    return None


def _mcp_tool_decorator(decorators: Iterable[ast.expr]) -> ast.Call | None:
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "tool"
            and isinstance(func.value, ast.Name)
            and func.value.id == "mcp"
        ):
            return decorator
    return None


def _write_phase_terms(name: str) -> list[str]:
    lowered = name.casefold()
    tokens = {token for token in re.split(r"[^A-Za-z0-9]+", lowered) if token}
    terms = set(tokens & WRITE_PHASE_TERMS)
    if "read_back" in lowered or "readback" in lowered:
        terms.add("read_back")
    return sorted(terms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit that write-tool design docs are present while current CLI/MCP surfaces stay read-only."
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    payload = audit_write_design_gates(Path(args.project_root))
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "write design gate audit: "
            f"status={payload['status']} "
            f"design_docs={payload['design_docs_checked']} "
            f"approved_write_tools={len(payload['approved_write_tools'])}"
        )
        for finding in payload["findings"]:
            print(
                f"- {finding['kind']}: {finding['path']}:{finding['line']}: "
                f"{finding['name']}: {finding['message']}"
            )
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

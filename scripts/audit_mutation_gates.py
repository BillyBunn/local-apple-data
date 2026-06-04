#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]

MUTATION_VERBS = {
    "add",
    "append",
    "apply",
    "archive",
    "complete",
    "create",
    "delete",
    "draft",
    "edit",
    "flag",
    "import",
    "mark",
    "move",
    "remove",
    "save",
    "send",
    "uncomplete",
    "update",
    "write",
}
APPROVED_WRITE_MCP_TOOLS = {"icloud_drive_apply_change", "reminders_apply_change"}
APPROVED_WRITE_CLI_HANDLERS = {"icloud_drive_apply", "reminders_apply"}
MANIFEST_WRITE_CAPABILITIES = {
    "Create",
    "Delete",
    "Edit",
    "Manage",
    "Mutate",
    "Send",
    "Update",
    "Write",
}
REQUIRED_MUTATION_GATE_TEXT = {
    "README.md": "The only apply-capable mutation surfaces are Reminders apply and iCloud Drive create-text apply",
    "docs/MUTATION_GATES.md": "Approved write tools: `reminders apply`, `reminders_apply_change`, `icloud-drive apply`, and `icloud_drive_apply_change`",
    "docs/WRITE_TOOL_ROADMAP.md": "Reminders apply and iCloud Drive create-text apply are the only approved write surfaces",
    "src/local_apple_data/mcp_server.py": "The only apply-capable mutation surfaces are Reminders apply and iCloud Drive create-text apply",
}


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
    read_only_annotations: bool = True
    write_annotations: bool = False


def audit_mutation_gates(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    findings: list[Finding] = []
    mcp_tools = _mcp_tools(root / "src/local_apple_data/mcp_server.py", findings)
    cli_handlers = _cli_handlers(root / "src/local_apple_data/cli.py", findings)

    for tool in mcp_tools:
        approved_write = tool.name in APPROVED_WRITE_MCP_TOOLS
        terms = _mutation_terms(tool.name)
        if terms and not approved_write:
            findings.append(
                Finding(
                    "mutation_like_mcp_tool",
                    tool.path,
                    tool.line,
                    tool.name,
                    f"Exposed MCP tool name contains mutation verb(s): {', '.join(terms)}",
                )
            )
        if approved_write and not tool.write_annotations:
            findings.append(
                Finding(
                    "approved_write_mcp_tool_annotation",
                    tool.path,
                    tool.line,
                    tool.name,
                    "Approved MCP write tool must use WRITE_ANNOTATIONS.",
                )
            )
        if not approved_write and not tool.read_only_annotations:
            findings.append(
                Finding(
                    "mcp_tool_not_read_only",
                    tool.path,
                    tool.line,
                    tool.name,
                    "MCP tool is not annotated with READ_ONLY_ANNOTATIONS.",
                )
            )

    for handler in cli_handlers:
        exposed_name = handler.name.removesuffix("_command").removeprefix("_")
        approved_write = exposed_name in APPROVED_WRITE_CLI_HANDLERS
        terms = _mutation_terms(exposed_name)
        if terms and not approved_write:
            findings.append(
                Finding(
                    "mutation_like_cli_handler",
                    handler.path,
                    handler.line,
                    handler.name,
                    f"Exposed CLI command handler contains mutation verb(s): {', '.join(terms)}",
                )
            )

    findings.extend(_mutation_contract_findings(root))
    findings.extend(_plugin_manifest_findings(root))

    return {
        "cli_handlers_checked": len(cli_handlers),
        "findings": [finding.to_json(root) for finding in findings],
        "mcp_tools_checked": len(mcp_tools),
        "mutation_verbs": sorted(MUTATION_VERBS),
        "approved_write_tools": sorted(APPROVED_WRITE_MCP_TOOLS),
        "read_only": not APPROVED_WRITE_MCP_TOOLS and not findings,
        "status": "ok" if not findings else "error",
    }


def _mcp_tools(path: Path, findings: list[Finding]) -> list[ExposedName]:
    tree = _parse_python(path, findings)
    if tree is None:
        return []
    tools: list[ExposedName] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorator = _mcp_tool_decorator(node.decorator_list)
        if decorator is None:
            continue
        tools.append(
            ExposedName(
                name=node.name,
                path=path,
                line=node.lineno,
                read_only_annotations=_uses_read_only_annotations(decorator),
                write_annotations=_uses_write_annotations(decorator),
            )
        )
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


def _uses_read_only_annotations(decorator: ast.Call) -> bool:
    return _annotation_name(decorator) == "READ_ONLY_ANNOTATIONS"


def _uses_write_annotations(decorator: ast.Call) -> bool:
    return _annotation_name(decorator) == "WRITE_ANNOTATIONS"


def _annotation_name(decorator: ast.Call) -> str | None:
    for keyword in decorator.keywords:
        if keyword.arg != "annotations":
            continue
        if isinstance(keyword.value, ast.Name):
            return keyword.value.id
        return None
    return None


def _mutation_terms(name: str) -> list[str]:
    tokens = {token for token in re.split(r"[^A-Za-z0-9]+", name.casefold()) if token}
    return sorted(tokens & MUTATION_VERBS)


def _mutation_contract_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
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
    return findings


def _plugin_manifest_findings(root: Path) -> list[Finding]:
    path = root / ".codex-plugin/plugin.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Finding(
                "plugin_manifest_unreadable",
                path,
                0,
                "plugin.json",
                f"Could not read plugin manifest: {type(exc).__name__}",
            )
        ]

    capabilities = set(manifest.get("interface", {}).get("capabilities", []))
    write_capabilities = sorted(capabilities & MANIFEST_WRITE_CAPABILITIES)
    if not write_capabilities or APPROVED_WRITE_MCP_TOOLS:
        return []
    return [
        Finding(
            "plugin_manifest_write_capability",
            path,
            0,
            "interface.capabilities",
            f"Manifest exposes write capability without mutation gate audit support: {', '.join(write_capabilities)}",
        )
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit that public CLI/MCP surfaces remain read-only until mutation gates are approved."
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    payload = audit_mutation_gates(Path(args.project_root))
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "mutation gate audit: "
            f"status={payload['status']} "
            f"mcp_tools={payload['mcp_tools_checked']} "
            f"cli_handlers={payload['cli_handlers_checked']}"
        )
        for finding in payload["findings"]:
            print(
                f"- {finding['kind']}: {finding['path']}:{finding['line']}: "
                f"{finding['name']}: {finding['message']}"
            )
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

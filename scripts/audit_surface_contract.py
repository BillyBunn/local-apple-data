#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CORE_MCP_TOOLS = ("apple_data_health", "apple_data_doctor")
CORE_CLI_COMMANDS = ("health", "doctor")


@dataclass(frozen=True)
class SurfaceContract:
    name: str
    label: str
    cli_group: str
    cli_subparser: str
    cli_commands: tuple[str, ...]
    mcp_tools: tuple[str, ...]


SURFACE_CONTRACTS = (
    SurfaceContract(
        name="mail",
        label="Mail",
        cli_group="mail",
        cli_subparser="mail_subparsers",
        cli_commands=("search", "get", "content"),
        mcp_tools=("mail_search", "mail_get_metadata", "mail_get_content"),
    ),
    SurfaceContract(
        name="messages",
        label="Messages",
        cli_group="messages",
        cli_subparser="messages_subparsers",
        cli_commands=("search", "get"),
        mcp_tools=("messages_search", "messages_get_chat"),
    ),
    SurfaceContract(
        name="hide_my_email",
        label="Hide My Email",
        cli_group="hide-my-email",
        cli_subparser="hide_my_email_subparsers",
        cli_commands=("search", "get"),
        mcp_tools=("hide_my_email_search", "hide_my_email_get_alias"),
    ),
    SurfaceContract(
        name="voice_memos",
        label="Voice Memos",
        cli_group="voice-memos",
        cli_subparser="voice_memos_subparsers",
        cli_commands=("search", "get", "export"),
        mcp_tools=(
            "voice_memos_search",
            "voice_memos_get_recording",
            "voice_memos_export_audio",
        ),
    ),
    SurfaceContract(
        name="notes",
        label="Notes",
        cli_group="notes",
        cli_subparser="notes_subparsers",
        cli_commands=("search", "get", "content"),
        mcp_tools=("notes_search", "notes_get_metadata", "notes_get_content"),
    ),
    SurfaceContract(
        name="icloud_drive",
        label="iCloud Drive",
        cli_group="icloud-drive",
        cli_subparser="icloud_drive_subparsers",
        cli_commands=("search", "get", "content", "plan", "apply"),
        mcp_tools=(
            "icloud_drive_search",
            "icloud_drive_get_metadata",
            "icloud_drive_get_content",
            "icloud_drive_plan_change",
            "icloud_drive_apply_change",
        ),
    ),
    SurfaceContract(
        name="calendar",
        label="Calendar",
        cli_group="calendar",
        cli_subparser="calendar_subparsers",
        cli_commands=("search", "get", "plan", "apply"),
        mcp_tools=(
            "calendar_search",
            "calendar_get_event",
            "calendar_plan_change",
            "calendar_apply_change",
        ),
    ),
    SurfaceContract(
        name="reminders",
        label="Reminders",
        cli_group="reminders",
        cli_subparser="reminders_subparsers",
        cli_commands=("search", "due", "eventkit-search", "content", "plan", "apply"),
        mcp_tools=(
            "reminders_search",
            "reminders_due",
            "reminders_eventkit_search",
            "reminders_get_content",
            "reminders_plan_change",
            "reminders_apply_change",
        ),
    ),
    SurfaceContract(
        name="contacts",
        label="Contacts",
        cli_group="contacts",
        cli_subparser="contacts_subparsers",
        cli_commands=("search", "get", "plan", "apply"),
        mcp_tools=(
            "contacts_search",
            "contacts_get",
            "contacts_plan_change",
            "contacts_apply_change",
        ),
    ),
    SurfaceContract(
        name="photos",
        label="Photos",
        cli_group="photos",
        cli_subparser="photos_subparsers",
        cli_commands=("search", "get", "export"),
        mcp_tools=("photos_search", "photos_get_asset", "photos_export_asset"),
    ),
)


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
class CliParsers:
    top_level: dict[str, int]
    commands_by_owner: dict[str, dict[str, int]]


def audit_surface_contract(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    findings: list[Finding] = []

    mcp_path = root / "src/local_apple_data/mcp_server.py"
    cli_path = root / "src/local_apple_data/cli.py"
    health_path = root / "src/local_apple_data/health.py"
    matrix_path = root / "docs/CAPABILITY_MATRIX.md"

    mcp_tools = _mcp_tool_names(mcp_path, findings)
    cli_parsers = _cli_parsers(cli_path, findings)
    health_summary_surfaces = _health_summary_surfaces(health_path, findings)
    access_surfaces = _access_requirement_surfaces(health_path, findings)
    matrix_labels = _capability_matrix_labels(matrix_path, findings)

    expected_mcp_tools = set(CORE_MCP_TOOLS)
    expected_top_level_cli = set(CORE_CLI_COMMANDS)
    expected_surface_names = {contract.name for contract in SURFACE_CONTRACTS}
    expected_matrix_labels = {contract.label for contract in SURFACE_CONTRACTS}
    expected_cli_commands = sum(
        len(contract.cli_commands) for contract in SURFACE_CONTRACTS
    ) + len(CORE_CLI_COMMANDS)

    for contract in SURFACE_CONTRACTS:
        expected_mcp_tools.update(contract.mcp_tools)
        expected_top_level_cli.add(contract.cli_group)
        _require_matrix_label(contract, matrix_labels, matrix_path, findings)
        _require_health_surface(contract, health_summary_surfaces, health_path, findings)
        _require_access_surface(contract, access_surfaces, health_path, findings)
        _require_cli_group(contract, cli_parsers, cli_path, findings)
        for command in contract.cli_commands:
            _require_cli_command(contract, command, cli_parsers, cli_path, findings)
        for tool in contract.mcp_tools:
            _require_mcp_tool(tool, mcp_tools, mcp_path, findings)

    for tool in CORE_MCP_TOOLS:
        _require_mcp_tool(tool, mcp_tools, mcp_path, findings)
    for command in CORE_CLI_COMMANDS:
        if command not in cli_parsers.top_level:
            findings.append(
                Finding(
                    "missing_core_cli_command",
                    cli_path,
                    0,
                    command,
                    f"Top-level CLI command is missing: {command}",
                )
            )

    for tool in sorted(set(mcp_tools) - expected_mcp_tools):
        findings.append(
            Finding(
                "unexpected_mcp_tool",
                mcp_path,
                mcp_tools[tool],
                tool,
                "MCP tool is not covered by the public surface contract.",
            )
        )
    for command in sorted(set(cli_parsers.top_level) - expected_top_level_cli):
        findings.append(
            Finding(
                "unexpected_cli_group",
                cli_path,
                cli_parsers.top_level[command],
                command,
                "Top-level CLI parser is not covered by the public surface contract.",
            )
        )
    for label in sorted(set(matrix_labels) - expected_matrix_labels):
        findings.append(
            Finding(
                "unexpected_capability_matrix_row",
                matrix_path,
                matrix_labels[label],
                label,
                "Capability matrix row is not covered by the public surface contract.",
            )
        )
    for surface in sorted(health_summary_surfaces - expected_surface_names):
        findings.append(
            Finding(
                "unexpected_health_surface",
                health_path,
                0,
                surface,
                "Health surface is not covered by the public surface contract.",
            )
        )
    for surface in sorted(access_surfaces - expected_surface_names):
        findings.append(
            Finding(
                "unexpected_access_requirement_surface",
                health_path,
                0,
                surface,
                "Access requirement surface is not covered by the public surface contract.",
            )
        )

    return {
        "access_requirements_checked": len(access_surfaces),
        "capability_matrix_rows_checked": len(matrix_labels),
        "cli_commands_expected": expected_cli_commands,
        "cli_groups_checked": len(cli_parsers.top_level),
        "findings": [finding.to_json(root) for finding in findings],
        "health_surfaces_checked": len(health_summary_surfaces),
        "mcp_tools_checked": len(mcp_tools),
        "mcp_tools_expected": len(expected_mcp_tools),
        "status": "ok" if not findings else "error",
        "surfaces_checked": len(SURFACE_CONTRACTS),
    }


def _require_mcp_tool(
    tool: str,
    mcp_tools: dict[str, int],
    path: Path,
    findings: list[Finding],
) -> None:
    if tool in mcp_tools:
        return
    findings.append(
        Finding(
            "missing_mcp_tool",
            path,
            0,
            tool,
            f"MCP tool is missing from the public surface contract: {tool}",
        )
    )


def _require_cli_group(
    contract: SurfaceContract,
    cli_parsers: CliParsers,
    path: Path,
    findings: list[Finding],
) -> None:
    if contract.cli_group in cli_parsers.top_level:
        return
    findings.append(
        Finding(
            "missing_cli_group",
            path,
            0,
            contract.cli_group,
            f"CLI group is missing for surface {contract.name}.",
        )
    )


def _require_cli_command(
    contract: SurfaceContract,
    command: str,
    cli_parsers: CliParsers,
    path: Path,
    findings: list[Finding],
) -> None:
    commands = cli_parsers.commands_by_owner.get(contract.cli_subparser, {})
    if command in commands:
        return
    findings.append(
        Finding(
            "missing_cli_command",
            path,
            0,
            f"{contract.cli_group} {command}",
            f"CLI command is missing for surface {contract.name}: {command}",
        )
    )


def _require_matrix_label(
    contract: SurfaceContract,
    matrix_labels: dict[str, int],
    path: Path,
    findings: list[Finding],
) -> None:
    if contract.label in matrix_labels:
        return
    findings.append(
        Finding(
            "missing_capability_matrix_row",
            path,
            0,
            contract.label,
            f"Capability matrix row is missing for surface {contract.name}.",
        )
    )


def _require_health_surface(
    contract: SurfaceContract,
    health_surfaces: set[str],
    path: Path,
    findings: list[Finding],
) -> None:
    if contract.name in health_surfaces:
        return
    findings.append(
        Finding(
            "missing_health_surface",
            path,
            0,
            contract.name,
            f"Health summary is missing surface {contract.name}.",
        )
    )


def _require_access_surface(
    contract: SurfaceContract,
    access_surfaces: set[str],
    path: Path,
    findings: list[Finding],
) -> None:
    if contract.name in access_surfaces:
        return
    findings.append(
        Finding(
            "missing_access_requirement",
            path,
            0,
            contract.name,
            f"Health access requirements are missing surface {contract.name}.",
        )
    )


def _mcp_tool_names(path: Path, findings: list[Finding]) -> dict[str, int]:
    tree = _parse_python(path, findings)
    if tree is None:
        return {}
    tools: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if _mcp_tool_decorator(node.decorator_list) is not None:
            tools[node.name] = node.lineno
    return tools


def _cli_parsers(path: Path, findings: list[Finding]) -> CliParsers:
    tree = _parse_python(path, findings)
    if tree is None:
        return CliParsers(top_level={}, commands_by_owner={})

    top_level: dict[str, int] = {}
    commands_by_owner: dict[str, dict[str, int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_parser":
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
            continue
        owner = _call_owner_name(node.func.value)
        if owner == "subparsers":
            top_level[first_arg.value] = node.lineno
        elif owner and owner.endswith("_subparsers"):
            commands_by_owner.setdefault(owner, {})[first_arg.value] = node.lineno
    return CliParsers(top_level=top_level, commands_by_owner=commands_by_owner)


def _health_summary_surfaces(path: Path, findings: list[Finding]) -> set[str]:
    tree = _parse_python(path, findings)
    if tree is None:
        return set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_surface_summary":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Return) or not isinstance(child.value, ast.Dict):
                continue
            return _string_dict_keys(child.value)
    findings.append(
        Finding(
            "health_surface_summary_missing",
            path,
            0,
            "_surface_summary",
            "Health module is missing the normalized surface summary.",
        )
    )
    return set()


def _access_requirement_surfaces(path: Path, findings: list[Finding]) -> set[str]:
    tree = _parse_python(path, findings)
    if tree is None:
        return set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "ACCESS_REQUIREMENTS"
            for target in node.targets
        ):
            continue
        surfaces: set[str] = set()
        for child in ast.walk(node.value):
            if not isinstance(child, ast.Dict):
                continue
            surface = _dict_constant_value(child, "surface")
            if isinstance(surface, str):
                surfaces.add(surface)
        return surfaces
    findings.append(
        Finding(
            "access_requirements_missing",
            path,
            0,
            "ACCESS_REQUIREMENTS",
            "Health module is missing ACCESS_REQUIREMENTS.",
        )
    )
    return set()


def _capability_matrix_labels(path: Path, findings: list[Finding]) -> dict[str, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            Finding(
                "capability_matrix_unreadable",
                path,
                0,
                path.name,
                f"Could not read capability matrix: {type(exc).__name__}",
            )
        )
        return {}

    labels: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        label = cells[0]
        if not label or label == "Surface" or set(label) <= {"-", " "}:
            continue
        labels[label] = line_number
    return labels


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


def _call_owner_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_dict_keys(node: ast.Dict) -> set[str]:
    result: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            result.add(key.value)
    return result


def _dict_constant_value(node: ast.Dict, key_name: str) -> Any:
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or key.value != key_name:
            continue
        if isinstance(value, ast.Constant):
            return value.value
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit that public Apple data surfaces agree across MCP, CLI, health, and docs."
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    payload = audit_surface_contract(Path(args.project_root))
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "surface contract audit: "
            f"status={payload['status']} "
            f"surfaces={payload['surfaces_checked']} "
            f"mcp_tools={payload['mcp_tools_checked']}/{payload['mcp_tools_expected']} "
            f"cli_commands={payload['cli_commands_expected']}"
        )
        for finding in payload["findings"]:
            print(
                f"- {finding['kind']}: {finding['path']}:{finding['line']}: "
                f"{finding['name']}: {finding['message']}"
            )
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

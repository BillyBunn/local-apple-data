from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_surface_contract.py"
SPEC = importlib.util.spec_from_file_location("audit_surface_contract", SCRIPT_PATH)
assert SPEC is not None
audit_surface_contract = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_surface_contract"] = audit_surface_contract
SPEC.loader.exec_module(audit_surface_contract)


def test_current_project_surface_contract_passes() -> None:
    payload = audit_surface_contract.audit_surface_contract(
        Path(__file__).resolve().parents[1]
    )

    assert payload["status"] == "ok"
    assert payload["surfaces_checked"] == 12
    assert payload["mcp_tools_checked"] >= payload["mcp_tools_expected"]
    assert payload["capability_matrix_rows_checked"] == 12
    assert payload["findings"] == []


def test_surface_contract_flags_missing_mcp_tool(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, omit_mcp_tool="notes_get_content")

    payload = audit_surface_contract.audit_surface_contract(root)

    assert payload["status"] == "error"
    assert _finding(payload, "missing_mcp_tool", "notes_get_content")


def test_surface_contract_flags_missing_cli_command(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, omit_cli_command=("voice_memos", "export"))

    payload = audit_surface_contract.audit_surface_contract(root)

    assert payload["status"] == "error"
    assert _finding(payload, "missing_cli_command", "voice-memos export")


def test_surface_contract_flags_missing_capability_matrix_row(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, omit_matrix_label="Photos")

    payload = audit_surface_contract.audit_surface_contract(root)

    assert payload["status"] == "error"
    assert _finding(payload, "missing_capability_matrix_row", "Photos")


def test_surface_contract_flags_missing_health_surface(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, omit_health_surface="calendar")

    payload = audit_surface_contract.audit_surface_contract(root)

    assert payload["status"] == "error"
    assert _finding(payload, "missing_health_surface", "calendar")


def _finding(payload: dict, kind: str, name: str) -> bool:
    return any(
        finding["kind"] == kind and finding["name"] == name
        for finding in payload["findings"]
    )


def _minimal_project(
    tmp_path: Path,
    *,
    omit_mcp_tool: str = "",
    omit_cli_command: tuple[str, str] | None = None,
    omit_matrix_label: str = "",
    omit_health_surface: str = "",
) -> Path:
    root = tmp_path / "project"
    root.joinpath("src/local_apple_data").mkdir(parents=True)
    root.joinpath("docs").mkdir()
    _write_mcp_server(root, omit_mcp_tool=omit_mcp_tool)
    _write_cli(root, omit_cli_command=omit_cli_command)
    _write_health(root, omit_health_surface=omit_health_surface)
    _write_capability_matrix(root, omit_matrix_label=omit_matrix_label)
    return root


def _write_mcp_server(root: Path, *, omit_mcp_tool: str = "") -> None:
    tools = list(audit_surface_contract.CORE_MCP_TOOLS)
    for contract in audit_surface_contract.SURFACE_CONTRACTS:
        tools.extend(contract.mcp_tools)

    lines = [
        "from mcp.server.fastmcp import FastMCP",
        "READ_ONLY_ANNOTATIONS = object()",
        'mcp = FastMCP("local-apple-data")',
    ]
    for tool in tools:
        if tool == omit_mcp_tool:
            continue
        lines.extend(
            [
                "@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)",
                f"def {tool}() -> dict:",
                "    return {}",
                "",
            ]
        )
    root.joinpath("src/local_apple_data/mcp_server.py").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _write_cli(
    root: Path,
    *,
    omit_cli_command: tuple[str, str] | None = None,
) -> None:
    lines = [
        "def build_parser():",
        "    import argparse",
        "    parser = argparse.ArgumentParser()",
        "    subparsers = parser.add_subparsers()",
    ]
    for command in audit_surface_contract.CORE_CLI_COMMANDS:
        lines.append(f'    subparsers.add_parser("{command}")')
    for contract in audit_surface_contract.SURFACE_CONTRACTS:
        lines.extend(
            [
                f'    {contract.name} = subparsers.add_parser("{contract.cli_group}")',
                f"    {contract.cli_subparser} = {contract.name}.add_subparsers()",
            ]
        )
        for command in contract.cli_commands:
            if omit_cli_command == (contract.name, command):
                continue
            lines.append(f'    {contract.cli_subparser}.add_parser("{command}")')
    lines.append("    return parser")
    root.joinpath("src/local_apple_data/cli.py").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _write_health(root: Path, *, omit_health_surface: str = "") -> None:
    surfaces = [
        contract.name
        for contract in audit_surface_contract.SURFACE_CONTRACTS
        if contract.name != omit_health_surface
    ]
    access = ",\n".join(f'    {{"surface": "{surface}"}}' for surface in surfaces)
    summary = ",\n".join(f'        "{surface}": {{}}' for surface in surfaces)
    root.joinpath("src/local_apple_data/health.py").write_text(
        f"""
ACCESS_REQUIREMENTS = [
{access}
]


def _surface_summary():
    return {{
{summary}
    }}
""".lstrip(),
        encoding="utf-8",
    )


def _write_capability_matrix(root: Path, *, omit_matrix_label: str = "") -> None:
    lines = [
        "# Capability Matrix",
        "",
        "| Surface | Local source | Search/list support | Exact detail support | Write support | Permissions | Current limits |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for contract in audit_surface_contract.SURFACE_CONTRACTS:
        if contract.label == omit_matrix_label:
            continue
        lines.append(
            f"| {contract.label} | Synthetic | Search | Detail | Not implemented | Local | Synthetic |"
        )
    root.joinpath("docs/CAPABILITY_MATRIX.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

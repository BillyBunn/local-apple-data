from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_release_readiness.py"
SPEC = importlib.util.spec_from_file_location("audit_release_readiness", SCRIPT_PATH)
assert SPEC is not None
audit_release_readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_release_readiness"] = audit_release_readiness
SPEC.loader.exec_module(audit_release_readiness)
surface_contract = sys.modules["audit_surface_contract"]
write_design_gate = sys.modules["audit_write_design_gates"]


def _make_minimal_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    for relative in audit_release_readiness.REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")

    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "local-apple-data"',
                'version = "0.1.0"',
                'description = "Synthetic"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "local-apple-data", "version": "0.1.0+test"}),
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 0.1.0+test\n",
        encoding="utf-8",
    )
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"local-apple-data": {"command": "./scripts/run_mcp_server.sh"}}}),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create-note apply, and Mail create-draft apply.\n",
        encoding="utf-8",
    )
    (root / "docs/MUTATION_GATES.md").write_text(
        "Approved write tools: `reminders apply`, `reminders_apply_change`, `icloud-drive apply`, `icloud_drive_apply_change`, `calendar apply`, `calendar_apply_change`, `contacts apply`, `contacts_apply_change`, `notes apply`, `notes_apply_change`, `mail apply`, and `mail_apply_change`.\n",
        encoding="utf-8",
    )
    (root / "docs/WRITE_TOOL_ROADMAP.md").write_text(
        "Reminders apply, iCloud Drive create-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create-note apply, and Mail create-draft apply are the only approved write surfaces.\n",
        encoding="utf-8",
    )
    for contract in write_design_gate.REQUIRED_DESIGN_DOCS.values():
        (root / str(contract["path"])).write_text(
            _write_design_doc_text(),
            encoding="utf-8",
        )
    _write_surface_contract_files(root)
    return root


def _write_surface_contract_files(root: Path) -> None:
    tools = list(surface_contract.CORE_MCP_TOOLS)
    for contract in surface_contract.SURFACE_CONTRACTS:
        tools.extend(contract.mcp_tools)
    mcp_lines = [
        "from mcp.server.fastmcp import FastMCP",
        "READ_ONLY_ANNOTATIONS = object()",
        "WRITE_ANNOTATIONS = object()",
        'INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create-note apply, and Mail create-draft apply."',
        'mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)',
    ]
    for tool in tools:
        annotation = (
            "WRITE_ANNOTATIONS"
            if tool in {
                "calendar_apply_change",
                "contacts_apply_change",
                "icloud_drive_apply_change",
                "mail_apply_change",
                "notes_apply_change",
                "reminders_apply_change",
            }
            else "READ_ONLY_ANNOTATIONS"
        )
        mcp_lines.extend(
            [
                f"@mcp.tool(annotations={annotation})",
                f"def {tool}() -> dict:",
                "    return {}",
                "",
            ]
        )
    (root / "src/local_apple_data/mcp_server.py").write_text(
        "\n".join(mcp_lines) + "\n",
        encoding="utf-8",
    )

    cli_lines = [
        "def _health_command(args):",
        "    return 0",
        "",
        "def build_parser():",
        "    import argparse",
        "    parser = argparse.ArgumentParser()",
        "    subparsers = parser.add_subparsers()",
    ]
    for command in surface_contract.CORE_CLI_COMMANDS:
        cli_lines.append(f'    subparsers.add_parser("{command}")')
    for contract in surface_contract.SURFACE_CONTRACTS:
        cli_lines.extend(
            [
                f'    {contract.name} = subparsers.add_parser("{contract.cli_group}")',
                f"    {contract.cli_subparser} = {contract.name}.add_subparsers()",
            ]
        )
        for command in contract.cli_commands:
            cli_lines.append(f'    {contract.cli_subparser}.add_parser("{command}")')
    cli_lines.append("    return parser")
    (root / "src/local_apple_data/cli.py").write_text(
        "\n".join(cli_lines) + "\n",
        encoding="utf-8",
    )

    surface_names = [contract.name for contract in surface_contract.SURFACE_CONTRACTS]
    access_lines = ",\n".join(f'    {{"surface": "{surface}"}}' for surface in surface_names)
    summary_lines = ",\n".join(f'        "{surface}": {{}}' for surface in surface_names)
    (root / "src/local_apple_data/health.py").write_text(
        f"""
ACCESS_REQUIREMENTS = [
{access_lines}
]


def _surface_summary():
    return {{
{summary_lines}
    }}
""".lstrip(),
        encoding="utf-8",
    )

    matrix_lines = [
        "# Capability Matrix",
        "",
        "| Surface | Local source | Search/list support | Exact detail support | Write support | Permissions | Current limits |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for contract in surface_contract.SURFACE_CONTRACTS:
        matrix_lines.append(
            f"| {contract.label} | Synthetic | Search | Detail | Not implemented | Local | Synthetic |"
        )
    (root / "docs/CAPABILITY_MATRIX.md").write_text(
        "\n".join(matrix_lines) + "\n",
        encoding="utf-8",
    )


def _write_design_doc_text() -> str:
    phrases = []
    for contract in write_design_gate.REQUIRED_DESIGN_DOCS.values():
        phrases.extend(contract["phrases"])
    return "\n".join(str(phrase) for phrase in phrases) + "\n"


def test_audit_reports_local_ready_and_missing_remote(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)

    payload = audit_release_readiness.audit_release_readiness(root)

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is False
    assert "missing_git_remote" in payload["blockers"]


def test_audit_fails_when_required_file_is_missing(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    root.joinpath("README.md").unlink()

    payload = audit_release_readiness.audit_release_readiness(root)
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["local_package_ready"] is False
    assert checks["required_files"]["status"] == "error"


def test_audit_reports_github_ready_when_remote_exists(tmp_path: Path) -> None:
    root = _make_minimal_project(tmp_path)
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/local-apple-data.git"],
        cwd=root,
        check=True,
    )

    payload = audit_release_readiness.audit_release_readiness(root)

    assert payload["local_package_ready"] is True
    assert payload["github_publication_ready"] is True
    assert "missing_git_remote" not in payload["blockers"]

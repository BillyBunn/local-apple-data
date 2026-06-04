from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_write_design_gates.py"
SPEC = importlib.util.spec_from_file_location("audit_write_design_gates", SCRIPT_PATH)
assert SPEC is not None
audit_write_design_gates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_write_design_gates"] = audit_write_design_gates
SPEC.loader.exec_module(audit_write_design_gates)


def test_current_project_write_design_gate_audit_passes() -> None:
    payload = audit_write_design_gates.audit_write_design_gates(
        Path(__file__).resolve().parents[1]
    )

    assert payload["status"] == "ok"
    assert payload["write_design_gate"] is True
    assert payload["design_docs_checked"] >= 1
    assert payload["approved_preview_tools"] == ["reminders_plan_change"]
    assert payload["approved_write_tools"] == []
    assert payload["findings"] == []


def test_write_design_gate_flags_missing_design_doc(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("docs/V1_11_REMINDERS_WRITE_DESIGN.md").unlink()

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_design_doc_missing", "reminders_write_v1")


def test_write_design_gate_flags_incomplete_design_doc(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    path = root / "docs/V1_11_REMINDERS_WRITE_DESIGN.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "Status: Preview-only implementation.",
            "Status: Draft.",
        ),
        encoding="utf-8",
    )

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_design_doc_contract_missing", "reminders_write_v1")


def test_write_design_gate_flags_write_phase_mcp_tool(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, mcp_tool_name="reminders_apply")

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_phase_mcp_tool", "reminders_apply")


def test_write_design_gate_flags_write_phase_cli_handler(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path, cli_handler_name="_reminders_preview_command")

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "write_phase_cli_handler", "_reminders_preview_command")


def test_write_design_gate_flags_missing_read_only_contract(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    root.joinpath("README.md").write_text("Synthetic README.\n", encoding="utf-8")

    payload = audit_write_design_gates.audit_write_design_gates(root)

    assert payload["status"] == "error"
    assert _finding(payload, "read_only_contract_missing", "README.md")


def _finding(payload: dict, kind: str, name: str) -> bool:
    return any(
        finding["kind"] == kind and finding["name"] == name
        for finding in payload["findings"]
    )


def _minimal_project(
    tmp_path: Path,
    *,
    mcp_tool_name: str = "apple_data_health",
    cli_handler_name: str = "_health_command",
) -> Path:
    root = tmp_path / "project"
    root.joinpath("src/local_apple_data").mkdir(parents=True)
    root.joinpath(".codex-plugin").mkdir()
    root.joinpath("docs").mkdir()

    (root / "README.md").write_text(
        "The current release is read-only.\n",
        encoding="utf-8",
    )
    (root / "docs/MUTATION_GATES.md").write_text(
        "The current plugin is read-only.\n",
        encoding="utf-8",
    )
    (root / "docs/WRITE_TOOL_ROADMAP.md").write_text(
        "The current release is read-only.\n",
        encoding="utf-8",
    )
    (root / "docs/V1_11_REMINDERS_WRITE_DESIGN.md").write_text(
        _design_doc_text(),
        encoding="utf-8",
    )
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"interface": {"capabilities": ["Read", "Search", "MCP", "Local"]}}),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/mcp_server.py").write_text(
        f"""
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = "Mutation is not available in this server."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def {mcp_tool_name}() -> dict:
    return {{}}
""".lstrip(),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/cli.py").write_text(
        f"""
def {cli_handler_name}(args):
    return 0
""".lstrip(),
        encoding="utf-8",
    )
    return root


def _design_doc_text() -> str:
    phrases = []
    for contract in audit_write_design_gates.REQUIRED_DESIGN_DOCS.values():
        phrases.extend(contract["phrases"])
    return "\n".join(str(phrase) for phrase in phrases) + "\n"

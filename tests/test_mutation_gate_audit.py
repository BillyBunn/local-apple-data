from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_mutation_gates.py"
SPEC = importlib.util.spec_from_file_location("audit_mutation_gates", SCRIPT_PATH)
assert SPEC is not None
audit_mutation_gates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_mutation_gates"] = audit_mutation_gates
SPEC.loader.exec_module(audit_mutation_gates)


def test_current_project_mutation_gate_audit_passes() -> None:
    payload = audit_mutation_gates.audit_mutation_gates(
        Path(__file__).resolve().parents[1]
    )

    assert payload["status"] == "ok"
    assert payload["read_only"] is False
    assert payload["approved_write_tools"] == [
        "calendar_apply_change",
        "contacts_apply_change",
        "icloud_drive_apply_change",
        "mail_apply_change",
        "notes_apply_change",
        "photos_apply_change",
        "reminders_apply_change",
    ]
    assert payload["mcp_tools_checked"] >= 43
    assert payload["cli_handlers_checked"] >= 43
    assert payload["findings"] == []


def test_mutation_gate_audit_flags_mcp_write_tool(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/mcp_server.py").write_text(
        """
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_create() -> dict:
    return {}
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "mutation_like_mcp_tool"
    assert payload["findings"][0]["name"] == "reminders_create"


def test_mutation_gate_audit_flags_non_readonly_mcp_annotation(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/mcp_server.py").write_text(
        """
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
WRITE_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=WRITE_ANNOTATIONS)
def reminders_search() -> dict:
    return {}
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "mcp_tool_not_read_only"


def test_mutation_gate_audit_flags_cli_write_handler(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/cli.py").write_text(
        """
def _mail_send_command(args):
    return 0
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "mutation_like_cli_handler"
    assert payload["findings"][0]["name"] == "_mail_send_command"


def _minimal_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.joinpath("src/local_apple_data").mkdir(parents=True)
    root.joinpath(".codex-plugin").mkdir()
    root.joinpath("docs").mkdir()

    (root / "README.md").write_text(
        "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply.\n",
        encoding="utf-8",
    )
    (root / "docs/MUTATION_GATES.md").write_text(
        "Approved write tools: `reminders apply`, `reminders_apply_change`, `icloud-drive apply`, `icloud_drive_apply_change`, `calendar apply`, `calendar_apply_change`, `contacts apply`, `contacts_apply_change`, `notes apply`, `notes_apply_change`, `mail apply`, `mail_apply_change`, `photos apply`, and `photos_apply_change`.\n",
        encoding="utf-8",
    )
    (root / "docs/WRITE_TOOL_ROADMAP.md").write_text(
        "Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply are the only approved write surfaces.\n",
        encoding="utf-8",
    )
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"interface": {"capabilities": ["Read", "Search", "MCP", "Local"]}}),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/mcp_server.py").write_text(
        """
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders apply, iCloud Drive create/append-text apply, Calendar create-event apply, Contacts create-contact apply, Notes create/append-text apply, Mail create-draft apply, and Photos import apply."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_search() -> dict:
    return {}
""".lstrip(),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/cli.py").write_text(
        """
def _reminders_search_command(args):
    return 0
""".lstrip(),
        encoding="utf-8",
    )
    return root

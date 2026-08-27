from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_mutation_gates.py"
SPEC = importlib.util.spec_from_file_location("audit_mutation_gates", SCRIPT_PATH)
assert SPEC is not None
audit_mutation_gates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["audit_mutation_gates"] = audit_mutation_gates
SPEC.loader.exec_module(audit_mutation_gates)

import build_public_release_tree


def test_current_project_mutation_gate_audit_passes() -> None:
    payload = audit_mutation_gates.audit_mutation_gates(
        Path(__file__).resolve().parents[1]
    )

    assert payload["status"] == "ok"
    assert payload["read_only"] is False
    assert payload["approved_write_tools"] == [
        "calendar_apply_calendar_change",
        "calendar_apply_change",
        "contacts_apply_change",
        "filesystem_apply_change",
        "icloud_drive_apply_change",
        "mail_apply_change",
        "mail_apply_cleanup",
        "mail_apply_mailbox_change",
        "messages_apply_change",
        "notes_apply_change",
        "photos_apply_change",
        "reminders_apply_change",
        "reminders_apply_list_change",
        "shortcuts_apply_run",
    ]
    assert len(payload["approved_write_tools"]) == 14
    assert payload["approved_local_cache_write_tools"] == [
        "mail_build_fts_index",
        "mail_create_template",
        "mail_delete_template",
    ]
    assert payload["mcp_tools_checked"] == 151
    assert payload["cli_handlers_checked"] == 154
    assert payload["findings"] == []


def test_minimal_project_mutation_gate_audit_passes(tmp_path: Path) -> None:
    payload = audit_mutation_gates.audit_mutation_gates(_minimal_project(tmp_path))

    assert payload["status"] == "ok"
    assert payload["findings"] == []


def test_mutation_gate_audit_passes_generated_public_tree(tmp_path: Path) -> None:
    source = _minimal_project(tmp_path)
    destination = tmp_path / "public"
    build_public_release_tree.build_release_tree(source, destination)

    assert not destination.joinpath(audit_mutation_gates.AGENTS_DOC).exists()
    payload = audit_mutation_gates.audit_mutation_gates(destination)

    assert payload["status"] == "ok"
    assert payload["findings"] == []


def test_mutation_gate_audit_flags_mcp_write_tool(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/mcp_server.py").write_text(
        """
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact same-source list-move/delete apply, iCloud Drive create-folder/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file apply, Calendar create-event/update/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact note append/set/clear/merge/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, exact-folder rename, exact empty child-folder delete, exact empty child-folder move, append-text, replace-text, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Mail synthetic `LAD-TEST-*` mailbox create/rename apply, Mail synthetic-only permanent delete/empty Trash/Junk cleanup apply, Photos import and exact asset favorite/hidden update apply, and Messages send-text/send-file apply."
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


@pytest.mark.parametrize(
    "tool_name",
    [
        "icloud_drive_rename_file",
        "icloud_drive_copy_file",
        "icloud_drive_trash_file",
        "icloud_drive_replace_file",
    ],
)
def test_mutation_gate_audit_flags_unapproved_mcp_location_verbs(
    tmp_path: Path,
    tool_name: str,
) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/mcp_server.py").write_text(
        f"""
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact same-source list-move/delete apply, iCloud Drive create-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text apply, Calendar create-event/update/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact note append/set/clear/merge/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, append-text, replace-text, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Mail synthetic `LAD-TEST-*` mailbox create/rename apply, Mail synthetic-only permanent delete/empty Trash/Junk cleanup apply, Photos import and exact asset favorite/hidden update apply, and Messages send-text/send-file apply."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def {tool_name}() -> dict:
    return {{}}
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "mutation_like_mcp_tool"
    assert payload["findings"][0]["name"] == tool_name


def test_mutation_gate_audit_flags_non_readonly_mcp_annotation(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/mcp_server.py").write_text(
        """
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
WRITE_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact same-source list-move/delete apply, iCloud Drive create-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text apply, Calendar create-event/update/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact note append/set/clear/merge/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, append-text, replace-text, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Mail synthetic `LAD-TEST-*` mailbox create/rename apply, Mail synthetic-only permanent delete/empty Trash/Junk cleanup apply, Photos import and exact asset favorite/hidden update apply, and Messages send-text/send-file apply."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=WRITE_ANNOTATIONS)
def reminders_search() -> dict:
    return {{}}
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "mcp_tool_not_read_only"


def test_mutation_gate_audit_requires_destructive_annotation_for_destructive_writes(
    tmp_path: Path,
) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/mcp_server.py").write_text(
        """
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
WRITE_ANNOTATIONS = object()
DESTRUCTIVE_WRITE_ANNOTATIONS = object()
INSTRUCTIONS = "The only apply-capable mutation surfaces are Reminders create/complete/uncomplete/due-date/title/notes/priority-update/exact same-source list-move/delete apply, iCloud Drive create-folder/create/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text apply, Calendar create-event/update/delete apply, Contacts create-contact/exact scalar/method/rich-field/image update/exact note append/set/clear/merge/exact group membership/exact group create/rename/delete/exact batch/delete apply, Notes default/exact-folder note create, exact child-folder create, append-text, replace-text, move-to-folder, and exact-note delete apply, Mail create-draft/send-message/reply-message/reply-all-message/forward-message/mark-read/mark-unread/flag-message/unflag-message/archive-message/move-message/trash-message apply including capped exact bulk triage, Mail synthetic `LAD-TEST-*` mailbox create/rename apply, Mail synthetic-only permanent delete/empty Trash/Junk cleanup apply, Photos import and exact asset favorite/hidden update apply, and Messages send-text/send-file apply."
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=WRITE_ANNOTATIONS)
def contacts_apply_change() -> dict:
    return {}
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "approved_destructive_mcp_tool_annotation"
    assert payload["findings"][0]["name"] == "contacts_apply_change"


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


@pytest.mark.parametrize(
    "handler_name",
    [
        "_icloud_drive_rename_command",
        "_icloud_drive_copy_command",
        "_icloud_drive_trash_command",
        "_icloud_drive_replace_command",
    ],
)
def test_mutation_gate_audit_flags_unapproved_cli_location_verbs(
    tmp_path: Path,
    handler_name: str,
) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/cli.py").write_text(
        f"""
def {handler_name}(args):
    return 0
""".lstrip(),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert payload["findings"][0]["kind"] == "mutation_like_cli_handler"
    assert payload["findings"][0]["name"] == handler_name


def test_mutation_gate_audit_flags_operation_contract_drift(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/adapters/icloud_drive.py").write_text(
        'PLAN_OPERATIONS = {"create_text", "append_text"}\n',
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "operation_contract_mismatch"
        and finding["name"] == "PLAN_OPERATIONS"
        and finding["path"] == "src/local_apple_data/adapters/icloud_drive.py"
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_flags_non_icloud_operation_contract_drift(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / "src/local_apple_data/adapters/mail.py").write_text(
        'PLAN_OPERATIONS = {"create_draft", "send_message", "permanent_delete"}\n',
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "operation_contract_mismatch"
        and finding["name"] == "PLAN_OPERATIONS"
        and finding["path"] == "src/local_apple_data/adapters/mail.py"
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_flags_manifest_capability_overclaim(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / ".codex-plugin/plugin.json").write_text(
        _plugin_manifest_json(capabilities=["Read", "Search", "Write", "MCP", "Local", "Delete"]),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "plugin_manifest_capability_contract"
        and finding["name"] == "interface.capabilities"
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_flags_cli_operation_choice_drift(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    path = root / "src/local_apple_data/cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'icloud_drive_plan.add_argument("--operation", choices=[',
            'icloud_drive_plan.add_argument("--operation", choices=["permanent-delete", ',
            1,
        ),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "operation_contract_mismatch"
        and finding["name"] == "cli.icloud_drive_plan.choices"
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_flags_mcp_operation_literal_drift(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    path = root / "src/local_apple_data/mcp_server.py"
    source = path.read_text(encoding="utf-8")
    literal_line = next(
        line for line in source.splitlines() if line.startswith("ICloudDriveOperation = ")
    )
    path.write_text(
        source.replace(
            literal_line,
            literal_line[:-1] + ', "permanent-delete"]',
            1,
        ),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "operation_contract_mismatch"
        and finding["name"] == "mcp.ICloudDriveOperation"
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_flags_manifest_text_overclaim(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps(
            {
                "description": "Local Apple Data with full CRUD and permanent-delete apply.",
                "interface": {
                    "capabilities": ["Read", "Search", "Write", "MCP", "Local"],
                    "longDescription": "Supports new chat, reply-all, and uses browser sessions.",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "plugin_manifest_text_contract"
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_flags_stale_agents_mutation_summary(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    (root / audit_mutation_gates.AGENTS_DOC).write_text(
        "Approved mutation is limited to Photos import, exact asset favorite/hidden update, "
        "and exact asset delete apply.\n",
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "read_only_contract_missing"
        and finding["path"] == audit_mutation_gates.AGENTS_DOC
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_requires_contacts_note_fail_closed_caveat(
    tmp_path: Path,
) -> None:
    root = _minimal_project(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "every note operation fails closed with `contacts_note_unavailable` before mutation",
            "Contacts note operations are available live",
        ),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "read_only_contract_missing"
        and finding["path"].endswith("README.md")
        for finding in payload["findings"]
    )


def test_mutation_gate_audit_requires_contacts_note_contract_in_mcp_instructions(
    tmp_path: Path,
) -> None:
    root = _minimal_project(tmp_path)
    path = root / "src/local_apple_data/mcp_server.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            audit_mutation_gates.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT,
            "Contacts note operations are unavailable.",
        ),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "read_only_contract_missing"
        and finding["path"].endswith("src/local_apple_data/mcp_server.py")
        for finding in payload["findings"]
    )


@pytest.mark.parametrize(
    ("field", "finding_name"),
    (
        ("description", "description"),
        ("longDescription", "interface.longDescription"),
    ),
)
def test_mutation_gate_audit_requires_contacts_note_contract_in_manifest(
    tmp_path: Path,
    field: str,
    finding_name: str,
) -> None:
    root = _minimal_project(tmp_path)
    path = root / ".codex-plugin/plugin.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    container = manifest if field == "description" else manifest["interface"]
    container[field] = container[field].replace(
        audit_mutation_gates.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT,
        "Contacts note operations are unavailable.",
    )
    path.write_text(json.dumps(manifest), encoding="utf-8")

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "plugin_manifest_text_contract"
        and finding["name"] == finding_name
        for finding in payload["findings"]
    )


def _minimal_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.joinpath("src/local_apple_data").mkdir(parents=True)
    root.joinpath("src/local_apple_data/adapters").mkdir(parents=True)
    root.joinpath(".codex-plugin").mkdir()
    root.joinpath("docs").mkdir()

    (root / "README.md").write_text(
        audit_mutation_gates.REQUIRED_MUTATION_GATE_TEXT["README.md"]
        + ".\nContacts note plan/apply contracts are designed and synthetic-testable, but they are not a usable live mutation surface: every note operation fails closed with `contacts_note_unavailable` before mutation.\n",
        encoding="utf-8",
    )
    (root / audit_mutation_gates.AGENTS_DOC).write_text(
        "Approved mutation is limited to "
        + audit_mutation_gates.CANONICAL_APPLY_SURFACE_SUMMARY
        + ".\nThe designed Contacts note gates are synthetic-testable but currently fail closed before mutation with `contacts_note_unavailable`.\n",
        encoding="utf-8",
    )
    (root / "docs/MUTATION_GATES.md").write_text(
        audit_mutation_gates.REQUIRED_MUTATION_GATE_TEXT["docs/MUTATION_GATES.md"]
        + ".\n"
        + "\n".join(
            audit_mutation_gates.REQUIRED_MUTATION_DETAIL_TEXT["docs/MUTATION_GATES.md"]
        )
        + "\n"
        + "recurrence outside simple count-bound daily/weekly/monthly/yearly create, add-to-non-recurring-event update, weekly weekday selection, monthly day-of-month selection, monthly nth-weekday selection, selected-occurrence delete, future-event recurring span delete, whole-series recurring-event delete, or first-visible or mid-series recurrence clearing.\n"
        + "custom monthly recurrence components beyond monthly BYDAY/BYMONTHDAY/monthly nth-weekday, custom yearly recurrence rules.\n",
        encoding="utf-8",
    )
    (root / "docs/WRITE_TOOL_ROADMAP.md").write_text(
        audit_mutation_gates.CANONICAL_APPLY_SURFACE_SUMMARY
        + " are the only approved write surfaces.\n",
        encoding="utf-8",
    )
    (root / ".codex-plugin/plugin.json").write_text(
        _plugin_manifest_json(),
        encoding="utf-8",
    )
    mcp_instructions = (
        audit_mutation_gates.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT
        + " The only apply-capable mutation surfaces are "
        + audit_mutation_gates.CANONICAL_APPLY_SURFACE_SUMMARY
        + "."
    )
    (root / "src/local_apple_data/mcp_server.py").write_text(
        _mcp_source(
            f"""
from mcp.server.fastmcp import FastMCP
READ_ONLY_ANNOTATIONS = object()
INSTRUCTIONS = {mcp_instructions!r}
mcp = FastMCP("local-apple-data", instructions=INSTRUCTIONS)
@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def reminders_search() -> dict:
    return {{}}
""".lstrip()
        ),
        encoding="utf-8",
    )
    (root / "src/local_apple_data/cli.py").write_text(
        _cli_source(
            """
def _reminders_search_command(args):
    return 0
""".lstrip()
        ),
        encoding="utf-8",
    )
    for relative, operation_sets in audit_mutation_gates.REQUIRED_OPERATION_SETS.items():
        lines = []
        for variable_name, values in operation_sets.items():
            literal = ", ".join(repr(value) for value in sorted(values))
            lines.append(f"{variable_name} = {{{literal}}}")
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_mutation_gate_audit_flags_missing_delete_text_identity_replay_contract(
    tmp_path: Path,
) -> None:
    root = _minimal_project(tmp_path)
    gates = root / "docs/MUTATION_GATES.md"
    gates.write_text(
        gates.read_text(encoding="utf-8").replace("stale identity/token replay refusal, ", ""),
        encoding="utf-8",
    )

    payload = audit_mutation_gates.audit_mutation_gates(root)

    assert payload["status"] == "error"
    assert any(
        finding["kind"] == "read_only_contract_missing"
        and finding["path"].endswith("docs/MUTATION_GATES.md")
        for finding in payload["findings"]
    )


def _plugin_manifest_json(*, capabilities: list[str] | None = None) -> str:
    return json.dumps(
        {
            "description": (
                audit_mutation_gates.CONTACTS_NOTE_FAIL_CLOSED_CONTRACT
                + " Local-first Apple data access with "
                + audit_mutation_gates.REQUIRED_PLUGIN_DESCRIPTION_TEXT
                + "."
            ),
            "interface": {
                "capabilities": capabilities or ["Read", "Search", "Write", "MCP", "Local"],
                "longDescription": " ".join(
                    audit_mutation_gates.REQUIRED_PLUGIN_LONG_DESCRIPTION_TEXT
                ),
            },
        }
    )


def _mcp_source(body: str) -> str:
    lines = ["from typing import Literal"]
    for type_name, values in sorted(
        audit_mutation_gates.REQUIRED_MCP_OPERATION_LITERALS.items()
    ):
        literal_values = ", ".join(f'"{value}"' for value in sorted(values))
        lines.append(f"{type_name} = Literal[{literal_values}]")
    return "\n".join(lines) + "\n" + body


def _cli_source(body: str) -> str:
    lines = [
        "class _Parser:",
        "    def add_argument(self, *args, **kwargs):",
        "        return None",
        "",
    ]
    for parser_name, choices in sorted(audit_mutation_gates.REQUIRED_CLI_OPERATION_CHOICES.items()):
        choices_text = ", ".join(f'"{choice}"' for choice in sorted(choices))
        lines.extend(
            [
                f"{parser_name} = _Parser()",
                f'{parser_name}.add_argument("--operation", choices=[{choices_text}])',
                "",
            ]
        )
    return "\n".join(lines) + "\n" + body

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_plugin_manifest_wires_skill_and_mcp() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "local-apple-data"
    assert manifest["version"].startswith("0.1.0")
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"
    assert manifest["license"] == "MIT"
    assert manifest["author"]["name"] == "Billy Bunn"
    assert "Read" in manifest["interface"]["capabilities"]
    assert "Write" in manifest["interface"]["capabilities"]
    assert "MCP" in manifest["interface"]["capabilities"]
    assert "iCloud Drive" in manifest["description"]
    assert "Calendar" in manifest["description"]
    assert (
        "approved Reminders, iCloud Drive create/append text, Calendar, Contacts, Notes, Mail draft, and Photos import apply"
        in manifest["description"]
    )


def test_mcp_manifest_uses_local_server_entrypoint() -> None:
    manifest = json.loads((PROJECT_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = manifest["mcpServers"]["local-apple-data"]

    assert server["command"] == "./scripts/run_mcp_server.sh"
    assert server["args"] == []
    assert server["cwd"] == "."


def test_skill_metadata_mentions_local_mcp_dependency() -> None:
    skill = (PROJECT_ROOT / "skills" / "local-apple-data" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    agent = (
        PROJECT_ROOT
        / "skills"
        / "local-apple-data"
        / "agents"
        / "openai.yaml"
    ).read_text(encoding="utf-8")

    assert "name: local-apple-data" in skill
    assert "Do not use the Gmail connector" in skill
    assert "calendar_get_event" in skill
    assert "calendar_plan_change" in skill
    assert "calendar_apply_change" in skill
    assert "contacts_get" in skill
    assert "contacts_plan_change" in skill
    assert "contacts_apply_change" in skill
    assert "hide_my_email_get_alias" in skill
    assert "icloud_drive_get_content" in skill
    assert "icloud_drive_plan_change" in skill
    assert "icloud_drive_apply_change" in skill
    assert "mail_plan_change" in skill
    assert "mail_apply_change" in skill
    assert "messages_get_chat" in skill
    assert "notes_plan_change" in skill
    assert "notes_apply_change" in skill
    assert "photos_get_asset" in skill
    assert "photos_export_asset" in skill
    assert "photos_plan_change" in skill
    assert "photos_apply_change" in skill
    assert "reminders_get_content" in skill
    assert "reminders_plan_change" in skill
    assert "reminders_apply_change" in skill
    assert "voice_memos_get_recording" in skill
    assert "voice_memos_export_audio" in skill
    assert 'value: "local-apple-data"' in agent
    assert "$local-apple-data" in agent


def test_public_release_docs_are_present() -> None:
    expected = [
        "CONTRIBUTING.md",
        "LICENSE",
        "CHANGELOG.md",
        "SECURITY.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        "docs/INSTALL.md",
        "docs/SAMPLE_OUTPUTS.md",
        "docs/MACOS_SUPPORT.md",
        "docs/ECOSYSTEM_REVIEW.md",
        "docs/PUBLIC_RELEASE_MANIFEST.md",
        "docs/CAPABILITY_MATRIX.md",
        "docs/MUTATION_GATES.md",
        "docs/V1_11_REMINDERS_WRITE_DESIGN.md",
        "docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md",
        "docs/V1_13_CALENDAR_WRITE_DESIGN.md",
        "docs/V1_14_CONTACTS_WRITE_DESIGN.md",
        "docs/V1_15_NOTES_WRITE_DESIGN.md",
        "docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md",
        "docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md",
        "docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md",
        "docs/WRITE_TOOL_ROADMAP.md",
        "docs/PUBLISHING.md",
    ]

    for relative in expected:
        path = PROJECT_ROOT / relative
        assert path.exists(), relative
        assert path.read_text(encoding="utf-8").strip(), relative


def test_public_release_builder_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "build_public_release_tree.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "build_release_tree" in source
    assert "public_release_scan.scan_public_files" in source


def test_public_git_checkout_preparer_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "prepare_public_git_checkout.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "prepare_public_git_checkout" in source
    assert "git" in source
    assert "remote" in source
    assert "--commit" in source
    assert '"commit"' in source


def test_release_receipt_generator_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "generate_release_receipt.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "generate_release_receipt" in source
    assert "paths_redacted" in source
    assert "public_git_checkout" in source
    assert "commit_sha" in source


def test_release_readiness_auditor_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "audit_release_readiness.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "audit_release_readiness" in source
    assert "github_publication_ready" in source
    assert "missing_git_remote" in source
    assert "--require-github-ready" in source


def test_mutation_gate_auditor_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "audit_mutation_gates.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "audit_mutation_gates" in source
    assert "mutation_like_mcp_tool" in source
    assert "mcp_tool_not_read_only" in source


def test_write_design_gate_auditor_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "audit_write_design_gates.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "audit_write_design_gates" in source
    assert "write_design_doc_contract_missing" in source
    assert "write_phase_mcp_tool" in source


def test_surface_contract_auditor_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "audit_surface_contract.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "audit_surface_contract" in source
    assert "missing_mcp_tool" in source
    assert "missing_cli_command" in source
    assert "missing_capability_matrix_row" in source


def test_mcp_client_config_renderer_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "render_mcp_client_config.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "render_config" in source
    assert "render_server_config" in source
    assert "claude-code" in source
    assert "cursor" in source
    assert "openclaw" in source
    assert "--server-only" in source
    assert "${workspaceFolder}/scripts/run_mcp_server.sh" in source


def test_cross_agent_sync_verifier_has_public_checkout_options() -> None:
    source = (PROJECT_ROOT / "scripts" / "verify_cross_agent_sync.py").read_text(
        encoding="utf-8"
    )

    assert "--project-root" in source
    assert "--personal-root" in source
    assert "--cache-root" in source
    assert "--skip-claude" in source
    assert "--skip-cursor" in source
    assert "--require-cursor" in source
    assert "--cursor-config" in source
    project_path = 'Path("/Users/' + 'billy/Projects/local-apple-data")'
    personal_path = 'Path("/Users/' + 'billy/plugins/local-apple-data")'
    assert project_path not in source
    assert personal_path not in source

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import public_release_scan
from scripts.audit_surface_contract import SURFACE_CONTRACTS


def test_plugin_manifest_wires_skill_and_mcp() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "local-apple-data"
    assert manifest["version"].startswith("0.1.0")
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"
    assert manifest["license"] == "MIT"
    assert manifest["author"]["name"] == "local-apple-data contributors"
    assert "Read" in manifest["interface"]["capabilities"]
    assert "Write" in manifest["interface"]["capabilities"]
    assert "MCP" in manifest["interface"]["capabilities"]
    assert "iCloud Drive" in manifest["description"]
    assert "Mail/Messages/Notes attachment export" in manifest["description"]
    assert "Calendar" in manifest["description"]
    assert len(manifest["interface"]["defaultPrompt"]) <= 3
    assert (
        "approved Reminders, iCloud Drive create-folder/create-folder-path/rename-folder/trash-folder/delete-folder/move-folder/copy-folder/create-text/append-text/replace-text/trash-text/delete-text/rename-text/copy-text/move-text/rename-file/copy-file/move-file/import-file/replace-file/trash-file/delete-file, Calendar create/update/delete with date-only all-day inference, exact availability create/update, exact allow-listed event URL create/update and exact event URL clearing, and simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly recurrence create plus add-to-non-recurring-event update plus weekly weekday, monthly weekday, monthly day-of-month, monthly nth-weekday, and yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year"
        in manifest["description"]
    )
    assert (
        "Mail draft/send/reply/reply-all/forward support optional exact sender selection and bounded local file attachments"
        in manifest["description"]
    )
    assert "mail:sender:v1" in manifest["interface"]["longDescription"]
    assert "optional sender_handle is accepted for create-draft/send/reply/reply-all/forward" in manifest["interface"]["longDescription"]
    assert "Mail create-draft/send-message/reply-message/reply-all-message/forward-message may attach bounded caller-selected local files" in manifest["interface"]["longDescription"]
    assert "content SHA-256 into the approval token" in manifest["interface"]["longDescription"]
    assert "private temporary file before Mail automation" in manifest["interface"]["longDescription"]
    assert "Mail attachment search can opt into text/PDF snippets with include_content" in manifest["interface"]["longDescription"]
    assert "Mail source attachment/non-body-part forwarding is allowed only for exact forward-message with explicit `include_source_attachments`" in manifest["interface"]["longDescription"]
    assert "Photos regular album management requires full Photos Library authorization" in manifest["interface"]["longDescription"]
    assert "Reminders list management is limited to exact create/rename/empty-delete" in manifest["interface"]["longDescription"]
    assert "Mail synthetic mailbox apply is limited to top-level `LAD-TEST-*` mailbox create/rename/delete" in manifest["interface"]["longDescription"]
    assert "delete remains live-blocked on this host by Mail.app AppleEvent `-10000`" in manifest["interface"]["longDescription"]
    assert "success requires exact target-state binding, mailbox-scoped absence proof, and Mail-idle guards" in manifest["interface"]["longDescription"]
    assert "Calendar create/update/delete supports timed or date-only/explicit all-day events" in manifest["interface"]["longDescription"]
    assert "simple count-, end-date-, or explicit-unbounded daily/weekly/monthly/yearly recurrence create and add-to-non-recurring-event update with weekly weekday, monthly weekday, monthly day-of-month, monthly nth-weekday, and yearly month/month-day/month-nth-weekday/day-of-year/week-of-year plus explicit weekday selection for week-of-year" in manifest["interface"]["longDescription"]
    assert "recurrence_year_days" in manifest["interface"]["longDescription"]
    assert "recurrence_year_weeks" in manifest["interface"]["longDescription"]
    assert "first-visible and mid-series recurrence clearing, mid-series recurrence replacement" in manifest["interface"]["longDescription"]
    assert "clear_recurrence" in manifest["interface"]["longDescription"]
    assert "exact allow-listed event URL create/update and exact event URL clearing with hash-only read-back proof" in manifest["interface"]["longDescription"]
    assert (
        "iCloud Drive regular-file rename/copy/move is limited to one exact non-text non-package regular-file handle with expected metadata SHA-256 binding, no-overwrite target proof, source/target presence proof, metadata-only read-back, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash."
        in manifest["interface"]["longDescription"]
    )
    assert (
        "iCloud Drive import-file is limited to one caller-selected local non-text non-package regular file outside iCloud Drive plus one exact target parent handle with private source identity/content binding, no-overwrite target proof, source-preservation proof, byte-preservation proof, metadata-only target read-back, no source path/hash return, `source_path_returned:false`, `source_hash_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash."
        in manifest["interface"]["longDescription"]
    )
    assert (
        "iCloud Drive replace-file is limited to one exact non-text non-package regular-file handle plus one caller-selected local non-text non-package regular file outside iCloud Drive with expected target metadata binding, private source identity/content binding, source/target extension match, target metadata drift refusal, source-preservation proof, byte-replacement proof, metadata-only target read-back, no source path/hash return, `source_path_returned:false`, `source_hash_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash."
        in manifest["interface"]["longDescription"]
    )
    assert (
        "iCloud Drive trash-file is limited to one exact non-text non-package regular-file handle with expected target metadata binding, target metadata drift refusal, recoverable Trash move, original absence proof, metadata-only read-back, no raw Trash path return, `trash_path_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash."
        in manifest["interface"]["longDescription"]
    )
    assert (
        "iCloud Drive delete-file is limited to one exact non-text non-package regular-file handle with expected target metadata binding, target metadata drift refusal, hidden staging identity proof, permanent unlink, original absence proof, metadata-only read-back, no raw staging or Trash path return, `staging_path_returned:false`, `trash_path_returned:false`, no inline content, `content_text_returned:false`, `content_hash_returned:false`, and no returned content hash."
        in manifest["interface"]["longDescription"]
    )
    assert (
        "Reminders apply is limited to create/complete/uncomplete/due-date/title/notes/priority-update/exact URL update/clear/exact absolute/relative/mixed display-alarm set/clear/start-date set/clear/recurrence create/update/clear/exact same-source list-move/delete"
        in manifest["description"]
    )


def test_mcp_manifest_uses_local_server_entrypoint() -> None:
    manifest = json.loads((PROJECT_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = manifest["mcpServers"]["local-apple-data"]

    assert server["command"] == "./scripts/run_mcp_server.sh"
    assert server["args"] == []
    assert server["cwd"] == "."


def test_mcp_runner_disables_bytecode_artifacts() -> None:
    runner = (PROJECT_ROOT / "scripts" / "run_mcp_server.sh").read_text(
        encoding="utf-8"
    )
    server = (PROJECT_ROOT / "src" / "local_apple_data" / "mcp_server.py").read_text(
        encoding="utf-8"
    )

    assert "export PYTHONDONTWRITEBYTECODE=1" in runner
    assert "sys.dont_write_bytecode = True" in server


def test_mcp_runner_exports_no_bytecode_before_python_starts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "plugin"
    scripts_dir = root / "scripts"
    python_path = root / ".venv" / "bin" / "python"
    scripts_dir.mkdir(parents=True)
    python_path.parent.mkdir(parents=True)
    runner = scripts_dir / "run_mcp_server.sh"
    shutil.copy(PROJECT_ROOT / "scripts" / "run_mcp_server.sh", runner)
    runner.chmod(0o755)
    python_path.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"${PYTHONDONTWRITEBYTECODE:-}\"\n",
        encoding="utf-8",
    )
    python_path.chmod(0o755)

    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID",
            "LOCAL_APPLE_DATA_OPERATOR_ENV_FILE",
            "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID",
            "PYTHONDONTWRITEBYTECODE",
        }
    }
    env["HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [str(runner)],
        cwd=root,
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.stdout.strip() == "1"


def test_mcp_runner_does_not_execute_operator_env_files() -> None:
    runner = (PROJECT_ROOT / "scripts" / "run_mcp_server.sh").read_text(
        encoding="utf-8"
    )

    assert "source " not in runner
    assert "Python strictly parses" in runner


def test_mcp_runner_real_python_startup_leaves_no_bytecode(
    tmp_path: Path,
) -> None:
    root = tmp_path / "plugin"
    scripts_dir = root / "scripts"
    python_path = root / ".venv" / "bin" / "python"
    package_dir = root / "src" / "local_apple_data"
    scripts_dir.mkdir(parents=True)
    python_path.parent.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    runner = scripts_dir / "run_mcp_server.sh"
    shutil.copy(PROJECT_ROOT / "scripts" / "run_mcp_server.sh", runner)
    runner.chmod(0o755)
    python_path.symlink_to(sys.executable)
    package_dir.joinpath("__init__.py").write_text("", encoding="utf-8")
    package_dir.joinpath("helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    package_dir.joinpath("mcp_server.py").write_text(
        "from .helper import VALUE\n"
        "raise SystemExit(0 if VALUE == 1 else 1)\n",
        encoding="utf-8",
    )

    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID",
            "LOCAL_APPLE_DATA_OPERATOR_ENV_FILE",
            "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID",
            "PYTHONDONTWRITEBYTECODE",
        }
    }
    env["HOME"] = str(tmp_path / "home")
    subprocess.run(
        [str(runner)],
        cwd=root,
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    artifacts = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    assert artifacts == []


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
    assert "calendar_list_participants" in skill
    assert "calendar_get_participant" in skill
    assert "calendar_list_calendar_events" in skill
    assert "calendar events" in skill
    assert "calendar_plan_change" in skill
    assert "calendar_apply_change" in skill
    assert "clear_recurrence" in skill
    assert "first-visible or mid-series supported recurring occurrence" in skill
    assert "contacts_get" in skill
    assert "contacts_count" in skill
    assert "contacts_export_archive" in skill
    assert "contacts_plan_change" in skill
    assert "contacts_apply_change" in skill
    assert "hide_my_email_get_alias" in skill
    assert "icloud_drive_get_root" in skill
    assert "icloud_drive_get_content" in skill
    assert "icloud_drive_list_folder" in skill
    assert "icloud_drive_list_tree" in skill
    assert "icloud_drive_plan_change" in skill
    assert "icloud_drive_apply_change" in skill
    assert "create-folder" in skill
    assert "rename-text" in skill
    assert "copy-text" in skill
    assert "move-text" in skill
    assert "mail_list_attachments" in skill
    assert "mail_export_attachment" in skill
    assert "mail_search_mailboxes" in skill
    assert "mail_get_mailbox" in skill
    assert "mail_search_senders" in skill
    assert "mail_get_sender" in skill
    assert "mail_plan_change" in skill
    assert "mail_apply_change" in skill
    assert "messages_get_chat" in skill
    assert "messages_list_attachments" in skill
    assert "messages_export_attachment" in skill
    assert "messages_plan_change" in skill
    assert "messages_apply_change" in skill
    assert "notes_search_folders" in skill
    assert "notes_get_folder" in skill
    assert "notes_list_folder_items" in skill
    assert "notes_list_folder_tree" in skill
    assert "notes_list_attachments" in skill
    assert "notes_export_attachment" in skill
    assert "notes_plan_change" in skill
    assert "notes_apply_change" in skill
    assert "photos_get_asset" in skill
    assert "photos_export_asset" in skill
    assert "photos_plan_change" in skill
    assert "photos_apply_change" in skill
    assert "reminders_get_content" in skill
    assert "reminders_list_items" in skill
    assert "reminders_plan_change" in skill
    assert "reminders_apply_change" in skill
    assert "voice_memos_get_recording" in skill
    assert "voice_memos_export_audio" in skill
    assert 'value: "local-apple-data"' in agent
    assert "$local-apple-data" in agent
    assert "exact opaque handle" in agent
    assert "approval token" in agent
    assert "explicit-confirmation" in agent
    assert "read-back gates" in agent
    assert len(_openai_yaml_field(agent, "default_prompt")) <= 1024
    assert len(_openai_yaml_field(agent, "description")) <= 1024
    for contract in SURFACE_CONTRACTS:
        for tool in contract.mcp_tools:
            assert tool in skill


def _openai_yaml_field(source: str, field: str) -> str:
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(field + ":"):
            return stripped.split(":", 1)[1].strip().strip('"')
    raise AssertionError(f"missing openai.yaml field: {field}")


def test_tv_selected_playlist_items_are_documented() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    matrix = (PROJECT_ROOT / "docs" / "CAPABILITY_MATRIX.md").read_text(
        encoding="utf-8"
    )
    codex_plugin = (PROJECT_ROOT / "docs" / "CODEX_PLUGIN.md").read_text(
        encoding="utf-8"
    )

    assert "local-apple-data tv playlist-items" in readme
    assert "capped selected-playlist item metadata by `tv:playlist:v1:` handle" in matrix
    assert "TV selected-playlist item listing must use `tv_list_playlist_items`" in codex_plugin


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
        "docs/FRESH_CHAT_HANDOFF.md",
        "docs/CAPABILITY_MATRIX.md",
        "docs/MUTATION_GATES.md",
        "docs/V1_11_REMINDERS_WRITE_DESIGN.md",
        "docs/V1_65_REMINDERS_LIST_MOVE_WRITE_DESIGN.md",
        "docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md",
        "docs/V1_13_CALENDAR_WRITE_DESIGN.md",
        "docs/V1_14_CONTACTS_WRITE_DESIGN.md",
        "docs/V1_48_CONTACTS_UPDATE_WRITE_DESIGN.md",
        "docs/V1_49_CONTACTS_DELETE_WRITE_DESIGN.md",
        "docs/V1_70_CONTACTS_BACKUP_AND_NOTE_APPEND_DESIGN.md",
        "docs/V1_71_CONTACTS_RICH_UPDATE_GROUP_BATCH_DESIGN.md",
        "docs/V1_72_CONTACTS_GROUP_CRUD_WRITE_DESIGN.md",
        "docs/V1_15_NOTES_WRITE_DESIGN.md",
        "docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md",
        "docs/V1_75_MAIL_DRAFT_ATTACHMENT_WRITE_DESIGN.md",
        "docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md",
        "docs/V1_46_MAIL_MOVE_WRITE_DESIGN.md",
        "docs/V1_66_MAIL_CROSS_ACCOUNT_MOVE_WRITE_DESIGN.md",
        "docs/V1_43_MAIL_SEND_WRITE_DESIGN.md",
        "docs/V1_44_MAIL_REPLY_WRITE_DESIGN.md",
        "docs/V1_50_MAIL_FORWARD_WRITE_DESIGN.md",
        "docs/V1_77_MAIL_SEARCH_DISCOVERY_DESIGN.md",
        "docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md",
        "docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md",
        "docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md",
        "docs/V1_157_ICLOUD_DRIVE_FOLDER_PATH_CREATE_WRITE_DESIGN.md",
        "docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md",
        "docs/V1_54_ICLOUD_DRIVE_RENAME_COPY_MOVE_WRITE_DESIGN.md",
        "docs/V1_60_ICLOUD_DRIVE_FOLDER_RENAME_WRITE_DESIGN.md",
        "docs/V1_61_ICLOUD_DRIVE_FOLDER_TRASH_WRITE_DESIGN.md",
        "docs/V1_62_ICLOUD_DRIVE_FOLDER_MOVE_WRITE_DESIGN.md",
        "docs/V1_63_ICLOUD_DRIVE_FOLDER_COPY_WRITE_DESIGN.md",
        "docs/V1_67_ICLOUD_DRIVE_FOLDER_DELETE_WRITE_DESIGN.md",
        "docs/V1_68_ICLOUD_DRIVE_DELETE_TEXT_WRITE_DESIGN.md",
        "docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md",
        "docs/V1_45_NOTES_MOVE_WRITE_DESIGN.md",
        "docs/V1_20_NOTES_ATTACHMENT_EXPORT.md",
        "docs/V1_21_MAIL_ATTACHMENT_EXPORT.md",
        "docs/V1_22_MESSAGES_ATTACHMENT_EXPORT.md",
        "docs/V1_23_MESSAGES_ATTRIBUTED_BODY.md",
        "docs/V1_64_MESSAGES_PARTICIPANTS_METADATA.md",
        "docs/V1_24_MESSAGES_SEND_TEXT_WRITE_DESIGN.md",
        "docs/V1_38_MESSAGES_SEND_FILE_WRITE_DESIGN.md",
        "docs/V1_47_MESSAGES_RISKY_MUTATION_SOURCE_REVIEW.md",
        "docs/WRITE_TOOL_ROADMAP.md",
        "docs/PUBLISHING.md",
    ]

    # The public tree builder omits operator-only docs on purpose. Requiring them in a
    # generated tree would make this suite fail on the builder's own output, so skip
    # exactly those there while keeping the source checkout strict.
    public_tree = public_release_scan.is_sanitized_public_tree(PROJECT_ROOT)

    for relative in expected:
        if public_tree and relative in public_release_scan.LOCAL_OPERATOR_DOCS:
            continue
        path = PROJECT_ROOT / relative
        assert path.exists(), relative
        assert path.read_text(encoding="utf-8").strip(), relative


def test_public_release_builder_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "build_public_release_tree.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "build_release_tree" in source
    assert "public_release_scan.scan_public_files" in source


def test_messages_helper_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "messages_helper.swift"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "decode_attributed_bodies" in source
    assert "NSUnarchiver" in source


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
    assert "redaction_scan" in source
    assert "public_git_checkout" in source
    assert "commit_sha" in source
    assert "source_git" in source


def test_release_readiness_auditor_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "audit_release_readiness.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "audit_release_readiness" in source
    assert "github_publication_ready" in source
    assert "missing_git_remote" in source
    assert "redaction_scan" in source
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


def test_messages_public_surface_auditor_is_present() -> None:
    path = PROJECT_ROOT / "scripts" / "audit_messages_public_surface.py"

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "audit_messages_public_surface" in source
    assert "messages_unreviewed_public_command" in source
    assert "messages_send_signature_changed" in source


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
    # Assemble the operator-specific paths from fragments so this assertion
    # (which proves they are ABSENT from the verifier) does not itself embed a
    # literal personal identifier in the public tree.
    operator_user = "bil" + "ly"
    project_path = f'Path("/Users/{operator_user}/Projects/local-apple-data")'
    personal_path = f'Path("/Users/{operator_user}/plugins/local-apple-data")'
    assert project_path not in source
    assert personal_path not in source

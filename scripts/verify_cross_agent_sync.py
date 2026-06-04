#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PERSONAL_ROOT = Path.home() / "plugins/local-apple-data"
DEFAULT_PLUGIN_CACHE_ROOT = Path.home() / ".codex/plugins/cache/personal/local-apple-data"
CURSOR_SERVER_NAME = "local-apple-data"

SYNC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "CHANGELOG.md",
    "SECURITY.md",
    "pyproject.toml",
    ".codex-plugin/plugin.json",
    ".mcp.json",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    "docs/CAPABILITY_MATRIX.md",
    "docs/CODEX_PLUGIN.md",
    "docs/CROSS_AGENT_ROUTING.md",
    "docs/ECOSYSTEM_REVIEW.md",
    "docs/INSTALL.md",
    "docs/MACOS_SUPPORT.md",
    "docs/MUTATION_GATES.md",
    "docs/PRIVACY_MODEL.md",
    "docs/PUBLISHING.md",
    "docs/PUBLIC_RELEASE_MANIFEST.md",
    "docs/SAMPLE_OUTPUTS.md",
    "docs/TESTING.md",
    "docs/THREAT_MODEL.md",
    "docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md",
    "docs/V1_11_REMINDERS_WRITE_DESIGN.md",
    "docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md",
    "docs/V1_13_CALENDAR_WRITE_DESIGN.md",
    "docs/V1_14_CONTACTS_WRITE_DESIGN.md",
    "docs/V1_15_NOTES_WRITE_DESIGN.md",
    "docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md",
    "docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md",
    "docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md",
    "docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md",
    "docs/V1_20_NOTES_ATTACHMENT_EXPORT.md",
    "docs/V1_21_MAIL_ATTACHMENT_EXPORT.md",
    "docs/V1_22_MESSAGES_ATTACHMENT_EXPORT.md",
    "docs/V1_23_MESSAGES_ATTRIBUTED_BODY.md",
    "docs/V1_24_MESSAGES_SEND_TEXT_WRITE_DESIGN.md",
    "docs/V1_25_SAFARI_BOOKMARKS.md",
    "docs/V1_26_SHORTCUTS_METADATA.md",
    "docs/V1_27_BOOKS_METADATA.md",
    "docs/V1_28_PODCASTS_METADATA.md",
    "docs/WRITE_TOOL_ROADMAP.md",
    "scripts/audit_release_readiness.py",
    "scripts/audit_mutation_gates.py",
    "scripts/audit_surface_contract.py",
    "scripts/audit_write_design_gates.py",
    "scripts/contacts_helper.swift",
    "scripts/eventkit_helper.swift",
    "scripts/messages_helper.swift",
    "scripts/photos_helper.swift",
    "scripts/build_public_release_tree.py",
    "scripts/generate_release_receipt.py",
    "scripts/prepare_public_git_checkout.py",
    "scripts/public_release_scan.py",
    "scripts/redaction_scan.py",
    "scripts/render_mcp_client_config.py",
    "scripts/run_mcp_server.sh",
    "scripts/verify_runtime.py",
    "scripts/verify_cross_agent_sync.py",
    "skills/local-apple-data/SKILL.md",
    "skills/local-apple-data/agents/openai.yaml",
    "src/local_apple_data/cli.py",
    "src/local_apple_data/health.py",
    "src/local_apple_data/mcp_server.py",
    "src/local_apple_data/adapters/books.py",
    "src/local_apple_data/adapters/calendar.py",
    "src/local_apple_data/adapters/contacts.py",
    "src/local_apple_data/adapters/hide_my_email.py",
    "src/local_apple_data/adapters/icloud_drive.py",
    "src/local_apple_data/adapters/mail.py",
    "src/local_apple_data/adapters/messages.py",
    "src/local_apple_data/adapters/notes.py",
    "src/local_apple_data/adapters/photos.py",
    "src/local_apple_data/adapters/podcasts.py",
    "src/local_apple_data/adapters/reminders.py",
    "src/local_apple_data/adapters/safari.py",
    "src/local_apple_data/adapters/shortcuts.py",
    "src/local_apple_data/adapters/voice_memos.py",
    "tests/test_cli_safari.py",
    "tests/test_cli_shortcuts.py",
    "tests/test_cli_books.py",
    "tests/test_cli_podcasts.py",
    "tests/test_safari_adapter.py",
    "tests/test_shortcuts_adapter.py",
    "tests/test_books_adapter.py",
    "tests/test_podcasts_adapter.py",
]


def _run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} exited {result.returncode}")
    return result.stdout


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _version(project_root: Path) -> str:
    return str(_load_json(project_root / ".codex-plugin/plugin.json")["version"])


def _assert_same_files(project_root: Path, personal_root: Path, cache_root: Path) -> None:
    for relative in SYNC_FILES:
        source = project_root / relative
        personal = personal_root / relative
        cache = cache_root / relative
        if not source.exists():
            raise RuntimeError(f"missing source file: {relative}")
        if not personal.exists() or source.read_bytes() != personal.read_bytes():
            raise RuntimeError(f"personal source mismatch: {relative}")
        if not cache.exists() or source.read_bytes() != cache.read_bytes():
            raise RuntimeError(f"installed cache mismatch: {relative}")


def _check_codex(version: str, plugin_cache_root: Path) -> Path:
    cache_root = plugin_cache_root / version
    if not cache_root.exists():
        raise RuntimeError("installed Codex cache version is missing")
    listing = _run(["codex", "plugin", "list"], cwd=Path.home())
    found = False
    for line in listing.splitlines():
        fields = line.split()
        if fields and fields[0] == "local-apple-data@personal" and version in fields:
            found = True
            break
    if not found:
        raise RuntimeError("Codex plugin list does not show the expected installed version")
    return cache_root


def _check_claude() -> None:
    listing = _run(["claude", "mcp", "list"], cwd=Path.home())
    matching = [line for line in listing.splitlines() if line.startswith("local-apple-data:")]
    if not matching:
        raise RuntimeError("Claude MCP server local-apple-data is missing")
    if "Connected" not in matching[0]:
        raise RuntimeError("Claude MCP server local-apple-data is not connected")


def _check_openclaw(project_root: Path) -> None:
    runner = project_root / "scripts/run_mcp_server.sh"
    payload = _run(["openclaw", "mcp", "show", "local-apple-data", "--json"], cwd=project_root)
    config = json.loads(payload)
    if config.get("command") != str(runner):
        raise RuntimeError("OpenClaw MCP command does not match the project runner")
    if config.get("args") != []:
        raise RuntimeError("OpenClaw MCP args should be empty")
    if config.get("cwd") != str(project_root):
        raise RuntimeError("OpenClaw MCP cwd does not match the project root")


def _cursor_config_candidates(project_root: Path, cursor_config: Path | None) -> list[Path]:
    if cursor_config is not None:
        return [cursor_config.expanduser().resolve()]
    return [
        (project_root / ".cursor/mcp.json").resolve(),
        (Path.home() / ".cursor/mcp.json").resolve(),
    ]


def _resolve_cursor_command(command: Any, *, config_path: Path) -> str | None:
    if not isinstance(command, str):
        return None
    if "${workspaceFolder}" not in command:
        return command
    if config_path.name != "mcp.json" or config_path.parent.name != ".cursor":
        return command
    workspace_root = config_path.parent.parent
    return command.replace("${workspaceFolder}", str(workspace_root))


def _check_cursor(
    project_root: Path,
    *,
    cursor_config: Path | None,
    require_cursor: bool,
) -> tuple[str, str | None]:
    runner = project_root / "scripts/run_mcp_server.sh"
    checked_existing_config = False
    for config_path in _cursor_config_candidates(project_root, cursor_config):
        if not config_path.exists():
            continue
        checked_existing_config = True
        payload = _load_json(config_path)
        servers = payload.get("mcpServers")
        if not isinstance(servers, dict):
            if cursor_config is not None:
                raise RuntimeError("Cursor MCP config is missing mcpServers")
            continue
        server = servers.get(CURSOR_SERVER_NAME)
        if server is None:
            if cursor_config is not None:
                raise RuntimeError("Cursor MCP server local-apple-data is missing")
            continue
        if not isinstance(server, dict):
            raise RuntimeError("Cursor MCP server local-apple-data is not an object")
        if server.get("type") not in (None, "stdio"):
            raise RuntimeError("Cursor MCP server local-apple-data is not stdio")
        if _resolve_cursor_command(server.get("command"), config_path=config_path) != str(runner):
            raise RuntimeError("Cursor MCP command does not match the project runner")
        if server.get("args", []) != []:
            raise RuntimeError("Cursor MCP args should be empty")
        return "mcp_configured", str(config_path)

    if require_cursor:
        if checked_existing_config:
            raise RuntimeError("Cursor MCP server local-apple-data is missing")
        raise RuntimeError("Cursor MCP config is missing")
    return "not_configured", None


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify local-apple-data source, installed plugin, and MCP client sync."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=_path_from_env("LOCAL_APPLE_DATA_PROJECT_ROOT", DEFAULT_PROJECT_ROOT),
        help="Canonical project root. Defaults to this script's repo root.",
    )
    parser.add_argument(
        "--personal-root",
        type=Path,
        default=_path_from_env("LOCAL_APPLE_DATA_PERSONAL_ROOT", DEFAULT_PERSONAL_ROOT),
        help="Personal plugin source root. Defaults to ~/plugins/local-apple-data.",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=_path_from_env("LOCAL_APPLE_DATA_CACHE_ROOT", DEFAULT_PLUGIN_CACHE_ROOT),
        help="Codex installed plugin cache root. Defaults to ~/.codex/plugins/cache/personal/local-apple-data.",
    )
    parser.add_argument("--skip-codex", action="store_true", help="Skip Codex install/cache checks.")
    parser.add_argument("--skip-claude", action="store_true", help="Skip Claude MCP connectivity checks.")
    parser.add_argument("--skip-openclaw", action="store_true", help="Skip OpenClaw MCP config checks.")
    parser.add_argument("--skip-cursor", action="store_true", help="Skip Cursor MCP config checks.")
    parser.add_argument(
        "--require-cursor",
        action="store_true",
        help="Fail if no Cursor MCP config contains local-apple-data.",
    )
    parser.add_argument(
        "--cursor-config",
        type=Path,
        default=None,
        help="Specific Cursor mcp.json to verify. Defaults to project .cursor/mcp.json then ~/.cursor/mcp.json.",
    )
    parser.add_argument("--skip-file-sync", action="store_true", help="Skip source/personal/cache file comparison.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    personal_root = args.personal_root.expanduser().resolve()
    plugin_cache_root = args.cache_root.expanduser().resolve()
    runner = project_root / "scripts/run_mcp_server.sh"

    version = _version(project_root)
    cache_root: Path | None = None
    surfaces: dict[str, str] = {}
    if args.skip_codex:
        surfaces["codex"] = "skipped"
    else:
        cache_root = _check_codex(version, plugin_cache_root)
        surfaces["codex"] = "installed_enabled"
    if args.skip_file_sync:
        file_sync = "skipped"
    elif cache_root is None:
        raise RuntimeError("file sync check requires Codex cache unless --skip-file-sync is set")
    else:
        _assert_same_files(project_root, personal_root, cache_root)
        file_sync = "ok"
    if args.skip_claude:
        surfaces["claude"] = "skipped"
    else:
        _check_claude()
        surfaces["claude"] = "mcp_connected"
    if args.skip_openclaw:
        surfaces["openclaw"] = "skipped"
    else:
        _check_openclaw(project_root)
        surfaces["openclaw"] = "mcp_configured"
    cursor_config: str | None = None
    if args.skip_cursor:
        surfaces["cursor"] = "skipped"
    else:
        cursor_status, cursor_config = _check_cursor(
            project_root,
            cursor_config=args.cursor_config,
            require_cursor=args.require_cursor,
        )
        surfaces["cursor"] = cursor_status
    summary = {
        "status": "ok",
        "plugin": "local-apple-data",
        "version": version,
        "project_root": str(project_root),
        "personal_root": str(personal_root),
        "installed_cache": str(cache_root) if cache_root is not None else None,
        "runner": str(runner),
        "file_sync": file_sync,
        "checked_files": len(SYNC_FILES),
        "surfaces": surfaces,
        "cursor_config": cursor_config,
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1)

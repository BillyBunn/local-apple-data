from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_cross_agent_sync.py"
SPEC = importlib.util.spec_from_file_location("verify_cross_agent_sync", SCRIPT_PATH)
assert SPEC is not None
verify_cross_agent_sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["verify_cross_agent_sync"] = verify_cross_agent_sync
SPEC.loader.exec_module(verify_cross_agent_sync)


def _make_project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    runner = scripts / "run_mcp_server.sh"
    runner.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return root


def _write_cursor_config(path: Path, server: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"mcpServers": {"local-apple-data": server}}, indent=2),
        encoding="utf-8",
    )


def test_cursor_check_is_optional_when_no_config_exists(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    status, config = verify_cross_agent_sync._check_cursor(
        root,
        cursor_config=tmp_path / "missing.json",
        require_cursor=False,
    )

    assert status == "not_configured"
    assert config is None


def test_cursor_check_accepts_project_workspace_folder_command(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)
    config_path = root / ".cursor" / "mcp.json"
    _write_cursor_config(
        config_path,
        {
            "type": "stdio",
            "command": "${workspaceFolder}/scripts/run_mcp_server.sh",
            "args": [],
        },
    )

    status, config = verify_cross_agent_sync._check_cursor(
        root,
        cursor_config=config_path,
        require_cursor=True,
    )

    assert status == "mcp_configured"
    assert config == str(config_path.resolve())


def test_cursor_check_accepts_explicit_absolute_command(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)
    config_path = tmp_path / "cursor-mcp.json"
    _write_cursor_config(
        config_path,
        {
            "type": "stdio",
            "command": str(root / "scripts" / "run_mcp_server.sh"),
            "args": [],
        },
    )

    status, config = verify_cross_agent_sync._check_cursor(
        root,
        cursor_config=config_path,
        require_cursor=True,
    )

    assert status == "mcp_configured"
    assert config == str(config_path.resolve())


def test_cursor_check_can_require_config(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    try:
        verify_cross_agent_sync._check_cursor(
            root,
            cursor_config=tmp_path / "missing.json",
            require_cursor=True,
        )
    except RuntimeError as exc:
        assert "Cursor MCP config is missing" in str(exc)
    else:
        raise AssertionError("expected missing Cursor config failure")


def test_cursor_check_rejects_wrong_runner(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)
    config_path = root / ".cursor" / "mcp.json"
    _write_cursor_config(
        config_path,
        {
            "type": "stdio",
            "command": "/tmp/not-local-apple-data",
            "args": [],
        },
    )

    try:
        verify_cross_agent_sync._check_cursor(
            root,
            cursor_config=config_path,
            require_cursor=True,
        )
    except RuntimeError as exc:
        assert "Cursor MCP command" in str(exc)
    else:
        raise AssertionError("expected wrong Cursor runner failure")

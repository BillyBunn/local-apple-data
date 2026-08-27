from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_mcp_client_config.py"
SPEC = importlib.util.spec_from_file_location("render_mcp_client_config", SCRIPT_PATH)
assert SPEC is not None
render_mcp_client_config = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["render_mcp_client_config"] = render_mcp_client_config
SPEC.loader.exec_module(render_mcp_client_config)


def _make_project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    scripts.joinpath("run_mcp_server.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return root


def test_render_cursor_config_uses_workspace_folder(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    payload = render_mcp_client_config.render_config(client="cursor", project_root=root)
    server = payload["mcpServers"]["local-apple-data"]

    assert server == {
        "type": "stdio",
        "command": "${workspaceFolder}/scripts/run_mcp_server.sh",
        "args": [],
    }


def test_render_cursor_config_can_use_absolute_runner(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    payload = render_mcp_client_config.render_config(
        client="cursor",
        project_root=root,
        absolute=True,
    )
    server = payload["mcpServers"]["local-apple-data"]

    assert server["type"] == "stdio"
    assert server["command"] == str(root / "scripts" / "run_mcp_server.sh")
    assert server["args"] == []


def test_render_claude_code_config_uses_project_mcp_shape(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    payload = render_mcp_client_config.render_config(client="claude-code", project_root=root)
    server = payload["mcpServers"]["local-apple-data"]

    assert server == {
        "command": str(root / "scripts" / "run_mcp_server.sh"),
        "args": [],
    }


def test_render_generic_config_uses_absolute_runner_and_cwd(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    payload = render_mcp_client_config.render_config(client="generic", project_root=root)
    server = payload["mcpServers"]["local-apple-data"]

    assert server["command"] == str(root / "scripts" / "run_mcp_server.sh")
    assert server["args"] == []
    assert server["cwd"] == str(root)


def test_render_openclaw_config_uses_absolute_runner_and_cwd(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    payload = render_mcp_client_config.render_config(client="openclaw", project_root=root)
    server = payload["mcpServers"]["local-apple-data"]

    assert server["command"] == str(root / "scripts" / "run_mcp_server.sh")
    assert server["args"] == []
    assert server["cwd"] == str(root)


def test_render_server_config_can_return_unwrapped_server(tmp_path: Path) -> None:
    root = _make_project_root(tmp_path)

    server = render_mcp_client_config.render_server_config(
        client="openclaw",
        project_root=root,
    )

    assert server == {
        "command": str(root / "scripts" / "run_mcp_server.sh"),
        "args": [],
        "cwd": str(root),
    }


def test_main_can_print_compact_server_only_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = _make_project_root(tmp_path)

    status = render_mcp_client_config.main(
        [
            "--client",
            "claude-code",
            "--project-root",
            str(root),
            "--server-only",
            "--compact",
        ]
    )

    assert status == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == {
        "command": str(root / "scripts" / "run_mcp_server.sh"),
        "args": [],
    }
    assert output.count("\n") == 1


def test_main_redacts_missing_runner_failure(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    try:
        render_mcp_client_config.render_config(client="generic", project_root=tmp_path)
    except ValueError as exc:
        assert "runner" in str(exc)
    else:
        raise AssertionError("expected missing runner failure")

    status = render_mcp_client_config.main(["--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "MCP config render failed: ValueError\n"
    assert str(tmp_path) not in captured.err
    assert "runner" not in captured.err


def test_render_config_fails_when_runner_missing(tmp_path: Path) -> None:
    try:
        render_mcp_client_config.render_config(client="generic", project_root=tmp_path)
    except ValueError as exc:
        assert "runner" in str(exc)
    else:
        raise AssertionError("expected missing runner failure")

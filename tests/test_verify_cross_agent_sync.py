from __future__ import annotations

import importlib.util
import json
import subprocess
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
    plugin = root / ".codex-plugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text('{"version": "0.0.0-test"}\n', encoding="utf-8")
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


def test_project_root_resolves_from_configured_openclaw_runner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)
    configured_root = _make_project_root(tmp_path / "configured")

    def fake_run(command: list[str], *, cwd: Path) -> str:
        assert command == ["openclaw", "mcp", "show", "local-apple-data", "--json"]
        assert cwd == default_root
        return json.dumps(
            {
                "command": str(configured_root / "scripts" / "run_mcp_server.sh"),
                "args": [],
                "cwd": str(configured_root),
            }
        )

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)
    monkeypatch.setattr(verify_cross_agent_sync, "DEFAULT_PROJECT_ROOT", default_root)
    monkeypatch.delenv(verify_cross_agent_sync.PROJECT_ROOT_ENV, raising=False)

    resolved = verify_cross_agent_sync._resolve_project_root(None, skip_openclaw=False)

    assert resolved == configured_root.resolve()


def test_project_root_resolution_skips_openclaw_when_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)

    def fake_run(command: list[str], *, cwd: Path) -> str:
        raise AssertionError("OpenClaw should not be called")

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)
    monkeypatch.setattr(verify_cross_agent_sync, "DEFAULT_PROJECT_ROOT", default_root)
    monkeypatch.delenv(verify_cross_agent_sync.PROJECT_ROOT_ENV, raising=False)

    resolved = verify_cross_agent_sync._resolve_project_root(None, skip_openclaw=True)

    assert resolved == default_root.resolve()


def test_project_root_env_overrides_openclaw_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)
    env_root = _make_project_root(tmp_path / "env")

    def fake_run(command: list[str], *, cwd: Path) -> str:
        raise AssertionError("OpenClaw should not be called")

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)
    monkeypatch.setattr(verify_cross_agent_sync, "DEFAULT_PROJECT_ROOT", default_root)
    monkeypatch.setenv(verify_cross_agent_sync.PROJECT_ROOT_ENV, str(env_root))

    resolved = verify_cross_agent_sync._resolve_project_root(None, skip_openclaw=False)

    assert resolved == env_root.resolve()


def test_project_root_argument_overrides_env_and_openclaw(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)
    env_root = _make_project_root(tmp_path / "env")
    explicit_root = _make_project_root(tmp_path / "explicit")

    def fake_run(command: list[str], *, cwd: Path) -> str:
        raise AssertionError("OpenClaw should not be called")

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)
    monkeypatch.setattr(verify_cross_agent_sync, "DEFAULT_PROJECT_ROOT", default_root)
    monkeypatch.setenv(verify_cross_agent_sync.PROJECT_ROOT_ENV, str(env_root))

    resolved = verify_cross_agent_sync._resolve_project_root(
        explicit_root,
        skip_openclaw=False,
    )

    assert resolved == explicit_root.resolve()


def test_configured_openclaw_root_rejects_non_empty_args(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)
    configured_root = _make_project_root(tmp_path / "configured")

    def fake_run(command: list[str], *, cwd: Path) -> str:
        return json.dumps(
            {
                "command": str(configured_root / "scripts" / "run_mcp_server.sh"),
                "args": ["--unexpected"],
                "cwd": str(configured_root),
            }
        )

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)

    assert verify_cross_agent_sync._configured_project_root_from_openclaw(default_root) is None


def test_configured_openclaw_root_rejects_wrong_runner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)
    configured_root = _make_project_root(tmp_path / "configured")

    def fake_run(command: list[str], *, cwd: Path) -> str:
        return json.dumps(
            {
                "command": str(configured_root / "scripts" / "not-the-runner.sh"),
                "args": [],
                "cwd": str(configured_root),
            }
        )

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)

    assert verify_cross_agent_sync._configured_project_root_from_openclaw(default_root) is None


def test_configured_openclaw_root_requires_plugin_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    default_root = _make_project_root(tmp_path)
    configured_root = _make_project_root(tmp_path / "configured")
    (configured_root / ".codex-plugin" / "plugin.json").unlink()

    def fake_run(command: list[str], *, cwd: Path) -> str:
        return json.dumps(
            {
                "command": str(configured_root / "scripts" / "run_mcp_server.sh"),
                "args": [],
                "cwd": str(configured_root),
            }
        )

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)

    assert verify_cross_agent_sync._configured_project_root_from_openclaw(default_root) is None


def test_openclaw_check_accepts_normalized_equivalent_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checked_root = _make_project_root(tmp_path)

    def fake_run(command: list[str], *, cwd: Path) -> str:
        return json.dumps(
            {
                "command": str(
                    checked_root / "scripts" / ".." / "scripts" / "run_mcp_server.sh"
                ),
                "args": [],
                "cwd": str(checked_root / "."),
            }
        )

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)

    verify_cross_agent_sync._check_openclaw(checked_root)


def test_openclaw_mismatch_error_includes_project_root_hint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checked_root = _make_project_root(tmp_path)
    configured_root = _make_project_root(tmp_path / "configured")

    def fake_run(command: list[str], *, cwd: Path) -> str:
        return json.dumps(
            {
                "command": str(configured_root / "scripts" / "run_mcp_server.sh"),
                "args": [],
                "cwd": str(configured_root),
            }
        )

    monkeypatch.setattr(verify_cross_agent_sync, "_run", fake_run)

    try:
        verify_cross_agent_sync._check_openclaw(checked_root)
    except RuntimeError as exc:
        message = str(exc)
        assert "OpenClaw MCP command does not match" in message
        assert "--project-root" in message
        assert str(configured_root) in message
    else:
        raise AssertionError("expected OpenClaw runner mismatch failure")


def test_openclaw_hint_is_empty_for_non_runner_command(tmp_path: Path) -> None:
    configured_root = _make_project_root(tmp_path)

    hint = verify_cross_agent_sync._project_root_hint_from_openclaw_config(
        {
            "command": str(configured_root / "scripts" / "other.sh"),
            "cwd": str(configured_root),
        }
    )

    assert hint == ""


def test_sync_files_cover_release_tooling_tests() -> None:
    expected = {
        ".gitignore",
        "AGENTS.md",
        "uv.lock",
        "tests/test_build_public_release_tree.py",
        "tests/test_generate_release_receipt.py",
        "tests/test_mutation_gate_audit.py",
        "tests/test_plugin_packaging.py",
        "tests/test_prepare_public_git_checkout.py",
        "tests/test_public_release_scan.py",
        "tests/test_redaction_scan_script.py",
        "tests/test_release_readiness_audit.py",
        "tests/test_render_mcp_client_config.py",
        "tests/test_surface_contract_audit.py",
        "tests/test_verify_cross_agent_sync.py",
        "tests/test_write_design_gate_audit.py",
    }

    project_root = SCRIPT_PATH.parents[1]

    assert expected <= set(verify_cross_agent_sync._sync_files(project_root))


def test_safe_error_message_redacts_unexpected_exception_text() -> None:
    assert (
        verify_cross_agent_sync._safe_error_message(
            RuntimeError("personal source mismatch: README.md")
        )
        == "personal source mismatch: README.md"
    )
    subclass_message = verify_cross_agent_sync._safe_error_message(
        NotImplementedError("permission denied for /private/local/cache")
    )
    message = verify_cross_agent_sync._safe_error_message(
        OSError("permission denied for /private/local/cache")
    )
    unsafe_runtime_message = verify_cross_agent_sync._safe_error_message(
        RuntimeError("permission denied for /private/local/cache")
    )
    path_runtime_message = verify_cross_agent_sync._safe_error_message(
        RuntimeError("OpenClaw configured project root appears to be /Users/example/project")
    )

    assert subclass_message == "NotImplementedError"
    assert "/private/" not in subclass_message
    assert message == "OSError"
    assert "permission denied" not in message
    assert "/private/" not in message
    assert unsafe_runtime_message == "RuntimeError"
    assert path_runtime_message == "RuntimeError"


def test_cli_redacts_unexpected_top_level_errors(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--project-root",
            str(missing_root),
            "--skip-codex",
            "--skip-file-sync",
            "--skip-claude",
            "--skip-openclaw",
            "--skip-cursor",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"message": "FileNotFoundError", "status": "error"}
    assert str(missing_root) not in result.stderr


def test_main_reports_claude_status_as_cli_connection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_version",
        lambda project_root: "0.0.0-test",
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_codex",
        lambda version, plugin_cache_root: cache_root,
    )
    monkeypatch.setattr(verify_cross_agent_sync, "_assert_same_files", lambda *args: 7)
    monkeypatch.setattr(verify_cross_agent_sync, "_check_claude", lambda: None)
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_openclaw",
        lambda project_root: None,
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_cursor",
        lambda project_root, *, cursor_config, require_cursor: ("mcp_configured", None),
    )
    monkeypatch.setattr(verify_cross_agent_sync, "_process_rows", lambda: [])

    status = verify_cross_agent_sync.main(
        [
            "--project-root",
            str(root),
            "--personal-root",
            str(personal_root),
            "--cache-root",
            str(cache_root),
        ]
    )

    # main() now returns an exit code (0 = all surfaces ok, 1 = a surface errored) so callers/CI
    # can detect a degraded cross-agent state; this all-success case returns 0.
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surfaces"]["claude"] == "mcp_cli_connected"
    assert payload["surfaces"]["claude"] != "mcp_connected"
    assert payload["live_mcp_processes"]["status"] == "ok"


def test_live_mcp_process_check_flags_stale_installed_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    current = cache_root / "0.0.0-current"
    stale = cache_root / "0.0.0-old"

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_rows",
        lambda: [
            (
                101,
                1,
                f"{current}/.venv/bin/python -m local_apple_data.mcp_server",
            ),
            (
                102,
                1,
                f"{project_root}/.venv/bin/python -m local_apple_data.mcp_server",
            ),
            (
                103,
                1,
                f"{stale}/.venv/bin/python -m local_apple_data.mcp_server",
            ),
        ],
    )

    payload = verify_cross_agent_sync._check_live_mcp_processes(
        project_root=project_root,
        personal_root=personal_root,
        plugin_cache_root=cache_root,
        version="0.0.0-current",
    )

    assert payload["status"] == "error"
    assert payload["current_cache_count"] == 1
    assert payload["project_root_count"] == 1
    assert payload["running_count"] == 3
    assert payload["stale_processes"] == [
        {
            "kind": "stale_installed_cache_process",
            "pid": 103,
            "ppid": 1,
            "version": "0.0.0-old",
        }
    ]
    assert payload["unknown_processes"] == []


def test_live_mcp_process_check_flags_unknown_and_prefix_processes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    project_prefix = project_root.with_name(f"{project_root.name}-old")

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_rows",
        lambda: [
            (
                111,
                1,
                f"{project_prefix}/.venv/bin/python -m local_apple_data.mcp_server",
            ),
            (
                112,
                1,
                "/tmp/other/.venv/bin/python -m local_apple_data.mcp_server",
            ),
        ],
    )

    payload = verify_cross_agent_sync._check_live_mcp_processes(
        project_root=project_root,
        personal_root=personal_root,
        plugin_cache_root=cache_root,
        version="0.0.0-current",
    )

    assert payload["status"] == "error"
    assert payload["project_root_count"] == 0
    assert payload["unknown_processes"] == [
        {"kind": "unknown_mcp_process", "pid": 111, "ppid": 1, "version": ""},
        {"kind": "unknown_mcp_process", "pid": 112, "ppid": 1, "version": ""},
    ]


def test_live_mcp_process_check_accepts_project_venv_python_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    external_python = tmp_path / "uv-python"
    external_python.write_text("# synthetic interpreter\n", encoding="utf-8")
    project_python = project_root / ".venv/bin/python"
    project_python.parent.mkdir(parents=True)
    project_python.symlink_to(external_python)

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_rows",
        lambda: [
            (
                121,
                1,
                f"{project_python} -m local_apple_data.mcp_server",
            )
        ],
    )

    payload = verify_cross_agent_sync._check_live_mcp_processes(
        project_root=project_root,
        personal_root=personal_root,
        plugin_cache_root=cache_root,
        version="0.0.0-current",
    )

    assert payload["status"] == "ok"
    assert payload["project_root_count"] == 1
    assert payload["unknown_processes"] == []


def test_live_mcp_process_check_ignores_shell_substring_false_positive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_rows",
        lambda: [
            (
                131,
                1,
                "/bin/zsh -lc 'echo -m local_apple_data.mcp_server'",
            ),
            (
                132,
                1,
                f"{project_root}/.venv/bin/python -m local_apple_data.mcp_server",
            ),
        ],
    )

    payload = verify_cross_agent_sync._check_live_mcp_processes(
        project_root=project_root,
        personal_root=personal_root,
        plugin_cache_root=cache_root,
        version="0.0.0-current",
    )

    assert payload["status"] == "ok"
    assert payload["running_count"] == 1
    assert payload["project_root_count"] == 1
    assert payload["unknown_processes"] == []


def test_live_mcp_process_check_accepts_pathless_codex_process_by_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    current_cache = cache_root / "0.0.0-current"

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_rows",
        lambda: [
            (
                141,
                1,
                "uv run --no-project --with mcp>=1.0,<2 python -m local_apple_data.mcp_server",
            ),
            (
                142,
                141,
                "/tmp/uv-build/bin/python -m local_apple_data.mcp_server",
            ),
        ],
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_cwd",
        lambda pid: current_cache if pid in {141, 142} else None,
    )

    payload = verify_cross_agent_sync._check_live_mcp_processes(
        project_root=project_root,
        personal_root=personal_root,
        plugin_cache_root=cache_root,
        version="0.0.0-current",
    )

    assert payload["status"] == "ok"
    assert payload["current_cache_count"] == 2
    assert payload["running_count"] == 2
    assert payload["unknown_processes"] == []


def test_main_reports_stale_live_mcp_processes_as_degraded(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_version",
        lambda project_root: "0.0.0-current",
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_codex",
        lambda version, plugin_cache_root: cache_root / version,
    )
    monkeypatch.setattr(verify_cross_agent_sync, "_assert_same_files", lambda *args: 7)
    monkeypatch.setattr(verify_cross_agent_sync, "_check_claude", lambda: None)
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_openclaw",
        lambda project_root: None,
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_cursor",
        lambda project_root, *, cursor_config, require_cursor: ("mcp_configured", None),
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_process_rows",
        lambda: [
            (
                201,
                1,
                f"{cache_root}/0.0.0-old/.venv/bin/python -m local_apple_data.mcp_server",
            )
        ],
    )

    status = verify_cross_agent_sync.main(
        [
            "--project-root",
            str(root),
            "--personal-root",
            str(personal_root),
            "--cache-root",
            str(cache_root),
        ]
    )

    assert status == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "degraded"
    assert payload["errors"] == ["live_mcp_processes"]
    assert payload["live_mcp_processes"]["stale_processes"][0]["version"] == "0.0.0-old"


def test_main_reports_live_process_check_failure_as_degraded(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"

    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_version",
        lambda project_root: "0.0.0-current",
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_codex",
        lambda version, plugin_cache_root: cache_root / version,
    )
    monkeypatch.setattr(verify_cross_agent_sync, "_assert_same_files", lambda *args: 7)
    monkeypatch.setattr(verify_cross_agent_sync, "_check_claude", lambda: None)
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_openclaw",
        lambda project_root: None,
    )
    monkeypatch.setattr(
        verify_cross_agent_sync,
        "_check_cursor",
        lambda project_root, *, cursor_config, require_cursor: ("mcp_configured", None),
    )

    def fail_process_rows() -> list[tuple[int, int, str]]:
        raise RuntimeError("ps timed out")

    monkeypatch.setattr(verify_cross_agent_sync, "_process_rows", fail_process_rows)

    status = verify_cross_agent_sync.main(
        [
            "--project-root",
            str(root),
            "--personal-root",
            str(personal_root),
            "--cache-root",
            str(cache_root),
        ]
    )

    assert status == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "degraded"
    assert payload["errors"] == ["live_mcp_processes"]
    assert payload["live_mcp_processes"] == {"message": "ps timed out", "status": "error"}


def test_sync_files_cover_runtime_package_and_tests() -> None:
    project_root = SCRIPT_PATH.parents[1]
    expected = {
        path.relative_to(project_root).as_posix()
        for root in (project_root / "src/local_apple_data", project_root / "tests")
        for path in root.rglob("*.py")
    }

    assert expected <= set(verify_cross_agent_sync._sync_files(project_root))


def test_sync_files_cover_nested_resources_and_exclude_generated_files(
    tmp_path: Path,
) -> None:
    project_root = _make_project_root(tmp_path)
    included = {
        "docs/nested/NOTE.txt": "doc\n",
        "scripts/helpers/tool.sh": "#!/bin/sh\n",
        "skills/local-apple-data/agents/anthropic.yaml": "name: test\n",
        ".codex-plugin/runtime.json": "{}\n",
        ".github/workflows/test.yml": "name: test\n",
        "src/local_apple_data/resources/schema.json": "{}\n",
        "tests/integration/fixture.txt": "fixture\n",
    }
    excluded = {
        "scripts/.DS_Store": "finder\n",
        "scripts/__pycache__/dynamic.cpython-312.pyc": "bytecode\n",
        "src/local_apple_data/__pycache__/dynamic.cpython-312.pyc": "bytecode\n",
        "tests/.pytest_cache/cache.txt": "cache\n",
    }
    for relative, content in {**included, **excluded}.items():
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    sync_files = set(verify_cross_agent_sync._sync_files(project_root))

    assert set(included) <= sync_files
    assert not set(excluded) & sync_files


def test_assert_same_files_returns_dynamic_checked_count(tmp_path: Path) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    for root in (project_root, personal_root, cache_root):
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "src/local_apple_data").mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(exist_ok=True)
        (root / "scripts").mkdir(exist_ok=True)
        (root / "docs" / "DYNAMIC.md").write_text("doc\n", encoding="utf-8")
        (root / "src/local_apple_data" / "dynamic.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "tests" / "test_dynamic.py").write_text("def test_dynamic(): pass\n", encoding="utf-8")
        (root / "scripts" / "dynamic.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    for relative in verify_cross_agent_sync.STATIC_SYNC_FILES:
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("static\n", encoding="utf-8")
    for relative in verify_cross_agent_sync._sync_files(project_root):
        source = project_root / relative
        for root in (personal_root, cache_root):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())

    checked = verify_cross_agent_sync._assert_same_files(
        project_root,
        personal_root,
        cache_root,
    )

    assert checked == len(verify_cross_agent_sync._sync_files(project_root))


def test_assert_same_files_reports_bounded_aggregate_mismatches(
    tmp_path: Path,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    for relative in verify_cross_agent_sync.STATIC_SYNC_FILES:
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("static\n", encoding="utf-8")
    dynamic = project_root / "docs" / "DYNAMIC.md"
    dynamic.parent.mkdir(parents=True, exist_ok=True)
    dynamic.write_text("dynamic\n", encoding="utf-8")
    for relative in verify_cross_agent_sync._sync_files(project_root):
        source = project_root / relative
        for root in (personal_root, cache_root):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())
    (personal_root / "README.md").write_text("different\n", encoding="utf-8")
    (personal_root / "docs" / "DYNAMIC.md").unlink()
    (cache_root / "CHANGELOG.md").unlink()

    try:
        verify_cross_agent_sync._assert_same_files(
            project_root,
            personal_root,
            cache_root,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected aggregate mismatch failure")

    assert "file sync mismatches (3)" in message
    assert "personal source mismatch: README.md" in message
    assert "personal source missing: docs/DYNAMIC.md" in message
    assert "installed cache missing: CHANGELOG.md" in message
    assert "different" not in message
    assert "dynamic\n" not in message


def test_assert_same_files_truncates_aggregate_mismatch_output(
    tmp_path: Path,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    personal_root.mkdir()
    cache_root.mkdir()
    for relative in verify_cross_agent_sync.STATIC_SYNC_FILES:
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("static\n", encoding="utf-8")

    try:
        verify_cross_agent_sync._assert_same_files(
            project_root,
            personal_root,
            cache_root,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected aggregate mismatch failure")

    assert "more mismatch(es)" in message
    assert message.count(" missing: ") <= verify_cross_agent_sync.MAX_FILE_SYNC_MISMATCHES


def test_assert_same_files_redacts_read_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _make_project_root(tmp_path)
    personal_root = tmp_path / "personal"
    cache_root = tmp_path / "cache"
    for relative in verify_cross_agent_sync.STATIC_SYNC_FILES:
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("static\n", encoding="utf-8")
    for relative in verify_cross_agent_sync._sync_files(project_root):
        source = project_root / relative
        for root in (personal_root, cache_root):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())
    read_errors = {
        project_root / "README.md": OSError("permission denied for /private/source"),
        personal_root / "CHANGELOG.md": OSError(
            "permission denied for /private/personal"
        ),
        cache_root / "LICENSE": OSError("permission denied for /private/cache"),
    }
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(path: Path) -> bytes:
        error = read_errors.get(path)
        if error is not None:
            raise error
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    try:
        verify_cross_agent_sync._assert_same_files(
            project_root,
            personal_root,
            cache_root,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected aggregate mismatch failure")

    assert "source unreadable: README.md" in message
    assert "personal source unreadable: CHANGELOG.md" in message
    assert "installed cache unreadable: LICENSE" in message
    assert "permission denied" not in message
    assert "/private/" not in message

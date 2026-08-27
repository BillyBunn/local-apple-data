from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_personal_plugin.py"
SPEC = importlib.util.spec_from_file_location("sync_personal_plugin", SCRIPT_PATH)
assert SPEC is not None
sync_personal_plugin = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["sync_personal_plugin"] = sync_personal_plugin
SPEC.loader.exec_module(sync_personal_plugin)


def _make_source(root: Path) -> None:
    root.joinpath(".codex-plugin").mkdir(parents=True)
    root.joinpath(".codex-plugin", "plugin.json").write_text("{}", encoding="utf-8")
    root.joinpath(".mcp.json").write_text("{}", encoding="utf-8")
    root.joinpath("scripts").mkdir()
    root.joinpath("scripts", "run_mcp_server.sh").write_text("#!/bin/sh\n", encoding="utf-8")


def test_sync_personal_plugin_uses_delete_excluded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "personal" / "local-apple-data"
    source.mkdir()
    _make_source(source)
    captured: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(sync_personal_plugin.subprocess, "run", fake_run)

    result = sync_personal_plugin.sync_personal_plugin(source, destination)

    command = captured["command"]
    assert result["status"] == "ok"
    assert "--delete" in command
    assert "--delete-excluded" in command
    assert "--exclude=.DS_Store" in command
    assert "--exclude=.claude" in command
    assert "--exclude=.env" in command
    assert "--exclude=.env.*" in command
    assert "--exclude=.venv" in command
    assert "--exclude=.pytest_cache" in command
    assert command[-2:] == [f"{source.resolve()}/", f"{destination.resolve()}/"]


def test_local_secret_config_patterns_are_ignored_by_git() -> None:
    gitignore = (SCRIPT_PATH.parents[1] / ".gitignore").read_text(encoding="utf-8")
    gitignore_lines = set(gitignore.splitlines())

    assert ".claude/" in gitignore_lines
    assert ".env" in gitignore_lines
    assert ".env.*" in gitignore_lines
    assert ".claude" in sync_personal_plugin.EXCLUDED_PATTERNS
    assert ".env" in sync_personal_plugin.EXCLUDED_PATTERNS
    assert ".env.*" in sync_personal_plugin.EXCLUDED_PATTERNS


def test_local_secret_config_patterns_are_check_ignored_by_git(tmp_path: Path) -> None:
    gitignore = (SCRIPT_PATH.parents[1] / ".gitignore").read_text(encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    repo.joinpath(".gitignore").write_text(gitignore, encoding="utf-8")
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for relative in [".env", ".env.local", ".claude/settings.json"]:
        repo.joinpath(relative).parent.mkdir(parents=True, exist_ok=True)
        repo.joinpath(relative).write_text("redacted\n", encoding="utf-8")
        result = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=repo,
            check=False,
        )
        assert result.returncode == 0


def test_sync_personal_plugin_rejects_invalid_source(tmp_path: Path) -> None:
    try:
        sync_personal_plugin.sync_personal_plugin(
            tmp_path / "missing",
            tmp_path / "personal",
        )
    except ValueError as exc:
        assert "plugin checkout" in str(exc)
    else:
        raise AssertionError("expected invalid source failure")


def test_sync_personal_plugin_rejects_unsafe_destinations(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _make_source(source)

    cases = [
        (source, "differ from source"),
        (source / "nested" / "local-apple-data", "inside the source"),
        (tmp_path, "contain the source"),
        (tmp_path / "personal" / "wrong-name", "end with local-apple-data"),
    ]

    for destination, expected_message in cases:
        try:
            sync_personal_plugin.sync_personal_plugin(source, destination)
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(f"expected destination safety failure for {destination}")


def test_sync_personal_plugin_cli_redacts_failures(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "personal" / "local-apple-data"
    source.mkdir()
    _make_source(source)

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            f"permission denied for {tmp_path / 'private'}",
        )

    monkeypatch.setattr(sync_personal_plugin.subprocess, "run", fake_run)

    exit_code = sync_personal_plugin.main(
        [
            "--source-root",
            str(source),
            "--personal-root",
            str(destination),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "personal plugin sync failed: RuntimeError\n"
    assert "permission denied" not in captured.err
    assert str(tmp_path) not in captured.err

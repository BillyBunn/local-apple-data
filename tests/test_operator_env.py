from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import local_apple_data.cli as cli
import local_apple_data.mcp_server as mcp_server
import local_apple_data.operator_env as operator_env
from local_apple_data.adapters import calendar as calendar_adapter
from local_apple_data.adapters import photos as photos_adapter
from local_apple_data.operator_env import OperatorEnvError, load_operator_env


EVENT_KEY = "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID"
PHOTOS_KEY = "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID"
PATH_KEY = "LOCAL_APPLE_DATA_OPERATOR_ENV_FILE"


def _write(path: Path, text: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def test_loads_allowlisted_values_without_overriding_existing_env(tmp_path: Path) -> None:
    path = tmp_path / ".env.operator"
    _write(
        path,
        f"export {EVENT_KEY}=machine-event\n{PHOTOS_KEY}=machine-photos\n",
    )
    env = {PATH_KEY: str(path), EVENT_KEY: "client-event"}

    parsed = load_operator_env(env)

    assert parsed == {EVENT_KEY: "machine-event", PHOTOS_KEY: "machine-photos"}
    assert env[EVENT_KEY] == "client-event"
    assert env[PHOTOS_KEY] == "machine-photos"


@pytest.mark.parametrize(
    "text",
    [
        "PATH=/tmp/bin\n",
        "ROOT=/tmp/elsewhere\n",
        f"{EVENT_KEY}=$(touch /tmp/should-not-run)\n",
        f"{EVENT_KEY}=first\n{EVENT_KEY}=second\n",
    ],
)
def test_rejects_disallowed_shell_or_duplicate_assignments(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / ".env.operator"
    _write(path, text)

    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: str(path)})


def test_rejects_relative_or_missing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: ""})
    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: " /tmp/operator.env "})
    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: "relative.env"})
    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: str(tmp_path / "missing.env")})


def test_rejects_surrounding_whitespace_in_existing_process_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env.operator"
    _write(path, f"{EVENT_KEY}=machine-event\n")

    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: str(path), EVENT_KEY: " client-event "})


def test_wraps_read_oserror_as_operator_env_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".env.operator"
    _write(path, f"{EVENT_KEY}=machine-event\n")

    def failed_fdopen(*_args: object, **_kwargs: object) -> object:
        raise OSError("synthetic read failure")

    monkeypatch.setattr(operator_env.os, "fdopen", failed_fdopen)
    with pytest.raises(OperatorEnvError, match="unreadable"):
        load_operator_env({PATH_KEY: str(path)})


def test_rejects_symlink_and_permissive_file(tmp_path: Path) -> None:
    target = tmp_path / "target.env"
    _write(target, f"{EVENT_KEY}=machine-event\n")
    link = tmp_path / "link.env"
    link.symlink_to(target)
    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: str(link)})

    target.chmod(0o644)
    with pytest.raises(OperatorEnvError):
        load_operator_env({PATH_KEY: str(target)})


def test_missing_default_file_is_optional(tmp_path: Path) -> None:
    env: dict[str, str] = {}

    assert load_operator_env(env, home=tmp_path) == {}
    assert EVENT_KEY not in env


def test_checkout_local_values_override_machine_defaults(tmp_path: Path) -> None:
    machine = tmp_path / "machine.env"
    local = tmp_path / ".env.local"
    _write(machine, f"{EVENT_KEY}=machine-event\n{PHOTOS_KEY}=machine-photos\n")
    _write(local, f"{EVENT_KEY}=checkout-event\n")
    env = {PATH_KEY: str(machine)}

    parsed = load_operator_env(env, local_env_path=local)

    assert parsed == {EVENT_KEY: "checkout-event", PHOTOS_KEY: "machine-photos"}
    assert env[EVENT_KEY] == "checkout-event"
    assert env[PHOTOS_KEY] == "machine-photos"


def test_cli_main_loads_operator_env_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".env.operator"
    _write(path, f"{EVENT_KEY}=cli-event\n{PHOTOS_KEY}=cli-photos\n")
    monkeypatch.setenv(PATH_KEY, str(path))
    monkeypatch.delenv(EVENT_KEY, raising=False)
    monkeypatch.delenv(PHOTOS_KEY, raising=False)
    monkeypatch.setattr(cli, "OPERATOR_LOCAL_ENV_PATH", tmp_path / "missing-local")
    args = SimpleNamespace(func=lambda _args: 0)
    parser = SimpleNamespace(parse_args=lambda _argv: args)
    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    assert cli.main([]) == 0
    assert calendar_adapter._eventkit_helper_info_plist()["CFBundleIdentifier"] == "cli-event"
    assert photos_adapter._photos_helper_info_plist()["CFBundleIdentifier"] == "cli-photos"


def test_mcp_main_loads_operator_env_before_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".env.operator"
    _write(path, f"{EVENT_KEY}=mcp-event\n{PHOTOS_KEY}=mcp-photos\n")
    monkeypatch.setenv(PATH_KEY, str(path))
    monkeypatch.delenv(EVENT_KEY, raising=False)
    monkeypatch.delenv(PHOTOS_KEY, raising=False)
    monkeypatch.setattr(
        mcp_server, "OPERATOR_LOCAL_ENV_PATH", tmp_path / "missing-local"
    )
    called: list[bool] = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: called.append(True))

    mcp_server.main()

    assert called == [True]
    assert calendar_adapter._eventkit_helper_info_plist()["CFBundleIdentifier"] == "mcp-event"
    assert photos_adapter._photos_helper_info_plist()["CFBundleIdentifier"] == "mcp-photos"


def test_cli_main_fails_closed_on_missing_explicit_operator_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(PATH_KEY, str(tmp_path / "missing.env"))

    assert cli.main([]) == 1
    assert "operator environment failed" in capsys.readouterr().err

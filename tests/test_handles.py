from __future__ import annotations

from pathlib import Path

from local_apple_data.handles import (
    SECRET_FILENAME,
    int_handle_matches,
    is_int_handle,
    is_opaque_handle,
    make_int_handle,
    make_opaque_handle,
    opaque_handle_matches,
)


def test_int_handle_is_opaque_and_rejects_tampering() -> None:
    handle = make_int_handle("mail:message", 12345)

    assert handle.startswith("mail:message:v2:")
    assert len(handle.removeprefix("mail:message:v2:")) == 32
    assert "3039" not in handle
    assert is_int_handle(handle, "mail:message") is True
    assert is_int_handle(handle, "notes:note") is False
    assert int_handle_matches(handle, "mail:message", 12345) is True
    assert int_handle_matches(handle, "mail:message", 12346) is False

    tampered = handle[:-1] + ("0" if handle[-1] != "0" else "1")
    assert int_handle_matches(tampered, "mail:message", 12345) is False


def test_opaque_handle_is_stable_and_prefix_scoped() -> None:
    first = make_opaque_handle("reminders:reminder", "store-a", 10)
    second = make_opaque_handle("reminders:reminder", "store-a", 10)
    other = make_opaque_handle("reminders:reminder", "store-b", 10)

    assert first == second
    assert first.startswith("reminders:reminder:v1:")
    assert first != other
    assert is_opaque_handle(first, "reminders:reminder") is True
    assert is_opaque_handle(first, "icloud:file") is False
    assert opaque_handle_matches(first, "reminders:reminder", "store-a", 10) is True
    assert opaque_handle_matches(first, "reminders:reminder", "store-b", 10) is False


def test_handle_secret_file_is_local_and_restrictive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("LOCAL_APPLE_DATA_HANDLE_SECRET", raising=False)
    monkeypatch.setenv("LOCAL_APPLE_DATA_STATE_DIR", str(tmp_path))

    make_int_handle("mail:message", 99)

    secret_path = tmp_path / SECRET_FILENAME
    assert secret_path.is_file()
    assert len(secret_path.read_text(encoding="utf-8").strip()) >= 32
    assert secret_path.stat().st_mode & 0o777 == 0o600


def test_malformed_handle_secret_file_is_repaired(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("LOCAL_APPLE_DATA_HANDLE_SECRET", raising=False)
    monkeypatch.setenv("LOCAL_APPLE_DATA_STATE_DIR", str(tmp_path))
    secret_path = tmp_path / SECRET_FILENAME
    secret_path.write_text("short\n", encoding="utf-8")

    handle = make_int_handle("mail:message", 100)

    assert int_handle_matches(handle, "mail:message", 100) is True
    assert len(secret_path.read_text(encoding="utf-8").strip()) >= 32
    assert secret_path.stat().st_mode & 0o777 == 0o600

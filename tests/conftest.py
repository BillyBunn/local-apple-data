from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_local_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Never load the operator's real machine helper-ID file while importing or
    # executing CLI/MCP modules in tests. Individual operator-env tests supply a
    # private explicit path and test the strict parser in isolation.
    operator_env = tmp_path / ".env.operator"
    operator_env.write_text("# synthetic test operator environment\n", encoding="utf-8")
    operator_env.chmod(0o600)
    monkeypatch.setenv("LOCAL_APPLE_DATA_OPERATOR_ENV_FILE", str(operator_env))
    monkeypatch.delenv(
        "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID", raising=False
    )
    monkeypatch.delenv(
        "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID", raising=False
    )
    # The source checkout also supports a private `.env.local` override. Point
    # CLI/MCP entrypoints at an absent synthetic path so tests never inspect the
    # operator's real checkout-local file.
    monkeypatch.setattr(
        "local_apple_data.cli.OPERATOR_LOCAL_ENV_PATH", tmp_path / ".env.local"
    )
    monkeypatch.setattr(
        "local_apple_data.mcp_server.OPERATOR_LOCAL_ENV_PATH",
        tmp_path / ".env.local",
    )
    # A missed runner mock must never rebuild either live signed helper app.
    # Redirect their application roots before any adapter test can reach an
    # ensure/build path.
    monkeypatch.setattr(
        "local_apple_data.adapters.calendar._eventkit_helper_app_root",
        lambda: tmp_path / "helpers" / "EventKitHelper.app",
    )
    monkeypatch.setattr(
        "local_apple_data.adapters.photos._photos_helper_app_root",
        lambda: tmp_path / "helpers" / "PhotosHelper.app",
    )
    monkeypatch.setattr(
        "local_apple_data.adapters.contacts._contacts_helper_app_root",
        lambda: tmp_path / "helpers" / "ContactsHelper.app",
    )
    monkeypatch.setenv("LOCAL_APPLE_DATA_HANDLE_SECRET", "synthetic-test-handle-secret")
    monkeypatch.setenv("LOCAL_APPLE_DATA_STATE_DIR", str(tmp_path / "state"))
    # Without this, redacted_log falls back to the operator's real event log at
    # ~/.local/state/local-apple-data/events.jsonl and the suite appends to it. Most test
    # files already set this themselves, but "most" is not isolation: any test that logs
    # without setting it wrote to the operator's private log, and a single tranche day put
    # tens of thousands of synthetic events there. Tests that set it in their own body
    # still win, because a later monkeypatch.setenv overrides this one.
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path / "logs"))
    # Same directory, same hazard. These two default under ~/.local/state/local-apple-data
    # as well, and today no test writes them only because every relevant test happens to
    # pass an explicit path argument -- the FTS index env var is set by no test at all.
    # That is one forgotten argument away from a test overwriting the operator's real Mail
    # content cache, so isolate them by construction rather than by habit.
    monkeypatch.setenv(
        "LOCAL_APPLE_DATA_MAIL_FTS_INDEX", str(tmp_path / "state" / "mail-fts.sqlite")
    )
    monkeypatch.setenv(
        "LOCAL_APPLE_DATA_MAIL_TEMPLATE_STATE",
        str(tmp_path / "state" / "mail-templates.json"),
    )
    # These two default to the operator's real home and real iCloud Drive. They used
    # to be unreachable from here: both adapters bound them as default argument
    # values at import time, so setting the variables after import did nothing. The
    # adapters now resolve them per call, which is what makes these two lines work.
    #
    # Nothing in the suite writes real data today, but only by habit -- every test
    # happens to pass an explicit `root=`, and the handful of default-root plan calls
    # happen to fail validation before reaching the filesystem. One test that calls
    # an apply path without `root=` would reach the real home directory with no guard
    # in front of it, and a default-root trash operation resolves to ~/.Trash.
    monkeypatch.setenv("LOCAL_APPLE_DATA_FS_ROOT", str(tmp_path / "home"))
    monkeypatch.setenv(
        "LOCAL_APPLE_DATA_ICLOUD_DRIVE_ROOT", str(tmp_path / "icloud")
    )

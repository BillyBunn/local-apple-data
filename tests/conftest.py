from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_local_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_HANDLE_SECRET", "synthetic-test-handle-secret")
    monkeypatch.setenv("LOCAL_APPLE_DATA_STATE_DIR", str(tmp_path / "state"))

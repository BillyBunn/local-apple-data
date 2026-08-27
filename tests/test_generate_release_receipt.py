from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate_release_receipt.py"
SPEC = importlib.util.spec_from_file_location("generate_release_receipt", SCRIPT_PATH)
assert SPEC is not None
generate_release_receipt = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_receipt"] = generate_release_receipt
SPEC.loader.exec_module(generate_release_receipt)


def test_current_project_release_receipt_is_path_redacted() -> None:
    payload = generate_release_receipt.generate_release_receipt(PROJECT_ROOT)
    serialized = json.dumps(payload, sort_keys=True)

    if "git_worktree_clean" in payload["blockers"]:
        assert payload["status"] == "error"
        assert payload["local_package_ready"] is False
    else:
        assert payload["status"] == "ok"
        assert payload["local_package_ready"] is True
    remote_check = next(
        check for check in payload["release_readiness"]["checks"] if check["name"] == "git_remote"
    )
    if remote_check["status"] == "ok":
        assert "missing_git_remote" not in payload["blockers"]
    else:
        assert "missing_git_remote" in payload["blockers"]
    assert payload["mutation_gate"]["status"] == "ok"
    assert payload["redaction_scan"] == {"finding_count": 0, "findings": [], "status": "ok"}
    assert "source_git" in payload
    if payload["source_git"]["is_git_checkout"]:
        assert len(payload["source_git"]["commit_sha"]) == 40
        assert isinstance(payload["source_git"]["dirty"], bool)
        assert "branch" not in payload["source_git"]
    assert payload["write_design_gate"]["status"] == "ok"
    assert payload["surface_contract"]["status"] == "ok"
    assert payload["public_git_checkout"]["file_count"] == payload["public_git_checkout"]["staged_files"]
    assert payload["public_git_checkout"]["file_count"] > 0
    assert payload["public_git_checkout"]["committed"] is True
    assert len(payload["public_git_checkout"]["commit_sha"]) == 40
    assert str(PROJECT_ROOT) not in serialized
    assert str(Path.home()) not in serialized


def test_release_receipt_cli_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--project-root",
            str(PROJECT_ROOT),
            "--output",
            str(output),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode in (0, 1)
    assert result.stdout == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    if result.returncode == 1:
        assert payload["status"] == "error"
        assert "git_worktree_clean" in payload["blockers"]
    else:
        assert payload["status"] == "ok"
    assert payload["privacy"]["paths_redacted"] is True
    assert "redaction_scan" in payload
    assert "source_git" in payload


def test_release_receipt_source_git_degrades_for_non_git_root(tmp_path: Path) -> None:
    payload = generate_release_receipt._source_git(tmp_path)

    assert payload == {
        "commit_sha": "",
        "dirty": None,
        "is_git_checkout": False,
    }


def test_release_receipt_cli_rejects_project_local_output() -> None:
    output = PROJECT_ROOT / f".blocked-release-receipt-{uuid.uuid4().hex}.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--project-root",
            str(PROJECT_ROOT),
            "--output",
            str(output),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "ValueError" in result.stderr
    assert not output.exists()


def test_release_receipt_cli_reports_output_write_errors(tmp_path: Path) -> None:
    output = tmp_path / "missing" / "receipt.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--project-root",
            str(PROJECT_ROOT),
            "--output",
            str(output),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "release receipt output failed: FileNotFoundError" in result.stderr
    assert not output.exists()

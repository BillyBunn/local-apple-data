from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "redaction_scan.py"
SPEC = importlib.util.spec_from_file_location("redaction_scan", SCRIPT_PATH)
assert SPEC is not None
redaction_scan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["redaction_scan"] = redaction_scan
SPEC.loader.exec_module(redaction_scan)
scan_paths = redaction_scan.scan_paths


def test_redaction_scan_flags_literal_apple_alias(tmp_path: Path) -> None:
    alias = "synthetic_alias_42" + "@" + "icloud.com"
    path = tmp_path / "leak.txt"
    path.write_text(f"alias={alias}\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert len(findings) == 1
    assert findings[0].pattern == "apple_private_alias"


def test_redaction_scan_ignores_policy_text(tmp_path: Path) -> None:
    path = tmp_path / "policy.md"
    path.write_text(
        "Do not use iCloud.com, OAuth, browser sessions, or keychain credentials.\n",
        encoding="utf-8",
    )

    assert scan_paths([tmp_path]) == []


def test_redaction_scan_cli_json_success(tmp_path: Path, capsys) -> None:
    tmp_path.joinpath("safe.txt").write_text("synthetic only\n", encoding="utf-8")

    status = redaction_scan.main(["--json", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"finding_count": 0, "findings": [], "status": "ok"}


def test_redaction_scan_cli_json_finding_omits_matched_value(tmp_path: Path, capsys) -> None:
    alias = "synthetic_alias_42" + "@" + "icloud.com"
    tmp_path.joinpath("leak.txt").write_text(f"alias={alias}\n", encoding="utf-8")

    status = redaction_scan.main(["--json", str(tmp_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert status == 1
    assert captured.err == ""
    assert payload["finding_count"] == 1
    assert payload["findings"][0]["line_number"] == 1
    assert payload["findings"][0]["pattern"] == "apple_private_alias"
    assert payload["findings"][0]["path"].endswith("leak.txt")
    assert alias not in captured.out

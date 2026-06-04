from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "public_release_scan.py"
SPEC = importlib.util.spec_from_file_location("public_release_scan", SCRIPT_PATH)
assert SPEC is not None
public_release_scan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["public_release_scan"] = public_release_scan
SPEC.loader.exec_module(public_release_scan)


def test_public_release_scan_flags_absolute_operator_path(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    local_path = "/Users/" + "billy" + "/Projects/local-apple-data"
    path.write_text(f"Use {local_path} here.\n", encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert len(findings) == 1
    assert findings[0].pattern == "absolute_billy_path"


def test_public_release_scan_skips_local_operator_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    path = docs / "IMPLEMENTATION_LOG.md"
    local_path = "/Users/" + "billy" + "/Projects/local-apple-data"
    path.write_text(f"Local path {local_path}.\n", encoding="utf-8")

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_allows_author_metadata(tmp_path: Path) -> None:
    path = tmp_path / "LICENSE"
    author = "Bil" + "ly Bunn"
    path.write_text(f"Copyright (c) 2026 {author}\n", encoding="utf-8")

    assert public_release_scan.scan_public_files(tmp_path) == []

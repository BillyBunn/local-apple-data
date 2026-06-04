#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "node_modules",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".pyc",
    ".sqlite",
    ".webp",
}

LOCAL_OPERATOR_DOCS = {
    "AGENTS.md",
    "docs/CROSS_AGENT_ROUTING.md",
    "docs/IMPLEMENTATION_LOG.md",
    "docs/V1_1_CONTENT_RETRIEVAL_PLAN.md",
    "docs/V1_1_KICKOFF_PROMPT.md",
}

SELF_SCAN_EXCLUSIONS = {
    "scripts/public_release_scan.py",
}

ALLOW_BILLY_BUNN = {
    "LICENSE",
    "pyproject.toml",
    ".codex-plugin/plugin.json",
    "tests/test_plugin_packaging.py",
}

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("absolute_billy_path", re.compile(r"/Users/billy\b")),
    ("personal_admin_path", re.compile(r"\bPersonal Admin\b")),
    ("codex_user_state_path", re.compile(r"/Users/[^/\s]+/\.codex\b")),
    ("openclaw_user_state_path", re.compile(r"/Users/[^/\s]+/\.openclaw\b")),
    ("private_note_title", re.compile(r"\bScans Review Packet for Billy\b")),
    ("billy_operator_term", re.compile(r"\bBilly\b")),
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    pattern: str


def iter_public_files(root: Path = PROJECT_ROOT) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in LOCAL_OPERATOR_DOCS:
            continue
        if relative in SELF_SCAN_EXCLUSIONS:
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def scan_public_files(root: Path = PROJECT_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_public_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for name, pattern in PATTERNS:
                if name == "billy_operator_term" and relative in ALLOW_BILLY_BUNN:
                    continue
                if pattern.search(line):
                    findings.append(Finding(path=path, line_number=line_number, pattern=name))
    return findings


def main() -> int:
    findings = scan_public_files(PROJECT_ROOT)
    if findings:
        print("public release scan failed", file=sys.stderr)
        for finding in findings:
            print(
                f"{finding.path.relative_to(PROJECT_ROOT)}:{finding.line_number}: {finding.pattern}",
                file=sys.stderr,
            )
        return 1
    print("public release scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

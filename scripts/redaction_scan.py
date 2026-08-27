#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".emlx",
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
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    (
        "apple_private_alias",
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@(?:icloud|me|mac|privaterelay\.appleid)\.com\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    pattern: str


def iter_scan_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        root = root.expanduser()
        if root.is_file():
            if _should_scan(root):
                yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and _should_scan(path):
                yield path


def scan_paths(roots: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_scan_files(roots):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for name, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(path=path, line_number=line_number, pattern=name))
    return findings


def _should_scan(path: Path) -> bool:
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return not any(part in EXCLUDED_DIRS for part in path.parts)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "path": _display_path(finding.path),
        "line_number": finding.line_number,
        "pattern": finding.pattern,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan repo text files for high-risk secrets.")
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to scan.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    args = parser.parse_args(argv)

    findings = scan_paths(Path(value) for value in args.paths)
    payload = {
        "finding_count": len(findings),
        "findings": [_finding_payload(finding) for finding in findings],
        "status": "error" if findings else "ok",
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
        return 1 if findings else 0
    if findings:
        print("redaction scan failed", file=sys.stderr)
        for finding in findings:
            print(
                f"{finding.path}:{finding.line_number}: {finding.pattern}",
                file=sys.stderr,
            )
        return 1
    print("redaction scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

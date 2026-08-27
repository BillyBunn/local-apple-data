#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PERSONAL_ROOT = Path.home() / "plugins" / "local-apple-data"
EXCLUDED_PATTERNS = (
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".codex",
    ".claude",
    ".DS_Store",
    ".env",
    ".env.*",
    "*.pyc",
    "*.pyo",
    "dist",
    "build",
)
REQUIRED_SOURCE_FILES = (
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "scripts/run_mcp_server.sh",
)


def sync_personal_plugin(
    source_root: Path = PROJECT_ROOT,
    personal_root: Path = DEFAULT_PERSONAL_ROOT,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    source = source_root.expanduser().resolve()
    destination = personal_root.expanduser().resolve()
    _validate_source(source)
    _validate_destination(source, destination)

    command = _rsync_command(source, destination, dry_run=dry_run)
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("rsync failed")
    return {
        "status": "ok",
        "source_root": str(source),
        "personal_root": str(destination),
        "dry_run": dry_run,
        "excluded_patterns": list(EXCLUDED_PATTERNS),
    }


def _validate_source(source: Path) -> None:
    missing = [
        relative
        for relative in REQUIRED_SOURCE_FILES
        if not source.joinpath(relative).exists()
    ]
    if missing:
        raise ValueError("source root is not a local-apple-data plugin checkout")


def _validate_destination(source: Path, destination: Path) -> None:
    home = Path.home().resolve()
    if destination == source:
        raise ValueError("personal plugin root must differ from source root")
    if destination == home:
        raise ValueError("personal plugin root must not be the home directory")
    try:
        source.relative_to(destination)
    except ValueError:
        pass
    else:
        raise ValueError("personal plugin root must not contain the source root")
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError("personal plugin root must not be inside the source root")
    if destination.name != "local-apple-data":
        raise ValueError("personal plugin root must end with local-apple-data")


def _rsync_command(source: Path, destination: Path, *, dry_run: bool) -> list[str]:
    command = ["rsync", "-a", "--delete", "--delete-excluded"]
    if dry_run:
        command.append("--dry-run")
    for pattern in EXCLUDED_PATTERNS:
        command.append(f"--exclude={pattern}")
    command.extend([f"{source}/", f"{destination}/"])
    return command


def _redact_paths(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    if "source_root" in result:
        result["source_root"] = "<source-root>"
    if "personal_root" in result:
        result["personal_root"] = "<personal-root>"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync the canonical source tree to the personal Codex plugin root."
    )
    parser.add_argument("--source-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument(
        "--personal-root",
        default=str(DEFAULT_PERSONAL_ROOT),
        help="Personal plugin root to update.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what rsync would change.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    source = Path(args.source_root)
    destination = Path(args.personal_root)
    try:
        payload = sync_personal_plugin(source, destination, dry_run=args.dry_run)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"personal plugin sync failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_redact_paths(payload), sort_keys=True))
    else:
        print(
            "personal plugin sync: "
            f"status={payload['status']} "
            f"dry_run={payload['dry_run']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

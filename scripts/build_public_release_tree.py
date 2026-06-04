#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import public_release_scan


EXCLUDED_DIRS = public_release_scan.EXCLUDED_DIRS | {
    ".codex",
    ".local-state",
    "logs",
}
EXCLUDED_SUFFIXES = public_release_scan.EXCLUDED_SUFFIXES
EXCLUDED_FILES = public_release_scan.LOCAL_OPERATOR_DOCS | {
    ".git",
}
EXCLUDED_FILE_NAMES = {".DS_Store"}


@dataclass(frozen=True)
class BuildResult:
    destination: Path
    file_count: int


def iter_release_files(root: Path = PROJECT_ROOT) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_stage(path, root):
            yield path


def build_release_tree(root: Path, destination: Path, *, force: bool = False) -> BuildResult:
    root = root.expanduser().resolve()
    destination = destination.expanduser().resolve(strict=False)
    _validate_destination(root, destination, force=force)

    if destination.exists() and force:
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    file_count = 0
    for source in iter_release_files(root):
        relative = source.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        file_count += 1

    findings = public_release_scan.scan_public_files(destination)
    if findings:
        details = ", ".join(
            f"{finding.path.relative_to(destination)}:{finding.line_number}:{finding.pattern}"
            for finding in findings
        )
        raise RuntimeError(f"staged public release tree failed scan: {details}")

    return BuildResult(destination=destination, file_count=file_count)


def _should_stage(path: Path, root: Path) -> bool:
    relative_path = path.relative_to(root)
    relative = relative_path.as_posix()
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    if relative in EXCLUDED_FILES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in relative_path.parts):
        return False
    return True


def _validate_destination(root: Path, destination: Path, *, force: bool) -> None:
    if destination == root:
        raise ValueError("destination must not be the project root")
    try:
        destination.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("destination must be outside the project root")

    if destination.exists() and not destination.is_dir():
        raise ValueError("destination exists and is not a directory")
    if destination.exists() and any(destination.iterdir()) and not force:
        raise ValueError("destination exists and is not empty; pass --force to replace it")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized public release tree.")
    parser.add_argument("--dest", required=True, help="Destination directory outside the repo.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--force", action="store_true", help="Replace an existing destination.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    try:
        result = build_release_tree(
            Path(args.project_root),
            Path(args.dest),
            force=args.force,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"public release tree build failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "destination": str(result.destination),
        "file_count": result.file_count,
        "status": "ok",
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"public release tree staged: {result.file_count} files -> {result.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_mutation_gates import audit_mutation_gates
from audit_release_readiness import audit_release_readiness
from audit_surface_contract import audit_surface_contract
from audit_write_design_gates import audit_write_design_gates
from prepare_public_git_checkout import prepare_public_git_checkout
from redaction_scan import scan_paths


def generate_release_receipt(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    release_readiness = audit_release_readiness(root)
    mutation_gate = audit_mutation_gates(root)
    surface_contract = audit_surface_contract(root)
    write_design_gate = audit_write_design_gates(root)
    redaction_scan = _redaction_scan(root)
    plugin = _load_json(root / ".codex-plugin/plugin.json")

    with tempfile.TemporaryDirectory(prefix="local-apple-data-receipt-") as tmp:
        public_git = prepare_public_git_checkout(
            root,
            Path(tmp) / "public-git",
            force=True,
            init_git=True,
            commit=True,
        )

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "package": {
            "name": "local-apple-data",
            "version": _package_version(root),
            "plugin_version": str(plugin.get("version", "")),
            "license": str(plugin.get("license", "")),
        },
        "status": "ok" if release_readiness["local_package_ready"] else "error",
        "local_package_ready": release_readiness["local_package_ready"],
        "github_publication_ready": release_readiness["github_publication_ready"],
        "blockers": list(release_readiness["blockers"]),
        "release_readiness": release_readiness,
        "redaction_scan": redaction_scan,
        "mutation_gate": mutation_gate,
        "write_design_gate": write_design_gate,
        "surface_contract": surface_contract,
        "source_git": _source_git(root),
        "public_git_checkout": {
            "branch": public_git.branch,
            "commit_sha": public_git.commit_sha,
            "committed": public_git.committed,
            "file_count": public_git.file_count,
            "git_initialized": public_git.git_initialized,
            "remote_configured": public_git.remote_configured,
            "staged_files": public_git.staged_files,
        },
        "privacy": {
            "paths_redacted": True,
            "live_content_included": False,
            "synthetic_tests_only": True,
        },
    }
    return _redact_paths(payload, root)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _package_version(root: Path) -> str:
    for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            _, value = stripped.split("=", 1)
            return value.strip().strip('"')
    return ""


def _redaction_scan(root: Path) -> dict[str, Any]:
    findings = scan_paths([root])
    return {
        "finding_count": len(findings),
        "findings": [
            {
                "line_number": finding.line_number,
                "path": finding.path.relative_to(root).as_posix(),
                "pattern": finding.pattern,
            }
            for finding in findings
        ],
        "status": "error" if findings else "ok",
    }


def _source_git(root: Path) -> dict[str, Any]:
    inside = _git_output(root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        return {
            "commit_sha": "",
            "dirty": None,
            "is_git_checkout": False,
        }

    commit_sha = _git_output(root, "rev-parse", "HEAD") or ""
    status = _git_output(root, "status", "--porcelain", "--untracked-files=normal")
    return {
        "commit_sha": commit_sha,
        "dirty": None if status is None else bool(status.splitlines()),
        "is_git_checkout": True,
    }


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _validate_output_path(root: Path, output: Path) -> Path:
    resolved = output.expanduser().resolve(strict=False)
    if resolved == root:
        raise ValueError("output path must be outside the project root")
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("output path must be outside the project root")
    if resolved.exists() and resolved.is_dir():
        raise ValueError("output path must be a file")
    return resolved


def _redact_paths(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _redact_paths(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_paths(item, root) for item in value]
    if isinstance(value, str):
        return _redact_string(value, root)
    return value


def _redact_string(value: str, root: Path) -> str:
    result = value.replace(str(root), "<project-root>")
    result = result.replace(str(Path.home()), "<home>")
    result = re.sub(r"/(?:private/)?tmp/[^\s,;\"']+", "<temp-path>", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a path-redacted public release readiness receipt."
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--output", default="", help="Optional JSON output file.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        root = Path(args.project_root).expanduser().resolve()
        output = _validate_output_path(root, Path(args.output)) if args.output else None
        payload = generate_release_receipt(root)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"release receipt generation failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        if output is not None:
            output.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"release receipt output failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if args.json or not args.output:
        print(text, end="")
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

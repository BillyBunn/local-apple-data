#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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


def generate_release_receipt(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    release_readiness = audit_release_readiness(root)
    mutation_gate = audit_mutation_gates(root)
    surface_contract = audit_surface_contract(root)
    write_design_gate = audit_write_design_gates(root)
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
        "mutation_gate": mutation_gate,
        "write_design_gate": write_design_gate,
        "surface_contract": surface_contract,
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
        payload = generate_release_receipt(Path(args.project_root))
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"release receipt generation failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve(strict=False)
        output.write_text(text, encoding="utf-8")
    if args.json or not args.output:
        print(text, end="")
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

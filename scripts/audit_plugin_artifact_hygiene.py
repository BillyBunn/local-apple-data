#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sync_personal_plugin import DEFAULT_PERSONAL_ROOT, EXCLUDED_PATTERNS


DEFAULT_CACHE_ROOT = Path.home() / ".codex/plugins/cache/personal/local-apple-data"


def audit_plugin_artifact_hygiene(
    *,
    personal_root: Path = DEFAULT_PERSONAL_ROOT,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    version: str | None = None,
) -> dict[str, Any]:
    plugin_version = version or _plugin_version(PROJECT_ROOT)
    roots = [
        ("personal_root", personal_root.expanduser().resolve()),
        ("installed_cache", (cache_root.expanduser().resolve() / plugin_version)),
    ]

    root_payloads: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for label, root in roots:
        root_findings = _find_artifacts(root, label)
        findings.extend(root_findings)
        root_payloads.append(
            {
                "artifact_count": len(root_findings),
                "exists": root.exists(),
                "name": label,
                "root": str(root),
            }
        )

    return {
        "checked_patterns": list(EXCLUDED_PATTERNS),
        "finding_count": len(findings),
        "findings": findings,
        "roots": root_payloads,
        "status": "ok" if not findings else "error",
        "version": plugin_version,
    }


def _plugin_version(project_root: Path) -> str:
    manifest = json.loads(
        (project_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    return str(manifest["version"])


def _find_artifacts(root: Path, label: str) -> list[dict[str, Any]]:
    if not root.exists():
        return [
            {
                "kind": "missing_root",
                "pattern": "",
                "relative_path": "",
                "root": label,
            }
        ]

    findings: list[dict[str, Any]] = []
    for directory, dirnames, filenames in os.walk(root):
        current = Path(directory)
        for name in list(dirnames):
            pattern = _matched_pattern(name)
            if pattern is None:
                continue
            path = current / name
            findings.append(_artifact_finding(root, path, label, pattern))
            dirnames.remove(name)
        for name in filenames:
            pattern = _matched_pattern(name)
            if pattern is None:
                continue
            findings.append(_artifact_finding(root, current / name, label, pattern))
    return findings


def _artifact_finding(root: Path, path: Path, label: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "generated_or_local_config_artifact",
        "pattern": pattern,
        "relative_path": path.relative_to(root).as_posix(),
        "root": label,
    }


def _matched_pattern(name: str) -> str | None:
    for pattern in EXCLUDED_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return pattern
    return None


def _redact_roots(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    redacted["roots"] = [
        {
            **root,
            "root": f"<{root['name'].replace('_', '-')}>",
        }
        for root in payload["roots"]
    ]
    return redacted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit personal and installed local-apple-data plugin roots for stale local artifacts."
    )
    parser.add_argument(
        "--personal-root",
        default=str(DEFAULT_PERSONAL_ROOT),
        help="Personal plugin source root to check.",
    )
    parser.add_argument(
        "--cache-root",
        default=str(DEFAULT_CACHE_ROOT),
        help="Installed plugin cache parent to check.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Installed plugin version directory to check. Defaults to the source manifest version.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    try:
        payload = audit_plugin_artifact_hygiene(
            personal_root=Path(args.personal_root),
            cache_root=Path(args.cache_root),
            version=args.version,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"plugin artifact hygiene audit failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_redact_roots(payload), sort_keys=True))
    else:
        print(
            "plugin artifact hygiene: "
            f"status={payload['status']} "
            f"finding_count={payload['finding_count']}"
        )
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

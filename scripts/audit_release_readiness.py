#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import public_release_scan
from audit_mutation_gates import audit_mutation_gates
from audit_surface_contract import audit_surface_contract
from audit_write_design_gates import audit_write_design_gates
from prepare_public_git_checkout import prepare_public_git_checkout


CheckStatus = Literal["ok", "warning", "error"]


REQUIRED_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "LICENSE",
    "SECURITY.md",
    ".codex-plugin/plugin.json",
    ".mcp.json",
    ".github/workflows/ci.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    "pyproject.toml",
    "uv.lock",
    "docs/INSTALL.md",
    "docs/SAMPLE_OUTPUTS.md",
    "docs/MACOS_SUPPORT.md",
    "docs/ECOSYSTEM_REVIEW.md",
    "docs/PUBLIC_RELEASE_MANIFEST.md",
    "docs/CAPABILITY_MATRIX.md",
    "docs/MUTATION_GATES.md",
    "docs/V1_11_REMINDERS_WRITE_DESIGN.md",
    "docs/WRITE_TOOL_ROADMAP.md",
    "docs/PUBLISHING.md",
    "docs/PRIVACY_MODEL.md",
    "docs/THREAT_MODEL.md",
    "docs/TESTING.md",
    "scripts/audit_release_readiness.py",
    "scripts/audit_mutation_gates.py",
    "scripts/audit_surface_contract.py",
    "scripts/audit_write_design_gates.py",
    "scripts/build_public_release_tree.py",
    "scripts/generate_release_receipt.py",
    "scripts/prepare_public_git_checkout.py",
    "scripts/public_release_scan.py",
    "scripts/redaction_scan.py",
    "scripts/render_mcp_client_config.py",
    "scripts/run_mcp_server.sh",
    "scripts/verify_runtime.py",
    "skills/local-apple-data/SKILL.md",
    "skills/local-apple-data/agents/openai.yaml",
    "src/local_apple_data/cli.py",
    "src/local_apple_data/health.py",
    "src/local_apple_data/mcp_server.py",
    "tests/test_mutation_gate_audit.py",
    "tests/test_write_design_gate_audit.py",
    "tests/test_public_release_scan.py",
    "tests/test_release_readiness_audit.py",
    "tests/test_generate_release_receipt.py",
    "tests/test_surface_contract_audit.py",
)


@dataclass(frozen=True)
class Check:
    name: str
    status: CheckStatus
    message: str


def audit_release_readiness(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    checks: list[Check] = []

    required_missing = _missing_required_files(root)
    if required_missing:
        checks.append(
            Check(
                "required_files",
                "error",
                f"missing required files: {', '.join(required_missing)}",
            )
        )
    else:
        checks.append(Check("required_files", "ok", f"{len(REQUIRED_FILES)} files present"))

    checks.append(_version_check(root))
    checks.append(_public_scan_check(root))
    checks.append(_mutation_gate_check(root))
    checks.append(_write_design_gate_check(root))
    checks.append(_surface_contract_check(root))
    checks.append(_public_git_checkout_check(root))
    checks.append(_git_remote_check(root))

    local_package_ready = all(check.status != "error" for check in checks)
    has_remote = any(check.name == "git_remote" and check.status == "ok" for check in checks)
    github_publication_ready = local_package_ready and has_remote
    blockers = _blockers(checks)

    return {
        "blockers": blockers,
        "checks": [
            {"message": check.message, "name": check.name, "status": check.status}
            for check in checks
        ],
        "github_publication_ready": github_publication_ready,
        "local_package_ready": local_package_ready,
        "project_root": str(root),
        "status": "ok" if local_package_ready else "error",
    }


def _missing_required_files(root: Path) -> list[str]:
    missing: list[str] = []
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.exists() or not path.is_file():
            missing.append(relative)
        elif not path.read_bytes():
            missing.append(relative)
    return missing


def _version_check(root: Path) -> Check:
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        package_version = str(pyproject["project"]["version"])
        plugin = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        plugin_version = str(plugin["version"])
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except (KeyError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return Check("version_consistency", "error", f"version metadata unreadable: {type(exc).__name__}")

    if not plugin_version.startswith(f"{package_version}+"):
        return Check(
            "version_consistency",
            "error",
            "plugin version must use the Python package version as its base",
        )
    if plugin_version not in changelog:
        return Check("version_consistency", "error", "plugin version missing from changelog")
    return Check("version_consistency", "ok", f"package {package_version}, plugin {plugin_version}")


def _public_scan_check(root: Path) -> Check:
    findings = public_release_scan.scan_public_files(root)
    if findings:
        first = findings[0]
        relative = first.path.relative_to(root).as_posix()
        return Check(
            "public_release_scan",
            "error",
            f"{len(findings)} findings; first {relative}:{first.line_number}:{first.pattern}",
        )
    return Check("public_release_scan", "ok", "no public leakage findings")


def _mutation_gate_check(root: Path) -> Check:
    payload = audit_mutation_gates(root)
    if payload["status"] != "ok":
        findings = payload["findings"]
        first = findings[0] if findings else {"kind": "unknown", "path": "", "line": 0}
        return Check(
            "mutation_gate_audit",
            "error",
            f"{len(findings)} findings; first {first['path']}:{first['line']}:{first['kind']}",
        )
    return Check(
        "mutation_gate_audit",
        "ok",
        f"{payload['mcp_tools_checked']} MCP tools and {payload['cli_handlers_checked']} CLI handlers read-only",
    )


def _surface_contract_check(root: Path) -> Check:
    payload = audit_surface_contract(root)
    if payload["status"] != "ok":
        findings = payload["findings"]
        first = findings[0] if findings else {"kind": "unknown", "path": "", "line": 0}
        return Check(
            "surface_contract_audit",
            "error",
            f"{len(findings)} findings; first {first['path']}:{first['line']}:{first['kind']}",
        )
    return Check(
        "surface_contract_audit",
        "ok",
        (
            f"{payload['surfaces_checked']} surfaces, "
            f"{payload['mcp_tools_checked']} MCP tools, "
            f"{payload['cli_commands_expected']} CLI commands aligned"
        ),
    )


def _write_design_gate_check(root: Path) -> Check:
    payload = audit_write_design_gates(root)
    if payload["status"] != "ok":
        findings = payload["findings"]
        first = findings[0] if findings else {"kind": "unknown", "path": "", "line": 0}
        return Check(
            "write_design_gate_audit",
            "error",
            f"{len(findings)} findings; first {first['path']}:{first['line']}:{first['kind']}",
        )
    return Check(
        "write_design_gate_audit",
        "ok",
        (
            f"{payload['design_docs_checked']} design docs, "
            f"{len(payload['approved_write_tools'])} approved write tools"
        ),
    )


def _public_git_checkout_check(root: Path) -> Check:
    try:
        with tempfile.TemporaryDirectory(prefix="local-apple-data-audit-") as tmp:
            destination = Path(tmp) / "public-git"
            result = prepare_public_git_checkout(
                root,
                destination,
                force=True,
                init_git=True,
                commit=True,
            )
    except (RuntimeError, ValueError, OSError) as exc:
        return Check("public_git_checkout", "error", f"public checkout failed: {exc}")

    if result.file_count <= 0:
        return Check("public_git_checkout", "error", "public checkout staged zero files")
    if result.staged_files != result.file_count:
        return Check(
            "public_git_checkout",
            "error",
            f"staged {result.staged_files} files but copied {result.file_count}",
        )
    if not result.committed or result.commit_sha is None:
        return Check("public_git_checkout", "error", "public checkout did not create a commit")
    return Check(
        "public_git_checkout",
        "ok",
        f"{result.file_count} sanitized files committed on {result.branch}",
    )


def _git_remote_check(root: Path) -> Check:
    result = subprocess.run(
        ["git", "remote", "-v"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return Check("git_remote", "warning", "not a git checkout or git remote unavailable")

    remotes = sorted(
        {
            line.split()[0]
            for line in result.stdout.splitlines()
            if line.strip() and len(line.split()) >= 2
        }
    )
    if not remotes:
        return Check("git_remote", "warning", "no git remote configured")
    return Check("git_remote", "ok", f"configured remotes: {', '.join(remotes)}")


def _blockers(checks: list[Check]) -> list[str]:
    blockers: list[str] = []
    for check in checks:
        if check.status == "error":
            blockers.append(check.name)
    if any(check.name == "git_remote" and check.status != "ok" for check in checks):
        blockers.append("missing_git_remote")
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit local public-release readiness.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument(
        "--require-github-ready",
        action="store_true",
        help="Exit nonzero unless the local package and git remote gate both pass.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    payload = audit_release_readiness(Path(args.project_root))
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "release readiness: "
            f"local_package_ready={payload['local_package_ready']} "
            f"github_publication_ready={payload['github_publication_ready']}"
        )
        for check in payload["checks"]:
            print(f"- {check['status']}: {check['name']}: {check['message']}")

    if not payload["local_package_ready"]:
        return 1
    if args.require_github_ready and not payload["github_publication_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import public_release_scan
import redaction_scan
from audit_messages_public_surface import audit_messages_public_surface
from audit_mutation_gates import audit_mutation_gates
from audit_surface_contract import audit_surface_contract
from audit_write_design_gates import REQUIRED_DESIGN_DOCS, audit_write_design_gates
from prepare_public_git_checkout import prepare_public_git_checkout, validated_remote_host


CheckStatus = Literal["ok", "warning", "error"]
SAFE_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SSH_SHORTHAND_REMOTE_RE = re.compile(
    r"^(?P<user>[A-Za-z0-9_.-]+)@(?P<host>[A-Za-z0-9_.-]+):(?P<path>.+)$"
)
REQUIRED_GITIGNORE_LINES = (".claude/", ".env", ".env.*")


BASE_REQUIRED_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "LICENSE",
    "SECURITY.md",
    ".codex-plugin/plugin.json",
    ".mcp.json",
    ".gitignore",
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
    "docs/PRE_PUBLICATION_AUDIT.md",
    "docs/FRESH_CHAT_HANDOFF.md",
    "docs/CAPABILITY_MATRIX.md",
    "docs/MUTATION_GATES.md",
    "docs/V1_33_FULL_CRUD_PRIORITY_PLAN.md",
    "docs/V1_11_REMINDERS_WRITE_DESIGN.md",
    "docs/V1_35_REMINDERS_DELETE_WRITE_DESIGN.md",
    "docs/V1_12_ICLOUD_DRIVE_WRITE_DESIGN.md",
    "docs/V1_13_CALENDAR_WRITE_DESIGN.md",
    "docs/V1_34_CALENDAR_UPDATE_WRITE_DESIGN.md",
    "docs/V1_36_CALENDAR_DELETE_WRITE_DESIGN.md",
    "docs/V1_14_CONTACTS_WRITE_DESIGN.md",
    "docs/V1_48_CONTACTS_UPDATE_WRITE_DESIGN.md",
    "docs/V1_49_CONTACTS_DELETE_WRITE_DESIGN.md",
    "docs/V1_15_NOTES_WRITE_DESIGN.md",
    "docs/V1_16_MAIL_DRAFT_WRITE_DESIGN.md",
    "docs/V1_37_MAIL_FLAG_WRITE_DESIGN.md",
    "docs/V1_40_MAIL_ARCHIVE_WRITE_DESIGN.md",
    "docs/V1_41_MAIL_TRASH_WRITE_DESIGN.md",
    "docs/V1_46_MAIL_MOVE_WRITE_DESIGN.md",
    "docs/V1_43_MAIL_SEND_WRITE_DESIGN.md",
    "docs/V1_44_MAIL_REPLY_WRITE_DESIGN.md",
    "docs/V1_50_MAIL_FORWARD_WRITE_DESIGN.md",
    "docs/V1_17_PHOTOS_IMPORT_WRITE_DESIGN.md",
    "docs/V1_18_ICLOUD_DRIVE_APPEND_WRITE_DESIGN.md",
    "docs/V1_52_ICLOUD_DRIVE_FOLDER_CREATE_WRITE_DESIGN.md",
    "docs/V1_53_ICLOUD_DRIVE_TRASH_WRITE_DESIGN.md",
    "docs/V1_19_NOTES_APPEND_WRITE_DESIGN.md",
    "docs/V1_34_NOTES_REPLACE_WRITE_DESIGN.md",
    "docs/V1_39_NOTES_FOLDER_CREATE_WRITE_DESIGN.md",
    "docs/V1_42_NOTES_DELETE_WRITE_DESIGN.md",
    "docs/V1_45_NOTES_MOVE_WRITE_DESIGN.md",
    "docs/V1_20_NOTES_ATTACHMENT_EXPORT.md",
    "docs/V1_21_MAIL_ATTACHMENT_EXPORT.md",
    "docs/V1_22_MESSAGES_ATTACHMENT_EXPORT.md",
    "docs/V1_23_MESSAGES_ATTRIBUTED_BODY.md",
    "docs/V1_64_MESSAGES_PARTICIPANTS_METADATA.md",
    "docs/V1_24_MESSAGES_SEND_TEXT_WRITE_DESIGN.md",
    "docs/V1_38_MESSAGES_SEND_FILE_WRITE_DESIGN.md",
    "docs/V1_47_MESSAGES_RISKY_MUTATION_SOURCE_REVIEW.md",
    "docs/V1_25_SAFARI_BOOKMARKS.md",
    "docs/V1_26_SHORTCUTS_METADATA.md",
    "docs/V1_27_BOOKS_METADATA.md",
    "docs/V1_28_PODCASTS_METADATA.md",
    "docs/V1_29_MUSIC_METADATA.md",
    "docs/V1_30_TV_METADATA.md",
    "docs/V1_31_FREEFORM_METADATA.md",
    "docs/WRITE_TOOL_ROADMAP.md",
    "docs/PUBLISHING.md",
    "docs/PRIVACY_MODEL.md",
    "docs/THREAT_MODEL.md",
    "docs/TESTING.md",
    "scripts/audit_plugin_artifact_hygiene.py",
    "scripts/audit_release_readiness.py",
    "scripts/audit_mutation_gates.py",
    "scripts/audit_messages_public_surface.py",
    "scripts/audit_surface_contract.py",
    "scripts/audit_write_design_gates.py",
    "scripts/build_public_release_tree.py",
    "scripts/messages_helper.swift",
    "scripts/generate_release_receipt.py",
    "scripts/prepare_public_git_checkout.py",
    "scripts/public_release_scan.py",
    "scripts/redaction_scan.py",
    "scripts/render_mcp_client_config.py",
    "scripts/run_mcp_server.sh",
    "scripts/sync_personal_plugin.py",
    "scripts/verify_runtime.py",
    "skills/local-apple-data/SKILL.md",
    "skills/local-apple-data/agents/openai.yaml",
    "src/local_apple_data/cli.py",
    "src/local_apple_data/health.py",
    "src/local_apple_data/mcp_server.py",
    "tests/test_build_public_release_tree.py",
    "tests/test_mutation_gate_audit.py",
    "tests/test_messages_public_surface_audit.py",
    "tests/test_plugin_packaging.py",
    "tests/test_plugin_artifact_hygiene_audit.py",
    "tests/test_prepare_public_git_checkout.py",
    "tests/test_write_design_gate_audit.py",
    "tests/test_public_release_scan.py",
    "tests/test_redaction_scan_script.py",
    "tests/test_release_readiness_audit.py",
    "tests/test_render_mcp_client_config.py",
    "tests/test_generate_release_receipt.py",
    "tests/test_surface_contract_audit.py",
    "tests/test_sync_personal_plugin.py",
    "tests/test_verify_cross_agent_sync.py",
)
REQUIRED_FILES = tuple(
    dict.fromkeys(
        [
            *BASE_REQUIRED_FILES,
            *(str(contract["path"]) for contract in REQUIRED_DESIGN_DOCS.values()),
        ]
    )
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
        # Report what was actually checked, not len(REQUIRED_FILES). On a generated
        # public tree the operator-only docs are skipped and genuinely are not there,
        # so the full count would be a receipt for files that do not exist.
        checked = len(REQUIRED_FILES) - len(_skipped_required_files(root))
        checks.append(Check("required_files", "ok", f"{checked} files present"))

    checks.append(_gitignore_policy_check(root))
    checks.append(_version_check(root))
    checks.append(_git_worktree_check(root))
    checks.append(_public_scan_check(root))
    checks.append(_redaction_scan_check(root))
    checks.append(_mutation_gate_check(root))
    checks.append(_write_design_gate_check(root))
    checks.append(_messages_public_surface_check(root))
    checks.append(_surface_contract_check(root))
    checks.append(_public_git_checkout_check(root))
    checks.append(_git_remote_check(root))
    checks.append(_git_publication_sync_check(root))

    local_package_ready = all(check.status != "error" for check in checks)
    has_remote = any(check.name == "git_remote" and check.status == "ok" for check in checks)
    publication_synced = any(check.name == "git_publication_sync" and check.status == "ok" for check in checks)
    github_publication_ready = local_package_ready and has_remote and publication_synced
    blockers = _blockers(checks)

    return {
        "blockers": blockers,
        "checks": [
            {"message": check.message, "name": check.name, "status": check.status}
            for check in checks
        ],
        "github_publication_ready": github_publication_ready,
        "local_package_ready": local_package_ready,
        "project_root": "<redacted>",
        "status": "ok" if local_package_ready else "error",
    }


def _skipped_required_files(root: Path) -> set[str]:
    """Required files not checked at ``root`` because it is a generated public tree.

    A generated public tree omits every operator-only doc by design. Requiring them
    there would make the builder's own output fail this audit.
    """

    if not public_release_scan.is_sanitized_public_tree(root):
        return set()
    return {
        relative
        for relative in REQUIRED_FILES
        if relative in public_release_scan.LOCAL_OPERATOR_DOCS
    }


def _missing_required_files(root: Path) -> list[str]:
    missing: list[str] = []
    skipped = _skipped_required_files(root)
    for relative in REQUIRED_FILES:
        if relative in skipped:
            continue
        path = root / relative
        try:
            exists = path.exists()
            is_file = path.is_file()
            content = path.read_bytes() if exists and is_file else b""
        except OSError:
            missing.append(relative)
            continue
        if not exists or not is_file:
            missing.append(relative)
        elif not content:
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


def _gitignore_policy_check(root: Path) -> Check:
    try:
        lines = set((root / ".gitignore").read_text(encoding="utf-8").splitlines())
    except OSError as exc:
        return Check("gitignore_policy", "error", f"source ignore file unreadable: {type(exc).__name__}")

    missing = [line for line in REQUIRED_GITIGNORE_LINES if line not in lines]
    if missing:
        return Check(
            "gitignore_policy",
            "error",
            f"missing local-secret ignore rules: {', '.join(missing)}",
        )
    return Check("gitignore_policy", "ok", "local-secret ignore rules present")


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


def _redaction_scan_check(root: Path) -> Check:
    findings = redaction_scan.scan_paths([root])
    if findings:
        first = findings[0]
        relative = first.path.relative_to(root).as_posix()
        return Check(
            "redaction_scan",
            "error",
            f"{len(findings)} findings; first {relative}:{first.line_number}:{first.pattern}",
        )
    return Check("redaction_scan", "ok", "no redaction findings")


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
        (
            f"{payload['mcp_tools_checked']} MCP tools, "
            f"{payload['cli_handlers_checked']} CLI handlers, "
            f"{len(payload.get('approved_write_tools', []))} approved write tools"
        ),
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


def _messages_public_surface_check(_root: Path) -> Check:
    payload = audit_messages_public_surface()
    if payload["status"] != "ok":
        findings = payload["findings"]
        first = findings[0] if findings else {"kind": "unknown", "name": ""}
        return Check(
            "messages_public_surface_audit",
            "error",
            f"{payload['finding_count']} findings; first {first['name']}:{first['kind']}",
        )
    return Check(
        "messages_public_surface_audit",
        "ok",
        (
            f"{len(payload['commands'])} public commands reviewed; "
            f"{len(payload['blocked_risky_operations'])} risky Messages operations blocked"
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
        return Check(
            "public_git_checkout",
            "error",
            f"public checkout failed: {type(exc).__name__}",
        )

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


def _git_worktree_check(root: Path) -> Check:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Check("git_worktree_clean", "warning", "git worktree status unavailable")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return Check("git_worktree_clean", "warning", "not a git checkout")

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Check("git_worktree_clean", "warning", "git worktree status unavailable")
    if status.returncode != 0:
        return Check("git_worktree_clean", "warning", "git status unavailable")

    changed = [line for line in status.stdout.splitlines() if line.strip()]
    if changed:
        return Check(
            "git_worktree_clean",
            "error",
            f"{len(changed)} uncommitted change(s); commit or discard before release",
        )
    return Check("git_worktree_clean", "ok", "git worktree clean")


def _git_remote_check(root: Path) -> Check:
    safe_remotes, warning = _safe_publication_remotes(root)
    if warning is not None:
        return warning
    return Check("git_remote", "ok", f"configured GitHub publication remotes: {', '.join(safe_remotes)}")


def _safe_publication_remotes(root: Path) -> tuple[list[str], Check | None]:
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], Check("git_remote", "warning", "not a git checkout or git remote unavailable")
    if result.returncode != 0:
        return [], Check("git_remote", "warning", "not a git checkout or git remote unavailable")

    remote_urls_by_name: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remote_urls_by_name.setdefault(parts[0], []).append(parts[1])
    if not remote_urls_by_name:
        return [], Check("git_remote", "warning", "no git remote configured")

    candidate_remotes = sorted(
        name
        for name, urls in remote_urls_by_name.items()
        if _remote_name_is_publication_safe(name)
        and all(_remote_url_is_github_publication_safe(url) for url in urls)
    )
    visibility_unverified = False
    private_or_non_public = False
    safe_remotes: list[str] = []
    for name in candidate_remotes:
        statuses = [_github_remote_visibility(root, url) for url in remote_urls_by_name[name]]
        if all(status == "public" for status in statuses):
            safe_remotes.append(name)
        elif any(status in {"private", "internal"} for status in statuses):
            private_or_non_public = True
        else:
            visibility_unverified = True
    if not safe_remotes:
        if private_or_non_public:
            return [], Check("git_remote", "warning", "no publication-safe public GitHub remote configured")
        if visibility_unverified:
            return [], Check("git_remote", "warning", "GitHub remote public visibility could not be verified")
        return [], Check("git_remote", "warning", "no publication-safe GitHub remote configured")
    return safe_remotes, None


def _git_publication_sync_check(root: Path) -> Check:
    safe_remotes, warning = _safe_publication_remotes(root)
    if warning is not None:
        return Check(
            "git_publication_sync",
            "warning",
            "publication sync unavailable because no safe GitHub remote is configured",
        )
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Check("git_publication_sync", "warning", "git HEAD unavailable for publication sync check")
    if head.returncode != 0 or not head.stdout.strip():
        return Check("git_publication_sync", "warning", "git HEAD unavailable for publication sync check")

    remote_ref_unavailable = False
    for remote in safe_remotes:
        try:
            refs = subprocess.run(
                ["git", "ls-remote", "--heads", "--tags", remote],
                cwd=root,
                env={
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            remote_ref_unavailable = True
            continue
        if refs.returncode != 0:
            remote_ref_unavailable = True
            continue
        head_sha = head.stdout.strip()
        for ref in refs.stdout.splitlines():
            parts = ref.split()
            if len(parts) >= 2 and parts[0] == head_sha:
                return Check("git_publication_sync", "ok", f"current HEAD is advertised by {remote}")
    if remote_ref_unavailable:
        return Check(
            "git_publication_sync",
            "warning",
            "live public GitHub remote refs unavailable for publication sync check",
        )
    return Check(
        "git_publication_sync",
        "warning",
        "current HEAD was not advertised by live public GitHub remote refs",
    )


def _remote_name_is_publication_safe(name: str) -> bool:
    return bool(SAFE_REMOTE_NAME_RE.fullmatch(name))


def _remote_url_is_github_publication_safe(url: str) -> bool:
    try:
        host = validated_remote_host(url)
    except ValueError:
        return False
    return host == "github.com"


def _github_remote_slug(url: str) -> str | None:
    try:
        host = validated_remote_host(url)
    except ValueError:
        return None
    if host != "github.com":
        return None
    shorthand_match = SSH_SHORTHAND_REMOTE_RE.fullmatch(url)
    if shorthand_match:
        path = shorthand_match.group("path")
    else:
        path = urlparse(url).path
    path = unquote(path).strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if owner.startswith("-") or repo.startswith("-"):
        return None
    if any(char.isspace() for char in owner + repo):
        return None
    return f"{owner}/{repo}"


def _github_remote_visibility(root: Path, url: str) -> Literal["public", "private", "internal", "unknown"]:
    slug = _github_remote_slug(url)
    if slug is None:
        return "unknown"
    try:
        result = subprocess.run(
            ["gh", "repo", "view", slug, "--json", "visibility", "--jq", ".visibility"],
            cwd=root,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    visibility = result.stdout.strip().lower()
    if visibility == "public":
        return "public"
    if visibility == "private":
        return "private"
    if visibility == "internal":
        return "internal"
    return "unknown"


def _blockers(checks: list[Check]) -> list[str]:
    blockers: list[str] = []
    for check in checks:
        if check.status == "error":
            blockers.append(check.name)
    if any(check.name == "git_remote" and check.status != "ok" for check in checks):
        blockers.append("missing_git_remote")
    if any(check.name == "git_publication_sync" and check.status != "ok" for check in checks) and not any(
        check.name == "git_remote" and check.status != "ok" for check in checks
    ):
        if any(
            check.name == "git_publication_sync" and "unavailable" in check.message
            for check in checks
        ):
            blockers.append("github_remote_unavailable")
        else:
            blockers.append("unpublished_git_commit")
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit local public-release readiness.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument(
        "--require-github-ready",
        action="store_true",
        help="Exit nonzero unless the local package, public GitHub remote, and live publication-sync gates all pass.",
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

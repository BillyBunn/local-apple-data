#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_public_release_tree import BuildResult, build_release_tree


RESERVED_BRANCH_NAMES = {
    "AUTO_MERGE",
    "BISECT_HEAD",
    "CHERRY_PICK_HEAD",
    "FETCH_HEAD",
    "HEAD",
    "MERGE_HEAD",
    "ORIG_HEAD",
    "REVERT_HEAD",
}

SSH_SHORTHAND_REMOTE_RE = re.compile(
    r"^(?P<user>[A-Za-z0-9_.-]+)@(?P<host>[A-Za-z0-9_.-]+):(?P<path>.+)$"
)


@dataclass(frozen=True)
class PublicGitCheckoutResult:
    branch: str
    commit_sha: str | None
    committed: bool
    destination: Path
    file_count: int
    git_initialized: bool
    remote_configured: bool
    staged_files: int


def prepare_public_git_checkout(
    root: Path,
    destination: Path,
    *,
    force: bool = False,
    init_git: bool = False,
    branch: str = "main",
    remote_url: str = "",
    commit: bool = False,
    commit_message: str = "Initial public release",
    commit_author_name: str = "local-apple-data release",
    commit_author_email: str = "local-apple-data@example.invalid",
) -> PublicGitCheckoutResult:
    if commit and not init_git:
        raise ValueError("--commit requires --init-git")
    if init_git:
        _validate_branch(branch)
        if commit:
            _validate_commit_message(commit_message)
            _validate_git_identity(commit_author_name, commit_author_email)
        if remote_url:
            _validate_remote_url(remote_url)

    release = build_release_tree(root, destination, force=force)
    commit_sha: str | None = None
    committed = False
    staged_files = 0
    remote_configured = False
    if init_git:
        _run_git_init(release.destination, branch)
        _run(["git", "add", "."], cwd=release.destination)
        staged_files = _staged_file_count(release.destination)
        if commit:
            if staged_files <= 0:
                raise RuntimeError("no files staged for initial commit")
            _run(["git", "config", "user.name", commit_author_name], cwd=release.destination)
            _run(["git", "config", "user.email", commit_author_email], cwd=release.destination)
            _run(["git", "commit", "-m", commit_message], cwd=release.destination)
            commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=release.destination).strip()
            committed = True
        if remote_url:
            _run(["git", "remote", "add", "origin", remote_url], cwd=release.destination)
            remote_configured = True

    return PublicGitCheckoutResult(
        branch=branch,
        commit_sha=commit_sha,
        committed=committed,
        destination=release.destination,
        file_count=release.file_count,
        git_initialized=init_git,
        remote_configured=remote_configured,
        staged_files=staged_files,
    )


def _run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} failed with exit {result.returncode}")
    return result.stdout


def _run_git_init(destination: Path, branch: str) -> None:
    try:
        _run(["git", "init", "-b", branch], cwd=destination)
    except RuntimeError:
        _run(["git", "init"], cwd=destination)
        _run(["git", "checkout", "-B", branch], cwd=destination)


def _staged_file_count(destination: Path) -> int:
    output = _run(["git", "diff", "--cached", "--name-only"], cwd=destination)
    return len([line for line in output.splitlines() if line.strip()])


def _validate_branch(branch: str) -> None:
    if not branch or any(char.isspace() for char in branch):
        raise ValueError("branch must be a non-empty single token")
    if branch.startswith("-"):
        raise ValueError("branch must not start with '-'")
    if branch == "@" or branch.startswith("@{") or branch.startswith("refs/"):
        raise ValueError("branch must be a plain branch name")
    if branch in RESERVED_BRANCH_NAMES:
        raise ValueError("branch must not use a reserved git ref name")
    try:
        result = subprocess.run(
            ["git", "check-ref-format", "--allow-onelevel", branch],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("branch could not be validated by git") from None
    if result.returncode != 0:
        raise ValueError("branch is not a valid git branch name")


def _validate_remote_url(remote_url: str) -> None:
    if any(ord(char) < 32 or ord(char) == 127 for char in remote_url):
        raise ValueError("remote URL must not contain control characters")
    trimmed = remote_url.strip()
    if not trimmed:
        raise ValueError("remote URL must not be empty")
    if trimmed.startswith("-"):
        raise ValueError("remote URL must not start with '-'")
    if trimmed != remote_url:
        raise ValueError("remote URL must not include surrounding whitespace")
    if any(char.isspace() for char in remote_url):
        raise ValueError("remote URL must not contain whitespace")
    if not remote_url.isascii():
        raise ValueError("remote URL must be ASCII")
    parsed = urlparse(remote_url)
    shorthand_match = SSH_SHORTHAND_REMOTE_RE.fullmatch(remote_url)
    if parsed.scheme == "https" and (parsed.username or parsed.password):
        raise ValueError("remote URL must not include credentials")
    if parsed.scheme == "ssh" and parsed.password:
        raise ValueError("remote URL must not include credentials")
    host = parsed.hostname or (shorthand_match.group("host") if shorthand_match else "")
    user = parsed.username or (shorthand_match.group("user") if shorthand_match else "")
    if host.startswith("-") or user.startswith("-"):
        raise ValueError("remote URL user and host must not start with '-'")
    if unquote(host).startswith("-") or unquote(user).startswith("-"):
        raise ValueError("remote URL user and host must not start with '-'")
    if shorthand_match and shorthand_match.group("path").startswith("-"):
        raise ValueError("remote URL path must not start with '-'")
    if not _remote_url_uses_allowed_transport(parsed, shorthand_match):
        raise ValueError("remote URL must use https://, ssh://, or user@host:path")


def validate_remote_url(remote_url: str) -> None:
    _validate_remote_url(remote_url)


def validated_remote_host(remote_url: str) -> str:
    _validate_remote_url(remote_url)
    parsed = urlparse(remote_url)
    shorthand_match = SSH_SHORTHAND_REMOTE_RE.fullmatch(remote_url)
    host = parsed.hostname or (shorthand_match.group("host") if shorthand_match else "")
    return host.lower()


def _remote_url_uses_allowed_transport(
    parsed: ParseResult, shorthand_match: re.Match[str] | None
) -> bool:
    if parsed.scheme:
        return (
            parsed.scheme in {"https", "ssh"}
            and bool(parsed.netloc)
            and bool(parsed.path and parsed.path != "/")
        )
    return shorthand_match is not None


def _validate_commit_message(commit_message: str) -> None:
    if not commit_message.strip():
        raise ValueError("commit message must not be empty")
    if "\x00" in commit_message:
        raise ValueError("commit message must not contain NUL")


def _validate_git_identity(name: str, email: str) -> None:
    if not name.strip():
        raise ValueError("commit author name must not be empty")
    if any(char in name for char in "\r\n\x00"):
        raise ValueError("commit author name must be a single line")
    if not email.strip() or "@" not in email:
        raise ValueError("commit author email must look like an email address")
    if any(char in email for char in "\r\n\t\x00"):
        raise ValueError("commit author email must be a single token")


def _payload(result: PublicGitCheckoutResult) -> dict[str, Any]:
    return {
        "branch": result.branch,
        "commit_sha": result.commit_sha,
        "committed": result.committed,
        "destination": str(result.destination),
        "file_count": result.file_count,
        "git_initialized": result.git_initialized,
        "remote_configured": result.remote_configured,
        "staged_files": result.staged_files,
        "status": "ok",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a sanitized public release checkout for GitHub publication."
    )
    parser.add_argument("--dest", required=True, help="Destination directory outside the repo.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Source checkout root.")
    parser.add_argument("--force", action="store_true", help="Replace an existing destination.")
    parser.add_argument("--init-git", action="store_true", help="Initialize git and stage files.")
    parser.add_argument("--branch", default="main", help="Branch name for --init-git.")
    parser.add_argument(
        "--remote-url",
        default="",
        help="Optional HTTPS/SSH origin remote URL for --init-git.",
    )
    parser.add_argument("--commit", action="store_true", help="Create an initial local commit after staging.")
    parser.add_argument(
        "--commit-message",
        default="Initial public release",
        help="Initial commit message for --commit.",
    )
    parser.add_argument(
        "--commit-author-name",
        default="local-apple-data release",
        help="Local git user.name to set before --commit.",
    )
    parser.add_argument(
        "--commit-author-email",
        default="local-apple-data@example.invalid",
        help="Local git user.email to set before --commit.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    try:
        result = prepare_public_git_checkout(
            Path(args.project_root),
            Path(args.dest),
            force=args.force,
            init_git=args.init_git,
            branch=args.branch,
            remote_url=args.remote_url,
            commit=args.commit,
            commit_message=args.commit_message,
            commit_author_name=args.commit_author_name,
            commit_author_email=args.commit_author_email,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(
            f"public git checkout preparation failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1

    payload = _payload(result)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        commit_note = f", commit {result.commit_sha}" if result.commit_sha else ""
        print(
            "public git checkout prepared: "
            f"{result.file_count} files -> {result.destination}{commit_note}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

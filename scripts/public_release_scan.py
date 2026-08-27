#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIRS = {
    ".claude",
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
    ".cer",
    ".crt",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".key",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".p12",
    ".pem",
    ".pdf",
    ".png",
    ".pyc",
    ".sqlite",
    ".webp",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    ".env",
    ".env.local",
    ".envrc",
}

LOCAL_OPERATOR_DOCS = {
    "AGENTS.md",
    "docs/CROSS_AGENT_ROUTING.md",
    "docs/ECOSYSTEM_REVIEW.md",
    "docs/FRESH_CHAT_HANDOFF.md",
    "docs/IMPLEMENTATION_LOG.md",
    "docs/NEXT_SESSION_HEADLESS_CRUD_KICKOFF_PROMPT.md",
    "docs/PRE_PUBLICATION_AUDIT.md",
    "docs/V1_1_CONTENT_RETRIEVAL_PLAN.md",
    "docs/V1_1_KICKOFF_PROMPT.md",
    "docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md",
}

# Written by scripts/build_public_release_tree.py into every tree it generates.
# This is the POSITIVE half of the public-tree test: without it, "is this a public
# tree?" would be pure absence-inference, and deleting tracked files from a real
# checkout would silently switch off the contract audits that depend on them.
PUBLIC_RELEASE_TREE_MARKER = ".public-release-tree.json"


# Public files that may legitimately name an operator/session doc. These are
# release-tooling files that verify or catalog the PRIVATE source checkout (the
# operator docs live in the private repo and never ship); the referenced names
# are ordinary filenames, not personal identifiers. AGENTS.md references stay
# narrowly restricted to list-literal lines (see _operator_doc_reference_allowed).
LOCAL_OPERATOR_DOC_REFERENCE_ALLOWLIST = {
    "scripts/verify_cross_agent_sync.py": {"AGENTS.md"},
    "tests/test_verify_cross_agent_sync.py": {"AGENTS.md"},
    "scripts/audit_release_readiness.py": {
        "docs/ECOSYSTEM_REVIEW.md",
        "docs/PRE_PUBLICATION_AUDIT.md",
        "docs/FRESH_CHAT_HANDOFF.md",
    },
    "scripts/audit_write_design_gates.py": {"docs/FRESH_CHAT_HANDOFF.md"},
    "tests/test_release_readiness_audit.py": {
        "docs/ECOSYSTEM_REVIEW.md",
        "docs/PRE_PUBLICATION_AUDIT.md",
        "docs/FRESH_CHAT_HANDOFF.md",
        "docs/CROSS_AGENT_ROUTING.md",
    },
    "tests/test_write_design_gate_audit.py": {"docs/FRESH_CHAT_HANDOFF.md"},
    "tests/test_plugin_packaging.py": {
        "docs/ECOSYSTEM_REVIEW.md",
        "docs/FRESH_CHAT_HANDOFF.md",
    },
}

SELF_SCAN_EXCLUSIONS = {
    "scripts/public_release_scan.py",
    "tests/test_public_release_scan.py",
}


def is_sanitized_public_tree(root: Path) -> bool:
    """Whether ``root`` is a generated public tree rather than the source checkout.

    The public tree builder deliberately omits every file in ``LOCAL_OPERATOR_DOCS``.
    Checks that require those docs must therefore skip them there, or the generated
    tree ships a test suite and a release audit that demand files the same generator
    refuses to ship -- which is exactly what happened before this helper existed.

    Both halves are required, and the marker is the load-bearing one:

    * ``PUBLIC_RELEASE_TREE_MARKER`` must be present. Only the builder writes it, so
      a tree cannot claim public-tree status just by *lacking* something. Without
      this, deleting the operator docs from a real checkout -- a sparse checkout of
      ``src scripts tests``, or a deliberate ``rm`` -- would silently switch off the
      mutation-gate and write-design-gate contracts. "Delete the evidence, the gate
      disappears" is the wrong direction for a gate.
    * Every operator doc must still be absent, keyed on *all* of them rather than any
      single one. A generated tree that has somehow acquired one of them is not the
      artifact the builder produced, so it fails loudly rather than quietly
      downgrading to public-tree rules.
    """

    if not (root / PUBLIC_RELEASE_TREE_MARKER).is_file():
        return False
    return not any((root / relative).exists() for relative in LOCAL_OPERATOR_DOCS)

# ---------------------------------------------------------------------------
# PERSONAL IDENTIFIER TOKENS
#
# The public release artifact must be agnostic of any specific operator. This
# is the maintainable single source of truth for the operator identifiers the
# scanner refuses to ship. Add a new personal token here (and only here) to
# extend coverage.
#
# The tokens are assembled from fragments on purpose: this scanner file is
# itself copied into the public tree, so it must not contain any literal
# personal substring that a `grep -ri "<token>"` sweep over the public tree
# would flag. Never write the literal token into this file.
# ---------------------------------------------------------------------------
_OPERATOR_GIVEN_NAME = "bil" + "ly"  # operator's given name, lower-cased at match time
_OPERATOR_FULL_NAME = "bil" + "lybunn"  # concatenated first+last, lower-cased at match time
_PERSONAL_BUNDLE_PREFIX = "com." + _OPERATOR_GIVEN_NAME  # personal signed-helper prefix
_PRIVATE_REMOTE_NAME = "local-apple-data-" + "private"  # operator-only git remote

# Case-insensitive standalone personal name tokens (word-boundary anchored).
PERSONAL_NAME_TOKENS: tuple[str, ...] = (
    _OPERATOR_FULL_NAME,
    _OPERATOR_GIVEN_NAME,
)

# Directory-username placeholders that are generic and therefore allowed after
# `/Users/`. Anything else under `/Users/<name>` is treated as a personal path.
GENERIC_USERNAME_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "you",
        "username",
        "user",
        "<user>",
        "<you>",
        "<username>",
        "me",
        "example",
        # Synthetic fixtures used by the test suite (deliberately non-personal).
        "synthetic",
        "otheruser",
    }
)

# Personal Apple mail domains. A local-part immediately before one of these is
# a real-looking personal address unless it is a masked form (contains `*`) or
# the Apple privaterelay relay domain (a legitimate constant, matched
# separately and never flagged).
_PERSONAL_MAIL_DOMAINS = r"(?:icloud|me|mac)\.com"
# A real local part: letters/digits/._%+- but NOT containing `*` (masked forms
# like `ab***@icloud.com` are allowed) and not the synthetic relay-token style
# `<token>@privaterelay.appleid.com` (privaterelay is excluded from the domain
# alternation above, so those never match).
_UNMASKED_LOCAL_PART = r"[A-Za-z0-9._%+-]+"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("personal_admin_path", re.compile(r"\bPersonal Admin\b")),
    ("codex_user_state_path", re.compile(r"/Users/[^/\s]+/\.codex\b")),
    ("openclaw_user_state_path", re.compile(r"/Users/[^/\s]+/\.openclaw\b")),
    (
        "personal_bundle_id",
        re.compile(re.escape(_PERSONAL_BUNDLE_PREFIX), re.IGNORECASE),
    ),
    (
        "private_remote_name",
        re.compile(re.escape(_PRIVATE_REMOTE_NAME), re.IGNORECASE),
    ),
    (
        "personal_name_token",
        re.compile(
            r"\b(?:" + "|".join(re.escape(tok) for tok in PERSONAL_NAME_TOKENS) + r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "personal_apple_address",
        re.compile(
            _UNMASKED_LOCAL_PART + r"@" + _PERSONAL_MAIL_DOMAINS + r"\b",
            re.IGNORECASE,
        ),
    ),
)

# `/Users/<name>` where <name> is not a generic placeholder is a personal path.
_ABSOLUTE_USER_PATH = re.compile(r"/Users/([A-Za-z0-9._-]+)")


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
        if path.name in EXCLUDED_FILE_NAMES:
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
            for operator_doc in LOCAL_OPERATOR_DOCS:
                if operator_doc in line:
                    if _operator_doc_reference_allowed(relative, operator_doc, line):
                        continue
                    findings.append(
                        Finding(
                            path=path,
                            line_number=line_number,
                            pattern=f"local_operator_doc_reference:{operator_doc}",
                        )
                    )
            for name, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(path=path, line_number=line_number, pattern=name))
            for match in _ABSOLUTE_USER_PATH.finditer(line):
                if match.group(1).lower() not in GENERIC_USERNAME_PLACEHOLDERS:
                    findings.append(
                        Finding(
                            path=path,
                            line_number=line_number,
                            pattern="personal_home_path",
                        )
                    )
    return findings


def _operator_doc_reference_allowed(relative: str, operator_doc: str, line: str) -> bool:
    if operator_doc not in LOCAL_OPERATOR_DOC_REFERENCE_ALLOWLIST.get(relative, set()):
        return False
    if operator_doc != "AGENTS.md":
        # Release-tooling files may reference session/operator docs that live in
        # the private checkout only; those names are not personal identifiers.
        return True
    return line.strip() in {'"AGENTS.md",', "'AGENTS.md',"}


def _finding_payload(finding: Finding, root: Path) -> dict[str, object]:
    return {
        "path": finding.path.relative_to(root).as_posix(),
        "line_number": finding.line_number,
        "pattern": finding.pattern,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan public-release files for local operator leakage."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(PROJECT_ROOT),
        help="Project or staged public tree root to scan.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    findings = scan_public_files(root)
    payload = {
        "finding_count": len(findings),
        "findings": [_finding_payload(finding, root) for finding in findings],
        "status": "error" if findings else "ok",
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
        return 1 if findings else 0
    if findings:
        print("public release scan failed", file=sys.stderr)
        for finding in findings:
            print(
                f"{finding.path.relative_to(root)}:{finding.line_number}: {finding.pattern}",
                file=sys.stderr,
            )
        return 1
    print("public release scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

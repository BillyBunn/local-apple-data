"""Prove the Swift contacts helper's create-idempotency / read-back label matching
is consistent with the Python free-form label contract (v1.180A): custom labels are
compared VERBATIM (exact case, spaces, punctuation), so two labels differing only in
case or spacing are DISTINCT, while an exact-verbatim duplicate still matches.

The label-matching logic (`labelsMatchVerbatim`, used by `labeledStringsMatch` /
`phoneNumbersMatch` in the create idempotency pre-check and read-back paths) lives in
the Swift helper. This test extracts the actual shipped functions from
`scripts/contacts_helper.swift` and compiles+runs them so a regression in the real
source is caught, mirroring the repo convention of exercising the helper directly.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts/contacts_helper.swift"


def _extract_func(source: str, name: str) -> str:
    # Extract a top-level `func <name>(...) { ... }` block by brace matching.
    match = re.search(rf"^func {re.escape(name)}\(", source, re.MULTILINE)
    if match is None:
        raise AssertionError(f"function {name} not found in contacts_helper.swift")
    start = match.start()
    depth = 0
    seen_open = False
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
            seen_open = True
        elif char == "}":
            depth -= 1
            if seen_open and depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"function {name} block not closed")


@pytest.mark.skipif(shutil.which("swift") is None, reason="swift toolchain unavailable")
def test_swift_label_matching_is_verbatim_and_case_sensitive(tmp_path) -> None:
    source = HELPER.read_text(encoding="utf-8")
    label_name = _extract_func(source, "labelName")
    contacts_label = _extract_func(source, "contactsLabel")
    matcher = _extract_func(source, "labelsMatchVerbatim")

    harness = tmp_path / "label_match_harness.swift"
    harness.write_text(
        "import Foundation\n"
        "import Contacts\n\n"
        f"{label_name}\n\n"
        f"{contacts_label}\n\n"
        f"{matcher}\n\n"
        'print(labelsMatchVerbatim("Work Phone", "Work Phone"))\n'  # verbatim dup -> true
        'print(labelsMatchVerbatim("Work Phone", "work phone"))\n'  # case-diff -> false
        'print(labelsMatchVerbatim("Work Phone", "work_phone"))\n'  # space/underscore -> false
        'print(labelsMatchVerbatim(CNLabelHome, "home"))\n',  # standard label -> true
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["swift", str(harness)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    assert lines == ["true", "false", "false", "true"], completed.stdout

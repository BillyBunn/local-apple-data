"""Prove the Swift photos helper's output path (`emit`) degrades gracefully instead
of trapping (v1.182). Two latent SIGTRAP crashes were reproduced on real hardware:

1. `emit` wrote to the output file with `try! data.write(to:)`. On a cold PhotoKit
   fetch the Python side timed out, its `TemporaryDirectory` context deleted the
   output directory, and the still-running helper's force-try trapped
   (EXC_BREAKPOINT / SIGTRAP) writing into the now-missing directory.
2. `emit` serialized with `try! JSONSerialization.data(...)`. Any non-JSON value
   (a non-finite Double, a Date, a non-string key) would have thrown into the
   non-throwing `emit` and trapped.

Both are now do/catch + sanitize paths. This test compiles+runs the shipped source
so a regression in `scripts/photos_helper.swift` is caught, mirroring the repo
convention (see `test_contacts_helper_label_matching.py`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts/photos_helper.swift"


def _extract_func(source: str, name: str) -> str:
    # Extract a top-level `func <name>(...) { ... }` block by brace matching.
    match = re.search(rf"^func {re.escape(name)}\(", source, re.MULTILINE)
    if match is None:
        raise AssertionError(f"function {name} not found in photos_helper.swift")
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
def test_serialize_payload_sanitizes_non_json_values_instead_of_trapping(tmp_path) -> None:
    source = HELPER.read_text(encoding="utf-8")
    sanitize = _extract_func(source, "sanitizeForJSON")
    serialize = _extract_func(source, "serializePayload")

    harness = tmp_path / "serialize_harness.swift"
    harness.write_text(
        "import Foundation\n\n"
        "let isoFormatter = ISO8601DateFormatter()\n\n"
        f"{sanitize}\n\n"
        f"{serialize}\n\n"
        # These values would make the old `try! JSONSerialization.data(...)` throw
        # (non-finite Doubles) or misencode (Date). serializePayload must sanitize
        # and produce valid JSON, never trap.
        "let payload: [String: Any] = [\n"
        '    "status": "ok",\n'
        '    "bad_double": Double.nan,\n'
        '    "inf_double": Double.infinity,\n'
        '    "a_date": Date(timeIntervalSince1970: 0),\n'
        '    "keep": 42,\n'
        "]\n"
        "if let data = serializePayload(payload), let text = String(data: data, encoding: .utf8) {\n"
        '    print(text)\n'
        "} else {\n"
        '    print("NIL")\n'
        "}\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["swift", str(harness)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = completed.stdout.strip()
    assert output != "NIL", completed.stdout
    # Non-finite doubles dropped, date coerced to a string, valid value kept.
    assert '"keep":42' in output, output
    assert "nan" not in output.lower(), output
    assert "inf" not in output.lower(), output
    assert '"a_date":"1970-01-01T00:00:00Z"' in output, output


@pytest.mark.skipif(shutil.which("swift") is None, reason="swift toolchain unavailable")
def test_emit_write_to_missing_dir_degrades_without_sigtrap(tmp_path) -> None:
    # Drive the whole shipped helper. An empty (invalid-JSON) request hits the
    # `invalid_request` emit path; pointing --output-json-file at a nonexistent
    # directory forces the file write to fail. The old `try! data.write(...)`
    # would SIGTRAP (negative exit code); the hardened path must write to stdout
    # and exit cleanly with a nonzero (but non-crashing) code.
    empty_input = tmp_path / "empty.json"
    empty_input.write_text("not valid json", encoding="utf-8")
    missing_output = tmp_path / "does" / "not" / "exist" / "output.json"

    completed = subprocess.run(
        [
            "swift",
            str(HELPER),
            "--input-json-file",
            str(empty_input),
            "--output-json-file",
            str(missing_output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    # No crash: SIGTRAP would surface as a negative return code (e.g. -5).
    assert completed.returncode >= 0, f"helper crashed: rc={completed.returncode}"
    assert completed.returncode != 0, "expected a nonzero failure exit, not success"
    assert not missing_output.exists()
    # The degraded output still reaches stdout so the caller can observe it.
    assert '"status":"error"' in completed.stdout.replace(" ", "")
    assert "invalid_request" in completed.stdout

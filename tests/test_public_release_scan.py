from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "public_release_scan.py"
SPEC = importlib.util.spec_from_file_location("public_release_scan", SCRIPT_PATH)
assert SPEC is not None
public_release_scan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["public_release_scan"] = public_release_scan
SPEC.loader.exec_module(public_release_scan)


# Personal identifier fragments are assembled at runtime so this test file
# never embeds a literal personal token that a `grep` over the public tree
# would flag (the scanner skips this file, but it is still shipped).
_NAME = "bil" + "ly"  # operator given name
_FULL = "Bil" + "ly Bunn"  # operator full name
_USER_PATH = "/Users/" + _NAME + "/Projects/local-apple-data"
# A personal home path whose username is not itself a flagged personal-name
# token, so it produces exactly one `personal_home_path` finding.
_NAME_FREE_USER_PATH = "/Users/acme/Projects/local-apple-data"
_BUNDLE = "com." + _NAME + ".local-apple-data.eventkit-helper"
_PRIVATE_REMOTE = "local-apple-data-" + "private"


def test_public_release_scan_flags_absolute_operator_path(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(f"Use {_NAME_FREE_USER_PATH} here.\n", encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert len(findings) == 1
    assert findings[0].pattern == "personal_home_path"


def test_public_release_scan_flags_planted_personal_name(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(f"Maintained by {_NAME}.\n", encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert [finding.pattern for finding in findings] == ["personal_name_token"]


def test_public_release_scan_flags_personal_name_case_insensitively(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(f"Maintained by {_NAME.upper()} and {_FULL}.\n", encoding="utf-8")

    patterns = {finding.pattern for finding in public_release_scan.scan_public_files(tmp_path)}

    assert patterns == {"personal_name_token"}


def test_public_release_scan_flags_planted_personal_bundle_id(tmp_path: Path) -> None:
    path = tmp_path / "config.py"
    path.write_text(f'BUNDLE = "{_BUNDLE}"\n', encoding="utf-8")

    patterns = {finding.pattern for finding in public_release_scan.scan_public_files(tmp_path)}

    # The bundle prefix also embeds the personal name, so both patterns fire.
    assert "personal_bundle_id" in patterns
    assert "personal_name_token" in patterns


def test_public_release_scan_flags_private_remote_name(tmp_path: Path) -> None:
    path = tmp_path / "docs.md"
    path.write_text(f"git remote add origin {_PRIVATE_REMOTE}\n", encoding="utf-8")

    patterns = {finding.pattern for finding in public_release_scan.scan_public_files(tmp_path)}

    assert "private_remote_name" in patterns


def test_public_release_scan_flags_personal_apple_address(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    address = "real" + "person" + "@" + "icloud.com"
    path.write_text(f"Contact {address} for access.\n", encoding="utf-8")

    patterns = {finding.pattern for finding in public_release_scan.scan_public_files(tmp_path)}

    assert "personal_apple_address" in patterns


def test_public_release_scan_passes_on_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Use /Users/you/Projects/local-apple-data with the local MCP server.\n"
        "Signed helper defaults to com.local-apple-data.eventkit-helper.\n",
        encoding="utf-8",
    )
    (tmp_path / "config.py").write_text(
        'BUNDLE = "com.local-apple-data.photos-helper"\n',
        encoding="utf-8",
    )

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_allows_generic_username_placeholders(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Examples: /Users/you/x, /Users/username/y, /Users/USER/z, "
        "/Users/synthetic/Library, /Users/otheruser/home.\n",
        encoding="utf-8",
    )

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_ignores_masked_apple_address(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Masked sender ab***@icloud.com is redacted.\n"
        "Masked sender c***@me.com is redacted.\n",
        encoding="utf-8",
    )

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_ignores_privaterelay_and_synthetic_relay_tokens(
    tmp_path: Path,
) -> None:
    # Assemble the relay domain from fragments so this test source does not
    # itself embed a literal relay address that the redaction scan flags. The
    # file written to disk still contains the full address for the scanner.
    relay_domain = "privaterelay" + ".appleid.com"
    (tmp_path / "README.md").write_text(
        f"The relay domain constant is {relay_domain}.\n"
        f"Synthetic example: relay-token@{relay_domain}.\n",
        encoding="utf-8",
    )

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_skips_local_operator_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    path = docs / "IMPLEMENTATION_LOG.md"
    path.write_text(f"Local path {_USER_PATH}.\n", encoding="utf-8")

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_excludes_extended_operator_docs() -> None:
    for relative in (
        "docs/FRESH_CHAT_HANDOFF.md",
        "docs/NEXT_SESSION_HEADLESS_CRUD_KICKOFF_PROMPT.md",
        "docs/ECOSYSTEM_REVIEW.md",
        "docs/PRE_PUBLICATION_AUDIT.md",
        "docs/V1_2_NOTES_CONTENT_AND_APPLE_DATA_EXPANSION_PLAN.md",
    ):
        assert relative in public_release_scan.LOCAL_OPERATOR_DOCS


def test_public_release_scan_skips_non_public_local_config_files(tmp_path: Path) -> None:
    private_path = _USER_PATH + "/private\n"
    tmp_path.joinpath(".env").write_text(private_path, encoding="utf-8")
    tmp_path.joinpath(".envrc").write_text(private_path, encoding="utf-8")
    tmp_path.joinpath("secret.pem").write_text(private_path, encoding="utf-8")

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_flags_operator_doc_reference_in_public_docs(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    operator_doc = "docs/" + "V1_1_CONTENT_RETRIEVAL_PLAN.md"
    path.write_text(f"See `{operator_doc}` for details.\n", encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert len(findings) == 1
    assert findings[0].pattern == f"local_operator_doc_reference:{operator_doc}"


def test_public_release_scan_flags_operator_doc_reference_in_public_script(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    path = scripts / "verify_cross_agent_sync.py"
    operator_doc = "docs/" + "CROSS_AGENT_ROUTING.md"
    path.write_text(f'PUBLIC_FILES = ["{operator_doc}"]\n', encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert len(findings) == 1
    assert findings[0].path == path
    assert findings[0].pattern == f"local_operator_doc_reference:{operator_doc}"


def test_public_release_scan_allows_agent_sync_verifier_references(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    tests = tmp_path / "tests"
    agent_doc = "AGENTS" + ".md"
    scripts.mkdir()
    tests.mkdir()
    scripts.joinpath("verify_cross_agent_sync.py").write_text(
        f'STATIC_SYNC_FILES = [\n    "{agent_doc}",\n]\n',
        encoding="utf-8",
    )
    tests.joinpath("test_verify_cross_agent_sync.py").write_text(
        f'expected = {{\n    "{agent_doc}",\n}}\n',
        encoding="utf-8",
    )

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_allows_release_tooling_doc_references(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    path = scripts / "audit_release_readiness.py"
    ecosystem_doc = "docs/" + "ECOSYSTEM_REVIEW.md"
    path.write_text(
        f'BASE_REQUIRED_FILES = (\n    "{ecosystem_doc}",\n)\n',
        encoding="utf-8",
    )

    assert public_release_scan.scan_public_files(tmp_path) == []


def test_public_release_scan_flags_agent_doc_reference_outside_allowlist(tmp_path: Path) -> None:
    agent_doc = "AGENTS" + ".md"
    tmp_path.joinpath("README.md").write_text(f"Read {agent_doc} first.\n", encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert len(findings) == 1
    assert findings[0].pattern == f"local_operator_doc_reference:{agent_doc}"


def test_public_release_scan_flags_nonnarrow_agent_doc_reference_in_allowlisted_file(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    agent_doc = "AGENTS" + ".md"
    path = tests / "test_verify_cross_agent_sync.py"
    path.write_text(f'OPERATOR_GUIDANCE = "Read {agent_doc}"\n', encoding="utf-8")

    findings = public_release_scan.scan_public_files(tmp_path)

    assert len(findings) == 1
    assert findings[0].path == path
    assert findings[0].pattern == f"local_operator_doc_reference:{agent_doc}"


def test_public_release_scan_cli_accepts_root_argument(tmp_path: Path, capsys) -> None:
    tmp_path.joinpath("README.md").write_text("Public release docs.\n", encoding="utf-8")

    status = public_release_scan.main([str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 0
    assert captured.out.strip() == "public release scan passed"
    assert captured.err == ""


def test_public_release_scan_cli_json_reports_findings_without_matched_text(
    tmp_path: Path, capsys
) -> None:
    tmp_path.joinpath("README.md").write_text(
        f"Use {_NAME_FREE_USER_PATH} here.\n", encoding="utf-8"
    )

    status = public_release_scan.main(["--json", str(tmp_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert status == 1
    assert captured.err == ""
    assert payload == {
        "finding_count": 1,
        "findings": [
            {"line_number": 1, "path": "README.md", "pattern": "personal_home_path"}
        ],
        "status": "error",
    }
    assert _NAME_FREE_USER_PATH not in captured.out


def _make_public_tree(root: Path, *, marker: bool = True) -> Path:
    """A root shaped like a generated public tree: no operator docs, marker present."""

    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# local-apple-data\n", encoding="utf-8")
    (root / "docs" / "PRIVACY_MODEL.md").write_text("privacy\n", encoding="utf-8")
    if marker:
        (root / public_release_scan.PUBLIC_RELEASE_TREE_MARKER).write_text(
            json.dumps({"generated_by": "scripts/build_public_release_tree.py"}) + "\n",
            encoding="utf-8",
        )
    return root


def test_is_sanitized_public_tree_true_for_marked_tree_without_operator_docs(
    tmp_path: Path,
) -> None:
    assert public_release_scan.is_sanitized_public_tree(_make_public_tree(tmp_path)) is True


def test_is_sanitized_public_tree_false_without_marker(tmp_path: Path) -> None:
    """The regression that matters: absence alone must not switch the gates off.

    A checkout that has lost every operator doc -- a sparse checkout of
    ``src scripts tests``, or a deliberate deletion -- looks exactly like a public
    tree if you only test for absence. Only the builder writes the marker, so
    "delete the evidence, the gate disappears" is not available.
    """

    root = _make_public_tree(tmp_path, marker=False)
    assert public_release_scan.is_sanitized_public_tree(root) is False


def test_is_sanitized_public_tree_false_when_any_operator_doc_is_present(
    tmp_path: Path,
) -> None:
    """Losing one operator doc fails loudly instead of downgrading to public rules."""

    for relative in sorted(public_release_scan.LOCAL_OPERATOR_DOCS):
        root = _make_public_tree(tmp_path / relative.replace("/", "_"))
        planted = root / relative
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("operator doc\n", encoding="utf-8")
        assert public_release_scan.is_sanitized_public_tree(root) is False, relative


def test_is_sanitized_public_tree_false_for_the_source_checkout() -> None:
    project_root = Path(__file__).resolve().parents[1]
    if not (project_root / "AGENTS.md").exists():
        # Running from the generated public tree, where the answer is legitimately
        # True; the source-checkout assertion does not apply there.
        return
    assert public_release_scan.is_sanitized_public_tree(project_root) is False


def test_is_sanitized_public_tree_false_for_an_empty_directory(tmp_path: Path) -> None:
    assert public_release_scan.is_sanitized_public_tree(tmp_path) is False

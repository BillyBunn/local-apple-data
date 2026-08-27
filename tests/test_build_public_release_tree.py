from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_public_release_tree.py"
SPEC = importlib.util.spec_from_file_location("build_public_release_tree", SCRIPT_PATH)
assert SPEC is not None
build_public_release_tree = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["build_public_release_tree"] = build_public_release_tree
SPEC.loader.exec_module(build_public_release_tree)

# The same module object the builder resolved, so the marker constant and the
# operator-doc set cannot drift between the builder and this test.
public_release_scan = build_public_release_tree.public_release_scan


def test_build_release_tree_excludes_operator_docs_and_includes_release_scripts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("# local-apple-data\n", encoding="utf-8")
    (source / ".git").write_text("gitdir: private\n", encoding="utf-8")
    docs = source / "docs"
    docs.mkdir()
    docs.joinpath("IMPLEMENTATION_LOG.md").write_text("local log\n", encoding="utf-8")
    docs.joinpath("INSTALL.md").write_text("install\n", encoding="utf-8")
    scripts = source / "scripts"
    scripts.mkdir()
    scripts.joinpath("public_release_scan.py").write_text("scanner\n", encoding="utf-8")
    scripts.joinpath("build_public_release_tree.py").write_text("builder\n", encoding="utf-8")
    scripts.joinpath(".DS_Store").write_text("finder metadata\n", encoding="utf-8")
    source.joinpath(".env").write_text("LOCAL_ONLY=1\n", encoding="utf-8")
    source.joinpath("release.pem").write_text("not public\n", encoding="utf-8")
    claude_state = source / ".claude"
    claude_state.mkdir()
    claude_state.joinpath("scheduled_tasks.lock").write_text("session lock\n", encoding="utf-8")

    destination = tmp_path / "public"
    result = build_public_release_tree.build_release_tree(source, destination)

    # 4 copied release files plus the generated public-tree marker.
    assert result.file_count == 5
    assert not destination.joinpath(".claude").exists()
    assert destination.joinpath("README.md").exists()
    assert destination.joinpath("docs", "INSTALL.md").exists()
    assert destination.joinpath("scripts", "public_release_scan.py").exists()
    assert destination.joinpath("scripts", "build_public_release_tree.py").exists()
    assert not destination.joinpath(".git").exists()
    assert not destination.joinpath("scripts", ".DS_Store").exists()
    assert not destination.joinpath(".env").exists()
    assert not destination.joinpath("release.pem").exists()
    assert not destination.joinpath("docs", "IMPLEMENTATION_LOG.md").exists()


def test_build_release_tree_refuses_destination_inside_project(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = source / "public"

    try:
        build_public_release_tree.build_release_tree(source, destination)
    except ValueError as exc:
        assert "outside the project root" in str(exc)
    else:
        raise AssertionError("expected destination safety failure")


def test_build_release_tree_refuses_non_empty_destination_without_force(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"
    destination.mkdir()
    destination.joinpath("old.txt").write_text("old\n", encoding="utf-8")

    try:
        build_public_release_tree.build_release_tree(source, destination)
    except ValueError as exc:
        assert "not empty" in str(exc)
    else:
        raise AssertionError("expected non-empty destination failure")


def test_build_release_tree_force_replaces_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"
    destination.mkdir()
    destination.joinpath("old.txt").write_text("old\n", encoding="utf-8")

    result = build_public_release_tree.build_release_tree(source, destination, force=True)

    # 1 copied release file plus the generated public-tree marker.
    assert result.file_count == 2
    assert destination.joinpath("README.md").exists()
    assert not destination.joinpath("old.txt").exists()


def test_main_redacts_release_tree_failure_text(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_build_release_tree(*args, **kwargs):
        raise RuntimeError("scan failed for /private/local/public-tree")

    monkeypatch.setattr(build_public_release_tree, "build_release_tree", fake_build_release_tree)

    status = build_public_release_tree.main(
        [
            "--project-root",
            str(tmp_path / "source"),
            "--dest",
            str(tmp_path / "public"),
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "public release tree build failed: RuntimeError\n"
    assert "/private/" not in captured.err
    assert "scan failed" not in captured.err


def test_main_redacts_release_tree_os_failure_text(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_build_release_tree(*args, **kwargs):
        raise OSError("permission denied for /private/local/public-tree")

    monkeypatch.setattr(build_public_release_tree, "build_release_tree", fake_build_release_tree)

    status = build_public_release_tree.main(
        [
            "--project-root",
            str(tmp_path / "source"),
            "--dest",
            str(tmp_path / "public"),
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "public release tree build failed: OSError\n"
    assert "/private/" not in captured.err
    assert "permission denied" not in captured.err


def test_main_redacts_release_tree_value_failure_text(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def fake_build_release_tree(*args, **kwargs):
        raise ValueError("destination inside /private/local/source")

    monkeypatch.setattr(build_public_release_tree, "build_release_tree", fake_build_release_tree)

    status = build_public_release_tree.main(
        [
            "--project-root",
            str(tmp_path / "source"),
            "--dest",
            str(tmp_path / "public"),
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "public release tree build failed: ValueError\n"
    assert "/private/" not in captured.err
    assert "destination inside" not in captured.err


def test_build_release_tree_writes_marker_that_identifies_it_as_a_public_tree(
    tmp_path: Path,
) -> None:
    """The builder's own output must satisfy ``is_sanitized_public_tree``.

    These two live in different files and drifted apart once already: the builder
    omitted the operator docs while four checks still demanded them. This asserts
    the round trip rather than each half separately.
    """

    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("# local-apple-data\n", encoding="utf-8")
    manifest = source / ".codex-plugin"
    manifest.mkdir()
    manifest.joinpath("plugin.json").write_text(
        json.dumps({"version": "0.1.0+codex.20260101000000"}), encoding="utf-8"
    )
    docs = source / "docs"
    docs.mkdir()
    docs.joinpath("IMPLEMENTATION_LOG.md").write_text("operator only\n", encoding="utf-8")

    destination = tmp_path / "public"
    build_public_release_tree.build_release_tree(source, destination)

    marker = destination / public_release_scan.PUBLIC_RELEASE_TREE_MARKER
    assert marker.is_file()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["generated_by"] == "scripts/build_public_release_tree.py"
    assert payload["source_version"] == "0.1.0+codex.20260101000000"

    assert public_release_scan.is_sanitized_public_tree(destination) is True
    # The source it was built from must never be mistaken for one.
    assert public_release_scan.is_sanitized_public_tree(source) is False

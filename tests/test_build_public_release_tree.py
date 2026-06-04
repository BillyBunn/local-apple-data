from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_public_release_tree.py"
SPEC = importlib.util.spec_from_file_location("build_public_release_tree", SCRIPT_PATH)
assert SPEC is not None
build_public_release_tree = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["build_public_release_tree"] = build_public_release_tree
SPEC.loader.exec_module(build_public_release_tree)


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

    destination = tmp_path / "public"
    result = build_public_release_tree.build_release_tree(source, destination)

    assert result.file_count == 4
    assert destination.joinpath("README.md").exists()
    assert destination.joinpath("docs", "INSTALL.md").exists()
    assert destination.joinpath("scripts", "public_release_scan.py").exists()
    assert destination.joinpath("scripts", "build_public_release_tree.py").exists()
    assert not destination.joinpath(".git").exists()
    assert not destination.joinpath("scripts", ".DS_Store").exists()
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

    assert result.file_count == 1
    assert destination.joinpath("README.md").exists()
    assert not destination.joinpath("old.txt").exists()

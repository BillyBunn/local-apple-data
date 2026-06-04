from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_public_git_checkout.py"
SPEC = importlib.util.spec_from_file_location("prepare_public_git_checkout", SCRIPT_PATH)
assert SPEC is not None
prepare_public_git_checkout = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["prepare_public_git_checkout"] = prepare_public_git_checkout
SPEC.loader.exec_module(prepare_public_git_checkout)


def test_prepare_public_git_checkout_builds_git_ready_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    docs = source / "docs"
    docs.mkdir()
    docs.joinpath("INSTALL.md").write_text("install\n", encoding="utf-8")
    docs.joinpath("IMPLEMENTATION_LOG.md").write_text("private log\n", encoding="utf-8")

    destination = tmp_path / "public"
    result = prepare_public_git_checkout.prepare_public_git_checkout(
        source,
        destination,
        init_git=True,
        branch="main",
    )

    assert result.file_count == 2
    assert result.committed is False
    assert result.commit_sha is None
    assert result.git_initialized is True
    assert result.remote_configured is False
    assert result.staged_files == 2
    assert destination.joinpath(".git").is_dir()
    assert destination.joinpath("README.md").exists()
    assert destination.joinpath("docs", "INSTALL.md").exists()
    assert not destination.joinpath("docs", "IMPLEMENTATION_LOG.md").exists()


def test_prepare_public_git_checkout_can_create_initial_commit(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")

    destination = tmp_path / "public"
    result = prepare_public_git_checkout.prepare_public_git_checkout(
        source,
        destination,
        init_git=True,
        branch="main",
        commit=True,
        commit_message="Initial sanitized public release",
    )

    assert result.file_count == 1
    assert result.staged_files == 1
    assert result.committed is True
    assert result.commit_sha is not None
    assert len(result.commit_sha) == 40

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=destination,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout
    assert status == ""


def test_prepare_public_git_checkout_commit_requires_git_init(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            tmp_path / "public",
            commit=True,
        )
    except ValueError as exc:
        assert "--commit requires --init-git" in str(exc)
    else:
        raise AssertionError("expected commit without init-git failure")


def test_prepare_public_git_checkout_rejects_bad_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            tmp_path / "public",
            init_git=True,
            branch="bad branch",
        )
    except ValueError as exc:
        assert "branch" in str(exc)
    else:
        raise AssertionError("expected branch validation failure")


def test_prepare_public_git_checkout_rejects_bad_commit_identity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            tmp_path / "public",
            init_git=True,
            commit=True,
            commit_author_email="not-an-email",
        )
    except ValueError as exc:
        assert "email" in str(exc)
    else:
        raise AssertionError("expected commit identity validation failure")


def test_prepare_public_git_checkout_rejects_bad_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            tmp_path / "public",
            init_git=True,
            remote_url="https://example.com/repo.git\nextra",
        )
    except ValueError as exc:
        assert "remote URL" in str(exc)
    else:
        raise AssertionError("expected remote URL validation failure")

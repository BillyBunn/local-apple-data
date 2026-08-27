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

import audit_release_readiness


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

    # 2 copied release files plus the generated public-tree marker.
    assert result.file_count == 3
    assert result.committed is False
    assert result.commit_sha is None
    assert result.git_initialized is True
    assert result.remote_configured is False
    # git stages the marker too, so this must equal file_count -- the invariant
    # audit_release_readiness checks as `public_git_checkout`.
    assert result.staged_files == 3
    assert result.staged_files == result.file_count
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

    # 1 copied release file plus the generated public-tree marker.
    assert result.file_count == 2
    assert result.staged_files == 2
    assert result.staged_files == result.file_count
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


def test_prepare_public_git_checkout_rebuilds_generated_tree_idempotently(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    manifest = source / ".codex-plugin"
    manifest.mkdir()
    manifest.joinpath("plugin.json").write_text(
        '{"version":"0.1.0+codex.20260101000000"}\n',
        encoding="utf-8",
    )

    generated = tmp_path / "generated"
    first = prepare_public_git_checkout.prepare_public_git_checkout(source, generated)

    rebuilt = tmp_path / "rebuilt"
    second = prepare_public_git_checkout.prepare_public_git_checkout(
        generated,
        rebuilt,
        init_git=True,
        commit=True,
    )

    assert second.file_count == first.file_count
    assert second.staged_files == second.file_count
    assert second.committed is True
    assert audit_release_readiness._public_git_checkout_check(generated).status == "ok"


def test_main_redacts_prepare_failure_text(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_prepare_public_git_checkout(*args, **kwargs):
        raise RuntimeError("git failed in /private/local/public-checkout")

    monkeypatch.setattr(
        prepare_public_git_checkout,
        "prepare_public_git_checkout",
        fake_prepare_public_git_checkout,
    )

    status = prepare_public_git_checkout.main(
        [
            "--project-root",
            str(tmp_path / "source"),
            "--dest",
            str(tmp_path / "public"),
            "--init-git",
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "public git checkout preparation failed: RuntimeError\n"
    assert "/private/" not in captured.err
    assert "git failed" not in captured.err


def test_main_redacts_prepare_os_failure_text(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_prepare_public_git_checkout(*args, **kwargs):
        raise OSError("permission denied for /private/local/public-checkout")

    monkeypatch.setattr(
        prepare_public_git_checkout,
        "prepare_public_git_checkout",
        fake_prepare_public_git_checkout,
    )

    status = prepare_public_git_checkout.main(
        [
            "--project-root",
            str(tmp_path / "source"),
            "--dest",
            str(tmp_path / "public"),
            "--init-git",
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "public git checkout preparation failed: OSError\n"
    assert "/private/" not in captured.err
    assert "permission denied" not in captured.err


def test_main_redacts_prepare_value_failure_text(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_prepare_public_git_checkout(*args, **kwargs):
        raise ValueError("destination inside /private/local/source")

    monkeypatch.setattr(
        prepare_public_git_checkout,
        "prepare_public_git_checkout",
        fake_prepare_public_git_checkout,
    )

    status = prepare_public_git_checkout.main(
        [
            "--project-root",
            str(tmp_path / "source"),
            "--dest",
            str(tmp_path / "public"),
            "--init-git",
        ]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "public git checkout preparation failed: ValueError\n"
    assert "/private/" not in captured.err
    assert "destination inside" not in captured.err


def test_prepare_public_git_checkout_can_add_https_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"
    remote_url = "https://github.com/example/local-apple-data.git"

    result = prepare_public_git_checkout.prepare_public_git_checkout(
        source,
        destination,
        init_git=True,
        remote_url=remote_url,
    )

    assert result.remote_configured is True
    configured = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=destination,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    assert configured == remote_url


def test_prepare_public_git_checkout_can_add_ssh_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"
    remote_url = "ssh://git@github.com/example/local-apple-data.git"

    result = prepare_public_git_checkout.prepare_public_git_checkout(
        source,
        destination,
        init_git=True,
        remote_url=remote_url,
    )

    assert result.remote_configured is True
    configured = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=destination,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    assert configured == remote_url


def test_prepare_public_git_checkout_can_add_ssh_shorthand_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"
    remote_url = "git@github.com:example/local-apple-data.git"

    result = prepare_public_git_checkout.prepare_public_git_checkout(
        source,
        destination,
        init_git=True,
        remote_url=remote_url,
    )

    assert result.remote_configured is True
    configured = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=destination,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    assert configured == remote_url


def test_validated_remote_host_normalizes_url_and_shorthand_hosts() -> None:
    assert (
        prepare_public_git_checkout.validated_remote_host(
            "https://GitHub.com/example/local-apple-data.git"
        )
        == "github.com"
    )
    assert (
        prepare_public_git_checkout.validated_remote_host(
            "git@GITHUB.com:example/local-apple-data.git"
        )
        == "github.com"
    )


def test_prepare_public_git_checkout_commit_requires_git_init(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            commit=True,
        )
    except ValueError as exc:
        assert "--commit requires --init-git" in str(exc)
    else:
        raise AssertionError("expected commit without init-git failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_bad_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            branch="bad branch",
        )
    except ValueError as exc:
        assert "branch" in str(exc)
    else:
        raise AssertionError("expected branch validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_invalid_branch_does_not_replace_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"
    destination.mkdir()
    destination.joinpath("old.txt").write_text("old\n", encoding="utf-8")

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            force=True,
            init_git=True,
            branch="bad branch",
        )
    except ValueError as exc:
        assert "branch" in str(exc)
    else:
        raise AssertionError("expected branch validation failure")
    assert destination.joinpath("old.txt").read_text(encoding="utf-8") == "old\n"


def test_prepare_public_git_checkout_rejects_ref_prefixed_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            branch="refs/heads/main",
        )
    except ValueError as exc:
        assert "plain branch" in str(exc)
    else:
        raise AssertionError("expected ref-prefixed branch validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_at_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            branch="@",
        )
    except ValueError as exc:
        assert "plain branch" in str(exc)
    else:
        raise AssertionError("expected at-branch validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_reserved_branch_before_git_init(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            branch="HEAD",
        )
    except ValueError as exc:
        assert "reserved git ref" in str(exc)
    else:
        raise AssertionError("expected reserved branch validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_branch_validation_does_not_require_git_checkout(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    prepare_public_git_checkout._validate_branch("main")


def test_prepare_public_git_checkout_rejects_git_invalid_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            branch="release..bad",
        )
    except ValueError as exc:
        assert "valid git branch" in str(exc)
    else:
        raise AssertionError("expected git branch validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_branch_shorthand(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            branch="@{-1}",
        )
    except ValueError as exc:
        assert "plain branch" in str(exc)
    else:
        raise AssertionError("expected branch shorthand validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_bad_commit_identity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            commit=True,
            commit_author_email="not-an-email",
        )
    except ValueError as exc:
        assert "email" in str(exc)
    else:
        raise AssertionError("expected commit identity validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_bad_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https://example.com/repo.git\nextra",
        )
    except ValueError as exc:
        assert "remote URL" in str(exc)
    else:
        raise AssertionError("expected remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_option_like_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="--upload-pack=echo nope",
        )
    except ValueError as exc:
        assert "start with '-'" in str(exc)
    else:
        raise AssertionError("expected option-like remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_whitespace_option_like_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url=" --upload-pack=echo nope",
        )
    except ValueError as exc:
        assert "start with '-'" in str(exc)
    else:
        raise AssertionError("expected option-like remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_control_character_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https://example.com/repo.git\x00",
        )
    except ValueError as exc:
        assert "control characters" in str(exc)
    else:
        raise AssertionError("expected control-character remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_surrounding_whitespace_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url=" https://example.com/repo.git ",
        )
    except ValueError as exc:
        assert "surrounding whitespace" in str(exc)
    else:
        raise AssertionError("expected surrounding-whitespace remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_internal_whitespace_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https://github.com/example/local apple data.git",
        )
    except ValueError as exc:
        assert "whitespace" in str(exc)
    else:
        raise AssertionError("expected internal-whitespace remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_non_ascii_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https://github.com/example/local-apple-data\u200b.git",
        )
    except ValueError as exc:
        assert "ASCII" in str(exc)
    else:
        raise AssertionError("expected non-ASCII remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_file_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="file:///tmp/local-apple-data.git",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected disallowed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_local_path_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="../local-apple-data.git",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected disallowed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_git_protocol_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="git://github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected disallowed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_http_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="http://github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected disallowed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_remote_url_without_repo_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https://github.com/",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected pathless remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_scheme_only_remote_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https:github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected malformed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_remote_url_with_credentials(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="https://user:token@github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "credentials" in str(exc)
    else:
        raise AssertionError("expected credentialed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_ssh_remote_url_with_password(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="ssh://git:token@github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "credentials" in str(exc)
    else:
        raise AssertionError("expected credentialed remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_url_host_starting_with_dash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="ssh://-evil.example/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "host" in str(exc)
    else:
        raise AssertionError("expected dash-host remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_url_user_starting_with_dash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="ssh://-git@github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "user" in str(exc)
        assert "host" in str(exc)
    else:
        raise AssertionError("expected dash-user remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_url_encoded_dash_user(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="ssh://%2Dgit@github.com/example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "user" in str(exc)
        assert "host" in str(exc)
    else:
        raise AssertionError("expected encoded dash-user remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_shorthand_host_starting_with_dash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="git@-evil.example:example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "host" in str(exc)
    else:
        raise AssertionError("expected dash-host remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_shorthand_user_starting_with_dash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="-git@github.com:example/local-apple-data.git",
        )
    except ValueError as exc:
        assert "start with '-'" in str(exc)
    else:
        raise AssertionError("expected dash-user remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_shorthand_path_starting_with_dash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="git@github.com:--upload-pack=evil",
        )
    except ValueError as exc:
        assert "path" in str(exc)
    else:
        raise AssertionError("expected dash-path remote URL validation failure")
    assert not destination.exists()


def test_prepare_public_git_checkout_rejects_ext_remote_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source.joinpath("README.md").write_text("# local-apple-data\n", encoding="utf-8")
    destination = tmp_path / "public"

    try:
        prepare_public_git_checkout.prepare_public_git_checkout(
            source,
            destination,
            init_git=True,
            remote_url="ext::echo-nope",
        )
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected disallowed remote URL validation failure")
    assert not destination.exists()

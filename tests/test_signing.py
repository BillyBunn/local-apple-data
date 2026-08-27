from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from typing import Any

from local_apple_data.adapters import _signing

_PEM = (
    "-----BEGIN CERTIFICATE-----\nMIIBfakefakefake\n-----END CERTIFICATE-----\n"
)


class _Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@contextlib.contextmanager
def _no_lock():
    yield


def test_signing_identity_prefers_env_override(monkeypatch) -> None:
    monkeypatch.setenv(_signing.SIGNING_IDENTITY_ENV, "Apple Development: Someone")

    def _which(_name: str) -> str:
        raise AssertionError("security should not be probed when override is set")

    monkeypatch.setattr(_signing.shutil, "which", _which)

    assert _signing.signing_identity() == "Apple Development: Someone"


def test_signing_identity_uses_conventional_cert_when_present(monkeypatch) -> None:
    monkeypatch.delenv(_signing.SIGNING_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")

    def _run(cmd: list[str], **_kwargs: Any) -> _Completed:
        if "find-certificate" in cmd:
            assert cmd[-1] == "-p" or "-p" in cmd
            return _Completed(0, stdout=_PEM)
        if cmd[1:2] == ["x509"]:
            return _Completed(
                0, stdout=f"subject=CN = {_signing.DEFAULT_LOCAL_SIGNING_IDENTITY}\n"
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    assert _signing.signing_identity() == _signing.DEFAULT_LOCAL_SIGNING_IDENTITY


def test_signing_identity_rejects_substring_only_match(monkeypatch) -> None:
    """A cert whose CN merely *contains* the name must not be treated as ours."""
    monkeypatch.delenv(_signing.SIGNING_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")

    def _run(cmd: list[str], **_kwargs: Any) -> _Completed:
        if "find-certificate" in cmd:
            return _Completed(0, stdout=_PEM)
        if cmd[1:2] == ["x509"]:
            # Substring superstring CN — not an exact match.
            return _Completed(
                0,
                stdout=(
                    "subject=CN = Archived "
                    f"{_signing.DEFAULT_LOCAL_SIGNING_IDENTITY} backup 2024\n"
                ),
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    assert _signing.signing_identity() is None


def test_signing_identity_coarse_when_openssl_absent(monkeypatch) -> None:
    """Without openssl the exact check can't run; coarse substring match stands."""
    monkeypatch.delenv(_signing.SIGNING_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(
        _signing.shutil,
        "which",
        lambda name: "/usr/bin/security" if name == "security" else None,
    )

    def _run(cmd: list[str], **_kwargs: Any) -> _Completed:
        assert "find-certificate" in cmd
        return _Completed(0, stdout=_PEM)

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    assert _signing.signing_identity() == _signing.DEFAULT_LOCAL_SIGNING_IDENTITY


def test_signing_identity_none_when_cert_absent(monkeypatch) -> None:
    monkeypatch.delenv(_signing.SIGNING_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        _signing.subprocess, "run", lambda *a, **k: _Completed(1, stderr="not found")
    )

    assert _signing.signing_identity() is None


def test_signing_identity_none_when_security_missing(monkeypatch) -> None:
    monkeypatch.delenv(_signing.SIGNING_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: None)

    assert _signing.signing_identity() is None


def test_codesign_command_stable_identity_shape(tmp_path: Path) -> None:
    entitlements = tmp_path / "entitlements.plist"
    app = tmp_path / "Helper.app"

    cmd = _signing.codesign_command(
        "/usr/bin/codesign", entitlements, app, _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    )

    assert cmd[0] == "/usr/bin/codesign"
    assert cmd[1:3] == ["-s", _signing.DEFAULT_LOCAL_SIGNING_IDENTITY]
    assert "--options" in cmd and "runtime" in cmd
    assert "--entitlements" in cmd
    assert str(entitlements) in cmd
    assert str(app) == cmd[-1]
    assert "-" not in cmd[1:3]


def test_codesign_command_ad_hoc_shape(tmp_path: Path) -> None:
    entitlements = tmp_path / "entitlements.plist"
    app = tmp_path / "Helper.app"

    cmd = _signing.codesign_command("/usr/bin/codesign", entitlements, app, None)

    assert cmd[1:3] == ["-s", "-"]
    assert "--deep" in cmd
    assert "--options" not in cmd
    assert "--entitlements" in cmd


def test_sign_helper_app_uses_stable_when_it_succeeds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        _signing, "signing_identity", lambda: _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    )
    runs: list[list[str]] = []

    def _run(cmd: list[str], **_k: Any) -> _Completed:
        runs.append(cmd)
        return _Completed(0)

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    result = _signing.sign_helper_app(
        "/usr/bin/codesign", tmp_path / "e.plist", tmp_path / "Helper.app"
    )

    assert result.returncode == 0
    # Only the stable attempt ran; no ad-hoc fallback.
    assert len(runs) == 1
    assert runs[0][1:3] == ["-s", _signing.DEFAULT_LOCAL_SIGNING_IDENTITY]


def test_sign_helper_app_falls_back_to_ad_hoc_on_failure(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        _signing, "signing_identity", lambda: _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    )
    runs: list[list[str]] = []

    def _run(cmd: list[str], **_k: Any) -> _Completed:
        runs.append(cmd)
        # Stable attempt (named identity) fails; ad-hoc ("-s","-") succeeds.
        if cmd[1:3] == ["-s", "-"]:
            return _Completed(0)
        return _Completed(1, stderr="no identity found")

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    result = _signing.sign_helper_app(
        "/usr/bin/codesign", tmp_path / "e.plist", tmp_path / "Helper.app"
    )

    assert result.returncode == 0
    assert len(runs) == 2
    assert runs[0][1:3] == ["-s", _signing.DEFAULT_LOCAL_SIGNING_IDENTITY]
    assert runs[1][1:3] == ["-s", "-"]


def test_sign_helper_app_ad_hoc_only_when_no_identity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_signing, "signing_identity", lambda: None)
    runs: list[list[str]] = []

    def _run(cmd: list[str], **_k: Any) -> _Completed:
        runs.append(cmd)
        return _Completed(1)  # even on failure, no stable retry to attempt

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    result = _signing.sign_helper_app(
        "/usr/bin/codesign", tmp_path / "e.plist", tmp_path / "Helper.app"
    )

    assert result.returncode == 1
    assert len(runs) == 1
    assert runs[0][1:3] == ["-s", "-"]


def test_provision_short_circuits_when_identity_present(monkeypatch) -> None:
    # Opt in to the keychain-mutating path. subprocess is mocked below; this
    # assertion of intent is what _signing.provisioning_allowed exists to require.
    monkeypatch.setattr(_signing, "provisioning_allowed", lambda: True)
    monkeypatch.setattr(
        _signing, "signing_identity", lambda: _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    )

    def _which(_name: str) -> str:
        raise AssertionError("provisioning must not run when an identity exists")

    monkeypatch.setattr(_signing.shutil, "which", _which)

    assert (
        _signing.provision_local_signing_identity()
        == _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    )


def test_provision_returns_none_when_tooling_absent(monkeypatch) -> None:
    # Opt in to the keychain-mutating path. subprocess is mocked below; this
    # assertion of intent is what _signing.provisioning_allowed exists to require.
    monkeypatch.setattr(_signing, "provisioning_allowed", lambda: True)
    monkeypatch.setattr(_signing, "signing_identity", lambda: None)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: None)

    def _run(*_a: Any, **_k: Any) -> _Completed:
        raise AssertionError("no subprocess should run without openssl/security")

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    assert _signing.provision_local_signing_identity() is None


def test_provision_generates_cert_and_confirms_identity(monkeypatch) -> None:
    # Opt in to the keychain-mutating path. subprocess is mocked below; this
    # assertion of intent is what _signing.provisioning_allowed exists to require.
    monkeypatch.setattr(_signing, "provisioning_allowed", lambda: True)
    monkeypatch.setattr(_signing, "_provision_lock", _no_lock)
    calls = {"count": 0}

    def _identity() -> str | None:
        calls["count"] += 1
        return None if calls["count"] <= 2 else _signing.DEFAULT_LOCAL_SIGNING_IDENTITY

    monkeypatch.setattr(_signing, "signing_identity", _identity)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")

    recorded: list[str] = []

    def _run(cmd: list[str], **_kwargs: Any) -> _Completed:
        recorded.append(Path(cmd[0]).name)
        return _Completed(0)

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    result = _signing.provision_local_signing_identity()

    assert result == _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    assert recorded == ["openssl", "openssl", "security"]


def test_provision_rechecks_identity_under_lock(monkeypatch) -> None:
    # Opt in to the keychain-mutating path. subprocess is mocked below; this
    # assertion of intent is what _signing.provisioning_allowed exists to require.
    monkeypatch.setattr(_signing, "provisioning_allowed", lambda: True)
    """A concurrent import observed after acquiring the lock short-circuits."""
    monkeypatch.setattr(_signing, "_provision_lock", _no_lock)
    calls = {"count": 0}

    def _identity() -> str | None:
        calls["count"] += 1
        # 1st call (pre-lock) None; 2nd call (post-lock re-check) present.
        return None if calls["count"] == 1 else _signing.DEFAULT_LOCAL_SIGNING_IDENTITY

    monkeypatch.setattr(_signing, "signing_identity", _identity)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")

    def _run(*_a: Any, **_k: Any) -> _Completed:
        raise AssertionError("must short-circuit on re-check; no keygen/import")

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    assert (
        _signing.provision_local_signing_identity()
        == _signing.DEFAULT_LOCAL_SIGNING_IDENTITY
    )


def test_provision_returns_none_on_openssl_failure(monkeypatch) -> None:
    # Opt in to the keychain-mutating path. subprocess is mocked below; this
    # assertion of intent is what _signing.provisioning_allowed exists to require.
    monkeypatch.setattr(_signing, "provisioning_allowed", lambda: True)
    monkeypatch.setattr(_signing, "_provision_lock", _no_lock)
    monkeypatch.setattr(_signing, "signing_identity", lambda: None)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        _signing.subprocess, "run", lambda *a, **k: _Completed(1, stderr="boom")
    )

    assert _signing.provision_local_signing_identity() is None


def test_provision_import_is_codesign_scoped_not_all_apps(monkeypatch) -> None:
    # Opt in to the keychain-mutating path. subprocess is mocked below; this
    # assertion of intent is what _signing.provisioning_allowed exists to require.
    monkeypatch.setattr(_signing, "provisioning_allowed", lambda: True)
    """The durable key must be imported with -T codesign only, never -A."""
    monkeypatch.setattr(_signing, "_provision_lock", _no_lock)
    monkeypatch.setattr(_signing, "signing_identity", lambda: None)
    monkeypatch.setattr(_signing.shutil, "which", lambda name: f"/usr/bin/{name}")

    commands: list[list[str]] = []

    def _run(cmd: list[str], **_kwargs: Any) -> _Completed:
        commands.append(cmd)
        return _Completed(0)

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    _signing.provision_local_signing_identity()

    pkcs12 = next(c for c in commands if "pkcs12" in c)
    assert "-legacy" in pkcs12
    security_import = next(c for c in commands if c[0].endswith("security"))
    assert "import" in security_import
    assert "-T" in security_import and "/usr/bin/codesign" in security_import
    assert any(arg.endswith("login.keychain-db") for arg in security_import)
    # -A grants silent access to ALL applications; it must not be present.
    assert "-A" not in security_import


def test_app_signing_authority_reads_leaf_authority(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(_signing.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        _signing.subprocess,
        "run",
        lambda *a, **k: _Completed(
            0, stderr="Identifier=x\nAuthority=Local Apple Data Signing\nTeamId=not set\n"
        ),
    )

    assert _signing.app_signing_authority(app) == "Local Apple Data Signing"


def test_app_signing_authority_reports_ad_hoc_as_empty(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(_signing.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        _signing.subprocess,
        "run",
        lambda *a, **k: _Completed(0, stderr="Identifier=x\nSignature=adhoc\n"),
    )

    assert _signing.app_signing_authority(app) == ""
    assert _signing.app_signed_ad_hoc(app) is True


def test_invalidate_removes_ad_hoc_when_identity_present(
    monkeypatch, tmp_path: Path
) -> None:
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(_signing, "app_signing_authority", lambda _p: "")

    assert _signing.invalidate_app_if_signing_mismatch(app, "Stable Identity") is True
    assert not app.exists()


def test_invalidate_removes_when_authority_differs(monkeypatch, tmp_path: Path) -> None:
    """Switching to a different named identity (e.g. Apple Development) rebuilds."""
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(
        _signing, "app_signing_authority", lambda _p: "Local Apple Data Signing"
    )

    assert (
        _signing.invalidate_app_if_signing_mismatch(app, "Apple Development: X") is True
    )
    assert not app.exists()


def test_invalidate_keeps_matching_authority(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(
        _signing, "app_signing_authority", lambda _p: "Local Apple Data Signing"
    )

    assert (
        _signing.invalidate_app_if_signing_mismatch(app, "Local Apple Data Signing")
        is False
    )
    assert app.exists()


def test_invalidate_never_removes_when_no_usable_identity(
    monkeypatch, tmp_path: Path
) -> None:
    """A locked keychain / no identity must not delete a working helper (grant)."""
    app = tmp_path / "Helper.app"
    app.mkdir()
    # Even a stable-signed on-disk app is left intact when identity is None: a
    # rebuild could only downgrade to ad-hoc and orphan an existing TCC grant.
    monkeypatch.setattr(
        _signing, "app_signing_authority", lambda _p: "Local Apple Data Signing"
    )
    assert _signing.invalidate_app_if_signing_mismatch(app, None) is False
    assert app.exists()


def test_invalidate_no_op_when_state_indeterminate(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(_signing, "app_signing_authority", lambda _p: None)

    assert _signing.invalidate_app_if_signing_mismatch(app, "Stable Identity") is False
    assert app.exists()


def test_provisioning_refuses_under_pytest_without_explicit_opt_in(monkeypatch) -> None:
    """The keychain-mutating path is closed by default while tests run.

    Deliberately does NOT patch `provisioning_allowed`. If a future test forgets to
    mock subprocess, this is what stops it importing a second identity into the
    operator's real login keychain.
    """
    monkeypatch.delenv(_signing.SIGNING_IDENTITY_ENV, raising=False)

    def _which(_name: str) -> str:
        raise AssertionError("provisioning must refuse before probing for tooling")

    def _run(cmd: list[str], **_k: Any) -> _Completed:
        raise AssertionError(f"provisioning must not shell out under pytest: {cmd}")

    monkeypatch.setattr(_signing.shutil, "which", _which)
    monkeypatch.setattr(_signing.subprocess, "run", _run)

    assert _signing.provisioning_allowed() is False
    assert _signing.provision_local_signing_identity() is None


def test_provision_lock_follows_state_dir_override(monkeypatch, tmp_path: Path) -> None:
    """The lock file is the only real on-disk write this module makes."""
    monkeypatch.setenv(_signing.STATE_DIR_ENV, str(tmp_path / "state"))

    lock_path = _signing._provision_lock_path()

    assert lock_path == tmp_path / "state" / ".signing-provision.lock"
    assert Path.home() not in lock_path.parents


def test_provision_lock_defaults_into_application_support(monkeypatch) -> None:
    monkeypatch.delenv(_signing.STATE_DIR_ENV, raising=False)

    lock_path = _signing._provision_lock_path()

    assert lock_path.parent == (
        Path.home() / "Library" / "Application Support" / "local-apple-data"
    )


def test_guard_transitively_protects_helper_app_deletion(monkeypatch, tmp_path: Path) -> None:
    """The refusal also protects the path that actually orphans TCC grants.

    `_prepare_*_helper_signing` feeds the provisioning result straight into
    `invalidate_app_if_signing_mismatch`, which deletes the on-disk helper app when
    the identity no longer matches. Deleting a helper is what orphaned the grants in
    the 2026-07-05 incident. Under pytest, provisioning returns None, and invalidate
    treats None as "no usable identity right now" and keeps the app.
    """
    app_root = tmp_path / "EventKitHelper.app"
    app_root.mkdir()
    (app_root / "marker").write_text("real helper", encoding="utf-8")

    def _run(cmd: list[str], **_k: Any) -> _Completed:
        raise AssertionError(f"no signing subprocess may run under pytest: {cmd}")

    monkeypatch.setattr(_signing.subprocess, "run", _run)

    identity = _signing.provision_local_signing_identity()
    removed = _signing.invalidate_app_if_signing_mismatch(app_root, identity)

    assert identity is None
    assert removed is False
    assert (app_root / "marker").exists()

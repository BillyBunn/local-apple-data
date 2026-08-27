"""Shared local code-signing helpers for the EventKit and Photos helper apps.

macOS TCC (on macOS 14+, and strictly on macOS 26) only presents the
personal-information access prompt to a helper process that has BOTH a real
NSApplication/`@main` lifecycle AND a *stable* code-signing identity. An ad-hoc
signature (``codesign -s -``) produces no stable designated requirement, so
``tccd`` cannot attribute the request and never presents the prompt. It also
means an ad-hoc grant is bound to a churning cdhash and is lost on every
rebuild.

This module centralizes: resolving a stable signing identity (env override,
then a conventional local self-signed cert, else ``None``), building and
running the ``codesign`` command (stable identity + hardened runtime +
entitlements when a usable identity exists, else ad-hoc), and provisioning the
conventional self-signed identity in the user's login keychain when none is
otherwise available.

Everything degrades to ``None``/ad-hoc rather than raising or destroying a
working helper: a stable identity that turns out to be unusable at signing time
(locked keychain, missing/duplicate private key, an unrelated leftover cert)
falls back to an ad-hoc signature that keeps the helper runnable for
non-prompting reads. Access is simply not obtained until a usable stable
identity exists again.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..handles import STATE_DIR_ENV

SIGNING_IDENTITY_ENV = "LOCAL_APPLE_DATA_SIGNING_IDENTITY"
DEFAULT_LOCAL_SIGNING_IDENTITY = "Local Apple Data Signing"

# Passphrase for the transient PKCS#12 bundle used only to import the freshly
# generated key into the login keychain. It never protects anything durable:
# the key material lives in a 0700 TemporaryDirectory that is removed on exit.
_PROVISION_P12_PASSPHRASE = "localappledata"

_CERT_BLOCK_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    re.DOTALL,
)


def _subject_common_name(subject_output: str) -> str | None:
    """Extract the CN value from ``openssl x509 -noout -subject`` output.

    Handles both the modern ``subject=CN = Value`` and legacy
    ``subject= /CN=Value`` renderings. Returns the CN string or ``None``.
    """
    for separator in ("CN = ", "CN=", "CN ="):
        if separator in subject_output:
            tail = subject_output.split(separator, 1)[1]
            # Our self-signed cert carries only a CN; guard anyway by trimming a
            # trailing comma-separated RDN if one is present.
            return tail.split(",")[0].strip()
    return None


def _has_exact_cn_cert(security: str, name: str) -> bool:
    """Whether the keychain holds a certificate whose CN is *exactly* ``name``.

    ``security find-certificate -c`` matches by case-insensitive SUBSTRING, so it
    reports success for unrelated certs whose CN merely contains ``name`` (or
    vice versa). Retrieve every substring match as PEM and confirm an exact CN
    with ``openssl``. When ``openssl`` is unavailable the exact check cannot run;
    fall back to the coarse substring result — signing itself still falls back to
    ad-hoc if the resolved identity turns out to be unusable, so a coarse false
    positive here never bricks anything.
    """
    result = subprocess.run(
        [security, "find-certificate", "-a", "-c", name, "-p"],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return False
    openssl = shutil.which("openssl")
    if not openssl:
        return True
    for pem in _CERT_BLOCK_RE.findall(result.stdout):
        subject = subprocess.run(
            [openssl, "x509", "-noout", "-subject"],
            input=pem,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if subject.returncode == 0 and _subject_common_name(subject.stdout) == name:
            return True
    return False


def signing_identity() -> str | None:
    """Return a stable code-signing identity name if one is available.

    Precedence: an explicit ``LOCAL_APPLE_DATA_SIGNING_IDENTITY`` override, then
    the conventional local self-signed cert if a certificate with that *exact*
    common name is present in the keychain, else ``None`` (ad-hoc fallback).

    This is a best-effort *name resolver*, not a usability guarantee: a cert can
    be present but unusable by ``codesign`` (locked keychain, missing private
    key, duplicate/ambiguous CN). Callers must therefore treat stable signing as
    best-effort and fall back to ad-hoc when it fails (see ``sign_helper_app``).
    """
    override = os.environ.get(SIGNING_IDENTITY_ENV, "").strip()
    if override:
        return override
    security = shutil.which("security")
    if not security:
        return None
    # `find-identity -p codesigning` hides untrusted self-signed certs, so probe
    # for the conventional cert by exact common name instead.
    if _has_exact_cn_cert(security, DEFAULT_LOCAL_SIGNING_IDENTITY):
        return DEFAULT_LOCAL_SIGNING_IDENTITY
    return None


def codesign_command(
    codesign: str,
    entitlements_file: Path,
    staged_app: Path,
    identity: str | None,
) -> list[str]:
    """Build the ``codesign`` argv for the staged helper app.

    A non-empty ``identity`` produces a stable, hardened-runtime, entitled
    signature so TCC presents its prompt; ``identity`` of ``None`` (or empty)
    produces an ad-hoc signature that keeps the helper runnable for
    non-prompting reads.
    """
    if identity:
        return [
            codesign,
            "-s",
            identity,
            "-f",
            "--options",
            "runtime",
            "--entitlements",
            str(entitlements_file),
            str(staged_app),
        ]
    return [
        codesign,
        "-s",
        "-",
        "-f",
        "--deep",
        "--entitlements",
        str(entitlements_file),
        str(staged_app),
    ]


def sign_helper_app(
    codesign: str,
    entitlements_file: Path,
    staged_app: Path,
) -> subprocess.CompletedProcess[str]:
    """Sign ``staged_app`` with the resolved stable identity, ad-hoc on failure.

    Resolves the stable identity and attempts a stable signature. If that
    attempt fails (the identity is present in the keychain but ``codesign``
    cannot use it — locked keychain, missing/duplicate private key, an unrelated
    leftover cert), retries with an ad-hoc signature so the helper still builds.
    Access will not be obtained until a usable stable identity exists, but reads
    keep working and the whole access path is never bricked by an unusable cert.

    Returns the ``CompletedProcess`` of the accepted run (the stable run if it
    succeeded, otherwise the ad-hoc fallback run).
    """
    identity = signing_identity()
    result = subprocess.run(
        codesign_command(codesign, entitlements_file, staged_app, identity),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 0 or not identity:
        return result
    return subprocess.run(
        codesign_command(codesign, entitlements_file, staged_app, None),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def _login_keychain_path() -> Path:
    return Path.home() / "Library" / "Keychains" / "login.keychain-db"


def provisioning_allowed() -> bool:
    """Whether identity provisioning may run. False under pytest.

    ``provision_local_signing_identity`` is the only code in this project that
    mutates a keychain: it generates a private key and runs
    ``security import -k <login keychain>``. Keychain mutations are not reversible by
    this code and can orphan existing TCC grants, because a helper app's designated
    requirement pins to the signing certificate's leaf hash -- losing or duplicating
    that certificate invalidates grants the user already gave.

    What this prevents is a test that forgets to mock ``subprocess`` and silently
    imports a second identity into the real login keychain, leaving a duplicate
    common name that makes ``codesign -s`` by name ambiguous. Every test in
    ``tests/test_signing.py`` mocks ``subprocess`` today, so this changes no current
    behaviour -- it makes that a property of the code rather than of every future
    test author remembering.

    It does not, and cannot, defend against a shell command run outside this module;
    that is a review-process control, documented in the contributor guide.

    Tests that deliberately exercise provisioning monkeypatch this function to return
    ``True``. That is intentionally an explicit, greppable act: opting in is how a
    test says "I know this is the keychain-mutating path and I have mocked it."
    """

    return not os.environ.get("PYTEST_CURRENT_TEST")


def _provision_lock_path() -> Path:
    # Honors LOCAL_APPLE_DATA_STATE_DIR so the lock follows the same private-state
    # root as the handle secret and the event log. This is the only path in this
    # module that is actually created on disk during provisioning -- the keychain
    # itself is written by `security`, not by us -- so it is the one that leaks into
    # the operator's real home when something calls provisioning without mocking.
    configured = os.environ.get(STATE_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser() / ".signing-provision.lock"
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "local-apple-data"
        / ".signing-provision.lock"
    )


@contextlib.contextmanager
def _provision_lock():
    """Exclusive filesystem lock serializing identity provisioning.

    Two concurrent request-access calls (e.g. ``calendar`` + ``photos``) must not
    both generate a key and ``security import`` the same CN, which would leave
    duplicate ``Local Apple Data Signing`` identities and make ``codesign -s`` by
    name ambiguous. Best-effort: if the lock cannot be created, provisioning
    still proceeds (the race window is narrow and the documented setup is
    sequential).
    """
    lock_path = _provision_lock_path()
    fd: int | None = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        if fd is not None:
            os.close(fd)
            fd = None
    try:
        yield
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def provision_local_signing_identity() -> str | None:
    """Ensure a stable local self-signed code-signing identity exists.

    If a stable identity is already resolvable (env override or the conventional
    cert already in the keychain), returns it unchanged and does nothing. When
    none is resolvable and both ``openssl`` and ``security`` are available,
    generates a self-signed code-signing cert named
    ``DEFAULT_LOCAL_SIGNING_IDENTITY`` in the LOGIN keychain and returns its
    name. On any failure (or when tooling is absent) returns ``None`` and never
    raises into the caller.

    Idempotent and serialized: an existing cert short-circuits before any
    generation, and a filesystem lock plus a re-check under the lock prevents
    concurrent callers from creating duplicate same-CN identities. Key material
    is created inside a 0700 ``TemporaryDirectory`` and is never left on disk.

    The key is imported with ``-T /usr/bin/codesign`` only (no ``-A``), so its
    keychain ACL is scoped to ``codesign`` rather than granting silent access to
    every application. The first ``codesign`` use therefore triggers a one-time
    keychain "Always Allow" prompt unless the user pre-authorizes it; this is
    documented as one-time setup.
    """
    if not provisioning_allowed():
        return None

    existing = signing_identity()
    if existing:
        return existing

    openssl = shutil.which("openssl")
    security = shutil.which("security")
    if not openssl or not security:
        return None

    login_keychain = _login_keychain_path()
    try:
        with _provision_lock():
            # Re-check under the lock: a concurrent caller may have just imported
            # the cert while we waited to acquire it.
            existing = signing_identity()
            if existing:
                return existing

            with tempfile.TemporaryDirectory(
                prefix="local-apple-data-signing-"
            ) as directory:
                os.chmod(directory, 0o700)
                work = Path(directory)
                key_pem = work / "key.pem"
                cert_pem = work / "cert.pem"
                identity_p12 = work / "identity.p12"

                generate = subprocess.run(
                    [
                        openssl,
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:2048",
                        "-keyout",
                        str(key_pem),
                        "-out",
                        str(cert_pem),
                        "-days",
                        "3650",
                        "-nodes",
                        "-subj",
                        f"/CN={DEFAULT_LOCAL_SIGNING_IDENTITY}",
                        "-addext",
                        "keyUsage=critical,digitalSignature",
                        "-addext",
                        "extendedKeyUsage=critical,codeSigning",
                        "-addext",
                        "basicConstraints=critical,CA:false",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if generate.returncode != 0:
                    return None

                # `-legacy` is REQUIRED: macOS `security` cannot verify the MAC of
                # an OpenSSL 3.x default PKCS#12 bundle.
                bundle = subprocess.run(
                    [
                        openssl,
                        "pkcs12",
                        "-export",
                        "-legacy",
                        "-inkey",
                        str(key_pem),
                        "-in",
                        str(cert_pem),
                        "-out",
                        str(identity_p12),
                        "-passout",
                        f"pass:{_PROVISION_P12_PASSPHRASE}",
                        "-name",
                        DEFAULT_LOCAL_SIGNING_IDENTITY,
                    ],
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if bundle.returncode != 0:
                    return None

                imported = subprocess.run(
                    [
                        security,
                        "import",
                        str(identity_p12),
                        "-k",
                        str(login_keychain),
                        "-P",
                        _PROVISION_P12_PASSPHRASE,
                        "-T",
                        "/usr/bin/codesign",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if imported.returncode != 0:
                    return None
    except (OSError, subprocess.SubprocessError):
        return None

    # Confirm the cert is now resolvable before claiming success.
    return signing_identity()


def app_signing_authority(app_root: Path) -> str | None:
    """Return the leaf signing authority of the on-disk app.

    A named authority (e.g. ``"Local Apple Data Signing"``) is returned as-is;
    an ad-hoc signature returns the empty string ``""``; an indeterminate state
    (missing app or ``codesign``, unsigned, or unreadable output) returns
    ``None``. Never raises.
    """
    if not app_root.exists():
        return None
    codesign = shutil.which("codesign")
    if not codesign:
        return None
    info = subprocess.run(
        [codesign, "-dvv", str(app_root)],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if info.returncode != 0:
        return None
    # codesign writes the display to stderr.
    output = (info.stderr or "") + (info.stdout or "")
    if "Signature=adhoc" in output:
        return ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Authority="):
            # The first Authority= line is the leaf certificate.
            return stripped[len("Authority=") :].strip()
    return None


def app_signed_ad_hoc(app_root: Path) -> bool | None:
    """Return whether the on-disk app is ad-hoc signed.

    ``True`` = ad-hoc (no stable authority), ``False`` = signed with a named
    authority, ``None`` = signing state could not be determined. Thin wrapper
    over :func:`app_signing_authority`.
    """
    authority = app_signing_authority(app_root)
    if authority is None:
        return None
    return authority == ""


def invalidate_app_if_signing_mismatch(app_root: Path, identity: str | None) -> bool:
    """Remove the on-disk app only when rebuilding would improve its signing.

    Called from the request-access paths after provisioning so the next
    ``_ensure_*_helper_app`` rebuilds and re-signs with the resolved identity.
    Returns ``True`` when the app was removed (forcing a rebuild).

    Conservative and non-destructive:

    * ``identity is None`` (no usable stable identity right now — e.g. a locked
      keychain, or provisioning unavailable): do NOTHING. Removing the app could
      only force a downgrade to an ad-hoc rebuild, which would orphan an existing
      TCC grant bound to the current signature. A working helper is left intact.
    * on-disk signature already matches ``identity`` (same named authority): keep
      it.
    * on-disk is ad-hoc, or signed by a *different* named authority than
      ``identity`` (e.g. the operator switched to an ``Apple Development``
      identity via the env override): remove it so the rebuild re-signs with the
      requested identity.
    * indeterminate on-disk state: leave it untouched.

    Never raises.
    """
    if identity is None:
        return False
    authority = app_signing_authority(app_root)
    if authority is None:
        return False
    if authority == identity:
        return False
    try:
        if app_root.is_symlink() or app_root.is_file():
            app_root.unlink()
        elif app_root.is_dir():
            shutil.rmtree(app_root, ignore_errors=True)
    except OSError:
        return False
    return True

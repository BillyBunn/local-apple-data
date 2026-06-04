from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path


DEFAULT_STATE_DIR = Path.home() / ".local/state/local-apple-data"
SECRET_ENV = "LOCAL_APPLE_DATA_HANDLE_SECRET"
STATE_DIR_ENV = "LOCAL_APPLE_DATA_STATE_DIR"
SECRET_FILENAME = "handle-secret.key"


def _state_dir() -> Path:
    configured = os.environ.get(STATE_DIR_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_STATE_DIR


def _secret_path() -> Path:
    return _state_dir() / SECRET_FILENAME


def _secret_bytes() -> bytes:
    configured = os.environ.get(SECRET_ENV)
    if configured:
        return configured.encode("utf-8")

    path = _secret_path()
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        secret = secrets.token_hex(32)
        path.write_text(secret + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    if len(secret) < 32:
        secret = secrets.token_hex(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secret + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return secret.encode("utf-8")


def _digest(label: str, payload: str) -> bytes:
    return hmac.new(
        _secret_bytes(),
        f"{label}\0{payload}".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _is_lower_hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)


def _parse_handle_token(handle: str, prefix: str, version: str, length: int) -> str | None:
    marker = f"{prefix}:{version}:"
    if not handle.startswith(marker):
        return None
    token = handle.removeprefix(marker)
    if len(token) != length or not _is_lower_hex(token):
        return None
    return token


def _int_handle_token(prefix: str, item_id: int) -> str:
    return _digest(f"int:{prefix}", str(item_id)).hex()[:32]


def make_int_handle(prefix: str, item_id: int) -> str:
    return f"{prefix}:v2:{_int_handle_token(prefix, item_id)}"


def is_int_handle(handle: str, prefix: str) -> bool:
    return _parse_handle_token(handle, prefix, "v2", 32) is not None


def int_handle_matches(handle: str, prefix: str, item_id: int) -> bool:
    token = _parse_handle_token(handle, prefix, "v2", 32)
    if token is None:
        return False
    return hmac.compare_digest(token, _int_handle_token(prefix, item_id))


def make_opaque_handle(prefix: str, *parts: object) -> str:
    payload = "\0".join(str(part) for part in parts)
    token = _digest(f"opaque:{prefix}", payload).hex()[:32]
    return f"{prefix}:v1:{token}"


def is_opaque_handle(handle: str, prefix: str) -> bool:
    return _parse_handle_token(handle, prefix, "v1", 32) is not None


def opaque_handle_matches(handle: str, prefix: str, *parts: object) -> bool:
    token = _parse_handle_token(handle, prefix, "v1", 32)
    if token is None:
        return False
    expected = make_opaque_handle(prefix, *parts).rsplit(":", 1)[-1]
    return hmac.compare_digest(token, expected)

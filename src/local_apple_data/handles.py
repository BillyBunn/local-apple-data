from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from collections.abc import Iterable
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


def _digest_with_secret(secret: bytes, label: str, payload: str) -> bytes:
    return hmac.new(
        secret,
        f"{label}\0{payload}".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _digest(label: str, payload: str) -> bytes:
    return _digest_with_secret(_secret_bytes(), label, payload)


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


def resolve_int_handles(
    handles: Iterable[str],
    prefix: str,
    item_ids: Iterable[int],
) -> dict[str, int]:
    """Resolve several opaque integer handles with one current-secret read.

    The caller still supplies the bounded live item-id candidate set. Invalid or
    unmatched handles are omitted, and no token or secret material is returned.
    """

    token_to_handle: dict[str, str] = {}
    for handle in handles:
        token = _parse_handle_token(handle, prefix, "v2", 32)
        if token is not None:
            token_to_handle[token] = handle
    if not token_to_handle:
        return {}

    secret = _secret_bytes()
    label = f"int:{prefix}"
    resolved: dict[str, int] = {}
    for item_id_value in item_ids:
        item_id = int(item_id_value)
        token = _digest_with_secret(secret, label, str(item_id)).hex()[:32]
        handle = token_to_handle.get(token)
        if handle is None:
            continue
        resolved[handle] = item_id
        if len(resolved) == len(token_to_handle):
            break
    return resolved


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

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping, MutableMapping
from pathlib import Path


OPERATOR_ENV_PATH_ENV = "LOCAL_APPLE_DATA_OPERATOR_ENV_FILE"
DEFAULT_OPERATOR_ENV_RELATIVE = Path(
    "Library/Application Support/local-apple-data/.env.operator"
)
ALLOWED_OPERATOR_ENV_KEYS = frozenset(
    {
        "LOCAL_APPLE_DATA_EVENTKIT_HELPER_BUNDLE_ID",
        "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID",
    }
)
_ASSIGNMENT_RE = re.compile(
    r"^(?:export[ \t]+)?(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>[A-Za-z0-9._-]+)$"
)


class OperatorEnvError(ValueError):
    """Machine-local operator environment is unsafe or malformed."""


def operator_env_path(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> tuple[Path, bool]:
    environ = os.environ if environ is None else environ
    if OPERATOR_ENV_PATH_ENV in environ:
        raw_explicit = str(environ.get(OPERATOR_ENV_PATH_ENV) or "")
        explicit = raw_explicit.strip()
        if raw_explicit != explicit or not explicit:
            raise OperatorEnvError(
                "operator environment override must be a non-empty absolute path"
            )
        path = Path(explicit)
        if not path.is_absolute():
            raise OperatorEnvError("operator environment override must be absolute")
        return path, True
    return (home or Path.home()) / DEFAULT_OPERATOR_ENV_RELATIVE, False


def load_operator_env(
    environ: MutableMapping[str, str] | None = None,
    *,
    home: Path | None = None,
    local_env_path: Path | None = None,
) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    path, explicit = operator_env_path(environ, home=home)
    parsed = _read_operator_env_file(path, required=explicit)
    if local_env_path is not None:
        parsed.update(_read_operator_env_file(local_env_path, required=False))

    for key in ALLOWED_OPERATOR_ENV_KEYS:
        raw_existing = str(environ.get(key) or "")
        existing = raw_existing.strip()
        if raw_existing != existing or (
            existing and re.fullmatch(r"[A-Za-z0-9._-]+", existing) is None
        ):
            raise OperatorEnvError("an existing helper bundle ID is invalid")
        if not existing and key in parsed:
            environ[key] = parsed[key]
    return parsed


def _read_operator_env_file(path: Path, *, required: bool) -> dict[str, str]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError as exc:
        if required:
            raise OperatorEnvError(
                "configured operator environment file is missing"
            ) from exc
        return {}
    except OSError as exc:
        raise OperatorEnvError("operator environment file is unreadable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OperatorEnvError("operator environment path must be a regular file")
        if metadata.st_uid != os.getuid():
            raise OperatorEnvError("operator environment file must be owned by this user")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise OperatorEnvError(
                "operator environment file must not be group/world accessible"
            )
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            lines = handle.read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise OperatorEnvError("operator environment file is unreadable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT_RE.fullmatch(line)
        if match is None:
            raise OperatorEnvError(
                f"operator environment line {line_number} is not an assignment"
            )
        key = match.group("key")
        if key not in ALLOWED_OPERATOR_ENV_KEYS:
            raise OperatorEnvError(
                f"operator environment line {line_number} uses a disallowed key"
            )
        if key in parsed:
            raise OperatorEnvError(
                f"operator environment line {line_number} duplicates a key"
            )
        parsed[key] = match.group("value")

    return parsed

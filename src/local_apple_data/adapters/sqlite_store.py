from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import quote


class StoreUnavailableError(RuntimeError):
    """Raised when a local SQLite store cannot be opened or queried safely."""


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open a SQLite database in read-only query-only mode."""

    try:
        uri = f"file:{quote(str(path.expanduser().resolve()), safe='/')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=1000")
        connection.execute("PRAGMA trusted_schema=OFF")
    except sqlite3.Error as exc:
        raise StoreUnavailableError("Unable to open SQLite store.") from exc
    return connection


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def schema_fingerprint(connection: sqlite3.Connection, tables: list[str]) -> str:
    parts: list[str] = []
    for table in sorted(tables):
        columns = sorted(table_columns(connection, table))
        parts.append(f"{table}:{','.join(columns)}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def require_columns(
    connection: sqlite3.Connection,
    table: str,
    required: set[str],
) -> None:
    present = table_columns(connection, table)
    missing = sorted(required - present)
    if missing:
        raise StoreUnavailableError(
            f"SQLite table {table} missing required columns: {', '.join(missing)}"
        )


def like_contains_pattern(query: str) -> str:
    escaped = (
        query.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def has_minimum_query_quality(query: str, *, min_alnum: int = 2) -> bool:
    return sum(1 for character in query if character.isalnum()) >= min_alnum

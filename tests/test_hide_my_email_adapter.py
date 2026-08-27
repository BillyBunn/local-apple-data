from __future__ import annotations

import sqlite3
from pathlib import Path

import local_apple_data.adapters.hide_my_email as hide_my_email_adapter
from local_apple_data.adapters.hide_my_email import (
    get_hide_my_email_alias,
    search_hide_my_email_aliases,
)


ICLOUD_ALIAS = "alpha_mask_42" + "@" + "icloud.com"
PRIVATE_RELAY_ALIAS = "relay-token" + "@" + "privaterelay.appleid.com"
NORMAL_ICLOUD = "plainuser" + "@" + "icloud.com"


def _make_mail_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE addresses (
                ROWID INTEGER PRIMARY KEY,
                address TEXT,
                comment TEXT
            );
            CREATE TABLE messages (
                ROWID INTEGER PRIMARY KEY,
                sender INTEGER,
                date_received INTEGER,
                date_sent INTEGER,
                deleted INTEGER
            );
            CREATE TABLE recipients (
                ROWID INTEGER PRIMARY KEY,
                message INTEGER,
                address INTEGER,
                type INTEGER
            );
            """
        )
        connection.executemany(
            "INSERT INTO addresses (ROWID, address, comment) VALUES (?, ?, ?)",
            [
                (1, ICLOUD_ALIAS, ""),
                (2, PRIVATE_RELAY_ALIAS, ""),
                (3, NORMAL_ICLOUD, ""),
            ],
        )
        connection.executemany(
            """
            INSERT INTO messages (ROWID, sender, date_received, date_sent, deleted)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (10, 3, 1000, 900, 0),
                (11, 1, 1001, 901, 0),
                (12, 3, 1002, 902, 0),
                (13, 2, 1003, 903, 0),
            ],
        )
        connection.executemany(
            "INSERT INTO recipients (ROWID, message, address, type) VALUES (?, ?, ?, ?)",
            [
                (100, 10, 1, 0),
                (101, 12, 1, 0),
                (102, 13, 2, 0),
            ],
        )


def test_search_hide_my_email_aliases_returns_masked_inference_only(tmp_path: Path) -> None:
    db_path = tmp_path / "Envelope Index"
    _make_mail_db(db_path)

    result = search_hide_my_email_aliases("alpha_mask", db_path=db_path)

    assert result["status"] == "ok"
    assert result["source"] == "hide_my_email"
    assert result["authoritative_inventory"] is False
    assert result["result_count"] == 1
    alias = result["results"][0]
    assert alias["handle"].startswith("hide_my_email:alias:v1:")
    assert alias["alias_preview"] == "al***@icloud.com"
    assert alias["domain"] == "icloud.com"
    assert alias["inference_kind"] == "possible_hide_my_email_icloud_alias"
    assert alias["confidence"] == "medium"
    assert alias["sender_count"] == 1
    assert alias["recipient_count"] == 2
    assert alias["message_count"] == 3
    assert alias["last_seen_date"] == 1002
    assert alias["provenance"] == "local_mail_address_metadata"
    assert ICLOUD_ALIAS not in str(result)
    assert NORMAL_ICLOUD not in str(result)


def test_search_hide_my_email_aliases_rejects_broad_domain_without_db(tmp_path: Path) -> None:
    result = search_hide_my_email_aliases("icloud.com", db_path=tmp_path / "missing.db")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_search_hide_my_email_aliases_detects_private_relay(tmp_path: Path) -> None:
    db_path = tmp_path / "Envelope Index"
    _make_mail_db(db_path)

    result = search_hide_my_email_aliases("relay-token", db_path=db_path)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    alias = result["results"][0]
    assert alias["alias_preview"] == "re***@privaterelay.appleid.com"
    assert alias["domain"] == "privaterelay.appleid.com"
    assert alias["inference_kind"] == "sign_in_with_apple_private_relay"
    assert alias["confidence"] == "high"
    assert PRIVATE_RELAY_ALIAS not in str(result)


def test_get_hide_my_email_alias_returns_exact_selected_alias(tmp_path: Path) -> None:
    db_path = tmp_path / "Envelope Index"
    _make_mail_db(db_path)
    search = search_hide_my_email_aliases("alpha_mask", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_hide_my_email_alias(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["authoritative_inventory"] is False
    assert result["privacy"]["alias_returned"] is True
    assert result["result"]["alias"] == ICLOUD_ALIAS
    assert result["result"]["alias_preview"] == "al***@icloud.com"
    assert result["result"]["authoritative_inventory"] is False


def test_get_hide_my_email_alias_rejects_invalid_handle() -> None:
    result = get_hide_my_email_alias("hide-my-email:1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_hide_my_email_aliases_degrades_without_store(tmp_path: Path) -> None:
    result = search_hide_my_email_aliases("alpha_mask", db_path=tmp_path / "missing.db")

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "mail_store_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_hide_my_email_store_warning_uses_generic_message(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "Envelope Index"
    _make_mail_db(db_path)

    def fail_schema(_connection):
        raise hide_my_email_adapter.StoreUnavailableError(
            "mail failed at /private/local/Envelope Index"
        )

    monkeypatch.setattr(hide_my_email_adapter, "_check_schema", fail_schema)

    result = search_hide_my_email_aliases("alpha_mask", db_path=db_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "mail_store_unavailable",
            "message": "Mail local store is unavailable or unreadable.",
        }
    ]

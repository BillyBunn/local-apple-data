from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

import local_apple_data.adapters.messages as messages_adapter
from local_apple_data.adapters.messages import (
    _messages_send_file_script,
    apply_messages_change,
    export_message_attachment,
    get_message_chat,
    get_message_participant,
    list_message_attachments,
    list_message_participants,
    plan_messages_change,
    search_message_chats,
)

ATTRIBUTED_BODY_B64 = (
    "BAtzdHJlYW10eXBlZIHoA4QBQISEhBlOU011dGFibGVBdHRyaWJ1dGVkU3RyaW5nAISEEk5T"
    "QXR0cmlidXRlZFN0cmluZwCEhAhOU09iamVjdACFkoSEhA9OU011dGFibGVTdHJpbmcBhIQI"
    "TlNTdHJpbmcBlYQBKxdBdHRyaWJ1dGVkIHJ1bnRpbWUgdGV4dIaEAmlJAReShISEDE5TRGlj"
    "dGlvbmFyeQCVhAFpAIaG"
)
MALFORMED_ATTRIBUTED_BODY_HEX = (
    "040B73747265616D747970656481E803840141848484194E534D757461626C6541747472"
    "696275746564537472696E67008484124E5341747472696275746564537472696E670084"
    "84084E534F626A6563740085928484840F4E534D757461626C65537472696E6701848408"
    "4E53537472696E67019584012B17417474726962757465642072756E74696D6520746578"
    "7486840269490117928484840C4E5344696374696F6E6172790095840169008686"
)


def _make_messages_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE chat (
                ROWID INTEGER PRIMARY KEY,
                guid TEXT,
                display_name TEXT,
                service_name TEXT
            );
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT,
                date INTEGER,
                is_from_me INTEGER,
                handle_id INTEGER,
                service TEXT,
                attributedBody BLOB
            );
            CREATE TABLE chat_message_join (
                chat_id INTEGER,
                message_id INTEGER
            );
            CREATE TABLE chat_handle_join (
                chat_id INTEGER,
                handle_id INTEGER
            );
            CREATE TABLE handle (
                ROWID INTEGER PRIMARY KEY,
                id TEXT,
                service TEXT
            );
            INSERT INTO chat VALUES
              (1, 'chat-guid-1', 'Synthetic Planning Chat', 'iMessage');
            INSERT INTO handle VALUES
              (7, '+15550100', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1, 7);
            INSERT INTO message VALUES
              (10, 'First synthetic message', 802310400, 0, 7, 'iMessage', NULL),
              (11, 'Second synthetic reply', 802310500, 1, 0, 'iMessage', NULL);
            INSERT INTO chat_message_join VALUES
              (1, 10),
              (1, 11);
            """
        )


def _add_second_messages_chat(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            INSERT INTO chat VALUES
              (2, 'chat-guid-2', 'Synthetic Other Chat', 'iMessage');
            INSERT INTO handle VALUES
              (8, '+15550200', 'iMessage');
            INSERT INTO chat_handle_join VALUES (2, 8);
            INSERT INTO message VALUES
              (20, 'Other synthetic message', 802310800, 0, 8, 'iMessage', NULL);
            INSERT INTO chat_message_join VALUES (2, 20);
            """
        )


def _assert_no_participant_list_identifier_leak(payload: dict) -> None:
    text = str(payload)
    for forbidden in (
        "+15550100",
        "15550100",
        "5550100",
        "+1555",
        "****0100",
        "••••0100",
        "chat-guid-1",
    ):
        assert forbidden not in text
    for item in payload.get("results", []):
        assert all(not key.endswith("_preview") for key in item)
        assert all("identifier" not in key for key in item)
        assert all("phone" not in key for key in item)
        assert all("email" not in key for key in item)


def _add_messages_attachment_schema(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE attachment (
                ROWID INTEGER PRIMARY KEY,
                guid TEXT,
                created_date INTEGER,
                start_date INTEGER,
                filename TEXT,
                uti TEXT,
                mime_type TEXT,
                transfer_state INTEGER,
                is_outgoing INTEGER,
                user_info BLOB,
                transfer_name TEXT,
                total_bytes INTEGER,
                is_sticker INTEGER
            );
            CREATE TABLE message_attachment_join (
                message_id INTEGER,
                attachment_id INTEGER
            );
            INSERT INTO attachment VALUES
              (20, 'attachment-guid-1', 802310300, 802310350,
               'Attachments/aa/bb/source-packet.pdf', 'com.adobe.pdf',
               'application/pdf', 0, 0, NULL, 'packet.pdf', 11, 0);
            INSERT INTO message_attachment_join VALUES (10, 20);
            """
        )


def _attachment_store(tmp_path: Path) -> tuple[Path, Path, str]:
    db_path = tmp_path / "chat.db"
    messages_root = tmp_path / "Messages"
    _make_messages_db(db_path)
    _add_messages_attachment_schema(db_path)
    attachment_path = messages_root / "Attachments/aa/bb/source-packet.pdf"
    attachment_path.parent.mkdir(parents=True)
    attachment_path.write_bytes(b"PDF PAYLOAD")
    search = search_message_chats("Planning", db_path=db_path)
    return db_path, messages_root, search["results"][0]["handle"]


def test_search_message_chats_returns_metadata_only(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)

    result = search_message_chats("Planning", db_path=db_path)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "chat_display_name"
    assert result["result_count"] == 1
    chat = result["results"][0]
    assert chat["handle"].startswith("messages:chat:v1:")
    assert chat["display_name"] == "Synthetic Planning Chat"
    assert chat["participants_count"] == 1
    assert "+15550100" not in str(result)
    assert "First synthetic message" not in str(result)
    assert "chat-guid-1" not in str(result)


def test_search_message_chats_rejects_broad_query_without_db(tmp_path: Path) -> None:
    result = search_message_chats("%", db_path=tmp_path / "missing.db")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"


def test_get_message_chat_returns_exact_bounded_transcript(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    search = search_message_chats("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_message_chat(handle, db_path=db_path, max_messages=10, max_chars=25)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is True
    assert result["result"]["messages_returned"] == 2
    assert result["result"]["messages"][0]["direction"] == "received"
    assert result["result"]["messages"][0]["text"] == "First synthetic message"
    assert result["result"]["messages"][1]["text"] == "Se"
    assert result["result"]["transcript_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"
    assert "+15550100" not in str(result)
    assert "chat-guid-1" not in str(result)


def test_list_message_participants_returns_opaque_handles_without_identifiers(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    chat = search_message_chats("Planning", db_path=db_path)["results"][0]

    result = list_message_participants(chat["handle"], db_path=db_path)

    assert result["status"] == "ok"
    assert result["privacy"]["participant_id_returned"] is False
    assert result["query"]["scope"] == "chat_participants"
    assert result["result_count"] == 1
    participant = result["results"][0]
    assert participant["handle"].startswith("messages:participant:v1:")
    assert "id_preview" not in participant
    assert "participant_id" not in participant
    assert participant["service"] == "iMessage"
    assert participant["participant_id_returned"] is False
    _assert_no_participant_list_identifier_leak(result)


def test_get_message_participant_returns_exact_detail(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    chat = search_message_chats("Planning", db_path=db_path)["results"][0]
    participant = list_message_participants(chat["handle"], db_path=db_path)["results"][0]

    result = get_message_participant(
        chat["handle"],
        participant["handle"],
        db_path=db_path,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["participant_id_returned"] is True
    assert result["result"]["handle"] == participant["handle"]
    assert result["result"]["participant_id"] == "+15550100"
    assert result["result"]["participant_id_returned"] is True
    assert result["result"]["service"] == "iMessage"


def test_message_participants_reject_invalid_handles(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    chat = search_message_chats("Planning", db_path=db_path)["results"][0]

    list_result = list_message_participants("messages:chat:v1:12345", db_path=db_path)
    get_result = get_message_participant(
        chat["handle"],
        "messages:participant:v1:12345",
        db_path=db_path,
    )

    assert list_result["status"] == "error"
    assert list_result["warnings"][0]["code"] == "invalid_handle"
    assert get_result["status"] == "error"
    assert get_result["warnings"][0]["code"] == "invalid_handle"


def test_message_participant_detail_refuses_cross_chat_handle_binding(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    _add_second_messages_chat(db_path)
    planning_chat = search_message_chats("Planning", db_path=db_path)["results"][0]
    other_chat = search_message_chats("Other", db_path=db_path)["results"][0]
    participant = list_message_participants(planning_chat["handle"], db_path=db_path)[
        "results"
    ][0]

    result = get_message_participant(
        other_chat["handle"],
        participant["handle"],
        db_path=db_path,
    )

    assert result["status"] == "not_found"
    assert result["privacy"]["participant_id_returned"] is False
    assert result["result"] is None
    assert "+15550100" not in str(result)
    assert "+15550200" not in str(result)
    assert "participant_id" not in str(result.get("result"))


def test_messages_send_plan_and_apply_reject_participant_handles(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    chat = search_message_chats("Planning", db_path=db_path)["results"][0]
    participant = list_message_participants(chat["handle"], db_path=db_path)["results"][0]

    plan = plan_messages_change(
        "send-text",
        handle=participant["handle"],
        body_text="Synthetic outbound message",
        db_path=db_path,
    )

    def runner(_script: str, _timeout: float) -> str:
        raise AssertionError("participant handle must not reach Messages automation")

    apply_result = apply_messages_change(
        "send-text",
        handle=participant["handle"],
        body_text="Synthetic outbound message",
        approval_token="messages-apply:v1:bad",
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
    )

    assert plan["status"] == "error"
    assert plan["mutation_applied"] is False
    assert plan["warnings"][0]["code"] == "invalid_handle"
    assert apply_result["status"] == "error"
    assert apply_result["mutation_applied"] is False
    assert apply_result["warnings"][0]["code"] == "invalid_handle"
    assert "+15550100" not in str(plan)
    assert "+15550100" not in str(apply_result)


def test_get_message_chat_uses_attributed_body_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    attributed_body = base64.b64decode(ATTRIBUTED_BODY_B64)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
            (12, None, 802310600, 0, 7, "iMessage", attributed_body),
        )
        connection.execute("INSERT INTO chat_message_join VALUES (?, ?)", (1, 12))
    search = search_message_chats("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_message_chat(handle, db_path=db_path, max_messages=10, max_chars=200)

    assert result["status"] == "ok"
    assert result["warnings"] == []
    assert result["result"]["messages_returned"] == 3
    message = result["result"]["messages"][2]
    assert message["text"] == "Attributed runtime text"
    assert message["text_source"] == "attributed_body"


def test_get_message_chat_preserves_valid_attributed_body_when_one_blob_fails(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    attributed_body = base64.b64decode(ATTRIBUTED_BODY_B64)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
            (12, None, 802310600, 0, 7, "iMessage", attributed_body),
        )
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                13,
                None,
                802310700,
                0,
                7,
                "iMessage",
                bytes.fromhex(MALFORMED_ATTRIBUTED_BODY_HEX),
            ),
        )
        connection.execute("INSERT INTO chat_message_join VALUES (?, ?)", (1, 12))
        connection.execute("INSERT INTO chat_message_join VALUES (?, ?)", (1, 13))
    search = search_message_chats("Planning", db_path=db_path)
    handle = search["results"][0]["handle"]

    result = get_message_chat(handle, db_path=db_path, max_messages=10, max_chars=200)

    assert result["status"] == "ok"
    assert result["warnings"][0]["code"] == "messages_attributed_body_unavailable"
    assert result["result"]["messages_returned"] == 3
    assert result["result"]["messages"][2]["text"] == "Attributed runtime text"
    assert result["result"]["messages"][2]["text_source"] == "attributed_body"


def test_get_message_chat_rejects_invalid_handle() -> None:
    result = get_message_chat("messages:chat:1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_message_chats_degrades_without_store(tmp_path: Path) -> None:
    result = search_message_chats("Planning", db_path=tmp_path / "missing.db")

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "messages_store_unavailable"
    assert str(tmp_path) not in result["warnings"][0]["message"]


def test_messages_store_warning_uses_generic_message(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)

    def fail_schema(_connection):
        raise messages_adapter.StoreUnavailableError(
            "messages failed at /private/local/chat.db"
        )

    monkeypatch.setattr(messages_adapter, "_check_schema", fail_schema)

    result = search_message_chats("Planning", db_path=db_path)

    assert result["status"] == "degraded"
    assert result["warnings"] == [
        {
            "code": "messages_store_unavailable",
            "message": "Messages local store is unavailable or unreadable.",
        }
    ]


def test_list_message_attachments_returns_exact_attachment_handles(tmp_path: Path) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)

    result = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["result_count"] == 1
    attachment = result["results"][0]
    assert attachment["handle"].startswith("messages:attachment:v1:")
    assert attachment["chat_handle"] == chat_handle
    assert attachment["filename"] == "packet.pdf"
    assert attachment["mime_type"] == "application/pdf"
    assert attachment["uti"] == "com.adobe.pdf"
    assert attachment["file_size"] == 11
    assert attachment["media_status"] == "available"
    assert attachment["attachment_type"] == "document"
    assert attachment["direction"] == "received"
    assert str(messages_root) not in str(result)
    assert "+15550100" not in str(result)
    assert "First synthetic message" not in str(result)
    assert "attachment-guid-1" not in str(result)


def test_export_message_attachment_writes_selected_file(tmp_path: Path) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)
    attachment_handle = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )["results"][0]["handle"]

    result = export_message_attachment(
        chat_handle,
        attachment_handle,
        output_dir=tmp_path / "exports",
        filename="../review packet.pdf",
        db_path=db_path,
        messages_root=messages_root,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["attachment_content_returned"] is False
    assert result["privacy"]["attachment_content_exported"] is True
    assert result["result"]["attachment_content_exported"] is True
    assert result["result"]["exported_filename"] == "review-packet.pdf"
    assert result["result"]["exported_bytes"] == 11
    assert Path(result["result"]["exported_path"]).read_bytes() == b"PDF PAYLOAD"
    assert str(messages_root) not in str(result)


def test_plan_messages_send_text_returns_approval_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]

    result = plan_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        db_path=db_path,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    preview = result["preview"]
    assert preview["operation"] == "send_text"
    assert preview["target"]["handle"] == handle
    assert preview["target"]["message_count"] == 2
    assert preview["proposed"]["body_chars"] == len("Synthetic outbound message")
    assert preview["proposed"]["attachments_permitted"] is False
    assert preview["approval"]["approval_token_format"].startswith("messages-apply:v1:")
    assert "chat-guid-1" not in str(result)
    assert "+15550100" not in str(result)


def test_plan_messages_send_file_returns_approval_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    source = tmp_path / "outbound-packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]

    result = plan_messages_change(
        "send-file",
        handle=handle,
        file_path=str(source),
        db_path=db_path,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    preview = result["preview"]
    assert preview["operation"] == "send_file"
    assert preview["target"]["handle"] == handle
    assert preview["proposed"]["kind"] == "messages_send_file"
    assert preview["proposed"]["filename"] == "outbound-packet.pdf"
    assert preview["proposed"]["file_size"] == len(b"PDF OUTBOUND")
    assert preview["proposed"]["attachment_type"] == "document"
    assert preview["proposed"]["file_content_returned"] is False
    assert preview["proposed"]["file_path_returned"] is False
    assert str(source) not in str(result)
    assert "chat-guid-1" not in str(result)
    assert "+15550100" not in str(result)


def test_plan_messages_send_file_rejects_missing_file_path(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]

    result = plan_messages_change("send-file", handle=handle, db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_file_path"


def test_apply_messages_send_text_requires_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    result = apply_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        approval_token=token,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_messages_send_text_writes_and_reads_back_with_mock_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, timeout: float) -> str:
        assert timeout > 0
        assert "send messageText to targetChat" in script
        assert "chat-guid-1" in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (12, "Synthetic outbound message", 802310600, 1, 0, "iMessage", None),
            )
            connection.execute("INSERT INTO chat_message_join VALUES (?, ?)", (1, 12))
        return ""

    result = apply_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
        read_back_timeout=0,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["chat_handle_confirmed"] is True
    assert result["read_back"]["body_chars"] == len("Synthetic outbound message")
    assert result["read_back"]["text_source"] == "text"
    assert "Synthetic outbound message" not in str(result["read_back"])
    assert "+15550100" not in str(result)


def test_apply_messages_send_file_writes_and_reads_back_with_mock_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    _add_messages_attachment_schema(db_path)
    source = tmp_path / "outbound-packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-file",
        handle=handle,
        file_path=str(source),
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(script: str, timeout: float) -> str:
        assert timeout > 0
        assert "send attachmentFile to targetChat" in script
        assert "send messageText" not in script
        assert "chat-guid-1" in script
        assert str(source) in script
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (12, "", 802310600, 1, 0, "iMessage", None),
            )
            connection.execute("INSERT INTO chat_message_join VALUES (?, ?)", (1, 12))
            connection.execute(
                "INSERT INTO attachment VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    21,
                    "attachment-guid-outbound",
                    802310600,
                    802310600,
                    "Attachments/cc/dd/outbound-packet.pdf",
                    "com.adobe.pdf",
                    "application/pdf",
                    0,
                    1,
                    None,
                    "outbound-packet.pdf",
                    len(b"PDF OUTBOUND"),
                    0,
                ),
            )
            connection.execute("INSERT INTO message_attachment_join VALUES (?, ?)", (12, 21))
        return ""

    result = apply_messages_change(
        "send-file",
        handle=handle,
        file_path=str(source),
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
        read_back_timeout=0,
    )

    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["approval"]["approval_token_verified"] is True
    assert result["read_back"]["chat_handle_confirmed"] is True
    assert result["read_back"]["attachment_filename"] == "outbound-packet.pdf"
    assert result["read_back"]["attachment_type"] == "document"
    assert result["read_back"]["file_size"] == len(b"PDF OUTBOUND")
    assert result["read_back"]["attachment_content_returned"] is False
    assert result["read_back"]["attachment_content_exported"] is False
    assert result["read_back"]["file_path_returned"] is False
    assert str(source) not in str(result["read_back"])
    assert "+15550100" not in str(result)


def test_apply_messages_send_file_rejects_stale_file_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    source = tmp_path / "outbound-packet.pdf"
    source.write_bytes(b"PDF OUTBOUND")
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-file",
        handle=handle,
        file_path=str(source),
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    source.write_bytes(b"UPDATED PDF OUTBOUND")

    result = apply_messages_change(
        "send-file",
        handle=handle,
        file_path=str(source),
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_messages_send_text_runner_os_errors_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(_script: str, _timeout: float) -> str:
        raise OSError("permission denied for /private/local/messages")

    result = apply_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
        read_back_timeout=0,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "write_error"
    assert "permission denied" not in str(result)
    assert "/private/local/messages" not in str(result)


def test_apply_messages_send_text_rejects_stale_chat_state(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
            (12, "New intervening message", 802310600, 0, 7, "iMessage", None),
        )
        connection.execute("INSERT INTO chat_message_join VALUES (?, ?)", (1, 12))

    result = apply_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
    )

    assert result["status"] == "error"
    assert result["mutation_applied"] is False
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_messages_send_text_detects_ghost_row(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    _make_messages_db(db_path)
    handle = search_message_chats("Planning", db_path=db_path)["results"][0]["handle"]
    plan = plan_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        db_path=db_path,
    )
    token = "messages-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]

    def runner(_script: str, _timeout: float) -> str:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (12, "", 802310600, 1, 0, "SMS", None),
            )
        return ""

    result = apply_messages_change(
        "send-text",
        handle=handle,
        body_text="Synthetic outbound message",
        approval_token=token,
        confirm_apply=True,
        db_path=db_path,
        script_runner=runner,
        read_back_timeout=0,
    )

    assert result["status"] == "partial"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "messages_send_ghost_row"


def test_send_file_script_uses_exact_chat_and_never_direct_recipient(tmp_path: Path) -> None:
    source = tmp_path / "packet.pdf"
    source.write_bytes(b"PDF")

    script = _messages_send_file_script(chat_guid="chat-guid-1", file_path=str(source))
    lowered = script.lower()

    assert "chat id chatIdentifier" in script
    assert "send attachmentFile to targetChat" in script
    assert "buddy" not in lowered
    assert "participant" not in lowered
    assert "phone" not in lowered
    assert "email" not in lowered
    assert "delete" not in lowered
    assert "remove" not in lowered


def test_message_attachment_export_rejects_bad_handles(tmp_path: Path) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)
    attachment_handle = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )["results"][0]["handle"]

    result = export_message_attachment(
        "messages:chat:1",
        attachment_handle,
        output_dir=tmp_path / "exports",
        db_path=db_path,
        messages_root=messages_root,
    )
    assert result["status"] == "error"
    assert result["privacy"]["attachment_content_exported"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"

    result = export_message_attachment(
        chat_handle,
        "messages:attachment:20",
        output_dir=tmp_path / "exports",
        db_path=db_path,
        messages_root=messages_root,
    )
    assert result["status"] == "error"
    assert result["privacy"]["attachment_content_exported"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_message_attachment_export_reports_unavailable_for_missing_file(
    tmp_path: Path,
) -> None:
    db_path, messages_root, chat_handle = _attachment_store(tmp_path)
    (messages_root / "Attachments/aa/bb/source-packet.pdf").unlink()
    attachment = list_message_attachments(
        chat_handle,
        db_path=db_path,
        messages_root=messages_root,
    )["results"][0]

    result = export_message_attachment(
        chat_handle,
        attachment["handle"],
        output_dir=tmp_path / "exports",
        db_path=db_path,
        messages_root=messages_root,
    )

    assert attachment["media_status"] == "unavailable"
    assert result["status"] == "attachment_unavailable"
    assert result["privacy"]["attachment_content_exported"] is False
    assert result["result"]["attachment_content_exported"] is False
    assert result["warnings"][0]["code"] == "messages_attachment_unavailable"
    assert not (tmp_path / "exports" / "packet.pdf").exists()

from __future__ import annotations

import json
from pathlib import Path

from local_apple_data.redacted_log import log_result


def test_log_result_excludes_query_and_result_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_APPLE_DATA_LOG_DIR", str(tmp_path))
    payload = {
        "schema_version": 1,
        "source": "mail",
        "status": "ok",
        "result_count": 1,
        "query": {"scope": "subject", "text": "do not log query"},
        "results": [{"subject": "do not log subject"}],
        "privacy": {
            "output_tier": "metadata",
            "content_inspected": False,
            "raw_rows_inspected": False,
            "credentials_inspected": False,
        },
        "warnings": [{"code": "sample_warning", "message": "do not log message"}],
    }

    log_result("mail.search", payload)

    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["command"] == "mail.search"
    assert event["warning_codes"] == ["sample_warning"]
    assert "do not log query" not in text
    assert "do not log subject" not in text
    assert "do not log message" not in text


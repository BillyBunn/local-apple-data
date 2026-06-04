from __future__ import annotations

import json
from pathlib import Path

from local_apple_data.cli import main


def test_cli_photos_search(monkeypatch, capsys) -> None:
    def fake_search(
        query: str,
        *,
        limit: int,
        media_type: str,
        max_scan_assets: int,
    ) -> dict:
        assert query == "IMG"
        assert limit == 8
        assert media_type == "image"
        assert max_scan_assets == 456
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": {"content_inspected": False, "output_tier": "metadata"},
            "results": [
                {
                    "handle": "photos:asset:v1:0123456789abcdef0123456789abcdef",
                    "primary_filename": "IMG_SYNTHETIC.JPG",
                }
            ],
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.search_photos", fake_search)

    exit_code = main(
        [
            "photos",
            "search",
            "--json",
            "--query",
            "IMG",
            "--limit",
            "8",
            "--media-type",
            "image",
            "--max-scan-assets",
            "456",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["source"] == "photos"
    assert parsed["result_count"] == 1
    assert parsed["results"][0]["handle"].startswith("photos:asset:v1:")


def test_cli_photos_get(monkeypatch, capsys) -> None:
    def fake_get(handle: str, *, max_scan_assets: int) -> dict:
        assert handle == "photos:asset:v1:0123456789abcdef0123456789abcdef"
        assert max_scan_assets == 654
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": {"content_inspected": False, "output_tier": "detail"},
            "result": {
                "handle": handle,
                "primary_filename": "IMG_SYNTHETIC.JPG",
                "resources": [{"filename": "IMG_SYNTHETIC.JPG"}],
                "asset_content_returned": False,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.get_photo_asset", fake_get)

    exit_code = main(
        [
            "photos",
            "get",
            "--json",
            "--handle",
            "photos:asset:v1:0123456789abcdef0123456789abcdef",
            "--max-scan-assets",
            "654",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["asset_content_returned"] is False


def test_cli_photos_export(monkeypatch, tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "exports"

    def fake_export(
        handle: str,
        *,
        output_dir: Path,
        filename: str | None,
        max_scan_assets: int,
    ) -> dict:
        assert handle == "photos:asset:v1:0123456789abcdef0123456789abcdef"
        assert output_dir == tmp_path / "exports"
        assert filename == "photo-export.jpg"
        assert max_scan_assets == 987
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": {"content_exported": True, "output_tier": "export"},
            "result": {
                "handle": handle,
                "asset_content_returned": False,
                "asset_content_exported": True,
                "exported_path": str(output_dir / "photo-export.jpg"),
                "exported_filename": "photo-export.jpg",
                "exported_bytes": 1234,
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.export_photo_asset", fake_export)

    exit_code = main(
        [
            "photos",
            "export",
            "--json",
            "--handle",
            "photos:asset:v1:0123456789abcdef0123456789abcdef",
            "--output-dir",
            str(output_dir),
            "--filename",
            "photo-export.jpg",
            "--max-scan-assets",
            "987",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["result"]["asset_content_exported"] is True


def test_cli_photos_plan(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "IMG_IMPORT.JPG"

    def fake_plan(operation: str, *, source_file: str, media_type: str) -> dict:
        assert operation == "import"
        assert source_file == str(source)
        assert media_type == "image"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": {"content_inspected": False, "output_tier": "preview"},
            "mode": "plan",
            "mutation_applied": False,
            "apply_available": True,
            "preview": {
                "approval": {"approval_fingerprint": "synthetic-fingerprint"},
                "proposed": {"source_filename": "IMG_IMPORT.JPG"},
            },
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.plan_photo_change", fake_plan)

    exit_code = main(
        [
            "photos",
            "plan",
            "--json",
            "--operation",
            "import",
            "--source-file",
            str(source),
            "--media-type",
            "image",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "plan"
    assert parsed["mutation_applied"] is False


def test_cli_photos_apply(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "IMG_IMPORT.JPG"

    def fake_apply(
        operation: str,
        *,
        source_file: str,
        media_type: str,
        approval_token: str,
        confirm_apply: bool,
    ) -> dict:
        assert operation == "import"
        assert source_file == str(source)
        assert media_type == "image"
        assert approval_token == "photos-apply:v1:synthetic-fingerprint"
        assert confirm_apply is True
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": {"content_inspected": False, "output_tier": "mutation"},
            "mode": "apply",
            "mutation_applied": True,
            "read_back": {"primary_filename": "IMG_IMPORT.JPG"},
            "result_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr("local_apple_data.cli.apply_photo_change", fake_apply)

    exit_code = main(
        [
            "photos",
            "apply",
            "--json",
            "--operation",
            "import",
            "--source-file",
            str(source),
            "--media-type",
            "image",
            "--approval-token",
            "photos-apply:v1:synthetic-fingerprint",
            "--confirm-apply",
        ]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ok"
    assert parsed["mode"] == "apply"
    assert parsed["mutation_applied"] is True

from __future__ import annotations

from pathlib import Path

from local_apple_data.adapters.photos import (
    apply_photo_change,
    export_photo_asset,
    get_photo_asset,
    plan_photo_change,
    search_photos,
)


def _photos_runner(payload: dict, _timeout: float) -> dict:
    if payload["command"] == "photos":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "assets": [
                {
                    "asset_id": "runtime-photo-1",
                    "media_type": "image",
                    "media_subtypes": 0,
                    "pixel_width": 4032,
                    "pixel_height": 3024,
                    "duration": 0.0,
                    "favorite": False,
                    "hidden": False,
                    "source_type": 1,
                    "creation_date": "2026-06-04T17:00:00.000Z",
                    "modification_date": "2026-06-04T18:00:00.000Z",
                    "primary_filename": "IMG_SYNTHETIC.JPG",
                    "resource_count": 1,
                    "asset_content_returned": False,
                    "resources": [
                        {
                            "filename": "IMG_SYNTHETIC.JPG",
                            "type": 1,
                            "uniform_type_identifier": "public.jpeg",
                        }
                    ],
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "photo_by_id":
        assert payload["asset_id"] == "runtime-photo-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "asset": {
                "asset_id": "runtime-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 4032,
                "pixel_height": 3024,
                "duration": 0.0,
                "favorite": False,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T17:00:00.000Z",
                "modification_date": "2026-06-04T18:00:00.000Z",
                "primary_filename": "IMG_SYNTHETIC.JPG",
                "resource_count": 1,
                "asset_content_returned": False,
                "resources": [
                    {
                        "filename": "IMG_SYNTHETIC.JPG",
                        "type": 1,
                        "uniform_type_identifier": "public.jpeg",
                    }
                ],
            },
            "warnings": [],
        }
    if payload["command"] == "export_photo_by_id":
        assert payload["asset_id"] == "runtime-photo-1"
        assert payload["output_dir"]
        assert payload["filename"] in {"", "synthetic-export.jpg"}
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "asset": {
                "asset_id": "runtime-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 4032,
                "pixel_height": 3024,
                "duration": 0.0,
                "favorite": False,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T17:00:00.000Z",
                "modification_date": "2026-06-04T18:00:00.000Z",
                "primary_filename": "IMG_SYNTHETIC.JPG",
                "resource_count": 1,
                "asset_content_returned": False,
                "asset_content_exported": True,
                "exported_path": str(Path(payload["output_dir"]) / "synthetic-export.jpg"),
                "exported_filename": "synthetic-export.jpg",
                "exported_bytes": 1234,
                "resources": [
                    {
                        "filename": "IMG_SYNTHETIC.JPG",
                        "type": 1,
                        "uniform_type_identifier": "public.jpeg",
                    }
                ],
            },
            "warnings": [],
        }
    if payload["command"] == "photos_apply_change":
        assert payload["operation"] == "import"
        assert payload["media_type"] == "image"
        assert payload["source_file"].endswith("IMG_IMPORT.JPG")
        assert payload["expected_filename"] == "IMG_IMPORT.JPG"
        assert payload["expected_file_size_bytes"] > 0
        assert len(payload["expected_file_sha256"]) == 64
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "asset": {
                "asset_id": "created-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 1600,
                "pixel_height": 1200,
                "duration": 0.0,
                "favorite": False,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T19:00:00.000Z",
                "modification_date": "2026-06-04T19:00:00.000Z",
                "primary_filename": "IMG_IMPORT.JPG",
                "resource_count": 1,
                "asset_content_returned": False,
                "resources": [
                    {
                        "filename": "IMG_IMPORT.JPG",
                        "type": 1,
                        "uniform_type_identifier": "public.jpeg",
                    }
                ],
            },
            "warnings": [],
        }
    raise AssertionError(f"unexpected Photos command: {payload['command']}")


def _source_photo(tmp_path: Path) -> Path:
    source = tmp_path / "IMG_IMPORT.JPG"
    source.write_bytes(b"synthetic image bytes")
    return source


def _photo_import_plan(tmp_path: Path) -> dict:
    return plan_photo_change("import", source_file=_source_photo(tmp_path))


def _photos_token(plan: dict) -> str:
    return "photos-apply:v1:" + plan["preview"]["approval"]["approval_fingerprint"]


def test_search_photos_returns_metadata_only() -> None:
    result = search_photos("SYNTHETIC", photos_runner=_photos_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "filename"
    assert result["result_count"] == 1
    asset = result["results"][0]
    assert asset["handle"].startswith("photos:asset:v1:")
    assert asset["primary_filename"] == "IMG_SYNTHETIC.JPG"
    assert asset["asset_content_returned"] is False
    assert "runtime-photo-1" not in str(result)
    assert "resources" not in asset


def test_search_photos_rejects_broad_query_without_runner() -> None:
    called = False

    def runner(_payload: dict, _timeout: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = search_photos("%", photos_runner=runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"
    assert called is False


def test_get_photo_asset_returns_exact_resource_metadata() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = get_photo_asset(handle, photos_runner=_photos_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["privacy"]["output_tier"] == "detail"
    assert result["result"]["resources"][0]["filename"] == "IMG_SYNTHETIC.JPG"
    assert result["result"]["asset_content_returned"] is False
    assert "runtime-photo-1" not in str(result)


def test_get_photo_asset_rejects_invalid_handle() -> None:
    result = get_photo_asset("photos:asset:runtime-photo-1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_export_photo_asset_returns_exact_export_metadata(tmp_path: Path) -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = export_photo_asset(
        handle,
        output_dir=tmp_path / "exports",
        filename="synthetic-export.jpg",
        photos_runner=_photos_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "export"
    assert result["privacy"]["content_exported"] is True
    assert result["result"]["asset_content_returned"] is False
    assert result["result"]["asset_content_exported"] is True
    assert result["result"]["exported_filename"] == "synthetic-export.jpg"
    assert result["result"]["exported_bytes"] == 1234
    assert result["result"]["exported_path"].endswith("/exports/synthetic-export.jpg")
    assert "runtime-photo-1" not in str(result)


def test_export_photo_asset_rejects_invalid_handle(tmp_path: Path) -> None:
    result = export_photo_asset("photos:asset:runtime-photo-1", output_dir=tmp_path)

    assert result["status"] == "error"
    assert result["privacy"]["output_tier"] == "export"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_search_photos_degrades_without_access() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "authorization_status": "denied",
            "assets": [],
            "warnings": [
                {
                    "code": "photos_access_unavailable",
                    "message": "Photos access is not authorized for this process.",
                }
            ],
        }

    result = search_photos("SYNTHETIC", photos_runner=runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "photos_access_unavailable"


def test_plan_photo_change_import_returns_preview_only(tmp_path: Path) -> None:
    source = _source_photo(tmp_path)

    result = plan_photo_change("import", source_file=source)

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mode"] == "plan"
    assert result["mutation_applied"] is False
    assert result["apply_available"] is True
    assert result["preview"]["idempotency_key"].startswith("photos-plan:v1:")
    assert result["preview"]["approval"]["approval_token_format"].startswith("photos-apply:v1:")
    assert result["preview"]["proposed"]["source_filename"] == "IMG_IMPORT.JPG"
    assert result["preview"]["proposed"]["media_type"] == "image"
    assert result["preview"]["proposed"]["source_path_returned"] is False
    assert str(tmp_path) not in str(result)


def test_plan_photo_change_rejects_unsupported_media(tmp_path: Path) -> None:
    source = tmp_path / "import.txt"
    source.write_text("not a photo", encoding="utf-8")

    result = plan_photo_change("import", source_file=source)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "unsupported_media_type"


def test_apply_photo_change_requires_confirmation(tmp_path: Path) -> None:
    plan = _photo_import_plan(tmp_path)

    result = apply_photo_change(
        "import",
        source_file=tmp_path / "IMG_IMPORT.JPG",
        approval_token=_photos_token(plan),
        photos_runner=_photos_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_apply_confirmation"


def test_apply_photo_change_rejects_bad_token(tmp_path: Path) -> None:
    _photo_import_plan(tmp_path)

    result = apply_photo_change(
        "import",
        source_file=tmp_path / "IMG_IMPORT.JPG",
        approval_token="photos-apply:v1:bad",
        confirm_apply=True,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_approval_token"


def test_apply_photo_change_imports_and_reads_back(tmp_path: Path) -> None:
    plan = _photo_import_plan(tmp_path)

    result = apply_photo_change(
        "import",
        source_file=tmp_path / "IMG_IMPORT.JPG",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "mutation"
    assert result["mode"] == "apply"
    assert result["mutation_applied"] is True
    assert result["read_back"]["handle"].startswith("photos:asset:v1:")
    assert result["read_back"]["primary_filename"] == "IMG_IMPORT.JPG"
    assert result["read_back"]["asset_content_returned"] is False
    assert "created-photo-1" not in str(result)
    assert str(tmp_path) not in str(result)


def test_apply_photo_change_degrades_without_access(tmp_path: Path) -> None:
    plan = _photo_import_plan(tmp_path)

    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "authorization_status": "denied",
            "asset": None,
            "warnings": [
                {
                    "code": "photos_access_unavailable",
                    "message": "Photos access is not authorized for this process.",
                }
            ],
        }

    result = apply_photo_change(
        "import",
        source_file=tmp_path / "IMG_IMPORT.JPG",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert result["status"] == "degraded"
    assert result["mutation_applied"] is False
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "photos_access_unavailable"

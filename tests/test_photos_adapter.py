from __future__ import annotations

import subprocess
from pathlib import Path

import local_apple_data.adapters.photos as photos_adapter
from local_apple_data.handles import make_opaque_handle
from local_apple_data.adapters.photos import (
    apply_photo_change,
    export_photo_asset,
    get_photo_album,
    get_photo_asset,
    list_photo_album_assets,
    plan_photo_change,
    request_photos_full_access,
    search_photo_albums,
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
    if payload["command"] == "photo_albums":
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "albums": [
                {
                    "album_id": "runtime-album-1",
                    "title": "Synthetic Album",
                    "asset_collection_type": 1,
                    "asset_collection_subtype": 2,
                    "estimated_asset_count": 0,
                    "asset_count": 0,
                    "can_add_content": True,
                    "can_remove_content": True,
                    "can_rename": True,
                    "can_delete": True,
                    "raw_album_identifier_returned": False,
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "photo_album_by_id":
        assert payload["album_id"] == "runtime-album-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "album": {
                "album_id": "runtime-album-1",
                "title": "Synthetic Album",
                "asset_collection_type": 1,
                "asset_collection_subtype": 2,
                "estimated_asset_count": 0,
                "asset_count": 0,
                "can_add_content": True,
                "can_remove_content": True,
                "can_rename": True,
                "can_delete": True,
                "raw_album_identifier_returned": False,
            },
            "warnings": [],
        }
    if payload["command"] == "photo_album_assets":
        assert payload["album_id"] == "runtime-album-1"
        assert payload["limit"] == 20
        assert payload["max_assets"] == 5000
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "album": {
                "album_id": "runtime-album-1",
                "title": "Synthetic Album",
                "asset_collection_type": 1,
                "asset_collection_subtype": 2,
                "estimated_asset_count": 1,
                "asset_count": 1,
                "can_add_content": True,
                "can_remove_content": True,
                "can_rename": True,
                "can_delete": True,
                "raw_album_identifier_returned": False,
            },
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
                }
            ],
            "warnings": [],
        }
    if payload["command"] == "photo_album_membership":
        assert payload["asset_id"] == "runtime-photo-1"
        assert payload["album_id"] == "runtime-album-1"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "in_album": False,
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
    if payload["command"] == "photos_update_flags":
        assert payload["asset_id"] == "runtime-photo-1"
        assert payload["expected_favorite"] is False
        assert payload["expected_hidden"] is False
        assert payload["favorite"] is True
        assert payload["hidden"] is False
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "asset": {
                "asset_id": "runtime-photo-1",
                "media_type": "image",
                "media_subtypes": 0,
                "pixel_width": 4032,
                "pixel_height": 3024,
                "duration": 0.0,
                "favorite": True,
                "hidden": False,
                "source_type": 1,
                "creation_date": "2026-06-04T17:00:00.000Z",
                "modification_date": "2026-06-04T18:30:00.000Z",
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
    if payload["command"] == "photos_album_membership":
        assert payload["asset_id"] == "runtime-photo-1"
        assert payload["album_id"] == "runtime-album-1"
        assert payload["operation"] in {"add_to_album", "remove_from_album"}
        assert payload["expected_asset_state"]["primary_filename"] == "IMG_SYNTHETIC.JPG"
        assert payload["expected_album_state"]["title"] == "Synthetic Album"
        target_in_album = payload["operation"] == "add_to_album"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
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
            "album": {
                "album_id": "runtime-album-1",
                "title": "Synthetic Album",
                "asset_collection_type": 1,
                "asset_collection_subtype": 2,
                "estimated_asset_count": 1 if target_in_album else 0,
                "asset_count": 1 if target_in_album else 0,
                "can_add_content": True,
                "can_remove_content": True,
                "can_rename": True,
                "can_delete": True,
                "raw_album_identifier_returned": False,
            },
            "in_album": target_in_album,
            "mutation_applied": True,
            "asset_content_returned": False,
            "raw_asset_identifier_returned": False,
            "raw_album_identifier_returned": False,
            "warnings": [],
        }
    if payload["command"] == "photos_album_management":
        operation = payload["operation"]
        assert operation in {"create_album", "rename_album", "delete_album"}
        if operation == "create_album":
            assert payload["album_title"]
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "photos",
                "authorization_status": "authorized",
                "album": {
                    "album_id": "created-album-1",
                    "title": payload["album_title"],
                    "asset_collection_type": 1,
                    "asset_collection_subtype": 2,
                    "estimated_asset_count": 0,
                    "asset_count": 0,
                    "can_add_content": True,
                    "can_remove_content": True,
                    "can_rename": True,
                    "can_delete": True,
                    "raw_album_identifier_returned": False,
                },
                "mutation_applied": True,
                "raw_album_identifier_returned": False,
                "warnings": [],
            }
        assert payload["album_id"] == "runtime-album-1"
        assert payload["expected_album_state"]["title"]
        if operation == "delete_album":
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "photos",
                "authorization_status": "authorized",
                "album": None,
                "deleted": True,
                "verified_absent": True,
                "mutation_applied": True,
                "raw_album_identifier_returned": False,
                "warnings": [],
            }
        assert payload["album_title"]
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "album": {
                "album_id": "runtime-album-1",
                "title": payload["album_title"],
                "asset_collection_type": 1,
                "asset_collection_subtype": 2,
                "estimated_asset_count": 0,
                "asset_count": 0,
                "can_add_content": True,
                "can_remove_content": True,
                "can_rename": True,
                "can_delete": True,
                "raw_album_identifier_returned": False,
            },
            "mutation_applied": True,
            "raw_album_identifier_returned": False,
            "warnings": [],
        }
    if payload["command"] == "photos_delete_asset":
        assert payload["asset_id"] == "runtime-photo-1"
        assert payload["expected_state"]["primary_filename"] == "IMG_SYNTHETIC.JPG"
        assert payload["expected_state"]["favorite"] is False
        assert payload["expected_state"]["hidden"] is False
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "asset": None,
            "mutation_applied": True,
            "deleted": True,
            "verified_absent": True,
            "asset_content_returned": False,
            "raw_asset_identifier_returned": False,
            "recently_deleted_empty": False,
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


def test_search_photo_albums_returns_metadata_only() -> None:
    result = search_photo_albums("Synthetic", photos_runner=_photos_runner)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "album_title"
    assert result["result_count"] == 1
    album = result["results"][0]
    assert album["handle"].startswith("photos:album:v1:")
    assert album["title"] == "Synthetic Album"
    assert album["asset_collection_type"] == 1
    assert album["asset_collection_subtype"] == 2
    assert album["raw_album_identifier_returned"] is False
    assert "runtime-album-1" not in str(result)


def test_search_photo_albums_rejects_broad_query_without_runner() -> None:
    called = False

    def runner(_payload: dict, _timeout: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = search_photo_albums("%", photos_runner=runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"
    assert called is False


def test_get_photo_album_returns_exact_album_metadata() -> None:
    search = search_photo_albums("Synthetic", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = get_photo_album(handle, photos_runner=_photos_runner)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Synthetic Album"
    assert result["result"]["handle"] == handle
    assert result["result"]["raw_album_identifier_returned"] is False
    assert "runtime-album-1" not in str(result)


def test_get_photo_album_rejects_invalid_handle() -> None:
    result = get_photo_album("photos:album:runtime-album-1")

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_album_handle"


def test_get_photo_album_returns_not_found_for_missing_album() -> None:
    handle = make_opaque_handle("photos:album", "missing-album")

    result = get_photo_album(handle, photos_runner=_photos_runner)

    assert result["status"] == "not_found"
    assert result["result"] is None
    assert "missing-album" not in str(result)


def test_get_photo_album_degrades_without_access() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "authorization_status": "denied",
            "albums": [],
            "warnings": [{"code": "photos_access_unavailable", "message": "denied"}],
        }

    handle = make_opaque_handle("photos:album", "runtime-album-1")
    result = get_photo_album(handle, photos_runner=runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["warnings"][0]["code"] == "photos_access_unavailable"


def test_list_photo_album_assets_returns_metadata_only() -> None:
    search = search_photo_albums("Synthetic", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = list_photo_album_assets(handle, photos_runner=_photos_runner)

    assert result["status"] == "ok"
    assert result["privacy"]["content_inspected"] is False
    assert result["privacy"]["output_tier"] == "metadata"
    assert result["parent"]["title"] == "Synthetic Album"
    assert result["parent"]["handle"] == handle
    assert result["parent"]["raw_album_identifier_returned"] is False
    assert result["query"]["scope"] == "album_assets"
    assert result["result_count"] == 1
    asset = result["results"][0]
    assert asset["handle"].startswith("photos:asset:v1:")
    assert asset["primary_filename"] == "IMG_SYNTHETIC.JPG"
    assert asset["asset_content_returned"] is False
    assert "resources" not in asset
    assert "runtime-photo-1" not in str(result)
    assert "runtime-album-1" not in str(result)


def test_list_photo_album_assets_rejects_invalid_handle() -> None:
    result = list_photo_album_assets("photos:album:runtime-album-1")

    assert result["status"] == "error"
    assert result["parent"] is None
    assert result["results"] == []
    assert result["warnings"][0]["code"] == "invalid_album_handle"


def test_list_photo_album_assets_degrades_without_access() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "authorization_status": "denied",
            "albums": [],
            "warnings": [{"code": "photos_access_unavailable", "message": "denied"}],
        }

    handle = make_opaque_handle("photos:album", "runtime-album-1")
    result = list_photo_album_assets(handle, photos_runner=runner)

    assert result["status"] == "degraded"
    assert result["authorization_status"] == "denied"
    assert result["results"] == []
    assert result["warnings"][0]["code"] == "photos_access_unavailable"


def test_list_photo_album_assets_preserves_album_scan_truncation_on_not_found() -> None:
    calls: list[str] = []

    def runner(payload: dict, _timeout: float) -> dict:
        calls.append(str(payload["command"]))
        assert payload["command"] == "photo_albums"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "albums": [],
            "warnings": [
                {"code": "scan_truncated", "message": "Photos album scan stopped at the scan limit."}
            ],
        }

    handle = make_opaque_handle("photos:album", "album-outside-scan")
    result = list_photo_album_assets(handle, photos_runner=runner)

    assert calls == ["photo_albums"]
    assert result["status"] == "not_found"
    assert result["results"] == []
    assert [warning["code"] for warning in result["warnings"]] == [
        "scan_truncated",
        "photo_album_not_found",
    ]


def test_list_photo_album_assets_preserves_truncation_warning() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photo_album_assets":
            response = _photos_runner(payload, timeout)
            response["warnings"] = [
                {"code": "result_truncated", "message": "Photos album asset listing stopped at the result limit."}
            ]
            return response
        return _photos_runner(payload, timeout)

    search = search_photo_albums("Synthetic", photos_runner=runner)
    result = list_photo_album_assets(search["results"][0]["handle"], photos_runner=runner)

    assert result["status"] == "ok"
    assert result["warnings"][0]["code"] == "result_truncated"


def test_plan_photo_add_to_album_requires_expected_membership() -> None:
    photo = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    album = search_photo_albums("Synthetic", photos_runner=_photos_runner)

    result = plan_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        photos_runner=_photos_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_expected_membership"


def test_plan_photo_add_to_album_rejects_expected_membership_mismatch() -> None:
    photo = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    album = search_photo_albums("Synthetic", photos_runner=_photos_runner)

    result = plan_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=True,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "expected_membership_mismatch"


def test_plan_photo_add_to_album_rejects_unsupported_album() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        response = _photos_runner(payload, timeout)
        if payload["command"] == "photo_album_by_id":
            response["album"]["can_add_content"] = False
        return response

    photo = search_photos("SYNTHETIC", photos_runner=runner)
    album = search_photo_albums("Synthetic", photos_runner=runner)

    result = plan_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=False,
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "photos_album_add_not_supported"


def test_plan_photo_remove_from_album_rejects_unsupported_album() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        response = _photos_runner(payload, timeout)
        if payload["command"] == "photo_album_by_id":
            response["album"]["can_remove_content"] = False
        return response

    photo = search_photos("SYNTHETIC", photos_runner=runner)
    album = search_photo_albums("Synthetic", photos_runner=runner)

    result = plan_photo_change(
        "remove_from_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=True,
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "photos_album_remove_not_supported"


def test_apply_photo_add_to_album_reads_back_membership() -> None:
    photo = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    album = search_photo_albums("Synthetic", photos_runner=_photos_runner)
    plan = plan_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=False,
        photos_runner=_photos_runner,
    )

    result = apply_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=False,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=_photos_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "add_to_album"
    assert plan["preview"]["target"]["album_handle"].startswith("photos:album:v1:")
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["in_album"] is True
    assert result["read_back"]["raw_album_identifier_returned"] is False
    assert "runtime-album-1" not in str(result)
    assert "runtime-photo-1" not in str(result)


def test_apply_photo_add_to_album_rejects_membership_read_back_mismatch() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        response = _photos_runner(payload, timeout)
        if payload["command"] == "photos_album_membership":
            response["in_album"] = False
        return response

    photo = search_photos("SYNTHETIC", photos_runner=runner)
    album = search_photo_albums("Synthetic", photos_runner=runner)
    plan = plan_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=False,
        photos_runner=runner,
    )

    result = apply_photo_change(
        "add_to_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=False,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "read_back_state_mismatch"


def test_apply_photo_remove_from_album_reads_back_membership() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photo_album_membership":
            response = _photos_runner(payload, timeout)
            response["in_album"] = True
            return response
        return _photos_runner(payload, timeout)

    photo = search_photos("SYNTHETIC", photos_runner=runner)
    album = search_photo_albums("Synthetic", photos_runner=runner)
    plan = plan_photo_change(
        "remove_from_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=True,
        photos_runner=runner,
    )

    result = apply_photo_change(
        "remove_from_album",
        handle=photo["results"][0]["handle"],
        album_handle=album["results"][0]["handle"],
        expected_in_album=True,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "remove_from_album"
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["in_album"] is False
    assert result["read_back"]["raw_album_identifier_returned"] is False
    assert "runtime-album-1" not in str(result)
    assert "runtime-photo-1" not in str(result)


def _album_runner(title: str = "Vacation Original", asset_count: int = 0):
    def runner(payload: dict, timeout: float) -> dict:
        response = _photos_runner(payload, timeout)
        if payload["command"] in {"photo_albums", "photo_album_by_id"}:
            albums = response.get("albums")
            if isinstance(albums, list):
                for album in albums:
                    album["title"] = title
                    album["asset_count"] = asset_count
                    album["estimated_asset_count"] = asset_count
            album = response.get("album")
            if isinstance(album, dict):
                album["title"] = title
                album["asset_count"] = asset_count
                album["estimated_asset_count"] = asset_count
        return response

    return runner


def test_plan_photo_create_album_accepts_regular_title() -> None:
    result = plan_photo_change("create_album", album_title="Vacation", photos_runner=_photos_runner)

    assert result["status"] == "ok"
    assert result["preview"]["proposed"]["album_title"] == "Vacation"


def test_plan_photo_create_album_rejects_missing_title() -> None:
    result = plan_photo_change("create_album", album_title="   ", photos_runner=_photos_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_album_title"


def test_plan_photo_create_album_rejects_duplicate_title() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        response = _photos_runner(payload, timeout)
        if payload["command"] == "photo_albums":
            response["albums"][0]["title"] = "Vacation Duplicate"
        return response

    result = plan_photo_change(
        "create_album",
        album_title="Vacation Duplicate",
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "duplicate_album_title"


def test_plan_photo_create_album_rejects_limited_photos_access() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        response = _photos_runner(payload, timeout)
        if payload["command"] == "photo_albums":
            response["authorization_status"] = "limited"
            response["albums"] = []
        return response

    result = plan_photo_change(
        "create_album",
        album_title="Vacation Limited",
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["authorization_status"] == "limited"
    assert result["preview"] is None
    assert result["warnings"][0]["code"] == "photos_full_access_required"


def test_plan_photo_create_album_fails_closed_on_title_scan_truncation() -> None:
    def runner(payload: dict, _timeout: float) -> dict:
        assert payload["command"] == "photo_albums"
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "albums": [],
            "warnings": [
                {"code": "result_truncated", "message": "Photos album search stopped at the result limit."}
            ],
        }

    result = plan_photo_change(
        "create_album",
        album_title="Vacation Unique",
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert [warning["code"] for warning in result["warnings"]] == [
        "result_truncated",
        "album_title_scan_truncated",
    ]


def test_plan_photo_rename_album_rejects_limited_photos_access() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        response = _album_runner()(payload, timeout)
        if payload["command"] in {"photo_albums", "photo_album_by_id"}:
            response["authorization_status"] = "limited"
        return response

    handle = make_opaque_handle("photos:album", "runtime-album-1")
    result = plan_photo_change(
        "rename_album",
        album_handle=handle,
        new_album_title="Vacation Renamed",
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["authorization_status"] == "limited"
    assert result["preview"] is None
    assert result["warnings"][0]["code"] == "photos_full_access_required"


def test_apply_photo_create_album_reads_back_album() -> None:
    plan = plan_photo_change(
        "create_album",
        album_title="Vacation Created",
        photos_runner=_photos_runner,
    )

    result = apply_photo_change(
        "create_album",
        album_title="Vacation Created",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=_photos_runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "create_album"
    assert plan["preview"]["proposed"]["album_title"] == "Vacation Created"
    assert result["status"] == "ok"
    assert result["mutation_applied"] is True
    assert result["read_back"]["album"]["title"] == "Vacation Created"
    assert result["read_back"]["raw_album_identifier_returned"] is False
    assert "created-album-1" not in str(result)


def test_apply_photo_create_album_surfaces_helper_duplicate_race() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photos_album_management":
            return {
                "schema_version": 1,
                "status": "error",
                "source": "photos",
                "authorization_status": "authorized",
                "album": None,
                "warnings": [
                    {
                        "code": "duplicate_album_title",
                    "message": "A Photos album with the requested title already exists.",
                    }
                ],
            }
        return _photos_runner(payload, timeout)

    plan = plan_photo_change(
        "create_album",
        album_title="Vacation Race",
        photos_runner=runner,
    )

    result = apply_photo_change(
        "create_album",
        album_title="Vacation Race",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "duplicate_album_title"
    assert result["mutation_applied"] is False


def test_apply_photo_create_album_surfaces_full_access_requirement() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photos_album_management":
            return {
                "schema_version": 1,
                "status": "degraded",
                "source": "photos",
                "authorization_status": "limited",
                "album": None,
                "warnings": [
                    {
                        "code": "photos_full_access_required",
                        "message": "Photos album management requires full Photos Library access.",
                    }
                ],
            }
        return _photos_runner(payload, timeout)

    plan = plan_photo_change(
        "create_album",
        album_title="Vacation Limited",
        photos_runner=runner,
    )

    result = apply_photo_change(
        "create_album",
        album_title="Vacation Limited",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "degraded"
    assert result["authorization_status"] == "limited"
    assert result["warnings"][0]["code"] == "photos_full_access_required"
    assert result["mutation_applied"] is False


def test_apply_photo_create_album_preserves_helper_apply_unknown() -> None:
    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photos_album_management":
            return {
                "schema_version": 1,
                "status": "apply_unknown",
                "source": "photos",
                "authorization_status": "authorized",
                "mutation_applied": True,
                "warnings": [
                    {
                        "code": "duplicate_album_title",
                        "message": "Post-apply title uniqueness could not be proven.",
                    }
                ],
            }
        return _photos_runner(payload, timeout)

    plan = plan_photo_change(
        "create_album",
        album_title="Vacation Unknown",
        photos_runner=runner,
    )

    result = apply_photo_change(
        "create_album",
        album_title="Vacation Unknown",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert plan["status"] == "ok"
    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["warnings"][0]["code"] == "duplicate_album_title"


def test_apply_photo_rename_album_reads_back_title() -> None:
    runner = _album_runner(title="Vacation Original")
    album = search_photo_albums("Vacation", photos_runner=runner)
    handle = album["results"][0]["handle"]
    plan = plan_photo_change(
        "rename_album",
        album_handle=handle,
        new_album_title="Vacation Renamed",
        photos_runner=runner,
    )

    result = apply_photo_change(
        "rename_album",
        album_handle=handle,
        new_album_title="Vacation Renamed",
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["target"]["album_handle"] == handle
    assert plan["preview"]["proposed"]["previous_album_title"] == "Vacation Original"
    assert result["status"] == "ok"
    assert result["read_back"]["album"]["title"] == "Vacation Renamed"
    assert "runtime-album-1" not in str(result)


def test_plan_photo_delete_album_rejects_non_empty_album() -> None:
    runner = _album_runner(asset_count=1)
    album = search_photo_albums("Vacation", photos_runner=runner)

    result = plan_photo_change(
        "delete_album",
        album_handle=album["results"][0]["handle"],
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "non_empty_album_blocked"


def test_apply_photo_delete_album_proves_absence() -> None:
    runner = _album_runner()
    album = search_photo_albums("Vacation", photos_runner=runner)
    handle = album["results"][0]["handle"]
    plan = plan_photo_change("delete_album", album_handle=handle, photos_runner=runner)

    result = apply_photo_change(
        "delete_album",
        album_handle=handle,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert plan["status"] == "ok"
    assert plan["preview"]["operation"] == "delete_album"
    assert result["status"] == "ok"
    assert result["result_count"] == 0
    assert result["read_back"]["deleted"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["raw_album_identifier_returned"] is False
    assert "runtime-album-1" not in str(result)


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
    assert result["privacy"]["content_exported"] is False
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_export_photo_asset_degraded_response_does_not_mark_exported(
    tmp_path: Path,
) -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

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

    result = export_photo_asset(handle, output_dir=tmp_path / "exports", photos_runner=runner)

    assert result["status"] == "degraded"
    assert result["privacy"]["output_tier"] == "export"
    assert result["privacy"]["content_exported"] is False
    assert result["warnings"][0]["code"] == "photos_access_unavailable"


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


def test_plan_photo_change_update_flags_returns_exact_preview() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = plan_photo_change(
        "update-flags",
        handle=handle,
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["preview"]["target"]["handle"] == handle
    assert result["preview"]["target"]["expected_favorite"] is False
    assert result["preview"]["target"]["expected_hidden"] is False
    assert result["preview"]["proposed"]["favorite"] is True
    assert result["preview"]["proposed"]["hidden"] is False
    assert result["preview"]["proposed"]["raw_asset_identifier_returned"] is False
    assert "runtime-photo-1" not in str(result)


def test_plan_photo_change_update_flags_requires_expected_state() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = plan_photo_change(
        "update_flags",
        handle=handle,
        favorite=True,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_expected_state"


def test_plan_photo_change_update_flags_requires_target_without_scan() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        raise AssertionError("update_flags input validation should not scan Photos")

    result = plan_photo_change(
        "update_flags",
        handle=make_opaque_handle("photos:asset", "runtime-photo-1"),
        expected_favorite=False,
        expected_hidden=False,
        photos_runner=runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "missing_target_flags"


def test_plan_photo_change_update_flags_rejects_stale_expected_state() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = plan_photo_change(
        "update_flags",
        handle=handle,
        favorite=True,
        expected_favorite=True,
        expected_hidden=False,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "expected_state_mismatch"


def test_plan_photo_change_update_flags_honors_large_scan_limit() -> None:
    seen_limits: list[tuple[int, int]] = []

    def runner(payload: dict, _timeout: float) -> dict:
        if payload["command"] == "photos":
            seen_limits.append((payload["limit"], payload["max_assets"]))
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "photos",
                "authorization_status": "authorized",
                "assets": [
                    {
                        "asset_id": "late-photo",
                        "media_type": "image",
                        "media_subtypes": 0,
                        "pixel_width": 1,
                        "pixel_height": 1,
                        "duration": 0.0,
                        "favorite": False,
                        "hidden": False,
                        "source_type": 1,
                        "creation_date": "2026-06-04T17:00:00.000Z",
                        "modification_date": "2026-06-04T18:00:00.000Z",
                        "primary_filename": "IMG_LATE.JPG",
                        "resource_count": 1,
                        "asset_content_returned": False,
                    }
                ],
                "warnings": [],
            }
        if payload["command"] == "photo_by_id":
            assert payload["asset_id"] == "late-photo"
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "photos",
                "authorization_status": "authorized",
                "asset": {
                    "asset_id": "late-photo",
                    "media_type": "image",
                    "media_subtypes": 0,
                    "pixel_width": 1,
                    "pixel_height": 1,
                    "duration": 0.0,
                    "favorite": False,
                    "hidden": False,
                    "source_type": 1,
                    "creation_date": "2026-06-04T17:00:00.000Z",
                    "modification_date": "2026-06-04T18:00:00.000Z",
                    "primary_filename": "IMG_LATE.JPG",
                    "resource_count": 1,
                    "asset_content_returned": False,
                    "resources": [],
                },
                "warnings": [],
            }
        raise AssertionError(f"unexpected command {payload['command']}")

    result = plan_photo_change(
        "update_flags",
        handle=make_opaque_handle("photos:asset", "late-photo"),
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
        max_scan_assets=10000,
        photos_runner=runner,
    )

    assert result["status"] == "ok"
    assert seen_limits == [(10000, 10000)]


def test_plan_photo_change_delete_returns_exact_preview() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]

    result = plan_photo_change(
        "delete",
        handle=handle,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["output_tier"] == "preview"
    assert result["mutation_applied"] is False
    assert result["preview"]["operation"] == "delete"
    assert result["preview"]["target"]["handle"] == handle
    assert len(result["preview"]["target"]["delete_safe_sha256"]) == 64
    assert result["preview"]["target"]["expected_state"]["primary_filename"] == "IMG_SYNTHETIC.JPG"
    assert result["preview"]["proposed"]["delete_scope"] == "library_asset"
    assert result["preview"]["proposed"]["permanent_delete"] == "blocked"
    assert result["preview"]["proposed"]["recently_deleted_empty"] == "blocked"
    assert result["preview"]["proposed"]["raw_asset_identifier_returned"] is False
    assert "runtime-photo-1" not in str(result)


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


def test_apply_photo_change_update_flags_reads_back_exact_state() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]
    plan = plan_photo_change(
        "update_flags",
        handle=handle,
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
        photos_runner=_photos_runner,
    )

    result = apply_photo_change(
        "update_flags",
        handle=handle,
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "update_flags"
    assert result["mutation_applied"] is True
    assert result["read_back"]["favorite"] is True
    assert result["read_back"]["hidden"] is False
    assert result["read_back"]["asset_content_returned"] is False
    assert "runtime-photo-1" not in str(result)


def test_apply_photo_change_update_flags_rejects_read_back_state_mismatch() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]
    plan = plan_photo_change(
        "update_flags",
        handle=handle,
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
        photos_runner=_photos_runner,
    )

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photos_update_flags":
            response = _photos_runner(payload, timeout)
            response["asset"]["favorite"] = False
            return response
        return _photos_runner(payload, timeout)

    result = apply_photo_change(
        "update_flags",
        handle=handle,
        favorite=True,
        expected_favorite=False,
        expected_hidden=False,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is False
    assert result["read_back"] is None
    assert result["warnings"][0]["code"] == "read_back_state_mismatch"


def test_apply_photo_change_delete_proves_absence() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]
    plan = plan_photo_change("delete", handle=handle, photos_runner=_photos_runner)

    result = apply_photo_change(
        "delete",
        handle=handle,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=_photos_runner,
    )

    assert result["status"] == "ok"
    assert result["operation"] == "delete"
    assert result["mutation_applied"] is True
    assert result["result_count"] == 0
    assert result["read_back"]["deleted"] is True
    assert result["read_back"]["verified_absent"] is True
    assert result["read_back"]["recently_deleted_empty"] is False
    assert result["read_back"]["asset_content_returned"] is False
    assert result["read_back"]["raw_asset_identifier_returned"] is False
    assert "runtime-photo-1" not in str(result)


def test_apply_photo_change_delete_requires_absence_proof() -> None:
    search = search_photos("SYNTHETIC", photos_runner=_photos_runner)
    handle = search["results"][0]["handle"]
    plan = plan_photo_change("delete", handle=handle, photos_runner=_photos_runner)

    def runner(payload: dict, timeout: float) -> dict:
        if payload["command"] == "photos_delete_asset":
            response = _photos_runner(payload, timeout)
            response["verified_absent"] = False
            return response
        return _photos_runner(payload, timeout)

    result = apply_photo_change(
        "delete",
        handle=handle,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is True
    assert result["read_back"] is None
    assert result["warnings"][0]["code"] == "read_back_state_mismatch"


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


def test_request_photos_full_access_calls_helper() -> None:
    seen: dict[str, object] = {}

    def runner(payload: dict, timeout: float) -> dict:
        seen["payload"] = payload
        seen["timeout"] = timeout
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": "authorized",
            "request_result": "granted",
            "warnings": [],
        }

    result = request_photos_full_access(photos_runner=runner)

    assert seen["payload"] == {"command": "request_photos_full_access"}
    assert seen["timeout"] == 190.0
    assert result["status"] == "ok"
    assert result["authorization_status"] == "authorized"
    assert result["request_result"] == "granted"


def test_request_photos_full_access_timeout() -> None:
    def runner(_payload: dict, _timeout: float) -> dict:
        raise subprocess.TimeoutExpired(["swift"], 190.0)

    result = request_photos_full_access(photos_runner=runner)

    assert result["status"] == "degraded"
    assert result["request_result"] == "timeout"
    assert result["warnings"][0]["code"] == "photos_access_request_timeout"


def test_request_photos_full_access_does_not_provision_with_mocked_runner(
    monkeypatch,
) -> None:
    # The prepare hook only fires on the real photos_runner=None path.
    monkeypatch.setattr(
        photos_adapter,
        "_prepare_photos_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("prepare fired with a mocked runner")),
    )

    def runner(_payload: dict, _timeout: float) -> dict:
        return {"status": "ok", "authorization_status": "authorized", "warnings": []}

    result = request_photos_full_access(photos_runner=runner)

    assert result["status"] == "ok"


def test_prepare_photos_helper_signing_provisions_and_invalidates(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        photos_adapter,
        "_provision_local_signing_identity",
        lambda: "Local Apple Data Signing",
    )

    def _invalidate(app_root, identity):
        calls["app_root"] = app_root
        calls["identity"] = identity
        return True

    monkeypatch.setattr(
        photos_adapter._signing, "invalidate_app_if_signing_mismatch", _invalidate
    )

    photos_adapter._prepare_photos_helper_signing()

    assert calls["identity"] == "Local Apple Data Signing"
    assert calls["app_root"] == photos_adapter._photos_helper_app_root()


def test_photos_read_path_never_provisions(monkeypatch) -> None:
    monkeypatch.setattr(
        photos_adapter,
        "_provision_local_signing_identity",
        lambda: (_ for _ in ()).throw(AssertionError("read path provisioned")),
    )
    monkeypatch.setattr(
        photos_adapter,
        "_prepare_photos_helper_signing",
        lambda: (_ for _ in ()).throw(AssertionError("read path prepared signing")),
    )

    result = search_photos("beach", photos_runner=_photos_runner)

    assert result["status"] in {"ok", "degraded", "error"}


def test_photos_helper_uses_shared_stable_signing(monkeypatch, tmp_path: Path) -> None:
    # The Photos ensure path must sign through the shared module (stable identity
    # + hardened runtime + entitlement, with ad-hoc fallback), not a hard-coded
    # ad-hoc signature.
    photos_source = Path("src/local_apple_data/adapters/photos.py").read_text(
        encoding="utf-8"
    )
    assert "_signing.sign_helper_app(" in photos_source


def test_photos_helper_has_exact_delete_command() -> None:
    source = Path("scripts/photos_helper.swift").read_text(encoding="utf-8")

    assert 'if command == "photos_delete_asset"' in source
    assert "PHAssetChangeRequest.deleteAssets" in source
    assert "canPerform(.delete)" in source
    assert "func numericValue" in source
    assert "as? UInt" in source
    assert "numericValue(expected)" in source
    assert '"verified_absent"' in source
    assert '"recently_deleted_empty"' in source


def test_photos_helper_has_request_access_command() -> None:
    source = Path("scripts/photos_helper.swift").read_text(encoding="utf-8")

    assert 'commandLineOptionValue("--input-json-file")' in source
    assert 'commandLineOptionValue("--output-json-file")' in source
    assert 'if command == "request_photos_full_access"' in source
    assert "if fullLibraryAuthorized(initialStatus)" in source
    assert "if fullLibraryAuthorized(finalStatus)" in source
    assert "already_limited" not in source
    assert "PHPhotoLibrary.requestAuthorization(for: .readWrite)" in source
    assert "PHPhotoLibrary.requestAuthorization { status in" in source
    assert '"photos_access_request_timeout"' in source
    assert '"photos_full_access_required"' in source


def test_photos_helper_has_album_assets_command() -> None:
    source = Path("scripts/photos_helper.swift").read_text(encoding="utf-8")

    assert 'if command == "photo_album_assets"' in source
    assert "PHAsset.fetchAssets(in: album, options: nil)" in source
    assert "assetPayload(asset, includeResources: false)" in source
    assert '"Photos album asset scan stopped at the scan limit."' in source
    assert '"Photos album asset listing stopped at the result limit."' in source


def test_photos_helper_album_detail_returns_authorization_status() -> None:
    source = Path("scripts/photos_helper.swift").read_text(encoding="utf-8")
    detail_source = source.split('if command == "photo_album_by_id"', 1)[1].split(
        'if command == "photo_album_assets"',
        1,
    )[0]

    assert detail_source.count('"authorization_status"') >= 3


def test_photos_helper_has_album_management_command() -> None:
    source = Path("scripts/photos_helper.swift").read_text(encoding="utf-8")

    assert 'if command == "photos_album_management"' in source
    assert "fullLibraryAuthorized(status)" in source
    assert "albumManagementAccessUnavailablePayload(status)" in source
    assert '"photos_full_access_required"' in source
    assert "creationRequestForAssetCollection(withTitle: albumTitle)" in source
    assert "PHAssetCollectionChangeRequest(for: album)" in source
    assert "PHAssetCollectionChangeRequest.deleteAssetCollections" in source
    assert "isValidAlbumTitle" in source
    assert "fetchAlbumWithExactTitle" in source
    assert '"result_truncated"' in source
    assert "album.canPerform(.rename)" in source
    assert "album.canPerform(.delete)" in source


def test_photos_helper_app_declares_photos_usage_strings() -> None:
    plist = photos_adapter._photos_helper_info_plist()

    assert plist["CFBundleIdentifier"] == photos_adapter.PHOTOS_HELPER_BUNDLE_ID
    # The generic default applies only when no operator bundle-id override is set
    # (an override such as a `.env.local`-pinned id legitimately changes this).
    import os as _os

    if not _os.environ.get("LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID"):
        assert plist["CFBundleIdentifier"] == "com.local-apple-data.photos-helper"
    assert "NSPhotoLibraryUsageDescription" in plist
    assert "NSPhotoLibraryAddUsageDescription" in plist
    assert photos_adapter._photos_helper_entitlements() == {
        "com.apple.security.personal-information.photos-library": True,
    }


def test_photos_helper_app_validation_checks_plist_digest_and_signature(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_root = tmp_path / "PhotosHelper.app"
    contents = app_root / "Contents"
    executable = contents / "MacOS" / "photos_helper"
    resources = contents / "Resources"
    executable.parent.mkdir(parents=True)
    resources.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    entitlements = resources / "entitlements.plist"
    with (contents / "Info.plist").open("wb") as handle:
        import plistlib

        plistlib.dump(photos_adapter._photos_helper_info_plist(), handle)
    with entitlements.open("wb") as handle:
        plistlib.dump(photos_adapter._photos_helper_entitlements(), handle)
    (resources / "source.sha256").write_text("digest", encoding="utf-8")

    def fake_run(args, *_unused, **_kwargs):
        stdout = ""
        if "--entitlements" in args:
            stdout = "com.apple.security.personal-information.photos-library"
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(photos_adapter.subprocess, "run", fake_run)

    assert photos_adapter._photos_helper_app_valid(app_root, "digest") is True

    (resources / "source.sha256").write_text("stale", encoding="utf-8")
    assert photos_adapter._photos_helper_app_valid(app_root, "digest") is False


# --- v1.182 cold-start timeout robustness (read-only retry, apply no-retry) ---


def test_read_timeout_value_accommodates_cold_photokit_init() -> None:
    # A cold PhotoKit fetch can take tens of seconds; the read budget must be
    # generous enough that a warm library never spuriously times out.
    assert photos_adapter.PHOTOS_TIMEOUT_SECONDS >= 45.0


def test_search_photos_retries_once_on_cold_start_timeout() -> None:
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "photos" and calls.count("photos") == 1:
            raise subprocess.TimeoutExpired(cmd="open", timeout=timeout)
        return _photos_runner(payload, timeout)

    result = search_photos("SYNTHETIC", photos_runner=runner)

    # First (cold) call timed out, warm retry succeeded.
    assert calls.count("photos") == 2
    assert result["status"] == "ok"
    assert result["result_count"] == 1


def test_search_photos_degrades_cleanly_when_both_reads_time_out() -> None:
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        raise subprocess.TimeoutExpired(cmd="open", timeout=timeout)

    result = search_photos("SYNTHETIC", photos_runner=runner)

    # Exactly one retry: two attempts, then a clean degraded result (no crash).
    assert calls.count("photos") == 2
    assert result["status"] == "degraded"
    assert any(warning["code"] == "photos_timeout" for warning in result["warnings"])


def test_apply_photo_delete_does_not_retry_on_timeout() -> None:
    calls: list[str] = []

    def runner(payload: dict, timeout: float) -> dict:
        calls.append(payload["command"])
        if payload["command"] == "photos_delete_asset":
            raise subprocess.TimeoutExpired(cmd="open", timeout=timeout)
        return _photos_runner(payload, timeout)

    search = search_photos("SYNTHETIC", photos_runner=runner)
    handle = search["results"][0]["handle"]
    plan = plan_photo_change("delete", handle=handle, photos_runner=runner)
    result = apply_photo_change(
        "delete",
        handle=handle,
        approval_token=_photos_token(plan),
        confirm_apply=True,
        photos_runner=runner,
    )

    # A destructive apply timeout is NOT retried: the mutation command runs once.
    assert calls.count("photos_delete_asset") == 1
    assert result["status"] == "apply_unknown"
    assert result["mutation_applied"] is False
    assert any(warning["code"] == "photos_apply_timeout" for warning in result["warnings"])

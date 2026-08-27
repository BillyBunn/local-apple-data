from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from . import _signing
from .sqlite_store import has_minimum_query_quality
from .warning_safety import safe_warning_payloads


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PHOTOS_HELPER = PROJECT_ROOT / "scripts/photos_helper.swift"
PHOTOS_HELPER_BUNDLE_ID = os.environ.get(
    "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID",
    "com.local-apple-data.photos-helper",
)


def _photos_helper_bundle_id() -> str:
    return os.environ.get(
        "LOCAL_APPLE_DATA_PHOTOS_HELPER_BUNDLE_ID",
        PHOTOS_HELPER_BUNDLE_ID,
    )
# Cold PhotoKit init (first access after auth/reboot on a real library) can take
# tens of seconds; a 15s budget reliably timed out and raced the temp-dir deletion.
# 60s accommodates the cold fetch; a warm retry (below) covers the rare miss.
PHOTOS_TIMEOUT_SECONDS = 60.0
PHOTOS_APPLY_TIMEOUT_SECONDS = 90.0
PHOTOS_REQUEST_ACCESS_TIMEOUT_SECONDS = 190.0
DEFAULT_LIMIT = 20
DEFAULT_MAX_SCAN_ASSETS = 5000
PHOTO_HANDLE_PREFIX = "photos:asset"
PHOTO_ALBUM_HANDLE_PREFIX = "photos:album"
MAX_PREVIEW_FILENAME_CHARS = 255
MAX_IMPORT_BYTES = 2 * 1024 * 1024 * 1024
MAX_ALBUM_TITLE_CHARS = 200
PLAN_OPERATIONS = {
    "import",
    "update_flags",
    "delete",
    "add_to_album",
    "remove_from_album",
    "create_album",
    "rename_album",
    "delete_album",
}
APPROVAL_TOKEN_PREFIX = "photos-apply:v1:"
IMAGE_SUFFIXES = {".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
VIDEO_SUFFIXES = {".m4v", ".mov", ".mp4"}
PhotosRunner = Callable[[dict[str, Any], float], dict[str, Any]]


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _detail_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "detail",
    }


def _export_privacy(*, content_exported: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "content_exported": content_exported,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "export",
    }


def _preview_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "preview",
    }


def _mutation_privacy(*, content_inspected: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": content_inspected,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "mutation",
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Photos search requires a non-empty filename query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Photos search requires at least two letters or digits.",
            )
        ],
    }


def _empty_album_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Photos album search requires a non-empty album-title query.",
            )
        ],
    }


def _broad_album_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Photos album search requires at least two letters or digits.",
            )
        ],
    }


def search_photos(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    media_type: str = "all",
    max_scan_assets: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not has_minimum_query_quality(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, 50))
    bounded_media_type = _bounded_media_type(media_type)
    response = _photos_response(
        query=query,
        limit=bounded_limit,
        media_type=bounded_media_type,
        max_scan_assets=max_scan_assets,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return _photos_degraded_result(response, detail=False)

    results = [_asset_metadata(asset) for asset in response.get("assets", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "filename",
            "limit": bounded_limit,
            "media_type": bounded_media_type,
            "max_scan_assets": _bounded_max_scan(max_scan_assets),
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def search_photo_albums(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_albums: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_album_query_result()
    if not has_minimum_query_quality(query):
        return _broad_album_query_result()

    bounded_limit = max(1, min(limit, 50))
    response = _photos_album_response(
        query=query,
        limit=bounded_limit,
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return _photos_album_degraded_result(response, detail=False)

    results = [_album_metadata(album) for album in response.get("albums", [])]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status"),
        "query": {
            "scope": "album_title",
            "limit": bounded_limit,
            "max_scan_albums": _bounded_max_scan(max_scan_albums),
        },
        "results": results,
        "result_count": len(results),
        "warnings": _safe_warnings(response),
    }


def request_photos_full_access(
    *,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    """Trigger the PhotoKit Photos access prompt from the same helper path used for Photos calls."""

    runner = photos_runner or _run_photos_helper
    if photos_runner is None:
        # Real request-access path only: provision a stable signing identity and
        # rebuild the helper stably signed so TCC actually presents the prompt.
        _prepare_photos_helper_signing()
    try:
        response = _run_read_helper(
            runner,
            {"command": "request_photos_full_access"},
            PHOTOS_REQUEST_ACCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "timeout",
            "warnings": [
                _warning(
                    "photos_access_request_timeout",
                    "Photos access prompt did not complete before timeout.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "privacy": _privacy(),
            "authorization_status": "unknown",
            "request_result": "unavailable",
            "warnings": [
                _warning(
                    "photos_unavailable",
                    "Photos access request is unavailable through the local PhotoKit helper.",
                )
            ],
        }
    return {
        "schema_version": 1,
        "status": str(response.get("status") or "degraded"),
        "source": "photos",
        "privacy": _privacy(),
        "authorization_status": str(response.get("authorization_status") or "unknown"),
        "request_result": str(response.get("request_result") or "unknown"),
        "warnings": _safe_warnings(response),
    }


def get_photo_album(
    handle: str,
    *,
    max_scan_albums: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_ALBUM_HANDLE_PREFIX):
        return _invalid_album_handle_result()

    response = _photos_album_response(
        query="",
        limit=_bounded_max_scan(max_scan_albums),
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return _photos_album_degraded_result(response, detail=True)

    album_id = _resolve_album_id(handle, response.get("albums", []))
    if album_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "privacy": _detail_privacy(),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = photos_runner or _run_photos_helper
    try:
        detail = _run_read_helper(
            runner,
            {"command": "photo_album_by_id", "album_id": album_id},
            PHOTOS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _album_detail_unavailable_result()

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "privacy": _detail_privacy(),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _photos_album_degraded_result(detail, detail=True)

    album = detail.get("album")
    if not isinstance(album, dict):
        return _album_detail_unavailable_result()

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _detail_privacy(),
        "result": _album_detail(album),
        "result_count": 1,
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
    }


def list_photo_album_assets(
    handle: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_albums: int = DEFAULT_MAX_SCAN_ASSETS,
    max_scan_assets: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_ALBUM_HANDLE_PREFIX):
        return _invalid_album_asset_list_handle_result()

    selected = _selected_album(
        handle,
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if selected["status"] != "ok":
        return _album_asset_list_error(
            status="degraded" if selected["status"] == "degraded" else str(selected["status"]),
            authorization_status=selected.get("authorization_status"),
            warnings=selected["warnings"]
            or [_warning("photo_album_not_found", "Selected Photos album was not found.")],
        )

    response = _photo_album_assets_response(
        album_id=str(selected["album_id"]),
        limit=limit,
        max_scan_assets=max_scan_assets,
        photos_runner=photos_runner,
    )
    if response.get("status") == "not_found":
        return _album_asset_list_error(
            status="not_found",
            authorization_status=response.get("authorization_status"),
            warnings=_safe_warnings(response)
            or [_warning("photo_album_not_found", "Selected Photos album was not found.")],
        )
    if response.get("status") != "ok":
        return _album_asset_list_error(
            status="degraded",
            authorization_status=response.get("authorization_status"),
            warnings=_safe_warnings(response),
        )

    album = response.get("album")
    if not isinstance(album, dict):
        album = selected["album"]
    assets = response.get("assets")
    if not isinstance(assets, list):
        return _album_asset_list_error(
            status="degraded",
            authorization_status=response.get("authorization_status"),
            warnings=[_warning("photos_read_error", "Photo album assets could not be read safely.")],
        )

    results = [_asset_metadata(asset) for asset in assets if isinstance(asset, dict)]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _privacy(),
        "authorization_status": response.get("authorization_status")
        or selected.get("authorization_status"),
        "parent": _album_detail(album),
        "query": {
            "scope": "album_assets",
            "limit": max(1, min(limit, 50)),
            "max_scan_albums": _bounded_max_scan(max_scan_albums),
            "max_scan_assets": _bounded_max_scan(max_scan_assets),
        },
        "results": results,
        "result_count": len(results),
        "warnings": selected["warnings"] + _safe_warnings(response),
    }


def get_photo_asset(
    handle: str,
    *,
    max_scan_assets: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_HANDLE_PREFIX):
        return _invalid_handle_result()

    response = _photos_response(
        query="",
        limit=_bounded_max_scan(max_scan_assets),
        media_type="all",
        max_scan_assets=max_scan_assets,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return _photos_degraded_result(response, detail=True)

    asset_id = _resolve_asset_id(handle, response.get("assets", []))
    if asset_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "privacy": _detail_privacy(),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = photos_runner or _run_photos_helper
    try:
        detail = _run_read_helper(
            runner,
            {"command": "photo_by_id", "asset_id": asset_id},
            PHOTOS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _detail_unavailable_result()

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "privacy": _detail_privacy(),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _photos_degraded_result(detail, detail=True)

    asset = detail.get("asset")
    if not isinstance(asset, dict):
        return _detail_unavailable_result()

    result = _asset_detail(asset)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _detail_privacy(),
        "result": result,
        "result_count": 1,
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
    }


def export_photo_asset(
    handle: str,
    *,
    output_dir: Path,
    filename: str | None = None,
    max_scan_assets: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_HANDLE_PREFIX):
        return _invalid_export_handle_result()

    response = _photos_response(
        query="",
        limit=_bounded_max_scan(max_scan_assets),
        media_type="all",
        max_scan_assets=max_scan_assets,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return _photos_export_degraded_result(response)

    asset_id = _resolve_asset_id(handle, response.get("assets", []))
    if asset_id is None:
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": _safe_warnings(response),
        }

    runner = photos_runner or _run_photos_helper
    try:
        detail = _run_read_helper(
            runner,
            {
                "command": "export_photo_by_id",
                "asset_id": asset_id,
                "output_dir": str(output_dir.expanduser()),
                "filename": filename or "",
            },
            PHOTOS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return _export_unavailable_result()

    if detail.get("status") == "not_found":
        return {
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "privacy": _export_privacy(),
            "result": None,
            "warnings": _safe_warnings(detail),
        }
    if detail.get("status") != "ok":
        return _photos_export_degraded_result(detail)

    asset = detail.get("asset")
    if not isinstance(asset, dict):
        return _export_unavailable_result()

    result = _asset_export_detail(asset)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _export_privacy(content_exported=True),
        "result": result,
        "result_count": 1,
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
    }


def plan_photo_change(
    operation: str,
    *,
    source_file: str | Path = "",
    media_type: str = "auto",
    handle: str = "",
    album_handle: str = "",
    album_title: str = "",
    new_album_title: str = "",
    favorite: bool | None = None,
    hidden: bool | None = None,
    expected_favorite: bool | None = None,
    expected_hidden: bool | None = None,
    expected_in_album: bool | None = None,
    max_scan_assets: int = DEFAULT_MAX_SCAN_ASSETS,
    max_scan_albums: int = DEFAULT_MAX_SCAN_ASSETS,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    if normalized_operation not in PLAN_OPERATIONS:
        return _preview_error(
            [
                _warning(
                    "invalid_operation",
                    "Expected operation import, update_flags, delete, add_to_album, remove_from_album, create_album, rename_album, or delete_album.",
                )
            ]
        )
    if normalized_operation == "update_flags":
        return _plan_update_flags_photo_change(
            handle=handle,
            favorite=favorite,
            hidden=hidden,
            expected_favorite=expected_favorite,
            expected_hidden=expected_hidden,
            max_scan_assets=max_scan_assets,
            photos_runner=photos_runner,
        )
    if normalized_operation == "delete":
        return _plan_delete_photo_change(
            handle=handle,
            max_scan_assets=max_scan_assets,
            photos_runner=photos_runner,
        )
    if normalized_operation in {"add_to_album", "remove_from_album"}:
        return _plan_album_membership_photo_change(
            operation=normalized_operation,
            handle=handle,
            album_handle=album_handle,
            expected_in_album=expected_in_album,
            max_scan_assets=max_scan_assets,
            max_scan_albums=max_scan_albums,
            photos_runner=photos_runner,
        )
    if normalized_operation in {"create_album", "rename_album", "delete_album"}:
        return _plan_album_management_photo_change(
            operation=normalized_operation,
            album_handle=album_handle,
            album_title=album_title,
            new_album_title=new_album_title,
            max_scan_albums=max_scan_albums,
            photos_runner=photos_runner,
        )

    source = _source_file_metadata(source_file, media_type=media_type)
    warnings: list[dict[str, str]] = []
    warnings.extend(source.pop("warnings"))
    if warnings:
        return _preview_error(warnings)

    proposed = {
        "source_filename": source["filename"],
        "source_extension": source["extension"],
        "media_type": source["media_type"],
        "file_size_bytes": source["file_size_bytes"],
        "file_sha256": source["file_sha256"],
        "asset_content_returned": False,
        "source_path_returned": False,
        "album_targeting": "blocked",
        "network_import": "blocked",
    }
    fingerprint_payload = {
        "operation": normalized_operation,
        "target": {"library": "system_photo_library"},
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": normalized_operation,
            "target": {"library": "system_photo_library"},
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def apply_photo_change(
    operation: str,
    *,
    source_file: str | Path = "",
    media_type: str = "auto",
    handle: str = "",
    album_handle: str = "",
    album_title: str = "",
    new_album_title: str = "",
    favorite: bool | None = None,
    hidden: bool | None = None,
    expected_favorite: bool | None = None,
    expected_hidden: bool | None = None,
    expected_in_album: bool | None = None,
    max_scan_assets: int = DEFAULT_MAX_SCAN_ASSETS,
    max_scan_albums: int = DEFAULT_MAX_SCAN_ASSETS,
    approval_token: str = "",
    confirm_apply: bool = False,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    plan = plan_photo_change(
        normalized_operation,
        source_file=source_file,
        media_type=media_type,
        handle=handle,
        album_handle=album_handle,
        album_title=album_title,
        new_album_title=new_album_title,
        favorite=favorite,
        hidden=hidden,
        expected_favorite=expected_favorite,
        expected_hidden=expected_hidden,
        expected_in_album=expected_in_album,
        max_scan_assets=max_scan_assets,
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if plan.get("status") != "ok":
        return _apply_error(_safe_warnings(plan), plan=plan)

    preview = plan.get("preview")
    if not isinstance(preview, dict):
        return _apply_error(
            [_warning("invalid_plan", "Photos apply requires a valid plan preview.")],
            plan=plan,
        )
    approval = preview.get("approval")
    fingerprint = approval.get("approval_fingerprint") if isinstance(approval, dict) else None
    expected_token = _approval_token(str(fingerprint or ""))
    if not confirm_apply:
        return _apply_error(
            [_warning("missing_apply_confirmation", "Photos apply requires confirm_apply=true.")],
            plan=plan,
        )
    if not approval_token.strip() or approval_token.strip() != expected_token:
        return _apply_error(
            [_warning("invalid_approval_token", "Photos apply approval token did not match the plan.")],
            plan=plan,
        )

    runner = photos_runner or _run_photos_helper
    asset_id = ""
    album_id = ""
    if normalized_operation in {"update_flags", "delete", "add_to_album", "remove_from_album"}:
        selected = _selected_asset(handle, max_scan_assets=max_scan_assets, photos_runner=photos_runner)
        if selected["status"] != "ok":
            return _apply_error(
                selected["warnings"],
                plan=plan,
                status=selected["status"],
                authorization_status=selected.get("authorization_status"),
            )
        asset_id = str(selected["asset_id"])
    if normalized_operation in {"add_to_album", "remove_from_album", "rename_album", "delete_album"}:
        selected_album = _selected_album(
            album_handle,
            max_scan_albums=max_scan_albums,
            photos_runner=photos_runner,
        )
        if selected_album["status"] != "ok":
            return _apply_error(
                selected_album["warnings"],
                plan=plan,
                status=selected_album["status"],
                authorization_status=selected_album.get("authorization_status"),
            )
        album_id = str(selected_album["album_id"])
    try:
        applied = runner(
            _apply_helper_payload(
                preview,
                source_file=source_file,
                asset_id=asset_id,
                album_id=album_id,
            ),
            PHOTOS_APPLY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("photos_apply_timeout", "Photos apply timed out through the local PhotoKit helper.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("photos_unavailable", "Photos apply is unavailable through the local PhotoKit helper.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("photos_apply_failed", "Photos change could not be applied safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            mutation_applied=bool(applied.get("mutation_applied")),
            authorization_status=applied.get("authorization_status"),
        )

    if preview["operation"] == "delete":
        if not bool(applied.get("deleted")) or not bool(applied.get("verified_absent")):
            return _apply_error(
                [
                    _warning(
                        "read_back_state_mismatch",
                        "Photos delete read-back did not prove the selected asset was absent.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": {
                "deleted": True,
                "verified_absent": True,
                "asset_content_returned": False,
                "raw_asset_identifier_returned": False,
                "recently_deleted_empty": False,
            },
            "result_count": 0,
            "warnings": _safe_warnings(applied),
        }

    if preview["operation"] in {"add_to_album", "remove_from_album"}:
        target_in_album = bool(preview["proposed"]["target_in_album"])
        if bool(applied.get("in_album")) != target_in_album:
            return _apply_error(
                [
                    _warning(
                        "read_back_state_mismatch",
                        "Photos album membership read-back did not match the approved target state.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        asset = applied.get("asset")
        album = applied.get("album")
        if not isinstance(asset, dict) or not isinstance(album, dict):
            return _apply_error(
                [_warning("read_back_unavailable", "Photos album membership read-back was unavailable.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": {
                "asset": _asset_detail(asset),
                "album": _album_detail(album),
                "in_album": target_in_album,
                "asset_content_returned": False,
                "raw_asset_identifier_returned": False,
                "raw_album_identifier_returned": False,
            },
            "result_count": 1,
            "warnings": _safe_warnings(applied),
        }

    if preview["operation"] in {"create_album", "rename_album"}:
        album = applied.get("album")
        if not isinstance(album, dict):
            return _apply_error(
                [_warning("read_back_unavailable", "Photos album management read-back was unavailable.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        expected_title = str(preview["proposed"]["album_title"])
        if _bounded_string(album.get("title"), MAX_ALBUM_TITLE_CHARS) != expected_title:
            return _apply_error(
                [_warning("read_back_state_mismatch", "Photos album read-back did not match the approved title.")],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": {
                "album": _album_detail(album),
                "raw_album_identifier_returned": False,
            },
            "result_count": 1,
            "warnings": _safe_warnings(applied),
        }

    if preview["operation"] == "delete_album":
        if not bool(applied.get("deleted")) or not bool(applied.get("verified_absent")):
            return _apply_error(
                [
                    _warning(
                        "read_back_state_mismatch",
                        "Photos album delete read-back did not prove the selected album was absent.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=True,
                authorization_status=applied.get("authorization_status"),
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "privacy": _mutation_privacy(content_inspected=False),
            "authorization_status": applied.get("authorization_status"),
            "mode": "apply",
            "operation": str(preview["operation"]),
            "mutation_applied": True,
            "apply_available": True,
            "idempotency_key": preview["idempotency_key"],
            "approval": {
                "approval_fingerprint": fingerprint,
                "approval_token_verified": True,
            },
            "read_back": {
                "deleted": True,
                "verified_absent": True,
                "raw_album_identifier_returned": False,
            },
            "result_count": 0,
            "warnings": _safe_warnings(applied),
        }

    asset = applied.get("asset")
    if not isinstance(asset, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Photos change succeeded but read-back was unavailable.")],
            plan=plan,
            status="apply_unknown",
            mutation_applied=True,
            authorization_status=applied.get("authorization_status"),
        )
    if preview["operation"] == "update_flags":
        proposed = preview["proposed"]
        if bool(asset.get("favorite")) != bool(proposed["favorite"]) or bool(asset.get("hidden")) != bool(proposed["hidden"]):
            return _apply_error(
                [
                    _warning(
                        "read_back_state_mismatch",
                        "Photos update read-back did not match the approved target state.",
                    )
                ],
                plan=plan,
                status="apply_unknown",
                mutation_applied=False,
                authorization_status=applied.get("authorization_status"),
            )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _mutation_privacy(content_inspected=False),
        "authorization_status": applied.get("authorization_status"),
        "mode": "apply",
        "operation": str(preview["operation"]),
        "mutation_applied": True,
        "apply_available": True,
        "idempotency_key": preview["idempotency_key"],
        "approval": {
            "approval_fingerprint": fingerprint,
            "approval_token_verified": True,
        },
        "read_back": _asset_detail(asset),
        "result_count": 1,
        "warnings": _safe_warnings(applied),
    }


def _photos_response(
    *,
    query: str,
    limit: int,
    media_type: str,
    max_scan_assets: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    runner = photos_runner or _run_photos_helper
    scan_limit = _bounded_max_scan(max_scan_assets)
    try:
        return _run_read_helper(
            runner,
            {
                "command": "photos",
                "query": query,
                "limit": max(1, min(limit, scan_limit)),
                "media_type": _bounded_media_type(media_type),
                "max_assets": scan_limit,
            },
            PHOTOS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "photos_timeout",
                    "Photos access timed out through the local PhotoKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "photos_unavailable",
                    "Photos access is unavailable through the local PhotoKit helper.",
                )
            ],
        }


def _photos_album_response(
    *,
    query: str,
    limit: int,
    max_scan_albums: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    runner = photos_runner or _run_photos_helper
    scan_limit = _bounded_max_scan(max_scan_albums)
    try:
        return _run_read_helper(
            runner,
            {
                "command": "photo_albums",
                "query": query,
                "limit": max(1, min(limit, scan_limit)),
                "max_albums": scan_limit,
            },
            PHOTOS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "photos_timeout",
                    "Photos album access timed out through the local PhotoKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "photos_unavailable",
                    "Photos album access is unavailable through the local PhotoKit helper.",
                )
            ],
        }


def _photo_album_assets_response(
    *,
    album_id: str,
    limit: int,
    max_scan_assets: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    runner = photos_runner or _run_photos_helper
    scan_limit = _bounded_max_scan(max_scan_assets)
    try:
        return _run_read_helper(
            runner,
            {
                "command": "photo_album_assets",
                "album_id": album_id,
                "limit": max(1, min(limit, 50)),
                "max_assets": scan_limit,
            },
            PHOTOS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "photos_timeout",
                    "Photos album asset access timed out through the local PhotoKit helper.",
                )
            ],
        }
    except (OSError, ValueError):
        return {
            "status": "degraded",
            "warnings": [
                _warning(
                    "photos_unavailable",
                    "Photos album asset access is unavailable through the local PhotoKit helper.",
                )
            ],
        }


def _run_read_helper(
    runner: PhotosRunner,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Run a READ-only Photos helper call, retrying once on a cold-start timeout.

    The first call after auth/reboot can exceed the timeout while PhotoKit warms
    its cache; the second call is warm and fast. Only timeouts are retried, and
    only for read operations — apply/mutation paths call the runner directly so a
    timeout there surfaces as degraded without a second mutation attempt. The
    graceful helper `emit` guarantees a timed-out run never crashes.
    """

    try:
        return runner(payload, timeout)
    except subprocess.TimeoutExpired:
        return runner(payload, timeout)


def _run_photos_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    app_root = _ensure_photos_helper_app()
    opener = shutil.which("open") or "/usr/bin/open"
    with tempfile.TemporaryDirectory(prefix="local-apple-data-photos-") as directory:
        os.chmod(directory, 0o700)
        input_path = Path(directory) / "input.json"
        output_path = Path(directory) / "output.json"
        input_fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(input_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
        output_fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(output_fd)
        completed = subprocess.run(
            [
                opener,
                "-W",
                "-n",
                str(app_root),
                "--args",
                "--input-json-file",
                str(input_path),
                "--output-json-file",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError("Photos helper app failed.")
        output_text = output_path.read_text()
        if not output_text:
            raise ValueError("Photos helper app returned no output.")
        parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("Photos helper returned invalid JSON.")
    return parsed


def _run_photos_helper_script(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        ["swift", str(PHOTOS_HELPER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("Photos helper failed.")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("Photos helper returned invalid JSON.")
    return parsed


def _photos_helper_app_root() -> Path:
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "local-apple-data"
        / "PhotosHelper.app"
    )


def _photos_helper_source_digest() -> str:
    return hashlib.sha256(PHOTOS_HELPER.read_bytes()).hexdigest()


def _photos_helper_info_plist() -> dict[str, Any]:
    return {
        "CFBundleExecutable": "photos_helper",
        "CFBundleIdentifier": _photos_helper_bundle_id(),
        "CFBundleName": "Local Apple Data Photos Helper",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "11.0",
        "NSPhotoLibraryUsageDescription": (
            "Allow local-apple-data to read local Photos metadata only when explicitly requested."
        ),
        "NSPhotoLibraryAddUsageDescription": (
            "Allow local-apple-data to write local Photos only after explicit approval."
        ),
    }


def _photos_helper_entitlements() -> dict[str, bool]:
    return {
        "com.apple.security.personal-information.photos-library": True,
    }


def _provision_local_signing_identity() -> str | None:
    """Provision the shared local self-signed identity if none exists.

    Idempotent and non-raising; see adapters._signing. Reused across the
    EventKit and Photos helpers so a single conventional identity signs both.
    """
    return _signing.provision_local_signing_identity()


def _prepare_photos_helper_signing() -> None:
    """Provision a stable identity and invalidate a stale-signed helper app.

    Invoked only from the request-access path (never from read/mutation paths).
    Ensures the Photos helper is rebuilt stably signed before the prompt so the
    PhotoKit grant survives rebuilds instead of churning with an ad-hoc cdhash.
    Non-raising.
    """
    try:
        identity = _provision_local_signing_identity()
        _signing.invalidate_app_if_signing_mismatch(
            _photos_helper_app_root(), identity
        )
    except (OSError, ValueError):
        return


def _ensure_photos_helper_app() -> Path:
    app_root = _photos_helper_app_root()
    digest = _photos_helper_source_digest()
    if _photos_helper_app_valid(app_root, digest):
        return app_root

    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise ValueError("Photos helper compiler unavailable.")
    codesign = shutil.which("codesign")
    if not codesign:
        raise ValueError("Photos helper signer unavailable.")

    parent = app_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    staging_root = Path(tempfile.mkdtemp(prefix=".PhotosHelper.", dir=parent))
    staged_app = staging_root / "PhotosHelper.app"
    contents = staged_app / "Contents"
    executable = contents / "MacOS" / "photos_helper"
    digest_file = contents / "Resources" / "source.sha256"
    entitlements_file = contents / "Resources" / "entitlements.plist"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(_photos_helper_info_plist(), handle)
    with entitlements_file.open("wb") as handle:
        plistlib.dump(_photos_helper_entitlements(), handle)
    digest_file.write_text(digest)
    completed = subprocess.run(
        [swiftc, str(PHOTOS_HELPER), "-o", str(executable)],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ValueError("Photos helper app build failed.")

    # Stable identity + hardened runtime + photos-library entitlement so the TCC
    # prompt presents and the grant survives rebuilds; falls back to ad-hoc when
    # a resolved stable identity is unusable (locked keychain, missing/duplicate
    # key, unrelated leftover cert) so the helper still builds for reads.
    sign = _signing.sign_helper_app(codesign, entitlements_file, staged_app)
    if sign.returncode != 0 or not _photos_helper_app_valid(staged_app, digest):
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ValueError("Photos helper app signing failed.")

    if app_root.is_symlink() or app_root.is_file():
        app_root.unlink()
    elif app_root.exists():
        shutil.rmtree(app_root)
    staged_app.rename(app_root)
    shutil.rmtree(staging_root, ignore_errors=True)
    return app_root


def _photos_helper_app_valid(app_root: Path, digest: str) -> bool:
    contents = app_root / "Contents"
    executable = contents / "MacOS" / "photos_helper"
    digest_file = contents / "Resources" / "source.sha256"
    info_plist = contents / "Info.plist"
    entitlements_file = contents / "Resources" / "entitlements.plist"
    if not executable.is_file() or not digest_file.is_file() or not info_plist.is_file():
        return False
    try:
        if digest_file.read_text().strip() != digest:
            return False
        with info_plist.open("rb") as handle:
            if plistlib.load(handle) != _photos_helper_info_plist():
                return False
        with entitlements_file.open("rb") as handle:
            if plistlib.load(handle) != _photos_helper_entitlements():
                return False
    except (OSError, plistlib.InvalidFileException):
        return False

    codesign = shutil.which("codesign")
    if not codesign:
        return False
    verified = subprocess.run(
        [codesign, "--verify", "--deep", "--strict", str(app_root)],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if verified.returncode != 0:
        return False
    entitlements = subprocess.run(
        [codesign, "-d", "--entitlements", ":-", str(app_root)],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return (
        entitlements.returncode == 0
        and "com.apple.security.personal-information.photos-library" in entitlements.stdout
    )


def _plan_update_flags_photo_change(
    *,
    handle: str,
    favorite: bool | None,
    hidden: bool | None,
    expected_favorite: bool | None,
    expected_hidden: bool | None,
    max_scan_assets: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    if favorite is None and hidden is None:
        warnings.append(_warning("missing_target_flags", "Photos update_flags requires favorite or hidden."))
    if expected_favorite is None or expected_hidden is None:
        warnings.append(
            _warning(
                "missing_expected_state",
                "Photos update_flags requires expected_favorite and expected_hidden.",
            )
        )
    if not is_opaque_handle(handle, PHOTO_HANDLE_PREFIX):
        warnings.append(_warning("invalid_handle", "Expected photos:asset:v1 opaque handle from search output."))
    if warnings:
        return _preview_error(warnings)
    selected = _selected_asset(handle, max_scan_assets=max_scan_assets, photos_runner=photos_runner)
    if selected["status"] != "ok":
        warnings.extend(
            selected["warnings"]
            or [_warning("photo_asset_not_found", "Selected Photos asset was not found.")]
        )
    if warnings:
        return _preview_error(warnings)

    asset = selected["asset"]
    current_favorite = bool(asset.get("favorite"))
    current_hidden = bool(asset.get("hidden"))
    if current_favorite != expected_favorite or current_hidden != expected_hidden:
        return _preview_error(
            [
                _warning(
                    "expected_state_mismatch",
                    "Current Photos asset favorite/hidden state did not match expected state.",
                )
            ]
        )

    proposed = {
        "favorite": current_favorite if favorite is None else bool(favorite),
        "hidden": current_hidden if hidden is None else bool(hidden),
        "asset_content_returned": False,
        "raw_asset_identifier_returned": False,
    }
    target = {
        "handle": handle,
        "expected_favorite": current_favorite,
        "expected_hidden": current_hidden,
    }
    fingerprint_payload = {
        "operation": "update_flags",
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _preview_privacy(),
        "authorization_status": selected.get("authorization_status"),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "update_flags",
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_delete_photo_change(
    *,
    handle: str,
    max_scan_assets: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_HANDLE_PREFIX):
        return _preview_error([_warning("invalid_handle", "Expected photos:asset:v1 opaque handle from search output.")])
    selected = _selected_asset(handle, max_scan_assets=max_scan_assets, photos_runner=photos_runner)
    if selected["status"] != "ok":
        return _preview_error(
            selected["warnings"]
            or [_warning("photo_asset_not_found", "Selected Photos asset was not found.")]
        )

    asset = selected["asset"]
    expected_state = _asset_delete_expected_state(asset)
    delete_safe_sha256 = _asset_state_sha256(asset)
    target = {
        "handle": handle,
        "delete_safe_sha256": delete_safe_sha256,
        "expected_state": expected_state,
        "asset_content_returned": False,
        "raw_asset_identifier_returned": False,
    }
    proposed = {
        "delete_asset": True,
        "delete_scope": "library_asset",
        "album_only_removal": "blocked",
        "permanent_delete": "blocked",
        "recently_deleted_empty": "blocked",
        "asset_content_returned": False,
        "raw_asset_identifier_returned": False,
    }
    fingerprint_payload = {
        "operation": "delete",
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _preview_privacy(),
        "authorization_status": selected.get("authorization_status"),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": "delete",
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_album_membership_photo_change(
    *,
    operation: str,
    handle: str,
    album_handle: str,
    expected_in_album: bool | None,
    max_scan_assets: int,
    max_scan_albums: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    if not is_opaque_handle(handle, PHOTO_HANDLE_PREFIX):
        warnings.append(_warning("invalid_handle", "Expected photos:asset:v1 opaque handle from search output."))
    if not is_opaque_handle(album_handle, PHOTO_ALBUM_HANDLE_PREFIX):
        warnings.append(_warning("invalid_album_handle", "Expected photos:album:v1 opaque handle from album output."))
    if expected_in_album is None:
        warnings.append(_warning("missing_expected_membership", "Photos album membership requires expected_in_album."))
    if warnings:
        return _preview_error(warnings)

    selected = _selected_asset(handle, max_scan_assets=max_scan_assets, photos_runner=photos_runner)
    if selected["status"] != "ok":
        return _preview_error(
            selected["warnings"]
            or [_warning("photo_asset_not_found", "Selected Photos asset was not found.")]
        )
    selected_album = _selected_album(
        album_handle,
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if selected_album["status"] != "ok":
        return _preview_error(
            selected_album["warnings"]
            or [_warning("photo_album_not_found", "Selected Photos album was not found.")]
        )

    album = selected_album["album"]
    if operation == "add_to_album" and not bool(album.get("can_add_content")):
        return _preview_error([_warning("photos_album_add_not_supported", "Selected Photos album does not allow adding assets.")])
    if operation == "remove_from_album" and not bool(album.get("can_remove_content")):
        return _preview_error([_warning("photos_album_remove_not_supported", "Selected Photos album does not allow removing assets.")])

    membership = _photo_album_membership(
        asset_id=str(selected["asset_id"]),
        album_id=str(selected_album["album_id"]),
        photos_runner=photos_runner,
    )
    if membership["status"] != "ok":
        return _preview_error(
            membership["warnings"]
            or [_warning("photos_album_membership_unavailable", "Photos album membership could not be read safely.")]
        )
    current_in_album = bool(membership["in_album"])
    if current_in_album != expected_in_album:
        return _preview_error(
            [
                _warning(
                    "expected_membership_mismatch",
                    "Current Photos album membership did not match expected state.",
                )
            ]
        )
    if operation == "add_to_album" and current_in_album:
        return _preview_error([_warning("already_in_album", "Selected Photos asset is already in the selected album.")])
    if operation == "remove_from_album" and not current_in_album:
        return _preview_error([_warning("not_in_album", "Selected Photos asset is not in the selected album.")])

    asset = selected["asset"]
    target_in_album = operation == "add_to_album"
    target = {
        "handle": handle,
        "album_handle": album_handle,
        "expected_in_album": current_in_album,
        "asset_safe_sha256": _asset_state_sha256(asset),
        "album_safe_sha256": _album_state_sha256(album),
        "expected_asset_state": _asset_delete_expected_state(asset),
        "expected_album_state": _album_expected_state(album),
        "asset_content_returned": False,
        "raw_asset_identifier_returned": False,
        "raw_album_identifier_returned": False,
    }
    proposed = {
        "album_membership": "add" if target_in_album else "remove",
        "target_in_album": target_in_album,
        "asset_delete": "blocked",
        "album_create_delete": "blocked",
        "bulk_membership": "blocked",
        "asset_content_returned": False,
        "raw_asset_identifier_returned": False,
        "raw_album_identifier_returned": False,
    }
    fingerprint_payload = {
        "operation": operation,
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _preview_privacy(),
        "authorization_status": selected.get("authorization_status") or selected_album.get("authorization_status"),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _plan_album_management_photo_change(
    *,
    operation: str,
    album_handle: str,
    album_title: str,
    new_album_title: str,
    max_scan_albums: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    if operation == "create_album":
        title, warnings = _normalized_album_title(album_title, field_name="album_title")
        if warnings:
            return _preview_error(warnings)
        duplicate = _find_album_by_exact_title(
            title,
            max_scan_albums=max_scan_albums,
            photos_runner=photos_runner,
        )
        if duplicate["status"] != "ok":
            return _preview_error(duplicate["warnings"])
        access_warning = _full_photos_access_warning(duplicate.get("authorization_status"))
        if access_warning is not None:
            return _preview_error([access_warning], authorization_status=duplicate.get("authorization_status"))
        if duplicate["album"] is not None:
            return _preview_error(
                [_warning("duplicate_album_title", "A Photos album with the requested title already exists.")]
            )
        target = {
            "library": "system_photo_library",
            "album_title": title,
            "regular_album": True,
            "raw_album_identifier_returned": False,
        }
        proposed = {
            "album_title": title,
            "album_create": True,
            "album_rename": "blocked",
            "album_delete": "blocked",
            "smart_shared_synced_album": "blocked",
            "raw_album_identifier_returned": False,
        }
        authorization_status = duplicate.get("authorization_status")
    else:
        if not is_opaque_handle(album_handle, PHOTO_ALBUM_HANDLE_PREFIX):
            return _preview_error(
                [_warning("invalid_album_handle", "Expected photos:album:v1 opaque handle from album output.")]
            )
        selected_album = _selected_album(
            album_handle,
            max_scan_albums=max_scan_albums,
            photos_runner=photos_runner,
        )
        if selected_album["status"] != "ok":
            return _preview_error(
                selected_album["warnings"]
                or [_warning("photo_album_not_found", "Selected Photos album was not found.")]
            )
        access_warning = _full_photos_access_warning(selected_album.get("authorization_status"))
        if access_warning is not None:
            return _preview_error([access_warning], authorization_status=selected_album.get("authorization_status"))
        album = selected_album["album"]
        current_title = _bounded_string(album.get("title"), MAX_ALBUM_TITLE_CHARS)
        expected_state = _album_expected_state(album)
        target = {
            "album_handle": album_handle,
            "album_safe_sha256": _album_state_sha256(album),
            "expected_album_state": expected_state,
            "regular_album": True,
            "raw_album_identifier_returned": False,
        }
        authorization_status = selected_album.get("authorization_status")
        if operation == "rename_album":
            title, warnings = _normalized_album_title(
                new_album_title,
                field_name="new_album_title",
            )
            if warnings:
                return _preview_error(warnings)
            if title == current_title:
                return _preview_error([_warning("no_op_album_rename", "Photos album rename requires a new title.")])
            if not bool(album.get("can_rename")):
                return _preview_error([_warning("photos_album_rename_not_supported", "Selected Photos album does not allow renaming.")])
            duplicate = _find_album_by_exact_title(
                title,
                max_scan_albums=max_scan_albums,
                photos_runner=photos_runner,
            )
            if duplicate["status"] != "ok":
                return _preview_error(duplicate["warnings"])
            if duplicate["album"] is not None:
                return _preview_error(
                    [_warning("duplicate_album_title", "A Photos album with the requested title already exists.")]
                )
            proposed = {
                "album_title": title,
                "previous_album_title": current_title,
                "album_create": "blocked",
                "album_rename": True,
                "album_delete": "blocked",
                "raw_album_identifier_returned": False,
            }
        else:
            if not bool(album.get("can_delete")):
                return _preview_error([_warning("photos_album_delete_not_supported", "Selected Photos album does not allow deletion.")])
            if _int_value(album.get("asset_count")) != 0:
                return _preview_error([_warning("non_empty_album_blocked", "Photos album delete is limited to empty regular albums.")])
            proposed = {
                "album_title": current_title,
                "album_create": "blocked",
                "album_rename": "blocked",
                "album_delete": True,
                "non_empty_album_delete": "blocked",
                "raw_album_identifier_returned": False,
            }

    fingerprint_payload = {
        "operation": operation,
        "target": target,
        "proposed": proposed,
    }
    idempotency_key = _plan_idempotency_key(fingerprint_payload)
    approval_fingerprint = _approval_fingerprint(
        {
            **fingerprint_payload,
            "idempotency_key": idempotency_key,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "privacy": _preview_privacy(),
        "authorization_status": authorization_status,
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": {
            "operation": operation,
            "target": target,
            "proposed": proposed,
            "idempotency_key": idempotency_key,
            "approval": {
                "required_for_apply": True,
                "apply_tool_available": True,
                "approval_fingerprint": approval_fingerprint,
                "approval_token_format": f"{APPROVAL_TOKEN_PREFIX}<approval_fingerprint>",
            },
            "read_back_required_after_apply": True,
        },
        "result_count": 1,
        "warnings": [],
    }


def _selected_asset(
    handle: str,
    *,
    max_scan_assets: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_HANDLE_PREFIX):
        return {
            "status": "error",
            "asset": None,
            "asset_id": "",
            "warnings": [
                _warning("invalid_handle", "Expected photos:asset:v1 opaque handle from search output.")
            ],
        }
    response = _photos_response(
        query="",
        limit=_bounded_max_scan(max_scan_assets),
        media_type="all",
        max_scan_assets=max_scan_assets,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return {
            "status": "degraded",
            "asset": None,
            "asset_id": "",
            "authorization_status": response.get("authorization_status"),
            "warnings": _safe_warnings(response),
        }
    asset_id = _resolve_asset_id(handle, response.get("assets", []))
    if asset_id is None:
        return {
            "status": "not_found",
            "asset": None,
            "asset_id": "",
            "warnings": [_warning("photo_asset_not_found", "Selected Photos asset was not found.")],
        }
    runner = photos_runner or _run_photos_helper
    try:
        detail = _run_read_helper(
            runner,
            {"command": "photo_by_id", "asset_id": asset_id},
            PHOTOS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return {
            "status": "detail_unavailable",
            "asset": None,
            "asset_id": asset_id,
            "warnings": [_warning("photos_read_error", "Photo asset details could not be read safely.")],
        }
    if detail.get("status") == "not_found":
        return {
            "status": "not_found",
            "asset": None,
            "asset_id": "",
            "warnings": [_warning("photo_asset_not_found", "Selected Photos asset was not found.")],
        }
    if detail.get("status") != "ok":
        return {
            "status": str(detail.get("status") or "degraded"),
            "asset": None,
            "asset_id": asset_id,
            "authorization_status": detail.get("authorization_status"),
            "warnings": _safe_warnings(detail),
        }
    asset = detail.get("asset")
    if not isinstance(asset, dict):
        return {
            "status": "detail_unavailable",
            "asset": None,
            "asset_id": asset_id,
            "warnings": [_warning("photos_read_error", "Photo asset details could not be read safely.")],
        }
    return {
        "status": "ok",
        "asset": asset,
        "asset_id": asset_id,
        "authorization_status": detail.get("authorization_status"),
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
    }


def _selected_album(
    handle: str,
    *,
    max_scan_albums: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PHOTO_ALBUM_HANDLE_PREFIX):
        return {
            "status": "error",
            "album": None,
            "album_id": "",
            "warnings": [
                _warning("invalid_album_handle", "Expected photos:album:v1 opaque handle from album output.")
            ],
        }
    response = _photos_album_response(
        query="",
        limit=_bounded_max_scan(max_scan_albums),
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return {
            "status": "degraded",
            "album": None,
            "album_id": "",
            "authorization_status": response.get("authorization_status"),
            "warnings": _safe_warnings(response),
        }
    album_id = _resolve_album_id(handle, response.get("albums", []))
    if album_id is None:
        return {
            "status": "not_found",
            "album": None,
            "album_id": "",
            "warnings": _safe_warnings(response)
            + [_warning("photo_album_not_found", "Selected Photos album was not found.")],
        }
    runner = photos_runner or _run_photos_helper
    try:
        detail = _run_read_helper(
            runner,
            {"command": "photo_album_by_id", "album_id": album_id},
            PHOTOS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return {
            "status": "detail_unavailable",
            "album": None,
            "album_id": album_id,
            "warnings": [_warning("photos_read_error", "Photo album details could not be read safely.")],
        }
    if detail.get("status") == "not_found":
        return {
            "status": "not_found",
            "album": None,
            "album_id": "",
            "warnings": _safe_warnings(response)
            + _safe_warnings(detail)
            + [_warning("photo_album_not_found", "Selected Photos album was not found.")],
        }
    if detail.get("status") != "ok":
        return {
            "status": str(detail.get("status") or "degraded"),
            "album": None,
            "album_id": album_id,
            "authorization_status": detail.get("authorization_status"),
            "warnings": _safe_warnings(detail),
        }
    album = detail.get("album")
    if not isinstance(album, dict):
        return {
            "status": "detail_unavailable",
            "album": None,
            "album_id": album_id,
            "warnings": [_warning("photos_read_error", "Photo album details could not be read safely.")],
        }
    return {
        "status": "ok",
        "album": album,
        "album_id": album_id,
        "authorization_status": detail.get("authorization_status"),
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
    }


def _photo_album_membership(
    *,
    asset_id: str,
    album_id: str,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    runner = photos_runner or _run_photos_helper
    try:
        response = _run_read_helper(
            runner,
            {
                "command": "photo_album_membership",
                "asset_id": asset_id,
                "album_id": album_id,
            },
            PHOTOS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return {
            "status": "detail_unavailable",
            "in_album": False,
            "warnings": [_warning("photos_read_error", "Photo album membership could not be read safely.")],
        }
    return {
        "status": str(response.get("status") or "degraded"),
        "authorization_status": response.get("authorization_status"),
        "in_album": bool(response.get("in_album")),
        "warnings": _safe_warnings(response),
    }


def _asset_metadata(asset: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(asset.get("asset_id") or "")
    return {
        "handle": make_opaque_handle(PHOTO_HANDLE_PREFIX, asset_id),
        "media_type": asset.get("media_type"),
        "media_subtypes": _int_value(asset.get("media_subtypes")),
        "pixel_width": _int_value(asset.get("pixel_width")),
        "pixel_height": _int_value(asset.get("pixel_height")),
        "duration": _float_value(asset.get("duration")),
        "favorite": bool(asset.get("favorite")),
        "hidden": bool(asset.get("hidden")),
        "source_type": _int_value(asset.get("source_type")),
        "creation_date": _bounded_string(asset.get("creation_date"), 100),
        "modification_date": _bounded_string(asset.get("modification_date"), 100),
        "primary_filename": _bounded_string(asset.get("primary_filename"), 500),
        "resource_count": _int_value(asset.get("resource_count")),
        "asset_content_returned": False,
    }


def _asset_detail(asset: dict[str, Any]) -> dict[str, Any]:
    result = _asset_metadata(asset)
    result["resources"] = _bounded_payload(asset.get("resources"))
    return result


def _album_metadata(album: dict[str, Any]) -> dict[str, Any]:
    album_id = str(album.get("album_id") or "")
    return {
        "handle": make_opaque_handle(PHOTO_ALBUM_HANDLE_PREFIX, album_id),
        "title": _bounded_string(album.get("title"), 500),
        "asset_collection_type": _int_value(album.get("asset_collection_type")),
        "asset_collection_subtype": _int_value(album.get("asset_collection_subtype")),
        "estimated_asset_count": _int_value(album.get("estimated_asset_count")),
        "asset_count": _int_value(album.get("asset_count")),
        "can_add_content": bool(album.get("can_add_content")),
        "can_remove_content": bool(album.get("can_remove_content")),
        "can_rename": bool(album.get("can_rename")),
        "can_delete": bool(album.get("can_delete")),
        "raw_album_identifier_returned": False,
    }


def _album_detail(album: dict[str, Any]) -> dict[str, Any]:
    return _album_metadata(album)


def _asset_export_detail(asset: dict[str, Any]) -> dict[str, Any]:
    result = _asset_detail(asset)
    result["asset_content_exported"] = bool(asset.get("asset_content_exported"))
    result["exported_path"] = _bounded_string(asset.get("exported_path"), 1000)
    result["exported_filename"] = _bounded_string(asset.get("exported_filename"), 500)
    result["exported_bytes"] = _int_value(asset.get("exported_bytes"))
    return result


def _asset_state_sha256(asset: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(_asset_delete_expected_state(asset)).encode("utf-8")
    ).hexdigest()


def _asset_delete_expected_state(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "media_type": asset.get("media_type"),
        "media_subtypes": _int_value(asset.get("media_subtypes")),
        "pixel_width": _int_value(asset.get("pixel_width")),
        "pixel_height": _int_value(asset.get("pixel_height")),
        "duration": _float_value(asset.get("duration")),
        "favorite": bool(asset.get("favorite")),
        "hidden": bool(asset.get("hidden")),
        "source_type": _int_value(asset.get("source_type")),
        "creation_date": _bounded_string(asset.get("creation_date"), 100),
        "modification_date": _bounded_string(asset.get("modification_date"), 100),
        "primary_filename": _bounded_string(asset.get("primary_filename"), 500),
        "resource_count": _int_value(asset.get("resource_count")),
    }


def _album_state_sha256(album: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(_album_expected_state(album)).encode("utf-8")
    ).hexdigest()


def _album_expected_state(album: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _bounded_string(album.get("title"), 500),
        "asset_collection_type": _int_value(album.get("asset_collection_type")),
        "asset_collection_subtype": _int_value(album.get("asset_collection_subtype")),
        "asset_count": _int_value(album.get("asset_count")),
        "can_add_content": bool(album.get("can_add_content")),
        "can_remove_content": bool(album.get("can_remove_content")),
    }


def _resolve_asset_id(handle: str, assets: Any) -> str | None:
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or "")
        if asset_id and opaque_handle_matches(handle, PHOTO_HANDLE_PREFIX, asset_id):
            return asset_id
    return None


def _resolve_album_id(handle: str, albums: Any) -> str | None:
    if not isinstance(albums, list):
        return None
    for album in albums:
        if not isinstance(album, dict):
            continue
        album_id = str(album.get("album_id") or "")
        if album_id and opaque_handle_matches(handle, PHOTO_ALBUM_HANDLE_PREFIX, album_id):
            return album_id
    return None


def _find_album_by_exact_title(
    title: str,
    *,
    max_scan_albums: int,
    photos_runner: PhotosRunner | None,
) -> dict[str, Any]:
    response = _photos_album_response(
        query=title,
        limit=_bounded_max_scan(max_scan_albums),
        max_scan_albums=max_scan_albums,
        photos_runner=photos_runner,
    )
    if response.get("status") != "ok":
        return {
            "status": "degraded",
            "album": None,
            "authorization_status": response.get("authorization_status"),
            "warnings": _safe_warnings(response),
        }
    for album in response.get("albums", []):
        if isinstance(album, dict) and _bounded_string(album.get("title"), MAX_ALBUM_TITLE_CHARS) == title:
            return {
                "status": "ok",
                "album": album,
                "authorization_status": response.get("authorization_status"),
                "warnings": _safe_warnings(response),
            }
    warnings = _safe_warnings(response)
    if any(warning.get("code") in {"scan_truncated", "result_truncated"} for warning in warnings):
        return {
            "status": "degraded",
            "album": None,
            "authorization_status": response.get("authorization_status"),
            "warnings": warnings
            + [
                _warning(
                    "album_title_scan_truncated",
                    "Photos album title uniqueness could not be proven within the scan limit.",
                )
            ],
        }
    return {
        "status": "ok",
        "album": None,
        "authorization_status": response.get("authorization_status"),
        "warnings": warnings,
    }


def _normalized_album_title(title: str, *, field_name: str) -> tuple[str, list[dict[str, str]]]:
    normalized = _bounded_string(title, MAX_ALBUM_TITLE_CHARS).strip()
    if not normalized:
        return "", [_warning("missing_album_title", f"Photos {field_name} is required.")]
    if normalized != title.strip():
        return "", [_warning("album_title_too_long", "Photos album title is too long.")]
    return normalized, []


def _full_photos_access_warning(authorization_status: Any) -> dict[str, str] | None:
    if str(authorization_status or "") == "authorized":
        return None
    return _warning(
        "photos_full_access_required",
        "Photos album management requires full Photos Library access.",
    )


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _detail_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected photos:asset:v1 opaque handle from search output.",
            )
        ],
    }


def _invalid_album_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _detail_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_album_handle",
                "Expected photos:album:v1 opaque handle from album output.",
            )
        ],
    }


def _invalid_album_asset_list_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _privacy(),
        "parent": None,
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "invalid_album_handle",
                "Expected photos:album:v1 opaque handle from album output.",
            )
        ],
    }


def _invalid_export_handle_result() -> dict[str, Any]:
    result = _invalid_handle_result()
    result["privacy"] = _export_privacy()
    return result


def _preview_error(warnings: list[dict[str, str]], *, authorization_status: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "privacy": _preview_privacy(),
        "mode": "plan",
        "mutation_applied": False,
        "apply_available": True,
        "preview": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _apply_error(
    warnings: list[dict[str, str]],
    *,
    plan: dict[str, Any] | None,
    status: str = "error",
    mutation_applied: bool = False,
    authorization_status: Any = None,
) -> dict[str, Any]:
    preview = plan.get("preview") if isinstance(plan, dict) else None
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "photos",
        "privacy": _mutation_privacy(content_inspected=False),
        "mode": "apply",
        "mutation_applied": mutation_applied,
        "apply_available": True,
        "preview": preview if isinstance(preview, dict) else None,
        "read_back": None,
        "result_count": 0,
        "warnings": warnings,
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _photos_degraded_result(response: dict[str, Any], *, detail: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "photos",
        "privacy": _detail_privacy() if detail else _privacy(),
        "authorization_status": response.get("authorization_status"),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": _safe_warnings(response),
    }


def _photos_album_degraded_result(response: dict[str, Any], *, detail: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "photos",
        "privacy": _detail_privacy() if detail else _privacy(),
        "authorization_status": response.get("authorization_status"),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": _safe_warnings(response),
    }


def _album_asset_list_error(
    *,
    status: str,
    authorization_status: Any = None,
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "source": "photos",
        "privacy": _privacy(),
        "parent": None,
        "results": [],
        "result_count": 0,
        "warnings": warnings or [],
    }
    if authorization_status is not None:
        payload["authorization_status"] = authorization_status
    return payload


def _album_detail_unavailable_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "detail_unavailable",
        "source": "photos",
        "privacy": _detail_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "photos_read_error",
                "Photo album details could not be read safely.",
            )
        ],
    }


def _photos_export_degraded_result(response: dict[str, Any]) -> dict[str, Any]:
    asset = response.get("asset")
    return {
        "schema_version": 1,
        "status": response.get("status") if response.get("status") else "export_unavailable",
        "source": "photos",
        "privacy": _export_privacy(),
        "authorization_status": response.get("authorization_status"),
        "result": _asset_detail(asset) if isinstance(asset, dict) else None,
        "result_count": 1 if isinstance(asset, dict) else 0,
        "warnings": _safe_warnings(response),
    }


def _detail_unavailable_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "detail_unavailable",
        "source": "photos",
        "privacy": _detail_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "photos_read_error",
                "Photo asset details could not be read safely.",
            )
        ],
    }


def _export_unavailable_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "export_unavailable",
        "source": "photos",
        "privacy": _export_privacy(),
        "result": None,
        "warnings": [
            _warning(
                "photos_export_failed",
                "Photo asset could not be exported safely.",
            )
        ],
    }


def _safe_warnings(response: dict[str, Any]) -> list[dict[str, str]]:
    return safe_warning_payloads(
        response,
        _warning,
        fallback_message="Photos warning detail was redacted.",
    )


def _bounded_media_type(value: str) -> str:
    media_type = value.strip().lower()
    return media_type if media_type in {"all", "image", "video", "audio"} else "all"


def _bounded_max_scan(value: int) -> int:
    return max(1, min(value, 10000))


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _float_value(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _bounded_string(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text[:max(1, min(max_chars, 1000))]


def _bounded_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _bounded_string(value, 1000)
    if isinstance(value, list):
        return [_bounded_payload(item) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key)[:100]: _bounded_payload(item)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, bool | int | float) or value is None:
        return value
    return _bounded_string(value, 1000)


def _source_file_metadata(source_file: str | Path, *, media_type: str) -> dict[str, Any]:
    path = Path(source_file).expanduser() if source_file else Path()
    warnings: list[dict[str, str]] = []
    if not source_file:
        return {"warnings": [_warning("missing_source_file", "Photos import requires source_file.")]}
    try:
        if path.is_symlink():
            warnings.append(_warning("symlink_source_blocked", "Photos import source_file cannot be a symlink."))
        if not path.exists():
            warnings.append(_warning("source_file_unavailable", "Photos import source_file is unavailable."))
        elif not path.is_file():
            warnings.append(_warning("source_file_unavailable", "Photos import source_file must be a regular file."))
        stat = path.stat() if path.exists() else None
    except OSError:
        stat = None
        warnings.append(_warning("source_file_unavailable", "Photos import source_file is unavailable."))

    normalized_media_type, media_warning = _normalize_import_media_type(path, media_type)
    if media_warning is not None:
        warnings.append(media_warning)

    if stat is not None:
        if stat.st_size <= 0:
            warnings.append(_warning("empty_source_file", "Photos import source_file cannot be empty."))
        if stat.st_size > MAX_IMPORT_BYTES:
            warnings.append(_warning("source_file_too_large", "Photos import source_file exceeds the maximum size."))

    filename = path.name[:MAX_PREVIEW_FILENAME_CHARS] if path.name else ""
    if not filename:
        warnings.append(_warning("missing_source_filename", "Photos import source_file must have a filename."))

    if warnings:
        return {"warnings": warnings}

    try:
        file_sha256 = _file_sha256(path)
    except OSError:
        return {"warnings": [_warning("source_file_unavailable", "Photos import source_file is unreadable.")]}

    return {
        "warnings": [],
        "filename": filename,
        "extension": path.suffix.lower(),
        "media_type": normalized_media_type,
        "file_size_bytes": int(stat.st_size) if stat is not None else 0,
        "file_sha256": file_sha256,
    }


def _normalize_import_media_type(path: Path, requested: str) -> tuple[str, dict[str, str] | None]:
    normalized = requested.strip().lower() if requested else "auto"
    if normalized not in {"auto", "image", "video"}:
        return "", _warning("invalid_media_type", "Photos import media_type must be auto, image, or video.")

    inferred = _infer_media_type(path)
    if inferred is None:
        return "", _warning("unsupported_media_type", "Photos import supports common image and video files only.")
    if normalized != "auto" and normalized != inferred:
        return "", _warning("media_type_mismatch", "Photos import media_type does not match source_file extension.")
    return inferred, None


def _infer_media_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_helper_payload(
    preview: dict[str, Any],
    *,
    source_file: str | Path,
    asset_id: str = "",
    album_id: str = "",
) -> dict[str, Any]:
    proposed = preview["proposed"]
    if preview["operation"] == "update_flags":
        target = preview["target"]
        return {
            "command": "photos_update_flags",
            "asset_id": asset_id,
            "expected_favorite": target["expected_favorite"],
            "expected_hidden": target["expected_hidden"],
            "favorite": proposed["favorite"],
            "hidden": proposed["hidden"],
        }
    if preview["operation"] == "delete":
        target = preview["target"]
        return {
            "command": "photos_delete_asset",
            "asset_id": asset_id,
            "expected_state": target["expected_state"],
        }
    if preview["operation"] in {"add_to_album", "remove_from_album"}:
        target = preview["target"]
        return {
            "command": "photos_album_membership",
            "operation": preview["operation"],
            "asset_id": asset_id,
            "album_id": album_id,
            "expected_asset_state": target["expected_asset_state"],
            "expected_album_state": target["expected_album_state"],
            "expected_in_album": target["expected_in_album"],
        }
    if preview["operation"] in {"create_album", "rename_album", "delete_album"}:
        target = preview["target"]
        proposed = preview["proposed"]
        return {
            "command": "photos_album_management",
            "operation": preview["operation"],
            "album_id": album_id,
            "album_title": proposed["album_title"],
            "expected_album_state": target.get("expected_album_state", {}),
        }
    return {
        "command": "photos_apply_change",
        "operation": preview["operation"],
        "source_file": str(Path(source_file).expanduser()),
        "media_type": proposed["media_type"],
        "expected_filename": proposed["source_filename"],
        "expected_file_size_bytes": proposed["file_size_bytes"],
        "expected_file_sha256": proposed["file_sha256"],
    }


def _plan_idempotency_key(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]
    return f"photos-plan:v1:{digest}"


def _approval_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _approval_token(fingerprint: str) -> str:
    return f"{APPROVAL_TOKEN_PREFIX}{fingerprint}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

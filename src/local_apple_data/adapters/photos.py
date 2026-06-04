from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PHOTOS_HELPER = PROJECT_ROOT / "scripts/photos_helper.swift"
PHOTOS_TIMEOUT_SECONDS = 15.0
PHOTOS_APPLY_TIMEOUT_SECONDS = 90.0
DEFAULT_LIMIT = 20
DEFAULT_MAX_SCAN_ASSETS = 5000
PHOTO_HANDLE_PREFIX = "photos:asset"
MAX_PREVIEW_FILENAME_CHARS = 255
MAX_IMPORT_BYTES = 2 * 1024 * 1024 * 1024
PLAN_OPERATIONS = {"import"}
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


def _export_privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "content_exported": True,
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
        detail = runner(
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
        detail = runner(
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
        "privacy": _export_privacy(),
        "result": result,
        "result_count": 1,
        "warnings": _safe_warnings(response) + _safe_warnings(detail),
    }


def plan_photo_change(
    operation: str,
    *,
    source_file: str | Path = "",
    media_type: str = "auto",
) -> dict[str, Any]:
    normalized_operation = operation.strip().replace("-", "_")
    warnings: list[dict[str, str]] = []
    if normalized_operation not in PLAN_OPERATIONS:
        warnings.append(_warning("invalid_operation", "Expected operation import."))
        return _preview_error(warnings)

    source = _source_file_metadata(source_file, media_type=media_type)
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
    approval_token: str = "",
    confirm_apply: bool = False,
    photos_runner: PhotosRunner | None = None,
) -> dict[str, Any]:
    plan = plan_photo_change(
        operation,
        source_file=source_file,
        media_type=media_type,
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
    try:
        applied = runner(
            _apply_helper_payload(preview, source_file=source_file),
            PHOTOS_APPLY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _apply_error(
            [_warning("photos_import_timeout", "Photos import timed out through the local PhotoKit helper.")],
            plan=plan,
            status="apply_unknown",
        )
    except (OSError, ValueError):
        return _apply_error(
            [_warning("photos_unavailable", "Photos import is unavailable through the local PhotoKit helper.")],
            plan=plan,
        )

    if applied.get("status") != "ok":
        return _apply_error(
            _safe_warnings(applied)
            or [_warning("photos_import_failed", "Photos asset could not be imported safely.")],
            plan=plan,
            status=str(applied.get("status") or "error"),
            authorization_status=applied.get("authorization_status"),
        )

    asset = applied.get("asset")
    if not isinstance(asset, dict):
        return _apply_error(
            [_warning("read_back_unavailable", "Photos import succeeded but read-back was unavailable.")],
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
    try:
        return runner(
            {
                "command": "photos",
                "query": query,
                "limit": max(1, min(limit, DEFAULT_MAX_SCAN_ASSETS)),
                "media_type": _bounded_media_type(media_type),
                "max_assets": _bounded_max_scan(max_scan_assets),
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


def _run_photos_helper(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
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


def _asset_export_detail(asset: dict[str, Any]) -> dict[str, Any]:
    result = _asset_detail(asset)
    result["asset_content_exported"] = bool(asset.get("asset_content_exported"))
    result["exported_path"] = _bounded_string(asset.get("exported_path"), 1000)
    result["exported_filename"] = _bounded_string(asset.get("exported_filename"), 500)
    result["exported_bytes"] = _int_value(asset.get("exported_bytes"))
    return result


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


def _invalid_export_handle_result() -> dict[str, Any]:
    result = _invalid_handle_result()
    result["privacy"] = _export_privacy()
    return result


def _preview_error(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
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
    warnings = response.get("warnings")
    if not isinstance(warnings, list):
        return []
    safe: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        if isinstance(code, str) and isinstance(message, str):
            safe.append(_warning(code, message))
    return safe


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


def _apply_helper_payload(preview: dict[str, Any], *, source_file: str | Path) -> dict[str, Any]:
    proposed = preview["proposed"]
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

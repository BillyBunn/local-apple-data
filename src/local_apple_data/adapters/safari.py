from __future__ import annotations

import hashlib
import plistlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_SAFARI_BOOKMARKS_PLIST = Path.home() / "Library/Safari/Bookmarks.plist"
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_SCAN_ITEMS = 20000
HANDLE_PREFIX = "safari:item"
FOLDER_HANDLE_PREFIX = "safari:folder"
READING_LIST_TITLE = "com.apple.ReadingList"
BLOCKED_BROAD_QUERIES = {
    "bookmark",
    "bookmarks",
    "favorite",
    "favorites",
    "history",
    "http",
    "https",
    "list",
    "reading",
    "readinglist",
    "safari",
    "tab",
    "tabs",
    "www",
    "com",
    "net",
    "org",
}


@dataclass(frozen=True)
class SafariItem:
    item_key: str
    path_indexes: tuple[int, ...]
    title: str
    url: str
    kind: str
    date_added: int | None
    date_last_viewed: int | None


@dataclass(frozen=True)
class SafariFolder:
    folder_key: str
    title: str
    path_indexes: tuple[int, ...]
    child_item_count: int
    child_folder_count: int


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _detail_privacy(*, url_returned: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content",
        "url_returned": url_returned,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result(*, source: str = "safari") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": source,
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Safari bookmark search requires a non-empty title or URL query.",
            )
        ],
    }


def _broad_query_result(*, source: str = "safari") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": source,
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Safari bookmark search requires a specific title or URL term.",
            )
        ],
    }


def _invalid_handle_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "safari",
        "privacy": _detail_privacy(url_returned=False),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected safari:item:v1 opaque handle from search output.",
            )
        ],
    }


def _invalid_folder_handle_result(*, source: str = "safari_folder") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": source,
        "privacy": _privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                "Expected safari:folder:v1 opaque handle from folder metadata output.",
            )
        ],
    }


def _unavailable_result(*, detail: bool = False, code: str = "safari_store_unavailable") -> dict[str, Any]:
    messages = {
        "safari_store_unavailable": "Safari bookmarks store is missing or unreadable.",
        "safari_parse_error": "Safari bookmarks store could not be parsed safely.",
    }
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "safari",
        "privacy": _detail_privacy(url_returned=False) if detail else _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [_warning(code, messages[code])],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def search_safari_items(
    query: str,
    *,
    bookmarks_path: Path = DEFAULT_SAFARI_BOOKMARKS_PLIST,
    limit: int = DEFAULT_LIMIT,
    kind: str = "all",
    max_scan_items: int = MAX_SCAN_ITEMS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not _is_specific_query(query):
        return _broad_query_result()

    normalized_kind = _normalize_kind(kind)
    if normalized_kind is None:
        return {
            "schema_version": 1,
            "status": "error",
            "source": "safari",
            "privacy": _privacy(),
            "results": [],
            "result_count": 0,
            "warnings": [
                _warning(
                    "invalid_kind",
                    "Expected Safari kind all, bookmark, or reading_list.",
                )
            ],
        }

    loaded = _load_items(bookmarks_path, max_scan_items=max_scan_items)
    if loaded["status"] != "ok":
        return _unavailable_result(code=loaded["warning_code"])

    lowered_query = query.casefold()
    bounded_limit = max(1, min(limit, MAX_LIMIT))
    results: list[dict[str, Any]] = []
    for item in loaded["items"]:
        if normalized_kind != "all" and item.kind != normalized_kind:
            continue
        if lowered_query not in item.title.casefold() and lowered_query not in item.url.casefold():
            continue
        results.append(_item_metadata(item, loaded["fingerprint"]))
        if len(results) >= bounded_limit:
            break

    warnings = []
    if loaded["truncated"]:
        warnings.append(
            _warning(
                "scan_truncated",
                "Safari bookmark search stopped at the scan limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "safari",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _privacy(),
        "query": {
            "scope": "bookmark_title_or_url",
            "kind": normalized_kind,
            "limit": bounded_limit,
            "max_scan_items": max_scan_items,
        },
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def search_safari_folders(
    query: str,
    *,
    bookmarks_path: Path = DEFAULT_SAFARI_BOOKMARKS_PLIST,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result(source="safari_folders")
    if not _is_specific_query(query):
        return _broad_query_result(source="safari_folders")

    loaded = _load_items(bookmarks_path, max_scan_items=max_scan_items)
    if loaded["status"] != "ok":
        result = _unavailable_result(code=loaded["warning_code"])
        result["source"] = "safari_folders"
        return result

    lowered_query = query.casefold()
    bounded_limit = max(1, min(limit, MAX_LIMIT))
    results: list[dict[str, Any]] = []
    for folder in loaded["folders"]:
        if lowered_query not in folder.title.casefold():
            continue
        results.append(_folder_metadata(folder, loaded["fingerprint"]))
        if len(results) >= bounded_limit:
            break

    warnings = []
    if loaded["truncated"]:
        warnings.append(
            _warning(
                "scan_truncated",
                "Safari folder search stopped at the scan limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "safari_folders",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _privacy(),
        "query": {
            "scope": "folder_title",
            "limit": bounded_limit,
            "max_scan_items": max_scan_items,
        },
        "results": results,
        "result_count": len(results),
        "warnings": warnings,
    }


def get_safari_item(
    handle: str,
    *,
    bookmarks_path: Path = DEFAULT_SAFARI_BOOKMARKS_PLIST,
    max_scan_items: int = MAX_SCAN_ITEMS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, HANDLE_PREFIX):
        return _invalid_handle_result()

    loaded = _load_items(bookmarks_path, max_scan_items=max_scan_items)
    if loaded["status"] != "ok":
        return _unavailable_result(detail=True, code=loaded["warning_code"])

    for item in loaded["items"]:
        if opaque_handle_matches(handle, HANDLE_PREFIX, loaded["fingerprint"], item.item_key):
            result = _item_metadata(item, loaded["fingerprint"])
            result["url"] = item.url
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "safari",
                "store_fingerprint": loaded["fingerprint"],
                "privacy": _detail_privacy(url_returned=True),
                "result": result,
                "result_count": 1,
                "warnings": [],
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "safari",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _detail_privacy(url_returned=False),
        "result": None,
        "warnings": [],
    }


def get_safari_folder(
    handle: str,
    *,
    bookmarks_path: Path = DEFAULT_SAFARI_BOOKMARKS_PLIST,
    max_scan_items: int = MAX_SCAN_ITEMS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        return _invalid_folder_handle_result()

    loaded = _load_items(bookmarks_path, max_scan_items=max_scan_items)
    if loaded["status"] != "ok":
        result = _unavailable_result(code=loaded["warning_code"])
        result["source"] = "safari_folder"
        return result

    folder = _find_folder(handle, loaded)
    if folder is None:
        return _folder_not_found_result(loaded["fingerprint"], source="safari_folder")

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "safari_folder",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _privacy(),
        "result": _folder_metadata(folder, loaded["fingerprint"]),
        "result_count": 1,
        "warnings": [],
    }


def list_safari_folder_items(
    handle: str,
    *,
    bookmarks_path: Path = DEFAULT_SAFARI_BOOKMARKS_PLIST,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, FOLDER_HANDLE_PREFIX):
        return _invalid_folder_handle_result(source="safari_folder_items")

    loaded = _load_items(bookmarks_path, max_scan_items=max_scan_items)
    if loaded["status"] != "ok":
        result = _unavailable_result(code=loaded["warning_code"])
        result["source"] = "safari_folder_items"
        return result

    folder = _find_folder(handle, loaded)
    if folder is None:
        return _folder_not_found_result(loaded["fingerprint"], source="safari_folder_items")

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    child_depth = len(folder.path_indexes) + 1
    direct_items = [
        item
        for item in loaded["items"]
        if len(item.path_indexes) == child_depth and item.path_indexes[:-1] == folder.path_indexes
    ]
    direct_folders = [
        child
        for child in loaded["folders"]
        if len(child.path_indexes) == child_depth and child.path_indexes[:-1] == folder.path_indexes
    ]
    direct_children = sorted([*direct_items, *direct_folders], key=lambda child: child.path_indexes)[
        :bounded_limit
    ]
    child_items = [child for child in direct_children if isinstance(child, SafariItem)]
    child_folders = [child for child in direct_children if isinstance(child, SafariFolder)]

    warnings = []
    if loaded["truncated"]:
        warnings.append(
            _warning(
                "scan_truncated",
                "Safari folder item listing stopped at the scan limit.",
            )
        )

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "safari_folder_items",
        "store_fingerprint": loaded["fingerprint"],
        "privacy": _privacy(),
        "query": {"scope": "selected_folder_items", "limit": bounded_limit},
        "folder": _folder_metadata(folder, loaded["fingerprint"]),
        "results": [_item_metadata(item, loaded["fingerprint"]) for item in child_items],
        "child_folders": [_folder_metadata(child, loaded["fingerprint"]) for child in child_folders],
        "result_count": len(child_items),
        "child_folder_count": len(child_folders),
        "warnings": warnings,
    }


def _load_items(bookmarks_path: Path, *, max_scan_items: int) -> dict[str, Any]:
    path = bookmarks_path.expanduser()
    try:
        raw = path.read_bytes()
    except OSError:
        return {"status": "error", "warning_code": "safari_store_unavailable"}

    try:
        plist = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ValueError, TypeError):
        return {"status": "error", "warning_code": "safari_parse_error"}

    fingerprint = hashlib.sha256(raw).hexdigest()[:16]
    items: list[SafariItem] = []
    folders: list[SafariFolder] = []
    truncated = False
    for entry in _iter_entries(plist, max_scan_items=max_scan_items):
        if isinstance(entry, SafariItem):
            items.append(entry)
        else:
            folders.append(entry)
        if len(items) + len(folders) >= max_scan_items:
            truncated = True
            break
    return {
        "status": "ok",
        "fingerprint": fingerprint,
        "items": items,
        "folders": folders,
        "truncated": truncated,
    }


def _iter_entries(root: Any, *, max_scan_items: int):
    stack: list[tuple[Any, tuple[int, ...], bool]] = [(root, (), False)]
    visited = 0
    while stack:
        node, path_indexes, in_reading_list = stack.pop()
        if not isinstance(node, dict):
            continue

        node_title = str(node.get("Title") or "")
        node_is_reading_list = in_reading_list or node_title == READING_LIST_TITLE
        children = node.get("Children")
        if isinstance(children, list):
            if path_indexes and not node_is_reading_list:
                visited += 1
                if visited > max_scan_items:
                    return
                yield _make_folder(node, path_indexes)
            for index, child in reversed(list(enumerate(children))):
                stack.append((child, (*path_indexes, index), node_is_reading_list))

        url = node.get("URLString")
        if not isinstance(url, str) or not url.strip():
            continue
        visited += 1
        if visited > max_scan_items:
            return
        yield _make_item(node, url.strip(), path_indexes, node_is_reading_list)


def _make_item(
    node: dict[str, Any],
    url: str,
    path_indexes: tuple[int, ...],
    in_reading_list: bool,
) -> SafariItem:
    title = _item_title(node, url)
    reading_list = node.get("ReadingList")
    is_reading_list = in_reading_list or isinstance(reading_list, dict)
    date_added = None
    date_last_viewed = None
    if isinstance(reading_list, dict):
        date_added = _timestamp(reading_list.get("DateAdded"))
        date_last_viewed = _timestamp(reading_list.get("DateLastViewed"))
    item_key = hashlib.sha256(
        "\0".join((str(path_indexes), title, url, "reading_list" if is_reading_list else "bookmark")).encode(
            "utf-8"
        )
    ).hexdigest()[:32]
    return SafariItem(
        item_key=item_key,
        path_indexes=path_indexes,
        title=title,
        url=url,
        kind="reading_list" if is_reading_list else "bookmark",
        date_added=date_added,
        date_last_viewed=date_last_viewed,
    )


def _make_folder(node: dict[str, Any], path_indexes: tuple[int, ...]) -> SafariFolder:
    title = _bounded_text(str(node.get("Title") or "Untitled Folder").strip() or "Untitled Folder", 200)
    children = node.get("Children") if isinstance(node.get("Children"), list) else []
    child_item_count = 0
    child_folder_count = 0
    for child in children:
        if not isinstance(child, dict):
            continue
        if isinstance(child.get("URLString"), str) and child["URLString"].strip():
            child_item_count += 1
        child_title = str(child.get("Title") or "")
        if isinstance(child.get("Children"), list) and child_title != READING_LIST_TITLE:
            child_folder_count += 1
    folder_key = hashlib.sha256(
        "\0".join((str(path_indexes), title, str(child_item_count), str(child_folder_count))).encode(
            "utf-8"
        )
    ).hexdigest()[:32]
    return SafariFolder(
        folder_key=folder_key,
        title=title,
        path_indexes=path_indexes,
        child_item_count=child_item_count,
        child_folder_count=child_folder_count,
    )


def _item_title(node: dict[str, Any], url: str) -> str:
    uri_dictionary = node.get("URIDictionary")
    if isinstance(uri_dictionary, dict):
        candidate = uri_dictionary.get("title")
        if isinstance(candidate, str) and candidate.strip():
            return _bounded_text(candidate.strip(), 200)
    candidate = node.get("Title")
    if isinstance(candidate, str) and candidate.strip():
        return _bounded_text(candidate.strip(), 200)
    parsed = urlparse(url)
    if parsed.hostname:
        return _bounded_text(parsed.hostname, 200)
    return "Untitled"


def _item_metadata(item: SafariItem, fingerprint: str) -> dict[str, Any]:
    parsed = urlparse(item.url)
    hostname = parsed.hostname or ""
    path_depth = len([part for part in parsed.path.split("/") if part])
    return {
        "handle": make_opaque_handle(HANDLE_PREFIX, fingerprint, item.item_key),
        "title": item.title,
        "kind": item.kind,
        "url_domain": hostname.lower(),
        "url_scheme": parsed.scheme.lower() or None,
        "url_has_query": bool(parsed.query),
        "url_path_depth": path_depth,
        "date_added": item.date_added,
        "date_last_viewed": item.date_last_viewed,
    }


def _folder_metadata(folder: SafariFolder, fingerprint: str) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(FOLDER_HANDLE_PREFIX, fingerprint, folder.folder_key),
        "title": folder.title,
        "kind": "folder",
        "path_depth": len(folder.path_indexes),
        "child_item_count": folder.child_item_count,
        "child_folder_count": folder.child_folder_count,
    }


def _find_folder(handle: str, loaded: dict[str, Any]) -> SafariFolder | None:
    for folder in loaded["folders"]:
        if opaque_handle_matches(handle, FOLDER_HANDLE_PREFIX, loaded["fingerprint"], folder.folder_key):
            return folder
    return None


def _folder_not_found_result(fingerprint: str, *, source: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "not_found",
        "source": source,
        "store_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def _normalize_kind(kind: str) -> str | None:
    normalized = kind.strip().replace("-", "_").lower() or "all"
    if normalized in {"all", "bookmark", "reading_list"}:
        return normalized
    return None


def _timestamp(value: Any) -> int | None:
    if isinstance(value, datetime):
        return int(value.timestamp())
    return None


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."

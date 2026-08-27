from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import has_minimum_query_quality


DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_SCAN_ITEMS = 5000
DEFAULT_TIMEOUT_SECONDS = 20.0
TV_APP_PATH = Path("/System/Applications/TV.app")
DEFAULT_TV_LIBRARY = Path.home() / "Movies/TV/TV Library.tvlibrary/Library.tvdb"
ITEM_HANDLE_PREFIX = "tv:item"
PLAYLIST_HANDLE_PREFIX = "tv:playlist"
FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"
BLOCKED_BROAD_QUERIES = {
    "all",
    "apple",
    "appletv",
    "download",
    "downloads",
    "episode",
    "episodes",
    "library",
    "libraries",
    "movie",
    "movies",
    "playlist",
    "playlists",
    "season",
    "seasons",
    "show",
    "shows",
    "tv",
    "unwatched",
    "video",
    "videos",
    "watched",
}


@dataclass(frozen=True)
class TVCommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


TVRunner = Callable[[list[str], float], TVCommandResult]


@dataclass(frozen=True)
class TVItem:
    persistent_id: str
    database_id: str
    title: str
    show: str
    artist: str
    genre: str
    video_kind: str
    duration_seconds: float | None
    season_number: int | None
    episode_number: int | None
    year: int | None


@dataclass(frozen=True)
class TVPlaylist:
    persistent_id: str
    database_id: str
    title: str
    kind: str
    item_count: int | None
    duration_seconds: float | None


def _privacy(*, playlist_items_returned: bool = False) -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
        "video_content_returned": False,
        "file_path_returned": False,
        "raw_identifier_returned": False,
        "artwork_returned": False,
        "description_returned": False,
        "playback_state_returned": False,
        "watched_state_returned": False,
        "rating_returned": False,
        "playlist_items_returned": playlist_items_returned,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_query_result(*, source: str) -> dict[str, Any]:
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
                "TV search requires a non-empty title, show, artist, genre, or playlist query.",
            )
        ],
    }


def _broad_query_result(*, source: str) -> dict[str, Any]:
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
                "TV search requires a specific title, show, artist, genre, or playlist term.",
            )
        ],
    }


def _invalid_handle_result(*, source: str, expected: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": source,
        "privacy": _privacy(),
        "result": None,
        "warnings": [
            _warning(
                "invalid_handle",
                f"Expected {expected} opaque handle from search output.",
            )
        ],
    }


def _automation_degraded_result(
    *,
    source: str,
    detail: bool = False,
    code: str = "tv_automation_error",
) -> dict[str, Any]:
    messages = {
        "tv_automation_unavailable": "TV.app automation is unavailable.",
        "tv_automation_error": "TV.app automation returned an error.",
        "tv_parse_error": "TV.app automation output could not be parsed safely.",
    }
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": source,
        "privacy": _privacy(),
        "results": [] if not detail else None,
        "result": None,
        "result_count": 0 if not detail else None,
        "warnings": [_warning(code, messages[code])],
    }


def _not_found_result(*, source: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "not_found",
        "source": source,
        "privacy": _privacy(),
        "result": None,
        "warnings": [_warning("not_found", "No TV item matched that opaque handle.")],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def search_tv_items(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: TVRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result(source="tv")
    if not _is_specific_query(query):
        return _broad_query_result(source="tv")

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded = _load_items(
        command_name="search_items",
        query=query,
        limit=bounded_limit,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _automation_degraded_result(source="tv", code=loaded["warning_code"])

    warnings = _scan_warnings(loaded["items"], bounded_scan)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "tv",
        "store_fingerprint": _fingerprint_items(loaded["items"]),
        "privacy": _privacy(),
        "query": {
            "scope": "title_show_artist_or_genre",
            "limit": bounded_limit,
            "max_scan_items": bounded_scan,
        },
        "results": [_item_metadata(item) for item in loaded["items"][:bounded_limit]],
        "result_count": min(len(loaded["items"]), bounded_limit),
        "warnings": warnings,
    }


def get_tv_item(
    handle: str,
    *,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: TVRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, ITEM_HANDLE_PREFIX):
        return _invalid_handle_result(source="tv", expected="tv:item:v1")

    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded = _load_items(
        command_name="list_items",
        query="",
        limit=bounded_scan,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _automation_degraded_result(
            source="tv",
            detail=True,
            code=loaded["warning_code"],
        )

    for item in loaded["items"]:
        if opaque_handle_matches(handle, ITEM_HANDLE_PREFIX, item.persistent_id):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "tv",
                "store_fingerprint": _fingerprint_items(loaded["items"]),
                "privacy": _privacy(),
                "result": _item_metadata(item),
                "warnings": _scan_warnings(loaded["items"], bounded_scan),
            }

    return _not_found_result(source="tv")


def search_tv_playlists(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: TVRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result(source="tv_playlists")
    if not _is_specific_query(query):
        return _broad_query_result(source="tv_playlists")

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded = _load_playlists(
        command_name="search_playlists",
        query=query,
        limit=bounded_limit,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _automation_degraded_result(
            source="tv_playlists",
            code=loaded["warning_code"],
        )

    warnings = _scan_warnings(loaded["playlists"], bounded_scan)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "tv_playlists",
        "store_fingerprint": _fingerprint_playlists(loaded["playlists"]),
        "privacy": _privacy(),
        "query": {
            "scope": "playlist_name",
            "limit": bounded_limit,
            "max_scan_items": bounded_scan,
        },
        "results": [
            _playlist_metadata(playlist) for playlist in loaded["playlists"][:bounded_limit]
        ],
        "result_count": min(len(loaded["playlists"]), bounded_limit),
        "warnings": warnings,
    }


def get_tv_playlist(
    handle: str,
    *,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: TVRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PLAYLIST_HANDLE_PREFIX):
        return _invalid_handle_result(
            source="tv_playlists",
            expected="tv:playlist:v1",
        )

    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded = _load_playlists(
        command_name="list_playlists",
        query="",
        limit=bounded_scan,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _automation_degraded_result(
            source="tv_playlists",
            detail=True,
            code=loaded["warning_code"],
        )

    for playlist in loaded["playlists"]:
        if opaque_handle_matches(handle, PLAYLIST_HANDLE_PREFIX, playlist.persistent_id):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "tv_playlists",
                "store_fingerprint": _fingerprint_playlists(loaded["playlists"]),
                "privacy": _privacy(),
                "result": _playlist_metadata(playlist),
                "warnings": _scan_warnings(loaded["playlists"], bounded_scan),
            }

    return _not_found_result(source="tv_playlists")


def list_tv_playlist_items(
    handle: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: TVRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PLAYLIST_HANDLE_PREFIX):
        return _invalid_handle_result(
            source="tv_playlist_items",
            expected="tv:playlist:v1",
        )

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded_playlists = _load_playlists(
        command_name="list_playlists",
        query="",
        limit=bounded_scan,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded_playlists["status"] != "ok":
        return _automation_degraded_result(
            source="tv_playlist_items",
            code=loaded_playlists["warning_code"],
        )

    selected_playlist: TVPlaylist | None = None
    for playlist in loaded_playlists["playlists"]:
        if opaque_handle_matches(handle, PLAYLIST_HANDLE_PREFIX, playlist.persistent_id):
            selected_playlist = playlist
            break

    if selected_playlist is None:
        return _not_found_result(source="tv_playlist_items")

    loaded_items = _load_items(
        command_name="list_playlist_items",
        query=selected_playlist.persistent_id,
        limit=bounded_limit,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded_items["status"] != "ok":
        return _automation_degraded_result(
            source="tv_playlist_items",
            code=loaded_items["warning_code"],
        )

    warnings = [
        *_scan_warnings(loaded_playlists["playlists"], bounded_scan),
        *_scan_warnings(loaded_items["items"], bounded_scan),
    ]
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "tv_playlist_items",
        "store_fingerprint": _fingerprint_items(loaded_items["items"]),
        "privacy": _privacy(playlist_items_returned=True),
        "query": {
            "scope": "selected_playlist_items",
            "limit": bounded_limit,
            "max_scan_items": bounded_scan,
        },
        "playlist": _playlist_metadata(selected_playlist),
        "results": [_item_metadata(item) for item in loaded_items["items"][:bounded_limit]],
        "result_count": min(len(loaded_items["items"]), bounded_limit),
        "warnings": warnings,
    }


def check_tv_readiness(
    *,
    tv_app_path: Path = TV_APP_PATH,
    library_path: Path = DEFAULT_TV_LIBRARY,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    osascript_available = shutil.which("osascript") is not None
    tv_app_available = tv_app_path.exists()
    library_available = library_path.exists()
    if not osascript_available:
        warnings.append(_warning("osascript_unavailable", "The osascript tool is unavailable."))
    if not tv_app_available:
        warnings.append(_warning("tv_app_missing", "TV.app is not available."))
    if not library_available:
        warnings.append(
            _warning("tv_library_missing", "The default TV library package was not found.")
        )
    return {
        "status": "ok" if osascript_available and tv_app_available else "degraded",
        "source": "tv",
        "osascript_available": osascript_available,
        "tv_app_available": tv_app_available,
        "library_available": library_available,
        "warnings": warnings,
    }


def _load_items(
    *,
    command_name: str,
    query: str,
    limit: int,
    max_scan_items: int,
    runner: TVRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    result = _run_tv_command(
        [command_name, query, str(limit), str(max_scan_items)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if result["status"] != "ok":
        return result
    try:
        items = [
            item
            for item in (_parse_item_record(record) for record in _records(result["stdout"]))
            if item.persistent_id
        ]
    except ValueError:
        return {"status": "degraded", "warning_code": "tv_parse_error"}
    return {"status": "ok", "items": items}


def _load_playlists(
    *,
    command_name: str,
    query: str,
    limit: int,
    max_scan_items: int,
    runner: TVRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    result = _run_tv_command(
        [command_name, query, str(limit), str(max_scan_items)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if result["status"] != "ok":
        return result
    try:
        playlists = [
            playlist
            for playlist in (
                _parse_playlist_record(record) for record in _records(result["stdout"])
            )
            if playlist.persistent_id
        ]
    except ValueError:
        return {"status": "degraded", "warning_code": "tv_parse_error"}
    return {"status": "ok", "playlists": playlists}


def _run_tv_command(
    args: list[str],
    *,
    runner: TVRunner | None,
    timeout_seconds: float,
) -> dict[str, str]:
    active_runner = runner or _default_runner
    try:
        result = active_runner(args, timeout_seconds)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "degraded", "warning_code": "tv_automation_unavailable"}
    if result.returncode != 0:
        return {"status": "degraded", "warning_code": "tv_automation_error"}
    return {"status": "ok", "stdout": result.stdout}


def _default_runner(args: list[str], timeout_seconds: float) -> TVCommandResult:
    completed = subprocess.run(
        ["osascript", "-e", TV_APPLESCRIPT, "--", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        check=False,
    )
    return TVCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _records(stdout: str) -> list[str]:
    payload = stdout.strip("\r\n")
    if not payload:
        return []
    return [record for record in payload.split(RECORD_SEPARATOR) if record]


def _parse_item_record(record: str) -> TVItem:
    fields = record.split(FIELD_SEPARATOR)
    if len(fields) != 11:
        raise ValueError("invalid item field count")
    return TVItem(
        persistent_id=fields[0],
        database_id=fields[1],
        title=fields[2],
        show=fields[3],
        artist=fields[4],
        genre=fields[5],
        video_kind=fields[6],
        duration_seconds=_safe_float(fields[7]),
        season_number=_safe_int(fields[8]),
        episode_number=_safe_int(fields[9]),
        year=_safe_int(fields[10]),
    )


def _parse_playlist_record(record: str) -> TVPlaylist:
    fields = record.split(FIELD_SEPARATOR)
    if len(fields) != 6:
        raise ValueError("invalid playlist field count")
    return TVPlaylist(
        persistent_id=fields[0],
        database_id=fields[1],
        title=fields[2],
        kind=fields[3] or "unknown",
        item_count=_safe_int(fields[4]),
        duration_seconds=_safe_float(fields[5]),
    )


def _item_metadata(item: TVItem) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(ITEM_HANDLE_PREFIX, item.persistent_id),
        "title": item.title,
        "show": item.show,
        "artist": item.artist,
        "genre": item.genre,
        "video_kind": item.video_kind,
        "duration_seconds": item.duration_seconds,
        "season_number": item.season_number,
        "episode_number": item.episode_number,
        "year": item.year,
        "raw_identifier_returned": False,
        "file_path_returned": False,
        "video_content_returned": False,
        "artwork_returned": False,
        "description_returned": False,
        "playback_state_returned": False,
        "watched_state_returned": False,
        "rating_returned": False,
    }


def _playlist_metadata(playlist: TVPlaylist) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(PLAYLIST_HANDLE_PREFIX, playlist.persistent_id),
        "title": playlist.title,
        "kind": playlist.kind,
        "item_count": playlist.item_count,
        "duration_seconds": playlist.duration_seconds,
        "raw_identifier_returned": False,
        "playlist_items_returned": False,
    }


def _fingerprint_items(items: list[TVItem]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(items)).encode("utf-8"))
    for item in items:
        digest.update(b"\0")
        digest.update(item.persistent_id.encode("utf-8"))
    return digest.hexdigest()[:16]


def _fingerprint_playlists(playlists: list[TVPlaylist]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(playlists)).encode("utf-8"))
    for playlist in playlists:
        digest.update(b"\0")
        digest.update(playlist.persistent_id.encode("utf-8"))
    return digest.hexdigest()[:16]


def _scan_warnings(items: list[object], max_scan_items: int) -> list[dict[str, str]]:
    if len(items) >= max_scan_items:
        return [_warning("scan_limit_reached", "TV.app automation stopped at the scan limit.")]
    return []


def _bounded_scan_items(max_scan_items: int) -> int:
    return max(1, min(max_scan_items, MAX_SCAN_ITEMS))


def _safe_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


TV_APPLESCRIPT = r'''
on cleanText(value)
    try
        if value is missing value then return ""
        set valueText to value as string
    on error
        return ""
    end try
    set valueText to my replaceText(valueText, (ASCII character 31), " ")
    set valueText to my replaceText(valueText, (ASCII character 30), " ")
    set valueText to my replaceText(valueText, return, " ")
    set valueText to my replaceText(valueText, linefeed, " ")
    return valueText
end cleanText

on replaceText(theText, searchString, replacementString)
    set AppleScript's text item delimiters to searchString
    set textItems to text items of theText
    set AppleScript's text item delimiters to replacementString
    set newText to textItems as string
    set AppleScript's text item delimiters to ""
    return newText
end replaceText

on joinFields(fieldList)
    set AppleScript's text item delimiters to (ASCII character 31)
    set joinedText to fieldList as string
    set AppleScript's text item delimiters to ""
    return joinedText
end joinFields

on joinRecords(recordList)
    set AppleScript's text item delimiters to (ASCII character 30)
    set joinedText to recordList as string
    set AppleScript's text item delimiters to ""
    return joinedText
end joinRecords

on itemRecord(videoItem)
    try
        set persistentIdValue to persistent ID of videoItem as string
    on error
        set persistentIdValue to ""
    end try
    try
        set databaseIdValue to database ID of videoItem as string
    on error
        set databaseIdValue to ""
    end try
    try
        set titleValue to name of videoItem
    on error
        set titleValue to ""
    end try
    try
        set showValue to show of videoItem
    on error
        set showValue to ""
    end try
    try
        set artistValue to artist of videoItem
    on error
        set artistValue to ""
    end try
    try
        set genreValue to genre of videoItem
    on error
        set genreValue to ""
    end try
    try
        set videoKindValue to video kind of videoItem as string
    on error
        set videoKindValue to ""
    end try
    try
        set durationValue to duration of videoItem as string
    on error
        set durationValue to ""
    end try
    try
        set seasonNumberValue to season number of videoItem as string
    on error
        set seasonNumberValue to ""
    end try
    try
        set episodeNumberValue to episode number of videoItem as string
    on error
        set episodeNumberValue to ""
    end try
    try
        set yearValue to year of videoItem as string
    on error
        set yearValue to ""
    end try
    return my joinFields({persistentIdValue, databaseIdValue, my cleanText(titleValue), my cleanText(showValue), my cleanText(artistValue), my cleanText(genreValue), my cleanText(videoKindValue), durationValue, seasonNumberValue, episodeNumberValue, yearValue})
end itemRecord

on playlistRecord(playlistItem)
    try
        set persistentIdValue to persistent ID of playlistItem as string
    on error
        set persistentIdValue to ""
    end try
    try
        set databaseIdValue to database ID of playlistItem as string
    on error
        set databaseIdValue to ""
    end try
    try
        set titleValue to name of playlistItem
    on error
        set titleValue to ""
    end try
    try
        set kindValue to special kind of playlistItem as string
    on error
        set kindValue to "user"
    end try
    try
        set itemCountValue to count of tracks of playlistItem as string
    on error
        set itemCountValue to ""
    end try
    try
        set durationValue to duration of playlistItem as string
    on error
        set durationValue to ""
    end try
    return my joinFields({persistentIdValue, databaseIdValue, my cleanText(titleValue), kindValue, itemCountValue, durationValue})
end playlistRecord

on containsQuery(valueText, queryText)
    if queryText is "" then return true
    return (my cleanText(valueText)) contains queryText
end containsQuery

on itemMatches(videoItem, queryText)
    try
        if my containsQuery(name of videoItem, queryText) then return true
    end try
    try
        if my containsQuery(show of videoItem, queryText) then return true
    end try
    try
        if my containsQuery(artist of videoItem, queryText) then return true
    end try
    try
        if my containsQuery(genre of videoItem, queryText) then return true
    end try
    try
        if my containsQuery(video kind of videoItem, queryText) then return true
    end try
    return false
end itemMatches

on run argv
    set commandName to item 1 of argv
    set queryText to item 2 of argv
    set resultLimit to (item 3 of argv) as integer
    set scanLimit to (item 4 of argv) as integer
    set outputRecords to {}
    tell application "TV"
        if commandName is "search_items" or commandName is "list_items" then
            set scannedCount to 0
            repeat with videoItem in tracks of library playlist 1
                set scannedCount to scannedCount + 1
                if scannedCount > scanLimit then exit repeat
                if commandName is "list_items" or my itemMatches(videoItem, queryText) then
                    set end of outputRecords to my itemRecord(videoItem)
                    if (count of outputRecords) >= resultLimit then exit repeat
                end if
            end repeat
            return my joinRecords(outputRecords)
        end if
        if commandName is "search_playlists" or commandName is "list_playlists" then
            set scannedCount to 0
            repeat with playlistItem in playlists
                set scannedCount to scannedCount + 1
                if scannedCount > scanLimit then exit repeat
                if commandName is "list_playlists" or my containsQuery(name of playlistItem, queryText) then
                    set end of outputRecords to my playlistRecord(playlistItem)
                    if (count of outputRecords) >= resultLimit then exit repeat
                end if
            end repeat
            return my joinRecords(outputRecords)
        end if
        if commandName is "list_playlist_items" then
            set playlistScanCount to 0
            repeat with playlistItem in playlists
                set playlistScanCount to playlistScanCount + 1
                if playlistScanCount > scanLimit then exit repeat
                try
                    set playlistPersistentIdValue to persistent ID of playlistItem as string
                on error
                    set playlistPersistentIdValue to ""
                end try
                if playlistPersistentIdValue is queryText then
                    set scannedCount to 0
                    repeat with videoItem in tracks of playlistItem
                        set scannedCount to scannedCount + 1
                        if scannedCount > scanLimit then exit repeat
                        set end of outputRecords to my itemRecord(videoItem)
                        if (count of outputRecords) >= resultLimit then exit repeat
                    end repeat
                    return my joinRecords(outputRecords)
                end if
            end repeat
            return ""
        end if
    end tell
    return ""
end run
'''

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
MUSIC_APP_PATH = Path("/System/Applications/Music.app")
DEFAULT_MUSIC_LIBRARY = Path.home() / "Music/Music/Music Library.musiclibrary/Library.musicdb"
TRACK_HANDLE_PREFIX = "music:track"
PLAYLIST_HANDLE_PREFIX = "music:playlist"
FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"
BLOCKED_BROAD_QUERIES = {
    "album",
    "albums",
    "all",
    "artist",
    "artists",
    "audio",
    "library",
    "libraries",
    "lyric",
    "lyrics",
    "music",
    "playlist",
    "playlists",
    "song",
    "songs",
    "track",
    "tracks",
}


@dataclass(frozen=True)
class MusicCommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


MusicRunner = Callable[[list[str], float], MusicCommandResult]


@dataclass(frozen=True)
class MusicTrack:
    persistent_id: str
    database_id: str
    title: str
    artist: str
    album: str
    album_artist: str
    genre: str
    duration_seconds: float | None
    track_number: int | None
    disc_number: int | None
    year: int | None


@dataclass(frozen=True)
class MusicPlaylist:
    persistent_id: str
    database_id: str
    title: str
    kind: str
    track_count: int | None
    duration_seconds: float | None


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
        "audio_content_returned": False,
        "lyrics_returned": False,
        "file_path_returned": False,
        "raw_identifier_returned": False,
        "play_history_returned": False,
        "rating_returned": False,
        "playlist_tracks_returned": False,
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
                "Music search requires a non-empty track, artist, album, genre, or playlist query.",
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
                "Music search requires a specific track, artist, album, genre, or playlist term.",
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
    code: str = "music_automation_error",
) -> dict[str, Any]:
    messages = {
        "music_automation_unavailable": "Music.app automation is unavailable.",
        "music_automation_error": "Music.app automation returned an error.",
        "music_parse_error": "Music.app automation output could not be parsed safely.",
    }
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": source,
        "privacy": _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
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
        "warnings": [_warning("not_found", "No Music item matched that opaque handle.")],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def search_music_tracks(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: MusicRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result(source="music")
    if not _is_specific_query(query):
        return _broad_query_result(source="music")

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded = _load_tracks(
        command_name="search_tracks",
        query=query,
        limit=bounded_limit,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _automation_degraded_result(source="music", code=loaded["warning_code"])

    fingerprint = _fingerprint_tracks(loaded["tracks"])
    warnings = _scan_warnings(loaded["tracks"], bounded_scan)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "music",
        "store_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {
            "scope": "track_title_artist_album_or_genre",
            "limit": bounded_limit,
            "max_scan_items": bounded_scan,
        },
        "results": [_track_metadata(track) for track in loaded["tracks"][:bounded_limit]],
        "result_count": min(len(loaded["tracks"]), bounded_limit),
        "warnings": warnings,
    }


def get_music_track(
    handle: str,
    *,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: MusicRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, TRACK_HANDLE_PREFIX):
        return _invalid_handle_result(source="music", expected="music:track:v1")

    bounded_scan = _bounded_scan_items(max_scan_items)
    loaded = _load_tracks(
        command_name="list_tracks",
        query="",
        limit=bounded_scan,
        max_scan_items=bounded_scan,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if loaded["status"] != "ok":
        return _automation_degraded_result(
            source="music",
            detail=True,
            code=loaded["warning_code"],
        )

    for track in loaded["tracks"]:
        if opaque_handle_matches(handle, TRACK_HANDLE_PREFIX, track.persistent_id):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "music",
                "store_fingerprint": _fingerprint_tracks(loaded["tracks"]),
                "privacy": _privacy(),
                "result": _track_metadata(track),
                "warnings": _scan_warnings(loaded["tracks"], bounded_scan),
            }

    return _not_found_result(source="music")


def search_music_playlists(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: MusicRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result(source="music_playlists")
    if not _is_specific_query(query):
        return _broad_query_result(source="music_playlists")

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
            source="music_playlists",
            code=loaded["warning_code"],
        )

    fingerprint = _fingerprint_playlists(loaded["playlists"])
    warnings = _scan_warnings(loaded["playlists"], bounded_scan)
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "music_playlists",
        "store_fingerprint": fingerprint,
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


def get_music_playlist(
    handle: str,
    *,
    max_scan_items: int = MAX_SCAN_ITEMS,
    runner: MusicRunner | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, PLAYLIST_HANDLE_PREFIX):
        return _invalid_handle_result(
            source="music_playlists",
            expected="music:playlist:v1",
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
            source="music_playlists",
            detail=True,
            code=loaded["warning_code"],
        )

    for playlist in loaded["playlists"]:
        if opaque_handle_matches(handle, PLAYLIST_HANDLE_PREFIX, playlist.persistent_id):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "music_playlists",
                "store_fingerprint": _fingerprint_playlists(loaded["playlists"]),
                "privacy": _privacy(),
                "result": _playlist_metadata(playlist),
                "warnings": _scan_warnings(loaded["playlists"], bounded_scan),
            }

    return _not_found_result(source="music_playlists")


def check_music_readiness(
    *,
    music_app_path: Path = MUSIC_APP_PATH,
    library_path: Path = DEFAULT_MUSIC_LIBRARY,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    osascript_available = shutil.which("osascript") is not None
    music_app_available = music_app_path.exists()
    library_available = library_path.exists()
    if not osascript_available:
        warnings.append(
            _warning("osascript_unavailable", "The osascript tool is unavailable.")
        )
    if not music_app_available:
        warnings.append(_warning("music_app_missing", "Music.app is not available."))
    if not library_available:
        warnings.append(
            _warning(
                "music_library_missing",
                "The default Music library package was not found.",
            )
        )
    return {
        "status": "ok" if osascript_available and music_app_available else "degraded",
        "source": "music",
        "osascript_available": osascript_available,
        "music_app_available": music_app_available,
        "library_available": library_available,
        "warnings": warnings,
    }


def _load_tracks(
    *,
    command_name: str,
    query: str,
    limit: int,
    max_scan_items: int,
    runner: MusicRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    result = _run_music_command(
        [command_name, query, str(limit), str(max_scan_items)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    if result["status"] != "ok":
        return result
    try:
        tracks = [
            track
            for track in (_parse_track_record(record) for record in _records(result["stdout"]))
            if track.persistent_id
        ]
    except ValueError:
        return {"status": "degraded", "warning_code": "music_parse_error"}
    return {"status": "ok", "tracks": tracks}


def _load_playlists(
    *,
    command_name: str,
    query: str,
    limit: int,
    max_scan_items: int,
    runner: MusicRunner | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    result = _run_music_command(
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
        return {"status": "degraded", "warning_code": "music_parse_error"}
    return {"status": "ok", "playlists": playlists}


def _run_music_command(
    args: list[str],
    *,
    runner: MusicRunner | None,
    timeout_seconds: float,
) -> dict[str, str]:
    active_runner = runner or _default_runner
    try:
        result = active_runner(args, timeout_seconds)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"status": "degraded", "warning_code": "music_automation_unavailable"}
    if result.returncode != 0:
        return {"status": "degraded", "warning_code": "music_automation_error"}
    return {"status": "ok", "stdout": result.stdout}


def _default_runner(args: list[str], timeout_seconds: float) -> MusicCommandResult:
    completed = subprocess.run(
        ["osascript", "-e", MUSIC_APPLESCRIPT, "--", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        check=False,
    )
    return MusicCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _records(stdout: str) -> list[str]:
    payload = stdout.strip("\r\n")
    if not payload:
        return []
    return [record for record in payload.split(RECORD_SEPARATOR) if record]


def _parse_track_record(record: str) -> MusicTrack:
    fields = record.split(FIELD_SEPARATOR)
    if len(fields) != 11:
        raise ValueError("invalid track field count")
    return MusicTrack(
        persistent_id=fields[0],
        database_id=fields[1],
        title=fields[2],
        artist=fields[3],
        album=fields[4],
        album_artist=fields[5],
        genre=fields[6],
        duration_seconds=_safe_float(fields[7]),
        track_number=_safe_int(fields[8]),
        disc_number=_safe_int(fields[9]),
        year=_safe_int(fields[10]),
    )


def _parse_playlist_record(record: str) -> MusicPlaylist:
    fields = record.split(FIELD_SEPARATOR)
    if len(fields) != 6:
        raise ValueError("invalid playlist field count")
    return MusicPlaylist(
        persistent_id=fields[0],
        database_id=fields[1],
        title=fields[2],
        kind=fields[3] or "unknown",
        track_count=_safe_int(fields[4]),
        duration_seconds=_safe_float(fields[5]),
    )


def _track_metadata(track: MusicTrack) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(TRACK_HANDLE_PREFIX, track.persistent_id),
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "album_artist": track.album_artist,
        "genre": track.genre,
        "duration_seconds": track.duration_seconds,
        "track_number": track.track_number,
        "disc_number": track.disc_number,
        "year": track.year,
        "raw_identifier_returned": False,
        "file_path_returned": False,
        "audio_content_returned": False,
        "lyrics_returned": False,
        "play_history_returned": False,
        "rating_returned": False,
    }


def _playlist_metadata(playlist: MusicPlaylist) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(PLAYLIST_HANDLE_PREFIX, playlist.persistent_id),
        "title": playlist.title,
        "kind": playlist.kind,
        "track_count": playlist.track_count,
        "duration_seconds": playlist.duration_seconds,
        "raw_identifier_returned": False,
        "playlist_tracks_returned": False,
    }


def _fingerprint_tracks(tracks: list[MusicTrack]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(tracks)).encode("utf-8"))
    for track in tracks:
        digest.update(b"\0")
        digest.update(track.persistent_id.encode("utf-8"))
    return digest.hexdigest()[:16]


def _fingerprint_playlists(playlists: list[MusicPlaylist]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(playlists)).encode("utf-8"))
    for playlist in playlists:
        digest.update(b"\0")
        digest.update(playlist.persistent_id.encode("utf-8"))
    return digest.hexdigest()[:16]


def _scan_warnings(items: list[object], max_scan_items: int) -> list[dict[str, str]]:
    if len(items) >= max_scan_items:
        return [
            _warning(
                "scan_limit_reached",
                "Music.app automation stopped at the scan limit.",
            )
        ]
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


MUSIC_APPLESCRIPT = r'''
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

on trackRecord(trackItem)
    try
        set persistentIdValue to persistent ID of trackItem as string
    on error
        set persistentIdValue to ""
    end try
    try
        set databaseIdValue to database ID of trackItem as string
    on error
        set databaseIdValue to ""
    end try
    try
        set titleValue to name of trackItem
    on error
        set titleValue to ""
    end try
    try
        set artistValue to artist of trackItem
    on error
        set artistValue to ""
    end try
    try
        set albumValue to album of trackItem
    on error
        set albumValue to ""
    end try
    try
        set albumArtistValue to album artist of trackItem
    on error
        set albumArtistValue to ""
    end try
    try
        set genreValue to genre of trackItem
    on error
        set genreValue to ""
    end try
    try
        set durationValue to duration of trackItem as string
    on error
        set durationValue to ""
    end try
    try
        set trackNumberValue to track number of trackItem as string
    on error
        set trackNumberValue to ""
    end try
    try
        set discNumberValue to disc number of trackItem as string
    on error
        set discNumberValue to ""
    end try
    try
        set yearValue to year of trackItem as string
    on error
        set yearValue to ""
    end try
    return my joinFields({persistentIdValue, databaseIdValue, my cleanText(titleValue), my cleanText(artistValue), my cleanText(albumValue), my cleanText(albumArtistValue), my cleanText(genreValue), durationValue, trackNumberValue, discNumberValue, yearValue})
end trackRecord

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
        set trackCountValue to count of tracks of playlistItem as string
    on error
        set trackCountValue to ""
    end try
    try
        set durationValue to duration of playlistItem as string
    on error
        set durationValue to ""
    end try
    return my joinFields({persistentIdValue, databaseIdValue, my cleanText(titleValue), kindValue, trackCountValue, durationValue})
end playlistRecord

on containsQuery(valueText, queryText)
    if queryText is "" then return true
    return (my cleanText(valueText)) contains queryText
end containsQuery

on trackMatches(trackItem, queryText)
    try
        if my containsQuery(name of trackItem, queryText) then return true
    end try
    try
        if my containsQuery(artist of trackItem, queryText) then return true
    end try
    try
        if my containsQuery(album of trackItem, queryText) then return true
    end try
    try
        if my containsQuery(album artist of trackItem, queryText) then return true
    end try
    try
        if my containsQuery(genre of trackItem, queryText) then return true
    end try
    return false
end trackMatches

on run argv
    set commandName to item 1 of argv
    set queryText to item 2 of argv
    set resultLimit to (item 3 of argv) as integer
    set scanLimit to (item 4 of argv) as integer
    set outputRecords to {}
    tell application "Music"
        if commandName is "search_tracks" or commandName is "list_tracks" then
            set scannedCount to 0
            repeat with trackItem in tracks of library playlist 1
                set scannedCount to scannedCount + 1
                if scannedCount > scanLimit then exit repeat
                if commandName is "list_tracks" or my trackMatches(trackItem, queryText) then
                    set end of outputRecords to my trackRecord(trackItem)
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
    end tell
    return ""
end run
'''

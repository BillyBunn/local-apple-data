from __future__ import annotations

from local_apple_data.adapters.music import (
    FIELD_SEPARATOR,
    RECORD_SEPARATOR,
    MusicCommandResult,
    get_music_playlist,
    get_music_track,
    search_music_playlists,
    search_music_tracks,
)


def _track_record(
    persistent_id: str = "RUNTIME-MUSIC-TRACK-ID",
    database_id: str = "123",
    title: str = "Runtime Song",
    artist: str = "Runtime Artist",
    album: str = "Runtime Album",
    album_artist: str = "Runtime Album Artist",
    genre: str = "Runtime Genre",
    duration: str = "123.4",
    track_number: str = "7",
    disc_number: str = "1",
    year: str = "2026",
) -> str:
    return FIELD_SEPARATOR.join(
        [
            persistent_id,
            database_id,
            title,
            artist,
            album,
            album_artist,
            genre,
            duration,
            track_number,
            disc_number,
            year,
        ]
    )


def _playlist_record(
    persistent_id: str = "RUNTIME-MUSIC-PLAYLIST-ID",
    database_id: str = "456",
    title: str = "Runtime Playlist",
    kind: str = "user",
    track_count: str = "3",
    duration: str = "456.7",
) -> str:
    return FIELD_SEPARATOR.join(
        [persistent_id, database_id, title, kind, track_count, duration]
    )


def _runner(command: list[str], _timeout: float) -> MusicCommandResult:
    command_name = command[0]
    if command_name in {"search_tracks", "list_tracks"}:
        return MusicCommandResult(
            returncode=0,
            stdout=RECORD_SEPARATOR.join(
                [
                    _track_record(),
                    _track_record(
                        persistent_id="SECOND-MUSIC-TRACK-ID",
                        database_id="789",
                        title="Other Song",
                    ),
                ]
            ),
        )
    if command_name in {"search_playlists", "list_playlists"}:
        return MusicCommandResult(
            returncode=0,
            stdout=RECORD_SEPARATOR.join(
                [
                    _playlist_record(),
                    _playlist_record(
                        persistent_id="SECOND-MUSIC-PLAYLIST-ID",
                        database_id="987",
                        title="Other Playlist",
                    ),
                ]
            ),
        )
    return MusicCommandResult(returncode=1, stdout="", stderr="unsupported")


def test_search_music_tracks_returns_metadata_without_raw_identifiers() -> None:
    result = search_music_tracks("Runtime", runner=_runner)

    assert result["status"] == "ok"
    assert result["result_count"] == 2
    first = result["results"][0]
    assert first["handle"].startswith("music:track:v1:")
    assert first["title"] == "Runtime Song"
    assert first["duration_seconds"] == 123.4
    assert first["track_number"] == 7
    assert first["raw_identifier_returned"] is False
    assert first["file_path_returned"] is False
    assert first["audio_content_returned"] is False
    assert first["lyrics_returned"] is False
    assert "RUNTIME-MUSIC-TRACK-ID" not in str(result)


def test_get_music_track_requires_opaque_handle() -> None:
    result = get_music_track("music:track:123", runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_music_track_returns_exact_selected_metadata() -> None:
    search = search_music_tracks("Runtime", runner=_runner)
    handle = search["results"][0]["handle"]

    result = get_music_track(handle, runner=_runner)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Runtime Song"
    assert result["result"]["artist"] == "Runtime Artist"
    assert result["privacy"]["play_history_returned"] is False
    assert "RUNTIME-MUSIC-TRACK-ID" not in str(result)


def test_music_search_clamps_scan_limit() -> None:
    seen: dict[str, list[str]] = {}

    def runner(command: list[str], _timeout: float) -> MusicCommandResult:
        seen["command"] = command
        return MusicCommandResult(returncode=0, stdout=_track_record())

    result = search_music_tracks("Runtime", max_scan_items=999999, runner=runner)

    assert result["status"] == "ok"
    assert seen["command"][3] == "5000"
    assert result["query"]["max_scan_items"] == 5000


def test_music_search_skips_records_without_persistent_ids() -> None:
    def runner(_command: list[str], _timeout: float) -> MusicCommandResult:
        return MusicCommandResult(
            returncode=0,
            stdout=RECORD_SEPARATOR.join(
                [
                    _track_record(persistent_id="", database_id="raw-missing"),
                    _track_record(),
                ]
            ),
        )

    result = search_music_tracks("Runtime", runner=runner)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["title"] == "Runtime Song"
    assert "raw-missing" not in str(result)


def test_music_track_broad_query_is_rejected_before_runner() -> None:
    called = False

    def runner(command: list[str], timeout: float) -> MusicCommandResult:
        nonlocal called
        called = True
        return _runner(command, timeout)

    result = search_music_tracks("music", runner=runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"
    assert called is False


def test_search_music_playlists_and_get_exact_playlist() -> None:
    search = search_music_playlists("Runtime", runner=_runner)

    assert search["status"] == "ok"
    first = search["results"][0]
    assert first["handle"].startswith("music:playlist:v1:")
    assert first["title"] == "Runtime Playlist"
    assert first["track_count"] == 3
    assert first["playlist_tracks_returned"] is False
    assert "RUNTIME-MUSIC-PLAYLIST-ID" not in str(search)

    detail = get_music_playlist(first["handle"], runner=_runner)
    assert detail["status"] == "ok"
    assert detail["result"]["title"] == "Runtime Playlist"
    assert detail["result"]["duration_seconds"] == 456.7


def test_music_automation_errors_are_degraded() -> None:
    def runner(_command: list[str], _timeout: float) -> MusicCommandResult:
        return MusicCommandResult(returncode=1, stdout="", stderr="permission denied")

    result = search_music_tracks("Runtime", runner=runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "music_automation_error"

from __future__ import annotations

from local_apple_data.adapters.tv import (
    FIELD_SEPARATOR,
    RECORD_SEPARATOR,
    TVCommandResult,
    get_tv_item,
    get_tv_playlist,
    search_tv_items,
    search_tv_playlists,
)


def _item_record(
    persistent_id: str = "RUNTIME-TV-ITEM-ID",
    database_id: str = "123",
    title: str = "Runtime Episode",
    show: str = "Runtime Show",
    artist: str = "Runtime Studio",
    genre: str = "Runtime Genre",
    video_kind: str = "TV show",
    duration: str = "1234.5",
    season_number: str = "2",
    episode_number: str = "7",
    year: str = "2026",
) -> str:
    return FIELD_SEPARATOR.join(
        [
            persistent_id,
            database_id,
            title,
            show,
            artist,
            genre,
            video_kind,
            duration,
            season_number,
            episode_number,
            year,
        ]
    )


def _playlist_record(
    persistent_id: str = "RUNTIME-TV-PLAYLIST-ID",
    database_id: str = "456",
    title: str = "Runtime TV Playlist",
    kind: str = "user",
    item_count: str = "3",
    duration: str = "4567.8",
) -> str:
    return FIELD_SEPARATOR.join(
        [persistent_id, database_id, title, kind, item_count, duration]
    )


def _runner(command: list[str], _timeout: float) -> TVCommandResult:
    command_name = command[0]
    if command_name in {"search_items", "list_items"}:
        return TVCommandResult(
            returncode=0,
            stdout=RECORD_SEPARATOR.join(
                [
                    _item_record(),
                    _item_record(
                        persistent_id="SECOND-TV-ITEM-ID",
                        database_id="789",
                        title="Other Episode",
                    ),
                ]
            ),
        )
    if command_name in {"search_playlists", "list_playlists"}:
        return TVCommandResult(
            returncode=0,
            stdout=RECORD_SEPARATOR.join(
                [
                    _playlist_record(),
                    _playlist_record(
                        persistent_id="SECOND-TV-PLAYLIST-ID",
                        database_id="987",
                        title="Other TV Playlist",
                    ),
                ]
            ),
        )
    return TVCommandResult(returncode=1, stdout="", stderr="unsupported")


def test_search_tv_items_returns_metadata_without_raw_identifiers() -> None:
    result = search_tv_items("Runtime", runner=_runner)

    assert result["status"] == "ok"
    assert result["result_count"] == 2
    first = result["results"][0]
    assert first["handle"].startswith("tv:item:v1:")
    assert first["title"] == "Runtime Episode"
    assert first["show"] == "Runtime Show"
    assert first["duration_seconds"] == 1234.5
    assert first["season_number"] == 2
    assert first["episode_number"] == 7
    assert first["raw_identifier_returned"] is False
    assert first["file_path_returned"] is False
    assert first["video_content_returned"] is False
    assert first["artwork_returned"] is False
    assert first["description_returned"] is False
    assert first["playback_state_returned"] is False
    assert first["watched_state_returned"] is False
    assert "RUNTIME-TV-ITEM-ID" not in str(result)


def test_get_tv_item_requires_opaque_handle() -> None:
    result = get_tv_item("tv:item:123", runner=_runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_get_tv_item_returns_exact_selected_metadata() -> None:
    search = search_tv_items("Runtime", runner=_runner)
    handle = search["results"][0]["handle"]

    result = get_tv_item(handle, runner=_runner)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Runtime Episode"
    assert result["result"]["show"] == "Runtime Show"
    assert result["privacy"]["watched_state_returned"] is False
    assert "RUNTIME-TV-ITEM-ID" not in str(result)


def test_tv_search_clamps_scan_limit() -> None:
    seen: dict[str, list[str]] = {}

    def runner(command: list[str], _timeout: float) -> TVCommandResult:
        seen["command"] = command
        return TVCommandResult(returncode=0, stdout=_item_record())

    result = search_tv_items("Runtime", max_scan_items=999999, runner=runner)

    assert result["status"] == "ok"
    assert seen["command"][3] == "5000"
    assert result["query"]["max_scan_items"] == 5000


def test_tv_search_skips_records_without_persistent_ids() -> None:
    def runner(_command: list[str], _timeout: float) -> TVCommandResult:
        return TVCommandResult(
            returncode=0,
            stdout=RECORD_SEPARATOR.join(
                [
                    _item_record(persistent_id="", database_id="raw-missing"),
                    _item_record(),
                ]
            ),
        )

    result = search_tv_items("Runtime", runner=runner)

    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["results"][0]["title"] == "Runtime Episode"
    assert "raw-missing" not in str(result)


def test_tv_item_broad_query_is_rejected_before_runner() -> None:
    called = False

    def runner(command: list[str], timeout: float) -> TVCommandResult:
        nonlocal called
        called = True
        return _runner(command, timeout)

    result = search_tv_items("tv", runner=runner)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "broad_query"
    assert called is False


def test_search_tv_playlists_and_get_exact_playlist() -> None:
    search = search_tv_playlists("Runtime", runner=_runner)

    assert search["status"] == "ok"
    first = search["results"][0]
    assert first["handle"].startswith("tv:playlist:v1:")
    assert first["title"] == "Runtime TV Playlist"
    assert first["item_count"] == 3
    assert first["playlist_items_returned"] is False
    assert "RUNTIME-TV-PLAYLIST-ID" not in str(search)

    detail = get_tv_playlist(first["handle"], runner=_runner)
    assert detail["status"] == "ok"
    assert detail["result"]["title"] == "Runtime TV Playlist"
    assert detail["result"]["duration_seconds"] == 4567.8


def test_tv_automation_errors_are_degraded() -> None:
    def runner(_command: list[str], _timeout: float) -> TVCommandResult:
        return TVCommandResult(returncode=1, stdout="", stderr="permission denied")

    result = search_tv_items("Runtime", runner=runner)

    assert result["status"] == "degraded"
    assert result["warnings"][0]["code"] == "tv_automation_error"

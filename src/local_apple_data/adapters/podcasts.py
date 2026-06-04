from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..handles import is_opaque_handle, make_opaque_handle, opaque_handle_matches
from .sqlite_store import (
    StoreUnavailableError,
    connect_readonly,
    has_minimum_query_quality,
    like_contains_pattern,
    require_columns,
    schema_fingerprint,
)


DEFAULT_PODCASTS_DB = (
    Path.home()
    / "Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite"
)
PODCASTS_TABLES = ["ZMTPODCAST", "ZMTEPISODE"]
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
DEFAULT_CONTENT_CHARS = 4000
MAX_CONTENT_CHARS = 12000
SHOW_HANDLE_PREFIX = "podcasts:show"
EPISODE_HANDLE_PREFIX = "podcasts:episode"
BLOCKED_BROAD_QUERIES = {
    "all",
    "audio",
    "download",
    "downloaded",
    "episode",
    "episodes",
    "library",
    "listen",
    "listened",
    "podcast",
    "podcasts",
    "show",
    "shows",
    "transcript",
    "video",
}


def _privacy() -> dict[str, bool | str]:
    return {
        "content_inspected": False,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "metadata",
    }


def _detail_privacy(*, episode_description_returned: bool) -> dict[str, bool | str]:
    return {
        "content_inspected": episode_description_returned,
        "raw_rows_inspected": False,
        "credentials_inspected": False,
        "output_tier": "content" if episode_description_returned else "metadata",
        "episode_description_returned": episode_description_returned,
        "transcript_text_returned": False,
        "audio_content_returned": False,
    }


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _check_schema(connection) -> str:
    require_columns(
        connection,
        "ZMTPODCAST",
        {
            "Z_PK",
            "ZTITLE",
            "ZAUTHOR",
            "ZCATEGORY",
            "ZPROVIDER",
            "ZSUBSCRIBED",
            "ZHIDDEN",
            "ZLIBRARYEPISODESCOUNT",
            "ZDOWNLOADEDEPISODESCOUNT",
            "ZSAVEDEPISODESCOUNT",
            "ZNEWEPISODESCOUNT",
            "ZLASTDATEPLAYED",
            "ZUPDATEDDATE",
            "ZSTORECOLLECTIONID",
            "ZUUID",
            "ZFEEDURL",
            "ZWEBPAGEURL",
        },
    )
    require_columns(
        connection,
        "ZMTEPISODE",
        {
            "Z_PK",
            "ZPODCAST",
            "ZTITLE",
            "ZITUNESTITLE",
            "ZCLEANEDTITLE",
            "ZAUTHOR",
            "ZDURATION",
            "ZPUBDATE",
            "ZLASTDATEPLAYED",
            "ZPLAYHEAD",
            "ZHASBEENPLAYED",
            "ZPLAYCOUNT",
            "ZSAVED",
            "ZDOWNLOADPATH",
            "ZASSETURL",
            "ZEXPLICIT",
            "ZAUDIO",
            "ZVIDEO",
            "ZUUID",
            "ZGUID",
            "ZSTORETRACKID",
            "ZITEMDESCRIPTION",
            "ZITEMDESCRIPTIONWITHOUTHTML",
            "ZTRANSCRIPTIDENTIFIER",
            "ZFREETRANSCRIPTIDENTIFIER",
            "ZENTITLEDTRANSCRIPTIDENTIFIER",
            "ZWEBPAGEURL",
            "ZVISIBLE",
            "ZUSERDELETED",
            "ZFEEDDELETED",
        },
    )
    return schema_fingerprint(connection, PODCASTS_TABLES)


def check_podcasts_schema(*, db_path: Path = DEFAULT_PODCASTS_DB) -> dict[str, Any]:
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
    except StoreUnavailableError:
        return {
            "status": "degraded",
            "source": "podcasts",
            "schema_fingerprint": None,
            "tables_checked": PODCASTS_TABLES,
            "warnings": [
                _warning(
                    "podcasts_schema_unavailable",
                    "Apple Podcasts local schema could not be checked.",
                )
            ],
        }

    return {
        "status": "ok",
        "source": "podcasts",
        "schema_fingerprint": fingerprint,
        "tables_checked": PODCASTS_TABLES,
        "warnings": [],
    }


def search_podcasts(
    query: str,
    *,
    db_path: Path = DEFAULT_PODCASTS_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _empty_query_result()
    if not _is_specific_query(query):
        return _broad_query_result()

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    Z_PK AS show_id,
                    ZTITLE AS title,
                    ZAUTHOR AS author,
                    ZCATEGORY AS category,
                    ZPROVIDER AS provider,
                    ZSUBSCRIBED AS subscribed,
                    ZHIDDEN AS hidden,
                    ZLIBRARYEPISODESCOUNT AS library_episode_count,
                    ZDOWNLOADEDEPISODESCOUNT AS downloaded_episode_count,
                    ZSAVEDEPISODESCOUNT AS saved_episode_count,
                    ZNEWEPISODESCOUNT AS new_episode_count,
                    ZLASTDATEPLAYED AS last_played_at,
                    ZUPDATEDDATE AS updated_at,
                    ZSTORECOLLECTIONID AS store_collection_id,
                    ZUUID AS show_uuid,
                    ZFEEDURL AS feed_url,
                    ZWEBPAGEURL AS webpage_url
                FROM ZMTPODCAST
                WHERE COALESCE(ZTITLE, '') LIKE ? ESCAPE '\\'
                   OR COALESCE(ZAUTHOR, '') LIKE ? ESCAPE '\\'
                   OR COALESCE(ZCATEGORY, '') LIKE ? ESCAPE '\\'
                   OR COALESCE(ZPROVIDER, '') LIKE ? ESCAPE '\\'
                ORDER BY COALESCE(ZLASTDATEPLAYED, ZUPDATEDDATE, 0) DESC,
                         COALESCE(ZTITLE, '') ASC
                LIMIT ?
                """,
                (
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    like_contains_pattern(query),
                    bounded_limit,
                ),
            ).fetchall()
            episode_counts = _episode_counts(connection, [row["show_id"] for row in rows])
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=False)

    return {
        "schema_version": 1,
        "status": "ok",
        "source": "podcasts",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "query": {"scope": "show_title_author_category_or_provider", "limit": bounded_limit},
        "results": [
            _show_metadata(row, fingerprint, episode_counts=episode_counts) for row in rows
        ],
        "result_count": len(rows),
        "warnings": [],
    }


def get_podcast_show(
    handle: str,
    *,
    db_path: Path = DEFAULT_PODCASTS_DB,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, SHOW_HANDLE_PREFIX):
        return _invalid_handle_result("show", detail=True)

    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = _select_shows(connection)
            episode_counts = _episode_counts(connection, [row["show_id"] for row in rows])
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True)

    for row in rows:
        if opaque_handle_matches(handle, SHOW_HANDLE_PREFIX, fingerprint, _show_key(row)):
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "podcasts",
                "schema_fingerprint": fingerprint,
                "privacy": _privacy(),
                "result": _show_metadata(row, fingerprint, episode_counts=episode_counts),
                "result_count": 1,
                "warnings": [],
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "podcasts",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": None,
        "warnings": [],
    }


def list_podcast_episodes(
    handle: str,
    *,
    db_path: Path = DEFAULT_PODCASTS_DB,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, SHOW_HANDLE_PREFIX):
        return _invalid_handle_result("show", detail=True)

    bounded_limit = max(1, min(limit, MAX_LIMIT))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            show_rows = _select_shows(connection)
            show_row = _resolve_show_row(show_rows, fingerprint, handle)
            if show_row is None:
                return {
                    "schema_version": 1,
                    "status": "not_found",
                    "source": "podcasts",
                    "schema_fingerprint": fingerprint,
                    "privacy": _privacy(),
                    "result": None,
                    "warnings": [],
                }
            episode_rows = _select_episodes_for_show(
                connection,
                show_id=show_row["show_id"],
                limit=bounded_limit,
            )
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True)

    show = _show_metadata(show_row, fingerprint, episode_counts=None)
    show.update(
        {
            "episodes": [
                _episode_metadata(row, fingerprint, include_description=False)
                for row in episode_rows
            ],
            "episodes_returned": len(episode_rows),
            "episode_descriptions_returned": False,
            "transcript_text_returned": False,
            "audio_content_returned": False,
        }
    )
    return {
        "schema_version": 1,
        "status": "ok",
        "source": "podcasts",
        "schema_fingerprint": fingerprint,
        "privacy": _privacy(),
        "result": show,
        "result_count": len(episode_rows),
        "warnings": [],
    }


def get_podcast_episode(
    handle: str,
    *,
    db_path: Path = DEFAULT_PODCASTS_DB,
    max_chars: int = DEFAULT_CONTENT_CHARS,
) -> dict[str, Any]:
    if not is_opaque_handle(handle, EPISODE_HANDLE_PREFIX):
        return _invalid_handle_result("episode", detail=True, episode_detail=True)

    bounded_chars = max(1, min(max_chars, MAX_CONTENT_CHARS))
    try:
        with connect_readonly(db_path) as connection:
            fingerprint = _check_schema(connection)
            rows = _select_episodes(connection)
    except StoreUnavailableError as exc:
        return _store_degraded_result(exc, detail=True, episode_detail=True)

    for row in rows:
        if opaque_handle_matches(handle, EPISODE_HANDLE_PREFIX, fingerprint, _episode_key(row)):
            description = _clean_text(row["description_without_html"]) or _clean_text(
                row["description"]
            )
            description, truncated = _bounded_content(description, bounded_chars)
            result = _episode_metadata(
                row,
                fingerprint,
                include_description=bool(description),
            )
            result.update(
                {
                    "description": description,
                    "description_chars": len(description),
                    "description_truncated": truncated,
                    "episode_description_returned": bool(description),
                    "transcript_text_returned": False,
                    "audio_content_returned": False,
                }
            )
            warnings = []
            if truncated:
                warnings.append(
                    _warning("content_truncated", "Episode description was truncated.")
                )
            return {
                "schema_version": 1,
                "status": "ok",
                "source": "podcasts",
                "schema_fingerprint": fingerprint,
                "privacy": _detail_privacy(
                    episode_description_returned=bool(description),
                ),
                "result": result,
                "result_count": 1,
                "warnings": warnings,
            }

    return {
        "schema_version": 1,
        "status": "not_found",
        "source": "podcasts",
        "schema_fingerprint": fingerprint,
        "privacy": _detail_privacy(episode_description_returned=False),
        "result": None,
        "warnings": [],
    }


def _select_shows(connection) -> list[Any]:
    return connection.execute(
        """
        SELECT
            Z_PK AS show_id,
            ZTITLE AS title,
            ZAUTHOR AS author,
            ZCATEGORY AS category,
            ZPROVIDER AS provider,
            ZSUBSCRIBED AS subscribed,
            ZHIDDEN AS hidden,
            ZLIBRARYEPISODESCOUNT AS library_episode_count,
            ZDOWNLOADEDEPISODESCOUNT AS downloaded_episode_count,
            ZSAVEDEPISODESCOUNT AS saved_episode_count,
            ZNEWEPISODESCOUNT AS new_episode_count,
            ZLASTDATEPLAYED AS last_played_at,
            ZUPDATEDDATE AS updated_at,
            ZSTORECOLLECTIONID AS store_collection_id,
            ZUUID AS show_uuid,
            ZFEEDURL AS feed_url,
            ZWEBPAGEURL AS webpage_url
        FROM ZMTPODCAST
        ORDER BY COALESCE(ZLASTDATEPLAYED, ZUPDATEDDATE, 0) DESC,
                 COALESCE(ZTITLE, '') ASC
        """
    ).fetchall()


def _select_episodes(connection) -> list[Any]:
    return connection.execute(
        """
        SELECT
            e.Z_PK AS episode_id,
            e.ZPODCAST AS show_id,
            p.ZTITLE AS show_title,
            p.ZUUID AS show_uuid,
            e.ZTITLE AS title,
            e.ZITUNESTITLE AS itunes_title,
            e.ZCLEANEDTITLE AS cleaned_title,
            e.ZAUTHOR AS author,
            e.ZDURATION AS duration,
            e.ZPUBDATE AS published_at,
            e.ZLASTDATEPLAYED AS last_played_at,
            e.ZPLAYHEAD AS playhead,
            e.ZHASBEENPLAYED AS has_been_played,
            e.ZPLAYCOUNT AS play_count,
            e.ZSAVED AS saved,
            e.ZDOWNLOADPATH AS download_path,
            e.ZASSETURL AS asset_url,
            e.ZEXPLICIT AS explicit,
            e.ZAUDIO AS audio,
            e.ZVIDEO AS video,
            e.ZUUID AS episode_uuid,
            e.ZGUID AS guid,
            e.ZSTORETRACKID AS store_track_id,
            e.ZITEMDESCRIPTION AS description,
            e.ZITEMDESCRIPTIONWITHOUTHTML AS description_without_html,
            e.ZTRANSCRIPTIDENTIFIER AS transcript_identifier,
            e.ZFREETRANSCRIPTIDENTIFIER AS free_transcript_identifier,
            e.ZENTITLEDTRANSCRIPTIDENTIFIER AS entitled_transcript_identifier,
            e.ZWEBPAGEURL AS webpage_url
        FROM ZMTEPISODE e
        LEFT JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
        WHERE COALESCE(e.ZUSERDELETED, 0) = 0
          AND COALESCE(e.ZFEEDDELETED, 0) = 0
          AND COALESCE(e.ZVISIBLE, 1) != 0
        ORDER BY COALESCE(e.ZPUBDATE, e.ZLASTDATEPLAYED, 0) DESC,
                 COALESCE(e.ZTITLE, e.ZITUNESTITLE, '') ASC
        """
    ).fetchall()


def _select_episodes_for_show(connection, *, show_id: int, limit: int) -> list[Any]:
    return connection.execute(
        """
        SELECT
            e.Z_PK AS episode_id,
            e.ZPODCAST AS show_id,
            p.ZTITLE AS show_title,
            p.ZUUID AS show_uuid,
            e.ZTITLE AS title,
            e.ZITUNESTITLE AS itunes_title,
            e.ZCLEANEDTITLE AS cleaned_title,
            e.ZAUTHOR AS author,
            e.ZDURATION AS duration,
            e.ZPUBDATE AS published_at,
            e.ZLASTDATEPLAYED AS last_played_at,
            e.ZPLAYHEAD AS playhead,
            e.ZHASBEENPLAYED AS has_been_played,
            e.ZPLAYCOUNT AS play_count,
            e.ZSAVED AS saved,
            e.ZDOWNLOADPATH AS download_path,
            e.ZASSETURL AS asset_url,
            e.ZEXPLICIT AS explicit,
            e.ZAUDIO AS audio,
            e.ZVIDEO AS video,
            e.ZUUID AS episode_uuid,
            e.ZGUID AS guid,
            e.ZSTORETRACKID AS store_track_id,
            e.ZITEMDESCRIPTION AS description,
            e.ZITEMDESCRIPTIONWITHOUTHTML AS description_without_html,
            e.ZTRANSCRIPTIDENTIFIER AS transcript_identifier,
            e.ZFREETRANSCRIPTIDENTIFIER AS free_transcript_identifier,
            e.ZENTITLEDTRANSCRIPTIDENTIFIER AS entitled_transcript_identifier,
            e.ZWEBPAGEURL AS webpage_url
        FROM ZMTEPISODE e
        LEFT JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
        WHERE e.ZPODCAST = ?
          AND COALESCE(e.ZUSERDELETED, 0) = 0
          AND COALESCE(e.ZFEEDDELETED, 0) = 0
          AND COALESCE(e.ZVISIBLE, 1) != 0
        ORDER BY COALESCE(e.ZPUBDATE, e.ZLASTDATEPLAYED, 0) DESC,
                 COALESCE(e.ZTITLE, e.ZITUNESTITLE, '') ASC
        LIMIT ?
        """,
        (show_id, limit),
    ).fetchall()


def _episode_counts(connection, show_ids: list[int]) -> dict[int, int]:
    ids = [int(show_id) for show_id in show_ids if show_id is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(
        f"""
        SELECT ZPODCAST AS show_id, COUNT(*) AS episode_count
        FROM ZMTEPISODE
        WHERE COALESCE(ZUSERDELETED, 0) = 0
          AND COALESCE(ZFEEDDELETED, 0) = 0
          AND COALESCE(ZVISIBLE, 1) != 0
          AND ZPODCAST IN ({placeholders})
        GROUP BY ZPODCAST
        """,
        ids,
    ).fetchall()
    return {int(row["show_id"]): int(row["episode_count"] or 0) for row in rows}


def _resolve_show_row(rows: list[Any], fingerprint: str, handle: str) -> Any | None:
    for row in rows:
        if opaque_handle_matches(handle, SHOW_HANDLE_PREFIX, fingerprint, _show_key(row)):
            return row
    return None


def _show_metadata(
    row: Any,
    fingerprint: str,
    *,
    episode_counts: dict[int, int] | None,
) -> dict[str, Any]:
    result = {
        "handle": make_opaque_handle(SHOW_HANDLE_PREFIX, fingerprint, _show_key(row)),
        "title": _bounded_text(row["title"] or "Untitled", 300),
        "author": _bounded_text(row["author"] or "", 300),
        "category": _bounded_text(row["category"] or "", 120),
        "provider": _bounded_text(row["provider"] or "", 160),
        "subscribed": bool(row["subscribed"]) if row["subscribed"] is not None else False,
        "hidden": bool(row["hidden"]) if row["hidden"] is not None else False,
        "library_episode_count": _safe_int(row["library_episode_count"]),
        "downloaded_episode_count": _safe_int(row["downloaded_episode_count"]),
        "saved_episode_count": _safe_int(row["saved_episode_count"]),
        "new_episode_count": _safe_int(row["new_episode_count"]),
        "last_played_at": _apple_timestamp(row["last_played_at"]),
        "updated_at": _apple_timestamp(row["updated_at"]),
        "feed_url_returned": False,
        "webpage_url_returned": False,
        "raw_identifier_returned": False,
    }
    if episode_counts is not None:
        result["episode_count"] = episode_counts.get(int(row["show_id"]), 0)
    return result


def _episode_metadata(
    row: Any,
    fingerprint: str,
    *,
    include_description: bool,
) -> dict[str, Any]:
    return {
        "handle": make_opaque_handle(EPISODE_HANDLE_PREFIX, fingerprint, _episode_key(row)),
        "show_title": _bounded_text(row["show_title"] or "", 300),
        "title": _bounded_text(_episode_title(row), 300),
        "author": _bounded_text(row["author"] or "", 300),
        "duration_seconds": _safe_float(row["duration"]),
        "published_at": _apple_timestamp(row["published_at"]),
        "last_played_at": _apple_timestamp(row["last_played_at"]),
        "playhead_seconds": _safe_float(row["playhead"]),
        "has_been_played": bool(row["has_been_played"])
        if row["has_been_played"] is not None
        else False,
        "play_count": _safe_int(row["play_count"]),
        "saved": bool(row["saved"]) if row["saved"] is not None else False,
        "download_status": "downloaded" if _clean_text(row["download_path"]) else "unknown",
        "explicit": bool(row["explicit"]) if row["explicit"] is not None else False,
        "media_kind": "video" if bool(row["video"]) else "audio" if bool(row["audio"]) else "unknown",
        "transcript_status": "available" if _has_transcript(row) else "unknown",
        "description_returned": include_description,
        "transcript_text_returned": False,
        "audio_content_returned": False,
        "asset_url_returned": False,
        "enclosure_url_returned": False,
        "download_path_returned": False,
        "webpage_url_returned": False,
        "raw_identifier_returned": False,
    }


def _show_key(row: Any) -> str:
    for column in ("show_uuid", "store_collection_id"):
        value = _clean_text(row[column])
        if value:
            return f"{column}:{value}"
    return f"pk:{row['show_id']}"


def _episode_key(row: Any) -> str:
    for column in ("episode_uuid", "guid", "store_track_id"):
        value = _clean_text(row[column])
        if value:
            return f"{column}:{value}"
    return f"pk:{row['episode_id']}"


def _episode_title(row: Any) -> str:
    return (
        _clean_text(row["title"])
        or _clean_text(row["itunes_title"])
        or _clean_text(row["cleaned_title"])
        or "Untitled"
    )


def _has_transcript(row: Any) -> bool:
    return any(
        _clean_text(row[column])
        for column in (
            "transcript_identifier",
            "free_transcript_identifier",
            "entitled_transcript_identifier",
        )
    )


def _empty_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "podcasts",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "empty_query",
                "Apple Podcasts search requires a non-empty show title, author, category, or provider query.",
            )
        ],
    }


def _broad_query_result() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "source": "podcasts",
        "privacy": _privacy(),
        "results": [],
        "result_count": 0,
        "warnings": [
            _warning(
                "broad_query",
                "Apple Podcasts search requires a specific show title, author, category, or provider term.",
            )
        ],
    }


def _invalid_handle_result(
    kind: str,
    *,
    detail: bool,
    episode_detail: bool = False,
) -> dict[str, Any]:
    prefix = "podcasts:episode:v1" if kind == "episode" else "podcasts:show:v1"
    return {
        "schema_version": 1,
        "status": "error",
        "source": "podcasts",
        "privacy": _detail_privacy(episode_description_returned=False)
        if episode_detail
        else _privacy(),
        "result": None if detail else None,
        "results": [] if not detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "invalid_handle",
                f"Expected {prefix} opaque handle from search output.",
            )
        ],
    }


def _store_degraded_result(
    _exc: StoreUnavailableError,
    *,
    detail: bool,
    episode_detail: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "degraded",
        "source": "podcasts",
        "privacy": _detail_privacy(episode_description_returned=False)
        if episode_detail
        else _privacy(),
        "results": [] if not detail else None,
        "result": None if detail else None,
        "result_count": 0 if not detail else None,
        "warnings": [
            _warning(
                "podcasts_store_unavailable",
                "Apple Podcasts local store is missing, unreadable, or incompatible.",
            )
        ],
    }


def _is_specific_query(query: str) -> bool:
    compact = "".join(character.lower() for character in query if character.isalnum())
    if compact in BLOCKED_BROAD_QUERIES:
        return False
    return has_minimum_query_quality(query, min_alnum=2)


def _apple_timestamp(value: Any) -> str | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return (APPLE_EPOCH + timedelta(seconds=seconds)).isoformat()


def _bounded_content(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bounded_text(value: Any, limit: int) -> str:
    text = _clean_text(value)
    return text[:limit]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

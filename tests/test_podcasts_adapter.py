from __future__ import annotations

import sqlite3
from pathlib import Path

from local_apple_data.adapters.podcasts import (
    check_podcasts_schema,
    get_podcast_episode,
    get_podcast_show,
    list_podcast_episodes,
    search_podcasts,
)


def _make_podcasts_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "MTLibrary.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE ZMTPODCAST (
                Z_PK INTEGER PRIMARY KEY,
                ZTITLE TEXT,
                ZAUTHOR TEXT,
                ZCATEGORY TEXT,
                ZPROVIDER TEXT,
                ZSUBSCRIBED INTEGER,
                ZHIDDEN INTEGER,
                ZLIBRARYEPISODESCOUNT INTEGER,
                ZDOWNLOADEDEPISODESCOUNT INTEGER,
                ZSAVEDEPISODESCOUNT INTEGER,
                ZNEWEPISODESCOUNT INTEGER,
                ZLASTDATEPLAYED REAL,
                ZUPDATEDDATE REAL,
                ZUUID TEXT,
                ZSTORECOLLECTIONID TEXT,
                ZFEEDURL TEXT,
                ZWEBPAGEURL TEXT
            );
            CREATE TABLE ZMTEPISODE (
                Z_PK INTEGER PRIMARY KEY,
                ZPODCAST INTEGER,
                ZTITLE TEXT,
                ZITUNESTITLE TEXT,
                ZCLEANEDTITLE TEXT,
                ZAUTHOR TEXT,
                ZDURATION REAL,
                ZPUBDATE REAL,
                ZLASTDATEPLAYED REAL,
                ZPLAYHEAD REAL,
                ZHASBEENPLAYED INTEGER,
                ZPLAYCOUNT INTEGER,
                ZSAVED INTEGER,
                ZDOWNLOADPATH TEXT,
                ZASSETURL TEXT,
                ZEXPLICIT INTEGER,
                ZAUDIO INTEGER,
                ZVIDEO INTEGER,
                ZUUID TEXT,
                ZGUID TEXT,
                ZSTORETRACKID TEXT,
                ZITEMDESCRIPTION TEXT,
                ZITEMDESCRIPTIONWITHOUTHTML TEXT,
                ZTRANSCRIPTIDENTIFIER TEXT,
                ZFREETRANSCRIPTIDENTIFIER TEXT,
                ZENTITLEDTRANSCRIPTIDENTIFIER TEXT,
                ZWEBPAGEURL TEXT,
                ZVISIBLE INTEGER,
                ZUSERDELETED INTEGER,
                ZFEEDDELETED INTEGER
            );
            """
        )
        connection.execute(
            """
            INSERT INTO ZMTPODCAST
              (Z_PK, ZTITLE, ZAUTHOR, ZCATEGORY, ZPROVIDER, ZSUBSCRIBED, ZHIDDEN,
               ZLIBRARYEPISODESCOUNT, ZDOWNLOADEDEPISODESCOUNT, ZSAVEDEPISODESCOUNT,
               ZNEWEPISODESCOUNT, ZLASTDATEPLAYED, ZUPDATEDDATE, ZUUID,
               ZSTORECOLLECTIONID, ZFEEDURL, ZWEBPAGEURL)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "Synthetic Systems Show",
                "Ada Platform",
                "Technology",
                "Synthetic Provider",
                1,
                0,
                2,
                1,
                1,
                0,
                802310400.0,
                802310410.0,
                "SYNTHETIC-SHOW-UUID",
                "SYNTHETIC-COLLECTION-ID",
                "https://example.invalid/feed.xml",
                "https://example.invalid/show",
            ),
        )
        connection.execute(
            """
            INSERT INTO ZMTEPISODE
              (Z_PK, ZPODCAST, ZTITLE, ZITUNESTITLE, ZCLEANEDTITLE, ZAUTHOR,
               ZDURATION, ZPUBDATE, ZLASTDATEPLAYED, ZPLAYHEAD, ZHASBEENPLAYED,
               ZPLAYCOUNT, ZSAVED, ZDOWNLOADPATH, ZASSETURL, ZEXPLICIT, ZAUDIO,
               ZVIDEO, ZUUID, ZGUID, ZSTORETRACKID, ZITEMDESCRIPTION,
               ZITEMDESCRIPTIONWITHOUTHTML, ZTRANSCRIPTIDENTIFIER,
               ZFREETRANSCRIPTIDENTIFIER, ZENTITLEDTRANSCRIPTIDENTIFIER,
               ZWEBPAGEURL, ZVISIBLE, ZUSERDELETED, ZFEEDDELETED)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                10,
                1,
                "Synthetic Episode",
                "Synthetic iTunes Episode",
                "Synthetic Cleaned Episode",
                "Ada Platform",
                1200.0,
                802310300.0,
                802310350.0,
                300.0,
                0,
                2,
                1,
                "/private/synthetic/podcast.mp3",
                "https://example.invalid/audio.mp3",
                0,
                1,
                0,
                "SYNTHETIC-EPISODE-UUID",
                "SYNTHETIC-EPISODE-GUID",
                "SYNTHETIC-TRACK-ID",
                "<p>Fallback synthetic HTML description.</p>",
                "Synthetic plain description with details.",
                "SYNTHETIC-TRANSCRIPT-ID",
                "",
                "",
                "https://example.invalid/episode",
                1,
                0,
                0,
            ),
        )
        connection.execute(
            """
            INSERT INTO ZMTEPISODE
              (Z_PK, ZPODCAST, ZTITLE, ZITUNESTITLE, ZCLEANEDTITLE, ZAUTHOR,
               ZDURATION, ZPUBDATE, ZLASTDATEPLAYED, ZPLAYHEAD, ZHASBEENPLAYED,
               ZPLAYCOUNT, ZSAVED, ZDOWNLOADPATH, ZASSETURL, ZEXPLICIT, ZAUDIO,
               ZVIDEO, ZUUID, ZGUID, ZSTORETRACKID, ZITEMDESCRIPTION,
               ZITEMDESCRIPTIONWITHOUTHTML, ZTRANSCRIPTIDENTIFIER,
               ZFREETRANSCRIPTIDENTIFIER, ZENTITLEDTRANSCRIPTIDENTIFIER,
               ZWEBPAGEURL, ZVISIBLE, ZUSERDELETED, ZFEEDDELETED)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11,
                1,
                "Synthetic Deleted Episode",
                "",
                "",
                "Ada Platform",
                900.0,
                802310200.0,
                0.0,
                0.0,
                0,
                0,
                0,
                "",
                "https://example.invalid/deleted.mp3",
                0,
                1,
                0,
                "SYNTHETIC-DELETED-UUID",
                "SYNTHETIC-DELETED-GUID",
                "SYNTHETIC-DELETED-TRACK-ID",
                "Deleted description.",
                "Deleted plain description.",
                "",
                "",
                "",
                "https://example.invalid/deleted",
                1,
                1,
                0,
            ),
        )
    return db_path


def test_check_podcasts_schema_passes_for_synthetic_store(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)

    result = check_podcasts_schema(db_path=db_path)

    assert result["status"] == "ok"
    assert result["source"] == "podcasts"
    assert result["tables_checked"] == ["ZMTPODCAST", "ZMTEPISODE"]


def test_search_podcasts_returns_show_metadata_only(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)

    result = search_podcasts("Systems", db_path=db_path)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "show_title_author_category_or_provider"
    assert result["result_count"] == 1
    show = result["results"][0]
    assert show["handle"].startswith("podcasts:show:v1:")
    assert show["title"] == "Synthetic Systems Show"
    assert show["author"] == "Ada Platform"
    assert show["episode_count"] == 1
    assert show["feed_url_returned"] is False
    assert show["webpage_url_returned"] is False
    assert show["raw_identifier_returned"] is False
    assert "SYNTHETIC-SHOW-UUID" not in str(result)
    assert "SYNTHETIC-COLLECTION-ID" not in str(result)
    assert "example.invalid" not in str(result)
    assert "/private/synthetic" not in str(result)
    assert "Synthetic plain description" not in str(result)


def test_search_podcasts_rejects_empty_and_broad_queries(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)

    empty = search_podcasts(" ", db_path=db_path)
    broad = search_podcasts("Podcasts", db_path=db_path)

    assert empty["status"] == "error"
    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["status"] == "error"
    assert broad["warnings"][0]["code"] == "broad_query"


def test_get_podcast_show_returns_exact_metadata_by_handle(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)
    handle = search_podcasts("Systems", db_path=db_path)["results"][0]["handle"]

    result = get_podcast_show(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Synthetic Systems Show"
    assert result["result"]["episode_count"] == 1
    assert "SYNTHETIC-SHOW-UUID" not in str(result)
    assert "example.invalid" not in str(result)


def test_list_podcast_episodes_requires_exact_show_handle(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)

    result = list_podcast_episodes("podcasts:show:1", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_list_podcast_episodes_returns_metadata_only(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)
    handle = search_podcasts("Systems", db_path=db_path)["results"][0]["handle"]

    result = list_podcast_episodes(handle, db_path=db_path)

    assert result["status"] == "ok"
    assert result["result"]["episodes_returned"] == 1
    episode = result["result"]["episodes"][0]
    assert episode["handle"].startswith("podcasts:episode:v1:")
    assert episode["title"] == "Synthetic Episode"
    assert episode["transcript_status"] == "available"
    assert episode["description_returned"] is False
    assert episode["transcript_text_returned"] is False
    assert episode["audio_content_returned"] is False
    assert episode["download_path_returned"] is False
    assert "Synthetic plain description" not in str(result)
    assert "SYNTHETIC-TRANSCRIPT-ID" not in str(result)
    assert "SYNTHETIC-EPISODE-UUID" not in str(result)
    assert "example.invalid" not in str(result)
    assert "/private/synthetic" not in str(result)


def test_get_podcast_episode_returns_bounded_description_by_handle(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)
    show_handle = search_podcasts("Systems", db_path=db_path)["results"][0]["handle"]
    episode_handle = list_podcast_episodes(show_handle, db_path=db_path)["result"]["episodes"][0][
        "handle"
    ]

    result = get_podcast_episode(episode_handle, db_path=db_path, max_chars=10)

    assert result["status"] == "ok"
    assert result["privacy"]["episode_description_returned"] is True
    assert result["privacy"]["transcript_text_returned"] is False
    assert result["privacy"]["audio_content_returned"] is False
    assert result["result"]["description"] == "Synthetic "
    assert result["result"]["description_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"
    assert "SYNTHETIC-TRANSCRIPT-ID" not in str(result)
    assert "SYNTHETIC-EPISODE-UUID" not in str(result)
    assert "example.invalid" not in str(result)
    assert "/private/synthetic" not in str(result)


def test_get_podcast_episode_rejects_invalid_handle(tmp_path: Path) -> None:
    db_path = _make_podcasts_db(tmp_path)

    result = get_podcast_episode("podcasts:episode:1", db_path=db_path)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"

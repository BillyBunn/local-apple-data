from __future__ import annotations

import sqlite3
from pathlib import Path

from local_apple_data.adapters.books import (
    check_books_schema,
    get_book,
    list_book_annotations,
    search_books,
)


def _make_books_dbs(tmp_path: Path) -> tuple[Path, Path]:
    library_db = tmp_path / "BKLibrary.sqlite"
    annotations_db = tmp_path / "AEAnnotation.sqlite"
    with sqlite3.connect(library_db) as connection:
        connection.executescript(
            """
            CREATE TABLE ZBKLIBRARYASSET (
                Z_PK INTEGER PRIMARY KEY,
                ZASSETID TEXT,
                ZASSETGUID TEXT,
                ZSTOREID TEXT,
                ZTITLE TEXT,
                ZAUTHOR TEXT,
                ZGENRE TEXT,
                ZKIND TEXT,
                ZCONTENTTYPE INTEGER,
                ZISFINISHED INTEGER,
                ZREADINGPROGRESS REAL,
                ZLASTOPENDATE REAL,
                ZPATH TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO ZBKLIBRARYASSET
              (Z_PK, ZASSETID, ZASSETGUID, ZSTOREID, ZTITLE, ZAUTHOR, ZGENRE,
               ZKIND, ZCONTENTTYPE, ZISFINISHED, ZREADINGPROGRESS, ZLASTOPENDATE, ZPATH)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "SYNTHETIC-ASSET-ID-1",
                "SYNTHETIC-ASSET-GUID-1",
                "SYNTHETIC-STORE-ID-1",
                "Synthetic Systems Book",
                "Ada Platform",
                "Engineering",
                "ebook",
                1,
                0,
                0.42,
                802310400.0,
                "/private/synthetic/book.epub",
            ),
        )
        connection.execute(
            """
            INSERT INTO ZBKLIBRARYASSET
              (Z_PK, ZASSETID, ZASSETGUID, ZSTOREID, ZTITLE, ZAUTHOR, ZGENRE,
               ZKIND, ZCONTENTTYPE, ZISFINISHED, ZREADINGPROGRESS, ZLASTOPENDATE, ZPATH)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                2,
                "SYNTHETIC-ASSET-ID-2",
                "SYNTHETIC-ASSET-GUID-2",
                "SYNTHETIC-STORE-ID-2",
                "Synthetic Unmatched Book",
                "Grace Notes",
                "Reference",
                "pdf",
                2,
                1,
                1.0,
                802310300.0,
                "",
            ),
        )

    with sqlite3.connect(annotations_db) as connection:
        connection.executescript(
            """
            CREATE TABLE ZAEANNOTATION (
                Z_PK INTEGER PRIMARY KEY,
                ZANNOTATIONASSETID TEXT,
                ZANNOTATIONDELETED INTEGER,
                ZANNOTATIONTYPE INTEGER,
                ZANNOTATIONSTYLE INTEGER,
                ZANNOTATIONCREATIONDATE REAL,
                ZANNOTATIONMODIFICATIONDATE REAL,
                ZANNOTATIONNOTE TEXT,
                ZANNOTATIONREPRESENTATIVETEXT TEXT,
                ZANNOTATIONSELECTEDTEXT TEXT,
                ZANNOTATIONUUID TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO ZAEANNOTATION
              (Z_PK, ZANNOTATIONASSETID, ZANNOTATIONDELETED, ZANNOTATIONTYPE,
               ZANNOTATIONSTYLE, ZANNOTATIONCREATIONDATE, ZANNOTATIONMODIFICATIONDATE,
               ZANNOTATIONNOTE, ZANNOTATIONREPRESENTATIVETEXT, ZANNOTATIONSELECTEDTEXT,
               ZANNOTATIONUUID)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                10,
                "SYNTHETIC-ASSET-ID-1",
                0,
                1,
                2,
                802310410.0,
                802310420.0,
                "Synthetic user note.",
                "Representative surrounding text.",
                "Synthetic highlighted passage.",
                "SYNTHETIC-ANNOTATION-UUID-1",
            ),
        )
        connection.execute(
            """
            INSERT INTO ZAEANNOTATION
              (Z_PK, ZANNOTATIONASSETID, ZANNOTATIONDELETED, ZANNOTATIONTYPE,
               ZANNOTATIONSTYLE, ZANNOTATIONCREATIONDATE, ZANNOTATIONMODIFICATIONDATE,
               ZANNOTATIONNOTE, ZANNOTATIONREPRESENTATIVETEXT, ZANNOTATIONSELECTEDTEXT,
               ZANNOTATIONUUID)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11,
                "SYNTHETIC-ASSET-ID-1",
                1,
                1,
                2,
                802310410.0,
                802310430.0,
                "Deleted synthetic note.",
                "Deleted representative text.",
                "Deleted highlight.",
                "SYNTHETIC-ANNOTATION-UUID-DELETED",
            ),
        )
    return library_db, annotations_db


def test_check_books_schema_passes_for_synthetic_store(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)

    result = check_books_schema(library_db_path=library_db, annotations_db_path=annotations_db)

    assert result["status"] == "ok"
    assert result["source"] == "books"
    assert result["tables_checked"] == ["ZBKLIBRARYASSET", "ZAEANNOTATION"]


def test_search_books_returns_metadata_only(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)

    result = search_books("Systems", library_db_path=library_db, annotations_db_path=annotations_db)

    assert result["status"] == "ok"
    assert result["query"]["scope"] == "book_title_author_or_genre"
    assert result["result_count"] == 1
    book = result["results"][0]
    assert book["handle"].startswith("books:book:v1:")
    assert book["title"] == "Synthetic Systems Book"
    assert book["author"] == "Ada Platform"
    assert book["annotation_count"] == 1
    assert book["book_text_returned"] is False
    assert book["raw_identifier_returned"] is False
    assert "SYNTHETIC-ASSET-ID-1" not in str(result)
    assert "SYNTHETIC-ANNOTATION-UUID-1" not in str(result)
    assert "/private/synthetic" not in str(result)
    assert "Synthetic highlighted passage" not in str(result)


def test_search_books_rejects_empty_and_broad_queries(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)

    empty = search_books(" ", library_db_path=library_db, annotations_db_path=annotations_db)
    broad = search_books("Books", library_db_path=library_db, annotations_db_path=annotations_db)

    assert empty["status"] == "error"
    assert empty["warnings"][0]["code"] == "empty_query"
    assert broad["status"] == "error"
    assert broad["warnings"][0]["code"] == "broad_query"


def test_get_book_returns_exact_metadata_by_handle(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)
    handle = search_books("Systems", library_db_path=library_db, annotations_db_path=annotations_db)[
        "results"
    ][0]["handle"]

    result = get_book(handle, library_db_path=library_db, annotations_db_path=annotations_db)

    assert result["status"] == "ok"
    assert result["result"]["title"] == "Synthetic Systems Book"
    assert result["result"]["annotation_count"] == 1
    assert "SYNTHETIC-ASSET-ID-1" not in str(result)
    assert "/private/synthetic" not in str(result)


def test_get_book_rejects_invalid_handle(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)

    result = get_book("books:book:1", library_db_path=library_db, annotations_db_path=annotations_db)

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"


def test_list_book_annotations_requires_exact_book_handle(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)
    handle = search_books("Systems", library_db_path=library_db, annotations_db_path=annotations_db)[
        "results"
    ][0]["handle"]

    result = list_book_annotations(
        handle,
        library_db_path=library_db,
        annotations_db_path=annotations_db,
        max_chars=4000,
    )

    assert result["status"] == "ok"
    assert result["privacy"]["annotation_text_returned"] is True
    assert result["result"]["book_text_returned"] is False
    assert result["result"]["annotations_returned"] == 1
    annotation = result["result"]["annotations"][0]
    assert annotation["handle"].startswith("books:annotation:v1:")
    assert annotation["selected_text"] == "Synthetic highlighted passage."
    assert annotation["note_text"] == "Synthetic user note."
    assert "SYNTHETIC-ASSET-ID-1" not in str(result)
    assert "SYNTHETIC-ANNOTATION-UUID-1" not in str(result)
    assert "Deleted highlight" not in str(result)


def test_list_book_annotations_truncates_annotation_text(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)
    handle = search_books("Systems", library_db_path=library_db, annotations_db_path=annotations_db)[
        "results"
    ][0]["handle"]

    result = list_book_annotations(
        handle,
        library_db_path=library_db,
        annotations_db_path=annotations_db,
        max_chars=9,
    )

    assert result["status"] == "ok"
    assert result["result"]["annotation_text_truncated"] is True
    assert result["warnings"][0]["code"] == "content_truncated"
    assert result["result"]["annotations"][0]["selected_text"] == "Synthetic"


def test_list_book_annotations_rejects_invalid_handle(tmp_path: Path) -> None:
    library_db, annotations_db = _make_books_dbs(tmp_path)

    result = list_book_annotations(
        "books:book:1",
        library_db_path=library_db,
        annotations_db_path=annotations_db,
    )

    assert result["status"] == "error"
    assert result["warnings"][0]["code"] == "invalid_handle"

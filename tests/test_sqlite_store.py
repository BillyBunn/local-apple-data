from __future__ import annotations

from local_apple_data.adapters.sqlite_store import (
    has_minimum_query_quality,
    like_contains_pattern,
)


def test_like_contains_pattern_escapes_sql_wildcards() -> None:
    assert like_contains_pattern("%_\\") == r"%\%\_\\%"


def test_has_minimum_query_quality_blocks_wildcards_and_one_character() -> None:
    assert has_minimum_query_quality("%") is False
    assert has_minimum_query_quality("_") is False
    assert has_minimum_query_quality("a") is False
    assert has_minimum_query_quality("ai") is True

from datetime import datetime, timedelta, timezone

import pytest

from app.memory import CURRENT_SQL_FILTER, is_recallable

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def row(**overrides) -> dict:
    base = {"distance": 0.2, "superseded_by": None, "valid_until": None}
    return base | overrides


@pytest.mark.parametrize(
    "candidate,expected",
    [
        (row(), True),
        (row(valid_until=NOW - timedelta(days=1)), False),
        (row(valid_until=NOW + timedelta(days=1)), True),
        (row(superseded_by="another-uuid"), False),
        (row(distance=None), False),
    ],
    ids=[
        "current",
        "valid_until-expired",
        "valid_until-future",
        "superseded",
        "without-embedding",
    ],
)
def test_whether_a_candidate_is_recallable(candidate, expected):
    assert is_recallable(candidate, NOW) is expected


def test_valid_until_as_an_iso_string():
    expired = row(valid_until=(NOW - timedelta(days=1)).isoformat())
    assert is_recallable(expired, NOW) is False


def test_the_sql_filter_covers_the_same_fields_as_the_predicate():
    assert "valid_until" in CURRENT_SQL_FILTER
    assert "superseded_by" in CURRENT_SQL_FILTER

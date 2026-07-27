from datetime import datetime, timedelta, timezone

from app.config import settings
from app.memory import age_penalty, rank_score

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def test_age_penalty_saturates_at_one():
    assert age_penalty(days_ago(365), NOW) == 1.0
    assert age_penalty(days_ago(5000), NOW) == 1.0
    assert age_penalty(NOW, NOW) == 0.0


def test_quality_beats_recency_at_the_same_distance():
    old_and_good = rank_score(0.30, quality_score=1.0, created_at=days_ago(300))
    recent_and_bad = rank_score(0.30, quality_score=-1.0, created_at=days_ago(1))
    assert old_and_good < recent_and_bad


def test_age_does_not_dominate_similarity():
    close_and_old = rank_score(0.10, quality_score=0.0, created_at=days_ago(5000))
    far_and_new = rank_score(0.60, quality_score=0.0, created_at=NOW)
    assert close_and_old < far_and_new


def test_lower_distance_wins_all_else_being_equal():
    assert rank_score(0.10, 0.0, NOW) < rank_score(0.20, 0.0, NOW)


def test_thumbs_down_weighs_more_than_thumbs_up():
    assert settings.feedback_down > settings.feedback_up

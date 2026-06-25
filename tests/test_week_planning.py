"""Behavior tests for ``planned_weeks`` — which weeks a season's fetch covers.

Pure function, fully offline. It must be tolerant of Yahoo's metadata quirks:
the 2020 COVID season returns bogus ``start=end=0`` bounds for some leagues, and
a season still in progress must not fetch weeks that haven't happened yet.
"""

from __future__ import annotations


def test_completed_season_covers_full_range():
    from fetch_all import planned_weeks

    weeks = planned_weeks({"start_week": 1, "end_week": 23, "current_week": 23})

    assert weeks == list(range(1, 24))


def test_in_progress_season_caps_at_current_week():
    from fetch_all import planned_weeks

    # Season scheduled through week 23 but only week 10 has happened.
    weeks = planned_weeks({"start_week": 1, "end_week": 23, "current_week": 10})

    assert weeks == list(range(1, 11))


def test_2020_bogus_bounds_fall_back_to_one_through_current():
    from fetch_all import planned_weeks

    # The 2020 COVID season returns start=end=0 for some leagues; we still want
    # weeks 1..current_week rather than nothing.
    weeks = planned_weeks({"start_week": 0, "end_week": 0, "current_week": 4})

    assert weeks == [1, 2, 3, 4]


def test_no_usable_bounds_returns_empty():
    from fetch_all import planned_weeks

    # No metadata at all (all zero/missing) → nothing to fetch, not a bogus range.
    assert planned_weeks({}) == []
    assert planned_weeks({"start_week": 0, "end_week": 0, "current_week": 0}) == []


def test_current_week_past_end_does_not_extend_range():
    from fetch_all import planned_weeks

    # current_week running past the scheduled end (off-season) must not invent
    # weeks beyond end_week — the cap only ever shrinks the range.
    weeks = planned_weeks({"start_week": 1, "end_week": 23, "current_week": 30})

    assert weeks == list(range(1, 24))

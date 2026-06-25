"""Behavior tests for the real weekly per-player stats reconstruction.

Yahoo serves no true per-week per-player stats for MLB — only ``season``
(cumulative) and ``date`` (single day) coverage. A faithful week is therefore
the *sum of its days*, and only for **counting** stats: rate stats (AVG, ERA,
WHIP, OBP, K/9, ...) can't be summed and their components aren't tracked, so
weekly covers counting categories only. These pure helpers do the date math,
the rate-stat exclusion, the day-summing, and decide which weeks a run needs
to (re)compute. All fully offline.
"""

from __future__ import annotations


# -- counting_stat_ids: drop rate stats by global Yahoo stat-id ------------- #
def test_counting_stat_ids_excludes_rate_stats():
    from fetch_all import counting_stat_ids

    # 12239's categories: R,HR,RBI,SB,AVG,W,SV,K,ERA,WHIP.
    cats = {"scoring_stat_ids": ["7", "12", "13", "16", "3", "28", "32", "42", "26", "27"]}

    assert counting_stat_ids(cats) == ["7", "12", "13", "16", "28", "32", "42"]


def test_counting_stat_ids_handles_extra_league_categories():
    from fetch_all import counting_stat_ids

    # 14078 adds H, XBH, L, BB, QS, SV+H (counting) and OBP, K/9 (rate).
    cats = {"scoring_stat_ids": ["7", "8", "12", "13", "16", "21", "3", "4", "61",
                                 "28", "29", "39", "42", "26", "27", "57", "83", "89"]}

    counting = counting_stat_ids(cats)

    assert "3" not in counting and "4" not in counting   # AVG, OBP
    assert "26" not in counting and "27" not in counting  # ERA, WHIP
    assert "57" not in counting                            # K/9
    assert counting == ["7", "8", "12", "13", "16", "21", "61",
                        "28", "29", "39", "42", "83", "89"]


def test_counting_stat_ids_empty_when_no_categories():
    from fetch_all import counting_stat_ids

    assert counting_stat_ids({}) == []
    assert counting_stat_ids({"scoring_stat_ids": []}) == []


# -- week_dates: inclusive calendar days of a fantasy week ------------------- #
def test_week_dates_full_week_is_seven_inclusive_days():
    from fetch_all import week_dates

    dates = week_dates("2026-04-20", "2026-04-26")

    assert dates == ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23",
                     "2026-04-24", "2026-04-25", "2026-04-26"]


def test_week_dates_partial_opening_week():
    from fetch_all import week_dates

    # Week 1 of 2026 is a short 5-day week.
    assert week_dates("2026-03-25", "2026-03-29") == [
        "2026-03-25", "2026-03-26", "2026-03-27", "2026-03-28", "2026-03-29"]


def test_week_dates_single_day():
    from fetch_all import week_dates

    assert week_dates("2026-05-01", "2026-05-01") == ["2026-05-01"]


# -- sum_counting_stats: add daily lines, counting stats only --------------- #
def test_sum_counting_stats_adds_days_and_skips_rate():
    from fetch_all import sum_counting_stats

    counting = ["7", "12"]  # R, HR (3 = AVG is a rate stat, must be ignored)
    days = [
        {"469.p.1": {"7": 1.0, "12": 0.0, "3": 0.400}},
        {"469.p.1": {"7": 2.0, "12": 1.0, "3": 0.333}},
        {"469.p.1": {"7": 0.0, "12": 1.0, "3": 0.000}},
    ]

    out = sum_counting_stats(days, counting)

    assert out == {"469.p.1": {"7": 3.0, "12": 2.0}}
    assert "3" not in out["469.p.1"]  # rate stat never accumulated


def test_sum_counting_stats_player_rostered_only_some_days():
    from fetch_all import sum_counting_stats

    counting = ["7"]
    days = [
        {"469.p.1": {"7": 1.0}},                     # only p.1 today
        {"469.p.1": {"7": 1.0}, "469.p.2": {"7": 4.0}},  # p.2 added
    ]

    out = sum_counting_stats(days, counting)

    assert out == {"469.p.1": {"7": 2.0}, "469.p.2": {"7": 4.0}}


def test_sum_counting_stats_ignores_non_numeric_values():
    from fetch_all import sum_counting_stats

    # Yahoo can return "-" (already coerced) or stray strings; never crash.
    days = [
        {"469.p.1": {"7": 2.0, "12": "-"}},
        {"469.p.1": {"7": 1.0, "12": 3.0}},
    ]

    out = sum_counting_stats(days, ["7", "12"])

    assert out == {"469.p.1": {"7": 3.0, "12": 3.0}}


def test_sum_counting_stats_empty_days():
    from fetch_all import sum_counting_stats

    assert sum_counting_stats([], ["7"]) == {}
    assert sum_counting_stats([{}, {}], ["7"]) == {}


# -- weeks_needing_compute: refresh recomputes only the live edge ----------- #
def test_weeks_needing_compute_recomputes_current_and_lookback():
    from fetch_all import weeks_needing_compute

    # Daily refresh mid-season: weeks 1..10 already frozen on disk, current=10.
    planned = list(range(1, 11))
    existing = [str(w) for w in range(1, 11)]

    # Recompute the in-progress week and the one just behind it (boundary settle).
    assert weeks_needing_compute(planned, current_week=10, existing=existing) == [9, 10]


def test_weeks_needing_compute_fills_missing_weeks():
    from fetch_all import weeks_needing_compute

    # A prior run died after week 6; weeks 7,8 never got written. Backfill the
    # gap even though they're behind the lookback window.
    planned = list(range(1, 11))
    existing = [str(w) for w in range(1, 7)]  # 1..6 present, 7..10 missing

    assert weeks_needing_compute(planned, current_week=10, existing=existing) == [7, 8, 9, 10]


def test_weeks_needing_compute_nothing_on_disk_does_all():
    from fetch_all import weeks_needing_compute

    planned = list(range(1, 6))

    assert weeks_needing_compute(planned, current_week=5, existing=[]) == [1, 2, 3, 4, 5]

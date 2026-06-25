"""Behavior tests for ``_compute_weekly_counting`` orchestration (offline).

A fake client supplies canned game-week date ranges and per-day roster stats;
we assert the orchestration sums the right days into the right weeks, keeps only
counting stats, and — on an incremental refresh — recomputes just the live edge
while preserving weeks already frozen on disk.
"""

from __future__ import annotations

import json


class FakeClient:
    """Minimal stand-in for YahooClient's weekly-fetch surface.

    ``daily`` maps an ISO date to the league-wide ``{player_key: {stat_id: val}}``
    line returned for every team that day (same line per team here for brevity).
    ``records`` logs which dates were actually fetched, to prove freezing.
    """

    def __init__(self, game_weeks, daily):
        self._game_weeks = game_weeks
        self._daily = daily
        self.records = []

    def fetch_game_weeks(self, league_id, game_key):
        return self._game_weeks

    def fetch_roster_stats_by_date(self, team_id, league_id, game_key, day):
        self.records.append(day)
        return self._daily.get(day, {})


def _stat_categories(scoring_ids):
    return {"scoring_stat_ids": scoring_ids}


def test_full_rebuild_sums_days_per_week_counting_only(tmp_path):
    from fetch_all import _compute_weekly_counting

    descriptor = {"start_week": 1, "end_week": 2, "current_week": 2, "league_id": "L", "game_key": "469"}
    game_weeks = {1: ("2026-03-25", "2026-03-26"), 2: ("2026-03-27", "2026-03-28")}
    daily = {
        "2026-03-25": {"p.1": {"7": 1.0, "12": 0.0, "3": 0.5}},   # R, HR, AVG(rate)
        "2026-03-26": {"p.1": {"7": 2.0, "12": 1.0, "3": 0.4}},
        "2026-03-27": {"p.1": {"7": 0.0, "12": 1.0, "3": 0.0}},
        "2026-03-28": {"p.1": {"7": 3.0, "12": 0.0, "3": 1.0}},
    }
    client = FakeClient(game_weeks, daily)
    teams = [{"team_id": "1", "name": "Team One"}]

    weekly, recomputed = _compute_weekly_counting(
        client, teams, descriptor, _stat_categories(["7", "12", "3"]), tmp_path,
        recompute_all_weeks=True)

    assert recomputed == 2
    # Week 1 = 03-25 + 03-26; week 2 = 03-27 + 03-28. AVG (rate) excluded entirely.
    assert weekly == {
        "1": {"1": {"p.1": {"7": 3.0, "12": 1.0}}},
        "2": {"1": {"p.1": {"7": 3.0, "12": 1.0}}},
    }


def test_incremental_refresh_freezes_old_weeks(tmp_path):
    from fetch_all import _compute_weekly_counting

    # Three-week season, currently in week 3. Weeks 1 & 2 already on disk.
    descriptor = {"start_week": 1, "end_week": 3, "current_week": 3, "league_id": "L", "game_key": "469"}
    game_weeks = {1: ("2026-03-25", "2026-03-25"),
                  2: ("2026-03-26", "2026-03-26"),
                  3: ("2026-03-27", "2026-03-27")}
    daily = {
        "2026-03-26": {"p.1": {"7": 5.0}},   # week 2 (lookback edge)
        "2026-03-27": {"p.1": {"7": 9.0}},   # week 3 (current)
    }
    # Prior run froze weeks 1 and 2 on disk with sentinel values.
    (tmp_path / "player_stats.json").write_text(json.dumps({
        "weekly": {
            "1": {"1": {"p.1": {"7": 111.0}}},
            "2": {"1": {"p.1": {"7": 222.0}}},
        }
    }), encoding="utf-8")
    client = FakeClient(game_weeks, daily)
    teams = [{"team_id": "1", "name": "Team One"}]

    weekly, recomputed = _compute_weekly_counting(
        client, teams, descriptor, _stat_categories(["7"]), tmp_path,
        recompute_all_weeks=False)

    # Only current (3) + lookback (2) recomputed; week 1 kept from disk untouched.
    assert recomputed == 2
    assert weekly["1"] == {"1": {"p.1": {"7": 111.0}}}          # frozen sentinel
    assert weekly["2"] == {"1": {"p.1": {"7": 5.0}}}            # recomputed live
    assert weekly["3"] == {"1": {"p.1": {"7": 9.0}}}
    # Week 1's date was never fetched — proof it was frozen, not recomputed.
    assert "2026-03-25" not in client.records


def test_no_counting_stats_yields_empty(tmp_path):
    from fetch_all import _compute_weekly_counting

    descriptor = {"start_week": 1, "end_week": 1, "current_week": 1, "league_id": "L", "game_key": "469"}
    client = FakeClient({1: ("2026-03-25", "2026-03-25")}, {})
    teams = [{"team_id": "1", "name": "Team One"}]

    # Only a rate stat scored → nothing summable → empty weekly, no fetches.
    weekly, recomputed = _compute_weekly_counting(
        client, teams, descriptor, _stat_categories(["3"]), tmp_path,
        recompute_all_weeks=True)

    assert weekly == {} and recomputed == 0
    assert client.records == []

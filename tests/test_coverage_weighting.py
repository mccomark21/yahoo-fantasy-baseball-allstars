"""Behavior tests for roster-week-weighted coverage.

A retired/unreachable player should only drag down a season's coverage in
proportion to how much of the season they were actually rostered. A September
bench add who later retired must not, on its own, sink an otherwise-complete
season below the gate.

Duration is sampled from a handful of evenly-spaced weeks (not every week) to
keep the backfill's API cost down.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# planned_sample_weeks: evenly-spaced weeks to probe rosters at
# --------------------------------------------------------------------------- #
def test_sample_weeks_are_evenly_spaced_across_the_season():
    from fetch_all import planned_sample_weeks

    weeks = planned_sample_weeks({"start_week": 1, "end_week": 25, "current_week": 25},
                                 count=5)

    # Both ends included, spread evenly between.
    assert weeks == [1, 7, 13, 19, 25]


def test_sample_weeks_fewer_than_count_returns_all():
    from fetch_all import planned_sample_weeks

    # A short season (3 weeks) with count=5 → just probe every week, no dups.
    weeks = planned_sample_weeks({"start_week": 1, "end_week": 3, "current_week": 3},
                                 count=5)
    assert weeks == [1, 2, 3]


def test_sample_weeks_degenerate_seasons():
    from fetch_all import planned_sample_weeks

    # No usable week bounds → nothing to sample.
    assert planned_sample_weeks({}, count=5) == []
    # count<=0 is meaningless → empty.
    assert planned_sample_weeks({"start_week": 1, "end_week": 25, "current_week": 25},
                                count=0) == []


# --------------------------------------------------------------------------- #
# _historical_season_totals: weighted coverage
# --------------------------------------------------------------------------- #
class _FakeStatsClient:
    """Returns canned current-game stats; some ids are unreachable (retired)."""

    def __init__(self, stats_by_id, unreachable):
        self._stats_by_id = stats_by_id
        self._unreachable = set(unreachable)

    def fetch_current_game_season_stats(self, ids, season, cur_league_id, cur_game_key):
        wanted = {str(i) for i in ids}
        return ({k: v for k, v in self._stats_by_id.items() if k in wanted},
                self._unreachable & wanted)


def _roster(*players):
    return [{"team_id": "t1", "name": "Team One", "players": list(players)}]


def test_weighted_coverage_discounts_a_briefly_rostered_retiree():
    import fetch_all

    # One full-season reachable star, one retiree rostered only ~1/5 of weeks.
    roster_teams = _roster(
        {"player_id": "8967", "player_key": "404.p.8967", "name": "Full Season Star"},
        {"player_id": "9999", "player_key": "404.p.9999", "name": "Sept Bench Add"},
    )
    client = _FakeStatsClient(stats_by_id={"8967": {"7": "89"}}, unreachable={"9999"})
    weights = {"8967": 1.0, "9999": 0.2}

    season_totals, coverage = fetch_all._historical_season_totals(
        client, roster_teams, season=2021, cur_league_id="12239",
        cur_game_key="469", weights=weights)

    # Head count is still 1/2, but the gate rate is weighted: 1.0 / (1.0 + 0.2).
    assert coverage["total"] == 2
    assert coverage["reachable"] == 1
    assert coverage["rate"] == round(1.0 / 1.2, 6)
    assert coverage["unreachable"] == [{"player_id": "9999", "name": "Sept Bench Add"}]
    # Reachable star's stats still mapped onto the historical key.
    assert season_totals["t1"]["404.p.8967"] == {"7": "89"}


def test_all_zero_weights_fall_back_to_head_count_ratio():
    import fetch_all

    # If sampling produced no weight for anyone, don't report 0% — fall back to
    # the plain head-count ratio (here 1 of 2 reachable = 0.5).
    roster_teams = _roster(
        {"player_id": "8967", "player_key": "404.p.8967", "name": "Reachable"},
        {"player_id": "9999", "player_key": "404.p.9999", "name": "Retired"},
    )
    client = _FakeStatsClient(stats_by_id={"8967": {"7": "89"}}, unreachable={"9999"})

    _, coverage = fetch_all._historical_season_totals(
        client, roster_teams, season=2021, cur_league_id="12239",
        cur_game_key="469", weights={"8967": 0.0, "9999": 0.0})

    assert coverage["rate"] == 0.5


# --------------------------------------------------------------------------- #
# _roster_week_weights: sample weekly rosters → per-player season share
# --------------------------------------------------------------------------- #
class _FakeWeeklyRosterClient:
    """Serves a different league roster per week via fetch_league_rosters."""

    def __init__(self, rosters_by_week):
        self._rosters_by_week = rosters_by_week
        self.weeks_fetched = []

    def fetch_league_rosters(self, league_id, game_key, week):
        self.weeks_fetched.append(week)
        ids = self._rosters_by_week.get(week, [])
        return [{"team_id": "t1", "name": "Team One",
                 "players": [{"player_id": pid} for pid in ids]}]


def test_roster_week_weights_reflect_season_share():
    import fetch_all

    descriptor = {"start_week": 1, "end_week": 5, "current_week": 5}
    end_roster = _roster(
        {"player_id": "8967", "player_key": "404.p.8967", "name": "Full Season"},
        {"player_id": "9999", "player_key": "404.p.9999", "name": "Late Add"},
    )
    # 8967 rostered all five weeks; 9999 only shows up in the final week.
    client = _FakeWeeklyRosterClient({
        1: ["8967"], 2: ["8967"], 3: ["8967"], 4: ["8967"], 5: ["8967", "9999"],
    })

    weights = fetch_all._roster_week_weights(
        client, end_roster, descriptor, league_id="6791", game_key="404")

    assert client.weeks_fetched == [1, 2, 3, 4, 5]
    assert weights == {"8967": 1.0, "9999": 0.2}


# --------------------------------------------------------------------------- #
# fetch_season: weighting flips a borderline season from SKIP to KEEP
# --------------------------------------------------------------------------- #
class _FakeGateClient:
    """Full client stand-in for one historical season's fetch_season path.

    ``end_roster`` is the single team's end-of-season roster; ``reachable_ids``
    get canned stats. ``rosters_by_week`` drives the duration sampling.
    """

    def __init__(self, end_roster, reachable_ids, rosters_by_week):
        self._end_roster = end_roster
        self._reachable = set(reachable_ids)
        self._rosters_by_week = rosters_by_week

    def fetch_stat_categories(self, league_id, game_key, season):
        return {"league_id": league_id, "game_key": game_key, "season": season,
                "stats": [], "scoring_stat_ids": []}

    def fetch_teams(self, league_id, game_key):
        return [{"team_id": "t1", "team_key": f"{game_key}.l.{league_id}.t.1", "name": "Team One"}]

    def fetch_roster(self, team_id, league_id, game_key, week):
        return self._end_roster

    def fetch_league_rosters(self, league_id, game_key, week):
        ids = self._rosters_by_week.get(week, [])
        return [{"team_id": "t1", "name": "Team One",
                 "players": [{"player_id": pid} for pid in ids]}]

    def fetch_current_game_season_stats(self, ids, season, cur_league_id, cur_game_key):
        wanted = {str(i) for i in ids}
        stats = {pid: {"7": "10"} for pid in wanted if pid in self._reachable}
        return stats, (wanted - self._reachable)

    def fetch_matchups(self, league_id, game_key, weeks):
        return []


_GATE_DESCRIPTOR = {
    "season": 2021, "game_key": "404", "league_id": "6791",
    "start_week": 1, "end_week": 5, "current_week": 5,
}


def test_weighting_keeps_a_season_a_head_count_would_skip(tmp_path, monkeypatch):
    import common
    import fetch_all
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    # End roster: one full-season reachable star + one retiree added in week 5.
    end_roster = [
        {"player_id": "8967", "player_key": "404.p.8967", "name": "Full Season Star"},
        {"player_id": "9999", "player_key": "404.p.9999", "name": "Sept Bench Add"},
    ]
    # Head count = 1/2 = 50% → would SKIP. But the retiree is rostered only 1 of
    # 5 sampled weeks (weight 0.2), so weighted coverage = 1.0/1.2 ≈ 83% → KEEP.
    client = _FakeGateClient(
        end_roster, reachable_ids={"8967"},
        rosters_by_week={1: ["8967"], 2: ["8967"], 3: ["8967"],
                         4: ["8967"], 5: ["8967", "9999"]})

    written = fetch_all.fetch_season(
        client, "12239", _GATE_DESCRIPTOR, cur_game_key="469", cur_league_id="12239")

    assert written is True
    player_stats = common.load_json(tmp_path / "12239" / "2021" / "player_stats.json")
    assert player_stats["coverage"]["rate"] == round(1.0 / 1.2, 6)
    assert player_stats["coverage"]["total"] == 2


def test_season_between_75_and_80_percent_is_kept(tmp_path, monkeypatch):
    import common
    import fetch_all
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    # 3 full-season reachable players + 1 retiree rostered 4 of 5 weeks (w=0.8).
    # Weighted coverage = 3.0 / 3.8 ≈ 78.9% — below the old 80% bar, kept at 75%.
    end_roster = [
        {"player_id": "8967", "player_key": "404.p.8967", "name": "A"},
        {"player_id": "8968", "player_key": "404.p.8968", "name": "B"},
        {"player_id": "8969", "player_key": "404.p.8969", "name": "C"},
        {"player_id": "9999", "player_key": "404.p.9999", "name": "Retiree"},
    ]
    full = ["8967", "8968", "8969"]
    client = _FakeGateClient(
        end_roster, reachable_ids=set(full),
        rosters_by_week={1: full, 2: full + ["9999"], 3: full + ["9999"],
                         4: full + ["9999"], 5: full + ["9999"]})

    written = fetch_all.fetch_season(
        client, "12239", _GATE_DESCRIPTOR, cur_game_key="469", cur_league_id="12239")

    assert written is True
    rate = common.load_json(tmp_path / "12239" / "2021" / "player_stats.json")["coverage"]["rate"]
    assert 0.75 <= rate < 0.80

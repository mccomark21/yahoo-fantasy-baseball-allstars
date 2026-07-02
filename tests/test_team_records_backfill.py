"""Behavior tests for the team-records-only historical fetch path (issue #40).

Team-level season totals and matchups survive Yahoo's game archival and never
touch individual players, so Team Records can reach back further than the
player-facing views. ``fetch_team_records_season`` fetches only those inputs and
**bypasses the ≥MIN_COVERAGE player gate** that drops pre-2021 seasons on the
full path; ``run_team_records_backfill`` fills only the *gap* seasons the full
backfill left behind, never clobbering a fully-fetched season already on disk.
"""

from __future__ import annotations

import common
import fetch_all


# --------------------------------------------------------------------------- #
# fetch_team_records_season — minimal writes, no coverage gate
# --------------------------------------------------------------------------- #
class _FakeClient:
    """A stand-in for YahooClient exposing only what the lite path calls."""

    def __init__(self, team_stats, matchups):
        self._team_stats = team_stats      # team_id -> {stat_id: value}
        self._matchups = matchups

    def fetch_stat_categories(self, league_id, game_key, season):
        return {"league_id": league_id, "game_key": game_key, "season": season,
                "scoring_type": "head",
                "stats": [{"stat_id": "7", "name": "Home Runs", "abbr": "HR"}],
                "scoring_stat_ids": ["7"]}

    def fetch_teams(self, league_id, game_key):
        return [{"team_id": "1", "team_key": f"{game_key}.l.L.t.1", "name": "Alpha"},
                {"team_id": "2", "team_key": f"{game_key}.l.L.t.2", "name": "Beta"}]

    def fetch_team_season_stats(self, team_key, league_id, game_key):
        # keyed by the trailing team number in the fake team_key
        return self._team_stats[team_key.rsplit(".", 1)[-1]]

    def fetch_matchups(self, league_id, game_key, weeks):
        return self._matchups


_DESCRIPTOR = {"season": 2013, "game_key": "308", "league_id": "2935",
               "name": "My League"}


def test_writes_minimal_files_and_bypasses_coverage_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    client = _FakeClient(
        team_stats={"1": {"7": "212"}, "2": {"7": "180"}},
        matchups=[{"week": 1, "winner_team_key": "308.l.L.t.1",
                   "teams": [{"team_key": "308.l.L.t.1", "name": "Alpha", "points": "6"},
                             {"team_key": "308.l.L.t.2", "name": "Beta", "points": "4"}]}],
    )

    wrote = fetch_all.fetch_team_records_season(client, "12239", _DESCRIPTOR)
    assert wrote is True

    sdir = tmp_path / "12239" / "2013"
    ps = common.load_json(sdir / "player_stats.json")
    # Team totals captured; per-player data intentionally empty (unreachable),
    # and the season is flagged as a lightweight historical fill.
    assert ps["team_season_stats"] == {"1": {"7": "212"}, "2": {"7": "180"}}
    assert ps["season_totals"] == {}
    assert ps["weekly"] == {}
    assert ps["team_records_only"] is True
    assert ps["teams"] == {"1": "Alpha", "2": "Beta"}
    # Settings + matchups land; rosters (the player-only file) is never written.
    assert (sdir / "stat_categories.json").exists()
    assert (sdir / "matchups.json").exists()
    assert not (sdir / "rosters.json").exists()
    # No coverage block is computed or consulted — the gate is bypassed entirely.
    assert "coverage" not in ps


def test_skips_season_with_no_team_data_and_no_matchups(tmp_path, monkeypatch):
    # 2020's likely shape: teams resolve but carry empty stat lines, and the
    # bogus start=end=0 bounds yield no matchups. Nothing to show → skip, write
    # nothing, and say so.
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    client = _FakeClient(team_stats={"1": {}, "2": {}}, matchups=[])

    wrote = fetch_all.fetch_team_records_season(
        client, "12239", {**_DESCRIPTOR, "season": 2020})
    assert wrote is False
    assert not (tmp_path / "12239" / "2020").exists()


def test_keeps_season_with_team_data_even_without_matchups(tmp_path, monkeypatch):
    # Counting boards only need team totals; a season with totals but no matchups
    # is still worth keeping (it just won't contribute to the W-L-T boards).
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    client = _FakeClient(team_stats={"1": {"7": "150"}, "2": {"7": "140"}},
                         matchups=[])

    wrote = fetch_all.fetch_team_records_season(
        client, "12239", {**_DESCRIPTOR, "season": 2020})
    assert wrote is True
    ps = common.load_json(tmp_path / "12239" / "2020" / "player_stats.json")
    assert ps["team_season_stats"] == {"1": {"7": "150"}, "2": {"7": "140"}}


# --------------------------------------------------------------------------- #
# run_team_records_backfill — fills only the gap seasons
# --------------------------------------------------------------------------- #
def test_backfill_fills_only_gap_seasons(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    # Prove the run never mutates the committed data/leagues.json.
    real_leagues = common.PROJECT_ROOT / "data" / "leagues.json"
    before = real_leagues.read_bytes() if real_leagues.exists() else None

    # Seasons 2021-2022 already fully fetched on disk (the full-path output).
    for y in (2021, 2022):
        common.dump_json(tmp_path / "12239" / str(y) / "player_stats.json",
                         {"season_totals": {"t1": {"7": "20"}}})

    discovered = [
        {"season": y, "game_key": str(y), "league_id": "L", "name": "My League"}
        for y in (2019, 2020, 2021, 2022)
    ]

    class FakeDiscoverClient:
        def discover_league_seasons(self, league_id):
            return discovered

    filled = []

    def fake_fetch(client, entry_league_id, descriptor):
        filled.append(descriptor["season"])
        # Simulate a written lite season so list_seasons picks it up afterward.
        common.dump_json(
            tmp_path / entry_league_id / str(descriptor["season"]) / "player_stats.json",
            {"season_totals": {}, "team_season_stats": {"t1": {"7": "9"}}})
        return True

    monkeypatch.setattr(fetch_all, "fetch_team_records_season", fake_fetch)

    fetch_all.run_team_records_backfill(FakeDiscoverClient(), ["12239"])

    # Only the pre-2021 gap seasons are fetched; the on-disk seasons are left be.
    assert filled == [2019, 2020]

    # leagues.json now spans the full reachable history (existing + new lite).
    index = common.load_json(tmp_path / "leagues.json")
    assert index["leagues"][0]["seasons"] == [2019, 2020, 2021, 2022]

    after = real_leagues.read_bytes() if real_leagues.exists() else None
    assert after == before, "run mutated the committed data/leagues.json"


def test_backfill_since_floors_the_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    discovered = [
        {"season": y, "game_key": str(y), "league_id": "L", "name": "My League"}
        for y in (2016, 2017, 2018)
    ]

    class FakeDiscoverClient:
        def discover_league_seasons(self, league_id):
            return discovered

    filled = []
    monkeypatch.setattr(
        fetch_all, "fetch_team_records_season",
        lambda client, lid, d: (filled.append(d["season"]) or True))

    fetch_all.run_team_records_backfill(FakeDiscoverClient(), ["12239"], since=2017)

    assert filled == [2017, 2018]

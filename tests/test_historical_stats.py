"""Behavior tests for the historical-stats recipe (the 2026-06-24 fix).

These exercise the hard-won logic from the handoff through public interfaces,
fully offline:

  - Yahoo's ``players;.../stats`` JSON, where ``player_key`` and ``player_stats``
    are *siblings* under each ``player`` wrapper (the all-zeros bug).
  - The drop-bad-key-and-retry loop: one retired player must not abort a batch;
    their id lands in ``unreachable``.
  - Historical roster key-mapping by stable ``player_id`` + the coverage block.
  - The 80% coverage gate that decides whether a season is kept.
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Yahoo JSON payload builders (mirror the real nested shape)
# --------------------------------------------------------------------------- #
def _player_node(player_key: str, player_id: str, name: str, stats: dict) -> dict:
    """One Yahoo ``player`` wrapper: id-fields list + a sibling player_stats dict."""
    return {
        "player": [
            [
                {"player_key": player_key},
                {"player_id": player_id},
                {"name": {"full": name}},
            ],
            {
                "player_stats": {
                    "0": {"coverage_type": "season", "season": "2023"},
                    "stats": [{"stat": {"stat_id": sid, "value": val}}
                              for sid, val in stats.items()],
                }
            },
        ]
    }


def players_payload(players: list) -> dict:
    """A full ``fantasy_content.players`` response from a list of player nodes."""
    indexed = {str(i): node for i, node in enumerate(players)}
    indexed["count"] = len(players)
    return {"fantasy_content": {"players": indexed}}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeQuery:
    """Stand-in for a yfpy query: only ``get_response(url)`` is used here.

    ``payload_for`` receives the request URL and returns the JSON payload to
    serve (or raises, to simulate Yahoo's bad-key 400).
    """

    def __init__(self, payload_for):
        self._payload_for = payload_for
        self.urls = []

    def get_response(self, url):
        self.urls.append(url)
        return FakeResponse(self._payload_for(url))


# --------------------------------------------------------------------------- #
# Tracer bullet: real stats parse out of the sibling-shaped JSON
# --------------------------------------------------------------------------- #
def test_fetch_current_game_season_stats_parses_real_values(yahoo_client):
    payload = players_payload([
        _player_node("469.p.8967", "8967", "Paul Goldschmidt",
                     {"7": "89", "12": "25", "13": "80"}),
    ])
    fake = FakeQuery(lambda url: payload)
    yahoo_client.query = lambda *a, **k: fake

    stats, unreachable = yahoo_client.fetch_current_game_season_stats(
        ["8967"], season=2023, cur_league_id="12239", cur_game_key="469")

    assert stats == {"8967": {"7": "89", "12": "25", "13": "80"}}
    assert unreachable == set()


def test_retired_player_is_dropped_and_marked_unreachable(yahoo_client):
    # The batch holds one live player (8967) and one retired (9999). Yahoo
    # rejects the whole request naming the bad key; the client must drop it,
    # retry, and still return the live player's stats.
    good = players_payload([
        _player_node("469.p.8967", "8967", "Paul Goldschmidt", {"7": "89"}),
    ])

    def payload_for(url):
        if "469.p.9999" in url:
            raise RuntimeError(
                "Invalid input: Player key 469.p.9999 does not exist.")
        return good

    fake = FakeQuery(payload_for)
    yahoo_client.query = lambda *a, **k: fake

    stats, unreachable = yahoo_client.fetch_current_game_season_stats(
        ["8967", "9999"], season=2023, cur_league_id="12239", cur_game_key="469")

    assert stats == {"8967": {"7": "89"}}
    assert unreachable == {"9999"}


def test_batches_requests_above_batch_size(yahoo_client):
    # More ids than the batch size → split into multiple requests, all merged.
    import re

    def payload_for(url):
        ids = re.findall(r"\.p\.(\d+)", url)
        return players_payload([
            _player_node(f"469.p.{pid}", pid, f"Player {pid}", {"7": pid})
            for pid in ids
        ])

    fake = FakeQuery(payload_for)
    yahoo_client.query = lambda *a, **k: fake

    stats, unreachable = yahoo_client.fetch_current_game_season_stats(
        ["1", "2", "3"], season=2023, cur_league_id="12239", cur_game_key="469",
        batch_size=2)

    assert len(fake.urls) == 2  # 3 ids / batch of 2 → two requests
    assert stats == {"1": {"7": "1"}, "2": {"7": "2"}, "3": {"7": "3"}}
    assert unreachable == set()


# --------------------------------------------------------------------------- #
# _historical_season_totals: map stats onto historical keys + coverage block
# --------------------------------------------------------------------------- #
class FakeClient:
    """Stand-in for YahooClient that returns canned current-game stats."""

    def __init__(self, stats_by_id, unreachable):
        self._stats_by_id = stats_by_id
        self._unreachable = set(unreachable)

    def fetch_current_game_season_stats(self, ids, season, cur_league_id, cur_game_key):
        wanted = {str(i) for i in ids}
        return ({k: v for k, v in self._stats_by_id.items() if k in wanted},
                self._unreachable & wanted)


def test_historical_totals_map_onto_historical_keys_with_coverage():
    import fetch_all

    roster_teams = [
        {"team_id": "t1", "name": "Team One", "players": [
            {"player_id": "8967", "player_key": "388.p.8967", "name": "Paul Goldschmidt"}]},
        {"team_id": "t2", "name": "Team Two", "players": [
            {"player_id": "9999", "player_key": "388.p.9999", "name": "Retired Guy"}]},
    ]
    client = FakeClient(stats_by_id={"8967": {"7": "89"}}, unreachable={"9999"})

    season_totals, coverage = fetch_all._historical_season_totals(
        client, roster_teams, season=2023, cur_league_id="12239", cur_game_key="469")

    # Stats are keyed by the HISTORICAL roster key, not the current-game key.
    assert season_totals == {"t1": {"388.p.8967": {"7": "89"}}, "t2": {}}
    assert coverage["total"] == 2
    assert coverage["reachable"] == 1
    assert coverage["rate"] == 0.5
    assert coverage["unreachable"] == [{"player_id": "9999", "name": "Retired Guy"}]


# --------------------------------------------------------------------------- #
# fetch_season: the 80% coverage gate
# --------------------------------------------------------------------------- #
class FakeSeasonClient:
    """A YahooClient stand-in covering the calls fetch_season makes for a
    historical season. ``roster`` is the single team's player list; reachable
    ids get canned stats, the rest are reported unreachable."""

    def __init__(self, roster, reachable_ids):
        self._roster = roster
        self._reachable = set(reachable_ids)

    def fetch_stat_categories(self, league_id, game_key, season):
        return {"league_id": league_id, "game_key": game_key, "season": season,
                "stats": [], "scoring_stat_ids": []}

    def fetch_teams(self, league_id, game_key):
        return [{"team_id": "t1", "team_key": f"{game_key}.l.{league_id}.t.1", "name": "Team One"}]

    def fetch_roster(self, team_id, league_id, game_key, week):
        return self._roster

    def fetch_current_game_season_stats(self, ids, season, cur_league_id, cur_game_key):
        wanted = {str(i) for i in ids}
        stats = {pid: {"7": "10"} for pid in wanted if pid in self._reachable}
        return stats, (wanted - self._reachable)

    def fetch_matchups(self, league_id, game_key, weeks):
        return []


_HIST_DESCRIPTOR = {
    "season": 2021, "game_key": "404", "league_id": "L21",
    "start_week": 1, "end_week": 1, "current_week": 1,
}


def _two_player_roster():
    return [
        {"player_id": "8967", "player_key": "404.p.8967", "name": "Reachable Guy"},
        {"player_id": "9999", "player_key": "404.p.9999", "name": "Retired Guy"},
    ]


def test_low_coverage_season_is_skipped_and_writes_nothing(tmp_path, monkeypatch):
    import common
    import fetch_all
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    client = FakeSeasonClient(_two_player_roster(), reachable_ids={"8967"})  # 1/2 = 50%

    written = fetch_all.fetch_season(
        client, "12239", _HIST_DESCRIPTOR, cur_game_key="469", cur_league_id="12239")

    assert written is False
    # Nothing partial left on disk for the skipped season.
    assert not (tmp_path / "12239" / "2021").exists()


def test_sufficient_coverage_season_is_written_with_coverage_block(tmp_path, monkeypatch):
    import common
    import fetch_all
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    client = FakeSeasonClient(_two_player_roster(), reachable_ids={"8967", "9999"})  # 100%

    written = fetch_all.fetch_season(
        client, "12239", _HIST_DESCRIPTOR, cur_game_key="469", cur_league_id="12239")

    assert written is True
    player_stats = common.load_json(tmp_path / "12239" / "2021" / "player_stats.json")
    assert player_stats["coverage"]["rate"] == 1.0
    assert player_stats["weekly"] == {}  # no historical weekly for MLB
    # Real stat values mapped onto the historical roster keys.
    assert player_stats["season_totals"]["t1"]["404.p.8967"] == {"7": "10"}


# --------------------------------------------------------------------------- #
# to_number: the sentinel handling the value-aware completeness check rests on
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sentinel", ["-", "--", "", "INF", "NA", "N/A", "60/200", None])
def test_to_number_rejects_non_scalar_sentinels(sentinel):
    from common import to_number
    assert to_number(sentinel) is None


@pytest.mark.parametrize("value,expected", [
    ("89", 89.0), ("0.268", 0.268), ("0", 0.0), (25, 25.0), (3.5, 3.5),
])
def test_to_number_parses_real_values(value, expected):
    from common import to_number
    assert to_number(value) == expected

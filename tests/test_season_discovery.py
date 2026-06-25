"""Behavior tests for season discovery — the renew-chain walk that decides
which seasons a league existed for (and thus what the backfill fetches).

Fully offline: the network boundary is ``YahooClient.query``, stubbed per-test
to return fake league-metadata objects chained by their ``renew`` tokens.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


# --------------------------------------------------------------------------- #
# _parse_renew: the "<game_key>_<league_id>" token the chain walk hinges on
# --------------------------------------------------------------------------- #
def test_parse_renew_splits_game_key_and_league_id():
    from yahoo_client import _parse_renew

    assert _parse_renew("404_11111") == ("404", "11111")


def test_parse_renew_returns_none_for_missing_or_malformed():
    from yahoo_client import _parse_renew

    # No link at all (newest season, or a league that was never renewed).
    assert _parse_renew(None) is None
    assert _parse_renew("") is None
    # Malformed: a bare token with no "<gk>_<id>" pair.
    assert _parse_renew("12239") is None


# --------------------------------------------------------------------------- #
# discover_league_seasons: walk the renew chain backward across game_keys
# --------------------------------------------------------------------------- #
def _meta(season, game_key, league_id, renew=None, name="My League", num_teams=12):
    """A fake league-metadata object shaped like yfpy's (attribute access)."""
    return SimpleNamespace(
        league_key=f"{game_key}.l.{league_id}",
        season=season,
        league_id=league_id,
        name=name,
        num_teams=num_teams,
        start_week=1,
        end_week=23,
        current_week=23,
        renew=renew,
    )


def _stub_chain(client, metas_by_league_id):
    """Stub ``client.query`` so each league_id serves its canned metadata."""
    def query(league_id, game_key=None):
        meta = metas_by_league_id[str(league_id)]
        return SimpleNamespace(get_league_metadata=lambda: meta)
    client.query = query


def test_discovery_walks_chain_and_sorts_oldest_to_newest(yahoo_client):
    # 2025 (entry) renews from 2024, which has no prior link.
    _stub_chain(yahoo_client, {
        "12239": _meta(2025, "422", "12239", renew="404_11111"),
        "11111": _meta(2024, "404", "11111", renew=None),
    })

    seasons = yahoo_client.discover_league_seasons("12239")

    assert [s["season"] for s in seasons] == [2024, 2025]
    assert [s["game_key"] for s in seasons] == ["404", "422"]
    assert [s["league_id"] for s in seasons] == ["11111", "12239"]


def test_discovery_stops_gracefully_at_inaccessible_earlier_season(yahoo_client):
    from yfpy.exceptions import YahooFantasySportsDataNotFound

    # The entry season is readable and links back to an older league the
    # account never joined → that read 404s. Discovery keeps the readable
    # seasons instead of blowing up.
    metas = {"12239": _meta(2025, "422", "12239", renew="404_99999")}

    def get_meta(league_id):
        if str(league_id) == "99999":
            raise YahooFantasySportsDataNotFound("no access", payload={})
        return metas[str(league_id)]

    def query(league_id, game_key=None):
        return SimpleNamespace(get_league_metadata=lambda: get_meta(league_id))
    yahoo_client.query = query

    seasons = yahoo_client.discover_league_seasons("12239")

    assert [s["season"] for s in seasons] == [2025]


def test_discovery_raises_when_entry_league_is_unreadable(yahoo_client):
    from yfpy.exceptions import YahooFantasySportsDataNotFound

    # Nothing discovered yet → an unreadable entry league is a real error
    # (bad id, or the account isn't even in its own league), not a soft stop.
    def query(league_id, game_key=None):
        def boom():
            raise YahooFantasySportsDataNotFound("bad id", payload={})
        return SimpleNamespace(get_league_metadata=boom)
    yahoo_client.query = query

    with pytest.raises(YahooFantasySportsDataNotFound):
        yahoo_client.discover_league_seasons("00000")


def test_discovery_terminates_on_a_renew_cycle(yahoo_client):
    # A malformed chain that points back at an already-seen league must not
    # loop forever — the `seen` guard stops it.
    _stub_chain(yahoo_client, {
        "12239": _meta(2025, "422", "12239", renew="404_11111"),
        "11111": _meta(2024, "404", "11111", renew="422_12239"),  # back-reference
    })

    seasons = yahoo_client.discover_league_seasons("12239")

    assert [s["season"] for s in seasons] == [2024, 2025]

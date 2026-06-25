"""Behavior test for the ``--since`` backfill floor.

We only want history back to a chosen year (2021), not all the way to 2010 —
older seasons are mostly unreachable retirees and slow to scan. ``run_backfill``
must therefore skip discovered seasons older than the floor, while still using
the newest season to locate the current game.
"""

from __future__ import annotations


def test_backfill_since_skips_seasons_older_than_floor(monkeypatch, tmp_path):
    import common
    import fetch_all
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    discovered = [
        {"season": y, "game_key": str(y), "league_id": "L", "name": "My League"}
        for y in (2019, 2020, 2021, 2022)
    ]

    class FakeClient:
        def discover_league_seasons(self, league_id):
            return discovered

    fetched = []
    monkeypatch.setattr(
        fetch_all, "fetch_season",
        lambda client, lid, d, cur_game_key, cur_league_id, **kw: (fetched.append(d["season"]) or True))

    fetch_all.run_backfill(FakeClient(), ["12239"], since=2021)

    assert fetched == [2021, 2022]

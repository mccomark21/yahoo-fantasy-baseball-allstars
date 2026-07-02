"""Counting-board season-span filter in Team Records (issue #40 follow-up).

Leagues churn their scoring categories over the years — LOC alone has carried
one-off cats like NSB, CYC, SLAM, or a lone-season SV. A "record" drawn from a
stat the league only ran a season or two isn't an all-time mark, it's noise, and
it bloats the chip rail. ``compute_team_records`` therefore keeps a counting board
only when its stat was scored in at least ``MIN_STAT_SEASONS`` seasons; durable
stats are untouched. These tests pin the threshold, including its exact boundary.
"""

from __future__ import annotations

import common
import compute_records


def _write_season(root, league_id, season, cats):
    """Write one season's raw files. ``cats`` is a list of (stat_id, abbr); each
    listed stat gets a team total for both teams so its board has entries."""
    common.dump_json(root / league_id / str(season) / "stat_categories.json", {
        "scoring_type": "head",
        "scoring_stat_ids": [sid for sid, _ in cats],
        "stats": [{"stat_id": sid, "abbr": abbr, "position_type": "B",
                   "sort_order": "1"} for sid, abbr in cats],
    })
    totals = {tid: {sid: str(100 + i) for sid, _ in cats}
              for i, tid in enumerate(("1", "2"))}
    common.dump_json(root / league_id / str(season) / "player_stats.json", {
        "teams": {"1": "Alpha", "2": "Beta"}, "season_totals": {}, "weekly": {},
        "team_season_stats": totals, "team_records_only": True,
    })


def _boards(tmp_path, monkeypatch, per_season_cats):
    """Compute team records over the given {season: [(stat_id, abbr), ...]} map
    and return the set of counting-board stat abbrs that survived the filter."""
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    league_id = "99999"
    for season, cats in per_season_cats.items():
        _write_season(tmp_path, league_id, season, cats)
    out = compute_records.compute_team_records(
        league_id, sorted(per_season_cats), "head")
    return {b["stat"] for b in out["season_stats"]}


def test_short_lived_stat_is_dropped_durable_stat_is_kept(tmp_path, monkeypatch):
    # HR/R scored all six seasons; CYC only the first two.
    per_season = {}
    for season in range(2011, 2017):  # 6 seasons
        cats = [("7", "HR"), ("60", "R")]
        if season in (2011, 2012):
            cats.append(("70", "CYC"))
        per_season[season] = cats

    boards = _boards(tmp_path, monkeypatch, per_season)
    assert {"HR", "R"} <= boards      # 6 seasons — durable, kept
    assert "CYC" not in boards        # 2 seasons — short-lived, dropped


def test_five_seasons_kept_four_dropped_at_the_boundary(tmp_path, monkeypatch):
    # MIN_STAT_SEASONS is a >= threshold: exactly 5 survives, 4 does not.
    assert compute_records.MIN_STAT_SEASONS == 5
    per_season = {}
    for season in range(2011, 2017):  # 6 seasons
        cats = [("7", "HR")]                       # anchor: present every season
        if season <= 2015:                         # 2011-2015 → 5 seasons
            cats.append(("90", "XBH"))
        if season <= 2014:                          # 2011-2014 → 4 seasons
            cats.append(("91", "CG"))
        per_season[season] = cats

    boards = _boards(tmp_path, monkeypatch, per_season)
    assert "XBH" in boards            # exactly 5 seasons — kept
    assert "CG" not in boards         # only 4 seasons — dropped

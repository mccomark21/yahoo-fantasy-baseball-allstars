"""Behavior tests for the all-star scoring engine and diamond assignment.

Covers three deepenings:

  * stat **orientation** — ERA/WHIP score lower-is-better even when Yahoo hands
    back a blank ``sort_order`` (issue #24);
  * role-aware **scoring pools** — starters and relievers judged within their own
    pool so wins matter to SP and saves to RP, with an innings qualifier (#24);
  * distinct **diamond assignment** — LF/CF/RF resolve to three distinct players
    (issue #23).

Everything runs offline against hand-built player/stat fixtures.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _player(name, positions, stats, *, mlb_team="", key=None):
    """A rostered-player dict shaped like ``load_season_players`` produces."""
    return {
        "name": name,
        "player_key": key or name,
        "eligible_positions": list(positions),
        "mlb_team": mlb_team,
        "fantasy_team": "Test Team",
        "raw_stats": {str(k): v for k, v in stats.items()},
    }


def _cat(stat_id, abbr, *, pitching, sort_order="1", display_only=False):
    return {
        "stat_id": str(stat_id),
        "abbr": abbr,
        "display_name": abbr,
        "name": abbr,
        "position_type": "P" if pitching else "B",
        "sort_order": sort_order,
        "enabled": True,
        "is_only_display_stat": display_only,
    }


# Stat ids mirror the real leagues: 12=HR, 50=IP(display), 28=W, 32=SV, 26=ERA, 27=WHIP.
def _pitching_categories():
    stats = [
        _cat(50, "IP", pitching=True, display_only=True),
        _cat(28, "W", pitching=True),
        _cat(32, "SV", pitching=True),
        _cat(26, "ERA", pitching=True, sort_order=""),   # blank like real Yahoo data
        _cat(27, "WHIP", pitching=True, sort_order=""),
    ]
    return {"scoring_stat_ids": ["28", "32", "26", "27"], "stats": stats}


def _batting_categories():
    stats = [_cat(12, "HR", pitching=False)]
    return {"scoring_stat_ids": ["12"], "stats": stats}


# --------------------------------------------------------------------------- #
# Candidate 1 — stat orientation
# --------------------------------------------------------------------------- #
def test_blank_sort_order_falls_back_to_lower_is_better():
    from common import higher_is_better

    assert higher_is_better(_cat(26, "ERA", pitching=True, sort_order="")) is False
    assert higher_is_better(_cat(27, "WHIP", pitching=True, sort_order="")) is False
    # Unknown stat with a blank sort_order still defaults to higher-is-better.
    assert higher_is_better(_cat(42, "K", pitching=True, sort_order="")) is True


def test_explicit_sort_order_is_honored():
    from common import higher_is_better

    assert higher_is_better(_cat(7, "R", pitching=False, sort_order="1")) is True
    assert higher_is_better(_cat(26, "ERA", pitching=True, sort_order="0")) is False


def test_lower_era_scores_higher_than_higher_era():
    """The headline #24 fix: all else equal, the lower ERA wins."""
    from compute_allstars import score_players

    good = _player("Ace", ["RP"], {"26": 2.00, "27": 1.00, "28": 0, "32": 10})
    bad = _player("Arsonist", ["RP"], {"26": 5.00, "27": 1.00, "28": 0, "32": 10})
    score_players([good, bad], _pitching_categories())
    assert good["rp_score"] > bad["rp_score"]


# --------------------------------------------------------------------------- #
# Candidate 2 — role-aware scoring pools
# --------------------------------------------------------------------------- #
def test_high_save_reliever_outranks_low_save_reliever():
    from compute_allstars import score_players

    closer = _player("Closer", ["RP"], {"32": 30, "28": 1, "26": 3.0, "27": 1.1})
    mopup = _player("Mop-up", ["RP"], {"32": 1, "28": 1, "26": 3.0, "27": 1.1})
    score_players([closer, mopup], _pitching_categories())
    assert closer["rp_score"] > mopup["rp_score"]


def test_high_innings_win_starter_outranks_low_innings_starter():
    from compute_allstars import score_players

    workhorse = _player("Workhorse", ["SP"], {"50": 180, "28": 15, "32": 0, "26": 3.0, "27": 1.1})
    spot = _player("Spot Starter", ["SP"], {"50": 40, "28": 3, "32": 0, "26": 3.0, "27": 1.1})
    score_players([workhorse, spot], _pitching_categories())
    assert workhorse["sp_score"] > spot["sp_score"]


def test_role_signature_stats_count_only_in_their_own_pool():
    from common import counts_for_role

    saves = _cat(32, "SV", pitching=True)
    wins = _cat(28, "W", pitching=True)
    strikeouts = _cat(42, "K", pitching=True)
    assert counts_for_role(saves, "SP") is False and counts_for_role(saves, "RP") is True
    assert counts_for_role(wins, "RP") is False and counts_for_role(wins, "SP") is True
    assert counts_for_role(strikeouts, "SP") and counts_for_role(strikeouts, "RP")


def test_saves_do_not_win_the_starter_pool():
    """A save-hoarding swingman must not out-score a workhorse starter in the SP
    pool — saves are a reliever stat and don't count toward SP ranking."""
    from compute_allstars import score_players

    # Workhorse is better on every SP-relevant stat; the swingman's sole edge is
    # 16 saves, which must be ignored when ranking starters.
    workhorse = _player("Workhorse", ["SP"], {"50": 190, "28": 16, "32": 0, "26": 2.50, "27": 0.95})
    swingman = _player("Swingman", ["SP", "RP"], {"50": 45, "28": 1, "32": 16, "26": 3.20, "27": 1.20})
    score_players([workhorse, swingman], _pitching_categories())
    assert workhorse["sp_score"] > swingman["sp_score"]


def test_role_pools_judge_wins_among_starters_and_saves_among_relievers():
    """A reliever's zero wins must not sink them in the RP pool, and a starter's
    zero saves must not sink them in the SP pool."""
    from compute_allstars import score_players

    # Two starters (wins, no saves) and two relievers (saves, no wins).
    sp_good = _player("SP Good", ["SP"], {"50": 180, "28": 18, "32": 0, "26": 2.5, "27": 1.0})
    sp_bad = _player("SP Bad", ["SP"], {"50": 90, "28": 6, "32": 0, "26": 4.5, "27": 1.4})
    rp_good = _player("RP Good", ["RP"], {"50": 70, "28": 0, "32": 35, "26": 2.0, "27": 0.9})
    rp_bad = _player("RP Bad", ["RP"], {"50": 50, "28": 0, "32": 5, "26": 4.0, "27": 1.3})
    players = [sp_good, sp_bad, rp_good, rp_bad]
    score_players(players, _pitching_categories())

    # Best starter tops the SP pool; best reliever tops the RP pool.
    assert sp_good["sp_score"] > sp_bad["sp_score"]
    assert rp_good["rp_score"] > rp_bad["rp_score"]
    # The good reliever (0 wins, 35 saves) is the RP-pool leader — saves weren't
    # drowned out by comparing against win-accruing starters.
    assert rp_good["rp_score"] == max(p["rp_score"] for p in players)


# --------------------------------------------------------------------------- #
# Candidate 3 — distinct diamond assignment
# --------------------------------------------------------------------------- #
def test_outfield_slots_get_three_distinct_players():
    """Issue #23: one outfielder tops LF, CF and RF by score, but the diamond
    must show the top three distinct outfielders."""
    from compute_allstars import build_league

    of = [
        _player("Slugger", ["OF"], {"12": 40}, key="of1"),
        _player("Masher", ["OF"], {"12": 30}, key="of2"),
        _player("Basher", ["OF"], {"12": 20}, key="of3"),
        _player("Spare", ["OF"], {"12": 10}, key="of4"),
    ]
    all_stars, races = build_league(of, _batting_categories())

    winners = [all_stars["LF"]["player_name"], all_stars["CF"]["player_name"],
               all_stars["RF"]["player_name"]]
    assert winners == ["Slugger", "Masher", "Basher"]   # top three, distinct, by score
    assert len(set(winners)) == 3
    # UTIL surfaces the best bat NOT already crowned at a position — never a repeat.
    assert all_stars["UTIL"]["player_name"] == "Spare"
    assert all_stars["UTIL"]["player_name"] not in winners
    # Positional races keep the full ranked list per slot, unaffected by assignment.
    assert [r["player_name"] for r in races["LF"]] == ["Slugger", "Masher", "Basher", "Spare"]


def test_batting_slots_get_distinct_players_including_util():
    from common import assign_distinct

    a = _player("A", ["2B", "SS"], {"12": 50}, key="a")
    b = _player("B", ["SS"], {"12": 40}, key="b")
    c = _player("C", ["2B", "SS"], {"12": 30}, key="c")
    # Pre-ranked candidate lists per slot (descending by score).
    chosen = assign_distinct({"2B": [a, c], "SS": [a, b, c], "UTIL": [a, b, c]})
    assert chosen["2B"]["name"] == "A"
    assert chosen["SS"]["name"] == "B"    # A is taken at 2B, so SS falls to B
    assert chosen["UTIL"]["name"] == "C"  # A and B taken, so UTIL falls to C
    assert len({chosen[s]["name"] for s in ("2B", "SS", "UTIL")}) == 3


def test_two_way_player_may_appear_once_on_each_side():
    from common import assign_distinct

    ohtani = _player("Ohtani", ["UTIL", "SP"], {"12": 50}, key="ohtani")
    chosen = assign_distinct({"UTIL": [ohtani], "SP": [ohtani]})
    # Batting and pitching are independent groups — the two-way star takes both.
    assert chosen["UTIL"]["name"] == "Ohtani"
    assert chosen["SP"]["name"] == "Ohtani"

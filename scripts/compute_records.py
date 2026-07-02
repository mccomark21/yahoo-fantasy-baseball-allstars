#!/usr/bin/env python3
"""Compute all-time records across every stored season.

Reads ALL raw per-season JSON for each league and writes:

  data/records_teams.json    top-5 best/worst team-seasons by W-L-T (category
                             aggregate for "head" leagues, weekly for "headone"),
                             plus a top-5 team-season leaderboard per counting
                             scoring category
  data/records_players.json  single-week and season-total records per stat,
                             with player / fantasy-team / season / week context

Player attribution: a player's weekly and season lines are tied to the fantasy
team that rostered them that season (captured per-team in player_stats.json).
Player *names* come from roster snapshots pooled across all seasons; a player who
only ever appears mid-season and was never on a season-end roster falls back to a
cleaned player key. Both single-week and season-total boards cover counting
scoring stats only — rate stats (AVG/ERA/WHIP…) and lower-is-better stats are
excluded so an all-time mark is an unambiguous maximum.

    python scripts/compute_records.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    DATA_DIR, clean_number, counting_scoring_stats, dump_json, list_seasons,
    load_json, scoring_stats, scoring_type, season_dir, stat_abbr, to_number,
)


# A counting-stat board must span at least this many seasons to earn a place in
# all-time Team Records. Leagues churn their category set over the years (LOC has
# carried one-off cats like NSB, CYC, SLAM, or a lone-season SV); a "record" set
# from a stat that only existed a year or two isn't an all-time mark, it's noise.
MIN_STAT_SEASONS = 5

# Depth of the all-time Player Records leaderboards (issue #30): the top N
# player-seasons (and player-weeks) per stat, not just the single best. A player
# may appear more than once across a board — different seasons are distinct marks.
PLAYER_TOP_N = 10


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pretty_key(player_key: str) -> str:
    """Last resort label when a player never appears on a roster snapshot."""
    return f"Player {player_key}" if player_key else "Unknown"


# --------------------------------------------------------------------------- #
# Player name index (pooled across all seasons of a league)
# --------------------------------------------------------------------------- #
def build_name_index(league_id: str, seasons: List[int]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for season in seasons:
        path = season_dir(league_id, season) / "rosters.json"
        if not path.exists():
            continue
        rosters = load_json(path)
        for team in rosters.get("teams", []):
            for player in team.get("players", []):
                pk = player.get("player_key", "")
                name = player.get("name", "")
                if pk and name:
                    names[pk] = name
    return names


# --------------------------------------------------------------------------- #
# Team records
# --------------------------------------------------------------------------- #
def _mark_num(v: float):
    """Int when whole, else 2-place — for W/L/T marks and counting totals."""
    return int(v) if float(v) == int(v) else round(float(v), 2)


def league_scoring_type(league_id: str, seasons: List[int]) -> str:
    """The league's scoring format, from the newest season that recorded it.

    A league-constant, but only present on files fetched after the format was
    captured; scan newest → oldest and take the first value, else ``""``."""
    for season in reversed(seasons):
        path = season_dir(league_id, season) / "stat_categories.json"
        if path.exists():
            st = scoring_type(load_json(path))
            if st:
                return st
    return ""


def _season_wlt(matchups: List[dict], use_head: bool, cat_count: int) -> List[dict]:
    """Every team's season-long W-L-T from one season's matchups.

    ``head`` (categories): per matchup a team banks its category wins as W, the
    opponent's as L, and the untied remainder (``C − own − opp``) as T — the
    season aggregate a Yahoo categories league ranks by. ``headone`` (one win
    per week): a plain weekly win / loss / tie off ``winner_team_key``. All
    matchups count, playoffs included."""
    wlt: Dict[str, dict] = {}  # team_key -> {name, w, l, t}
    for m in matchups:
        teams = m.get("teams", [])
        if len(teams) != 2:
            continue
        winner = m.get("winner_team_key") or ""
        tied = bool(m.get("is_tied"))
        a, b = teams
        for own, opp in ((a, b), (b, a)):
            key = own.get("team_key", "")
            if not key:
                continue
            rec = wlt.setdefault(key, {"name": "", "w": 0.0, "l": 0.0, "t": 0.0})
            rec["name"] = own.get("name", "") or rec["name"]
            if use_head:
                op = to_number(own.get("points"))
                pp = to_number(opp.get("points"))
                if op is None or pp is None:
                    continue
                rec["w"] += op
                rec["l"] += pp
                rec["t"] += max(0.0, cat_count - op - pp)
            elif tied:
                rec["t"] += 1
            elif winner and key == winner:
                rec["w"] += 1
            elif winner:
                rec["l"] += 1
            # winner missing and not tied → unplayed matchup, skip
    return [
        {"fantasy_team": rec["name"], "season": None,  # season filled by caller
         "wins": _mark_num(rec["w"]), "losses": _mark_num(rec["l"]),
         "ties": _mark_num(rec["t"]), "_w": rec["w"], "_l": rec["l"]}
        for rec in wlt.values()
        if rec["w"] or rec["l"] or rec["t"]
    ]


def compute_team_records(league_id: str, seasons: List[int], scoring: str) -> dict:
    """Best/worst season W-L-T leaderboards + per-counting-stat team-season
    leaderboards, all top-5. The unit is a team-season, so a franchise may
    appear more than once. ``scoring`` selects the W-L-T formula per league."""
    season_rows: List[dict] = []              # W-L-T, one per (season, team)
    stat_boards: Dict[str, dict] = {}         # abbr -> {display, entries[]}
    stat_order: List[str] = []                # first-seen scoring order (bat→pit)
    stat_seasons: Dict[str, set] = {}         # abbr -> {seasons it was scored in}

    for season in seasons:
        sdir = season_dir(league_id, season)
        cat_path = sdir / "stat_categories.json"
        stat_categories = load_json(cat_path) if cat_path.exists() else {}

        # -- Season W-L-T (format-aware) -------------------------------------- #
        mpath = sdir / "matchups.json"
        matchups = load_json(mpath).get("matchups", []) if mpath.exists() else []
        cat_count = len(scoring_stats(stat_categories)) if stat_categories else 0
        use_head = scoring == "head" and cat_count > 0
        for row in _season_wlt(matchups, use_head, cat_count):
            row["season"] = season
            season_rows.append(row)

        # -- Counting-stat team-season totals --------------------------------- #
        # Yahoo's authoritative team category total (standings "Stats" view),
        # captured per team in player_stats.json. This is the team's accumulated
        # HR/R/K — NOT the sum of its roster's full individual season totals, which
        # over-counts late adds and the bench. Seasons fetched before team totals
        # were captured simply contribute nothing here (no wrong-source fallback).
        spath = sdir / "player_stats.json"
        if not stat_categories or not spath.exists():
            continue
        player_stats = load_json(spath)
        team_names = player_stats.get("teams", {})
        team_season_stats = player_stats.get("team_season_stats", {})
        for cat in counting_scoring_stats(stat_categories):
            abbr = stat_abbr(cat)
            stat_seasons.setdefault(abbr, set()).add(season)
            board = stat_boards.get(abbr)
            if board is None:
                # Yahoo's ``name`` is the friendly label ("Home Runs"); its
                # ``display_name`` is just the abbr. Prefer name, fall back down.
                board = stat_boards[abbr] = {
                    "display": cat.get("name") or cat.get("display_name") or abbr,
                    "entries": []}
                stat_order.append(abbr)
            sid = str(cat["stat_id"])
            for team_id, stats in team_season_stats.items():
                v = to_number(stats.get(sid))
                if v is None:
                    continue
                board["entries"].append({
                    "fantasy_team": team_names.get(team_id, ""),
                    "value": clean_number(v, abbr), "season": season, "_raw": v})

    def public(rows: List[dict]) -> List[dict]:
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]

    best = sorted(season_rows, key=lambda r: (-r["_w"], r["_l"]))[:5]
    worst = sorted(season_rows, key=lambda r: (-r["_l"], r["_w"]))[:5]

    # A board earns a place only if the stat was scored in >= MIN_STAT_SEASONS
    # seasons AND has team totals to rank. Short-lived cats (a category the league
    # carried a year or two, then dropped) produce a "record" that isn't all-time.
    kept, dropped = [], []
    for abbr in stat_order:
        span = len(stat_seasons.get(abbr, set()))
        if stat_boards[abbr]["entries"] and span >= MIN_STAT_SEASONS:
            kept.append(abbr)
        else:
            dropped.append((abbr, span))
    if dropped:
        log("    dropped short-lived / empty counting boards: "
            + ", ".join(f"{a} ({s}yr)" for a, s in dropped))

    season_stats = [
        {"stat": abbr, "display": stat_boards[abbr]["display"],
         "entries": public(sorted(stat_boards[abbr]["entries"],
                                  key=lambda e: -e["_raw"])[:5])}
        for abbr in kept
    ]

    return {
        "scoring_type": scoring,
        "best_season": public(best),
        "worst_season": public(worst),
        "season_stats": season_stats,
    }


# --------------------------------------------------------------------------- #
# Player records
# --------------------------------------------------------------------------- #
def compute_player_records(league_id: str, seasons: List[int], names: Dict[str, str]) -> dict:
    """Top-N all-time player leaderboards per stat (issue #30).

    For every counting scoring category, collect *every* player-season and
    player-week line, then keep the top ``PLAYER_TOP_N`` by value. The unit is a
    player-season / player-week, so the same player may hold several places on a
    board — different seasons are distinct marks. Only counting stats are ranked
    (via ``counting_scoring_stats``): rate stats (AVG/ERA/WHIP…) and lower-is-
    better stats are excluded — an all-time record is an unambiguous maximum, and
    excluding ratios keeps a wide category set (LOC scores 18) manageable.

    Reach is data-bound, not calendar-bound: Yahoo archival leaves early seasons
    without per-player lines (season totals reach ~2021+, weekly is current-season
    only), so a board spans exactly the seasons that carry player stats and grows
    as more live history accrues. The frontend surfaces the true covered span."""
    # abbr -> {"display", "group", "entries": [record dict, ...]} — accumulated,
    # then grouped/cut. ``stat_order`` is the first-seen scoring order; the final
    # output is re-sorted batting → pitching by ``group`` so a league that scores
    # both hitting and pitching cats (LOC scores 18) never interleaves the two.
    season_boards: Dict[str, dict] = {}
    week_boards: Dict[str, dict] = {}
    stat_order: List[str] = []

    def name_of(pk: str) -> str:
        return names.get(pk) or _pretty_key(pk)

    def board(store: Dict[str, dict], abbr: str, display: str, group: str) -> dict:
        b = store.get(abbr)
        if b is None:
            b = store[abbr] = {"display": display, "group": group, "entries": []}
            if abbr not in stat_order:
                stat_order.append(abbr)
        return b

    for season in seasons:
        sdir = season_dir(league_id, season)
        cat_path = sdir / "stat_categories.json"
        stats_path = sdir / "player_stats.json"
        if not cat_path.exists() or not stats_path.exists():
            continue

        stat_categories = load_json(cat_path)
        player_stats = load_json(stats_path)
        team_names = player_stats.get("teams", {})

        # Stat id -> (abbr, display, group) for the counting scoring cats (rate and
        # lower-is-better stats excluded, deduped by abbr). Yahoo's ``name`` is the
        # friendly label ("Home Runs"); its ``display_name`` is just the abbr.
        tracked: Dict[str, tuple] = {}
        for cat in counting_scoring_stats(stat_categories):
            abbr = stat_abbr(cat)
            display = cat.get("name") or cat.get("display_name") or abbr
            tracked[str(cat["stat_id"])] = (abbr, display, cat.get("group", ""))

        # Season totals.
        for team_id, players in player_stats.get("season_totals", {}).items():
            team_name = team_names.get(team_id, "")
            for pk, line in players.items():
                for sid, (abbr, display, group) in tracked.items():
                    v = to_number(line.get(sid))
                    if v is None:
                        continue
                    board(season_boards, abbr, display, group)["entries"].append(
                        {"value": clean_number(v, abbr), "player_name": name_of(pk),
                         "fantasy_team": team_name, "season": season, "_raw": v})

        # Single-week.
        for week, teams in player_stats.get("weekly", {}).items():
            wk = int(week)
            for team_id, players in teams.items():
                team_name = team_names.get(team_id, "")
                for pk, line in players.items():
                    for sid, (abbr, display, group) in tracked.items():
                        v = to_number(line.get(sid))
                        if v is None:
                            continue
                        board(week_boards, abbr, display, group)["entries"].append(
                            {"value": clean_number(v, abbr), "player_name": name_of(pk),
                             "fantasy_team": team_name, "season": season, "week": wk,
                             "_raw": v})

    # Batting boards before pitching; original scoring order within each group.
    group_rank = {"batting": 0, "pitching": 1}

    def finalize(store: Dict[str, dict]) -> List[dict]:
        present = [a for a in stat_order if store.get(a) and store[a]["entries"]]
        present.sort(key=lambda a: (group_rank.get(store[a]["group"], 2),
                                    stat_order.index(a)))
        out = []
        for abbr in present:
            b = store[abbr]
            entries = sorted(b["entries"], key=lambda e: -e["_raw"])[:PLAYER_TOP_N]
            for e in entries:
                e.pop("_raw", None)
            out.append({"stat": abbr, "display": b["display"],
                        "group": b["group"], "entries": entries})
        return out

    return {"single_week": finalize(week_boards), "season_total": finalize(season_boards)}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    leagues_index = load_json(DATA_DIR / "leagues.json")
    leagues = leagues_index.get("leagues", [])
    updated = utc_now()

    teams_out: Dict[str, dict] = {}
    players_out: Dict[str, dict] = {}

    for league in leagues:
        league_id = str(league["id"])
        seasons = league.get("seasons") or list_seasons(league_id)
        seasons = sorted(int(s) for s in seasons)
        log(f"League {league_id} - {len(seasons)} seasons: {seasons}")

        scoring = league_scoring_type(league_id, seasons)
        names = build_name_index(league_id, seasons)
        teams_out[league_id] = compute_team_records(league_id, seasons, scoring)
        players_out[league_id] = compute_player_records(league_id, seasons, names)
        tr = teams_out[league_id]
        log(f"  team records ({scoring or 'scoring_type?'}): "
            f"{len(tr['best_season'])} best / {len(tr['worst_season'])} worst season, "
            f"{len(tr['season_stats'])} counting-stat boards; "
            f"{len(players_out[league_id]['season_total'])} season + "
            f"{len(players_out[league_id]['single_week'])} weekly player records")

    dump_json(DATA_DIR / "records_teams.json", {"updated_at": updated, "leagues": teams_out})
    dump_json(DATA_DIR / "records_players.json", {"updated_at": updated, "leagues": players_out})
    log("Wrote records_teams.json and records_players.json")


if __name__ == "__main__":
    main()

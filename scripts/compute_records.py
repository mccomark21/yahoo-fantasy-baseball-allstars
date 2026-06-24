#!/usr/bin/env python3
"""Compute all-time records across every stored season.

Reads ALL raw per-season JSON for each league and writes:

  data/records_teams.json    highest single-week score, most category wins in a
                             week, longest win streak, best season record
  data/records_players.json  single-week and season-total records per stat,
                             with player / fantasy-team / season / week context

Player attribution: a player's weekly and season lines are tied to the fantasy
team that rostered them that season (captured per-team in player_stats.json).
Player *names* come from roster snapshots pooled across all seasons; a player who
only ever appears mid-season and was never on a season-end roster falls back to a
cleaned player key. Single-week records cover counting stats only (a 1-AB 1.000
AVG week is noise); season totals include rate stats too.

    python scripts/compute_records.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    DATA_DIR, RATE_STATS, clean_number, dump_json, higher_is_better, list_seasons,
    load_json, scoring_stats, season_dir, stat_abbr, to_number,
)


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
def compute_team_records(league_id: str, seasons: List[int]) -> dict:
    highest_week = None          # max team points (= category wins) in any week
    longest_streak = None        # longest consecutive-win run within a season
    best_record = None           # most wins in a season (tiebreak: fewer losses)

    for season in seasons:
        path = season_dir(league_id, season) / "matchups.json"
        if not path.exists():
            continue
        matchups = load_json(path).get("matchups", [])

        names: Dict[str, str] = {}
        results: Dict[str, List[tuple]] = {}  # team_key -> [(week, 'W'|'L'|'T')]

        for m in matchups:
            week = int(m.get("week") or 0)
            winner = m.get("winner_team_key") or ""
            tied = bool(m.get("is_tied"))
            for t in m.get("teams", []):
                key = t.get("team_key", "")
                name = t.get("name", "")
                if key:
                    names[key] = name
                pts = to_number(t.get("points"))
                if pts is not None and (highest_week is None or pts > highest_week["score"]):
                    highest_week = {"fantasy_team": name, "score": clean_number(pts, ""),
                                    "season": season, "week": week}
                if tied:
                    res = "T"
                elif winner and key == winner:
                    res = "W"
                elif winner:
                    res = "L"
                else:
                    res = None
                if res and key:
                    results.setdefault(key, []).append((week, res))

        for key, games in results.items():
            games.sort(key=lambda g: g[0])
            wins = sum(1 for _, r in games if r == "W")
            losses = sum(1 for _, r in games if r == "L")
            name = names.get(key, "")

            run = best_run = 0
            for _, r in games:
                run = run + 1 if r == "W" else 0
                best_run = max(best_run, run)
            if best_run and (longest_streak is None or best_run > longest_streak["streak"]):
                longest_streak = {"fantasy_team": name, "streak": best_run, "season": season}

            if best_record is None or (wins, -losses) > (best_record["wins"], -best_record["losses"]):
                best_record = {"fantasy_team": name, "wins": wins, "losses": losses, "season": season}

    most_category_wins = None
    if highest_week is not None:
        # In H2H-categories scoring a team's weekly points ARE its category wins.
        most_category_wins = {"fantasy_team": highest_week["fantasy_team"],
                              "wins": highest_week["score"],
                              "season": highest_week["season"], "week": highest_week["week"]}

    return {
        "highest_week_score": highest_week,
        "most_category_wins_week": most_category_wins,
        "longest_win_streak": longest_streak,
        "best_season_record": best_record,
    }


# --------------------------------------------------------------------------- #
# Player records
# --------------------------------------------------------------------------- #
def compute_player_records(league_id: str, seasons: List[int], names: Dict[str, str]) -> dict:
    # abbr -> winning record dict. Only "higher is better" stats are tracked
    # (an all-time record is a maximum).
    season_best: Dict[str, dict] = {}
    week_best: Dict[str, dict] = {}

    for season in seasons:
        sdir = season_dir(league_id, season)
        cat_path = sdir / "stat_categories.json"
        stats_path = sdir / "player_stats.json"
        if not cat_path.exists() or not stats_path.exists():
            continue

        stat_categories = load_json(cat_path)
        player_stats = load_json(stats_path)
        team_names = player_stats.get("teams", {})

        # Stat id -> (abbr, counting?) for the higher-is-better scoring cats.
        tracked: Dict[str, tuple] = {}
        for cat in scoring_stats(stat_categories):
            if not higher_is_better(cat):
                continue  # a "record low ERA" is noisy/ambiguous — skip
            abbr = stat_abbr(cat)
            tracked[str(cat["stat_id"])] = (abbr, abbr.upper() not in RATE_STATS)

        def name_of(pk: str) -> str:
            return names.get(pk) or _pretty_key(pk)

        # Season totals.
        for team_id, players in player_stats.get("season_totals", {}).items():
            team_name = team_names.get(team_id, "")
            for pk, line in players.items():
                for sid, (abbr, _counting) in tracked.items():
                    v = to_number(line.get(sid))
                    if v is None:
                        continue
                    cur = season_best.get(abbr)
                    if cur is None or v > cur["_raw"]:
                        season_best[abbr] = {"stat": abbr, "value": clean_number(v, abbr),
                                             "player_name": name_of(pk), "fantasy_team": team_name,
                                             "season": season, "_raw": v}

        # Single-week (counting stats only).
        for week, teams in player_stats.get("weekly", {}).items():
            wk = int(week)
            for team_id, players in teams.items():
                team_name = team_names.get(team_id, "")
                for pk, line in players.items():
                    for sid, (abbr, counting) in tracked.items():
                        if not counting:
                            continue
                        v = to_number(line.get(sid))
                        if v is None:
                            continue
                        cur = week_best.get(abbr)
                        if cur is None or v > cur["_raw"]:
                            week_best[abbr] = {"stat": abbr, "value": clean_number(v, abbr),
                                               "player_name": name_of(pk), "fantasy_team": team_name,
                                               "season": season, "week": wk, "_raw": v}

    def finalize(d: Dict[str, dict]) -> List[dict]:
        out = []
        for rec in sorted(d.values(), key=lambda r: r["stat"]):
            rec.pop("_raw", None)
            out.append(rec)
        return out

    return {"single_week": finalize(week_best), "season_total": finalize(season_best)}


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

        names = build_name_index(league_id, seasons)
        teams_out[league_id] = compute_team_records(league_id, seasons)
        players_out[league_id] = compute_player_records(league_id, seasons, names)
        log(f"  team records computed; "
            f"{len(players_out[league_id]['season_total'])} season + "
            f"{len(players_out[league_id]['single_week'])} weekly player records")

    dump_json(DATA_DIR / "records_teams.json", {"updated_at": updated, "leagues": teams_out})
    dump_json(DATA_DIR / "records_players.json", {"updated_at": updated, "leagues": players_out})
    log("Wrote records_teams.json and records_players.json")


if __name__ == "__main__":
    main()

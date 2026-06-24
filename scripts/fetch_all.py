#!/usr/bin/env python3
"""Fetch Yahoo Fantasy Baseball data and write the raw per-season JSON layer.

Two modes:

  --mode backfill   Discover every season each league existed (walking the
                    ``renew`` chain) and fetch everything for all of them. Slow,
                    run once. Historical seasons are never re-fetched here on a
                    later refresh.

  --mode refresh    Current season only — re-fetch and overwrite just that
                    season's raw JSON. This is the daily-cron path.

Output per league/season → ``data/{league_id}/{season}/``:
  stat_categories.json, rosters.json, player_stats.json, matchups.json

It also (re)writes ``data/leagues.json`` (the league/season index the frontend
and compute scripts read). Raw files are keyed under the *entry* league id from
``config.yaml`` so every season of a league lives in one directory tree.

Progress is printed to stdout so it's visible in the GitHub Actions log.

    python scripts/fetch_all.py --mode backfill
    python scripts/fetch_all.py --mode refresh
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA_DIR, dump_json, list_seasons, season_dir  # noqa: E402
from yahoo_client import YahooClient  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# --------------------------------------------------------------------------- #
# Week planning
# --------------------------------------------------------------------------- #
def planned_weeks(descriptor: dict) -> List[int]:
    """Weeks to fetch for a season, tolerant of Yahoo's metadata quirks.

    Normally ``start_week``..``end_week``, capped at ``current_week`` for a
    season still in progress. The 2020 COVID season returns bogus bounds for
    some leagues (``start=end=0``); there we fall back to ``1``..``current_week``.
    """
    start = int(descriptor.get("start_week") or 0)
    end = int(descriptor.get("end_week") or 0)
    current = int(descriptor.get("current_week") or 0)

    if start <= 0:
        start = 1
    if end < start:
        end = current if current >= start else 0
    if current and current < end:
        end = current  # season in progress — only completed/active weeks exist
    if end < start:
        return []
    return list(range(start, end + 1))


# --------------------------------------------------------------------------- #
# Per-season fetch
# --------------------------------------------------------------------------- #
def fetch_season(client: YahooClient, entry_league_id: str, descriptor: dict) -> None:
    """Fetch all four raw files for one league-season and write them to disk."""
    season = descriptor["season"]
    game_key = descriptor["game_key"]
    league_id = descriptor["league_id"]  # per-season Yahoo id (renew chain)
    out_dir = season_dir(entry_league_id, season)

    log(f"  [{season}] league {league_id} game_key {game_key}")

    # 1. Stat categories ---------------------------------------------------- #
    try:
        stat_categories = client.fetch_stat_categories(league_id, game_key, season)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! stat categories failed: {exc}")
        stat_categories = {"league_id": league_id, "game_key": game_key,
                           "season": season, "stats": [], "scoring_stat_ids": []}
    dump_json(out_dir / "stat_categories.json", stat_categories)

    # 2. Rosters (player info + fantasy-team assignment) -------------------- #
    teams: List[dict] = []
    try:
        teams = client.fetch_teams(league_id, game_key)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! team list failed: {exc}")

    roster_teams = []
    for team in teams:
        try:
            players = client.fetch_roster(team["team_id"], league_id, game_key, "current")
        except Exception as exc:  # noqa: BLE001
            log(f"    ! roster failed for {team['name']}: {exc}")
            players = []
        roster_teams.append({**team, "players": players})
    dump_json(out_dir / "rosters.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "week_label": "current", "teams": roster_teams,
    })
    log(f"    rosters: {len(roster_teams)} teams")

    # 3. Player stats — season totals + week-by-week, per fantasy team ------ #
    #    Captured per team (not merged) so records can attribute each player's
    #    weekly line to the team that actually rostered them that week.
    weeks = planned_weeks(descriptor)
    season_totals: Dict[str, dict] = {}
    for team in teams:
        season_totals[team["team_id"]] = _safe_roster_stats(
            client, team, league_id, game_key, None, "season")

    weekly: Dict[str, dict] = {}
    for week in weeks:
        per_team: Dict[str, dict] = {}
        for team in teams:
            per_team[team["team_id"]] = _safe_roster_stats(
                client, team, league_id, game_key, week, f"week {week}")
        weekly[str(week)] = per_team
    dump_json(out_dir / "player_stats.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "teams": {t["team_id"]: t["name"] for t in teams},
        "season_totals": season_totals,
        "weekly": weekly,
    })
    log(f"    player_stats: season totals + {len(weeks)} weeks")

    # 4. Matchups ----------------------------------------------------------- #
    try:
        matchups = client.fetch_matchups(league_id, game_key, weeks or None)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! matchups failed: {exc}")
        matchups = []
    dump_json(out_dir / "matchups.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "matchups": matchups,
    })
    log(f"    matchups: {len(matchups)} records")


def season_is_complete(entry_league_id: str, season) -> bool:
    """True if a season already has substantive data on disk.

    Used by ``--resume`` to skip seasons fetched in a prior run. A season
    counts as complete only when all four raw files exist and the
    rate/network-sensitive ones (player stats, matchups) carry real content —
    a stalled request leaves them empty (``{}``/``0`` bytes), so size is a
    good-enough proxy for "actually fetched".
    """
    d = season_dir(entry_league_id, season)
    needed = ("stat_categories.json", "rosters.json", "player_stats.json", "matchups.json")
    if not all((d / f).exists() for f in needed):
        return False
    # player_stats holds season + weekly lines; a real one is many KB.
    if (d / "player_stats.json").stat().st_size < 1000:
        return False
    # matchups for a full season are tens of KB; an empty list is ~90 bytes.
    if (d / "matchups.json").stat().st_size < 250:
        return False
    return True


def _safe_roster_stats(client, team, league_id, game_key, week, scope) -> dict:
    try:
        return client.fetch_roster_stats(team["team_id"], league_id, game_key, week)
    except Exception as exc:  # noqa: BLE001 — one bad team shouldn't kill the run
        log(f"    ! {scope} stats failed for {team['name']}: {exc}")
        return {}


# --------------------------------------------------------------------------- #
# leagues.json index
# --------------------------------------------------------------------------- #
def write_leagues_index(entries: List[dict]) -> None:
    """Write data/leagues.json from per-league season info.

    ``entries`` items: ``{id, name, seasons:[int,...]}``. Top-level ``season``
    is the latest across all leagues.
    """
    leagues = []
    latest = 0
    for e in entries:
        seasons = sorted(e["seasons"])
        if not seasons:
            continue
        cur = seasons[-1]
        latest = max(latest, cur)
        leagues.append({"id": e["id"], "name": e["name"], "season": cur, "seasons": seasons})
    dump_json(DATA_DIR / "leagues.json", {
        "season": latest, "updated_at": utc_now(), "leagues": leagues,
    })
    log(f"Wrote leagues.json ({len(leagues)} leagues, latest season {latest})")


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def run_backfill(client: YahooClient, league_ids: List[str], resume: bool = False) -> None:
    index_entries = []
    for league_id in league_ids:
        log(f"\n=== Backfill league {league_id} ===")
        seasons = client.discover_league_seasons(league_id)
        log(f"Discovered {len(seasons)} seasons: {[s['season'] for s in seasons]}")
        for descriptor in seasons:
            if resume and season_is_complete(league_id, descriptor["season"]):
                log(f"  [{descriptor['season']}] already complete — skipping (resume)")
                continue
            fetch_season(client, league_id, descriptor)
        name = seasons[-1]["name"] if seasons else league_id
        index_entries.append({"id": league_id, "name": name,
                              "seasons": [s["season"] for s in seasons]})
    write_leagues_index(index_entries)


def run_refresh(client: YahooClient, league_ids: List[str]) -> None:
    index_entries = []
    for league_id in league_ids:
        log(f"\n=== Refresh league {league_id} (current season) ===")
        descriptor = client.fetch_league_metadata(league_id)  # current season
        fetch_season(client, league_id, descriptor)
        # Season list = whatever's already on disk plus the just-refreshed one.
        seasons = sorted(set(list_seasons(league_id)) | {descriptor["season"]})
        index_entries.append({"id": league_id, "name": descriptor["name"], "seasons": seasons})
    write_leagues_index(index_entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", required=True, choices=("backfill", "refresh"))
    parser.add_argument("--resume", action="store_true",
                        help="Backfill only: skip seasons already complete on disk.")
    args = parser.parse_args()

    config = load_config()
    league_ids = [str(lid) for lid in config.get("league_ids", [])]
    if not league_ids:
        log("No league_ids found in config.yaml — nothing to do.")
        sys.exit(1)

    client = YahooClient()
    if args.mode == "backfill":
        run_backfill(client, league_ids, resume=args.resume)
    else:
        run_refresh(client, league_ids)
    log("\nDone.")


if __name__ == "__main__":
    main()

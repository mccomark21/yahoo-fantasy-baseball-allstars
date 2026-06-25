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

from common import DATA_DIR, dump_json, list_seasons, season_dir, to_number  # noqa: E402
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


def planned_sample_weeks(descriptor: dict, count: int = 5) -> List[int]:
    """``count`` evenly-spaced weeks across a season, for sampling rosters.

    Used to estimate how much of a season each player was rostered without
    fetching every week. Always includes the first and last playable week. If
    the season has ``<= count`` weeks, returns them all.
    """
    weeks = planned_weeks(descriptor)
    if not weeks or count <= 0:
        return []
    if count == 1:
        return [weeks[-1]]
    if len(weeks) <= count:
        return weeks
    last = len(weeks) - 1
    idxs = sorted({round(i * last / (count - 1)) for i in range(count)})
    return [weeks[i] for i in idxs]


# Minimum roster-week-weighted coverage for a historical season to be kept.
# Each player counts in proportion to how much of the season they were rostered
# (see ``_roster_week_weights``), so a briefly-rostered retiree barely lowers
# the bar; a player who was a season-long hole counts fully. Below this, too
# much of the season's roster-value is unrecoverable to show honestly.
MIN_COVERAGE = 0.75


# --------------------------------------------------------------------------- #
# Per-season fetch
# --------------------------------------------------------------------------- #
def fetch_season(
    client: YahooClient,
    entry_league_id: str,
    descriptor: dict,
    cur_game_key: str,
    cur_league_id: str,
) -> bool:
    """Fetch and write all raw files for one league-season.

    The current season uses Yahoo's per-team roster-stats endpoint (season
    totals + weekly). Past seasons can't get stats that way — their archived
    game returns zeros — so they're pulled via the current-game recipe
    (``YahooClient.fetch_current_game_season_stats``), season totals only.
    A past season whose reachable-player coverage falls below ``MIN_COVERAGE``
    is skipped entirely and *not* written. Returns ``True`` when the season was
    written, ``False`` when skipped.
    """
    season = descriptor["season"]
    game_key = descriptor["game_key"]
    league_id = descriptor["league_id"]  # per-season Yahoo id (renew chain)
    is_current = str(game_key) == str(cur_game_key)
    out_dir = season_dir(entry_league_id, season)

    log(f"  [{season}] league {league_id} game_key {game_key}"
        + ("" if is_current else "  (historical)"))

    # 1. Stat categories ---------------------------------------------------- #
    try:
        stat_categories = client.fetch_stat_categories(league_id, game_key, season)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! stat categories failed: {exc}")
        stat_categories = {"league_id": league_id, "game_key": game_key,
                           "season": season, "stats": [], "scoring_stat_ids": []}

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

    # 3. Player stats ------------------------------------------------------- #
    #    Captured per team (not merged) so records can attribute each player's
    #    line to the team that rostered them that season.
    weeks = planned_weeks(descriptor)
    coverage: Optional[dict] = None
    if is_current:
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
        stats_label = f"season totals + {len(weeks)} weeks"
    else:
        # Weight each player by how much of the season they were rostered, so a
        # briefly-rostered retiree barely moves the coverage gate.
        weights = _roster_week_weights(
            client, roster_teams, descriptor, league_id, game_key)
        season_totals, coverage = _historical_season_totals(
            client, roster_teams, season, cur_league_id, cur_game_key, weights=weights)
        weekly = {}  # Yahoo serves no historical weekly per-player stats for MLB.
        if coverage["rate"] < MIN_COVERAGE:
            log(f"    coverage {coverage['rate']:.0%} "
                f"({coverage['reachable']}/{coverage['total']}) < {MIN_COVERAGE:.0%} "
                f"— excluding season, nothing written")
            return False
        stats_label = (f"season totals (coverage {coverage['rate']:.0%}, "
                       f"{len(coverage['unreachable'])} players unavailable)")

    # 4. Matchups ----------------------------------------------------------- #
    try:
        matchups = client.fetch_matchups(league_id, game_key, weeks or None)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! matchups failed: {exc}")
        matchups = []

    # Write everything (only reached once a historical season clears coverage). #
    dump_json(out_dir / "stat_categories.json", stat_categories)
    dump_json(out_dir / "rosters.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "week_label": "current", "teams": roster_teams,
    })
    log(f"    rosters: {len(roster_teams)} teams")
    player_stats = {
        "league_id": league_id, "game_key": game_key, "season": season,
        "teams": {t["team_id"]: t["name"] for t in teams},
        "season_totals": season_totals,
        "weekly": weekly,
    }
    if coverage is not None:
        player_stats["coverage"] = coverage
    dump_json(out_dir / "player_stats.json", player_stats)
    log(f"    player_stats: {stats_label}")
    dump_json(out_dir / "matchups.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "matchups": matchups,
    })
    log(f"    matchups: {len(matchups)} records")
    return True


def _roster_week_weights(
    client: YahooClient, roster_teams: List[dict], descriptor: dict,
    league_id: str, game_key: str, count: int = 5,
) -> Dict[str, float]:
    """Each end-of-season-rostered player's share of the season, in [0, 1].

    Samples ``count`` evenly-spaced weeks' league rosters and weights every
    player by the fraction of those samples they appear in. Players rostered
    all season approach 1.0; late-season adds approach 0. When the season has
    no samplable weeks, everyone weighs 1.0 (degrades to a head count).
    """
    end_ids = {str(p["player_id"]) for t in roster_teams
               for p in t["players"] if p.get("player_id")}
    weeks = planned_sample_weeks(descriptor, count)
    if not weeks:
        return {pid: 1.0 for pid in end_ids}

    appearances: Dict[str, int] = {pid: 0 for pid in end_ids}
    for week in weeks:
        try:
            rosters = client.fetch_league_rosters(league_id, game_key, week)
        except Exception as exc:  # noqa: BLE001 — a bad week shouldn't kill weighting
            log(f"    ! sample roster failed for week {week}: {exc}")
            continue
        present = {str(p.get("player_id")) for team in rosters
                   for p in team.get("players", [])}
        for pid in end_ids & present:
            appearances[pid] += 1
    return {pid: appearances[pid] / len(weeks) for pid in end_ids}


def _historical_season_totals(
    client: YahooClient, roster_teams: List[dict], season: int,
    cur_league_id: str, cur_game_key: str,
    weights: Optional[Dict[str, float]] = None,
) -> tuple[Dict[str, dict], dict]:
    """Season totals for a past season via the current game, plus a coverage block.

    Returns ``(season_totals, coverage)`` where ``season_totals`` is keyed
    ``{team_id: {historical_player_key: {stat_id: value}}}`` (the shape the
    compute scripts expect) and ``coverage`` summarizes reachability.

    ``coverage["rate"]`` is *roster-week weighted*: each player contributes
    ``weights[player_id]`` (their share of the season rostered) to both the
    denominator and — if reachable — the numerator, so a player who barely
    played barely affects the gate. With ``weights=None`` every player weighs
    1.0, i.e. a plain head-count ratio.
    """
    # Distinct stable player_ids across all rosters this season.
    ids = {str(p["player_id"]) for t in roster_teams for p in t["players"] if p.get("player_id")}
    stats_by_id, unreachable = client.fetch_current_game_season_stats(
        ids, season, cur_league_id, cur_game_key)

    season_totals: Dict[str, dict] = {}
    for team in roster_teams:
        team_stats: Dict[str, dict] = {}
        for player in team["players"]:
            pid = str(player.get("player_id") or "")
            pk = player.get("player_key", "")
            line = stats_by_id.get(pid)
            if pk and line is not None:
                team_stats[pk] = line
        season_totals[team["team_id"]] = team_stats

    missing = sorted(unreachable & ids)
    total = len(ids)
    reachable = total - len(missing)
    # Names for the unreachable players, for an honest "stats unavailable" label.
    names_by_id = {str(p.get("player_id")): p.get("name", "")
                   for t in roster_teams for p in t["players"]}

    def weight(pid: str) -> float:
        return 1.0 if weights is None else float(weights.get(pid, 0.0))

    total_weight = sum(weight(i) for i in ids)
    reachable_weight = sum(weight(i) for i in ids if i not in unreachable)
    # Fall back to the head-count ratio if no player carried any weight (e.g. a
    # season we couldn't sample) so a zero denominator never reads as 0% covered.
    if total_weight > 0:
        rate = round(reachable_weight / total_weight, 6)
    else:
        rate = (reachable / total) if total else 0.0

    coverage = {
        "total": total,
        "reachable": reachable,
        "rate": rate,
        "unreachable": [{"player_id": i, "name": names_by_id.get(i, "")} for i in missing],
    }
    return season_totals, coverage


def season_is_complete(entry_league_id: str, season) -> bool:
    """True if a season already has substantive, *real-valued* data on disk.

    Used by ``--resume`` to skip seasons fetched in a prior run. File size is
    not trusted here: a zero-value season (the old historical-stats bug) still
    produced ~800 KB files because the structure was present. So we require all
    four files to exist AND ``player_stats.json`` to carry at least one genuine
    non-zero stat value in ``season_totals``.
    """
    d = season_dir(entry_league_id, season)
    needed = ("stat_categories.json", "rosters.json", "player_stats.json", "matchups.json")
    if not all((d / f).exists() for f in needed):
        return False
    try:
        from common import load_json
        season_totals = load_json(d / "player_stats.json").get("season_totals", {})
    except Exception:  # noqa: BLE001 — unreadable/corrupt → treat as incomplete
        return False
    for team_lines in season_totals.values():
        for line in team_lines.values():
            for value in line.values():
                if to_number(value):  # truthy → real, non-zero numeric
                    return True
    return False


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
def run_backfill(client: YahooClient, league_ids: List[str], resume: bool = False,
                 since: Optional[int] = None) -> None:
    index_entries = []
    for league_id in league_ids:
        log(f"\n=== Backfill league {league_id} ===")
        seasons = client.discover_league_seasons(league_id)
        log(f"Discovered {len(seasons)} seasons: {[s['season'] for s in seasons]}")
        current = max(seasons, key=lambda s: s["season"]) if seasons else None
        cur_gk = current["game_key"] if current else None
        cur_lid = current["league_id"] if current else None
        if since is not None:
            seasons = [s for s in seasons if s["season"] >= since]
            log(f"  --since {since}: backfilling {[s['season'] for s in seasons]}")

        kept: List[int] = []
        for descriptor in seasons:
            if resume and season_is_complete(league_id, descriptor["season"]):
                log(f"  [{descriptor['season']}] already complete — skipping (resume)")
                kept.append(descriptor["season"])
                continue
            if fetch_season(client, league_id, descriptor, cur_gk, cur_lid):
                kept.append(descriptor["season"])
        name = seasons[-1]["name"] if seasons else league_id
        index_entries.append({"id": league_id, "name": name, "seasons": kept})
    write_leagues_index(index_entries)


def run_refresh(client: YahooClient, league_ids: List[str]) -> None:
    index_entries = []
    for league_id in league_ids:
        log(f"\n=== Refresh league {league_id} (current season) ===")
        descriptor = client.fetch_league_metadata(league_id)  # current season
        # Refresh only ever touches the current season, which is its own game.
        fetch_season(client, league_id, descriptor,
                     descriptor["game_key"], descriptor["league_id"])
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
    parser.add_argument("--since", type=int, default=None,
                        help="Backfill only: ignore seasons older than this year "
                             "(e.g. --since 2021).")
    args = parser.parse_args()

    config = load_config()
    league_ids = [str(lid) for lid in config.get("league_ids", [])]
    if not league_ids:
        log("No league_ids found in config.yaml — nothing to do.")
        sys.exit(1)

    client = YahooClient()
    if args.mode == "backfill":
        run_backfill(client, league_ids, resume=args.resume, since=args.since)
    else:
        run_refresh(client, league_ids)
    log("\nDone.")


if __name__ == "__main__":
    main()

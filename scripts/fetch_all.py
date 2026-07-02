#!/usr/bin/env python3
"""Fetch Yahoo Fantasy Baseball data and write the raw per-season JSON layer.

Two modes:

  --mode backfill   Discover every season each league existed (walking the
                    ``renew`` chain) and fetch everything for all of them. Slow,
                    run once. Historical seasons are never re-fetched here on a
                    later refresh.

  --mode refresh    Current season only — re-fetch and overwrite just that
                    season's raw JSON. This is the daily-cron path.

  --mode team-records
                    Team-records-only historical fill. Walks the ``renew`` chain
                    and, for every season the full backfill couldn't reach (it
                    drops pre-2021 seasons at the player-coverage gate), fetches
                    just the inputs Team Records need — settings, teams, per-team
                    season totals, matchups — bypassing the coverage gate. Team
                    totals survive game archival, so this reaches each league's
                    earliest season. Player-facing views are unaffected: the
                    added seasons carry no per-player data. Run once, like
                    backfill; never re-fetches a season already on disk.

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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402  (write_leagues_index reads common.DATA_DIR dynamically)
from common import dump_json, list_seasons, load_json, season_dir, to_number  # noqa: E402
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
# Weekly counting stats
# --------------------------------------------------------------------------- #
#
# Yahoo serves no true per-week per-player stats for MLB — only ``season``
# (cumulative) and ``date`` (single day) coverage; the roster-by-week endpoint
# silently collapses to a single date. So a faithful week is the *sum of its
# days*, and only for COUNTING stats. Rate stats (ratios) can't be summed, and
# their components (earned runs, walks/hits allowed) aren't tracked, so weekly
# covers counting categories only; rate stats stay season-totals-only.
#
# These are the global Yahoo MLB stat_ids for ratio/rate stats. stat_ids are
# global (id 3 is always AVG, 26 always ERA, ... — identical across leagues),
# so excluding by id is stable even as leagues enable different categories.
RATE_STAT_IDS = frozenset({
    "3",   # AVG
    "4",   # OBP
    "5",   # SLG
    "6",   # OPS
    "26",  # ERA
    "27",  # WHIP
    "37",  # K/BB
    "57",  # K/9
    "58",  # BB/9
    "60",  # H/AB (a composite pair, not a summable total)
})


def counting_stat_ids(stat_categories: dict) -> List[str]:
    """The league's scoring stats that are summable counting totals.

    Drops rate stats (see ``RATE_STAT_IDS``) from the league's scored
    categories, preserving order. These are the only stats a faithful weekly
    value can be reconstructed for.
    """
    return [sid for sid in stat_categories.get("scoring_stat_ids", [])
            if sid not in RATE_STAT_IDS]


def week_dates(start: str, end: str) -> List[str]:
    """Every ISO calendar date from ``start`` to ``end`` inclusive."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out: List[str] = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def sum_counting_stats(
    daily_lines: "Iterable[Dict[str, dict]]", counting_ids: "Iterable[str]",
) -> Dict[str, Dict[str, float]]:
    """Sum counting stats across a week's daily roster lines.

    ``daily_lines`` is one ``{player_key: {stat_id: value}}`` dict per day.
    Returns ``{player_key: {stat_id: weekly_total}}`` limited to ``counting_ids``
    (rate stats are never accumulated). Non-numeric values are skipped so a
    stray ``"-"`` never crashes the sum. A player present on only some days is
    summed over just those days.
    """
    ids = set(counting_ids)
    out: Dict[str, Dict[str, float]] = {}
    for day in daily_lines:
        for player_key, line in day.items():
            acc = out.setdefault(player_key, {})
            for sid, val in line.items():
                if sid in ids and isinstance(val, (int, float)) and not isinstance(val, bool):
                    acc[sid] = acc.get(sid, 0) + val
    return out


def weeks_needing_compute(
    planned: List[int], current_week: int, existing: "Iterable[str]",
    lookback: int = 1,
) -> List[int]:
    """Which planned weeks a refresh must (re)compute.

    Always recomputes the in-progress week plus ``lookback`` weeks behind it
    (so a week that just closed gets its final day settled), and fills any
    week missing from ``existing`` (e.g. a prior run that died mid-season).
    Completed weeks already on disk outside the lookback window are frozen.
    """
    have = {str(w) for w in existing}
    return [w for w in planned
            if w >= current_week - lookback or str(w) not in have]


# --------------------------------------------------------------------------- #
# Per-season fetch
# --------------------------------------------------------------------------- #
def fetch_season(
    client: YahooClient,
    entry_league_id: str,
    descriptor: dict,
    cur_game_key: str,
    cur_league_id: str,
    recompute_all_weeks: bool = False,
) -> bool:
    """Fetch and write all raw files for one league-season.

    The current season uses Yahoo's per-team roster-stats endpoint for season
    totals, plus per-day roster stats summed into real weekly counting totals
    (see ``_compute_weekly_counting``). Past seasons can't get stats that way —
    their archived game returns zeros — so they're pulled via the current-game
    recipe (``YahooClient.fetch_current_game_season_stats``), season totals only.
    A past season whose reachable-player coverage falls below ``MIN_COVERAGE``
    is skipped entirely and *not* written. Returns ``True`` when the season was
    written, ``False`` when skipped.

    ``recompute_all_weeks`` (backfill) rebuilds every week from scratch; left
    False (daily refresh) only the in-progress week + a lookback are recomputed
    and merged onto the weeks already frozen on disk, to keep the call count low.
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
                           "season": season, "scoring_type": "",
                           "stats": [], "scoring_stat_ids": []}

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
        weekly, recomputed = _compute_weekly_counting(
            client, teams, descriptor, stat_categories, out_dir,
            recompute_all_weeks=recompute_all_weeks)
        stats_label = (f"season totals + {len(weekly)} weeks "
                       f"(counting stats; {recomputed} recomputed)")
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
    # Team season category totals — the standings "Stats" view, and the correct
    # source for team counting-stat records (issue #29). Summing rostered players'
    # full individual season totals over-counts late adds and the bench; this is
    # Yahoo's own aggregate and, unlike per-player stats, it survives archival so
    # every season (current + historical) gets real numbers. One call per team.
    team_season_stats: Dict[str, dict] = {}
    for team in teams:
        tk = team.get("team_key")
        if not tk:
            continue
        try:
            team_season_stats[team["team_id"]] = client.fetch_team_season_stats(
                tk, league_id, game_key)
        except Exception as exc:  # noqa: BLE001
            log(f"    ! team season stats failed for {team['name']}: {exc}")

    player_stats = {
        "league_id": league_id, "game_key": game_key, "season": season,
        "teams": {t["team_id"]: t["name"] for t in teams},
        "season_totals": season_totals,
        "team_season_stats": team_season_stats,
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


def fetch_team_records_season(
    client: YahooClient,
    entry_league_id: str,
    descriptor: dict,
) -> bool:
    """Fetch ONLY the inputs Team Records needs for one historical season.

    Team-level season totals and matchups come straight from Yahoo and never
    touch individual players, and — unlike per-player stats — they *survive game
    archival*. So they reach as far back as the ``renew`` chain, well past the
    2021 wall the full path hits (that wall is the ≥``MIN_COVERAGE`` player gate,
    which exists only because retired players are unreachable). This path fetches
    stat categories + teams + per-team season totals + matchups, **bypasses the
    coverage gate entirely**, and writes a minimal raw set: no rosters, and a
    ``player_stats.json`` whose ``season_totals``/``weekly`` are empty (no
    per-player data is available or needed — ``compute_records`` already treats
    such a season as contributing nothing to player records and everything to
    team records).

    Returns ``True`` when a season carrying usable team data was written,
    ``False`` when there was nothing worth keeping (an archived stub with neither
    team totals nor matchups — the likely fate of the 2020 COVID season).
    """
    season = descriptor["season"]
    game_key = descriptor["game_key"]
    league_id = descriptor["league_id"]  # per-season Yahoo id (renew chain)
    out_dir = season_dir(entry_league_id, season)

    log(f"  [{season}] league {league_id} game_key {game_key}  (team records only)")

    # 1. Stat categories — for scoring_type, the category count C (W-L-T math),
    #    and the dynamic counting-cat set the boards are built from.
    try:
        stat_categories = client.fetch_stat_categories(league_id, game_key, season)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! stat categories failed: {exc}")
        stat_categories = {"league_id": league_id, "game_key": game_key,
                           "season": season, "scoring_type": "",
                           "stats": [], "scoring_stat_ids": []}

    # 2. Teams — only for team_key (to fetch totals) and the id→name map. No
    #    rosters, no per-player fetch: that's the archived, unreachable part.
    try:
        teams = client.fetch_teams(league_id, game_key)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! team list failed: {exc}")
        teams = []

    # 3. Team season category totals — Yahoo's authoritative team HR/R/K aggregate
    #    (the standings "Stats" view); survives archival, one call per team. This
    #    is the whole reason team records can go back further than everything else.
    team_season_stats: Dict[str, dict] = {}
    for team in teams:
        tk = team.get("team_key")
        if not tk:
            continue
        try:
            team_season_stats[team["team_id"]] = client.fetch_team_season_stats(
                tk, league_id, game_key)
        except Exception as exc:  # noqa: BLE001
            log(f"    ! team season stats failed for {team['name']}: {exc}")

    # 4. Matchups — the W-L-T source. Passing the planned weeks when we can derive
    #    them, else None so fetch_matchups reads the season's bounds from metadata.
    #    The 2020 COVID season can report start=end=0 and yield no weeks; that's
    #    handled below rather than treated as an error.
    try:
        matchups = client.fetch_matchups(
            league_id, game_key, planned_weeks(descriptor) or None)
    except Exception as exc:  # noqa: BLE001
        log(f"    ! matchups failed: {exc}")
        matchups = []

    # An archived stub with neither real team totals nor matchups has nothing to
    # show — skip it explicitly (and loudly) instead of writing an empty season.
    # ``team_season_stats`` can be a dict of *empty* per-team lines (2020's likely
    # shape), so check for actual stat content, not just team keys.
    has_team_data = any(line for line in team_season_stats.values())
    if not has_team_data and not matchups:
        log(f"    — no team totals and no matchups — skipping {season} "
            f"(nothing written)")
        return False

    dump_json(out_dir / "stat_categories.json", stat_categories)
    dump_json(out_dir / "player_stats.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "teams": {t["team_id"]: t["name"] for t in teams},
        "season_totals": {},          # no reachable per-player data (archived)
        "team_season_stats": team_season_stats,
        "weekly": {},                 # no historical weekly per-player stats
        "team_records_only": True,    # marks a lightweight historical season
    })
    dump_json(out_dir / "matchups.json", {
        "league_id": league_id, "game_key": game_key, "season": season,
        "matchups": matchups,
    })
    log(f"    wrote team-records season: {len(team_season_stats)} team totals, "
        f"{len(matchups)} matchups")
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


def _safe_roster_stats_by_date(client, team, league_id, game_key, day) -> dict:
    try:
        return client.fetch_roster_stats_by_date(team["team_id"], league_id, game_key, day)
    except Exception as exc:  # noqa: BLE001 — one bad (team, day) shouldn't kill the week
        log(f"    ! {day} stats failed for {team['name']}: {exc}")
        return {}


def _load_existing_weekly(out_dir) -> Dict[str, dict]:
    """The ``weekly`` block already on disk for this season (or ``{}``)."""
    from common import load_json
    try:
        return load_json(out_dir / "player_stats.json").get("weekly", {}) or {}
    except Exception:  # noqa: BLE001 — missing/corrupt → start fresh
        return {}


def _compute_weekly_counting(
    client: YahooClient, teams: List[dict], descriptor: dict,
    stat_categories: dict, out_dir, recompute_all_weeks: bool = False,
) -> tuple:
    """Build real per-week counting-stat totals for the current season.

    Each week is the *sum of its calendar days* (Yahoo serves no true per-week
    per-player MLB stats), restricted to counting categories — rate stats can't
    be summed and stay season-totals-only. One ``roster-by-date`` call per team
    per day; off-days sum harmlessly to zero.

    ``recompute_all_weeks`` rebuilds every planned week (backfill). Otherwise
    only the live edge is recomputed (``weeks_needing_compute``) and merged onto
    the weeks already frozen on disk. Returns ``(weekly, num_weeks_recomputed)``.
    """
    weeks = planned_weeks(descriptor)
    counting = counting_stat_ids(stat_categories)
    if not weeks or not counting:
        return {}, 0

    game_weeks = client.fetch_game_weeks(descriptor["league_id"], descriptor["game_key"])

    if recompute_all_weeks:
        weekly: Dict[str, dict] = {}
        to_compute = list(weeks)
    else:
        weekly = dict(_load_existing_weekly(out_dir))
        current_week = int(descriptor.get("current_week") or weeks[-1])
        to_compute = weeks_needing_compute(weeks, current_week, weekly.keys())

    league_id = descriptor["league_id"]
    game_key = descriptor["game_key"]
    for week in to_compute:
        span = game_weeks.get(week)
        if not span or not span[0] or not span[1]:
            log(f"    ! week {week}: no date range from Yahoo — skipped")
            continue
        days = week_dates(span[0], span[1])
        per_team: Dict[str, dict] = {}
        for team in teams:
            daily_lines = [
                _safe_roster_stats_by_date(client, team, league_id, game_key, day)
                for day in days
            ]
            per_team[team["team_id"]] = sum_counting_stats(daily_lines, counting)
        weekly[str(week)] = per_team

    return weekly, len(to_compute)


# --------------------------------------------------------------------------- #
# leagues.json index
# --------------------------------------------------------------------------- #
def write_leagues_index(entries: List[dict]) -> None:
    """Write data/leagues.json from per-league season info.

    ``entries`` items: ``{id, name, seasons:[int,...]}``. Top-level ``season``
    is the latest across all leagues.
    """
    # Per-league URL slugs (id → slug) drive the frontend's shareable hash
    # routes (#/<slug>). A league without a configured slug falls back to its id.
    slug_map = {str(k): str(v) for k, v in load_config().get("league_slugs", {}).items()}
    leagues = []
    latest = 0
    for e in entries:
        seasons = sorted(e["seasons"])
        if not seasons:
            continue
        cur = seasons[-1]
        latest = max(latest, cur)
        # Scoring format is a league-constant; surface it here (read from the raw
        # stat_categories fetch_season just wrote) so the frontend has it without
        # opening a per-season file. Newest season with a value wins.
        scoring = ""
        for s in reversed(seasons):
            cat_path = season_dir(e["id"], s) / "stat_categories.json"
            if cat_path.exists():
                st = common.scoring_type(load_json(cat_path))
                if st:
                    scoring = st
                    break
        leagues.append({"id": e["id"], "name": e["name"], "season": cur,
                        "slug": slug_map.get(e["id"], e["id"]),
                        "scoring_type": scoring, "seasons": seasons})
    # Read common.DATA_DIR at call time (not an import-time copy) so a test that
    # redirects ``common.DATA_DIR`` to a tmp dir actually catches this write.
    dump_json(common.DATA_DIR / "leagues.json", {
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
            if fetch_season(client, league_id, descriptor, cur_gk, cur_lid,
                            recompute_all_weeks=True):
                kept.append(descriptor["season"])
        name = seasons[-1]["name"] if seasons else league_id
        index_entries.append({"id": league_id, "name": name, "seasons": kept})
    write_leagues_index(index_entries)


def run_refresh(client: YahooClient, league_ids: List[str],
                rebuild_weeks: bool = False) -> None:
    index_entries = []
    for league_id in league_ids:
        log(f"\n=== Refresh league {league_id} (current season) ===")
        descriptor = client.fetch_league_metadata(league_id)  # current season
        # Refresh only ever touches the current season, which is its own game.
        # Normally only the live-edge week is recomputed; ``rebuild_weeks``
        # forces every week of the current season to be rebuilt from scratch
        # (a one-time repair, e.g. after changing how weekly is computed).
        fetch_season(client, league_id, descriptor,
                     descriptor["game_key"], descriptor["league_id"],
                     recompute_all_weeks=rebuild_weeks)
        # Season list = whatever's already on disk plus the just-refreshed one.
        seasons = sorted(set(list_seasons(league_id)) | {descriptor["season"]})
        index_entries.append({"id": league_id, "name": descriptor["name"], "seasons": seasons})
    write_leagues_index(index_entries)


def run_team_records_backfill(client: YahooClient, league_ids: List[str],
                              since: Optional[int] = None) -> None:
    """Fill the historical seasons the full backfill can't reach — for Team
    Records only.

    The full backfill drops every pre-2021 season at the player-coverage gate,
    so those seasons never land on disk. Team records don't need players, and
    their inputs survive archival (see ``fetch_team_records_season``), so this
    path walks the renew chain and fills exactly the *gap* seasons — the ones
    discovery finds that aren't already on disk. Seasons the full path already
    wrote (with real player data) are left untouched. ``leagues.json`` is then
    rewritten to span everything now on disk, so ``compute_records`` picks up the
    newly reachable team-seasons; player records stay put because the added
    seasons carry no per-player data.
    """
    index_entries = []
    for league_id in league_ids:
        log(f"\n=== Team-records backfill league {league_id} ===")
        seasons = client.discover_league_seasons(league_id)
        log(f"Discovered {len(seasons)} seasons: {[s['season'] for s in seasons]}")
        existing = set(list_seasons(league_id))
        gaps = [s for s in seasons if s["season"] not in existing]
        if since is not None:
            gaps = [s for s in gaps if s["season"] >= since]
        log(f"  on disk: {sorted(existing)}")
        log(f"  gap seasons to fill: {[s['season'] for s in gaps]}")

        written, skipped = [], []
        for descriptor in gaps:
            if fetch_team_records_season(client, league_id, descriptor):
                written.append(descriptor["season"])
            else:
                skipped.append(descriptor["season"])
        if skipped:
            log(f"  skipped (nothing to keep): {skipped}")

        # Season list = everything now on disk (existing full + new lightweight).
        all_seasons = sorted(set(list_seasons(league_id)))
        name = seasons[-1]["name"] if seasons else league_id
        index_entries.append({"id": league_id, "name": name, "seasons": all_seasons})
    write_leagues_index(index_entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", required=True,
                        choices=("backfill", "refresh", "team-records"))
    parser.add_argument("--resume", action="store_true",
                        help="Backfill only: skip seasons already complete on disk.")
    parser.add_argument("--since", type=int, default=None,
                        help="Backfill / team-records only: ignore seasons older "
                             "than this year (e.g. --since 2021).")
    parser.add_argument("--rebuild-weeks", action="store_true",
                        help="Refresh only: rebuild every week of the current "
                             "season from scratch (one-time weekly repair).")
    args = parser.parse_args()

    config = load_config()
    league_ids = [str(lid) for lid in config.get("league_ids", [])]
    if not league_ids:
        log("No league_ids found in config.yaml — nothing to do.")
        sys.exit(1)

    client = YahooClient()
    if args.mode == "backfill":
        run_backfill(client, league_ids, resume=args.resume, since=args.since)
    elif args.mode == "team-records":
        run_team_records_backfill(client, league_ids, since=args.since)
    else:
        run_refresh(client, league_ids, rebuild_weeks=args.rebuild_weeks)
    log("\nDone.")


if __name__ == "__main__":
    main()

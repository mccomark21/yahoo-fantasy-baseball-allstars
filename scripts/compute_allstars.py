#!/usr/bin/env python3
"""Compute the current-season all-star and positional-race aggregates.

Reads the raw per-season layer (``data/{league}/{season}/``) for each league's
*latest* season and writes:

  data/all_stars.json         top player per position per league
  data/positional_races.json  full ranked player list per position per league

Ranking uses actual season stats — not ``percent_owned``. Each player gets a
composite z-score: for every scoring category the league tracks, how many
standard deviations above/below the pool mean they sit (sign-flipped for "lower
is better" stats like ERA/WHIP), summed. Players are scored within role pools —
batters, starters, relievers — so wins are judged among starters and saves among
relievers, with innings as a starter workload qualifier. The all-star at each
position is the highest composite among players eligible there; the three
outfield slots are filled by three distinct players.

    python scripts/compute_allstars.py
"""

from __future__ import annotations

import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    DATA_DIR, assign_distinct, clean_number, counts_for_role, dump_json,
    eligible_positions, is_batter, is_pitching_stat, higher_is_better, load_json,
    mlb_team_id, mlb_team_logo_url, scoring_stats, season_dir, stat_abbr,
    to_number, TARGET_POSITIONS,
)


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_season_players(league_id: str, season: int) -> tuple[List[dict], dict]:
    """Return (rostered players with season stats attached, stat_categories).

    Each player dict carries roster info plus ``raw_stats`` (``{stat_id: value}``)
    and ``fantasy_team`` (the team currently rostering them).
    """
    sdir = season_dir(league_id, season)
    stat_categories = load_json(sdir / "stat_categories.json")
    rosters = load_json(sdir / "rosters.json")
    player_stats = load_json(sdir / "player_stats.json")

    # player_key -> season stat line, flattened across teams.
    stats_by_key: Dict[str, dict] = {}
    for team_stats in player_stats.get("season_totals", {}).values():
        stats_by_key.update(team_stats)

    players: List[dict] = []
    for team in rosters.get("teams", []):
        team_name = team.get("name", "")
        for info in team.get("players", []):
            pk = info.get("player_key", "")
            players.append({
                **info,
                "fantasy_team": team_name,
                "raw_stats": stats_by_key.get(pk, {}),
            })
    return players, stat_categories


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _category_distribution(pool: List[dict], stat_id: str):
    """(mean, stdev) of a stat across a player pool, or ``None`` if not rankable."""
    vals = [to_number(p["raw_stats"].get(stat_id)) for p in pool]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    stdev = statistics.pstdev(vals)
    if stdev == 0:
        return None
    return statistics.mean(vals), stdev


class ScoringPool:
    """Composite z-score of a player against one pool of comparable peers.

    A *pool* is the set of players a slot's candidates should be judged against
    (all batters, or just starters, or just relievers) together with the
    categories they're scored on. Each category contributes a z-score versus the
    pool's mean/stdev — sign-flipped for lower-is-better stats — and the score is
    their sum. Scoring within a role pool is what lets wins count among starters
    and saves among relievers: a reliever's zero wins no longer drags them
    against starters, because relievers are never scored in the starter pool.

    A workload qualifier (innings for starters) is just another category in the
    pool, so a starter below the pool's mean innings is penalized automatically.
    """

    def __init__(self, members: List[dict], categories: List[dict]):
        self.categories = list(categories)
        self.dists: Dict[str, tuple] = {}
        for cat in self.categories:
            sid = str(cat["stat_id"])
            dist = _category_distribution(members, sid)
            if dist is not None:
                self.dists[sid] = dist

    def score(self, player: dict) -> float:
        total = 0.0
        for cat in self.categories:
            sid = str(cat["stat_id"])
            dist = self.dists.get(sid)
            if dist is None:
                continue
            v = to_number(player["raw_stats"].get(sid))
            if v is None:
                continue
            mean, stdev = dist
            z = (v - mean) / stdev
            total += z if higher_is_better(cat) else -z
        return total


def _innings_category(stat_categories: dict) -> dict | None:
    """The Innings Pitched category, if the league tracks it — the SP workload
    qualifier. It's a display-only stat, so it isn't in ``scoring_stats``."""
    for stat in stat_categories.get("stats", []):
        if stat_abbr(stat).upper() == "IP":
            return stat
    return None


def score_players(players: List[dict], stat_categories: dict) -> List[dict]:
    """Attach ``batting_score``, ``sp_score`` and ``rp_score`` to every player.

    Batters are scored against the batter pool; starters against the SP pool
    (with an innings qualifier) and relievers against the RP pool, so each
    pitcher's role stats are judged among peers who accrue them."""
    cats = scoring_stats(stat_categories)
    batting_cats = [c for c in cats if not is_pitching_stat(c)]
    pitching_cats = [c for c in cats if is_pitching_stat(c)]
    ip_cat = _innings_category(stat_categories)
    sp_cats = [c for c in pitching_cats if counts_for_role(c, "SP")]
    sp_cats += [ip_cat] if ip_cat else []   # innings is the starter workload qualifier
    rp_cats = [c for c in pitching_cats if counts_for_role(c, "RP")]

    batters = [p for p in players if is_batter(p)]
    starters = [p for p in players if "SP" in eligible_positions(p)]
    relievers = [p for p in players if "RP" in eligible_positions(p)]

    batting_pool = ScoringPool(batters, batting_cats)
    sp_pool = ScoringPool(starters, sp_cats)
    rp_pool = ScoringPool(relievers, rp_cats)

    for p in players:
        p["batting_score"] = batting_pool.score(p)
        p["sp_score"] = sp_pool.score(p)
        p["rp_score"] = rp_pool.score(p)
    return cats


def _score_key(position: str) -> str:
    """Which composite ranks candidates for a diamond slot."""
    if position == "SP":
        return "sp_score"
    if position == "RP":
        return "rp_score"
    return "batting_score"


# --------------------------------------------------------------------------- #
# Output shaping
# --------------------------------------------------------------------------- #
def _display_stats(player: dict, cats: List[dict]) -> dict:
    out = {}
    for cat in cats:
        v = to_number(player["raw_stats"].get(str(cat["stat_id"])))
        if v is None:
            continue
        out[stat_abbr(cat)] = clean_number(v, stat_abbr(cat))
    return out


def _base_entry(player: dict, position: str, cats: List[dict]) -> dict:
    entry = {
        "player_name": player.get("name", ""),
        "position": position,
        "mlb_team": player.get("mlb_team", ""),
    }
    tid = mlb_team_id(player.get("mlb_team", ""))
    if tid is not None:
        entry["mlb_team_id"] = tid
        entry["mlb_team_logo_url"] = mlb_team_logo_url(player.get("mlb_team", ""))
    if player.get("headshot_url"):
        entry["headshot_url"] = player["headshot_url"]
    entry["fantasy_team"] = player.get("fantasy_team", "")
    entry["stats"] = _display_stats(player, cats)
    return entry


def build_league(players: List[dict], stat_categories: dict) -> tuple[dict, dict]:
    """Return (all_stars_for_league, races_for_league)."""
    cats = score_players(players, stat_categories)
    batting_cats = [c for c in cats if not is_pitching_stat(c)]
    pitching_cats = [c for c in cats if is_pitching_stat(c)]

    all_stars: Dict[str, dict] = {}
    races: Dict[str, list] = {}
    ranked_by_slot: Dict[str, list] = {}
    display_cats_by_slot: Dict[str, list] = {}

    for position in TARGET_POSITIONS:
        is_pitching = position in ("SP", "RP")
        score_key = _score_key(position)
        display_cats = pitching_cats if is_pitching else batting_cats

        candidates = [p for p in players if position in eligible_positions(p)]
        if not candidates:
            continue
        candidates.sort(key=lambda p: (-p[score_key], p.get("name", "")))
        ranked_by_slot[position] = candidates
        display_cats_by_slot[position] = display_cats

        race = []
        for rank, player in enumerate(candidates, start=1):
            entry = _base_entry(player, position, display_cats)
            race.append({"rank": rank, **entry, "score": round(player[score_key], 3)})
        races[position] = race

    # The diamond shows three distinct outfielders, not the same star three
    # times — assign within position groups before shaping the all-star entries.
    for position, player in assign_distinct(ranked_by_slot).items():
        all_stars[position] = _base_entry(player, position, display_cats_by_slot[position])

    _mark_leader(all_stars, players)
    return all_stars, races


def _mark_leader(all_stars: Dict[str, dict], players: List[dict]) -> None:
    """Flag the headline hitter — the highest batting composite among the
    batting-position all-stars — with ``is_leader``."""
    by_name = {p.get("name", ""): p for p in players}
    best_pos, best_score = None, None
    for position, entry in all_stars.items():
        if position in ("SP", "RP"):
            continue
        player = by_name.get(entry["player_name"])
        if player is None:
            continue
        if best_score is None or player["batting_score"] > best_score:
            best_score, best_pos = player["batting_score"], position
    if best_pos is not None:
        all_stars[best_pos]["is_leader"] = True


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    leagues_index = load_json(DATA_DIR / "leagues.json")
    leagues = leagues_index.get("leagues", [])
    top_season = leagues_index.get("season", 0)
    updated = utc_now()

    all_stars_out: Dict[str, dict] = {}
    races_out: Dict[str, dict] = {}

    for league in leagues:
        league_id = str(league["id"])
        season = int(league.get("season") or top_season)
        log(f"League {league_id} - season {season}")
        try:
            players, stat_categories = load_season_players(league_id, season)
        except FileNotFoundError as exc:
            log(f"  ! missing raw data, skipping: {exc}")
            continue
        all_stars, races = build_league(players, stat_categories)
        all_stars_out[league_id] = all_stars
        races_out[league_id] = races
        log(f"  {len(all_stars)} positions filled from {len(players)} rostered players")

    dump_json(DATA_DIR / "all_stars.json",
              {"season": top_season, "updated_at": updated, "leagues": all_stars_out})
    dump_json(DATA_DIR / "positional_races.json",
              {"season": top_season, "updated_at": updated, "leagues": races_out})
    log("Wrote all_stars.json and positional_races.json")


if __name__ == "__main__":
    main()

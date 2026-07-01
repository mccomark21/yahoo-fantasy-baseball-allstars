#!/usr/bin/env python3
"""Compute the current-season all-star and positional-race aggregates.

Reads the raw per-season layer (``data/{league}/{season}/``) for each league's
*latest* season and writes:

  data/all_stars.json         roster per league — lineup (fielders + Util),
                              bench (5 reserves), rotation (5 SP), bullpen (2 RP)
  data/positional_races.json  full ranked player list per position per league

Ranking uses actual season stats — not ``percent_owned``. Each player gets a
composite z-score: for every scoring category the league tracks, how many
standard deviations above/below the pool mean they sit (sign-flipped for "lower
is better" stats like ERA/WHIP), summed. Players are scored within role pools —
batters, starters, relievers — so wins are judged among starters and saves among
relievers, with innings as a starter workload qualifier. The starter at each
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
    BENCH_SIZE, BULLPEN_SIZE, DATA_DIR, INFIELD_POSITIONS, OF_SLOTS,
    RACE_POSITIONS, ROTATION_SIZE, assign_distinct, clean_number,
    counts_for_role, dump_json, eligible_positions, is_batter, is_pitcher,
    is_pitching_stat, higher_is_better, load_json, mlb_team_id,
    mlb_team_logo_url, player_key, scoring_stats, season_dir, stat_abbr,
    to_number,
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

    Each category's z-score is clamped to ``±Z_CLAMP`` before summing, so a lone
    freak-outlier stat can't run away with a composite — which matters most when
    the same composites are compared across roles to rank the bench (issue #27).
    """

    Z_CLAMP = 2.5

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
            z = max(-self.Z_CLAMP, min(self.Z_CLAMP, z))
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


def _best_pool_score(player: dict) -> float:
    """A player's strongest standardized composite across the pools they belong
    to — the cross-role yardstick the bench is ranked by (issue #27). Because
    each pool's z-scores are clamped to the same range, a hitter's batting
    composite and a pitcher's role composite are comparable enough to seed one
    position-agnostic reserve list."""
    scores = []
    if is_batter(player):
        scores.append(player["batting_score"])
    if "SP" in eligible_positions(player):
        scores.append(player["sp_score"])
    if "RP" in eligible_positions(player):
        scores.append(player["rp_score"])
    return max(scores) if scores else float("-inf")


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


def _display_cats_for(player: dict, batting_cats: List[dict],
                      pitching_cats: List[dict]) -> List[dict]:
    """Pitchers show pitching stats, everyone else their batting line — so a
    mixed bench renders each reserve in their own currency."""
    return pitching_cats if is_pitcher(player) and not is_batter(player) else batting_cats


def _rank_candidates(players: List[dict]) -> Dict[str, list]:
    """Full ranked candidate list per race position (single OF, no DH) — the raw
    pools both roster assignment and the emitted races draw from."""
    ranked: Dict[str, list] = {}
    for position in RACE_POSITIONS:
        score_key = _score_key(position)
        candidates = [p for p in players if position in eligible_positions(p)]
        if not candidates:
            continue
        candidates.sort(key=lambda p: (-p[score_key], p.get("name", "")))
        ranked[position] = candidates
    return ranked


def _shape_race(candidates: List[dict], position: str, cats_for, score_for) -> list:
    """JSON-ready ranked list — ``cats_for`` picks each row's display stats and
    ``score_for`` its composite (both callables of the player)."""
    return [
        {"rank": rank, **_base_entry(player, position, cats_for(player)),
         "score": round(score_for(player), 3)}
        for rank, player in enumerate(candidates, start=1)
    ]


def _build_races(ranked: Dict[str, list], bench_pool: List[dict], crowned: set,
                 batting_cats: List[dict], pitching_cats: List[dict]) -> dict:
    """The JSON positional-race lists.

    Fielding, OF and pitching races are the full ranked pools. The Util and Bench
    races drop anyone already ``crowned`` — a fielding-race leader, a starter or a
    reliever — so they surface only genuinely available flex/reserve options
    (issue #27). The Bench race additionally omits the Util pick (already applied
    to ``bench_pool``), so its top entries mirror the bench roster section."""
    races: Dict[str, list] = {}
    for position in INFIELD_POSITIONS + ["OF", "SP", "RP"]:
        if position not in ranked:
            continue
        cats = pitching_cats if position in ("SP", "RP") else batting_cats
        score_key = _score_key(position)
        races[position] = _shape_race(
            ranked[position], position, lambda p: cats, lambda p: p[score_key])

    util_pool = [p for p in ranked.get("UTIL", []) if player_key(p) not in crowned]
    races["UTIL"] = _shape_race(
        util_pool, "UTIL", lambda p: batting_cats, lambda p: p["batting_score"])

    races["BN"] = _shape_race(
        bench_pool, "BN",
        lambda p: _display_cats_for(p, batting_cats, pitching_cats),
        _best_pool_score)
    return races


def _build_lineup(ranked: Dict[str, list], batting_cats: List[dict]) -> tuple[dict, dict]:
    """The on-field starting nine: five fielders, three distinct outfielders, and
    a Util flex — all distinct players. Returns ``(lineup_entries, chosen)`` where
    ``chosen`` maps each slot to its raw player dict."""
    ranked_by_slot: Dict[str, list] = {}
    for pos in INFIELD_POSITIONS:
        if pos in ranked:
            ranked_by_slot[pos] = ranked[pos]
    for slot in OF_SLOTS:                      # three slots share the one OF pool
        if "OF" in ranked:
            ranked_by_slot[slot] = ranked["OF"]
    if "UTIL" in ranked:
        ranked_by_slot["UTIL"] = ranked["UTIL"]

    chosen = assign_distinct(ranked_by_slot)   # distinct within the batting group
    lineup = {slot: _base_entry(player, slot, batting_cats)
              for slot, player in chosen.items()}
    return lineup, chosen


def build_league(players: List[dict], stat_categories: dict) -> tuple[dict, dict]:
    """Return (all_stars_for_league, races_for_league).

    ``all_stars`` is grouped into the four roster sections the field view renders
    (issue #27): ``lineup`` (fielders + Util), ``bench`` (5 reserves), ``rotation``
    (top 5 SP) and ``bullpen`` (top 2 relievers). ``races`` is the ranked field per
    race position — one OF race, plus Util and Bench races limited to players not
    already crowned as a starter or on the pitching staff."""
    cats = score_players(players, stat_categories)
    batting_cats = [c for c in cats if not is_pitching_stat(c)]
    pitching_cats = [c for c in cats if is_pitching_stat(c)]

    ranked = _rank_candidates(players)

    lineup, chosen = _build_lineup(ranked, batting_cats)
    _mark_leader(lineup, players)

    rotation_players = ranked.get("SP", [])[:ROTATION_SIZE]
    rotation = [_base_entry(p, "SP", pitching_cats) for p in rotation_players]
    if rotation:
        rotation[0]["is_leader"] = True        # highlight the #1 starter

    # The bullpen mirrors the rotation: the best relievers by RP composite. A
    # two-way arm already crowned in the rotation is skipped so no one appears in
    # both pitching sections.
    rotation_keys = {player_key(p) for p in rotation_players}
    bullpen_players = [p for p in ranked.get("RP", [])
                       if player_key(p) not in rotation_keys][:BULLPEN_SIZE]
    bullpen = [_base_entry(p, "RP", pitching_cats) for p in bullpen_players]
    if bullpen:
        bullpen[0]["is_leader"] = True          # highlight the #1 reliever

    # Crowned = the fielding-race leaders (lineup minus the Util flex) plus the
    # pitching staff — excluded from both the Util and Bench races.
    fielders = {player_key(p) for slot, p in chosen.items() if slot != "UTIL"}
    crowned = fielders | rotation_keys | {player_key(p) for p in bullpen_players}

    # The bench: best available performers, hitter or pitcher, once the fielding
    # starters, the Util pick and the pitching staff are set aside.
    util_key = player_key(chosen["UTIL"]) if "UTIL" in chosen else None
    bench_excluded = crowned | ({util_key} if util_key else set())
    bench_pool = [p for p in players if player_key(p) not in bench_excluded]
    bench_pool.sort(key=lambda p: (-_best_pool_score(p), p.get("name", "")))
    bench = [_base_entry(p, "BN", _display_cats_for(p, batting_cats, pitching_cats))
             for p in bench_pool[:BENCH_SIZE]]

    all_stars = {
        "lineup": lineup,
        "bench": bench,
        "rotation": rotation,
        "bullpen": bullpen,
    }
    races = _build_races(ranked, bench_pool, crowned, batting_cats, pitching_cats)
    return all_stars, races


def _mark_leader(lineup: Dict[str, dict], players: List[dict]) -> None:
    """Flag the headline hitter — the highest batting composite among the
    starting lineup — with ``is_leader``."""
    by_name = {p.get("name", ""): p for p in players}
    best_slot, best_score = None, None
    for slot, entry in lineup.items():
        player = by_name.get(entry["player_name"])
        if player is None:
            continue
        if best_score is None or player["batting_score"] > best_score:
            best_score, best_slot = player["batting_score"], slot
    if best_slot is not None:
        lineup[best_slot]["is_leader"] = True


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
        filled = (len(all_stars["lineup"]) + len(all_stars["bench"])
                  + len(all_stars["rotation"]) + len(all_stars["bullpen"]))
        log(f"  {filled} roster spots filled from {len(players)} rostered players")

    dump_json(DATA_DIR / "all_stars.json",
              {"season": top_season, "updated_at": updated, "leagues": all_stars_out})
    dump_json(DATA_DIR / "positional_races.json",
              {"season": top_season, "updated_at": updated, "leagues": races_out})
    log("Wrote all_stars.json and positional_races.json")


if __name__ == "__main__":
    main()

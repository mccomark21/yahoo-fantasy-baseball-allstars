#!/usr/bin/env python3
"""Shared helpers for the data pipeline.

Paths, JSON IO, numeric coercion, MLB team-logo lookup, stat-category
classification, and position-eligibility logic used by ``fetch_all.py``,
``compute_allstars.py`` and ``compute_records.py``.

The raw per-season layer written by ``fetch_all.py`` and read by the compute
scripts lives at ``data/{league_id}/{season}/`` with these files:

  stat_categories.json  {league_id, game_key, season, stats:[...], scoring_stat_ids:[...]}
  rosters.json          {..., teams:[{team_key, team_id, name, players:[player_info...]}]}
  player_stats.json     {..., teams:{team_id:name},
                         season_totals:{team_id:{player_key:{stat_id:value}}},
                         weekly:{week:{team_id:{player_key:{stat_id:value}}}}}
  matchups.json         {..., matchups:[{week, winner_team_key, teams:[{team_key,name,points}]}]}

``{league_id}`` is the *entry* (current-season) league id from ``config.yaml`` —
stable across seasons even though Yahoo issues a fresh per-season league id down
the ``renew`` chain — so every season of a league nests under one directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# --------------------------------------------------------------------------- #
# JSON IO
# --------------------------------------------------------------------------- #
def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def league_dir(league_id) -> Path:
    return DATA_DIR / str(league_id)


def season_dir(league_id, season) -> Path:
    return league_dir(league_id) / str(season)


def list_seasons(league_id) -> List[int]:
    """Season subdirectories present on disk for a league, oldest → newest."""
    base = league_dir(league_id)
    if not base.exists():
        return []
    out = []
    for child in base.iterdir():
        if child.is_dir() and child.name.isdigit():
            out.append(int(child.name))
    return sorted(out)


# --------------------------------------------------------------------------- #
# Numeric coercion
# --------------------------------------------------------------------------- #
def to_number(value) -> Optional[float]:
    """Coerce a Yahoo stat value to a float, or ``None`` if it isn't numeric.

    Yahoo hands stats back as strings and uses sentinels for "no value":
    ``"-"``, ``""``, ``"INF"`` (ERA/WHIP on 0 IP), and ratio displays like
    ``"60/200"`` (H/AB). All of those become ``None`` so callers can skip them.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in {"-", "--", "INF", "NA", "N/A"}:
        return None
    if "/" in s:  # ratio display (e.g. H/AB) — not a scalar
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean_number(value: float, abbr: str):
    """Render a numeric stat the way the frontend expects: rate stats keep
    decimals, counting stats collapse to ``int`` when whole."""
    if abbr.upper() in RATE_STATS:
        # AVG/OBP/SLG/OPS to 3 places; ERA/WHIP and other rates to 2.
        places = 3 if abbr.upper() in {"AVG", "OBP", "SLG", "OPS"} else 2
        return round(value, places)
    if value == int(value):
        return int(value)
    return round(value, 2)


# --------------------------------------------------------------------------- #
# Stat-category classification
# --------------------------------------------------------------------------- #
# Rate stats: not counting totals. Excluded from single-week records (a 1-AB
# 1.000 week is noise) and rendered with decimals.
RATE_STATS = {"AVG", "OBP", "SLG", "OPS", "ERA", "WHIP", "K/9", "K/BB", "BB/9"}

# Fallback batting/pitching split when a stat carries no position_type, keyed by
# abbreviation. (position_type from league settings is the primary signal.)
_BATTING_ABBR = {"R", "HR", "RBI", "SB", "AVG", "OBP", "SLG", "OPS", "H", "AB",
                 "2B", "3B", "BB", "CS", "TB", "HBP", "SO"}
_PITCHING_ABBR = {"W", "L", "SV", "K", "ERA", "WHIP", "IP", "QS", "HLD", "BS",
                  "SVH", "K/9", "K/BB", "BB/9", "ER", "CG", "SHO"}


def stat_abbr(stat: dict) -> str:
    """Best human label for a stat category: abbr, else display_name/name."""
    return (stat.get("abbr") or stat.get("display_name") or stat.get("name")
            or stat.get("stat_id") or "").strip()


def is_pitching_stat(stat: dict) -> bool:
    ptype = (stat.get("position_type") or "").upper()
    if ptype == "P":
        return True
    if ptype == "B":
        return False
    return stat_abbr(stat).upper() in _PITCHING_ABBR


def higher_is_better(stat: dict) -> bool:
    """Yahoo ``sort_order``: ``"0"`` = ascending (lower better, e.g. ERA/WHIP);
    anything else descending (higher better)."""
    return str(stat.get("sort_order", "1")).strip() != "0"


def scoring_stats(stat_categories: dict) -> List[dict]:
    """The league's enabled, non-display-only stat categories."""
    ids = set(stat_categories.get("scoring_stat_ids") or [])
    out = []
    for stat in stat_categories.get("stats", []):
        if str(stat.get("stat_id")) in ids:
            out.append(stat)
    # Fallback for older raw files without scoring_stat_ids.
    if not out:
        for stat in stat_categories.get("stats", []):
            if stat.get("enabled") and not stat.get("is_only_display_stat"):
                out.append(stat)
    return out


def stat_id_to_abbr(stat_categories: dict) -> Dict[str, str]:
    return {str(s.get("stat_id")): stat_abbr(s) for s in stat_categories.get("stats", [])}


# --------------------------------------------------------------------------- #
# Positions
# --------------------------------------------------------------------------- #
BATTING_POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
PITCHING_POSITIONS = ["SP", "RP"]
# Display order on the diamond / in the races view.
TARGET_POSITIONS = BATTING_POSITIONS + PITCHING_POSITIONS + ["UTIL", "DH"]

# A Yahoo eligibility token → the diamond positions it qualifies a player for.
_ELIGIBILITY: Dict[str, set] = {
    "C": {"C"}, "1B": {"1B"}, "2B": {"2B"}, "3B": {"3B"}, "SS": {"SS"},
    "LF": {"LF"}, "CF": {"CF"}, "RF": {"RF"},
    "OF": {"LF", "CF", "RF"},          # generic outfield → all three
    "UTIL": {"UTIL"}, "DH": {"DH"},
    "SP": {"SP"}, "RP": {"RP"},
    "P": {"SP", "RP"},                 # generic pitcher → both
}

_BATTING_TOKENS = set(BATTING_POSITIONS) | {"OF", "UTIL", "DH"}
_PITCHING_TOKENS = {"SP", "RP", "P"}


def _tokens(player: dict) -> List[str]:
    return [str(p).upper() for p in (player.get("eligible_positions") or [])]


def is_pitcher(player: dict) -> bool:
    return bool(set(_tokens(player)) & _PITCHING_TOKENS)


def is_batter(player: dict) -> bool:
    return bool(set(_tokens(player)) & _BATTING_TOKENS)


def eligible_positions(player: dict) -> set:
    """Diamond positions a player can fill.

    Every batter is UTIL-eligible. DH is only granted to players Yahoo actually
    flags ``DH`` — leagues without a DH slot simply leave that position empty,
    which the frontend already tolerates.
    """
    targets: set = set()
    for tok in _tokens(player):
        targets |= _ELIGIBILITY.get(tok, set())
    if is_batter(player):
        targets.add("UTIL")
    return targets


# --------------------------------------------------------------------------- #
# MLB team logos
# --------------------------------------------------------------------------- #
# Yahoo abbreviation (incl. common aliases) → MLB Stats team id, used to build
# the mlbstatic SVG logo URL the frontend renders.
_MLB_TEAM_IDS: Dict[str, int] = {
    "LAA": 108, "ANA": 108,
    "ARI": 109, "AZ": 109,
    "BAL": 110, "BOS": 111,
    "CHC": 112, "CHN": 112,
    "CIN": 113, "CLE": 114, "COL": 115, "DET": 116, "HOU": 117,
    "KC": 118, "KCR": 118,
    "LAD": 119, "LA": 119,
    "WSH": 120, "WAS": 120, "WSN": 120,
    "NYM": 121, "NYN": 121,
    "OAK": 133, "ATH": 133,
    "PIT": 134,
    "SD": 135, "SDP": 135,
    "SEA": 136,
    "SF": 137, "SFG": 137,
    "STL": 138,
    "TB": 139, "TBR": 139, "TBD": 139,
    "TEX": 140, "TOR": 141, "MIN": 142, "PHI": 143, "ATL": 144,
    "CWS": 145, "CHW": 145, "CHA": 145,
    "MIA": 146, "FLA": 146,
    "NYY": 147, "NYA": 147,
    "MIL": 158,
}


def mlb_team_id(abbr: str) -> Optional[int]:
    return _MLB_TEAM_IDS.get((abbr or "").upper())


def mlb_team_logo_url(abbr: str) -> str:
    tid = mlb_team_id(abbr)
    return f"https://www.mlbstatic.com/team-logos/{tid}.svg" if tid else ""

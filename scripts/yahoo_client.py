#!/usr/bin/env python3
"""Yahoo Fantasy Baseball data-access layer.

Wraps ``yfpy`` and adds the extensions this project needs over the
reference repo (https://github.com/mccomark21/yahoo-fantasy-data-hub):

  - Historical season discovery — walk the league ``renew`` chain backward
    to find every season the league existed, across MLB ``game_key``s.
  - Per-league/per-season stat categories.
  - Player season totals (``stats;type=season``) and weekly stats
    (``stats;type=week``).
  - Matchup scores across all weeks of a season.
  - Roster fetch via ``get_team_roster_player_info_by_week``.

All fetch methods return plain JSON-serializable dicts/lists so the
orchestration layer (``fetch_all.py``) can dump them straight to disk.

Auth is read from the environment (``YAHOO_CONSUMER_KEY``,
``YAHOO_CONSUMER_SECRET``, ``YAHOO_REFRESH_TOKEN``), provided via a local
``.env`` file or as GitHub Secrets in CI.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

from dotenv import load_dotenv
from requests.exceptions import HTTPError
from yfpy.exceptions import YahooFantasySportsDataNotFound
from yfpy.query import YahooFantasySportsQuery

# Load .env from the project root (no-op if the vars are already set, e.g. in CI).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REQUIRED_ENV_VARS = (
    "YAHOO_CONSUMER_KEY",
    "YAHOO_CONSUMER_SECRET",
    "YAHOO_REFRESH_TOKEN",
)

GAME_CODE = "mlb"

# Yahoo Fantasy REST base (yfpy funnels every call through get_response(url)).
_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2/"
# Yahoo rejects a multi-key players request if ANY key is invalid, naming the
# offending key in the error so we can drop it and retry.
_BAD_KEY_RE = re.compile(r"Player key (\S+?) does not exist")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def decode_str(value) -> str:
    """Decode the byte-ish strings yfpy occasionally returns into clean unicode."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    s = str(value)
    if (s.startswith("b'") and s.endswith("'")) or (s.startswith('b"') and s.endswith('"')):
        try:
            return eval(s).decode("utf-8", errors="replace")  # noqa: S307
        except Exception:
            return s[2:-1]
    return s


def _stats_to_dict(player) -> Dict[str, Union[int, float, str]]:
    """Flatten a Player's stat list into ``{stat_id: value}``."""
    player_stats = getattr(player, "player_stats", None)
    stats = getattr(player_stats, "stats", None) or getattr(player, "stats", None) or []
    out: Dict[str, Union[int, float, str]] = {}
    for stat in stats:
        stat_id = getattr(stat, "stat_id", None)
        if stat_id is None:
            continue
        out[str(stat_id)] = getattr(stat, "value", None)
    return out


def _find_player_key(node) -> Optional[str]:
    """Find the ``player_key`` anywhere under a raw-JSON player wrapper."""
    if isinstance(node, dict):
        if "player_key" in node:
            return node["player_key"]
        for v in node.values():
            found = _find_player_key(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_player_key(v)
            if found:
                return found
    return None


def _collect_stats(node) -> Dict[str, Union[int, float, str]]:
    """Collect ``{stat_id: value}`` from anywhere under a raw-JSON node."""
    out: Dict[str, Union[int, float, str]] = {}

    def walk(n):
        if isinstance(n, dict):
            stat = n.get("stat")
            if isinstance(stat, dict) and "stat_id" in stat:
                out[str(stat["stat_id"])] = stat.get("value")
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _parse_players_stats_json(payload: dict) -> Dict[str, Dict[str, Union[int, float, str]]]:
    """Parse a raw ``players;.../stats`` JSON response into ``{player_key: {stat_id: value}}``.

    In multi-key responses Yahoo nests ``player_key`` and ``player_stats`` as
    *siblings* under each ``player`` wrapper (not in the same dict), so we
    associate at the wrapper level.
    """
    out: Dict[str, Dict[str, Union[int, float, str]]] = {}

    def walk(node):
        if isinstance(node, dict):
            if "player" in node:
                wrapper = node["player"]
                key = _find_player_key(wrapper)
                if key:
                    out[key] = _collect_stats(wrapper)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return out


def _extract_positions(eligible_positions) -> List[str]:
    """Normalize ``eligible_positions`` (list/dict/obj) to a list of position strings."""
    if not eligible_positions:
        return []
    if not isinstance(eligible_positions, list):
        eligible_positions = [eligible_positions]
    out: List[str] = []
    for pos in eligible_positions:
        if isinstance(pos, str):
            out.append(pos)
        elif isinstance(pos, dict):
            p = pos.get("position")
            if p:
                out.append(p)
        else:
            p = getattr(pos, "position", None)
            if p:
                out.append(str(p))
    return out


def _player_name(player) -> str:
    name_obj = getattr(player, "name", None)
    if name_obj is not None:
        full = getattr(name_obj, "full", None)
        if full:
            return decode_str(full)
    return decode_str(getattr(player, "full_name", "") or "")


def extract_player(player) -> dict:
    """Flatten a yfpy Player into the fields the frontend cares about."""
    selected = getattr(player, "selected_position", None)
    selected_pos = getattr(selected, "position", None) if selected is not None else None

    return {
        "player_key": decode_str(getattr(player, "player_key", "")),
        "player_id": str(getattr(player, "player_id", "") or ""),
        "name": _player_name(player),
        "mlb_team": decode_str(getattr(player, "editorial_team_abbr", "") or ""),
        "mlb_team_full": decode_str(getattr(player, "editorial_team_full_name", "") or ""),
        "headshot_url": decode_str(getattr(player, "headshot_url", "") or ""),
        "image_url": decode_str(getattr(player, "image_url", "") or ""),
        "eligible_positions": _extract_positions(getattr(player, "eligible_positions", None)),
        "primary_position": decode_str(getattr(player, "primary_position", "") or ""),
        "selected_position": decode_str(selected_pos or ""),
        "status": decode_str(getattr(player, "status", "") or ""),
    }


def _parse_renew(renew: Optional[str]):
    """Parse a League ``renew``/``renewed`` token ("<game_key>_<league_id>").

    Returns ``(game_key, league_id)`` or ``None`` when there is no link.
    """
    if not renew:
        return None
    # Yahoo formats this as "<game_key>_<league_id>", e.g. "422_12239".
    parts = [p for p in str(renew).strip().split("_") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class YahooClient:
    """Authenticated gateway to one Yahoo account's MLB fantasy leagues.

    A single ``YahooClient`` can read any league/season the account has
    access to. Internally it caches one ``YahooFantasySportsQuery`` per
    ``(league_id, game_key)`` pair, since each query object is bound to a
    single league.

    Rate limiting: Yahoo returns HTTP 999 ("rate limiting") once an IP
    exceeds its request budget — and yfpy raises that *before* its own
    retry/backoff kicks in, so its ``retries`` knob is useless against it.
    Cloud CI runners (shared IPs) trip this far sooner than a home IP. We
    defend on two fronts: a minimum spacing between requests to stay under
    the limit, and a long exponential back-off that retries when a 999 does
    slip through. Both are tunable via env vars so CI can be gentler.
    """

    # Seconds to wait between consecutive Yahoo requests (throttle).
    MIN_REQUEST_INTERVAL = float(os.environ.get("YAHOO_MIN_REQUEST_INTERVAL", "0.6"))
    # Back-off waits (seconds) applied on successive 999 rate-limit hits.
    RATE_LIMIT_BACKOFF = (15.0, 30.0, 60.0, 120.0, 240.0)

    def __init__(self, game_code: str = GAME_CODE):
        missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
        if missing:
            raise RuntimeError(
                "Missing Yahoo credentials: "
                + ", ".join(missing)
                + ". Set them in a .env file (local) or as GitHub Secrets (CI)."
            )
        self.game_code = game_code
        self._token_json = {
            "access_token": "auto_refresh",
            "consumer_key": os.environ["YAHOO_CONSUMER_KEY"],
            "consumer_secret": os.environ["YAHOO_CONSUMER_SECRET"],
            "guid": "",
            "refresh_token": os.environ["YAHOO_REFRESH_TOKEN"],
            "token_time": 0.0,
            "token_type": "bearer",
        }
        self._queries: Dict[tuple, YahooFantasySportsQuery] = {}
        self._game_weeks_cache: Dict[str, Dict[int, tuple]] = {}
        self._last_request_ts = 0.0

    # -- query factory ----------------------------------------------------- #
    def query(self, league_id, game_key=None) -> YahooFantasySportsQuery:
        """Return a query bound to ``league_id`` (and ``game_key`` if given).

        When ``game_key`` is omitted the query targets the current MLB season.
        """
        key = (str(league_id), str(game_key) if game_key is not None else None)
        if key not in self._queries:
            q = YahooFantasySportsQuery(
                league_id=str(league_id),
                game_code=self.game_code,
                game_id=int(game_key) if game_key is not None else None,
                yahoo_access_token_json=self._token_json,
                browser_callback=False,
            )
            self._install_rate_limit_guard(q)
            self._queries[key] = q
        return self._queries[key]

    # -- rate-limit guard -------------------------------------------------- #
    def _install_rate_limit_guard(self, q: YahooFantasySportsQuery) -> None:
        """Wrap ``q.get_response`` with throttling + 999 back-off.

        Every Yahoo HTTP call funnels through ``get_response``, so wrapping it
        once covers all fetch methods. The throttle clock is shared across all
        query objects on this client (one ``_last_request_ts``), so spacing
        holds even as we hop between leagues/seasons.
        """
        original = q.get_response

        def guarded(url):
            for wait in (*self.RATE_LIMIT_BACKOFF, None):
                # Throttle: keep a minimum gap since the previous request.
                gap = time.monotonic() - self._last_request_ts
                if gap < self.MIN_REQUEST_INTERVAL:
                    time.sleep(self.MIN_REQUEST_INTERVAL - gap)
                try:
                    return original(url)
                except HTTPError as exc:
                    if "rate limiting" in str(exc).lower() and wait is not None:
                        print(f"  Rate limited by Yahoo; backing off {wait:.0f}s...", flush=True)
                        time.sleep(wait)
                        continue
                    raise
                finally:
                    self._last_request_ts = time.monotonic()

        q.get_response = guarded

    # -- season discovery -------------------------------------------------- #
    def discover_league_seasons(self, league_id) -> List[dict]:
        """Find every season ``league_id``'s league existed.

        Starts from the current-season league and walks the ``renew`` chain
        backward through prior MLB ``game_key``s. Returns one descriptor per
        season, sorted oldest → newest.

        Walking stops gracefully at the oldest *accessible* season: Yahoo
        blocks metadata reads on leagues the authenticated account never
        joined, so a chain that predates membership simply ends there rather
        than raising.
        """
        seasons: List[dict] = []
        seen: set = set()

        game_key: Optional[str] = None  # current season for the entry league
        current_league_id = str(league_id)

        while current_league_id is not None and current_league_id not in seen:
            seen.add(current_league_id)
            q = self.query(current_league_id, game_key)
            try:
                meta = q.get_league_metadata()
            except YahooFantasySportsDataNotFound as exc:
                league_key = f"{game_key}.l.{current_league_id}" if game_key else current_league_id
                if not seasons:
                    # The entry league itself is unreadable — that's a real
                    # problem (bad id, or the account isn't in its own league).
                    raise
                print(f"  Note: stopping discovery at {league_key} (no access to earlier seasons): {exc}")
                break

            descriptor = self._season_descriptor(meta, current_league_id)
            seasons.append(descriptor)

            prev = _parse_renew(getattr(meta, "renew", None))
            if prev is None:
                break
            game_key, current_league_id = prev

        seasons.sort(key=lambda s: s["season"])
        return seasons

    @staticmethod
    def _season_descriptor(meta, fallback_league_id: str) -> dict:
        league_key = decode_str(getattr(meta, "league_key", "") or "")
        game_key = league_key.split(".", 1)[0] if "." in league_key else ""
        return {
            "season": int(getattr(meta, "season", 0) or 0),
            "game_key": game_key,
            "league_id": str(getattr(meta, "league_id", fallback_league_id) or fallback_league_id),
            "league_key": league_key,
            "name": decode_str(getattr(meta, "name", "") or ""),
            "num_teams": int(getattr(meta, "num_teams", 0) or 0),
            "start_week": int(getattr(meta, "start_week", 0) or 0),
            "end_week": int(getattr(meta, "end_week", 0) or 0),
            "current_week": int(getattr(meta, "current_week", 0) or 0),
        }

    def fetch_league_metadata(self, league_id, game_key=None) -> dict:
        """Return the season descriptor for a single league/season."""
        meta = self.query(league_id, game_key).get_league_metadata()
        return self._season_descriptor(meta, str(league_id))

    # -- stat categories --------------------------------------------------- #
    def fetch_stat_categories(self, league_id, game_key, season=None) -> dict:
        """Fetch the stat categories this league tracked this season.

        yfpy 17 exposes these via ``get_league_settings().stat_categories``
        (there is no standalone ``get_league_stat_categories``).
        """
        settings = self.query(league_id, game_key).get_league_settings()
        stat_categories = getattr(settings, "stat_categories", None)
        stats = getattr(stat_categories, "stats", None) or []
        # Scoring format is a league-constant on the settings object, so it costs
        # no extra API call. "head" = head-to-head categories, "headone" = a
        # single win per week. Drives how season W-L-T records are computed.
        scoring_type = decode_str(getattr(settings, "scoring_type", "") or "")

        out_stats: List[dict] = []
        scoring_stat_ids: List[str] = []
        for stat in stats:
            stat_id = str(getattr(stat, "stat_id", "") or "")
            enabled = bool(getattr(stat, "enabled", 0))
            display_only = bool(getattr(stat, "is_only_display_stat", 0))
            out_stats.append({
                "stat_id": stat_id,
                "name": decode_str(getattr(stat, "name", "") or ""),
                "display_name": decode_str(getattr(stat, "display_name", "") or ""),
                "abbr": decode_str(getattr(stat, "abbr", "") or ""),
                "group": decode_str(getattr(stat, "group", "") or ""),
                "position_type": decode_str(getattr(stat, "position_type", "") or ""),
                "sort_order": str(getattr(stat, "sort_order", "") or ""),
                "enabled": enabled,
                "is_only_display_stat": display_only,
            })
            if enabled and not display_only and stat_id:
                scoring_stat_ids.append(stat_id)

        return {
            "league_id": str(league_id),
            "game_key": str(game_key),
            "season": int(season) if season is not None else None,
            "scoring_type": scoring_type,
            "stats": out_stats,
            "scoring_stat_ids": scoring_stat_ids,
        }

    # -- player stats ------------------------------------------------------ #
    #
    # MLB note: Yahoo does NOT support week coverage on the per-player stats
    # endpoint (``players;player_keys=.../stats;type=week`` returns no stats for
    # baseball — only season and date coverage work there). Weekly stats must
    # come from the *team roster* endpoint, which Yahoo does serve per week for
    # MLB. ``fetch_roster_stats`` is the efficient primitive (one API call per
    # team); the ``player_keys``-keyed helpers below build on it.
    def fetch_roster_stats(self, team_id, league_id, game_key, week=None) -> Dict[str, dict]:
        """Stats for every player on one team's roster.

        ``week=None`` returns season totals; an int/``"current"`` returns that
        week's totals. Returns ``{player_key: {stat_id: value, ...}}`` limited
        to the league's tracked stat categories.
        """
        q = self.query(league_id, game_key)
        if week is None:
            players = q.get_team_roster_player_stats(str(team_id))
        else:
            players = q.get_team_roster_player_stats_by_week(str(team_id), chosen_week=week)

        out: Dict[str, dict] = {}
        for entry in players:
            player = getattr(entry, "player", entry)
            player_key = decode_str(getattr(player, "player_key", "") or "")
            if player_key:
                out[player_key] = _stats_to_dict(player)
        return out

    def fetch_team_season_stats(self, team_key, league_id, game_key) -> Dict[str, Union[int, float, str]]:
        """A team's season *category totals* — the standings "Stats" view.

        Yahoo's authoritative team-level aggregate: only active-lineup production
        while the player was rostered counts. This is the correct source for a
        team's season HR/R/K record — NOT summing rostered players' full individual
        season totals, which over-counts late adds and the bench and misses dropped
        players. Returns ``{stat_id: value}`` (values are Yahoo's raw strings).

        yfpy's typed ``get_team_stats`` returns only fantasy *points* (a
        ``TeamPoints``), and no typed method surfaces ``team_stats.stats`` — so we
        hit the raw ``team/{team_key}/stats;type=season`` resource. Unlike per-
        player stats, team totals SURVIVE game archival: past seasons return real
        values (verified live against 2021/2022), so this works for every season.
        """
        url = (f"https://fantasysports.yahooapis.com/fantasy/v2/"
               f"team/{team_key}/stats;type=season")
        data = self.query(league_id, game_key).get_response(url).json()
        team = data.get("fantasy_content", {}).get("team", [])
        node = None
        for part in team if isinstance(team, list) else []:
            if isinstance(part, dict) and "team_stats" in part:
                node = part["team_stats"]
                break
        out: Dict[str, Union[int, float, str]] = {}
        for wrapped in (node or {}).get("stats", []):
            stat = wrapped.get("stat", wrapped) if isinstance(wrapped, dict) else {}
            sid = stat.get("stat_id")
            if sid is not None:
                out[str(sid)] = stat.get("value")
        return out

    def fetch_roster_stats_by_date(self, team_id, league_id, game_key, day) -> Dict[str, dict]:
        """Stats for one team's roster on a single calendar date.

        ``day`` is an ISO date string (``YYYY-MM-DD``). Yahoo serves per-player
        MLB stats with ``date`` coverage (a real single-day box score) through
        ``get_team_roster_player_info_by_date`` — the primitive a faithful
        weekly total is summed from, since true week coverage doesn't exist.
        Returns ``{player_key: {stat_id: value, ...}}``.
        """
        q = self.query(league_id, game_key)
        players = q.get_team_roster_player_info_by_date(str(team_id), chosen_date=day)
        out: Dict[str, dict] = {}
        for entry in players:
            player = getattr(entry, "player", entry)
            player_key = decode_str(getattr(player, "player_key", "") or "")
            if player_key:
                out[player_key] = _stats_to_dict(player)
        return out

    def fetch_game_weeks(self, league_id, game_key) -> Dict[int, tuple]:
        """Map each fantasy week to its ``(start, end)`` ISO dates for a season.

        Yahoo's authoritative week→date ranges (week 1 is often a short opening
        week). Cached per game_key since both leagues' current season share one
        game. Returns ``{week: (start, end)}``.
        """
        gk = str(game_key)
        if gk not in self._game_weeks_cache:
            weeks = self.query(league_id, game_key).get_game_weeks_by_game_id(int(game_key))
            self._game_weeks_cache[gk] = {
                int(getattr(w, "week", 0) or 0): (
                    decode_str(getattr(w, "start", "") or ""),
                    decode_str(getattr(w, "end", "") or ""),
                )
                for w in weeks
            }
        return self._game_weeks_cache[gk]

    def fetch_league_player_stats(self, league_id, game_key, week=None) -> Dict[str, dict]:
        """Stats for every rostered player in the league (one call per team).

        ``week=None`` for season totals, otherwise that week's totals. Returns
        ``{player_key: {stat_id: value, ...}}``.
        """
        out: Dict[str, dict] = {}
        for team in self.fetch_teams(league_id, game_key):
            try:
                out.update(self.fetch_roster_stats(team["team_id"], league_id, game_key, week))
            except Exception as exc:  # noqa: BLE001 — one bad team shouldn't kill the run
                scope = "season" if week is None else f"week {week}"
                print(f"  Warning: {scope} stats failed for team {team['name']}: {exc}")
        return out

    def fetch_season_stats(self, player_keys: Iterable[str], league_id, game_key) -> Dict[str, dict]:
        """Season totals (``stats;type=season``) for the given player keys.

        Returns ``{player_key: {stat_id: value, ...}}``. Pulls the league's
        rostered-player season stats (one call per team) and filters to the
        requested keys; pass a falsy ``player_keys`` to get every rostered
        player.
        """
        wanted = {str(k) for k in player_keys} if player_keys else None
        all_stats = self.fetch_league_player_stats(league_id, game_key, week=None)
        if wanted is None:
            return all_stats
        return {pk: s for pk, s in all_stats.items() if pk in wanted}

    def fetch_weekly_stats(self, player_keys: Iterable[str], league_id, game_key, week) -> Dict[str, dict]:
        """Weekly stats for the given player keys for one week.

        Returns ``{player_key: {stat_id: value, ...}}``. Pulls each team's
        roster stats for the week (the only endpoint Yahoo serves weekly for
        MLB) and filters to the requested keys; pass a falsy ``player_keys`` to
        get every rostered player.
        """
        wanted = {str(k) for k in player_keys} if player_keys else None
        all_stats = self.fetch_league_player_stats(league_id, game_key, week=week)
        if wanted is None:
            return all_stats
        return {pk: s for pk, s in all_stats.items() if pk in wanted}

    # -- historical season stats (current-game recipe) --------------------- #
    #
    # Yahoo serves per-player stat *values* only through the CURRENT game; the
    # archived game_key of a past season returns "-" (→ 0.0) for everything.
    # But the current game will report ANY past season a player actually played
    # via ``players;player_keys={cur_gk}.p.{id}/stats;type=season;season=YYYY``.
    # Numeric player_ids are stable across game_keys, so a historical roster key
    # (``{old_gk}.p.{id}``) maps to the current game by swapping the prefix.
    # The catch: a player must still exist in the current game — retired players
    # 400 with "Player key ... does not exist", and one bad key aborts the whole
    # multi-key request, so we drop the named key and retry.
    def fetch_current_game_season_stats(
        self,
        player_ids: Iterable[str],
        season: int,
        cur_league_id: str,
        cur_game_key: str,
        batch_size: int = 25,
    ) -> Tuple[Dict[str, dict], Set[str]]:
        """Season totals for a *past* ``season`` via the current game.

        ``player_ids`` are the stable numeric ids (no game prefix). Returns
        ``({player_id: {stat_id: value}}, unreachable_player_ids)`` where
        unreachable ids are players no longer present in the current game
        (retired) whose historical stats are irrecoverable.
        """
        q = self.query(cur_league_id, cur_game_key)
        ids = [str(pid) for pid in player_ids]
        stats: Dict[str, dict] = {}
        unreachable: Set[str] = set()
        for start in range(0, len(ids), batch_size):
            chunk = ids[start:start + batch_size]
            self._fetch_season_stats_chunk(q, chunk, season, cur_game_key, stats, unreachable)
        return stats, unreachable

    def _fetch_season_stats_chunk(self, q, ids, season, cur_game_key, stats, unreachable) -> None:
        """Fetch one batch, dropping any key Yahoo reports as nonexistent."""
        remaining = list(ids)
        # Worst case every key is bad; +1 for the final clean request.
        for _ in range(len(ids) + 1):
            if not remaining:
                return
            keys = ",".join(f"{cur_game_key}.p.{pid}" for pid in remaining)
            url = f"{_API_BASE}players;player_keys={keys}/stats;type=season;season={season}"
            try:
                payload = q.get_response(url).json()
            except Exception as exc:  # noqa: BLE001
                match = _BAD_KEY_RE.search(str(exc))
                if not match:
                    print(f"  Warning: season {season} stats batch failed: {str(exc)[:120]}")
                    return
                bad_id = match.group(1).split(".p.")[-1]
                unreachable.add(bad_id)
                remaining = [pid for pid in remaining if pid != bad_id]
                continue
            for key, line in _parse_players_stats_json(payload).items():
                pid = key.split(".p.")[-1]
                stats[pid] = line
            return

    # -- matchups ---------------------------------------------------------- #
    def fetch_matchups(self, league_id, game_key, weeks: Optional[Iterable[int]] = None) -> List[dict]:
        """Matchup scores for every (or selected) week of a season.

        When ``weeks`` is omitted, fetches ``start_week``..``end_week`` from
        league metadata. For H2H category leagues a team's ``points`` is its
        category-win total for that week.
        """
        q = self.query(league_id, game_key)
        if weeks is None:
            meta = q.get_league_metadata()
            start = int(getattr(meta, "start_week", 1) or 1)
            end = int(getattr(meta, "end_week", 0) or 0)
            weeks = range(start, end + 1) if end >= start else [int(getattr(meta, "current_week", 1) or 1)]

        out: List[dict] = []
        for week in weeks:
            try:
                matchups = q.get_league_matchups_by_week(int(week))
            except Exception as exc:  # noqa: BLE001
                print(f"  Warning: matchups failed for week {week}: {exc}")
                continue
            for matchup in matchups:
                out.append(self._matchup_to_dict(matchup, int(week)))
        return out

    @staticmethod
    def _matchup_to_dict(matchup, week: int) -> dict:
        teams = []
        for team in getattr(matchup, "teams", None) or []:
            teams.append({
                "team_key": decode_str(getattr(team, "team_key", "") or ""),
                "team_id": str(getattr(team, "team_id", "") or ""),
                "name": decode_str(getattr(team, "name", "") or ""),
                "points": getattr(team, "points", None),
            })
        return {
            "week": int(getattr(matchup, "week", week) or week),
            "is_playoffs": bool(getattr(matchup, "is_playoffs", 0)),
            "is_consolation": bool(getattr(matchup, "is_consolation", 0)),
            "is_tied": bool(getattr(matchup, "is_tied", 0)),
            "winner_team_key": decode_str(getattr(matchup, "winner_team_key", "") or ""),
            "teams": teams,
        }

    # -- rosters ----------------------------------------------------------- #
    def fetch_teams(self, league_id, game_key) -> List[dict]:
        """List the fantasy teams in a league."""
        teams = self.query(league_id, game_key).get_league_teams()
        out = []
        for team in teams:
            out.append({
                "team_key": decode_str(getattr(team, "team_key", "") or ""),
                "team_id": str(getattr(team, "team_id", "") or ""),
                "name": decode_str(getattr(team, "name", "") or ""),
            })
        return out

    def fetch_roster(self, team_id, league_id, game_key, week: Union[int, str] = "current") -> List[dict]:
        """Roster for one fantasy team, via ``get_team_roster_player_info_by_week``."""
        roster = self.query(league_id, game_key).get_team_roster_player_info_by_week(
            str(team_id), week
        )
        out = []
        for entry in roster:
            player = getattr(entry, "player", entry)
            out.append(extract_player(player))
        return out

    def fetch_league_rosters(self, league_id, game_key, week: Union[int, str] = "current") -> List[dict]:
        """All rosters in a league: ``[{team..., players: [...]}]``."""
        out = []
        for team in self.fetch_teams(league_id, game_key):
            try:
                players = self.fetch_roster(team["team_id"], league_id, game_key, week)
            except Exception as exc:  # noqa: BLE001
                print(f"  Warning: roster failed for team {team['name']}: {exc}")
                players = []
            out.append({**team, "players": players})
        return out


# --------------------------------------------------------------------------- #
# Smoke test — `python scripts/yahoo_client.py` discovers seasons for the
# leagues in config.yaml (requires valid Yahoo credentials in the environment).
# --------------------------------------------------------------------------- #
def _main() -> None:
    import yaml

    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

    league_ids = [str(lid) for lid in config.get("league_ids", [])]
    if not league_ids:
        print("No league_ids in config.yaml")
        return

    client = YahooClient()
    for league_id in league_ids:
        print(f"\n=== League {league_id} ===")
        seasons = client.discover_league_seasons(league_id)
        for s in seasons:
            print(
                f"  {s['season']}  game_key={s['game_key']:>4}  "
                f"league_id={s['league_id']:>7}  weeks {s['start_week']}-{s['end_week']}  "
                f"{s['num_teams']} teams  {s['name']}"
            )


if __name__ == "__main__":
    _main()

# Handoff: historical stats — recipe DONE + live-verified, weighted gate added, backfill NOT yet run

_Rewritten 2026-06-24 (supersedes the "code done, backfill not run" version)._

## TL;DR

The historical-stats recipe works and is **live-verified** (not just modeled).
Since the last handoff we also made the season keep/skip gate **fairer** (weight
players by how much of the season they were rostered) and **decided to only
collect data back to 2021** (older seasons are mostly retired/unreachable and
slow to scan). Code + tests are complete and green (**42 passing**), but nothing
is committed and the real backfill has **not** been run yet.

## The recipe (unchanged, still true — verified live this session)

1. **Archived game-keys never serve player stat values** — a past season's own
   game returns `'-'` (→ `0.0`) for everything. Dead path.
2. **Only the CURRENT game serves per-player stats**, for players still in it:
   ```
   players;player_keys={CUR_GK}.p.{id}/stats;type=season;season={YYYY}
   ```
   Numeric `player_id`s are stable across game-keys, so a historical roster key
   maps to the current game by swapping the prefix. Retired players 400
   ("Player key ... does not exist") and **one bad key aborts the whole multi-key
   request** → drop the named key and retry.

Live dry run this session (league 12239, no writes to `data/`):
- 2025: parsed 217 real stat lines; drop-bad-key retry dropped only the retired
  Kershaw; coverage block written; `weekly={}` as designed.
- Confirms the **modeled JSON shape matches live Yahoo** — the one thing the
  offline tests couldn't prove. Recipe is trustworthy.

## NEW this session: roster-week weighted coverage gate

**Problem the owner raised:** the old gate counted every rostered player equally,
so a retiree who was a September bench add sank a season as hard as a season-long
core player.

**Fix (built test-first):** weight each end-of-season-rostered player by the
fraction of the season they were actually rostered, sampled from ~5 evenly-spaced
weeks (full per-week scan was too many API calls). Per-week *roster membership*
IS available for retired players (different endpoint than stats) — verified live.

- `planned_sample_weeks(descriptor, count=5)` — evenly-spaced weeks to probe.
- `_roster_week_weights(client, roster_teams, descriptor, league_id, game_key,
  count=5)` → `{player_id: share_in_[0,1]}`. Falls back to weight 1.0 for all if
  sampling fails/empty (degrades to head count).
- `_historical_season_totals(...)` gained an optional `weights` param.
  `coverage["rate"]` is now the **weighted** ratio; `total`/`reachable` stay raw
  head counts (for the "N players unavailable" label); `unreachable` unchanged.
  `weights=None` → old head-count behavior (keeps prior tests valid).
- `fetch_season` computes weights for historical seasons and passes them in.

**Empirical result (live, league 12239):** weighting barely moves the numbers —
the retirees in these leagues were mostly rostered all season, not brief adds:

| season | head-count | weighted | gate (75%) |
|--------|-----------|----------|-----------|
| 2023   | 95.2%     | 95.6%    | KEEP |
| 2022   | 91.3%     | 90.5%    | KEEP |
| 2021   | 76.0%     | 77.9%    | KEEP |
| 2019   | 62.8%     | 65.7%    | SKIP |

(2020 errors on roster fetch — game 398 "does not support accessing a roster by
week" — so it ends up empty → SKIP. 14078 was NOT measured: the full-history
scan was too slow and got killed, which is why we pivoted to `--since 2021`.)

## Decisions locked this session (from the owner)

- **Threshold lowered `MIN_COVERAGE` 0.80 → 0.75** so 2021 (77.9%) is kept.
- **Only collect data back to 2021.** Implemented as `fetch_all.py --since 2021`
  (ignores discovered seasons older than the floor; still uses the newest season
  to locate the current game).
- Weighted gate is the model going forward, even though it changed no decisions
  in 12239 — it's simply more defensible.

## Code state — ALL UNSTAGED (nothing committed)

`scripts/`:
- `yahoo_client.py` — the recipe (`fetch_current_game_season_stats`, sibling-JSON
  parser, drop-bad-key retry). From prior session, unchanged this session.
- `fetch_all.py` — this session added `planned_sample_weeks`,
  `_roster_week_weights`, the `weights` param on `_historical_season_totals`,
  `MIN_COVERAGE = 0.75`, and `run_backfill(..., since=)` + `--since` CLI arg.

Tests (`tests/`), **42 passing**, fully offline (`python -m pytest tests/`):
- `test_historical_stats.py` + `conftest.py` (prior session) — recipe parsing,
  retry, key-mapping, coverage block, the gate, `to_number`.
- `test_week_planning.py` — `planned_weeks` (5).
- `test_season_discovery.py` — `_parse_renew` + `discover_league_seasons`
  chain-walk / graceful-stop / hard-fail / cycle guard (6).
- `test_resume_gate.py` — `season_is_complete` value-aware resume gate (3).
- `test_coverage_weighting.py` — sampling, weighted coverage, zero-weight
  fallback, `_roster_week_weights`, SKIP→KEEP flip, 75% boundary (7).
- `test_backfill_since.py` — `--since` floor (1).
- `requirements-dev.txt` — dev deps (`pytest`), pulls `requirements.txt` via `-r`.

On-disk `data/` is the OLD mixed junk: 2010–2021 are all-zero (no coverage
block); 2022–2026 (12239) have real values but no coverage block; 14078 is
zeros/missing. All of it is to be wiped and regenerated.

## What's LEFT (next window)

1. **(Optional) Commit a checkpoint** of the vetted code + tests *before* the
   irreversible backfill (safe rollback point):
   `scripts/yahoo_client.py`, `scripts/fetch_all.py`, `tests/` (5 new files +
   the 2 prior), `requirements-dev.txt`. (Do NOT commit `data/` yet.)

2. **Wipe junk data + run the scoped backfill, then compute:**
   ```bash
   cd "c:/Users/mccom/OneDrive/Documents/yahoo-fantasy-baseball-allstars"
   rm -rf data/12239 data/14078 frontend/public/data/12239 frontend/public/data/14078
   python scripts/fetch_all.py --mode backfill --since 2021
   python scripts/compute_allstars.py
   python scripts/compute_records.py
   ```
   - Expect ~2021–2025 kept per league (+ current 2026); each historical
     `player_stats.json` should have non-zero `season_totals` and a `coverage`
     block; `leagues.json` lists only kept seasons.
   - **Watch the clock / rate limits.** Sampling adds ~5×teams roster calls per
     historical season; Yahoo 999 backoffs can stack. The client throttles
     (`YAHOO_MIN_REQUEST_INTERVAL`, default 0.6s) and backs off. Make sure no
     other Yahoo-hitting script is running (shared IP).
   - `frontend/public/data/` is a build artifact: the deploy workflow does
     `cp -R data frontend/public/data`. To preview locally, copy manually; the
     committed source of truth is `data/`.

3. **Docs** (`PRODUCT.md`/`DESIGN.md` — see memory `project_context`): historical
   = season-totals only; **roster-week-weighted ≥75% coverage gate**; retired
   players omitted+labeled via the `coverage` block; no historical weekly;
   data only back to 2021.

4. **Commit + push** code + regenerated `data/`. Pushing triggers the Pages
   deploy workflow.

5. (Known, out of scope) Current-season **weekly** per-player MLB stats are also
   broken (0/`date`) — `single_week` player records are compromised even live.
   Flag to owner separately.

## Scratchpad diagnostics (this session)

Under the session scratchpad (not committed):
- `dryrun_hist.py` — live recipe dry run, no writes.
- `persist_dryrun.py` — writes a real KEEP season + a SKIP coverage report to a
  scratch dir for review.
- `verify_weighted_gate.py` — head-count vs weighted gate per season
  (`LEAGUE_ID=14078 python verify_weighted_gate.py` for the other league; it
  defaults to all historical seasons, per-season try/except).

Memory `yahoo-mlb-api-quirks` has the recipe mechanism + coverage figures.

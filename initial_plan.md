# Yahoo Fantasy Baseball All-Stars

## Project Summary

A static web app hosted on GitHub Pages that celebrates performance across two Yahoo Fantasy Baseball leagues — past and present. GitHub Actions runs Python scripts on a daily schedule to fetch Yahoo data and commit the results as JSON files to the repo. The React frontend reads those JSON files directly; there is no backend server or database.

---

## Decisions (Resolved)

| Topic | Decision |
|---|---|
| Hosting | GitHub Pages (static frontend only) |
| Data pipeline | GitHub Actions cron — Python scripts fetch Yahoo data, commit JSON to repo |
| Backend server | None — eliminated by the static architecture |
| Database | None — JSON files in `data/` are the data store |
| Leagues | Two fixed leagues owned by the app owner — hardcoded in `config.yaml`, no user entry |
| Ranking metric | Actual season stats (HR, AVG, RBI, SB, ERA, WHIP, etc.) — not `percent_owned` |
| Scoring format | Head-to-Head Categories; stat categories fetched dynamically per league per season |
| League access | Owner's OAuth token used for all fetches (stored as GitHub Secret) |
| Historical depth | Full history: Actions discovers and fetches all past seasons on first run |

---

## Reference Project

Data collection mirrors [yahoo-fantasy-data-hub](https://github.com/mccomark21/yahoo-fantasy-data-hub):
- Auth via `yfpy` using `YAHOO_CONSUMER_KEY`, `YAHOO_CONSUMER_SECRET`, `YAHOO_REFRESH_TOKEN` (stored as GitHub Secrets)
- Roster fetch: `get_team_roster_player_info_by_week(team_id, "current")`
- Extended with:
  - Historical season discovery: probe past MLB `game_key`s to find all years a league existed
  - `get_league_stat_categories()` per league per season
  - Player season totals via `stats;type=season`
  - Weekly player stats via `stats;type=week` across all weeks of all seasons
  - Matchup scores via `get_league_matchups_by_week()` across all seasons

---

## How It Works

```
config.yaml (two hardcoded league IDs)
        ↓
GitHub Actions (daily cron or manual trigger)
        ↓
Python scripts fetch Yahoo data via yfpy
        ↓
Scripts compute all-stars, positional races, and all-time records
        ↓
Output written as JSON to data/ directory
        ↓
JSON committed to main branch → deploy.yml fires
        ↓
Vite build runs → dist/ deployed to GitHub Pages
        ↓
React app fetches JSON from relative paths and renders views
```

---

## GitHub Actions Workflows

### `historical-backfill.yml` (manual trigger — `workflow_dispatch`)
Runs once on initial setup. Iterates backward through all known MLB `game_key`s to find every season both leagues existed, then fetches full data for each: rosters, stat categories, season totals, all weekly stats, and all matchup scores. Progress is visible in the Actions log. Historical seasons are never re-fetched after this.

### `daily-refresh.yml` (cron — runs once daily)
Fetches current-season data only: rosters, current week stats, latest matchup scores. Recomputes all-stars, positional races, and records. Commits updated JSON, which triggers `deploy.yml`.

### `deploy.yml` (triggered on push to `main`)
Runs `vite build` and deploys `dist/` to GitHub Pages via the `peaceiris/actions-gh-pages` action.

---

## Data Output Structure

Python scripts write two layers of JSON:

**Raw per-season data** (used for filtering and re-sorting in the browser):
```
data/
└── {league_id}/
    └── {season}/
        ├── stat_categories.json   # Which stats this league tracked this year
        ├── rosters.json           # Player → fantasy team assignments
        ├── player_stats.json      # Season totals + week-by-week breakdown per player
        └── matchups.json          # Week-by-week team scores and matchup results
```

**Pre-computed aggregates** (loaded directly by each frontend view):
```
data/
├── leagues.json              # Both leagues with metadata and season list
├── all_stars.json            # Current-season top player per position per league
├── positional_races.json     # Current-season full player rankings per position per league
├── records_teams.json        # All-time team records across all seasons
└── records_players.json      # All-time player stat records across all seasons
```

---

## JSON Schemas (Key Fields)

### `all_stars.json`
```json
{
  "season": 2025,
  "updated_at": "2025-06-15T06:00:00Z",
  "leagues": {
    "12345": {
      "C":  {
        "player_name": "William Contreras",
        "mlb_team": "MIL",
        "mlb_team_logo_url": "https://...",
        "headshot_url": "https://...",
        "fantasy_team": "Base Invaders",
        "position": "C",
        "stats": { "HR": 14, "AVG": 0.291, "RBI": 38 }
      },
      "1B": { "..." },
      "SS": { "..." }
    }
  }
}
```

### `records_players.json`
```json
{
  "updated_at": "2025-06-15T06:00:00Z",
  "leagues": {
    "12345": {
      "single_week": [
        { "stat": "HR", "value": 9, "player_name": "...", "fantasy_team": "...", "season": 2019, "week": 14 }
      ],
      "season_total": [
        { "stat": "HR", "value": 52, "player_name": "...", "fantasy_team": "...", "season": 2022 }
      ]
    }
  }
}
```

### `records_teams.json`
```json
{
  "updated_at": "2025-06-15T06:00:00Z",
  "leagues": {
    "12345": {
      "highest_week_score": { "fantasy_team": "...", "score": 8.5, "season": 2021, "week": 7 },
      "longest_win_streak": { "fantasy_team": "...", "streak": 11, "season": 2018 },
      "best_season_record": { "fantasy_team": "...", "wins": 17, "losses": 3, "season": 2020 }
    }
  }
}
```

---

## Frontend Views

### 1. All-Stars (Homepage)

**Layout:** Full-screen baseball diamond occupying most of the viewport. Player cards are positioned directly on top of their field positions. Positions displayed: C, 1B, 2B, 3B, SS, LF, CF, RF, SP, RP, UTIL, DH.

**Visual Design — Stadium View:**
- Dark mode
- Realistic baseball field as the background
- Stadium lights glowing effect
- Crowd in the background, slightly blurred
- Player cards float above their field positions

**Player Card:**
Each card contains:
- Player headshot (from Yahoo/MLB API)
- Player name
- MLB team logo (small)
- Fantasy team name
- Position badge

Example card:
```
┌─────────────────────┐
│  [headshot photo]   │
│  Bobby Witt Jr.     │
│  [KC logo]          │
│  Fantasy Team:      │
│  "Base Invaders"    │
│        SS           │
└─────────────────────┘
```

Cards are clean, readable, and sized to fit comfortably on the diamond without overlapping.

**League Toggle:** A tab or pill switcher at the top lets the user flip between the two leagues. The diamond re-renders with that league's all-stars.

---

### 2. Positional Races

Full ranked leaderboard for each position showing all rostered players competing for the all-star slot. Sortable by any stat category the league tracks. Filterable by position. Shows how close the race is between players.

---

### 3. Team Records (All-Time)

Table of all-time team milestones across every season in the league's history:
- Highest single-week score ever
- Longest win streak ever
- Most category wins in a single week
- Best season record ever

Each record shows the fantasy team name, the season, and the week (where applicable).

---

### 4. Player Records (All-Time)

Table of all-time individual player records across every season:
- Most HR in a single week (all-time)
- Best single-week AVG (all-time)
- Most K's by a pitcher in a single week (all-time)
- Best season total per stat category

Each record shows the player name, fantasy team that season, season year, and week (for weekly records).

---

## Directory Structure

```
yahoo-fantasy-baseball-allstars/
├── .github/
│   └── workflows/
│       ├── historical-backfill.yml   # Manual trigger; full history fetch for both leagues
│       ├── daily-refresh.yml         # Daily cron; current season only
│       └── deploy.yml                # Vite build + GitHub Pages deploy on push to main
├── scripts/
│   ├── fetch_all.py                  # Entry point: --mode backfill or --mode refresh
│   ├── yahoo_client.py               # yfpy wrapper (rosters, stats, matchups, season discovery)
│   ├── compute_allstars.py           # Builds all_stars.json and positional_races.json
│   └── compute_records.py            # Builds records_teams.json and records_players.json
├── data/                             # Committed output — never hand-edited
│   ├── leagues.json
│   ├── all_stars.json
│   ├── positional_races.json
│   ├── records_teams.json
│   ├── records_players.json
│   └── {league_id}/
│       └── {season}/
│           ├── stat_categories.json
│           ├── rosters.json
│           ├── player_stats.json
│           └── matchups.json
├── frontend/
│   ├── public/
│   │   └── data -> ../../data        # Symlink so Vite serves data/ as static assets in dev
│   ├── src/
│   │   ├── App.tsx
│   │   ├── data.ts                   # Typed fetch helpers: loadAllStars(), loadRecords(), etc.
│   │   └── components/
│   │       ├── DiamondView.tsx        # SVG/CSS baseball diamond with positioned player cards
│   │       ├── PlayerCard.tsx         # Headshot, name, MLB team logo, fantasy team, position badge
│   │       ├── PositionalRace.tsx     # Ranked leaderboard per position; sortable by stat
│   │       ├── TeamRecords.tsx        # All-time team milestones table
│   │       └── PlayerRecords.tsx      # All-time player stat records table
│   └── vite.config.ts
├── config.yaml                       # Two league IDs; stat fetch settings
├── .env.example                      # Local dev only — not committed
├── requirements.txt
└── README.md
```

---

## Environment Variables / Secrets

**GitHub Secrets** (used by Actions workflows):
```
YAHOO_CONSUMER_KEY
YAHOO_CONSUMER_SECRET
YAHOO_REFRESH_TOKEN
```

**Local `.env`** (for running scripts locally):
```
YAHOO_CONSUMER_KEY=...
YAHOO_CONSUMER_SECRET=...
YAHOO_REFRESH_TOKEN=...
```

**`config.yaml`** (committed to repo):
```yaml
league_ids:
  - "12345"
  - "67890"

free_agent_sort: AR
free_agent_sort_type: season
```

---

## Build Phases

### Phase 1 — Python Data Pipeline
1. Create `yahoo_client.py` from `fetch_baseball_data.py`; extend with:
   - `discover_league_seasons(league_id)` — probes MLB `game_key`s backward to find all historical seasons
   - `fetch_stat_categories(league_id, game_key, season)`
   - `fetch_season_stats(player_keys, league_id, game_key)`
   - `fetch_weekly_stats(player_keys, league_id, game_key, week)`
   - `fetch_matchups(league_id, game_key)`
2. Create `fetch_all.py` with two modes:
   - `--mode backfill`: discover all seasons → fetch everything → write raw JSON per season
   - `--mode refresh`: current season only → overwrite raw JSON for current season
3. Create `compute_allstars.py` — reads raw JSON, writes `all_stars.json` (includes headshot URLs and MLB team logo URLs) and `positional_races.json`
4. Create `compute_records.py` — reads all raw JSON across all seasons, writes `records_teams.json` and `records_players.json`
5. Test locally against both leagues; verify JSON output is correct

### Phase 2 — GitHub Actions Workflows
1. `historical-backfill.yml` — `workflow_dispatch`; runs `fetch_all.py --mode backfill` then both compute scripts; commits `data/`
2. `daily-refresh.yml` — cron `0 10 * * *` (6 AM ET); runs `fetch_all.py --mode refresh` then compute scripts; commits `data/`
3. `deploy.yml` — triggers on push to `main`; runs `vite build`; deploys `dist/` to GitHub Pages
4. Add secrets to GitHub repo; run backfill workflow manually; confirm data populates and Pages deploys

### Phase 3 — React Frontend
1. Scaffold Vite + React + TypeScript
2. Create `data.ts` with typed loaders: `loadAllStars()`, `loadPositionalRaces()`, `loadTeamRecords()`, `loadPlayerRecords()`, `loadSeasonData(leagueId, season)`
3. `DiamondView` — SVG or CSS-positioned baseball field background with stadium lighting effect; player cards anchored to each position coordinate
4. `PlayerCard` — headshot image, player name, small MLB team logo, fantasy team name, position badge; dark-mode glass-card styling that floats above the field
5. `PositionalRace` — ranked leaderboard with stat sort picker driven by the league's `stat_categories`
6. `TeamRecords` — all-time records table with season and week context per record
7. `PlayerRecords` — all-time player records table; filterable by stat category
8. League toggle (pill switcher) at the top of each view to switch between the two leagues
9. Navigation tabs: **All-Stars** / **Positional Races** / **Team Records** / **Player Records**
10. Hash routing (`HashRouter`) for GitHub Pages compatibility

### Phase 4 — Polish
1. `updated_at` timestamp shown on each view
2. Smooth card entrance animation when the diamond loads
3. Responsive layout — diamond scales down gracefully on mobile; cards stack on narrow screens
4. Write `README.md` covering: Yahoo app registration, adding GitHub Secrets, running the backfill, and local dev setup

---

## Notes

- `data/` is committed to the repo and version-controlled. Every daily refresh creates a commit, giving a built-in audit trail of how stats change over the season.
- The historical backfill is a one-time manual trigger. It may take several minutes for long-lived leagues — progress is visible in the Actions log. Historical seasons are never re-fetched.
- Stat categories are stored per league per season since leagues can change tracked stats year to year.
- All-Stars and Positional Races are current-season views. Records views span all stored seasons.
- Player headshots and MLB team logos are fetched from Yahoo's CDN URLs returned in the player data — no separate image hosting needed.
- GitHub Pages uses hash-based routing (`HashRouter`) since there is no server to handle path rewrites.

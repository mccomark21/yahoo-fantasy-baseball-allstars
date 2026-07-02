# Fantasy Baseball All-Stars

A celebration of fantasy baseball performance across two private Yahoo leagues —
past and present. The season's best players are staged on an immersive baseball
diamond, backed by ranked positional races and an all-time records archive. No
backend, no auth: a static site on GitHub Pages, refreshed daily by GitHub
Actions. See [PRODUCT.md](PRODUCT.md) and [DESIGN.md](DESIGN.md).

## Shareable URLs

Each league has its own link that opens directly on that league's All-Stars — no
league picker to fiddle with. Send friends the link for their league:

| League | Link |
| --- | --- |
| **League of Champions™** | https://mccomark21.github.io/yahoo-fantasy-baseball-allstars/#/loc |
| **Sega Memorial** | https://mccomark21.github.io/yahoo-fantasy-baseball-allstars/#/sega |

The league is the leading segment of the URL, so deep links carry it too — e.g.
`…/#/loc/team-records`. The bare site (`…/#/`) redirects to a default league.

Slugs are configured per league id in [`config.yaml`](config.yaml)
(`league_slugs`); the daily refresh writes them into `data/leagues.json`, which
the frontend reads.

## How it runs

- **Daily Refresh / Historical Backfill** (`.github/workflows/`) fetch Yahoo data
  once and commit it under `data/` (one bundle keyed by league id — both leagues
  share the same fetch).
- **Deploy** builds the frontend and publishes to GitHub Pages, chained after the
  data workflows. One build serves both league URLs.

## Development

- Pipeline / data scripts: `scripts/` (see docstrings); tests in `tests/`
  (`python -m pytest`).
- Frontend: `frontend/` (React + TypeScript + Vite) — see
  [frontend/README.md](frontend/README.md).

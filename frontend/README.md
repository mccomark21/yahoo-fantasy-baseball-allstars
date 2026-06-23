# Frontend — All-Stars Diamond

React + TypeScript + Vite. Static SPA that reads committed JSON from `data/`.

## Develop

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Data is served at `/data/*` via `public/data`, a junction/symlink to the
repo-root `data/` directory. If it's missing (fresh clone on Windows), recreate
it:

```powershell
New-Item -ItemType Junction -Path public\data -Target ..\..\data
```

```bash
# macOS / Linux
ln -s ../../data public/data
```

## Build

```bash
npm run build    # type-check + vite build → dist/
npm run preview  # serve the production build locally
```

`vite.config.ts` uses `base: "./"` so the build works under GitHub Pages'
`/<repo>/` path. Data files are copied into `dist/data/` at build time.

## Design system

Tokens live in `src/styles/tokens.css` (the Stadium Palette, OKLCH). See
`../DESIGN.md` for the roles, named rules, and resolved values. The DiamondView
establishes the system the other three views inherit.

## Data shape

`src/data.ts` holds the typed loaders and interfaces. The diamond renders from
`data/all_stars.json`; league names come from `data/leagues.json`. Position →
coordinate mapping and the dynamic stat formatter live in
`src/constants/positions.ts`.

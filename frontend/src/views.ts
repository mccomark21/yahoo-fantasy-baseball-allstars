/* The four views that share the broadcast shell. One source of truth for the
   nav tabs, the router, and the per-view header copy. `ready: false` views are
   stubbed for now (built in later phases) — their tabs read "Soon". */

export interface ViewDef {
  id: string;
  path: string;
  label: string;
  title: string;
  hint: string;
  ready: boolean;
}

export const VIEWS: ViewDef[] = [
  {
    id: "all-stars",
    path: "/",
    label: "All-Stars",
    title: "All-Stars",
    hint: "Tap a card for season stats",
    ready: true,
  },
  {
    id: "positional-races",
    path: "/positional-races",
    label: "Positional Races",
    title: "Positional Races",
    hint: "Who is leading each position",
    ready: false,
  },
  {
    id: "team-records",
    path: "/team-records",
    label: "Team Records",
    title: "Team Records",
    hint: "Franchise highs and lows",
    ready: false,
  },
  {
    id: "player-records",
    path: "/player-records",
    label: "Player Records",
    title: "Player Records",
    hint: "Single-season and career marks",
    ready: false,
  },
];

export const viewByPath = (path: string): ViewDef =>
  VIEWS.find((v) => v.path === path) ?? VIEWS[0];

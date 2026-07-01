/* Field geometry. Coordinates are percentages of the field box (0–100),
   anchored at each card's center. Home plate sits bottom-center; second base
   at the top; the mound in the middle. */

export interface PositionSpec {
  key: string;
  label: string; // badge text
  full: string; // accessible / list name
  x: number; // % across the field box
  y: number; // % down the field box
  group: "Infield" | "Outfield" | "Pitching";
}

/* Coordinates map each card's center onto its true defensive spot over the
   1320×660 field box (see Field.tsx: home 660,556 · 1B 824,392 · 2B 660,228 ·
   3B 496,392 · mound 660,408). Array order also drives the entrance stagger —
   kept back-to-front (outfield → infield → battery) so the lineup fills in like
   players jogging to their positions. */
export const FIELD_POSITIONS: PositionSpec[] = [
  { key: "LF", label: "LF", full: "Left Field", x: 16, y: 25, group: "Outfield" },
  { key: "CF", label: "CF", full: "Center Field", x: 50, y: 16, group: "Outfield" },
  { key: "RF", label: "RF", full: "Right Field", x: 80, y: 25, group: "Outfield" },
  { key: "SS", label: "SS", full: "Shortstop", x: 40, y: 49, group: "Infield" },
  { key: "2B", label: "2B", full: "Second Base", x: 59, y: 45, group: "Infield" },
  { key: "3B", label: "3B", full: "Third Base", x: 21, y: 65, group: "Infield" },
  { key: "1B", label: "1B", full: "First Base", x: 73, y: 64, group: "Infield" },
  { key: "SP", label: "SP", full: "Starting Pitcher", x: 50, y: 63, group: "Pitching" },
  { key: "C", label: "C", full: "Catcher", x: 50, y: 89, group: "Infield" },
];

/* The bench lives on the field — a labelled column out in right field, to the
   right of first base — so the diamond can fill the full width of the screen
   instead of being squeezed by a band beneath it. */
export const BENCH_POSITIONS: PositionSpec[] = [
  { key: "UTIL", label: "UTIL", full: "Utility", x: 91, y: 51, group: "Pitching" },
  { key: "DH", label: "DH", full: "Designated Hitter", x: 91, y: 68, group: "Pitching" },
  { key: "RP", label: "RP", full: "Relief Pitcher", x: 91, y: 85, group: "Pitching" },
];

/* Where the on-field "Bench" label sits (caps the top of the bench column,
   one rhythm-step above UTIL). */
export const BENCH_LABEL_POS = { x: 91, y: 40 };

/* Ordering used by the mobile grouped list. */
export const LIST_GROUPS: { title: string; keys: string[] }[] = [
  { title: "Infield", keys: ["C", "1B", "2B", "3B", "SS"] },
  { title: "Outfield", keys: ["LF", "CF", "RF"] },
  { title: "Pitching", keys: ["SP", "RP"] },
  { title: "Bench", keys: ["UTIL", "DH"] },
];

export const ALL_POSITIONS = [...FIELD_POSITIONS, ...BENCH_POSITIONS];

/* Rate stats shown without a leading zero (baseball convention: .331). */
const LEADING_ZERO_DROP = new Set(["AVG", "OBP", "SLG", "OPS"]);

export function formatStat(key: string, value: number): string {
  if (LEADING_ZERO_DROP.has(key)) {
    return value.toFixed(3).replace(/^0/, "");
  }
  if (Number.isInteger(value)) return String(value);
  // ERA / WHIP and other rates keep two decimals + leading zero.
  return value.toFixed(2);
}

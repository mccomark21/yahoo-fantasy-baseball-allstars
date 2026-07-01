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
   3B 496,392 · mound 660,408). The three outfields are undifferentiated OF
   slots (issue #27); the pitcher isn't on the mound — the Rotation and Bullpen
   ride in a column off to the left, mirroring the reserves on the right — so the
   corner fielders sit a touch inward to clear those flanking columns. Array
   order drives the entrance stagger, kept back-to-front (outfield → infield →
   battery) so the lineup fills in like players jogging to their positions. */
export const FIELD_POSITIONS: PositionSpec[] = [
  { key: "OF1", label: "OF", full: "Outfield", x: 31, y: 25, group: "Outfield" },
  { key: "OF2", label: "OF", full: "Outfield", x: 50, y: 15, group: "Outfield" },
  { key: "OF3", label: "OF", full: "Outfield", x: 69, y: 25, group: "Outfield" },
  { key: "SS", label: "SS", full: "Shortstop", x: 41, y: 49, group: "Infield" },
  { key: "2B", label: "2B", full: "Second Base", x: 59, y: 45, group: "Infield" },
  { key: "3B", label: "3B", full: "Third Base", x: 33, y: 66, group: "Infield" },
  { key: "1B", label: "1B", full: "First Base", x: 67, y: 65, group: "Infield" },
  { key: "C", label: "C", full: "Catcher", x: 50, y: 89, group: "Infield" },
];

/* The pitching staff and the reserves ride in labelled columns that flank the
   diamond — Rotation + Bullpen on the left, Utility + Bench on the right — so
   the field fills the full width of the screen. Each entry is a badge label for
   its section; the cards themselves come from the grouped roster arrays. */
export interface SectionSpec {
  key: string; // section id + column side
  title: string; // column heading
  badge: string; // per-card position badge
  full: string; // accessible position name
  side: "left" | "right";
}

export const ROSTER_SECTIONS: SectionSpec[] = [
  { key: "rotation", title: "Rotation", badge: "SP", full: "Starting Pitcher", side: "left" },
  { key: "bullpen", title: "Bullpen", badge: "RP", full: "Relief Pitcher", side: "left" },
  { key: "utility", title: "Utility", badge: "UTIL", full: "Utility", side: "right" },
  { key: "bench", title: "Bench", badge: "BN", full: "Bench", side: "right" },
];

/* Ordering used by the mobile grouped list. Lineup slots are keyed; the reserve
   and pitching sections come straight from their roster arrays. */
export const LINEUP_GROUPS: { title: string; keys: string[] }[] = [
  { title: "Infield", keys: ["C", "1B", "2B", "3B", "SS"] },
  { title: "Outfield", keys: ["OF1", "OF2", "OF3"] },
];

export const ALL_POSITIONS = FIELD_POSITIONS;

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

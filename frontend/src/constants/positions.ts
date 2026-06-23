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

export const FIELD_POSITIONS: PositionSpec[] = [
  { key: "CF", label: "CF", full: "Center Field", x: 50, y: 11, group: "Outfield" },
  { key: "LF", label: "LF", full: "Left Field", x: 19, y: 22, group: "Outfield" },
  { key: "RF", label: "RF", full: "Right Field", x: 81, y: 22, group: "Outfield" },
  { key: "SS", label: "SS", full: "Shortstop", x: 36.5, y: 40, group: "Infield" },
  { key: "2B", label: "2B", full: "Second Base", x: 63.5, y: 40, group: "Infield" },
  { key: "SP", label: "SP", full: "Starting Pitcher", x: 50, y: 57.5, group: "Pitching" },
  { key: "3B", label: "3B", full: "Third Base", x: 22, y: 60, group: "Infield" },
  { key: "1B", label: "1B", full: "First Base", x: 78, y: 60, group: "Infield" },
  { key: "C", label: "C", full: "Catcher", x: 50, y: 86, group: "Infield" },
];

export const BENCH_POSITIONS: PositionSpec[] = [
  { key: "UTIL", label: "UTIL", full: "Utility", x: 0, y: 0, group: "Pitching" },
  { key: "DH", label: "DH", full: "Designated Hitter", x: 0, y: 0, group: "Pitching" },
  { key: "RP", label: "RP", full: "Relief Pitcher", x: 0, y: 0, group: "Pitching" },
];

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

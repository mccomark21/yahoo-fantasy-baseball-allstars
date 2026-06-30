import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import "./StatTable.css";

/* =========================================================================
   StatTable — the shared broadcast stat sheet.

   One presentational primitive behind all three table views (Positional
   Races, Team Records, Player Records). It owns layout, the Tabular Lock,
   sticky chrome, and sort affordances; the parent owns the data and the
   sort STATE (so an external sort picker and the header clicks stay in
   sync). Numbers never reflow on sort because every numeric column is
   tabular-mono and the row set per column is unchanged by reordering.
   ========================================================================= */

export type SortDir = "asc" | "desc";

/* Per-view entrance choreography. Each table view picks the move that fits its
   content — standings drop into rank (cascade), trophies are set down with
   weight (settle), records slide in from the identity edge (wipe) — so the
   three views don't share the uniform fade reflex. All are transform/opacity
   only and replay when the dataset behind them changes (see entranceToken). */
export type Entrance = "cascade" | "settle" | "wipe";

/* Cap the staggered count so a 100-deep UTIL race doesn't trail a 3s delay. */
const STAGGER_CAP = 16;

export interface StatColumn<T> {
  /** stable id; also the sort key passed back through onSort */
  key: string;
  /** header content (plain text, or a node — then set headerLabel) */
  header: ReactNode;
  /** accessible header text when `header` is not a plain string */
  headerLabel?: string;
  /** mono tabular figures + end-alignment by default */
  numeric?: boolean;
  align?: "start" | "center" | "end";
  /** clickable header that calls onSort(key) */
  sortable?: boolean;
  /** pins the column to the left edge while the rest scrolls (identity col) */
  sticky?: boolean;
  /** cell renderer */
  render: (row: T) => ReactNode;
}

interface StatTableProps<T> {
  columns: StatColumn<T>[];
  rows: T[];
  getRowKey: (row: T, index: number) => string;
  /** visually-hidden <caption> naming the table for screen readers */
  caption: string;
  /** current sort, reflected as aria-sort + a header glyph */
  sort?: { key: string; dir: SortDir };
  /** header click handler; omit to make headers static */
  onSort?: (key: string) => void;
  /** column whose cells + header carry the crimson "in focus" wash */
  highlightKey?: string;
  /** rows to tint crimson (e.g. the league leader) */
  isFeatured?: (row: T) => boolean;
  /** shown in place of <tbody> when there are no rows */
  emptyLabel?: string;
  /** entrance choreography for the body rows (omit for no entrance) */
  entrance?: Entrance;
  /** when this value changes, the entrance replays and scroll resets to the
      identity column — pass the dataset identity (league + filter), NOT the
      sort, so reordering never re-animates or reflows the numbers. */
  entranceToken?: string | number;
}

function alignFor<T>(col: StatColumn<T>): "start" | "center" | "end" {
  return col.align ?? (col.numeric ? "end" : "start");
}

function SortGlyph({ state }: { state: "asc" | "desc" | "idle" }) {
  return (
    <svg
      className="stat-table__glyph"
      data-state={state}
      viewBox="0 0 12 14"
      width="11"
      height="13"
      aria-hidden="true"
    >
      {/* up + down chevrons; the active direction lights up */}
      <path className="stat-table__glyph-up" d="M2 6 6 2l4 4" />
      <path className="stat-table__glyph-down" d="M2 8l4 4 4-4" />
    </svg>
  );
}

export default function StatTable<T>({
  columns,
  rows,
  getRowKey,
  caption,
  sort,
  onSort,
  highlightKey,
  isFeatured,
  emptyLabel = "No entries yet.",
  entrance,
  entranceToken,
}: StatTableProps<T>) {
  const frameRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  // True when there are columns scrolled off the right edge — drives the fade
  // affordance so narrow screens know the box score continues sideways.
  const [fadeRight, setFadeRight] = useState(false);

  // Track horizontal overflow + measure the scrollbar gutters so the fade can
  // sit just inside them (never painting over a scrollbar).
  useEffect(() => {
    const el = wrapRef.current;
    const frame = frameRef.current;
    if (!el || !frame) return;

    const measure = () => {
      frame.style.setProperty("--sbw", `${el.offsetWidth - el.clientWidth}px`);
      frame.style.setProperty("--sbh", `${el.offsetHeight - el.clientHeight}px`);
    };
    const updateFade = () => {
      const maxX = el.scrollWidth - el.clientWidth;
      const next = maxX > 1 && el.scrollLeft < maxX - 1;
      setFadeRight((prev) => (prev === next ? prev : next));
    };

    measure();
    updateFade();
    el.addEventListener("scroll", updateFade, { passive: true });
    const ro = new ResizeObserver(() => {
      measure();
      updateFade();
    });
    // Observe both the scroller (viewport size) and the table (content width):
    // a late web-font swap widens the table without changing the scroller box,
    // so without the inner observe the overflow would go undetected.
    ro.observe(el);
    const table = el.querySelector("table");
    if (table) ro.observe(table);
    // Belt-and-suspenders for the same font-swap reflow.
    document.fonts?.ready.then(updateFade).catch(() => {});
    return () => {
      el.removeEventListener("scroll", updateFade);
      ro.disconnect();
    };
  }, [columns, rows]);

  // A fresh dataset starts at the identity column; this also keeps the
  // entrance transform invisible against the sticky column (always at scroll 0).
  useEffect(() => {
    if (entranceToken === undefined) return;
    wrapRef.current?.scrollTo({ left: 0 });
  }, [entranceToken]);

  return (
    <div
      className="stat-table-frame"
      ref={frameRef}
      data-fade-right={fadeRight || undefined}
    >
    <div
      className="stat-table-wrap"
      ref={wrapRef}
      tabIndex={0}
      role="group"
      aria-label={caption}
    >
      <table className="stat-table" data-entrance={entrance}>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((col) => {
              const active = sort?.key === col.key;
              const ariaSort = active
                ? sort!.dir === "asc"
                  ? "ascending"
                  : "descending"
                : col.sortable
                ? "none"
                : undefined;
              return (
                <th
                  key={col.key}
                  scope="col"
                  className="stat-table__th"
                  data-align={alignFor(col)}
                  data-numeric={col.numeric || undefined}
                  data-sticky={col.sticky || undefined}
                  data-highlight={highlightKey === col.key || undefined}
                  data-active={active || undefined}
                  aria-sort={ariaSort}
                >
                  {col.sortable && onSort ? (
                    <button
                      type="button"
                      className="stat-table__sort"
                      onClick={() => onSort(col.key)}
                      aria-label={
                        typeof col.header === "string"
                          ? `Sort by ${col.headerLabel ?? col.header}`
                          : col.headerLabel
                          ? `Sort by ${col.headerLabel}`
                          : undefined
                      }
                    >
                      <span className="stat-table__th-label">{col.header}</span>
                      <SortGlyph
                        state={active ? (sort!.dir === "asc" ? "asc" : "desc") : "idle"}
                      />
                    </button>
                  ) : (
                    <span className="stat-table__th-label">{col.header}</span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr className="stat-table__empty-row">
              <td colSpan={columns.length} className="stat-table__empty">
                {emptyLabel}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr
                // Token in the key remounts the rows when the dataset changes
                // (replaying the entrance); a plain sort keeps keys stable so
                // React reorders in place — no re-animation, no column reflow.
                key={
                  entranceToken === undefined
                    ? getRowKey(row, i)
                    : `${entranceToken}|${getRowKey(row, i)}`
                }
                className="stat-table__row"
                style={{ "--i": Math.min(i, STAGGER_CAP) } as CSSProperties}
                data-featured={isFeatured?.(row) || undefined}
              >
                {columns.map((col) => {
                  const common = {
                    className: "stat-table__cell",
                    "data-align": alignFor(col),
                    "data-numeric": col.numeric || undefined,
                    "data-sticky": col.sticky || undefined,
                    "data-highlight": (highlightKey === col.key) || undefined,
                  } as const;
                  return col.sticky ? (
                    <th key={col.key} scope="row" {...common}>
                      {col.render(row)}
                    </th>
                  ) : (
                    <td key={col.key} {...common}>
                      {col.render(row)}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
      <div className="stat-table-fade" aria-hidden="true" />
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  loadPositionalRaces,
  loadStatCategories,
  type PositionalRacesData,
  type RaceEntry,
  type StatCategoriesFile,
} from "../data";
import { useShell } from "../context/ShellContext";
import { formatStat } from "../constants/positions";
import StatTable, { type SortDir, type StatColumn } from "./StatTable";
import Avatar from "./Avatar";
import BallIcon from "./BallIcon";
import UpdatedAt from "./UpdatedAt";
import "./tableviews.css";

/* Phase 3.3 — Positional Races. A ranked field per position, sortable by any
   stat the league tracks. The sort picker is driven by the league's own
   stat_categories (their order and their higher-vs-lower-is-better
   direction); clicking a column header sorts by it too, and the two stay in
   sync. First of the three table views — it owns the shared StatTable. */

type Status = "loading" | "ready" | "error";

/* Canonical leaderboard order; positions absent from a league are filtered. */
const POSITION_ORDER = [
  "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "SP", "RP", "UTIL", "DH",
];

const RANK_KEY = "__rank";

interface DirInfo {
  /** "best first" direction for this stat (desc = higher is better) */
  best: SortDir;
  label: string;
}

export default function PositionalRaceView() {
  const { leagueId } = useShell();

  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<PositionalRacesData | null>(null);
  const [cats, setCats] = useState<StatCategoriesFile | null>(null);

  const [position, setPosition] = useState<string>("");
  const [sort, setSort] = useState<{ key: string; dir: SortDir }>({
    key: RANK_KEY,
    dir: "asc",
  });

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const races = await loadPositionalRaces();
      setData(races);
      setStatus("ready");
      // Stat categories (which refine the sort picker) are loaded by the
      // league-keyed effect below; a miss there never blocks the leaderboard.
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Re-fetch stat categories when the active league changes.
  useEffect(() => {
    if (!data || !leagueId) return;
    let cancelled = false;
    loadStatCategories(leagueId, data.season)
      .then((c) => !cancelled && setCats(c))
      .catch(() => !cancelled && setCats(null));
    return () => {
      cancelled = true;
    };
  }, [leagueId, data]);

  const races = data?.leagues[leagueId];

  // Positions this league actually fields, in canonical order.
  const positions = useMemo(() => {
    if (!races) return [];
    return POSITION_ORDER.filter((p) => races[p]?.length);
  }, [races]);

  // Keep the selected position valid as data / league changes.
  useEffect(() => {
    if (!positions.length) return;
    setPosition((prev) => (positions.includes(prev) ? prev : positions[0]));
  }, [positions]);

  const entries = (position && races?.[position]) || [];

  // Direction + label lookup for each stat, from the league's categories.
  const dirByStat = useMemo(() => {
    const map = new Map<string, DirInfo>();
    for (const s of cats?.stats ?? []) {
      map.set(s.abbr, {
        // sort_order "1" → higher is better → best is descending.
        best: s.sort_order === "1" ? "desc" : "asc",
        label: s.display_name || s.abbr,
      });
    }
    return map;
  }, [cats]);

  // The stat columns for this position, ordered by the categories file when
  // available, otherwise by their natural order in the data.
  const statKeys = useMemo(() => {
    const present = entries.length ? Object.keys(entries[0].stats) : [];
    if (!cats) return present;
    const order = cats.stats.map((s) => s.abbr);
    const ranked = present
      .filter((k) => order.includes(k))
      .sort((a, b) => order.indexOf(a) - order.indexOf(b));
    const extra = present.filter((k) => !order.includes(k));
    return [...ranked, ...extra];
  }, [entries, cats]);

  const bestDir = useCallback(
    (key: string): SortDir => dirByStat.get(key)?.best ?? "desc",
    [dirByStat]
  );

  // Reset to the race order whenever the position changes.
  useEffect(() => {
    setSort({ key: RANK_KEY, dir: "asc" });
  }, [position]);

  const sortedRows = useMemo(() => {
    const rows = [...entries];
    if (sort.key === RANK_KEY) {
      rows.sort((a, b) => a.rank - b.rank);
      return sort.dir === "asc" ? rows : rows.reverse();
    }
    const factor = sort.dir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      const av = a.stats[sort.key];
      const bv = b.stats[sort.key];
      const an = typeof av === "number" ? av : null;
      const bn = typeof bv === "number" ? bv : null;
      if (an === null && bn === null) return a.rank - b.rank;
      if (an === null) return 1; // missing values sink regardless of direction
      if (bn === null) return -1;
      if (an === bn) return a.rank - b.rank; // ties break by race rank
      return (an - bn) * factor;
    });
    return rows;
  }, [entries, sort]);

  const onHeaderSort = useCallback(
    (key: string) => {
      setSort((prev) =>
        prev.key === key
          ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
          : { key, dir: bestDir(key) }
      );
    },
    [bestDir]
  );

  const onPickSort = useCallback(
    (key: string) => {
      setSort(
        key === RANK_KEY
          ? { key: RANK_KEY, dir: "asc" }
          : { key, dir: bestDir(key) }
      );
    },
    [bestDir]
  );

  const columns = useMemo<StatColumn<RaceEntry>[]>(() => {
    const identity: StatColumn<RaceEntry> = {
      key: "player",
      header: "Player",
      sticky: true,
      render: (r) => (
        <div className="tv-id">
          <span className="tv-rank" data-lead={r.rank === 1 || undefined}>
            {r.rank}
          </span>
          <Avatar name={r.player_name} src={r.headshot_url} />
          <span className="tv-id__text">
            <span className="tv-id__name">{r.player_name}</span>
            <span className="tv-id__team">
              {r.mlb_team} · {r.fantasy_team}
            </span>
          </span>
        </div>
      ),
    };
    const stats: StatColumn<RaceEntry>[] = statKeys.map((key) => ({
      key,
      header: key,
      headerLabel: dirByStat.get(key)?.label ?? key,
      numeric: true,
      sortable: true,
      render: (r) => {
        const v = r.stats[key];
        return typeof v === "number" ? formatStat(key, v) : "—";
      },
    }));
    return [identity, ...stats];
  }, [statKeys, dirByStat]);

  if (status === "error") {
    return (
      <div className="state state--error" role="alert">
        <BallIcon />
        <h2>We lost the feed</h2>
        <p>The positional races couldn’t be loaded. Check your connection and try again.</p>
        <button type="button" className="btn-retry" onClick={load}>
          Retry
        </button>
      </div>
    );
  }

  if (status === "loading") {
    return <TableSkeleton />;
  }

  if (!races || positions.length === 0) {
    return (
      <div className="state" role="status">
        <BallIcon />
        <h2>No races yet</h2>
        <p>This league hasn’t fielded enough players to rank a positional race.</p>
      </div>
    );
  }

  const sortLabel =
    sort.key === RANK_KEY
      ? "the race"
      : dirByStat.get(sort.key)?.label ?? sort.key;

  return (
    <div className="tableview">
      <div className="tv-controls">
        <div
          className="tv-chips"
          role="group"
          aria-label="Filter by position"
        >
          {positions.map((p) => (
            <button
              key={p}
              type="button"
              className="tv-chip"
              data-active={p === position || undefined}
              aria-pressed={p === position}
              onClick={() => setPosition(p)}
            >
              {p}
            </button>
          ))}
        </div>

        <label className="tv-select">
          <span>Sort</span>
          <select
            value={sort.key}
            onChange={(e) => onPickSort(e.target.value)}
          >
            <option value={RANK_KEY}>Race rank</option>
            {statKeys.map((k) => (
              <option key={k} value={k}>
                {dirByStat.get(k)?.label ?? k}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="tv-controls__caption" aria-live="polite">
        <b>{entries.length}</b> ranked at {position}, by {sortLabel}
      </p>

      <StatTable
        columns={columns}
        rows={sortedRows}
        getRowKey={(r) => `${r.rank}-${r.player_name}`}
        caption={`${position} positional race, sorted by ${sortLabel}`}
        sort={sort.key === RANK_KEY ? undefined : sort}
        onSort={onHeaderSort}
        highlightKey={sort.key === RANK_KEY ? undefined : sort.key}
        isFeatured={(r) => r.rank === 1}
        emptyLabel="No players at this position."
        entrance="cascade"
        entranceToken={`${leagueId}:${position}`}
      />

      {data?.updated_at && (
        <div className="tv-foot">
          <span>Ranked by season composite score</span>
          <UpdatedAt iso={data.updated_at} />
        </div>
      )}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="tableview">
      <div className="tv-skeleton" aria-busy="true" aria-label="Loading races">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="tv-skeleton__row" />
        ))}
      </div>
    </div>
  );
}

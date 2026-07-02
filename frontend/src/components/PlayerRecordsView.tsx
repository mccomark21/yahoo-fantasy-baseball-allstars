import { useCallback, useEffect, useMemo, useState } from "react";
import {
  loadPlayerRecords,
  type PlayerRecordsData,
  type SeasonStatRecord,
  type WeekStatRecord,
} from "../data";
import { useShell } from "../context/ShellContext";
import { formatStat } from "../constants/positions";
import StatTable, { type StatColumn } from "./StatTable";
import BallIcon from "./BallIcon";
import UpdatedAt from "./UpdatedAt";
import SeasonRange from "./SeasonRange";
import "./tableviews.css";

/* Phase 3.5 — Player Records. All-time individual marks for the active
   league: the best single-week explosion and the best full-season total for
   every stat the league tracks. Toggle between the two timeframes, filter to
   one stat, and the trophy value glows amber — consistent with Team Records. */

type Status = "loading" | "ready" | "error";
type Mode = "single_week" | "season_total";

/* Canonical category order so the chips and rows read batting → pitching. */
const STAT_ORDER = ["R", "HR", "RBI", "SB", "AVG", "W", "SV", "K", "ERA", "WHIP"];

const ALL = "__all";

type AnyRecord = WeekStatRecord | SeasonStatRecord;

function orderStats(stats: string[]): string[] {
  return [...stats].sort((a, b) => {
    const ai = STAT_ORDER.indexOf(a);
    const bi = STAT_ORDER.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b);
  });
}

const UNRESOLVED = /^Player\s+\d+\.p\.\d+$/;
function PlayerName({ name }: { name: string }) {
  if (UNRESOLVED.test(name)) {
    return (
      <span className="tv-id__name" title={name} style={{ color: "var(--muted)" }}>
        Unknown player
      </span>
    );
  }
  return <span className="tv-id__name">{name}</span>;
}

export default function PlayerRecordsView() {
  const { leagueId } = useShell();
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<PlayerRecordsData | null>(null);
  const [mode, setMode] = useState<Mode>("single_week");
  const [stat, setStat] = useState<string>(ALL);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setData(await loadPlayerRecords());
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const league = data?.leagues[leagueId];
  const records: AnyRecord[] = useMemo(
    () => (league ? league[mode] : []),
    [league, mode]
  );

  const stats = useMemo(
    () => orderStats(Array.from(new Set(records.map((r) => r.stat)))),
    [records]
  );

  // Keep the stat filter valid as mode / league changes.
  useEffect(() => {
    setStat((prev) => (prev === ALL || stats.includes(prev) ? prev : ALL));
  }, [stats]);

  const rows = useMemo(() => {
    const filtered =
      stat === ALL ? records : records.filter((r) => r.stat === stat);
    return [...filtered].sort(
      (a, b) =>
        (STAT_ORDER.indexOf(a.stat) === -1 ? 99 : STAT_ORDER.indexOf(a.stat)) -
        (STAT_ORDER.indexOf(b.stat) === -1 ? 99 : STAT_ORDER.indexOf(b.stat))
    );
  }, [records, stat]);

  const isWeekly = mode === "single_week";

  // The span these records actually cover. Unlike Team Records, the player views
  // can't reach retired players, so old seasons contribute nothing and the range
  // is derived from the records themselves (it lands at 2021+), not the league's
  // full season list — which would overstate how far back player marks go.
  const span = useMemo(() => {
    const yrs = [
      ...(league?.season_total ?? []).map((r) => r.season),
      ...(league?.single_week ?? []).map((r) => r.season),
    ];
    if (!yrs.length) return null;
    return { lo: Math.min(...yrs), hi: Math.max(...yrs) };
  }, [league]);

  const columns = useMemo<StatColumn<AnyRecord>[]>(() => {
    const cols: StatColumn<AnyRecord>[] = [
      {
        key: "stat",
        header: "Stat",
        sticky: true,
        render: (r) => <span className="tv-stat">{r.stat}</span>,
      },
      {
        key: "value",
        header: "Mark",
        numeric: true,
        render: (r) => <span className="tv-mark">{formatStat(r.stat, r.value)}</span>,
      },
      {
        key: "player",
        header: "Player",
        render: (r) => (
          <span className="tv-id__text">
            <PlayerName name={r.player_name} />
            <span className="tv-id__team">{r.fantasy_team}</span>
          </span>
        ),
      },
      {
        key: "when",
        header: isWeekly ? "Season · Week" : "Season",
        align: "end",
        render: (r) => (
          <span className="tv-when">
            <span className="tv-when__season">{r.season}</span>
            {isWeekly && "week" in r ? (
              <>
                {" · "}
                <span className="tv-when__week">Wk {(r as WeekStatRecord).week}</span>
              </>
            ) : null}
          </span>
        ),
      },
    ];
    return cols;
  }, [isWeekly]);

  if (status === "error") {
    return (
      <div className="state state--error" role="alert">
        <BallIcon />
        <h2>We lost the feed</h2>
        <p>The player records couldn’t be loaded. Check your connection and try again.</p>
        <button type="button" className="btn-retry" onClick={load}>
          Retry
        </button>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div className="tableview">
        <div className="tv-skeleton" aria-busy="true" aria-label="Loading records">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="tv-skeleton__row" />
          ))}
        </div>
      </div>
    );
  }

  const hasAny =
    league && (league.single_week.length > 0 || league.season_total.length > 0);

  if (!hasAny) {
    return (
      <div className="state" role="status">
        <BallIcon />
        <h2>No records yet</h2>
        <p>This league doesn’t have enough reachable history to crown its all-time player marks.</p>
      </div>
    );
  }

  return (
    <div className="tableview">
      <div className="tv-controls">
        <div className="tv-controls__group">
          <div className="tv-segment" role="group" aria-label="Record timeframe">
            <button
              type="button"
              className="tv-segment__btn"
              data-active={mode === "single_week" || undefined}
              aria-pressed={mode === "single_week"}
              onClick={() => setMode("single_week")}
            >
              Single Week
            </button>
            <button
              type="button"
              className="tv-segment__btn"
              data-active={mode === "season_total" || undefined}
              aria-pressed={mode === "season_total"}
              onClick={() => setMode("season_total")}
            >
              Season Totals
            </button>
          </div>
        </div>

        <div className="tv-chips" role="group" aria-label="Filter by stat">
          <button
            type="button"
            className="tv-chip"
            data-active={stat === ALL || undefined}
            aria-pressed={stat === ALL}
            onClick={() => setStat(ALL)}
          >
            All
          </button>
          {stats.map((s) => (
            <button
              key={s}
              type="button"
              className="tv-chip"
              data-active={stat === s || undefined}
              aria-pressed={stat === s}
              onClick={() => setStat(s)}
            >
              {s}
            </button>
          ))}
        </div>
        {span && <SeasonRange lo={span.lo} hi={span.hi} />}
      </div>

      <StatTable
        columns={columns}
        rows={rows}
        getRowKey={(r) => `${mode}-${r.stat}`}
        caption={`All-time ${isWeekly ? "single-week" : "season-total"} player records`}
        emptyLabel="No records for this stat yet."
        entrance="wipe"
        entranceToken={`${leagueId}:${mode}:${stat}`}
      />

      {data?.updated_at && (
        <div className="tv-foot">
          <span>
            {isWeekly
              ? "Best single week, all-time"
              : "Best full-season total, all-time"}
          </span>
          <UpdatedAt iso={data.updated_at} />
        </div>
      )}
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  loadPlayerRecords,
  type PlayerRecordsData,
  type PlayerStatLeaderboard,
} from "../data";
import { useShell } from "../context/ShellContext";
import { formatStat } from "../constants/positions";
import StatTable, { type StatColumn } from "./StatTable";
import BallIcon from "./BallIcon";
import UpdatedAt from "./UpdatedAt";
import SeasonRange from "./SeasonRange";
import "./tableviews.css";

/* Phase 3.5 — Player Records (issue #30). All-time individual leaderboards for
   the active league. Pick a timeframe — the best single week or the best full
   season — then either browse the whole board at a glance ("All": the #1 mark in
   every stat) or filter to one stat for its ranked top-10 leaderboard. The unit
   is a player-season, so the same player can hold several places on a board
   (different seasons are distinct marks). The trophy value carries Stadium Amber.

   Reach is data-bound: Yahoo archival leaves season totals reaching ~2021+ and
   weekly current-season only, so single-week boards fill in as live history
   accrues. SeasonRange surfaces the true covered span rather than let "all-time"
   overstate how far back the marks go. */

type Status = "loading" | "ready" | "error";
type Mode = "single_week" | "season_total";

const ALL = "__all";

/** A flat table row for either view: the "All" summary (one #1 per stat, no
    rank) or a single stat's ranked board (rank set). */
interface Row {
  rank?: number;
  stat: string;
  value: number;
  player_name: string;
  fantasy_team: string;
  season: number;
  week?: number;
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

function When({ season, week }: { season: number; week?: number }) {
  return (
    <span className="tv-when">
      <span className="tv-when__season">{season}</span>
      {week != null ? (
        <>
          {" · "}
          <span className="tv-when__week">Wk {week}</span>
        </>
      ) : null}
    </span>
  );
}

export default function PlayerRecordsView() {
  const { leagueId } = useShell();
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<PlayerRecordsData | null>(null);
  const [mode, setMode] = useState<Mode>("season_total");
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
  const boards: PlayerStatLeaderboard[] = useMemo(
    () => (league ? league[mode] : []),
    [league, mode]
  );

  // Pipeline already orders boards batting → pitching; keep that order.
  const stats = useMemo(() => boards.map((b) => b.stat), [boards]);

  // Keep the stat filter valid as mode / league changes.
  useEffect(() => {
    setStat((prev) => (prev === ALL || stats.includes(prev) ? prev : ALL));
  }, [stats]);

  const board = useMemo(
    () => boards.find((b) => b.stat === stat),
    [boards, stat]
  );

  const isAll = stat === ALL;
  const isWeekly = mode === "single_week";

  const rows = useMemo<Row[]>(() => {
    if (isAll) {
      // Summary: the #1 mark in every stat, in canonical order.
      return stats
        .map((s) => {
          const b = boards.find((x) => x.stat === s);
          const top = b?.entries[0];
          return top ? { stat: s, ...top } : null;
        })
        .filter((r): r is Row => r !== null);
    }
    if (!board) return [];
    return board.entries.map((e, i) => ({ rank: i + 1, stat: board.stat, ...e }));
  }, [isAll, stats, boards, board]);

  // The span the active timeframe actually covers. Unlike Team Records, the
  // player views can't reach retired players / archived seasons, so the range is
  // derived from the entries themselves and tracks the mode: season totals land
  // ~2021+, single week is current-season only. Deriving it (rather than using the
  // league's full season list) keeps "all-time" from overstating the true reach.
  const span = useMemo(() => {
    const yrs = boards.flatMap((b) => b.entries.map((e) => e.season));
    if (!yrs.length) return null;
    return { lo: Math.min(...yrs), hi: Math.max(...yrs) };
  }, [boards]);

  const columns = useMemo<StatColumn<Row>[]>(() => {
    if (isAll) {
      return [
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
          render: (r) => <When season={r.season} week={r.week} />,
        },
      ];
    }
    // Ranked leaderboard for one stat: rank + player identity, mark, when.
    return [
      {
        key: "player",
        header: "Player",
        sticky: true,
        render: (r) => (
          <div className="tv-id">
            <span className="tv-rank" data-lead={r.rank === 1 || undefined}>
              {r.rank}
            </span>
            <span className="tv-id__text">
              <PlayerName name={r.player_name} />
              <span className="tv-id__team">{r.fantasy_team}</span>
            </span>
          </div>
        ),
      },
      {
        key: "value",
        header: "Mark",
        numeric: true,
        render: (r) => <span className="tv-mark">{formatStat(r.stat, r.value)}</span>,
      },
      {
        key: "when",
        header: isWeekly ? "Season · Week" : "Season",
        align: "end",
        render: (r) => <When season={r.season} week={r.week} />,
      },
    ];
  }, [isAll, isWeekly]);

  const caption = isAll
    ? `All-time ${isWeekly ? "single-week" : "season-total"} player records`
    : `Top ${rows.length} ${board?.display ?? stat} — best ${
        isWeekly ? "single week" : "season total"
      }, all-time`;

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
              data-active={mode === "season_total" || undefined}
              aria-pressed={mode === "season_total"}
              onClick={() => setMode("season_total")}
            >
              Season Totals
            </button>
            <button
              type="button"
              className="tv-segment__btn"
              data-active={mode === "single_week" || undefined}
              aria-pressed={mode === "single_week"}
              onClick={() => setMode("single_week")}
            >
              Single Week
            </button>
          </div>
        </div>

        <div className="tv-chips" role="group" aria-label="Filter by stat">
          <button
            type="button"
            className="tv-chip"
            data-active={isAll || undefined}
            aria-pressed={isAll}
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

      <p className="tv-controls__caption" aria-live="polite">
        {caption}
      </p>

      <StatTable
        columns={columns}
        rows={rows}
        getRowKey={(r) =>
          isAll
            ? `${mode}-${r.stat}`
            : `${mode}-${r.stat}-${r.rank}-${r.player_name}-${r.season}${
                r.week != null ? `-${r.week}` : ""
              }`
        }
        caption={caption}
        isFeatured={(r) => r.rank === 1}
        emptyLabel="No records for this stat yet."
        entrance={isAll ? "wipe" : "cascade"}
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

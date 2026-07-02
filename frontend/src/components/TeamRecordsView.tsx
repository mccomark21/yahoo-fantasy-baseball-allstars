import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  loadTeamRecords,
  type TeamRecords,
  type TeamRecordsData,
} from "../data";
import { useShell } from "../context/ShellContext";
import { formatStat } from "../constants/positions";
import StatTable, { type StatColumn } from "./StatTable";
import BallIcon from "./BallIcon";
import UpdatedAt from "./UpdatedAt";
import SeasonRange from "./SeasonRange";
import "./tableviews.css";

/* Phase 3.4 — Team Records (issue #29). Reshaped from four fixed matchup
   trophies into a Player-Records-style leaderboard: a chip selector — Best
   Season · Worst Season · then one chip per counting stat — swaps a top-5 table
   of all-time team-seasons beneath it. The unit is a team-season, so the same
   franchise can appear more than once. Best/Worst marks are a season-long
   W-L-T that matches the league's Yahoo scoring format (category aggregate for
   "head" leagues, weekly for "headone"); counting boards mark a season total.
   The mark carries Stadium Amber — the trophy number (Rarity Rule). */

type Status = "loading" | "ready" | "error";

const BEST = "__best";
const WORST = "__worst";

interface LeaderRow {
  rank: number;
  team: string;
  mark: ReactNode;
  season: number;
}

/* Best/Worst season W-L-T. Ties are shown only when they happen, so a headone
   league's clean 18–4 doesn't grow a redundant "–0". */
function WltMark({ w, l, t }: { w: number; l: number; t: number }) {
  return (
    <span className="tv-mark">
      {w}
      <span aria-hidden="true">–</span>
      {l}
      {t > 0 ? (
        <>
          <span aria-hidden="true">–</span>
          {t}
        </>
      ) : null}
      <span className="visually-hidden">
        {` ${w} wins ${l} losses${t > 0 ? ` ${t} ties` : ""}`}
      </span>
    </span>
  );
}

const COLUMNS: StatColumn<LeaderRow>[] = [
  {
    key: "team",
    header: "Team",
    sticky: true,
    render: (r) => (
      <div className="tv-id">
        <span className="tv-rank" data-lead={r.rank === 1 || undefined}>
          {r.rank}
        </span>
        <span className="tv-id__text">
          <span className="tv-id__name">{r.team}</span>
        </span>
      </div>
    ),
  },
  {
    key: "mark",
    header: "Mark",
    numeric: true,
    render: (r) => r.mark,
  },
  {
    key: "season",
    header: "Season",
    align: "end",
    render: (r) => <span className="tv-when tv-when__season">{r.season}</span>,
  },
];

export default function TeamRecordsView() {
  const { leagueId, leagues } = useShell();
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<TeamRecordsData | null>(null);
  const [sel, setSel] = useState<string>(BEST);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setData(await loadTeamRecords());
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rec: TeamRecords | undefined = data?.leagues[leagueId];

  // Selector entries: the two W-L-T boards, then one per counting stat (already
  // in the league's canonical batting → pitching order from the pipeline).
  const options = useMemo(() => {
    const opts = [
      { key: BEST, label: "Best Season" },
      { key: WORST, label: "Worst Season" },
    ];
    for (const b of rec?.season_stats ?? []) {
      opts.push({ key: b.stat, label: b.stat });
    }
    return opts;
  }, [rec]);

  // Keep the selection valid as league / data changes.
  useEffect(() => {
    const keys = new Set(options.map((o) => o.key));
    setSel((prev) => (keys.has(prev) ? prev : BEST));
  }, [options]);

  const board = useMemo(
    () => rec?.season_stats.find((b) => b.stat === sel),
    [rec, sel]
  );

  // The span these records search: every reachable season for the active league
  // (leagues.json lists exactly the seasons on disk). Team records reach back
  // further than the player-facing views, so we surface the range rather than
  // let the "all-time" copy hide how far back "all" actually goes.
  const span = useMemo(() => {
    const yrs = leagues.find((l) => l.id === leagueId)?.seasons ?? [];
    if (!yrs.length) return null;
    return { lo: Math.min(...yrs), hi: Math.max(...yrs) };
  }, [leagues, leagueId]);

  const rows = useMemo<LeaderRow[]>(() => {
    if (!rec) return [];
    if (sel === BEST || sel === WORST) {
      const src = sel === BEST ? rec.best_season : rec.worst_season;
      return src.map((s, i) => ({
        rank: i + 1,
        team: s.fantasy_team,
        mark: <WltMark w={s.wins} l={s.losses} t={s.ties} />,
        season: s.season,
      }));
    }
    if (!board) return [];
    return board.entries.map((e, i) => ({
      rank: i + 1,
      team: e.fantasy_team,
      mark: <span className="tv-mark">{formatStat(board.stat, e.value)}</span>,
      season: e.season,
    }));
  }, [rec, sel, board]);

  // Contextual copy for the live caption + footer.
  const isSeason = sel === BEST || sel === WORST;
  const wltNote =
    rec?.scoring_type === "head"
      ? "season-long category W–L–T"
      : "weekly W–L–T";
  const caption = isSeason
    ? `The ${sel === BEST ? "best" : "worst"} team-seasons of all time — ${wltNote}`
    : `Most ${board?.display ?? sel} in a single team-season`;

  if (status === "error") {
    return (
      <div className="state state--error" role="alert">
        <BallIcon />
        <h2>We lost the feed</h2>
        <p>The team records couldn’t be loaded. Check your connection and try again.</p>
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
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="tv-skeleton__row" />
          ))}
        </div>
      </div>
    );
  }

  const hasAny =
    rec && (rec.best_season.length > 0 || rec.season_stats.length > 0);

  if (!hasAny) {
    return (
      <div className="state" role="status">
        <BallIcon />
        <h2>No records yet</h2>
        <p>This league doesn’t have enough reachable history to crown its all-time team marks.</p>
      </div>
    );
  }

  return (
    <div className="tableview">
      <div className="tv-controls">
        <div className="tv-chips" role="group" aria-label="Team record category">
          {options.map((o, i) => (
            <Fragment key={o.key}>
              {i === 2 ? <span className="tv-chips__sep" aria-hidden="true" /> : null}
              <button
                type="button"
                className="tv-chip"
                data-active={sel === o.key || undefined}
                aria-pressed={sel === o.key}
                onClick={() => setSel(o.key)}
              >
                {o.label}
              </button>
            </Fragment>
          ))}
        </div>
        {span && <SeasonRange lo={span.lo} hi={span.hi} />}
      </div>

      <p className="tv-controls__caption" aria-live="polite">
        {caption}
      </p>

      <StatTable
        columns={COLUMNS}
        rows={rows}
        getRowKey={(r) => `${sel}-${r.rank}-${r.team}`}
        caption={caption}
        isFeatured={(r) => r.rank === 1}
        emptyLabel="No team-seasons to rank yet."
        entrance="cascade"
        entranceToken={`${leagueId}:${sel}`}
      />

      {data?.updated_at && (
        <div className="tv-foot">
          <span>
            {isSeason
              ? "All-time team-seasons, every reachable year"
              : "Top team-seasons, all-time"}
          </span>
          <UpdatedAt iso={data.updated_at} />
        </div>
      )}
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  loadTeamRecords,
  type TeamRecords,
  type TeamRecordsData,
} from "../data";
import { useShell } from "../context/ShellContext";
import StatTable, { type StatColumn } from "./StatTable";
import BallIcon from "./BallIcon";
import "./tableviews.css";

/* Phase 3.4 — Team Records. The all-time franchise milestones for the active
   league, presented in the shared StatTable. Each row is a different record
   with its own unit, so the "Mark" column carries the trophy number itself —
   the one place Stadium Amber is allowed here (Rarity Rule). */

type Status = "loading" | "ready" | "error";

interface TeamRow {
  id: string;
  name: string;
  desc: string;
  team: string;
  mark: ReactNode;
  season: number;
  week?: number;
}

function buildRows(rec: TeamRecords): TeamRow[] {
  const rows: TeamRow[] = [];

  if (rec.highest_week_score) {
    const r = rec.highest_week_score;
    rows.push({
      id: "highest_week_score",
      name: "Highest Week",
      desc: "Most category points in a single matchup",
      team: r.fantasy_team,
      mark: <Mark value={r.score} unit="pts" />,
      season: r.season,
      week: r.week,
    });
  }

  if (rec.most_category_wins_week) {
    const r = rec.most_category_wins_week;
    rows.push({
      id: "most_category_wins_week",
      name: "Category Sweep",
      desc: "Most stat categories won in one week",
      team: r.fantasy_team,
      mark: <Mark value={r.wins} unit="cats" />,
      season: r.season,
      week: r.week,
    });
  }

  if (rec.longest_win_streak) {
    const r = rec.longest_win_streak;
    rows.push({
      id: "longest_win_streak",
      name: "Win Streak",
      desc: "Most consecutive matchup wins",
      team: r.fantasy_team,
      mark: <Mark value={r.streak} unit="wks" />,
      season: r.season,
    });
  }

  if (rec.best_season_record) {
    const r = rec.best_season_record;
    rows.push({
      id: "best_season_record",
      name: "Best Season",
      desc: "Best regular-season win–loss record",
      team: r.fantasy_team,
      mark: (
        <span className="tv-mark">
          {r.wins}
          <span aria-hidden="true">–</span>
          {r.losses}
          <span className="visually-hidden"> win loss</span>
        </span>
      ),
      season: r.season,
    });
  }

  return rows;
}

function Mark({ value, unit }: { value: number; unit: string }) {
  return (
    <span className="tv-mark">
      {value}
      <small>{unit}</small>
    </span>
  );
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

const COLUMNS: StatColumn<TeamRow>[] = [
  {
    key: "record",
    header: "Record",
    sticky: true,
    render: (r) => (
      <div className="tv-record">
        <span className="tv-record__name">{r.name}</span>
        <span className="tv-record__desc">{r.desc}</span>
      </div>
    ),
  },
  {
    key: "team",
    header: "Holder",
    render: (r) => <span className="tv-id__name">{r.team}</span>,
  },
  {
    key: "mark",
    header: "Mark",
    numeric: true,
    render: (r) => r.mark,
  },
  {
    key: "when",
    header: "When",
    align: "end",
    render: (r) => <When season={r.season} week={r.week} />,
  },
];

export default function TeamRecordsView() {
  const { leagueId } = useShell();
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<TeamRecordsData | null>(null);

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

  const rows = useMemo(() => {
    const rec = data?.leagues[leagueId];
    return rec ? buildRows(rec) : [];
  }, [data, leagueId]);

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
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="tv-skeleton__row" />
          ))}
        </div>
      </div>
    );
  }

  if (rows.length === 0) {
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
      <StatTable
        columns={COLUMNS}
        rows={rows}
        getRowKey={(r) => r.id}
        caption="All-time team records"
      />
      {data?.updated_at && (
        <div className="tv-foot">
          <span>All-time, across every reachable season</span>
          <span>
            Updated{" "}
            <time dateTime={data.updated_at} className="mono">
              {formatDate(data.updated_at)}
            </time>
          </span>
        </div>
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

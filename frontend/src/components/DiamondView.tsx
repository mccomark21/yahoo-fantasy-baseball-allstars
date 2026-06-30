import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { loadAllStars, type AllStarsData } from "../data";
import {
  BENCH_POSITIONS,
  FIELD_POSITIONS,
  LIST_GROUPS,
  ALL_POSITIONS,
} from "../constants/positions";
import { useShell } from "../context/ShellContext";
import Field from "./Field";
import PlayerCard from "./PlayerCard";
import BallIcon from "./BallIcon";
import UpdatedAt from "./UpdatedAt";
import "./PlayerCard.css";
import "./diamond.css";

const DESIGN_W = 940;
const FIELD_H = Math.round(DESIGN_W * 0.76); // 714 — the field box the % coords assume
const BENCH_BAND_H = 116; // dugout band below the catcher (keep in sync with diamond.css)
const DESIGN_H = FIELD_H + BENCH_BAND_H; // 830 — full scaled unit: field + bench
const MAX_SCALE = 1.2; // let the field grow past natural size to fill the screen
const NARROW_BREAKPOINT = 600;

type Status = "loading" | "ready" | "error";

export default function DiamondView() {
  // The active league lives in the shell so it persists across views; this view
  // renders `renderedLeagueId`, which lags the shell's selection by one beat so
  // the cards can play their switch animation.
  const { leagueId } = useShell();
  const [renderedLeagueId, setRenderedLeagueId] = useState(leagueId);

  const [status, setStatus] = useState<Status>("loading");
  const [allStars, setAllStars] = useState<AllStarsData | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [isNarrow, setIsNarrow] = useState(false);
  const [entering, setEntering] = useState(true);
  const switchTimer = useRef<number>();

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const as = await loadAllStars();
      setAllStars(as);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Mirror the shell's league selection into the view. The first resolved id is
  // adopted instantly; later changes play the brief switch crossfade.
  useEffect(() => {
    if (leagueId === renderedLeagueId) return;
    if (!renderedLeagueId) {
      setRenderedLeagueId(leagueId);
      return;
    }
    setExpandedKey(null);
    setSwitching(true);
    window.clearTimeout(switchTimer.current);
    switchTimer.current = window.setTimeout(() => {
      setRenderedLeagueId(leagueId);
      setSwitching(false);
    }, 170);
    return () => window.clearTimeout(switchTimer.current);
  }, [leagueId, renderedLeagueId]);

  // Fit the fixed-size diamond into the available stage box via transform.
  useLayoutEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setIsNarrow(width < NARROW_BREAKPOINT);
      // Fill the available box. Allow modest upscaling past natural size so a
      // roomy desktop genuinely uses the screen; cap it so card text stays sharp.
      const fit = Math.min(width / DESIGN_W, height / DESIGN_H, MAX_SCALE);
      setScale(Number.isFinite(fit) && fit > 0 ? fit : 1);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [status]);

  // Entrance choreography fires once, on first ready render only.
  useEffect(() => {
    if (status !== "ready") return;
    const t = window.setTimeout(() => setEntering(false), 1500);
    return () => window.clearTimeout(t);
  }, [status]);

  // Escape collapses an expanded card.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpandedKey(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggleCard = useCallback((key: string) => {
    setExpandedKey((prev) => (prev === key ? null : key));
  }, []);

  if (status === "error") {
    return (
      <div className="state state--error" role="alert">
        <BallIcon />
        <h2>We lost the feed</h2>
        <p>The all-star data couldn’t be loaded. Check your connection and try again.</p>
        <button type="button" className="btn-retry" onClick={load}>
          Retry
        </button>
      </div>
    );
  }

  const league = allStars?.leagues[renderedLeagueId];
  const updated = allStars?.updated_at;

  return (
    <>
      <div className="stage" ref={stageRef}>
        {status === "loading" ? (
          <Skeleton scale={scale} isNarrow={isNarrow} />
        ) : isNarrow ? (
          <GroupedList
            league={league}
            switching={switching}
            expandedKey={expandedKey}
            onToggle={toggleCard}
          />
        ) : (
          <div
            className="diamond"
            data-entering={entering || undefined}
            style={{ "--scale": scale } as React.CSSProperties}
          >
            <div className="diamond__field-wrap">
              <div className="diamond__field">
                <Field />
              </div>
              <div className="diamond__lights" aria-hidden="true">
                <span className="diamond__light diamond__light--l" />
                <span className="diamond__light diamond__light--r" />
              </div>
              <div className="diamond__cards" data-switching={switching || undefined}>
                {FIELD_POSITIONS.map((pos, i) => (
                  <div
                    key={pos.key}
                    className="diamond__slot"
                    style={
                      {
                        "--x": `${pos.x}%`,
                        "--y": `${pos.y}%`,
                        "--i": i,
                      } as React.CSSProperties
                    }
                    data-active={expandedKey === pos.key || undefined}
                  >
                    <PlayerCard
                      position={pos}
                      player={league?.[pos.key] ?? null}
                      expanded={expandedKey === pos.key}
                      onToggle={() => toggleCard(pos.key)}
                      index={i}
                    />
                  </div>
                ))}
              </div>
            </div>

            <section
              className="diamond__bench"
              aria-label="Bench"
              data-switching={switching || undefined}
            >
              <h2 className="diamond__bench-label">Bench</h2>
              <div className="diamond__bench-row">
                {BENCH_POSITIONS.map((pos, i) => (
                  <PlayerCard
                    key={pos.key}
                    position={pos}
                    player={league?.[pos.key] ?? null}
                    expanded={expandedKey === pos.key}
                    onToggle={() => toggleCard(pos.key)}
                    index={FIELD_POSITIONS.length + i}
                  />
                ))}
              </div>
            </section>
          </div>
        )}
      </div>

      <footer className="view-footer">
        {updated && status === "ready" && (
          <p className="view-footer__updated">
            <UpdatedAt iso={updated} />
          </p>
        )}
      </footer>
    </>
  );
}

/* ----------------------------------------------------------------------- */

function Skeleton({ scale, isNarrow }: { scale: number; isNarrow: boolean }) {
  if (isNarrow) {
    return (
      <div className="skeleton-list" aria-busy="true" aria-label="Loading lineup">
        {ALL_POSITIONS.slice(0, 9).map((p) => (
          <div key={p.key} className="skel skel--row" />
        ))}
      </div>
    );
  }
  return (
    <div
      className="diamond"
      style={{ "--scale": scale } as React.CSSProperties}
      aria-busy="true"
      aria-label="Loading lineup"
    >
      <div className="diamond__field-wrap">
        <div className="diamond__field">
          <Field />
        </div>
        <div className="diamond__cards">
          {FIELD_POSITIONS.map((pos) => (
            <div
              key={pos.key}
              className="diamond__slot"
              style={{ "--x": `${pos.x}%`, "--y": `${pos.y}%` } as React.CSSProperties}
            >
              <div className="skel skel--card" />
            </div>
          ))}
        </div>
      </div>
      <div className="diamond__bench" aria-hidden="true">
        <h2 className="diamond__bench-label">Bench</h2>
        <div className="diamond__bench-row">
          {BENCH_POSITIONS.map((pos) => (
            <div key={pos.key} className="skel skel--card" />
          ))}
        </div>
      </div>
    </div>
  );
}

function GroupedList({
  league,
  switching,
  expandedKey,
  onToggle,
}: {
  league: ReturnType<() => AllStarsData["leagues"][string]> | undefined;
  switching: boolean;
  expandedKey: string | null;
  onToggle: (key: string) => void;
}) {
  return (
    <div className="grouped-list" data-switching={switching || undefined}>
      {LIST_GROUPS.map((group) => (
        <section key={group.title} className="grouped-list__group">
          <h2 className="grouped-list__title">{group.title}</h2>
          <div className="grouped-list__items">
            {group.keys.map((key, i) => {
              const pos = ALL_POSITIONS.find((p) => p.key === key)!;
              return (
                <PlayerCard
                  key={key}
                  position={pos}
                  player={league?.[key] ?? null}
                  expanded={expandedKey === key}
                  onToggle={() => onToggle(key)}
                  index={i}
                  variant="bench"
                />
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

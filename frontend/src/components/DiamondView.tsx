import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { loadAllStars, type AllStarsData } from "../data";
import {
  BENCH_POSITIONS,
  BENCH_LABEL_POS,
  FIELD_POSITIONS,
  LIST_GROUPS,
  ALL_POSITIONS,
} from "../constants/positions";
import { useShell } from "../context/ShellContext";
import Field from "./Field";
import PlayerCard from "./PlayerCard";
import BallIcon from "./BallIcon";
import "./PlayerCard.css";
import "./diamond.css";

const DESIGN_W = 1320; // broadcast wide-shot — fills landscape desktops
const DESIGN_H = 660; // field box the % coords assume (2:1; bench rides on the field)
// Below this, the wide field would be width-bound and float in a tall portrait
// viewport, so we fall back to the grouped list. Kept in sync with the
// field-first overlay breakpoint in diamond.css so the two never disagree.
const NARROW_BREAKPOINT = 860;

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
      // Fill the available box on both axes — no upper cap, so the field keeps
      // scaling up to fill ever-larger screens. Whichever axis binds first wins,
      // which keeps the field's aspect ratio intact (no distortion). The
      // transform-scaled card text is re-rasterised at the target size, so it
      // stays crisp however large the field grows.
      const fit = Math.min(width / DESIGN_W, height / DESIGN_H);
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

  return (
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

                {/* Bench — a labelled column out in right field */}
                <span
                  className="diamond__bench-label"
                  style={
                    {
                      "--x": `${BENCH_LABEL_POS.x}%`,
                      "--y": `${BENCH_LABEL_POS.y}%`,
                      "--i": FIELD_POSITIONS.length,
                    } as React.CSSProperties
                  }
                  aria-hidden="true"
                >
                  Bench
                </span>
                {BENCH_POSITIONS.map((pos, i) => (
                  <div
                    key={pos.key}
                    className="diamond__slot"
                    style={
                      {
                        "--x": `${pos.x}%`,
                        "--y": `${pos.y}%`,
                        "--i": FIELD_POSITIONS.length + 1 + i,
                      } as React.CSSProperties
                    }
                    data-active={expandedKey === pos.key || undefined}
                  >
                    <PlayerCard
                      position={pos}
                      player={league?.[pos.key] ?? null}
                      expanded={expandedKey === pos.key}
                      onToggle={() => toggleCard(pos.key)}
                      index={FIELD_POSITIONS.length + 1 + i}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
    </div>
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
          {[...FIELD_POSITIONS, ...BENCH_POSITIONS].map((pos) => (
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

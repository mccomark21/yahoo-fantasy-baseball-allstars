import { useState } from "react";
import type { AllStar } from "../data";
import { formatStat, type PositionSpec } from "../constants/positions";

interface Props {
  position: PositionSpec;
  player: AllStar | null;
  expanded: boolean;
  onToggle: () => void;
  /** stagger index for the entrance choreography */
  index: number;
  variant?: "field" | "bench";
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

function LeaderMark() {
  return (
    <span className="player-card__leader" title="League leader">
      <svg viewBox="0 0 24 24" aria-hidden="true" width="13" height="13">
        <path
          fill="currentColor"
          d="M5 19h14l1.5-9-4.8 3.3L12 6l-3.7 7.3L3.5 10 5 19Z"
        />
      </svg>
      <span className="visually-hidden">League leader</span>
    </span>
  );
}

export default function PlayerCard({
  position,
  player,
  expanded,
  onToggle,
  index,
  variant = "field",
}: Props) {
  const [imgFailed, setImgFailed] = useState(false);
  const [logoFailed, setLogoFailed] = useState(false);

  // Ghost: no player rostered at this slot.
  if (!player) {
    return (
      <div
        className="player-card player-card--ghost"
        data-variant={variant}
        style={{ "--i": index } as React.CSSProperties}
      >
        <span className="player-card__pos player-card__pos--ghost">
          {position.label}
        </span>
        <span className="player-card__ghost-label">Position not filled</span>
      </div>
    );
  }

  const statEntries = Object.entries(player.stats).slice(0, 4);
  const statsId = `stats-${variant}-${position.key}`;

  return (
    <div
      className="player-card"
      data-variant={variant}
      data-expanded={expanded || undefined}
      data-leader={player.is_leader || undefined}
      style={{ "--i": index } as React.CSSProperties}
    >
      <button
        type="button"
        className="player-card__toggle"
        aria-expanded={expanded}
        aria-controls={statsId}
        onClick={onToggle}
      >
        <span className="player-card__avatar">
          {player.headshot_url && !imgFailed ? (
            <img
              src={player.headshot_url}
              alt=""
              loading="lazy"
              decoding="async"
              onError={() => setImgFailed(true)}
            />
          ) : (
            <span className="player-card__initials" aria-hidden="true">
              {initials(player.player_name)}
            </span>
          )}
          <span className="player-card__pos">{position.label}</span>
        </span>

        <span className="player-card__id">
          <span className="player-card__name">{player.player_name}</span>
          <span className="player-card__team">
            {player.mlb_team_logo_url && !logoFailed ? (
              <img
                className="player-card__logo"
                src={player.mlb_team_logo_url}
                alt=""
                loading="lazy"
                decoding="async"
                onError={() => setLogoFailed(true)}
              />
            ) : (
              <span className="player-card__mlb">{player.mlb_team}</span>
            )}
            <span className="player-card__fantasy">{player.fantasy_team}</span>
          </span>
        </span>

        {player.is_leader && <LeaderMark />}
        <svg
          className="player-card__chevron"
          viewBox="0 0 24 24"
          aria-hidden="true"
          width="16"
          height="16"
        >
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m6 9 6 6 6-6"
          />
        </svg>
      </button>

      <div
        className="player-card__reveal"
        id={statsId}
        role="region"
        aria-label={`${player.player_name} season stats`}
        aria-hidden={!expanded}
      >
        <div className="player-card__stats">
          {statEntries.map(([key, value]) => (
            <span key={key} className="stat">
              <span className="stat__value mono">{formatStat(key, value)}</span>
              <span className="stat__key">{key}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

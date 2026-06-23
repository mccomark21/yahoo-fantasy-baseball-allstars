import type { League } from "../data";

interface Props {
  leagues: League[];
  activeId: string;
  onChange: (id: string) => void;
}

export default function LeagueToggle({ leagues, activeId, onChange }: Props) {
  const activeIndex = Math.max(
    0,
    leagues.findIndex((l) => l.id === activeId)
  );

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    let next = index;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (index + 1) % leagues.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp")
      next = (index - 1 + leagues.length) % leagues.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = leagues.length - 1;
    else return;
    e.preventDefault();
    onChange(leagues[next].id);
    const group = e.currentTarget.parentElement;
    (group?.querySelectorAll<HTMLButtonElement>("[role=tab]")[next])?.focus();
  }

  return (
    <div
      className="league-toggle"
      role="tablist"
      aria-label="Select league"
      style={
        {
          "--count": leagues.length,
          "--active": activeIndex,
        } as React.CSSProperties
      }
    >
      <span className="league-toggle__thumb" aria-hidden="true" />
      {leagues.map((lg, i) => {
        const active = lg.id === activeId;
        return (
          <button
            key={lg.id}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className="league-toggle__tab"
            data-active={active || undefined}
            onClick={() => onChange(lg.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {lg.name}
          </button>
        );
      })}
    </div>
  );
}

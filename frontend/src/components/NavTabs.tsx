import { VIEWS } from "../views";

interface Props {
  active: string;
  onChange: (id: string) => void;
}

export default function NavTabs({ active, onChange }: Props) {
  function focusTab(index: number) {
    const tabs = document.querySelectorAll<HTMLButtonElement>(
      ".nav-tabs [role=tab]"
    );
    tabs[index]?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % VIEWS.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + VIEWS.length) % VIEWS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = VIEWS.length - 1;
    else return;
    e.preventDefault();
    focusTab(next);
  }

  return (
    <div className="nav-tabs" role="tablist" aria-label="Views">
      {VIEWS.map((tab, i) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls="view-panel"
            tabIndex={isActive ? 0 : -1}
            className="nav-tabs__tab"
            data-active={isActive || undefined}
            data-soon={!tab.ready || undefined}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {tab.label}
            {!tab.ready && <span className="nav-tabs__soon">Soon</span>}
          </button>
        );
      })}
    </div>
  );
}

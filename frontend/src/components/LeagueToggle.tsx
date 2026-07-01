import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { League } from "../data";

interface Props {
  leagues: League[];
  activeId: string;
  onChange: (id: string) => void;
}

/* League picker — a dropdown living in the top nav. Rendered with the native
   Popover API so the menu sits in the browser's top layer and can't be clipped
   by the nav's `overflow-x: auto` scroll container. The trigger toggles the
   popover natively (`popovertarget`); we own positioning (anchored under the
   trigger, kept on-screen), roving focus, and listbox keyboard semantics. */
export default function LeagueToggle({ leagues, activeId, onChange }: Props) {
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  const active = leagues.find((l) => l.id === activeId) ?? leagues[0];
  const activeIndex = Math.max(
    0,
    leagues.findIndex((l) => l.id === active?.id)
  );

  // Anchor the top-layer menu under the trigger, right-aligned, clamped to the
  // viewport so a long league name never pushes it off-screen.
  const position = useCallback(() => {
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger || !menu) return;
    const r = trigger.getBoundingClientRect();
    menu.style.minWidth = `${r.width}px`;
    menu.style.top = `${Math.round(r.bottom + 6)}px`;
    const mw = menu.offsetWidth;
    const left = Math.min(
      Math.max(8, r.right - mw),
      window.innerWidth - mw - 8
    );
    menu.style.left = `${Math.round(left)}px`;
  }, []);

  // Mirror the popover's open/close into React state, and reposition + focus
  // the active option each time it opens.
  useEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const onToggle = (e: Event) => {
      const isOpen = (e as Event & { newState?: string }).newState === "open";
      setOpen(isOpen);
      if (isOpen) {
        position();
        menu
          .querySelectorAll<HTMLButtonElement>("[role=option]")
          [activeIndex]?.focus();
      } else if (menu.contains(document.activeElement)) {
        // Closed via keyboard/selection (focus was inside) — hand focus back to
        // the trigger. On an outside-click dismiss we leave focus where it landed.
        triggerRef.current?.focus();
      }
    };
    menu.addEventListener("toggle", onToggle);
    return () => menu.removeEventListener("toggle", onToggle);
  }, [position, activeIndex]);

  // Keep the menu anchored while open if the layout shifts underneath it.
  useEffect(() => {
    if (!open) return;
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
  }, [open, position]);

  function select(id: string) {
    onChange(id);
    menuRef.current?.hidePopover();
  }

  function onOptionKeyDown(e: React.KeyboardEvent, index: number) {
    const options = menuRef.current?.querySelectorAll<HTMLButtonElement>(
      "[role=option]"
    );
    if (!options) return;
    let next = index;
    if (e.key === "ArrowDown") next = (index + 1) % leagues.length;
    else if (e.key === "ArrowUp") next = (index - 1 + leagues.length) % leagues.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = leagues.length - 1;
    else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(leagues[index].id);
      return;
    } else return;
    e.preventDefault();
    options[next]?.focus();
  }

  if (!active) return null;

  return (
    <div className="league-picker">
      <button
        ref={triggerRef}
        type="button"
        className="league-picker__trigger"
        // @ts-expect-error — popovertarget is valid HTML, not yet in React's types
        popovertarget={menuId}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="league-picker__eyebrow">League</span>
        <span className="league-picker__name">{active.name}</span>
        <svg
          className="league-picker__chevron"
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
        ref={menuRef}
        id={menuId}
        // @ts-expect-error — popover is valid HTML, not yet in React's types
        popover="auto"
        className="league-picker__menu"
        role="listbox"
        aria-label="Select league"
      >
        {leagues.map((lg, i) => {
          const isActive = lg.id === active.id;
          return (
            <button
              key={lg.id}
              type="button"
              role="option"
              aria-selected={isActive}
              tabIndex={-1}
              className="league-picker__option"
              data-active={isActive || undefined}
              onClick={() => select(lg.id)}
              onKeyDown={(e) => onOptionKeyDown(e, i)}
            >
              <span className="league-picker__check" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="15" height="15">
                  <path
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="m5 12 5 5 9-11"
                  />
                </svg>
              </span>
              {lg.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

# Shape Brief: DiamondView

**Status:** Confirmed

---

## 1. Feature Summary

The All-Stars view is the homepage — a full-viewport CSS/SVG baseball diamond with 12 player cards floating at their field positions. It's the emotional anchor of the entire app: a night-game trophy case. Users arrive to see who earned the all-star slot at each position this season, switch between two leagues, and tap cards to reveal stats.

---

## 2. Primary User Action

Arrive → see the lineup → tap a card to reveal that player's season stats. Secondary: toggle between two leagues with the pill switcher.

---

## 3. Design Direction

**Color strategy:** Full palette
**Scene:** *"Stadium lights blazing over CSS-drawn turf, 9pm, friend group catching up on who's winning."*
**Mode:** Dark — near-pure-black bg, Sport Crimson for position badges and active toggle, Stadium Amber for "best" indicators, near-white ink for player names.

**Choreographed entrance (fires once on mount):**
1. Field geometry fades in (300ms)
2. Stadium light bloom rises from arc-light positions (400ms, slight blur bloom)
3. Player cards stagger in from each position coordinate (50ms delay per card, ease-out-quint, ~600ms total)

**`prefers-reduced-motion`:** crossfade only — no stagger, no bloom.

**References:** MLB The Show (card craftsmanship) · ESPN FC (dark broadcast production) · Nike (condensed sport type)

---

## 4. Scope

- **Fidelity:** Production-ready, shipped code
- **Breadth:** One view — DiamondView (also establishes design-system tokens for the rest of the app)
- **Interactivity:** Full — league toggle, card expand, keyboard nav, all states
- **Time intent:** Polish until it ships

---

## 5. Layout Strategy

- Full-viewport container
- SVG field occupies ~65% of viewport height, centered
- **Top zone:** Nav tabs (All-Stars / Positional Races / Team Records / Player Records) + league toggle pill beneath them
- **Field zone:** SVG diamond with 9 field positions (C, 1B, 2B, 3B, SS, LF, CF, RF, SP on the mound)
- **Bench strip:** 3-card flex row below the field for UTIL, DH, RP
- **Mobile (< 640px):** Diamond scales proportionally via `transform: scale()`. Below 480px / portrait: switch to a vertical grouped list (Infield / Outfield / Pitching / Bench)

---

## 6. Key States

| State | What the user sees |
|---|---|
| Loading | Pulsing skeleton cards at each position |
| Default | 12 cards on the field, league 1 active |
| Card collapsed | Headshot, name, position badge, fantasy team |
| Card expanded | Same + stats badges (dynamic from `stats` object, max 4) |
| League switch | Cards fade out → new league's cards fade in |
| Error | Centered message + retry button |
| No player at position | Ghost card: "Position not filled" |

---

## 7. Interaction Model

- **Card tap:** Expands to show stats badges. Same tap collapses. Keyboard: Enter/Space. Escape closes.
- **League toggle:** `role="tablist"` / `role="tab"`. Switches data; cards animate out/in.
- **Entrance animation:** Fires once on mount, not on re-render or league switch.
- **Nav tabs:** `role="tablist"`, `aria-selected`, keyboard arrow navigation.

---

## 8. Content Requirements

- **Position coordinates:** Hardcoded `POSITIONS` constant — maps abbreviation → `{x, y}` as % of field dimensions (C, 1B, 2B, 3B, SS, LF, CF, RF, SP)
- **Player data:** `player_name`, `position`, `fantasy_team`, `headshot_url`, `mlb_team_logo_url`, `stats` object
- **League names:** From `leagues.json`
- **Stats display:** Dynamic — show all keys from `stats` object, max 4. Pitchers show ERA/WHIP, hitters show HR/AVG/RBI — no hardcoded list
- **`updated_at` timestamp:** Small muted text at bottom of view
- **Data path:** `/data/all_stars.json` (served via `public/data` symlink)
- **Empty / loading / error copy:** To be written during build

---

## 9. Recommended References

- `animate.md` — entrance choreography, card expand
- `colorize.md` — dark mode palette application
- `layout.md` — SVG coordinate system, responsive scaling

---

## 10. Decisions Made

- **Card click:** Expand inline (not navigate away, not tooltip-only)
- **UTIL / DH / RP:** Bench strip below the diamond (not squeezed onto the field)
- **Field background:** CSS/SVG drawn — no photo dependency
- **Expanded stats:** Dynamic from `stats` object keys, max 4 displayed

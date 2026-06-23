<!-- SEED: re-run /impeccable document once there's code to capture the actual tokens and components. -->

---
name: Yahoo Fantasy Baseball All-Stars
description: Night-game celebration of two fantasy leagues, past and present
---

# Design System: Yahoo Fantasy Baseball All-Stars

## 1. Overview

**Creative North Star: "The Night Game Broadcast"**

You are watching a night game from a premium broadcast feed — not browsing a sports portal. The stadium is dark, the field blazes under white arc lights, and every element on screen feels like a directed shot from a broadcast director who respects their audience. The diamond is the opening shot. The records tables are the press box. Everything lives in the same stadium; nothing resets to a generic dashboard when you navigate.

This system draws from three references with precision: **MLB The Show**'s player-card craftsmanship (floating, collectible, identity-first), **ESPN FC**'s dark broadcast production polish (clean type on dark, one thing per view), and **Nike**'s sport typesetting confidence (condensed, commanding, unapologetic). It explicitly rejects the cluttered portal mentality of ESPN.com and Yahoo Sports — no competing widgets, no nav-level noise, no below-the-fold grabs. Each of the four views has one job and does it without apology.

Motion is choreographed. The All-Stars diamond entrance is a broadcast cut: the field resolves first, then the stadium lights come on, then the player cards stagger in from their positions. First load is a moment. Subsequent navigation is smooth and responsive. `prefers-reduced-motion` receives a crossfade equivalent — the content is always visible; the choreography is the enhancement.

**Key Characteristics:**
- Dark by default, lit from within — atmosphere through depth, not glow
- Full palette with four deliberate color roles; discipline enforced by a named rule
- Condensed bold type reads like a scoreboard; tabular mono locks stat columns
- Choreographed entrance motion makes first-load feel earned
- WCAG AA throughout — dark-mode contrast is designed, not assumed

## 2. Colors: The Stadium Palette

Four roles. The palette earns its fullness by assigning each role a clear territory — no freelancing.

> **Resolved tokens** live in `frontend/src/styles/tokens.css` (OKLCH). Values below are the committed source of truth. Contrast verified: ink 18:1, muted 8.7:1, all UI roles ≥4.2:1 against Night Field.

### Primary
- **Sport Crimson** `oklch(0.585 0.213 25)` · active/glow `oklch(0.64 0.205 27)`: Baseball red, vivid — the color of the stitching, the cap logo, the official MLB brand. Used for position badges, the active state on the league toggle, record-table row highlights when a stat is sorted. Never fills large surfaces. Its rarity makes it read as intent.

### Secondary
- **Stadium Amber** `oklch(0.82 0.145 78)` · deep `oklch(0.7 0.135 70)`: Championship gold — the color stadium floodlights cast on trophy metal. Reserved for all-time record indicators ("best ever" callouts, single-season crowns, win-streak markers). Appears no more than 5-8% of any view. When it shows up, it means something.

### Neutral
- **Night Field (bg)** `oklch(0.145 0.006 255)`: Near-pure black, the stadium floor. The faintest cool whisper for cohesion; reads as neutral. The atmosphere is carried by the brand colors and the layers above, not the background.
- **Press Box (surface)** `oklch(0.198 0.011 255)`: Dark surface, one step above Night Field. Used for the nav bar, the league toggle track, containers.
- **High Surface** `oklch(0.262 0.014 255)`: Player cards and record tiles. One more step up from Press Box. Used at ~88% opacity so the field reads through (see Field Always Shows Rule).
- **Floodlight (ink)** `oklch(0.972 0.008 90)`: Near-white with a breath of warmth, like stadium arc output. All body text and primary headings. 18:1 against Night Field.
- **Scorecard (muted)** `oklch(0.745 0.012 255)` · dim `oklch(0.6 0.012 255)`: Cool mid-gray for secondary text — stat keys, fantasy team labels, timestamps. 8.7:1 against Night Field (exceeds the ≥3:1 target; clears AA body text).

### Named Rules
**The Full-Field Rule.** Four color roles: crimson for intent, amber for records, dark neutrals for atmosphere, near-white for content. No decorative fifth color. If it doesn't map to one of these four roles, it doesn't belong in the palette.

**The Rarity Rule.** Sport Crimson covers ≤20% of any view; Stadium Amber covers ≤8%. Their power is proportional to their scarcity. The moment either bleeds into backgrounds or fills large table rows, the palette reads like a gaming app.

## 3. Typography: The Scoreboard Stack

**Display Font:** **Saira Condensed** (700/800) — condensed, technical-sport, scoreboard at distance. `--font-display`
**Body / UI Font:** **Hanken Grotesk** (400–700) — humanist sans, readable, neutral. Proportion + personality contrast against the condensed display. `--font-body`
**Stats Font:** **Spline Sans Mono** (400–600) with `font-variant-numeric: tabular-nums lining-nums` — number columns never shift. `--font-mono`

**Character:** The heading stack reads like a scoreboard seen from the upper deck — compressed, tall, built for information density at scale. Stats use a monospaced face with tabular lining figures so HR columns don't jitter when values change and two-digit numbers don't push single-digit ones sideways. Body copy is clean and unintrusive; it never competes with the data.

### Hierarchy
- **Display** (condensed, heavy — 700+, `clamp(2rem, 6vw, 4.5rem)`, line-height ~0.95–1.0): Player names on the diamond card, section titles on the homepage. Uppercase or title case. Letter-spacing ≥ -0.03em floor; never tighter.
- **Headline** (condensed, bold — 600–700, ~1.4rem–1.8rem, line-height ~1.1): Position labels on the diamond, table section headers ("Positional Races — SS"), record category titles. Uppercase encouraged.
- **Title** (regular or semibold, ~1rem–1.2rem, line-height ~1.3): Fantasy team names, league names, navigation tab labels. Title case.
- **Body** (regular — 400, ~0.875rem–1rem, line-height ~1.5–1.6): Stat descriptions, metadata, timestamps, supporting copy. Max 65–75ch line length. `text-wrap: pretty` on multi-line instances.
- **Label** (medium — 500, ~0.7rem–0.8rem, uppercase, letter-spacing 0.06–0.1em): Position badge text (C, SS, 1B), stat column headers (HR, AVG, RBI), chip/toggle labels.
- **Stats / Mono** (tabular mono, regular — 400–500, `font-variant-numeric: tabular-nums lining-nums`, ~0.875rem–1rem): All numeric stat values in leaderboards, records, and player cards. Columns must align vertically.

### Named Rules
**The Scoreboard Rule.** All primary display and headline type is condensed. Wide-tracking thin serifs, light-weight display fonts, and decorative script are prohibited — this is a stadium, not a magazine spread.

**The Tabular Lock Rule.** Every column of numbers uses `font-variant-numeric: tabular-nums lining-nums`. A sort operation must never cause number columns to reflow. If a font doesn't support tabular figures, it's the wrong choice for the stats font.

## 4. Elevation

Layered — three surfaces in depth. Depth is achieved through lightness steps in the neutral ramp, not drop shadows. Dark-mode shadows are almost invisible at low opacity; tonal layering communicates more clearly.

The field (Night Field bg) is always at the bottom. Surface (Press Box) lifts slightly above it for containers and the nav. High Surface lifts again for player cards and record tiles — they visibly float above the view beneath. Player cards on the diamond use a semi-transparent High Surface so the baseball field reads through; solid-black cards would erase the depth that defines the view.

Interactive states use a further lift: hover on a leaderboard row elevates it to High Surface to indicate focus without triggering a full card expand.

**Shadow Vocabulary:** Used sparingly and purposefully, not decoratively.
- **Card Ambient** `--shadow-card: 0 14px 34px -12px oklch(0 0 0 / 0.7), 0 4px 10px -4px oklch(0 0 0 / 0.6)`: Diffuse shadow beneath player cards. Makes them float without a heavy border. Dark-on-dark needs higher opacity than light-mode shadows.
- **Glow / Light Cue** `--glow-crimson` / `--glow-amber`: a 1px colored ring + low-spread glow for the active league toggle (crimson) and league-leader marks (amber). Broadcast spotlight, not glassmorphism.

### Named Rules
**The Field Always Shows Rule.** Player cards, overlays, and modal surfaces must have semi-transparent backgrounds (`High Surface` at ~85–90% opacity). The stadium floor is part of the design. Never fill a floating element with opaque Night Field; you lose the depth that makes the diamond view feel spatial.

**The No-Decorative-Glow Rule.** Glows are reserved for active state indicators and "best ever" record callouts — two use cases, nowhere else. Ambient decorative glows on cards, section headers, or background treatments are prohibited. Glassmorphism as default is explicitly banned.

## 5. Components

`[Components to be documented after implementation. Re-run /impeccable document to extract real tokens and generate component specs for: PlayerCard, DiamondView, LeagueToggle, PositionBadge, StatRow, RecordTile, NavTabs, SortPicker.]`

## 6. Do's and Don'ts

### Do:
- **Do** treat dark neutrals as three distinct architectural steps: Night Field (bg), Press Box (surface), High Surface (cards). The depth ramp is how spatial hierarchy is expressed.
- **Do** use condensed type for all Display and Headline roles — the stadium reads from a distance, not up close.
- **Do** make the All-Stars diamond entrance feel like a broadcast cut: field → stadium lights → player cards staggering in from their positions. The choreography is the first impression.
- **Do** use tabular lining figures (`font-variant-numeric: tabular-nums lining-nums`) on every numeric column in every leaderboard and records table. Numbers must lock in columns.
- **Do** reserve Stadium Amber strictly for all-time records and "best ever" callouts. Its meaning is "this is exceptional." Dilute it and it stops communicating.
- **Do** write a `prefers-reduced-motion` path for every animation: the content must be visible at full opacity with a crossfade or instant-transition fallback. Never gate content visibility on a class-triggered entrance animation.
- **Do** hit WCAG AA contrast for both Floodlight (ink) and Scorecard (muted) text against Night Field. Dark-mode contrast is not automatic; verify it with real values.
- **Do** make player cards semi-transparent on the diamond (≥85% opacity target). The baseball field beneath is part of the composition.

### Don't:
- **Don't** reproduce the cluttered portal feel of ESPN.com or Yahoo Sports — no competing widgets, no sidebar of tangential links, no persistent ad units. Each view has one job; everything else is noise.
- **Don't** use sport gradients — no diagonal team-color fades, no neon gradient headlines, no `background-clip: text` gradient fills. This is broadcast production, not a gaming app store page.
- **Don't** apply side-stripe borders (`border-left` or `border-right` wider than 1px as a colored accent) to table rows, cards, or callouts. Use background tint or elevated surface instead.
- **Don't** let the Positional Races, Team Records, or Player Records views feel like generic SaaS dashboards. Tables must carry the same dark broadcast language as the diamond — same type ramp, same surface layers, same palette.
- **Don't** use DraftKings / FanDuel UI patterns — aggressive green or orange CTAs, pulsing "live" indicators, urgency signals. The app celebrates past and present performance; it does not drive action.
- **Don't** fill player cards or record tiles with opaque Night Field — the field and surface depth beneath them must be visible. Solid opaque overlays flatten what the layered system builds.
- **Don't** animate CSS layout properties (width, height, top, left, grid-template-columns) during the diamond entrance or any transition. Transform and opacity only. Layout animations cause reflow jank and fail on low-power devices.
- **Don't** use a wide-tracking eyebrow label ("ALL STARS • 2025") above every section. One deliberate use of uppercase label type per view; repeated eyebrows across sections is AI scaffolding, not design voice.
- **Don't** use nested cards — the player card is already a high-surface element floating above the field. Putting another card-shaped container inside it collapses the depth model.

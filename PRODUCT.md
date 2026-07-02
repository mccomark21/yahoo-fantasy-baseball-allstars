# Product

## Register

brand

## Users

A private friend group — the two fantasy baseball leagues' members. They open this app to see who's on top, check the all-star lineup, and settle arguments about all-time records. The vibe is a league group chat, not a front-page sports portal: casual, competitive, and personal. The All-Stars diamond is the trophy case; the inner views are the stat sheets people pull up mid-argument.

## Product Purpose

A celebration of fantasy baseball performance across two Yahoo leagues — past and present. The app surfaces the season's best players on an immersive baseball diamond, then backs it up with ranked positional races and an all-time records archive. It runs automatically (daily GitHub Actions refresh) and hosts as a static site on GitHub Pages. There's no backend, no auth wall, no friction — you open it and you're in the stadium.

## Brand Personality

Slick, modern, sport. This feels like a real broadcast product built for your league. Stadium lights, dark atmosphere, sharp typography. Competitive energy without gambling-app aggression. It's ESPN Films, not ESPN.com.

## Anti-references

- **ESPN.com / Yahoo Sports**: cluttered portal energy — ads, endless nav, busyness as a signal of importance. This app has one job per view; it never shouts.
- **Generic SaaS dashboard**: sidebar-nav, card-grid, admin-panel feel. The records tables must feel like they belong in the same stadium as the diamond, not like a JIRA report.
- **DraftKings / FanDuel**: aggressive CTAs, neon betting UI, friction-as-a-product. No gambling-app patterns.

## Design Principles

1. **The diamond sets the register.** The All-Stars view is the emotional anchor. Every design decision — color, type, motion — should be consistent with something you'd see in a stadium broadcast. The inner views inherit that atmosphere; they don't reset to a generic dashboard.
2. **One thing per view.** No nav clutter, no sidebar, no competing calls-to-action. Each of the four views has one job and does it cleanly.
3. **Data is sport, not spreadsheet.** Leaderboards and records tables carry the same visual language as the diamond — dark background, strong typography, considered color. Stats feel like box scores, not Excel rows.
4. **Personal without being precious.** This is a friend group's trophy case. It should feel high-quality, but not so austere that it loses the fun of fantasy baseball. Player headshots, team names, league history — the human details are the point.
5. **Accessibility is non-negotiable.** Full WCAG AA compliance. Dark stadium aesthetic must still hit contrast minimums; reduced-motion users get equivalent experiences without degradation.

## Data & History

The app celebrates both the current season and league history, but the two are not the same shape — Yahoo's API only serves rich data for the live season, so the historical archive is deliberately scoped.

- **How far back we go.** For the **player-facing views** — All-Stars, Positional Races, and Player Records — history runs back to **2021** only. Those views need to reach individual players, and older players are mostly retired and unreachable through Yahoo's current game; each league's own earliest reachable season may be later still (e.g. one league starts at 2022) when coverage falls short — see the gate below.
- **Team Records reach back further.** Team Records are the exception: they're built from team-level season totals and matchup results, which come straight from Yahoo, never touch individual players, and — unlike per-player stats — **survive Yahoo's game archival**. So Team Records go back as far as each league's history is reachable at all (one league to **2010**, the other to ~**2011**), well past the 2021 wall the player views hit. This is deliberate, not a bug: each records view labels the exact span of seasons it draws from, so "all-time" never quietly means different things in different views.
- **What a historical season contains.** Season **totals only** — no week-by-week historical splits. Yahoo serves no true per-week per-player MLB stats at all (only cumulative-season and single-day coverage), and for past seasons not even that, so history is season totals exclusively.
- **Current-season weekly is counting stats only.** For the live season we reconstruct real weekly per-player numbers by summing each week's days — but only for **counting** stats (R, HR, RBI, SB, W, SV, K, and the like). **Rate** stats (AVG, OBP, ERA, WHIP, K/9…) can't be summed across days and their components aren't tracked, so they're shown at the season level only, never weekly. A weekly leaderboard therefore covers counting categories; rate categories live in season totals.
- **The coverage gate.** A past season is only kept if we can reach stats for enough of its end-of-season-rostered players. Coverage is **roster-week-weighted** — each player counts in proportion to how much of the season they were actually rostered (sampled across the year), so a September bench add who later retired doesn't sink a season the way a season-long core player would. A season is **kept only at ≥75% weighted coverage**; below that it is dropped entirely rather than shown half-empty.
- **Retired players.** Players who have left the league entirely are unreachable through Yahoo's current game and are **omitted from the totals but named and counted** in each season's `coverage` block (a "_N players unavailable_" label), so the gaps are honest and visible rather than silently missing.

## Accessibility & Inclusion

WCAG AA compliance throughout. Dark-mode palette must be designed to hit 4.5:1 body text contrast, not just pass superficially. All dynamic content updates (league switcher, sort controls) must be announced to screen readers. Player cards on the diamond must be keyboard-reachable. Every animation must have a `prefers-reduced-motion` alternative that preserves the content without the motion.

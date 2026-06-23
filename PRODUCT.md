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

## Accessibility & Inclusion

WCAG AA compliance throughout. Dark-mode palette must be designed to hit 4.5:1 body text contrast, not just pass superficially. All dynamic content updates (league switcher, sort controls) must be announced to screen readers. Player cards on the diamond must be keyboard-reachable. Every animation must have a `prefers-reduced-motion` alternative that preserves the content without the motion.

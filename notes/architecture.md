# 🏗️ Architecture

Notes on how the app is built — data flow, structure, tech choices, refactors, and tradeoffs. Capture design thoughts and "we should restructure X" ideas here.

**How to use:** Copy the template below to the top of the "Entries" list and fill in what you can. Don't sweat blank fields — capture the thought while it's fresh.

---

### Template (copy this)

```
## [short title]
- **Status:** ⬜ Not yet converted (add GitHub issue # once filed)
- **Date:** YYYY-MM-DD
- **Area:** (e.g. data layer / API / UI / build / infra)
- **Observation / idea:**
- **Current approach:**
- **Proposed approach:**
- **Tradeoffs / risks:**
- **Notes:**
```

---

## Entries

<!-- Add new architecture notes below, newest first -->
## Convert from a single github page to a github page per league
- **Status:** ✅ Converted → #25
- **Date:** 2026-06-30
- **Area:** build
- **Observation / idea:** Currently users have to select which league they're apart of to view all stars
- **Current approach:** we have a toggle to switch between leagues
- **Proposed approach:** I'd like to have two different URLs or github pages. One for each league. The goal would be for me to be able to share one URL to my friends in league A and a different one to my friends in league B.
- **Tradeoffs / risks:**
- **Notes:**

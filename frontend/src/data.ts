/* Typed fetch helpers for the committed JSON data files.
   Data is served from <base>/data/* via the public/data symlink in dev and
   the copied data/ directory in the production build. */

export interface PlayerStats {
  [stat: string]: number;
}

export interface AllStar {
  player_name: string;
  position: string;
  mlb_team: string;
  mlb_team_id?: number;
  mlb_team_logo_url?: string;
  headshot_url?: string;
  fantasy_team: string;
  is_leader?: boolean;
  stats: PlayerStats;
}

/** One league's roster, grouped into the sections the field view renders
    (issue #27): the on-field starting lineup (fielders keyed by slot — C, 1B …
    SS, OF1, OF2, OF3, UTIL), plus reserve/pitching sections as ranked lists. */
export interface LeagueAllStars {
  lineup: Record<string, AllStar>;
  bench: AllStar[];
  rotation: AllStar[];
  bullpen: AllStar[];
}

export interface AllStarsData {
  season: number;
  updated_at: string;
  leagues: Record<string, LeagueAllStars>;
}

export interface League {
  id: string;
  name: string;
  season: number;
  /** Yahoo scoring format: "head" (categories) | "headone" (one win/week). */
  scoring_type?: string;
  seasons: number[];
}

export interface LeaguesData {
  season: number;
  updated_at: string;
  leagues: League[];
}

/* --- Positional Races (positional_races.json) ------------------------------
   Full ranked field per position, per league. Same player shape as AllStar
   plus a 1-based `rank` and the composite `score` used to order the race. */

export interface RaceEntry {
  rank: number;
  player_name: string;
  position: string;
  mlb_team: string;
  mlb_team_id?: number;
  mlb_team_logo_url?: string;
  headshot_url?: string;
  fantasy_team: string;
  stats: PlayerStats;
  score: number;
}

/** position abbreviation (C, 1B, SS, …) → ranked players competing for it. */
export type PositionRaces = Record<string, RaceEntry[]>;

export interface PositionalRacesData {
  season: number;
  updated_at: string;
  leagues: Record<string, PositionRaces>;
}

/* --- Team Records (records_teams.json) -------------------------------------
   Per league, top-5 leaderboards of all-time team-seasons: the best and worst
   season W-L-T (category aggregate for "head" leagues, weekly for "headone"),
   plus one leaderboard per counting scoring category. The unit is a team-season,
   so the same franchise may appear more than once within a board. */

/** One team-season's season-long W-L-T record. */
export interface TeamSeasonRecord {
  fantasy_team: string;
  season: number;
  wins: number;
  losses: number;
  ties: number;
}

/** One team-season's total for a counting stat (e.g. team HR that season). */
export interface TeamStatEntry {
  fantasy_team: string;
  value: number;
  season: number;
}

/** A top-5 leaderboard for one counting stat. `stat` is the abbr (chip label);
    `display` is the friendly name ("Home Runs") for captions. */
export interface TeamStatLeaderboard {
  stat: string;
  display: string;
  entries: TeamStatEntry[];
}

export interface TeamRecords {
  /** "head" (categories) | "headone" (one win/week) — how W-L-T was computed. */
  scoring_type: string;
  best_season: TeamSeasonRecord[];
  worst_season: TeamSeasonRecord[];
  season_stats: TeamStatLeaderboard[];
}

export interface TeamRecordsData {
  updated_at: string;
  leagues: Record<string, TeamRecords>;
}

/* --- Player Records (records_players.json) ---------------------------------
   All-time top-10 individual leaderboards per tracked stat: best single week and
   best season total (issue #30). Mirrors the Team Records leaderboard shape. The
   unit is a player-season (or player-week), so the same player may appear more
   than once on a board — different seasons are distinct marks. `week` is present
   only on single-week entries. */

/** One player-season (or player-week) mark for a stat. */
export interface PlayerStatEntry {
  value: number;
  player_name: string;
  fantasy_team: string;
  season: number;
  /** present only on single-week entries */
  week?: number;
}

/** A top-10 leaderboard for one stat. `stat` is the abbr (chip label);
    `display` is the friendly name ("Home Runs") for captions. Boards arrive
    ordered batting → pitching; `group` is "batting" | "pitching". */
export interface PlayerStatLeaderboard {
  stat: string;
  display: string;
  group: string;
  entries: PlayerStatEntry[];
}

export interface PlayerRecords {
  single_week: PlayerStatLeaderboard[];
  season_total: PlayerStatLeaderboard[];
}

export interface PlayerRecordsData {
  updated_at: string;
  leagues: Record<string, PlayerRecords>;
}

/* --- Raw per-season files (data/{leagueId}/{season}/*.json) -----------------
   The unaggregated source the browser can re-filter and re-sort. Stat values
   are keyed by Yahoo numeric stat_id; map them through stat_categories. */

export interface StatCategory {
  stat_id: string;
  name: string;
  display_name: string;
  abbr: string;
  group: string; // "batting" | "pitching"
  position_type: string; // "B" | "P"
  sort_order: string;
  enabled: boolean;
  is_only_display_stat: boolean;
}

export interface StatCategoriesFile {
  league_id: string;
  game_key: string;
  season: number;
  stats: StatCategory[];
}

export interface RosterPlayer {
  player_key: string;
  player_id: string;
  name: string;
  mlb_team: string;
  mlb_team_full: string;
  headshot_url: string;
  image_url: string;
  eligible_positions: string[];
  primary_position: string;
  selected_position: string;
  status: string;
}

export interface RosterTeam {
  team_key: string;
  team_id: string;
  name: string;
  players: RosterPlayer[];
}

export interface RostersFile {
  league_id: string;
  game_key: string;
  season: number;
  week_label: string;
  teams: RosterTeam[];
}

/** stat_id → value. Raw Yahoo season totals arrive as strings ("28", ".291",
    "-"); reconstructed weekly values are numbers. Hence the union. */
export type StatLine = Record<string, string | number>;

export interface PlayerStatsFile {
  league_id: string;
  game_key: string;
  season: number;
  teams: Record<string, string>; // team_id → fantasy team name
  season_totals: Record<string, Record<string, StatLine>>; // teamId → playerKey → stats
  weekly: Record<string, Record<string, Record<string, StatLine>>>; // teamId → week → playerKey → stats
}

export interface MatchupTeam {
  team_key: string;
  team_id: string;
  name: string;
  points: number;
}

export interface Matchup {
  week: number;
  is_playoffs: boolean;
  is_consolation: boolean;
  is_tied: boolean;
  winner_team_key: string | null;
  teams: MatchupTeam[];
}

export interface MatchupsFile {
  league_id: string;
  game_key: string;
  season: number;
  matchups: Matchup[];
}

export interface SeasonData {
  stat_categories: StatCategoriesFile;
  rosters: RostersFile;
  player_stats: PlayerStatsFile;
  matchups: MatchupsFile;
}

const dataUrl = (file: string) => `${import.meta.env.BASE_URL}data/${file}`;

async function loadJson<T>(file: string): Promise<T> {
  const res = await fetch(dataUrl(file), { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to load ${file} (${res.status})`);
  }
  return (await res.json()) as T;
}

/* Defense-in-depth for non-finite numbers in the raw player_stats files (a
   pitcher's ERA is Infinity on zero innings). The pipeline now writes these as
   `null` at the source (scripts/common.py `dump_json`), so the files are valid
   JSON — but stale/cached copies or a future writer regression could still emit
   bare `Infinity` / `-Infinity` / `NaN` tokens, which are valid JS yet illegal
   JSON and make `res.json()` throw. Parse the text ourselves, coercing those
   bare numeric tokens to null. The regex only touches tokens in value position
   (after `:`, `[`, or `,`), so a quoted string like a team named "Infinity" is
   left untouched. */
async function loadJsonLenient<T>(file: string): Promise<T> {
  const res = await fetch(dataUrl(file), { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to load ${file} (${res.status})`);
  }
  const text = await res.text();
  const safe = text.replace(/([:[,]\s*)(-?Infinity|NaN)\b/g, "$1null");
  return JSON.parse(safe) as T;
}

export const loadLeagues = () => loadJson<LeaguesData>("leagues.json");
/** Stat-category metadata for one league-season — drives sort labels and the
    higher-vs-lower-is-better direction in the Positional Races sort picker. */
export const loadStatCategories = (leagueId: string, season: number | string) =>
  loadJson<StatCategoriesFile>(`${leagueId}/${season}/stat_categories.json`);
export const loadAllStars = () => loadJson<AllStarsData>("all_stars.json");
export const loadPositionalRaces = () =>
  loadJson<PositionalRacesData>("positional_races.json");
export const loadTeamRecords = () =>
  loadJson<TeamRecordsData>("records_teams.json");
export const loadPlayerRecords = () =>
  loadJson<PlayerRecordsData>("records_players.json");

/** Load the four raw files for one league-season in parallel. */
export async function loadSeasonData(
  leagueId: string,
  season: number | string
): Promise<SeasonData> {
  const dir = `${leagueId}/${season}`;
  const [stat_categories, rosters, player_stats, matchups] = await Promise.all([
    loadJson<StatCategoriesFile>(`${dir}/stat_categories.json`),
    loadJson<RostersFile>(`${dir}/rosters.json`),
    loadJsonLenient<PlayerStatsFile>(`${dir}/player_stats.json`),
    loadJson<MatchupsFile>(`${dir}/matchups.json`),
  ]);
  return { stat_categories, rosters, player_stats, matchups };
}

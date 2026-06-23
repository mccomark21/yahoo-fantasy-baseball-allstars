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

export type LeagueAllStars = Record<string, AllStar>;

export interface AllStarsData {
  season: number;
  updated_at: string;
  leagues: Record<string, LeagueAllStars>;
}

export interface League {
  id: string;
  name: string;
  season: number;
  seasons: number[];
}

export interface LeaguesData {
  season: number;
  updated_at: string;
  leagues: League[];
}

const dataUrl = (file: string) => `${import.meta.env.BASE_URL}data/${file}`;

async function loadJson<T>(file: string): Promise<T> {
  const res = await fetch(dataUrl(file), { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to load ${file} (${res.status})`);
  }
  return (await res.json()) as T;
}

export const loadLeagues = () => loadJson<LeaguesData>("leagues.json");
export const loadAllStars = () => loadJson<AllStarsData>("all_stars.json");

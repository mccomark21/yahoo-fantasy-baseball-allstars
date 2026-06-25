import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { loadLeagues, type League } from "../data";

/* Leagues + the active league live above the router so the selection survives
   switching between the four views (and page reloads, via localStorage). The
   per-view data (all-stars, records, …) is still loaded by each view. */

interface ShellValue {
  leagues: League[];
  season?: number;
  leagueId: string;
  setLeague: (id: string) => void;
}

const ShellContext = createContext<ShellValue | null>(null);

const STORAGE_KEY = "asg.leagueId";

const readStored = (): string => {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
};

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [season, setSeason] = useState<number>();
  const [leagueId, setLeagueId] = useState<string>(readStored);

  useEffect(() => {
    let cancelled = false;
    loadLeagues()
      .then((data) => {
        if (cancelled) return;
        setLeagues(data.leagues);
        setSeason(data.season);
        // Validate any stored/initial id against what the league list offers.
        setLeagueId((prev) => {
          const valid = data.leagues.some((l) => l.id === prev);
          return valid ? prev : data.leagues[0]?.id ?? "";
        });
      })
      .catch(() => {
        /* Toggle simply stays hidden until leagues load; views show their own
           error state for their own data. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLeague = useCallback((id: string) => {
    setLeagueId(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* private mode / storage disabled — selection still persists in memory */
    }
  }, []);

  const value = useMemo<ShellValue>(
    () => ({ leagues, season, leagueId, setLeague }),
    [leagues, season, leagueId, setLeague]
  );

  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useShell(): ShellValue {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used within a ShellProvider");
  return ctx;
}

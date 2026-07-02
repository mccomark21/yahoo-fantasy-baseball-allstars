import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { loadLeagues, type League } from "../data";

/* The active league is pinned by the URL: each league has its own shareable
   hash route (#/<slug>), so the selection lives in the address bar rather than
   in app state — deep-linkable and toggle-free. This provider loads the league
   index once, resolves the `:leagueSlug` route param to the active league, and
   redirects to the default league if the slug is unknown. Per-view data
   (all-stars, records, …) is still loaded by each view. */

interface ShellValue {
  leagues: League[];
  season?: number;
  /** ISO timestamp of the last data refresh — feeds the top-nav freshness stamp. */
  updated?: string;
  /** Yahoo id of the league pinned by the URL slug (empty until leagues load). */
  leagueId: string;
}

const ShellContext = createContext<ShellValue | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const { leagueSlug } = useParams();
  const navigate = useNavigate();
  const [leagues, setLeagues] = useState<League[]>([]);
  const [season, setSeason] = useState<number>();
  const [updated, setUpdated] = useState<string>();
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadLeagues()
      .then((data) => {
        if (cancelled) return;
        setLeagues(data.leagues);
        setSeason(data.season);
        setUpdated(data.updated_at);
        setLoaded(true);
      })
      .catch(() => {
        /* Views show their own error state for their own data; the shell simply
           renders without a resolved league. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const active = leagues.find((l) => l.slug === leagueSlug);

  // A slug that matches no league (typo, stale link, renamed slug) falls back to
  // the first league — replace history so Back doesn't bounce off the bad URL.
  useEffect(() => {
    if (!loaded || leagues.length === 0 || active) return;
    navigate(`/${leagues[0].slug}`, { replace: true });
  }, [loaded, leagues, active, navigate]);

  const leagueId = active?.id ?? "";

  const value = useMemo<ShellValue>(
    () => ({ leagues, season, updated, leagueId }),
    [leagues, season, updated, leagueId]
  );

  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useShell(): ShellValue {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used within a ShellProvider");
  return ctx;
}

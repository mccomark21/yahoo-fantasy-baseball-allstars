import { useEffect } from "react";
import {
  HashRouter,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { ShellProvider } from "./context/ShellContext";
import { loadLeagues } from "./data";
import AppShell from "./components/AppShell";
import DiamondView from "./components/DiamondView";
import PositionalRaceView from "./components/PositionalRaceView";
import TeamRecordsView from "./components/TeamRecordsView";
import PlayerRecordsView from "./components/PlayerRecordsView";

/* The bare site (#/) carries no league. Resolve the league index and redirect
   to the first league's route so someone opening the root still lands on a real
   view. Per-league URLs (#/loc, #/sega) are the links actually shared around. */
function RootRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    let cancelled = false;
    loadLeagues()
      .then((data) => {
        if (cancelled) return;
        const slug = data.leagues[0]?.slug;
        if (slug) navigate(`/${slug}`, { replace: true });
      })
      .catch(() => {
        /* leagues.json failed to load — nothing to redirect to. */
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);
  return null;
}

/* HashRouter: GitHub Pages has no server to rewrite deep paths, so routes live
   behind the URL fragment. The league is the leading route segment (#/<slug>),
   giving each league its own shareable URL; the four views share the AppShell
   chrome and nest under it. ShellProvider reads the slug to pin the league. */
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route
          path=":leagueSlug"
          element={
            <ShellProvider>
              <AppShell />
            </ShellProvider>
          }
        >
          <Route index element={<DiamondView />} />
          <Route path="positional-races" element={<PositionalRaceView />} />
          <Route path="team-records" element={<TeamRecordsView />} />
          <Route path="player-records" element={<PlayerRecordsView />} />
          {/* Unknown sub-path within a league → that league's All-Stars. */}
          <Route path="*" element={<Navigate to="." replace />} />
        </Route>
        {/* Root and anything else → resolve the default league. */}
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </HashRouter>
  );
}

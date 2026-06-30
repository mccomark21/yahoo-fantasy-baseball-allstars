import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { ShellProvider } from "./context/ShellContext";
import AppShell from "./components/AppShell";
import DiamondView from "./components/DiamondView";
import PositionalRaceView from "./components/PositionalRaceView";
import TeamRecordsView from "./components/TeamRecordsView";
import PlayerRecordsView from "./components/PlayerRecordsView";

/* HashRouter: GitHub Pages has no server to rewrite deep paths, so routes live
   behind the URL fragment. All four views share the AppShell chrome. */
export default function App() {
  return (
    <ShellProvider>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DiamondView />} />
            <Route path="positional-races" element={<PositionalRaceView />} />
            <Route path="team-records" element={<TeamRecordsView />} />
            <Route path="player-records" element={<PlayerRecordsView />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </ShellProvider>
  );
}

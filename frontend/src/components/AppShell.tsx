import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { VIEWS, viewByPath } from "../views";
import { useShell } from "../context/ShellContext";
import BallIcon from "./BallIcon";
import LeagueToggle from "./LeagueToggle";
import NavTabs from "./NavTabs";
import "./PlayerCard.css";
import "./diamond.css";

/* The broadcast chrome shared by all four views: brand + nav tabs, the view
   header (title / season / hint / league toggle), and the routed <Outlet />. */
export default function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const view = viewByPath(location.pathname);
  const { leagues, season, leagueId, setLeague } = useShell();

  function onNav(id: string) {
    const target = VIEWS.find((v) => v.id === id);
    if (target) navigate(target.path);
  }

  return (
    <div className="app" data-view={view.id}>
      <a className="skip-link" href="#view-panel">
        Skip to content
      </a>

      <header className="topbar">
        <div className="topbar__brand">
          <BallIcon />
          <span>League All-Stars</span>
        </div>
        <NavTabs active={view.id} onChange={onNav} />
      </header>

      <div className="viewhead">
        <div className="viewhead__title-wrap">
          <h1 className="viewhead__title">{view.title}</h1>
          {season && <span className="viewhead__season mono">{season}</span>}
        </div>
        <div className="viewhead__right">
          <p className="viewhead__hint">{view.hint}</p>
          {leagues.length > 0 && (
            <LeagueToggle
              leagues={leagues}
              activeId={leagueId}
              onChange={setLeague}
            />
          )}
        </div>
      </div>

      <main className="view" id="view-panel" role="tabpanel" aria-label={view.title}>
        <Outlet />
      </main>
    </div>
  );
}

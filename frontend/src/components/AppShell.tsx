import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { VIEWS, viewByPath } from "../views";
import { useShell } from "../context/ShellContext";
import BallIcon from "./BallIcon";
import LeagueToggle from "./LeagueToggle";
import NavTabs from "./NavTabs";
import UpdatedAt from "./UpdatedAt";
import "./PlayerCard.css";
import "./diamond.css";

/* The broadcast chrome shared by all four views. The top bar is the home for
   persistent controls — brand + season, nav tabs, the league dropdown, and the
   freshness stamp. The view header below carries only the per-view title (off
   the diamond) and hint, then the routed <Outlet />. */
export default function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const view = viewByPath(location.pathname);
  const { leagues, season, updated, leagueId, setLeague } = useShell();
  const isAllStars = view.id === "all-stars";

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
          <span className="topbar__wordmark">League All-Stars</span>
          {season && (
            <span className="topbar__season mono" aria-label={`${season} season`}>
              {season}
            </span>
          )}
        </div>

        <NavTabs active={view.id} onChange={onNav} />

        <div className="topbar__controls">
          {leagues.length > 0 && (
            <LeagueToggle
              leagues={leagues}
              activeId={leagueId}
              onChange={setLeague}
            />
          )}
          {updated && (
            <p className="topbar__updated">
              <UpdatedAt iso={updated} />
            </p>
          )}
        </div>
      </header>

      <div className="viewhead">
        {!isAllStars && <h1 className="viewhead__title">{view.title}</h1>}
        <p className="viewhead__hint">{view.hint}</p>
      </div>

      <main className="view" id="view-panel" role="tabpanel" aria-label={view.title}>
        <Outlet />
      </main>
    </div>
  );
}

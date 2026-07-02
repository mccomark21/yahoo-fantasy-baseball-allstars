import { useEffect } from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { VIEWS, viewByPath } from "../views";
import { useShell } from "../context/ShellContext";
import BallIcon from "./BallIcon";
import NavTabs from "./NavTabs";
import UpdatedAt from "./UpdatedAt";
import "./PlayerCard.css";
import "./diamond.css";

/* The broadcast chrome shared by all four views. The top bar is the home for
   persistent controls — brand + season, nav tabs, the current-league badge, and
   the freshness stamp. The league is pinned by the URL slug (#/<slug>), so the
   badge is a static label, not a switcher. The view header below carries only
   the per-view title (off the diamond) and hint, then the routed <Outlet />. */
export default function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { leagueSlug } = useParams();
  const { leagues, season, updated, leagueId } = useShell();

  // Routes are nested under the league segment (/<slug>/…), so strip the slug
  // prefix before matching the view — the view paths ("/", "/team-records", …)
  // are league-agnostic.
  const subPath =
    (leagueSlug ? location.pathname.replace(`/${leagueSlug}`, "") : location.pathname) ||
    "/";
  const view = viewByPath(subPath);
  const isAllStars = view.id === "all-stars";
  const activeLeague = leagues.find((l) => l.id === leagueId);

  // Navigate within the current league: keep the /<slug> prefix, swap the view.
  function onNav(id: string) {
    const target = VIEWS.find((v) => v.id === id);
    if (!target || !leagueSlug) return;
    const suffix = target.path === "/" ? "" : target.path;
    navigate(`/${leagueSlug}${suffix}`);
  }

  // Keep the document title in step with the route + league. SPA navigation
  // doesn't reload the page, so without this a screen reader announces the same
  // stale title on every view; the league name also makes a shared link's tab
  // self-describing.
  useEffect(() => {
    const league = activeLeague ? ` · ${activeLeague.name}` : "";
    document.title = `${view.title}${league} · Fantasy Baseball All-Stars`;
  }, [view.title, activeLeague]);

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
          {activeLeague && (
            <p className="topbar__league" aria-label={`League: ${activeLeague.name}`}>
              <span className="topbar__league-eyebrow">League</span>
              <span className="topbar__league-name">{activeLeague.name}</span>
            </p>
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

import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";
import AccountMenu from "./AccountMenu.jsx";
import AgentsMenu from "./AgentsMenu.jsx";
import ThemeToggle from "./ThemeToggle.jsx";
import Icon from "./Icon.jsx";
import { useAuth } from "./AuthContext.jsx";
import { useProject } from "./ProjectContext.jsx";
import { cn } from "../lib/utils.js";

const TABS = [
  { to: "/overview", label: "Overview" },
  { to: "/schedule", label: "Schedule" },
  { to: "/cast", label: "Cast" },
  { to: "/audience", label: "Audience" },
];

// The signed-in site: logo on the left; the results tabs, the Agents menu
// (the agent log, casting board, production and launch desks, advisors and
// the sign-off queue) and "New script" on the right; the page underneath.
export default function AppLayout() {
  const { canEdit } = useAuth();
  const { error, setError } = useProject();
  const location = useLocation();

  return (
    <div className="site">
      <header className="site-header">
        <div className="site-header__bar">
          <BrandLogo to="/" height={42} />
          <span className="site-header__spacer" />
          <nav className="site-tabs" aria-label="Results">
            {TABS.map((tab) => (
              <NavLink key={tab.to} to={tab.to} className={({ isActive }) => cn("site-tab", isActive && "active")}>
                {tab.label}
              </NavLink>
            ))}
          </nav>
          <div className="site-actions">
            <AgentsMenu />
            {canEdit && (
              <Link to="/new" className="btn btn--primary">
                <Icon name="upload" size={18} />
                <span className="btn-label">New script</span>
              </Link>
            )}
            <ThemeToggle />
            <AccountMenu />
          </div>
        </div>
      </header>

      <main className="site-main">
        {/* keyed on the path so each page fades up into place after navigation */}
        <div className="site-inner page-enter" key={location.pathname}>
          {error && (
            <div className="banner" data-tone="bad" role="alert">
              <Icon name="error" />
              <span className="banner__text">{error}</span>
              <button type="button" className="btn btn--icon banner__close" aria-label="Dismiss" onClick={() => setError("")}>
                <Icon name="close" size={18} />
              </button>
            </div>
          )}
          <Outlet />
        </div>
      </main>
    </div>
  );
}

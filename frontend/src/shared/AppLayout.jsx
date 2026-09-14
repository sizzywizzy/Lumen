import { Link, NavLink, Outlet } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";
import AccountMenu from "./AccountMenu.jsx";
import Icon from "./Icon.jsx";
import { useAuth } from "./AuthContext.jsx";
import { cn } from "../lib/utils.js";

const TABS = [
  { to: "/overview", label: "Overview" },
  { to: "/schedule", label: "Schedule" },
  { to: "/cast", label: "Cast" },
  { to: "/audience", label: "Audience" },
];

// The signed-in site: logo on the left, the results tabs and "New script" on
// the right, and the page underneath. Earlier tools (casting board, production
// tools, marketing, advisors, agent log) still have routes but no menu entry.
export default function AppLayout() {
  const { canEdit } = useAuth();

  return (
    <div className="site">
      <header className="site-header">
        <div className="site-header__bar">
          <BrandLogo to="/overview" height={42} />
          <span className="site-header__spacer" />
          <nav className="site-tabs" aria-label="Results">
            {TABS.map((tab) => (
              <NavLink key={tab.to} to={tab.to} className={({ isActive }) => cn("site-tab", isActive && "active")}>
                {tab.label}
              </NavLink>
            ))}
          </nav>
          <div className="site-actions">
            {canEdit && (
              <Link to="/new" className="btn btn--primary">
                <Icon name="upload" size={18} />
                <span className="btn-label">New script</span>
              </Link>
            )}
            <AccountMenu />
          </div>
        </div>
      </header>

      <main className="site-main">
        <div className="site-inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

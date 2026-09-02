import { NavLink } from "react-router-dom";
import Icon from "./Icon.jsx";
import { CameraArt } from "./CameraArt.jsx";
import { PRIMARY_NAV, SECONDARY_NAV } from "./navigation.js";
import { useAuth } from "./AuthContext.jsx";
import { cn, initials } from "../lib/utils.js";

function NavRow({ item, onNavigate }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => cn("nav-item", isActive && "active")}
    >
      {({ isActive }) => (
        <>
          <Icon name={item.icon} filled={isActive} />
          <span>{item.label}</span>
        </>
      )}
    </NavLink>
  );
}

// Fixed 256px rail present on every screen of the Stitch design.
export default function Sidebar() {
  const { user, activeProduction, role } = useAuth();

  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="sidebar-brand">
        <span className="sidebar-mark" aria-hidden="true">
          {/* the team's own camera mark, not a stock glyph */}
          <svg viewBox="0 -28 168 168" width="26" height="26" style={{ display: "block" }}>
            <CameraArt />
          </svg>
        </span>
        <div>
          <h1>CineNode</h1>
          <p className="mono-label">Production Dashboard</p>
        </div>
      </div>

      <div className="nav-group nav-group--main">
        {PRIMARY_NAV.map((item) => (
          <NavRow key={item.to} item={item} />
        ))}
      </div>

      <div className="nav-group nav-group--foot">
        {SECONDARY_NAV.map((item) => (
          <NavRow key={item.to} item={item} />
        ))}
        {/* the signed-in member, not a placeholder persona */}
        <div className="sidebar-user" title={activeProduction?.project_id}>
          <span className="avatar" aria-hidden="true">
            {initials(user?.name) || "··"}
          </span>
          <div className="who">
            <p>{user?.name || "Signed in"}</p>
            <p className="mono-label">{role || "member"}</p>
          </div>
        </div>
      </div>
    </nav>
  );
}

// Compact bottom bar for phones — the Stitch mobile fallback.
export function BottomNav() {
  return (
    <nav className="bottom-nav" aria-label="Primary mobile">
      {[...PRIMARY_NAV, SECONDARY_NAV[0]].map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => cn("nav-tab", isActive && "active")}
        >
          {({ isActive }) => (
            <>
              <Icon name={item.icon} filled={isActive} />
              <span>{item.short}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

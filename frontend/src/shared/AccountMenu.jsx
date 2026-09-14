import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "./Icon.jsx";
import { useAuth } from "./AuthContext.jsx";
import { useTheme } from "../theme/ThemeProvider.jsx";
import { initials, roleLabel } from "../lib/utils.js";

// Everything that is about you rather than the film: which production you're
// looking at, the team, settings, dark mode and signing out.
export default function AccountMenu() {
  const { user, productions, activeProduction, selectProduction, role, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => wrapRef.current && !wrapRef.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function signOut() {
    setOpen(false);
    await logout();
    navigate("/", { replace: true });
  }

  const close = () => setOpen(false);

  return (
    <div className="account" ref={wrapRef}>
      <button
        type="button"
        className="account-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Your account"
        onClick={() => setOpen((o) => !o)}
      >
        {initials(user?.name) || <Icon name="person" size={20} />}
      </button>

      {open && (
        <div className="account-menu" role="menu">
          <div className="account-head">
            <strong>{user?.name}</strong>
            <span className="body-sm muted">{user?.email}</span>
          </div>

          {productions.length > 1 ? (
            <label className="account-field">
              <span className="body-sm muted">Production</span>
              <span className="select-wrap">
                <select
                  className="select"
                  value={activeProduction?.project_id || ""}
                  onChange={(e) => selectProduction(e.target.value)}
                >
                  {productions.map((p) => (
                    <option key={p.project_id} value={p.project_id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <Icon name="expand_more" />
              </span>
            </label>
          ) : (
            activeProduction && (
              <div className="account-field">
                <span className="body-sm muted">Production</span>
                <span className="body-sm">
                  {activeProduction.name} · {roleLabel(role)}
                </span>
              </div>
            )
          )}

          <Link to="/team" className="account-item" role="menuitem" onClick={close}>
            <Icon name="group" />
            Team
          </Link>
          <Link to="/settings" className="account-item" role="menuitem" onClick={close}>
            <Icon name="settings" />
            Settings
          </Link>
          <button type="button" className="account-item" role="menuitem" onClick={toggleTheme}>
            <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} />
            {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          </button>
          <button type="button" className="account-item" role="menuitem" onClick={signOut}>
            <Icon name="logout" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

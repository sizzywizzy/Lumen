import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import Sidebar, { BottomNav } from "./Sidebar.jsx";
import ThemeToggle from "./ThemeToggle.jsx";
import Icon from "./Icon.jsx";
import LiveAgentTerminal from "./LiveAgentTerminal.jsx";
import CineNodeLogo from "./CineNodeLogo.jsx";
import { useProject } from "./ProjectContext.jsx";
import { useAuth } from "./AuthContext.jsx";
import { money } from "../lib/utils.js";

// Persistent chrome for every route: fixed sidebar, top bar with the global
// pipeline action + theme toggle, the docked agent terminal on wide screens,
// and a bottom nav / terminal drawer on small ones.
export default function AppShell() {
  const { state, events, revealed, running, error, runPipeline } = useProject();
  const { activeProduction, productions, selectProduction, canEdit, logout, user } = useAuth();
  const [railOpen, setRailOpen] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const isIntake = location.pathname === "/";
  const isLogs = location.pathname === "/logs";
  // The dedicated Logs page already shows the full stream — no need to dock it twice.
  const showRail = !isIntake && !isLogs;
  const cap = state?.budget_state?.cap;
  const productionName = activeProduction?.name || activeProduction?.project_id || "—";

  async function signOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <Sidebar />

      <div className="app-body">
        <header className="topbar">
          <button
            type="button"
            className="brand-mobile md-down"
            onClick={() => navigate("/")}
            aria-label="CineNode home"
          >
            <CineNodeLogo height={22} />
          </button>

          {/* Labelled key/value pair — colon, spacing and weight make the value
              read as data rather than as part of the label. */}
          <dl className="topbar-meta md-up">
            <div className="meta-pair">
              <dt>Project</dt>
              <dd>
                {productions.length > 1 ? (
                  <div className="select-wrap">
                    <select
                      className="select select--bare"
                      value={activeProduction?.project_id || ""}
                      aria-label="Switch production"
                      onChange={(e) => selectProduction(e.target.value)}
                    >
                      {productions.map((p) => (
                        <option key={p.project_id} value={p.project_id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <Icon name="arrow_drop_down" />
                  </div>
                ) : (
                  <span title={activeProduction?.project_id}>{productionName}</span>
                )}
              </dd>
            </div>
            {cap > 0 && (
              <div className="meta-pair only-desktop">
                <dt>Budget</dt>
                <dd className="nums">{money(cap)}</dd>
              </div>
            )}
          </dl>

          <div className="spacer" />
          {showRail && (
            <button
              type="button"
              className="btn btn--icon"
              onClick={() => (window.innerWidth >= 1280 ? setRailOpen((o) => !o) : setDrawerOpen(true))}
              title="Toggle live agent terminal"
              aria-label="Toggle live agent terminal"
            >
              <Icon name="terminal" size={20} />
            </button>
          )}
          <ThemeToggle />
          <button
            type="button"
            className="btn btn--icon"
            onClick={signOut}
            title={`Sign out ${user?.email || ""}`.trim()}
            aria-label="Sign out"
          >
            <Icon name="logout" size={20} />
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={runPipeline}
            disabled={running || !canEdit}
            title={canEdit ? undefined : "Your role on this production is read-only"}
          >
            <Icon name={running ? "progress_activity" : "play_arrow"} className={running ? "spin" : undefined} />
            <span>{running ? "Agents working…" : "Run pipeline"}</span>
          </button>
        </header>

        <div className="workspace">
          <main className="page-main">
            <div className="page-inner">
              {error && (
                <div className="banner" data-tone="bad" role="alert">
                  <Icon name="error" />
                  <span>{error}</span>
                </div>
              )}
              <Outlet />
              {!isIntake && state?.human_escalations?.length > 0 && (
                <section className="panel panel--pad">
                  <h3 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="pan_tool" />
                    Human sign-off queue
                  </h3>
                  {state.human_escalations.map((e, i) => (
                    <div className="queue-item" key={`${e.queue_item}-${i}`}>
                      <Icon name="pending_actions" />
                      <span>
                        <strong>{e.queue_item}</strong> — <span className="muted">{e.reason}</span>
                      </span>
                    </div>
                  ))}
                </section>
              )}
            </div>
          </main>

          {showRail && (
            <aside className={railOpen ? "terminal-rail open" : "terminal-rail"} aria-label="Live agent terminal">
              <div className="rail-head">
                <Icon name="terminal" size={18} />
                <span className="mono-label">
                  Live agent terminal — {Math.min(revealed, events.length)}/{events.length}
                </span>
                <span className="spacer" />
                <button
                  type="button"
                  className="btn btn--icon"
                  onClick={() => navigate("/logs")}
                  title="Open full terminal"
                  aria-label="Open full terminal"
                >
                  <Icon name="open_in_full" size={18} />
                </button>
              </div>
              <div className="rail-body">
                <LiveAgentTerminal events={events} revealed={revealed} />
              </div>
            </aside>
          )}
        </div>
      </div>

      {showRail && drawerOpen && (
        <>
          <button
            type="button"
            className="drawer-scrim"
            aria-label="Close terminal"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="terminal-drawer" role="dialog" aria-label="Live agent terminal">
            <div className="rail-head">
              <Icon name="terminal" size={18} />
              <span className="mono-label">
                Live agent terminal — {Math.min(revealed, events.length)}/{events.length}
              </span>
              <span className="spacer" />
              <button
                type="button"
                className="btn btn--icon"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close terminal"
              >
                <Icon name="close" size={18} />
              </button>
            </div>
            <div className="rail-body">
              <LiveAgentTerminal events={events} revealed={revealed} />
            </div>
          </div>
        </>
      )}

      <BottomNav />
    </div>
  );
}

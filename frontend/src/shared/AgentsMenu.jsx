import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Icon from "./Icon.jsx";
import { useProject } from "./ProjectContext.jsx";
import { phaseWords } from "../lib/production.js";
import { cn } from "../lib/utils.js";

// The agent layer: the screens where the agents' work shows and where people
// act on it, next to the results tabs.
export const AGENT_SCREENS = [
  { to: "/logs", icon: "terminal", label: "Agent log", hint: "Every message the agents sent each other." },
  { to: "/casting", icon: "groups", label: "Casting board", hint: "Rank the auditions, then lock or rule out actors." },
  { to: "/production", icon: "fact_check", label: "Production desk", hint: "Stripboard, territory clearances and the cost ledger." },
  { to: "/marketing", icon: "campaign", label: "Launch desk", hint: "Audience simulator, reception and campaign posts." },
  { to: "/advisors", icon: "auto_awesome", label: "AI advisors", hint: "Ask for a review of the cast, schedule or audience." },
];

export default function AgentsMenu() {
  const { state, running, job } = useProject();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const location = useLocation();
  const active = AGENT_SCREENS.some((screen) => location.pathname.startsWith(screen.to));
  const waiting = state?.human_escalations?.length || 0;
  const phase = running && job?.phases?.find((p) => p.status === "running");

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

  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <div className="agents" ref={wrapRef}>
      <button
        type="button"
        className={cn("btn btn--ghost agents-button", active && "is-active")}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={["Agents", running && "working now", waiting > 0 && `${waiting} waiting for sign-off`]
          .filter(Boolean)
          .join(", ")}
        title={running ? "The agents are working on this production" : "The agents behind the plan"}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name={running ? "progress_activity" : "hub"} className={running ? "spin" : undefined} />
        <span className="btn-label">Agents</span>
        {waiting > 0 && (
          <span className="count-badge" aria-hidden="true">
            {waiting}
          </span>
        )}
      </button>

      {open && (
        <div className="account-menu agents-menu" role="menu">
          <div className="account-head">
            <strong>{running ? "The agents are working" : "The agent layer"}</strong>
            <span className="body-sm muted">
              {running
                ? `Now: ${phase ? phaseWords(phase.key).toLowerCase() : "getting started"}.`
                : "Where the agents show their work, and where you decide."}
            </span>
          </div>
          {waiting > 0 && (
            <Link to="/overview#sign-off" className="account-item agents-item" role="menuitem">
              <Icon name="pending_actions" />
              <span>
                Sign-off queue
                <small>
                  {waiting} {waiting === 1 ? "decision is" : "decisions are"} waiting for a person.
                </small>
              </span>
            </Link>
          )}
          {AGENT_SCREENS.map((screen) => (
            <Link
              key={screen.to}
              to={screen.to}
              role="menuitem"
              className={cn("account-item agents-item", location.pathname.startsWith(screen.to) && "is-current")}
            >
              <Icon name={screen.icon} />
              <span>
                {screen.label}
                <small>{screen.hint}</small>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { api } from "./lib/api.js";
import { cn } from "./lib/utils.js";
import LiveAgentTerminal from "./shared/LiveAgentTerminal.jsx";
import CineNodeLogo from "./shared/CineNodeLogo.jsx";
import CastingView from "./features/casting/CastingView.jsx";
import ProdView from "./features/production/ProdView.jsx";
import LaunchView from "./features/launch/LaunchView.jsx";

const PROJECT_ID = "PROJ_NEON_NIGHTS";
const TABS = [
  { key: "casting", label: "I–II Casting", View: CastingView },
  { key: "production", label: "III–IV Production", View: ProdView },
  { key: "launch", label: "V–VI Launch", View: LaunchView },
];
const REVEAL_MS = 60; // terminal replay speed per message

export default function App() {
  const [mode, setMode] = useState("indie");
  const [tab, setTab] = useState("casting");
  const [state, setState] = useState(null);
  const [events, setEvents] = useState([]);
  const [revealed, setRevealed] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const timerRef = useRef(null);

  // On load, pick up any previously saved run.
  useEffect(() => {
    api.getState(PROJECT_ID).then((s) => {
      setState(s);
      setEvents(s.event_log);
      setRevealed(s.event_log.length);
    }).catch(() => {});
    return () => clearInterval(timerRef.current);
  }, []);

  async function runPipeline() {
    setRunning(true);
    setError("");
    setEvents([]);
    setRevealed(0);
    clearInterval(timerRef.current);
    try {
      await api.runPipeline(PROJECT_ID, mode);
      const s = await api.getState(PROJECT_ID);
      setState(s);
      setEvents(s.event_log);
      // Replay the A2A conversation message-by-message in the terminal.
      timerRef.current = setInterval(() => {
        setRevealed((r) => {
          if (r >= s.event_log.length) {
            clearInterval(timerRef.current);
            return r;
          }
          return r + 1;
        });
      }, REVEAL_MS);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  }

  const ActiveView = TABS.find((t) => t.key === tab).View;

  return (
    <>
      <div className="topbar">
        <h1><CineNodeLogo height={30} /></h1>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>{PROJECT_ID}</span>
        <div className="spacer" />
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="indie">Indies</option>
          <option value="enterprise">Big Dawgs</option>
        </select>
        <button className="primary" onClick={runPipeline} disabled={running}>
          {running ? "Agents working…" : "▶ Run pipeline"}
        </button>
      </div>
      <div className="layout">
        <div className="main">
          {error && <div className="card" style={{ color: "var(--bad)" }}>{error}</div>}
          <div className="tabs">
            {TABS.map((t) => (
              <button key={t.key} className={cn("tab", tab === t.key && "active")}
                      onClick={() => setTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
          <ActiveView state={state} />
          {state?.human_escalations?.length > 0 && (
            <div className="card">
              <h3>Human Sign-off Queue</h3>
              {state.human_escalations.map((e, i) => (
                <div key={i}>✋ <strong>{e.queue_item}</strong> — {e.reason}</div>
              ))}
            </div>
          )}
        </div>
        <LiveAgentTerminal events={events} revealed={revealed} />
      </div>
    </>
  );
}

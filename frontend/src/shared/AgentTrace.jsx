import Icon from "./Icon.jsx";
import { agentShort } from "./AgentLog.jsx";
import { agentTrace } from "../lib/production.js";
import { cn } from "../lib/utils.js";

// The execution trace: what the agents are doing, phase by phase, while they
// do it — and what they did, once they have finished.
//
// A producer watching a run should not be staring at a spinner wondering
// whether anything is happening, and a producer reading a finished plan should
// be able to see how it was arrived at rather than only what it came to. Each
// row shows the phase's real status as the backend reports it; once the run's
// traffic is loaded it also shows which agents spoke, how many messages it
// took, and whether either of Lumen's two negotiation loops actually fired.
//
// Every number comes from the A2A event log by way of `agentTrace`. A phase
// with no messages shows no messages: nothing here is filler.

const MARKS = {
  complete: { icon: "check_circle", spin: false },
  running: { icon: "progress_activity", spin: true },
  halted: { icon: "pause_circle", spin: false },
  failed: { icon: "error", spin: false },
  pending: { icon: "radio_button_unchecked", spin: false },
};

const TONES = { running: "warn", complete: "ok", failed: "bad" };

export default function AgentTrace({ phases, events, status, title = "Agent execution trace" }) {
  const rows = agentTrace(phases, events);
  const done = rows.filter((row) => row.status === "complete").length;
  const messages = rows.reduce((sum, row) => sum + row.messages, 0);
  const tone = TONES[status];

  return (
    <div className="agent-trace">
      <div className="row row--tight agent-trace__top">
        <Icon name="account_tree" style={{ color: "var(--primary)" }} />
        <strong className="mono-label">{title}</strong>
        {tone && (
          <span className="status-pill" data-tone={tone}>
            <span className="dot" />
            {status}
          </span>
        )}
        <span className="agent-trace__count mono-data">
          {done} of {rows.length} phases
          {messages > 0 && ` · ${messages} messages`}
        </span>
      </div>

      <ol className="trace-list">
        {rows.map((row) => {
          const mark = MARKS[row.status] || MARKS.pending;
          return (
            <li key={row.key} className={cn("trace-phase", `trace-phase--${row.status}`)}>
              <div className="trace-phase__rail">
                <Icon name={mark.icon} size={18} className={mark.spin ? "spin" : undefined} />
              </div>
              <div className="trace-phase__body">
                <div className="trace-phase__head">
                  <strong>{row.words}</strong>
                  {row.messages > 0 && (
                    <span className="trace-phase__messages mono-data">{row.messages} messages</span>
                  )}
                </div>
                {row.agents.length > 0 && (
                  <div className="trace-agents">
                    {row.agents.map((agent) => (
                      <span key={agent} className="trace-agent mono-data" title={agent}>
                        {agentShort(agent)}
                      </span>
                    ))}
                  </div>
                )}
                {row.loops.map((loop) => (
                  <div key={loop.pair} className="trace-loop">
                    <Icon name="cached" size={14} />
                    <span className="mono-data">{loop.pair}</span>
                    <small>{loop.detail}</small>
                  </div>
                ))}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

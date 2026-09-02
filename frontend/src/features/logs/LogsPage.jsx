import { useEffect, useMemo, useRef, useState } from "react";
import Panel from "../../shared/Panel.jsx";
import Icon from "../../shared/Icon.jsx";
import AgentLog, { agentShort } from "../../shared/AgentLog.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn } from "../../lib/utils.js";

// Dedicated Live Agent Terminal route (the Stitch "Logs" screen). Same A2A
// envelopes as the docked rail, with agent filtering, a payload search and a
// stream pause so a producer can read one exchange without it scrolling away.
export default function LogsPage() {
  const { events, revealed, running, projectId, runPipeline } = useProject();
  const [agent, setAgent] = useState("ALL");
  const [query, setQuery] = useState("");
  const [paused, setPaused] = useState(false);
  const frozenRef = useRef([]);
  const bodyRef = useRef(null);

  const live = useMemo(() => events.slice(0, revealed), [events, revealed]);

  // While paused, keep showing the snapshot taken at the moment of pausing.
  const source = paused ? frozenRef.current : live;
  useEffect(() => {
    if (!paused) frozenRef.current = live;
  }, [live, paused]);

  const agents = useMemo(() => [...new Set(events.map((e) => e.sender))].sort(), [events]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return source.filter((e) => {
      if (agent !== "ALL" && e.sender !== agent) return false;
      if (!q) return true;
      return `${e.sender} ${e.recipient} ${e.intent} ${JSON.stringify(e.payload)}`.toLowerCase().includes(q);
    });
  }, [source, agent, query]);

  useEffect(() => {
    if (!paused && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [visible.length, paused]);

  return (
    <>
      <Panel className="panel--pad">
        <div className="between">
          <div>
            <h2 className="headline-lg" style={{ margin: 0 }}>
              Live Agent Terminal
            </h2>
            <p className="mono-label muted" style={{ marginTop: 6 }}>
              A2A_ORCHESTRATION_LOGS // {running ? "NODE_STREAMING" : events.length ? "NODE_ACTIVE" : "NODE_IDLE"} ·{" "}
              {projectId}
            </p>
          </div>
          <div className="row row--tight">
            <div className="select-wrap" style={{ minWidth: 190 }}>
              <select
                className="select"
                value={agent}
                aria-label="Filter by agent"
                onChange={(e) => setAgent(e.target.value)}
              >
                <option value="ALL">All agents</option>
                {agents.map((a) => (
                  <option key={a} value={a}>
                    {agentShort(a)} — {a}
                  </option>
                ))}
              </select>
              <Icon name="arrow_drop_down" />
            </div>
            <div className="search-wrap" style={{ minWidth: 200 }}>
              <Icon name="filter_list" />
              <input
                className="input"
                type="search"
                placeholder="Filter intents or payloads…"
                value={query}
                aria-label="Filter log payloads"
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button
              type="button"
              className={cn("btn", paused ? "btn--tonal" : "btn--primary")}
              onClick={() => setPaused((p) => !p)}
              disabled={!events.length}
            >
              <Icon name={paused ? "play_arrow" : "pause"} />
              <span>{paused ? "Resume stream" : "Pause stream"}</span>
            </button>
          </div>
        </div>
      </Panel>

      <div className="terminal" ref={bodyRef} style={{ minHeight: "min(64vh, 620px)" }}>
        <AgentLog
          events={visible}
          connected={events.length > 0}
          emptyHint={
            events.length === 0
              ? "Run the pipeline to watch the agents negotiate in real time."
              : "No messages match the current agent or payload filter."
          }
        />
      </div>

      <div className="between mono-label muted">
        <span>
          {visible.length} of {events.length} envelopes
          {paused ? " · stream paused" : ""}
        </span>
        {events.length === 0 && (
          <button type="button" className="btn btn--ghost" onClick={runPipeline} disabled={running}>
            <Icon name="play_arrow" />
            Run pipeline
          </button>
        )}
      </div>
    </>
  );
}

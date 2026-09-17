import { useEffect, useMemo, useRef, useState } from "react";
import Panel from "../../shared/Panel.jsx";
import Icon from "../../shared/Icon.jsx";
import AgentLog, { agentShort } from "../../shared/AgentLog.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { api } from "../../lib/api.js";
import { cn } from "../../lib/utils.js";

const PAGE = 500; // the most envelopes /api/events returns at once

// Every envelope before `upTo`, read a page at a time.
async function readLog(projectId, upTo) {
  const out = [];
  while (out.length < upTo) {
    const page = await api.getEvents(projectId, out.length, Math.min(PAGE, upTo - out.length));
    if (!page.events.length) break;
    out.push(...page.events);
  }
  return out;
}

// Dedicated Live Agent Terminal route (the Stitch "Logs" screen): the whole
// A2A conversation, with agent filtering, a payload search and a stream pause
// so a producer can read one exchange without it scrolling away. The project
// state carries only the latest envelopes; the earlier ones load here.
export default function LogsPage() {
  const { events, revealed, eventOffset, running, projectId, runPipeline, canEdit } = useProject();
  const [agent, setAgent] = useState("ALL");
  const [query, setQuery] = useState("");
  const [paused, setPaused] = useState(false);
  const [earlier, setEarlier] = useState({ events: [], loading: false, error: "" });
  const frozenRef = useRef([]);
  const bodyRef = useRef(null);

  useEffect(() => {
    setEarlier({ events: [], loading: Boolean(eventOffset), error: "" });
    if (!projectId || !eventOffset) return undefined;
    let cancelled = false;
    readLog(projectId, eventOffset)
      .then((list) => !cancelled && setEarlier({ events: list, loading: false, error: "" }))
      .catch((e) => !cancelled && setEarlier({ events: [], loading: false, error: String(e.message || e) }));
    return () => {
      cancelled = true;
    };
  }, [projectId, eventOffset]);

  const allEvents = useMemo(() => [...earlier.events, ...events], [earlier.events, events]);
  const live = useMemo(() => [...earlier.events, ...events.slice(0, revealed)], [earlier.events, events, revealed]);

  // While paused, keep showing the snapshot taken at the moment of pausing.
  const source = paused ? frozenRef.current : live;
  useEffect(() => {
    if (!paused) frozenRef.current = live;
  }, [live, paused]);

  const agents = useMemo(() => [...new Set(allEvents.map((e) => e.sender))].sort(), [allEvents]);

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
              A2A_ORCHESTRATION_LOGS // {running ? "NODE_STREAMING" : allEvents.length ? "NODE_ACTIVE" : "NODE_IDLE"} ·{" "}
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
              disabled={!allEvents.length}
            >
              <Icon name={paused ? "play_arrow" : "pause"} />
              <span>{paused ? "Resume stream" : "Pause stream"}</span>
            </button>
          </div>
        </div>
      </Panel>

      {earlier.error && (
        <div className="banner" data-tone="bad" role="alert">
          <Icon name="error" />
          <span>Earlier messages didn't load: {earlier.error}</span>
        </div>
      )}

      <div className="terminal" ref={bodyRef} style={{ minHeight: "min(64vh, 620px)" }}>
        <AgentLog
          events={visible}
          connected={allEvents.length > 0}
          emptyHint={
            allEvents.length === 0
              ? "Run the pipeline to watch the agents negotiate in real time."
              : "No messages match the current agent or payload filter."
          }
        />
      </div>

      <div className="between mono-label muted">
        <span>
          {visible.length} of {allEvents.length} envelopes
          {earlier.loading ? " · loading earlier messages" : ""}
          {paused ? " · stream paused" : ""}
        </span>
        {allEvents.length === 0 && canEdit && (
          <button type="button" className="btn btn--ghost" onClick={runPipeline} disabled={running}>
            <Icon name={running ? "progress_activity" : "play_arrow"} className={running ? "spin" : undefined} />
            {running ? "Agents working…" : "Run pipeline"}
          </button>
        )}
      </div>
    </>
  );
}

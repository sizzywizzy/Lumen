import { Fragment } from "react";
import Icon from "./Icon.jsx";
import EmptyState from "./EmptyState.jsx";
import { clockTime } from "../lib/utils.js";

// Renders the real A2A envelopes from GlobalState.event_log in the Stitch
// terminal language: timestamp gutter, colour-coded agent badge, intent line
// with a health lamp, and a syntax-highlighted payload block.

// Domain hints keyed off the agent_* id the backend stamps on each envelope.
const AGENT_LOOKS = [
  { match: /orchestrat|director/, icon: "hub", accent: "wine" },
  { match: /cast|talent|audition|scout/, icon: "groups", accent: "plum" },
  { match: /schedul|venue|strip|logistic/, icon: "event_note", accent: "steel" },
  { match: /complian|legal|censor|qc|risk/, icon: "verified_user", accent: "steel" },
  { match: /market|campaign|asset|pr\b|social/, icon: "campaign", accent: "wine" },
  { match: /audience|persona|review|simulat|recut/, icon: "theaters", accent: "plum" },
];

export function agentLook(agentId) {
  const id = String(agentId || "").toLowerCase();
  return AGENT_LOOKS.find((l) => l.match.test(id)) || { icon: "smart_toy", accent: "plum" };
}

// agent_pr_risk -> PR_RISK ; agent_director_orchestrator -> DIR_ORC
export function agentShort(agentId) {
  const base = String(agentId || "agent").replace(/^agent_/, "");
  const words = base.split("_").filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 7).toUpperCase();
  return words
    .slice(0, 2)
    .map((w) => w.slice(0, 3))
    .join("_")
    .toUpperCase();
}

// Blocked / disqualified traffic reads red, conflicts and escalations amber.
function toneForEvent(event) {
  const blob = `${event.intent} ${JSON.stringify(event.payload || {})}`.toLowerCase();
  if (/blocked|disqualif|error|fail|reject/.test(blob)) return "bad";
  if (/conflict|escalat|awaiting_qc|warn|risk|over_budget/.test(blob)) return "warn";
  return "ok";
}

const JSON_TOKEN =
  /("(?:\\.|[^"\\])*")(\s*:)|("(?:\\.|[^"\\])*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(\btrue\b|\bfalse\b|\bnull\b)|([{}[\],:])/g;

// Lightweight JSON colouriser — keys, strings, numbers and punctuation get the
// muted syntax palette from the Stitch terminal so payloads stay scannable.
function highlightJson(value) {
  const text = JSON.stringify(value ?? {}, null, 2);
  const parts = [];
  let last = 0;
  let match;
  JSON_TOKEN.lastIndex = 0;
  while ((match = JSON_TOKEN.exec(text)) !== null) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index) });
    const [, key, colon, str, num, lit, punct] = match;
    if (key !== undefined) {
      parts.push({ text: key, cls: "j-key" });
      parts.push({ text: colon, cls: "j-punct" });
    } else if (str !== undefined) parts.push({ text: str, cls: "j-str" });
    else if (num !== undefined) parts.push({ text: num, cls: "j-num" });
    else if (lit !== undefined) parts.push({ text: lit, cls: "j-num" });
    else if (punct !== undefined) parts.push({ text: punct, cls: "j-punct" });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

export function LogEntry({ event }) {
  const look = agentLook(event.sender);
  const tone = toneForEvent(event);
  return (
    <div className="log-row">
      <span className="ts">{clockTime(event.timestamp)}</span>
      <div className="who">
        <span className="badge" data-agent={look.accent}>
          <Icon name={look.icon} />
        </span>
        <span className="tag">{agentShort(event.sender)}</span>
      </div>
      <div className="body">
        <div className="line">
          <span className="intent">{event.intent}</span>
          <span className="lamp" data-tone={tone === "ok" ? undefined : tone} />
        </div>
        <div className="line route">
          {event.in_reply_to ? "↩ reply to" : "→"} {event.recipient}
        </div>
        <div className="log-json">
          <pre>
            {highlightJson(event.payload).map((p, i) => (
              <Fragment key={i}>{p.cls ? <span className={p.cls}>{p.text}</span> : p.text}</Fragment>
            ))}
          </pre>
        </div>
      </div>
    </div>
  );
}

// Single-line variant for narrow slots (the Stitch marketing "Audience_Sim_Node"
// console): agent tag plus intent, no payload block.
export function LogLine({ event }) {
  const tone = toneForEvent(event);
  return (
    <div className="log-line" data-tone={tone === "ok" ? undefined : tone}>
      <span className="agent">[{agentShort(event.sender)}]</span>
      <span className="msg">{event.intent.replace(/_/g, " ")}</span>
    </div>
  );
}

export default function AgentLog({ events = [], connected = true, emptyHint, compact = false }) {
  return (
    <>
      <div className="log-sys">
        <span className="ts">[SYS]</span>
        {!compact && <span className="tag">A2A</span>}
        <span className="msg">
          {connected
            ? "A2A channel initialised. Streaming agent broadcasts."
            : "Channel idle. Waiting for orchestration to start."}
        </span>
      </div>
      {events.length === 0 && (
        <EmptyState icon="terminal" title="No agent traffic yet">
          {emptyHint || "Run the pipeline to watch the agents negotiate in real time."}
        </EmptyState>
      )}
      {events.map((e) =>
        compact ? <LogLine key={e.message_id} event={e} /> : <LogEntry key={e.message_id} event={e} />
      )}
    </>
  );
}

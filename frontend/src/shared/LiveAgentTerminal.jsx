import { useEffect, useRef } from "react";
import AgentLog from "./AgentLog.jsx";
import { cn } from "../lib/utils.js";

// The proof it's a real MAS: every A2A envelope, streamed in order.
// Same props as before (events + revealed count); the presentation is now the
// Stitch terminal. Reused by the docked rail, the mobile drawer and /logs.
export default function LiveAgentTerminal({
  events = [],
  revealed = events.length,
  flush = false,
  compact = false,
  className,
}) {
  const bodyRef = useRef(null);
  const visible = events.slice(0, revealed);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [revealed]);

  return (
    <div className={cn("terminal", flush && "terminal--flush", compact && "terminal--compact", className)} ref={bodyRef}>
      <AgentLog events={visible} connected={events.length > 0} compact={compact} />
    </div>
  );
}

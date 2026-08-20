import { useEffect, useRef } from "react";

// The proof it's a real MAS: every A2A envelope, streamed in order.
export default function LiveAgentTerminal({ events, revealed }) {
  const bodyRef = useRef(null);
  const visible = events.slice(0, revealed);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [revealed]);

  return (
    <div className="terminal-pane">
      <div className="terminal-header">
        ▌LIVE AGENT TERMINAL — {visible.length}/{events.length} messages
      </div>
      <div className="terminal-body" ref={bodyRef}>
        {visible.length === 0 && <div className="empty">Run the pipeline to watch the agents talk.</div>}
        {visible.map((e) => (
          <div className="msg" key={e.message_id}>
            <div>
              <span className="route">
                {e.sender} {e.in_reply_to ? <span className="reply-marker">↩</span> : "→"} {e.recipient}
              </span>{" "}
              <span className="intent">{e.intent}</span>
            </div>
            <pre>{JSON.stringify(e.payload)}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}

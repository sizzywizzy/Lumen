import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { cn, statusLabel, statusTone } from "../lib/utils.js";

// Full-pill status chip with a leading dot — the Stitch pattern for every
// backend status literal (LOCKED / AWAITING_QC / BLOCKED / DISQUALIFIED ...).
export default function StatusBadge({ status, tone, label }) {
  return (
    <span className="status-pill" data-tone={tone || statusTone(status)}>
      <span className="dot" />
      {label || statusLabel(status)}
    </span>
  );
}

/**
 * Editable variant: the pill itself is the control. It carries a caret and an
 * "editable" affordance so it reads as changeable rather than as a read-only
 * label, and it falls back to the plain badge when the member's role is
 * read-only. `onChange(status, reason)` should persist to the backend; the
 * caller decides how to reflect the result.
 */
export function StatusBadgeSelect({ status, options, onChange, disabled = false, busy = false, needsReason = [] }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(null); // status awaiting a reason
  const [reason, setReason] = useState("");
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) close();
    };
    const onKey = (e) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function close() {
    setOpen(false);
    setPending(null);
    setReason("");
  }

  function choose(next) {
    if (next === status) return close();
    if (needsReason.includes(next)) {
      setPending(next); // ask why before disqualifying
      return;
    }
    close();
    onChange(next, "");
  }

  if (disabled) return <StatusBadge status={status} />;

  return (
    <span className="status-edit" ref={wrapRef}>
      <button
        type="button"
        className={cn("status-pill", "status-pill--button")}
        data-tone={statusTone(status)}
        onClick={() => (open ? close() : setOpen(true))}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={busy}
        title="Change casting status"
      >
        <span className="dot" />
        {statusLabel(status)}
        <Icon name={busy ? "progress_activity" : "expand_more"} size={14} className={busy ? "spin" : undefined} />
      </button>

      {open && (
        <div className="status-menu" role="listbox">
          {pending ? (
            <div className="status-reason">
              <p className="mono-label muted">Reason for {statusLabel(pending)}</p>
              <input
                className="input"
                autoFocus
                placeholder="Scheduling conflict, budget, availability…"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const next = pending;
                    const why = reason;
                    close();
                    onChange(next, why);
                  }
                }}
              />
              <div className="row row--tight" style={{ justifyContent: "flex-end" }}>
                <button type="button" className="btn btn--ghost" onClick={close}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => {
                    const next = pending;
                    const why = reason;
                    close();
                    onChange(next, why);
                  }}
                >
                  Confirm
                </button>
              </div>
            </div>
          ) : (
            options.map((opt) => (
              <button
                key={opt}
                type="button"
                role="option"
                aria-selected={opt === status}
                className={cn("status-option", opt === status && "current")}
                onClick={() => choose(opt)}
              >
                <span className="status-pill" data-tone={statusTone(opt)}>
                  <span className="dot" />
                  {statusLabel(opt)}
                </span>
                {opt === status && <Icon name="check" size={16} />}
              </button>
            ))
          )}
        </div>
      )}
    </span>
  );
}

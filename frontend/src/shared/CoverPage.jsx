import { useRef, useState } from "react";
import { api } from "../lib/api.js";
import CineNodeLogo from "./CineNodeLogo.jsx";
import { CameraArt } from "./CameraArt.jsx";

// Phase 0 — Intake cover. Drop the script, set budget + shooting window + notes,
// then Start pre-production seeds the project and enters the studio (Phase I).
const PROJECT_ID = "PROJ_NEON_NIGHTS";

const serif = "'Bodoni Moda', Didot, 'Bodoni MT', Georgia, serif";

export default function CoverPage({ onEnter }) {
  const [fileName, setFileName] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [budget, setBudget] = useState("250000");
  const [start, setStart] = useState("2026-09-01");
  const [wrap, setWrap] = useState("2026-09-26");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef(null);

  const budgetNum = Number(budget || 0);
  const budgetFmt = budgetNum ? budgetNum.toLocaleString("en-US") : "";
  const ms = Date.parse(wrap) - Date.parse(start);
  const days = Number.isFinite(ms) ? Math.round(ms / 86400000) : NaN;
  const validWindow = Number.isFinite(days) && days > 0;
  const weeks = validWindow ? Math.max(1, Math.round(days / 7)) : 0;
  const windowLine = validWindow
    ? `${days} days · about ${weeks} weeks on set`
    : "Pick a start and a wrap date";

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) setFileName(f.name);
  }
  function onPick(e) {
    const f = e.target.files?.[0];
    if (f) setFileName(f.name);
  }

  async function startPreProduction() {
    if (!fileName || busy) return;
    setBusy(true);
    // Seed the project with the budget so the studio reflects it before the first run.
    try {
      await api.initPipeline(PROJECT_ID, budgetNum || undefined);
    } catch {
      /* backend offline — enter anyway; the studio falls back to defaults */
    }
    setBusy(false);
    onEnter(PROJECT_ID, { budget: budgetNum || undefined, start, wrap, notes });
  }

  const labelCap = { fontSize: 10, letterSpacing: 1, textTransform: "uppercase", color: "var(--muted)" };
  const inputBox = {
    height: 40, border: "1px solid var(--border)", borderRadius: 6,
    background: "var(--panel-2)", color: "var(--text)", colorScheme: "dark",
    padding: "0 10px", boxSizing: "border-box", font: "500 13px 'Segoe UI', system-ui, sans-serif",
  };

  return (
    <div
      style={{
        flex: 1, overflowY: "auto", overflowX: "hidden", padding: "40px clamp(20px, 4vw, 48px)", boxSizing: "border-box",
        background:
          "radial-gradient(900px 480px at 50% -10%, rgba(97,45,83,0.45), transparent 65%)," +
          "radial-gradient(700px 420px at 85% 110%, rgba(133,57,83,0.25), transparent 60%)," +
          "var(--bg)",
      }}
    >
      <div style={{ maxWidth: 1120, margin: "0 auto", display: "flex", flexDirection: "column", gap: 32 }}>
        {/* header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <CineNodeLogo height={44} />
          <span style={{ font: "500 11px/1 var(--mono)", letterSpacing: 2, color: "var(--muted)" }}>
            PHASE 0 · INTAKE
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))", gap: "clamp(24px, 4vw, 48px)", alignItems: "start" }}>
          {/* left — replaceable placeholder still (swap this block for <img src="/your-still.jpg" .../>) */}
          <div
            style={{
              position: "relative", height: "clamp(320px, 40vw, 560px)", borderRadius: 4, overflow: "hidden",
              border: "1px solid var(--border)", background: "#232323",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <div style={{
              position: "absolute", inset: 0,
              background:
                "radial-gradient(60% 45% at 25% 18%, rgba(97,45,83,0.9), transparent 70%)," +
                "radial-gradient(60% 45% at 85% 95%, rgba(133,57,83,0.8), transparent 65%)",
            }} />
            <svg viewBox="0 -28 168 168" width="52%" style={{ position: "relative", opacity: 0.92 }} aria-hidden="true">
              <CameraArt />
            </svg>
            <span style={{ position: "absolute", left: 16, bottom: 14, font: "11px var(--mono)", letterSpacing: 2, color: "#c9ccce" }}>
              NEON NIGHTS · PLACEHOLDER STILL
            </span>
          </div>

          {/* right — the intake form */}
          <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
            <h1 style={{ margin: 0, font: `400 clamp(44px, 5vw, 68px)/0.95 ${serif}`, letterSpacing: "-1.5px", color: "var(--text)" }}>
              Drop the<br />script.
            </h1>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, color: "var(--muted)", maxWidth: 440, textWrap: "pretty" }}>
              Hand over the screenplay, a budget and a shooting window — the agents carry it from casting to launch. You only sign off.
            </p>

            {/* dropzone */}
            <input ref={fileInput} type="file" accept=".pdf,.fountain,.fdx,.txt" onChange={onPick} style={{ display: "none" }} />
            <div
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => { e.preventDefault(); if (!dragging) setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6,
                height: 104, borderRadius: 8, cursor: "pointer", textAlign: "center", padding: 14, boxSizing: "border-box",
                border: `1.5px ${fileName ? "solid" : "dashed"} ${dragging || fileName ? "var(--accent)" : "#8a5f76"}`,
                background: dragging ? "#3b3238" : "var(--panel)",
              }}
            >
              {fileName ? (
                <>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent-text)" style={{ strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" }}><path d="M20 6L9 17l-5-5" /></svg>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)", overflowWrap: "anywhere" }}>{fileName}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)", display: "flex", gap: 6, alignItems: "center" }}>
                    Script attached
                    <button type="button" onClick={(e) => { e.stopPropagation(); setFileName(null); }}
                      style={{ background: "none", border: 0, padding: 0, color: "var(--accent-text)", font: "inherit", cursor: "pointer", textDecoration: "underline" }}>
                      Remove
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent-text)" style={{ strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" }}><path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></svg>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>Drop your script here</div>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>PDF, Fountain or FDX — or click to browse</div>
                </>
              )}
            </div>

            {/* budget + production window, aligned on one row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", columnGap: 12, rowGap: 8, alignItems: "end" }}>
              <h3 style={{ margin: 0, font: `500 20px/1.2 ${serif}`, color: "var(--text)" }}>Budget</h3>
              <h3 style={{ margin: 0, gridColumn: "span 2", font: `500 20px/1.2 ${serif}`, color: "var(--text)" }}>Production time</h3>

              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={labelCap}>Total · USD</span>
                <div style={{ ...inputBox, display: "flex", alignItems: "center", gap: 6, padding: "0 12px" }}>
                  <span style={{ color: "var(--muted)", fontSize: 14 }}>$</span>
                  <input value={budgetFmt} onChange={(e) => setBudget(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" aria-label="Budget in US dollars"
                    style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", font: "500 14px 'Segoe UI', system-ui, sans-serif", color: "var(--text)" }} />
                </div>
              </div>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, ...labelCap }}>Start
                <input type="date" value={start} onChange={(e) => setStart(e.target.value)} style={inputBox} />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, ...labelCap }}>Wrap
                <input type="date" value={wrap} onChange={(e) => setWrap(e.target.value)} style={inputBox} />
              </label>

              <div style={{ fontSize: 12, lineHeight: 1.4, color: "var(--muted)" }}>Sets casting caps, venue picks and territory reach.</div>
              <div style={{ gridColumn: "span 2", fontSize: 12, lineHeight: 1.4, color: "var(--muted)" }}>{windowLine}</div>
            </div>

            {/* special notes */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <h3 style={{ margin: 0, font: `500 20px/1.2 ${serif}`, color: "var(--text)" }}>Special notes</h3>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                placeholder="Anything the agents should know — cast wishes, locations to avoid, territories that matter…" aria-label="Special notes"
                style={{ height: 62, resize: "none", ...inputBox, height: 62, padding: "10px 12px", font: "400 13px/1.45 'Segoe UI', system-ui, sans-serif" }} />
            </div>

            <button type="button" className="primary" onClick={startPreProduction} disabled={!fileName || busy}
              style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 10, padding: "12px 22px", fontSize: 15, opacity: fileName && !busy ? 1 : 0.5, cursor: fileName && !busy ? "pointer" : "not-allowed" }}>
              {busy ? "Setting up…" : "Start pre-production"}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text)" style={{ strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" }}><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "../../shared/Icon.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn } from "../../lib/utils.js";
import { hasResults, productionTitle } from "../../lib/production.js";
import { Card } from "../results/parts.jsx";

const ACCEPTED = /\.(pdf|fdx|fountain|txt|text|md|markdown)$/i;
const MAX_BYTES = 8 * 1024 * 1024;

const STEPS = [
  ["Reading your script", "Breaking it into scenes and characters."],
  [
    "Casting, scheduling and test screening",
    "Finding actors for each role, booking shoot days and venues, and screening the story with 200 viewers. This can take a minute.",
  ],
  ["Your plan is ready", "Opening your overview."],
];
const STEP_ORDER = ["reading", "planning", "ready"];

function isoInDays(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Drop a script: one form, one button. It uploads the screenplay, runs the
// whole plan, shows honest progress, then opens the overview.
export default function NewScriptPage() {
  const navigate = useNavigate();
  const { startRun, state } = useProject();
  const { canEdit, activeProduction } = useAuth();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [budget, setBudget] = useState(String(Math.round(state?.budget_state?.cap || 250000)));
  const [start, setStart] = useState(() => isoInDays(28));
  const [wrap, setWrap] = useState(() => isoInDays(53));
  const [locality, setLocality] = useState(state?.locality || "Los Angeles, CA");
  const [notes, setNotes] = useState("");
  const [step, setStep] = useState(null);
  const [error, setError] = useState("");

  if (!canEdit) {
    return (
      <section className="card empty-plan">
        <h2>Only producers can drop in a script</h2>
        <p>Your role on this production can see the plan but not change it.</p>
        <Link to="/overview" className="btn btn--ghost">
          Back to the overview
        </Link>
      </section>
    );
  }

  function pick(candidate) {
    if (!candidate) return;
    if (!ACCEPTED.test(candidate.name)) {
      setError("That file type isn't supported. Use a PDF, Final Draft (.fdx), Fountain or plain text file.");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setError("That file is over 8 MB. Try a plain text version or a smaller PDF.");
      return;
    }
    setError("");
    setFile(candidate);
  }

  async function submit(e) {
    e.preventDefault();
    const amount = Number(budget);
    if (!file) return setError("Add your script first.");
    if (!amount || amount <= 0) return setError("Enter a budget above zero.");
    if (start && wrap && wrap < start) return setError("The wrap date needs to be on or after the first shoot day.");
    setError("");
    try {
      await startRun({ file, budget: amount, start, wrap, locality: locality.trim(), notes: notes.trim() }, setStep);
      setStep("ready");
      setTimeout(() => navigate("/overview"), 900);
    } catch (err) {
      setStep(null);
      setError(String(err.message || err));
    }
  }

  if (step) {
    const at = STEP_ORDER.indexOf(step);
    return (
      <>
        <div className="page-top">
          <div>
            <h1>Working on {file?.name}</h1>
            <p>Keep this page open while Lumen plans your production.</p>
          </div>
        </div>
        <Card>
          <ol className="progress-steps">
            {STEPS.map(([title, detail], i) => {
              const done = i < at || step === "ready";
              const active = !done && i === at;
              return (
                <li key={title} className={cn("progress-step", done && "is-done", active && "is-active")}>
                  <span className="progress-step__mark">
                    {done && <Icon name="check" />}
                    {active && <Icon name="progress_activity" className="spin" />}
                  </span>
                  <div>
                    <strong>{title}</strong>
                    <small>{detail}</small>
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>
      </>
    );
  }

  return (
    <>
      <div className="page-top">
        <div>
          <h1>New script</h1>
          <p>Drop in your screenplay. Lumen plans the shoot days, suggests your cast and screens the story with 200 test viewers.</p>
        </div>
      </div>

      <form className="dash-grid" onSubmit={submit}>
        <section className="col-7">
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.fdx,.fountain,.txt"
            hidden
            onChange={(e) => pick(e.target.files?.[0])}
          />
          <div
            className={cn("drop", dragging && "is-dragging", file && "has-file")}
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pick(e.dataTransfer?.files?.[0]);
            }}
          >
            <span className="drop-icon">
              <Icon name={file ? "description" : "upload"} />
            </span>
            <div className="drop-title">{file ? file.name : "Drop your screenplay here"}</div>
            <div className="drop-hint">
              {file
                ? `${Math.max(1, Math.round(file.size / 1024))} KB · click to choose a different file`
                : "or click to browse. PDF, Final Draft, Fountain or plain text, up to 8 MB."}
            </div>
          </div>
        </section>

        <Card className="col-5" title="About the shoot">
          <div className="form-stack" style={{ marginTop: 18 }}>
            <label className="field">
              <span className="mono-label">Budget</span>
              <span className="money-input">
                <span>$</span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={budget ? Number(budget).toLocaleString("en-US") : ""}
                  onChange={(e) => setBudget(e.target.value.replace(/[^0-9]/g, ""))}
                />
              </span>
              <span className="field-hint">Sets how much each role and location can cost.</span>
            </label>
            <div className="field">
              <span className="mono-label">Shooting dates</span>
              <div className="date-pair">
                <input className="input" type="date" aria-label="First shoot day" value={start} onChange={(e) => setStart(e.target.value)} />
                <input className="input" type="date" aria-label="Wrap day" value={wrap} onChange={(e) => setWrap(e.target.value)} />
              </div>
            </div>
            <label className="field">
              <span className="mono-label">Where you're filming</span>
              <input
                className="input"
                placeholder="City, and state or country"
                value={locality}
                onChange={(e) => setLocality(e.target.value)}
              />
              <span className="field-hint">Lumen looks for actors who live nearby.</span>
            </label>
            <label className="field">
              <span className="mono-label">Notes for the team (optional)</span>
              <textarea
                className="textarea"
                rows={3}
                placeholder="Anything casting or scheduling should know, like a stunt-heavy finale."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            {error && (
              <div className="banner" data-tone="bad" role="alert">
                <Icon name="error" />
                <span>{error}</span>
              </div>
            )}
            <button type="submit" className="btn btn--primary btn--lg btn--block" disabled={!file}>
              Plan my production
            </button>
            {hasResults(state) && (
              <p className="field-hint">
                This replaces the current plan for {productionTitle(state, activeProduction?.name)}.
              </p>
            )}
          </div>
        </Card>
      </form>
    </>
  );
}

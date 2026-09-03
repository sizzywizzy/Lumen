import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Panel from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import MetricCard, { MetricRow } from "../../shared/MetricCard.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import Icon from "../../shared/Icon.jsx";
import { api } from "../../lib/api.js";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn } from "../../lib/utils.js";
import { STAGE_BY_PATH } from "../../shared/navigation.js";

// AI Advisors: one card per skills/<name>/SKILL.md, presented by what it does
// for the producer rather than by its agent id. The button starts a background
// run of the advisor; the card polls the run and renders the shared result
// envelope. Technical detail (agent id, SKILL.md text) sits behind a toggle.

const ICONS = {
  casting: "groups",
  scheduling: "event_note",
  "audience-simulation": "theaters",
  "cultural-research": "public",
};
const POLL_MS = 2000;
const SEVERITY_TONE = { HIGH: "bad", MEDIUM: "warn", LOW: "ok" };
const RUN_TONE = { running: "warn", complete: "ok", failed: "bad" };
const RUN_LABEL = { running: "working", complete: "done", failed: "failed" };
const CONFIDENCE_TONE = { high: "ok", medium: "warn", low: "bad" };

function fmtDetail(detail) {
  if (!detail || typeof detail !== "object") return "";
  return Object.entries(detail)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(" · ");
}

function when(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
}

function stageIcon(status) {
  if (status === "complete") return "check_circle";
  if (status === "running") return "progress_activity";
  if (status === "failed") return "error";
  return "radio_button_unchecked";
}

// Initial form values from the input schema the backend sends with each skill.
function defaultsFor(inputs = []) {
  const out = {};
  for (const input of inputs) {
    if (input.type === "multiselect") out[input.key] = input.default || [];
    else out[input.key] = input.default ?? "";
  }
  return out;
}

// Form values -> the params object the API validates. Empty numbers are omitted.
function paramsFrom(inputs = [], values = {}) {
  const params = {};
  for (const input of inputs) {
    const value = values[input.key];
    if (input.type === "multiselect") {
      if (Array.isArray(value) && value.length) params[input.key] = value;
    } else if (value !== "" && value !== null && value !== undefined) {
      params[input.key] = Number(value);
    }
  }
  return params;
}

function inputsValid(inputs = [], values = {}) {
  return inputs.every((input) => {
    const value = values[input.key];
    if (input.type === "multiselect") return (value?.length || 0) >= (input.min_selected || 0);
    if (value === "" || value === null || value === undefined) return true;
    const n = Number(value);
    if (!Number.isFinite(n)) return false;
    if (input.min !== undefined && n < input.min) return false;
    if (input.max !== undefined && n > input.max) return false;
    return true;
  });
}

function StageList({ stages = [] }) {
  return (
    <ol className="stage-list">
      {stages.map((s) => (
        <li key={s.key} className={cn("stage", `stage--${s.status}`)}>
          <Icon name={stageIcon(s.status)} size={18} className={s.status === "running" ? "spin" : undefined} />
          <span className="stage-label">{s.label}</span>
          <span className="stage-detail mono-data">{fmtDetail(s.detail)}</span>
        </li>
      ))}
    </ol>
  );
}

function InputControls({ inputs, values, onChange, disabled }) {
  if (!inputs?.length) return null;
  return (
    <div className="form-grid">
      {inputs.map((input) =>
        input.type === "multiselect" ? (
          <div className="field" key={input.key} style={{ gridColumn: "1 / -1" }}>
            <span className="mono-label">{input.label}</span>
            <div className="market-picker">
              {input.options.map((opt) => {
                const on = (values[input.key] || []).includes(opt.value);
                return (
                  <button
                    type="button"
                    key={opt.value}
                    className={cn("tag-chip", on && "on")}
                    aria-pressed={on}
                    disabled={disabled}
                    onClick={() =>
                      onChange(
                        input.key,
                        on
                          ? (values[input.key] || []).filter((v) => v !== opt.value)
                          : [...(values[input.key] || []), opt.value]
                      )
                    }
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            {input.help && <span className="body-sm muted">{input.help}</span>}
          </div>
        ) : (
          <label className="field" key={input.key}>
            <span className="mono-label">{input.label}</span>
            <input
              className="input"
              type="number"
              min={input.min}
              max={input.max}
              value={values[input.key] ?? ""}
              disabled={disabled}
              onChange={(e) => onChange(input.key, e.target.value)}
            />
            {input.help && <span className="body-sm muted">{input.help}</span>}
          </label>
        )
      )}
    </div>
  );
}

function AdvisorResult({ result, provenance }) {
  const [showData, setShowData] = useState(false);
  if (!result) return null;
  const mode = provenance?.mode;
  return (
    <div className="skill-result">
      <p className="skill-summary">{result.summary}</p>
      <div className="row row--tight">
        <span className="status-pill" data-tone={CONFIDENCE_TONE[result.confidence] || "neutral"}>
          <span className="dot" />
          confidence {result.confidence}
        </span>
        {provenance && (
          <span className="mono-label muted">
            {mode === "live" ? "live model" : mode === "mixed" ? "partly live, partly offline" : "offline fallback"}
            {provenance.models_used?.length ? ` · ${provenance.models_used.join(", ")}` : ""}
          </span>
        )}
      </div>

      {result.highlights?.length > 0 && (
        <section>
          <h4 className="mono-label muted skill-section-title">Highlights</h4>
          <ul className="point-list">
            {result.highlights.map((h, i) => (
              <li key={i}>
                <span>{h}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {result.findings?.length > 0 && (
        <section>
          <h4 className="mono-label muted skill-section-title">Findings</h4>
          <div className="findings" style={{ gap: 10 }}>
            {result.findings.map((f, i) => (
              <article className="finding" data-severity={f.severity} key={i}>
                <div className="finding-head" style={{ marginBottom: 6 }}>
                  <span className="status-pill" data-tone={SEVERITY_TONE[f.severity] || "neutral"}>
                    <span className="dot" />
                    {f.severity}
                  </span>
                  <strong>{f.title}</strong>
                  <span className="spacer" />
                  {f.ref && <span className="tag-chip">{f.ref}</span>}
                </div>
                <p className="finding-content" style={{ marginBottom: 0, fontSize: 14 }}>{f.detail}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {result.next_actions?.length > 0 && (
        <section>
          <h4 className="mono-label muted skill-section-title">Next actions</h4>
          <ol className="skill-actions-list">
            {result.next_actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        </section>
      )}

      <div>
        <button type="button" className="btn btn--link" onClick={() => setShowData((s) => !s)}>
          {showData ? "Hide the full data" : "Show the full data"}
        </button>
        {showData && (
          <div className="log-json" style={{ marginTop: 8 }}>
            <pre>{JSON.stringify(result.data ?? {}, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

function AdvisorCard({ skill, runs, canEdit, onRun, starting, focused }) {
  const [showDetails, setShowDetails] = useState(false);
  const [selected, setSelected] = useState("");
  const [values, setValues] = useState(() => defaultsFor(skill.inputs));
  const latest = runs[0] || null;
  const run = runs.find((r) => r.run_id === selected) || latest;
  const running = runs.some((r) => r.status === "running");
  const busy = running || starting;
  const valid = inputsValid(skill.inputs, values);
  const setValue = (key, value) => setValues((v) => ({ ...v, [key]: value }));

  let blocker = "";
  if (!canEdit) blocker = "Your role on this production is read-only";
  else if (!skill.runnable) blocker = "This advisor has no agent behind it yet";
  else if (!valid) blocker = "Check the inputs above";

  return (
    <Panel className="span-6 panel--pad skill-card" id={`advisor-${skill.name}`} data-focus={focused ? "true" : undefined}>
      <div className="skill-head">
        <Icon name={ICONS[skill.name] || "auto_awesome"} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3>{skill.title}</h3>
          <p className="skill-desc" style={{ marginTop: 6 }}>{skill.description}</p>
        </div>
        {latest && (
          <span className="status-pill" data-tone={RUN_TONE[latest.status] || "neutral"}>
            <span className="dot" />
            {RUN_LABEL[latest.status] || latest.status}
          </span>
        )}
      </div>

      <InputControls inputs={skill.inputs} values={values} onChange={setValue} disabled={busy || !canEdit} />

      <div className="skill-actions">
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => onRun(skill, paramsFrom(skill.inputs, values))}
          disabled={busy || Boolean(blocker)}
          title={blocker || undefined}
        >
          <Icon name={busy ? "progress_activity" : "play_arrow"} className={busy ? "spin" : undefined} />
          {running ? "Working…" : starting ? "Starting…" : latest ? `${skill.cta} again` : skill.cta}
        </button>
        <button type="button" className="btn btn--ghost" onClick={() => setShowDetails((s) => !s)}>
          <Icon name="info" />
          {showDetails ? "Hide details" : "How it works"}
        </button>
        {runs.length > 1 && (
          <div className="select-wrap">
            <select
              className="select"
              value={run?.run_id || ""}
              aria-label="Previous runs"
              onChange={(e) => setSelected(e.target.value)}
            >
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {when(r.created_at)} · {RUN_LABEL[r.status] || r.status}
                </option>
              ))}
            </select>
            <Icon name="arrow_drop_down" />
          </div>
        )}
      </div>

      {showDetails && (
        <div className="skill-instructions">
          <p className="mono-label muted" style={{ marginBottom: 8 }}>
            {skill.agent} · phase {skill.phase} · gemini {skill.model} · {skill.path} v{skill.version}
          </p>
          <pre>{skill.instructions}</pre>
        </div>
      )}

      {run ? (
        <>
          <div className="agent-activity">
            <div className="row row--tight" style={{ marginBottom: 8 }}>
              <Icon name="smart_toy" style={{ color: "var(--primary)" }} />
              <strong className="mono-label">{skill.title}</strong>
              <span className="mono-label muted">{when(run.created_at)}</span>
            </div>
            <StageList stages={run.stages} />
          </div>
          {run.status === "failed" && (
            <div className="banner" data-tone="bad" role="alert">
              <Icon name="error" />
              <span>{run.error || "The advisor could not finish."}</span>
            </div>
          )}
          <AdvisorResult result={run.result} provenance={run.provenance} />
        </>
      ) : (
        <EmptyState icon="play_circle" title="Not run yet">
          Press the button to let this advisor work through the production. Results appear here and stay
          on record.
        </EmptyState>
      )}
    </Panel>
  );
}

export default function AdvisorsPage() {
  const { projectId, canEdit, refreshState } = useProject();
  const [params] = useSearchParams();
  const focus = params.get("advisor");

  const [skills, setSkills] = useState(null);
  const [runs, setRuns] = useState([]);
  const [starting, setStarting] = useState(null);
  const [error, setError] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listSkills()
      .then((d) => !cancelled && setSkills(d.skills))
      .catch((e) => !cancelled && setError(String(e.message || e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const loadRuns = useCallback(async () => {
    if (!projectId) return [];
    const { runs: list } = await api.listSkillRuns(projectId);
    setRuns(list);
    return list;
  }, [projectId]);

  useEffect(() => {
    loadRuns().catch((e) => setError(String(e.message || e)));
  }, [loadRuns]);

  // Poll while any run is in flight so the stage checklist advances live, then
  // pull the refreshed GlobalState so the terminal shows the agents' traffic.
  const anyRunning = runs.some((r) => r.status === "running");
  useEffect(() => {
    clearInterval(pollRef.current);
    if (!anyRunning) return undefined;
    pollRef.current = setInterval(async () => {
      try {
        const list = await loadRuns();
        if (!list.some((r) => r.status === "running")) {
          clearInterval(pollRef.current);
          refreshState().catch(() => {});
        }
      } catch (e) {
        clearInterval(pollRef.current);
        setError(String(e.message || e));
      }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [anyRunning, loadRuns, refreshState]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  // Deep link from the phase pages: /advisors?advisor=casting scrolls to that card.
  useEffect(() => {
    if (!focus || !skills) return;
    document.getElementById(`advisor-${focus}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus, skills]);

  async function run(skill, runParams) {
    if (!projectId) {
      setError("Pick a production first.");
      return;
    }
    setStarting(skill.name);
    setError("");
    try {
      await api.runSkill(skill.name, projectId, runParams);
      await loadRuns();
    } catch (e) {
      setError(`${skill.title}: ${e.message || e}`);
    } finally {
      setStarting(null);
    }
  }

  const runsBySkill = useMemo(() => {
    const map = {};
    for (const r of runs) {
      if (!map[r.skill]) map[r.skill] = [];
      map[r.skill].push(r);
    }
    return map;
  }, [runs]);

  const completed = runs.filter((r) => r.status === "complete").length;

  return (
    <>
      <PageHeader
        title="AI Advisors"
        sub="Ask an advisor to work through this production and come back with a recommendation. Each one follows a written procedure, runs in the background, and reports what it found, how sure it is, and what to do next."
        meta={STAGE_BY_PATH["/advisors"]}
        actions={
          <MetricRow>
            <MetricCard label="Advisors" value={skills ? skills.length : "…"} />
            <MetricCard label="Runs" value={runs.length} />
            <MetricCard label="Completed" value={completed} tone={completed ? "ok" : "plain"} />
          </MetricRow>
        }
      />

      {error && (
        <div className="banner" data-tone="bad" role="alert">
          <Icon name="error" />
          <span>{error}</span>
        </div>
      )}

      {!projectId && (
        <div className="banner" data-tone="warn" role="note">
          <Icon name="info" />
          <span>Start a production on Script Intake first, then the advisors can work on it.</span>
        </div>
      )}

      {!skills ? (
        <Panel>
          <EmptyState icon="progress_activity" title="Loading advisors…" />
        </Panel>
      ) : skills.length === 0 ? (
        <Panel>
          <EmptyState icon="folder_off" title="No advisors available">
            No SKILL.md files were found on the server. See skills.md in the repository.
          </EmptyState>
        </Panel>
      ) : (
        <div className="grid">
          {skills.map((s) => (
            <AdvisorCard
              key={s.name}
              skill={s}
              runs={runsBySkill[s.name] || []}
              canEdit={canEdit && Boolean(projectId)}
              onRun={run}
              starting={starting === s.name}
              focused={focus === s.name}
            />
          ))}
        </div>
      )}
    </>
  );
}

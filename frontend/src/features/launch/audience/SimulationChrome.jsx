import Icon from "../../../shared/Icon.jsx";
import Meter from "../../../shared/Meter.jsx";
import { cn } from "../../../lib/utils.js";

// Small presentational pieces shared by the audience-simulation dashboard.
// Kept in the existing design system — panels, meters, status pills, tokens.

/** The disclaimer is not decoration: it ships with every view of these numbers. */
export function SimulationDisclaimer({ text, provenance }) {
  const mode = provenance?.mode;
  return (
    <div className="banner sim-disclaimer" data-tone="warn" role="note">
      <Icon name="science" />
      <div>
        <strong>Simulated Audience Feedback</strong>
        <p style={{ marginTop: 4 }}>{text}</p>
        {mode && (
          <p className="mono-label" style={{ marginTop: 6, opacity: 0.85 }}>
            Model output: {mode === "live" ? "live Gemini" : mode === "mixed" ? "partly live, partly offline fallback" : "offline fallback (no live model)"}
            {provenance?.models_used?.length ? ` · ${provenance.models_used.join(", ")}` : ""}
            {provenance?.research_enabled ? " · web research on" : " · web research off"}
          </p>
        )}
      </div>
    </div>
  );
}

/** Tells the producer exactly which material a run will analyse. */
export function SourceMaterialNotice({ source, overridden }) {
  if (!source) return null;

  if (overridden) {
    return (
      <div className="source-note" data-kind="override">
        <Icon name="edit_note" size={18} />
        <span>Using the material pasted below, instead of the stored script.</span>
      </div>
    );
  }

  if (source.kind === "uploaded_script") {
    return (
      <div className="source-note" data-kind="script">
        <Icon name="description" size={18} />
        <span>
          Will analyse <strong>{source.filename}</strong> from Script Intake —{" "}
          {source.char_count?.toLocaleString()} characters
          {source.format ? ` · ${source.format}` : ""}
          {source.truncated ? " · truncated to the first 400k" : ""}.
        </span>
      </div>
    );
  }

  if (source.kind === "script_context") {
    return (
      <div className="source-note" data-kind="thin">
        <Icon name="warning" size={18} />
        <span>
          No screenplay uploaded yet — this would analyse only the project's logline and scene list.
          Drop a script on <strong>Script Intake</strong> for a fuller read.
        </span>
      </div>
    );
  }

  return (
    <div className="source-note" data-kind="thin">
      <Icon name="warning" size={18} />
      <span>No stored material. Paste a synopsis below, or upload a script on Script Intake.</span>
    </div>
  );
}

/** Agent stage checklist — real per-stage status streamed from the backend. */
export function AgentActivity({ stages = [], status }) {
  return (
    <div className="agent-activity">
      <div className="row row--tight" style={{ marginBottom: 12 }}>
        <Icon name="smart_toy" style={{ color: "var(--primary)" }} />
        <strong className="mono-label">Audience Simulation Agent</strong>
        {status === "running" && <span className="status-pill" data-tone="warn"><span className="dot" />working</span>}
        {status === "complete" && <span className="status-pill" data-tone="ok"><span className="dot" />complete</span>}
        {status === "failed" && <span className="status-pill" data-tone="bad"><span className="dot" />failed</span>}
      </div>
      <ol className="stage-list">
        {stages.map((s) => (
          <li key={s.key} className={cn("stage", `stage--${s.status}`)}>
            <Icon
              name={
                s.status === "complete" ? "check_circle"
                  : s.status === "running" ? "progress_activity"
                  : s.status === "failed" ? "error" : "radio_button_unchecked"
              }
              size={18}
              className={s.status === "running" ? "spin" : undefined}
            />
            <span className="stage-label">{s.label}</span>
            <span className="stage-detail mono-data">{formatDetail(s.detail)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function formatDetail(detail) {
  if (!detail || typeof detail !== "object") return "";
  const parts = [];
  if (detail.personas) parts.push(`${detail.personas} personas`);
  if (detail.cohorts) parts.push(`${detail.cohorts} cohorts`);
  if (detail.cohorts_scored) parts.push(`${detail.cohorts_scored} scored`);
  if (detail.responses) parts.push(`${detail.responses} responses`);
  if (detail.overall_score) parts.push(`${detail.overall_score}/10`);
  if (detail.genres?.length) parts.push(detail.genres.join(", "));
  if (detail.completeness) parts.push(detail.completeness.replace(/_/g, " "));
  if (detail.markets !== undefined && !detail.findings) parts.push(`${detail.markets} markets`);
  if (detail.findings) {
    const { HIGH = 0, MEDIUM = 0, LOW = 0 } = detail.findings;
    parts.push(`${HIGH} high · ${MEDIUM} med · ${LOW} low`);
  }
  return parts.join(" · ");
}

/** Rating distribution — the point is that it is not a single average. */
export function RatingHistogram({ histogram = {}, mean }) {
  const buckets = Object.entries(histogram)
    .map(([score, count]) => ({ score: Number(score), count }))
    .sort((a, b) => b.score - a.score);
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const total = buckets.reduce((sum, b) => sum + b.count, 0) || 1;

  return (
    <div className="histogram">
      {buckets.map((b) => (
        <div className="histogram-row" key={b.score}>
          <span className="histogram-score mono-data">{b.score}</span>
          <div className="histogram-track">
            <div
              className={cn("histogram-bar", mean && Math.round(mean) === b.score && "at-mean")}
              style={{ width: `${(b.count / max) * 100}%` }}
            />
          </div>
          <span className="histogram-count mono-data">
            {b.count ? `${b.count} (${Math.round((b.count / total) * 100)}%)` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

/** One audience-segment breakdown table. */
export function SegmentBars({ rows = [], overall }) {
  if (!rows.length) return null;
  return (
    <div className="segment-list">
      {rows.map((row) => {
        const delta = overall ? row.mean_score - overall : 0;
        return (
          <div className="segment-row" key={`${row.dimension}-${row.segment}`}>
            <div className="segment-head">
              <span className="segment-name">{row.segment}</span>
              <span className="mono-data">
                <strong>{row.mean_score.toFixed(1)}</strong>
                {overall ? (
                  <span className={cn(delta >= 0 ? "text-ok" : "text-warn")} style={{ marginLeft: 6 }}>
                    {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
                  </span>
                ) : null}
              </span>
            </div>
            <Meter value={row.mean_score * 10} tone={delta >= 0 ? undefined : "warn"} thin />
            <div className="segment-meta mono-data muted">
              n={row.n} · would watch {row.would_watch_pct}% · recommend {row.would_recommend_pct}% · spread ±{row.spread}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const SEVERITY_TONE = { HIGH: "bad", MEDIUM: "warn", LOW: "ok" };

/** Cultural sensitivity finding card. */
export function SensitivityFinding({ finding, marketName }) {
  return (
    <div className="finding" data-severity={finding.severity}>
      <div className="finding-head">
        <span className="status-pill" data-tone={SEVERITY_TONE[finding.severity] || "neutral"}>
          <span className="dot" />
          {finding.severity}
        </span>
        <span className="mono-label muted">{marketName}</span>
        <span className="spacer" />
        <span className={cn("tag-chip", finding.basis === "researched" && "on")}>
          {finding.basis === "researched" ? "researched" : "AI interpretation"}
        </span>
      </div>
      <p className="finding-content">{finding.content_detected}</p>
      <dl className="finding-body">
        <div>
          <dt>Why flagged</dt>
          <dd>{finding.why}</dd>
        </div>
        {finding.potential_audience_affected && (
          <div>
            <dt>Who may react</dt>
            <dd>{finding.potential_audience_affected}</dd>
          </div>
        )}
        {finding.pr_consideration && (
          <div>
            <dt>PR consideration</dt>
            <dd>{finding.pr_consideration}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

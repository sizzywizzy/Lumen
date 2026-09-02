import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Panel, { PanelHead } from "../../../shared/Panel.jsx";
import MetricCard, { MetricRow } from "../../../shared/MetricCard.jsx";
import EmptyState from "../../../shared/EmptyState.jsx";
import Icon from "../../../shared/Icon.jsx";
import {
  AgentActivity,
  SourceMaterialNotice,
  RatingHistogram,
  SegmentBars,
  SensitivityFinding,
  SimulationDisclaimer,
} from "./SimulationChrome.jsx";
import { api } from "../../../lib/api.js";
import { useProject } from "../../../shared/ProjectContext.jsx";
import { cn } from "../../../lib/utils.js";

const SEGMENT_TABS = [
  { key: "age_group", label: "Age" },
  { key: "market", label: "Market" },
  { key: "genre_affinity", label: "Genre affinity" },
  { key: "viewing_frequency", label: "Viewing habits" },
  { key: "taste_profile", label: "Taste" },
  { key: "pacing_tolerance", label: "Pacing tolerance" },
];

const POLL_MS = 2500;

export default function AudienceSimulation() {
  const { projectId, canEdit } = useProject();

  const [meta, setMeta] = useState(null); // list + capabilities + disclaimer
  const [history, setHistory] = useState([]);
  const [current, setCurrent] = useState(null);
  const [segmentTab, setSegmentTab] = useState("age_group");
  const [compareId, setCompareId] = useState("");
  const [compare, setCompare] = useState(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    material: "",
    material_label: "",
    panel_size: 500,
    markets: ["US", "IN", "GB"],
    seed: "",
  });
  const pollRef = useRef(null);

  const loadList = useCallback(async () => {
    if (!projectId) return null;
    const data = await api.listSimulations(projectId);
    setMeta(data);
    setHistory(data.simulations);
    return data.simulations;
  }, [projectId]);

  // Initial load: fetch history and open the newest completed run.
  useEffect(() => {
    let cancelled = false;
    loadList()
      .then(async (sims) => {
        if (cancelled || !sims?.length) return;
        const latest = sims[0];
        const detail = await api.getSimulation(projectId, latest.simulation_id);
        if (!cancelled) setCurrent(detail);
      })
      .catch((e) => !cancelled && setError(String(e.message || e)));
    return () => {
      cancelled = true;
    };
  }, [loadList, projectId]);

  // Poll while a run is in flight so the stage checklist advances live.
  useEffect(() => {
    clearInterval(pollRef.current);
    if (current?.status !== "running") return undefined;
    pollRef.current = setInterval(async () => {
      try {
        const detail = await api.getSimulation(projectId, current.simulation_id);
        setCurrent(detail);
        if (detail.status !== "running") {
          clearInterval(pollRef.current);
          loadList().catch(() => {});
        }
      } catch (e) {
        clearInterval(pollRef.current);
        setError(String(e.message || e));
      }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [current?.status, current?.simulation_id, projectId, loadList]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  async function startRun(e) {
    e?.preventDefault();
    setStarting(true);
    setError("");
    try {
      const payload = {
        material: form.material.trim() || undefined,
        material_label: form.material_label.trim(),
        panel_size: Number(form.panel_size),
        markets: form.markets,
        ...(form.seed !== "" ? { seed: Number(form.seed) } : {}),
      };
      const started = await api.startSimulation(projectId, payload);
      const detail = await api.getSimulation(projectId, started.simulation_id);
      setCurrent(detail);
      setShowForm(false);
      loadList().catch(() => {});
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setStarting(false);
    }
  }

  async function openSimulation(id) {
    setError("");
    try {
      setCurrent(await api.getSimulation(projectId, id));
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  useEffect(() => {
    if (!compareId) return setCompare(null);
    api.getSimulation(projectId, compareId).then(setCompare).catch(() => setCompare(null));
  }, [compareId, projectId]);

  const report = current?.report;
  const segments = report?.segments?.[segmentTab] || [];
  const toggleMarket = (code) =>
    setForm((f) => ({
      ...f,
      markets: f.markets.includes(code) ? f.markets.filter((m) => m !== code) : [...f.markets, code],
    }));

  const delta = useMemo(() => {
    if (!compare?.report || !report) return null;
    return {
      overall: +(report.overall_score - compare.report.overall_score).toFixed(2),
      watch: +(report.would_watch_pct - compare.report.would_watch_pct).toFixed(1),
      recommend: +(report.would_recommend_pct - compare.report.would_recommend_pct).toFixed(1),
    };
  }, [compare, report]);

  return (
    <div className="stack">
      {meta?.disclaimer && (
        <SimulationDisclaimer text={meta.disclaimer} provenance={current?.provenance} />
      )}

      {error && (
        <div className="banner" data-tone="bad" role="alert">
          <Icon name="error" />
          <span>{error}</span>
        </div>
      )}

      {/* ---- run controls ---- */}
      <Panel className="panel--pad">
        <div className="between" style={{ marginBottom: showForm ? 20 : 0 }}>
          <div>
            <h3 className="headline-md" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name="groups_3" style={{ color: "var(--primary)" }} />
              Audience Simulation
            </h3>
            <p className="muted body-sm" style={{ marginTop: 6 }}>
              {history.length
                ? `${history.length} run${history.length === 1 ? "" : "s"} on record · compare runs after a script revision`
                : "No runs yet for this production."}
            </p>
          </div>
          <div className="row row--tight">
            {history.length > 1 && (
              <div className="select-wrap">
                <select
                  className="select"
                  value={compareId}
                  aria-label="Compare with an earlier run"
                  onChange={(e) => setCompareId(e.target.value)}
                >
                  <option value="">Compare with…</option>
                  {history
                    .filter((h) => h.simulation_id !== current?.simulation_id && h.status === "complete")
                    .map((h) => (
                      <option key={h.simulation_id} value={h.simulation_id}>
                        {h.material_label || h.simulation_id} · {h.overall_score ?? "—"}/10
                      </option>
                    ))}
                </select>
                <Icon name="arrow_drop_down" />
              </div>
            )}
            <button
              type="button"
              className={cn("btn", showForm ? "btn--ghost" : "btn--primary")}
              onClick={() => setShowForm((v) => !v)}
              disabled={!canEdit}
              title={canEdit ? undefined : "Your role on this production is read-only"}
            >
              <Icon name={showForm ? "close" : "science"} />
              {showForm ? "Cancel" : "New simulation"}
            </button>
          </div>
        </div>

        {showForm && (
          <form className="stack" onSubmit={startRun}>
            <div className="field">
              <span className="mono-label">Movie material</span>
              <SourceMaterialNotice source={meta?.source_material} overridden={!!form.material.trim()} />
              <textarea
                className="textarea"
                rows={5}
                placeholder={
                  meta?.source_material?.kind === "uploaded_script"
                    ? "Leave blank to analyse the screenplay from Script Intake, or paste different material to override it."
                    : "Paste a synopsis, treatment or script."
                }
                value={form.material}
                onChange={(e) => setForm({ ...form, material: e.target.value })}
              />
              <span className="body-sm muted">
                The agent analyses only this material — it will not invent scenes or themes.
              </span>
            </div>
            <div className="form-grid">
              <label className="field">
                <span className="mono-label">Label</span>
                <input
                  className="input"
                  placeholder="Draft 2 — tightened act two"
                  value={form.material_label}
                  onChange={(e) => setForm({ ...form, material_label: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="mono-label">Panel size</span>
                <input
                  className="input"
                  type="number"
                  min="20"
                  max={meta?.capabilities?.max_panel_size || 1000}
                  value={form.panel_size}
                  onChange={(e) => setForm({ ...form, panel_size: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="mono-label">Seed (optional)</span>
                <input
                  className="input"
                  type="number"
                  placeholder="reuse to reproduce a panel"
                  value={form.seed}
                  onChange={(e) => setForm({ ...form, seed: e.target.value })}
                />
              </label>
            </div>
            <div className="field">
              <span className="mono-label">Target markets for the sensitivity review</span>
              <div className="market-picker">
                {(meta?.capabilities?.markets || []).map((m) => (
                  <button
                    type="button"
                    key={m.code}
                    className={cn("tag-chip", form.markets.includes(m.code) && "on")}
                    onClick={() => toggleMarket(m.code)}
                    aria-pressed={form.markets.includes(m.code)}
                  >
                    {m.name}
                  </button>
                ))}
              </div>
              {!meta?.capabilities?.research_enabled && (
                <span className="body-sm muted">
                  Web research is off (no Tavily key) — findings will be marked “AI interpretation”, never
                  presented as verified regulation.
                </span>
              )}
            </div>
            <div className="form-actions">
              <button type="submit" className="btn btn--primary" disabled={starting || !form.markets.length}>
                <Icon name={starting ? "progress_activity" : "play_arrow"} className={starting ? "spin" : undefined} />
                {starting ? "Starting…" : "Run simulation"}
              </button>
            </div>
          </form>
        )}
      </Panel>

      {!current && !showForm && (
        <Panel>
          <EmptyState icon="groups_3" title="No audience simulation yet">
            Run one to see how a synthetic panel of viewers might respond to this material, broken out by
            audience segment.
          </EmptyState>
        </Panel>
      )}

      {current && (
        <>
          {/* ---- agent activity ---- */}
          <Panel className="panel--pad">
            <AgentActivity stages={current.stages} status={current.status} />
            {current.status === "failed" && (
              <div className="banner" data-tone="bad" style={{ marginTop: 12 }}>
                <Icon name="error" />
                <span>{current.error}</span>
              </div>
            )}
          </Panel>

          {report && (
            <>
              {/* ---- headline numbers ---- */}
              <MetricRow>
                <MetricCard label="Simulated panel" value={report.panel_size} tone="plain" />
                <MetricCard label="Overall score" value={`${report.overall_score} / 10`} />
                <MetricCard label="Would watch" value={`${report.would_watch_pct}%`} tone="ok" />
                <MetricCard label="Would recommend" value={`${report.would_recommend_pct}%`} tone="ok" />
                <MetricCard label="Would finish" value={`${report.would_finish_pct}%`} tone="plain" />
              </MetricRow>

              {delta && (
                <div className="banner" data-tone="warn">
                  <Icon name="compare_arrows" />
                  <span>
                    vs <strong>{compare.config?.material_label || compare.simulation_id}</strong>:{" "}
                    overall <strong className={delta.overall >= 0 ? "text-ok" : "text-bad"}>
                      {delta.overall >= 0 ? "+" : ""}{delta.overall}
                    </strong>{" "}
                    · would watch {delta.watch >= 0 ? "+" : ""}{delta.watch}pp · recommend{" "}
                    {delta.recommend >= 0 ? "+" : ""}{delta.recommend}pp
                  </span>
                </div>
              )}

              <div className="grid">
                {/* ---- distribution ---- */}
                <Panel className="span-6 panel--clip panel--flex">
                  <PanelHead title="Response distribution" icon="bar_chart">
                    <span className="mono-data muted">spread ±{report.score_spread}</span>
                  </PanelHead>
                  <div className="panel--pad">
                    <RatingHistogram histogram={report.rating_histogram} mean={report.overall_score} />
                    <p className="body-sm muted" style={{ marginTop: 12 }}>
                      Median {report.median_score} · positive {report.sentiment_split.positive}% · mixed{" "}
                      {report.sentiment_split.mixed}% · negative {report.sentiment_split.negative}%
                    </p>
                  </div>
                </Panel>

                {/* ---- segments ---- */}
                <Panel className="span-6 panel--clip panel--flex">
                  <PanelHead title="Audience breakdown" icon="donut_small" />
                  <div className="panel--pad stack--sm">
                    <div className="pill-toggle" style={{ flexWrap: "wrap" }}>
                      {SEGMENT_TABS.map((t) => (
                        <button
                          key={t.key}
                          type="button"
                          className={cn(segmentTab === t.key && "active")}
                          onClick={() => setSegmentTab(t.key)}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                    <SegmentBars rows={segments} overall={report.overall_score} />
                  </div>
                </Panel>

                {/* ---- qualitative ---- */}
                <Panel className="span-4 panel--pad">
                  <h4 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="thumb_up" />
                    What the panel responded to
                  </h4>
                  <ul className="point-list">
                    {report.liked.map((p) => (
                      <li key={p.point}>
                        <span>{p.point}</span>
                        <span className="mono-data muted">{p.share_pct}%</span>
                      </li>
                    ))}
                    {!report.liked.length && <li className="muted">No consistent positives surfaced.</li>}
                  </ul>
                </Panel>
                <Panel className="span-4 panel--pad">
                  <h4 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="thumb_down" />
                    What held them back
                  </h4>
                  <ul className="point-list">
                    {report.disliked.map((p) => (
                      <li key={p.point}>
                        <span>{p.point}</span>
                        <span className="mono-data muted">{p.share_pct}%</span>
                      </li>
                    ))}
                    {!report.disliked.length && <li className="muted">No consistent negatives surfaced.</li>}
                  </ul>
                </Panel>
                <Panel className="span-4 panel--pad">
                  <h4 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="call_split" />
                    Most polarizing
                  </h4>
                  <ul className="point-list">
                    {report.polarizing.map((p) => (
                      <li key={p.point}>
                        <span>{p.point}</span>
                        <span className="mono-data muted">{p.share_pct}%</span>
                      </li>
                    ))}
                    {!report.polarizing.length && <li className="muted">Nothing strongly divided the panel.</li>}
                  </ul>
                  <div className="divider-line" />
                  <p className="mono-label muted" style={{ marginBottom: 6 }}>Widest score spread</p>
                  {report.most_divisive_dimensions.map((d) => (
                    <div className="between mono-data" key={d.dimension} style={{ padding: "3px 0" }}>
                      <span>{d.dimension.replace(/_/g, " ")}</span>
                      <span className="muted">±{d.spread} · mean {d.mean}</span>
                    </div>
                  ))}
                </Panel>

                {/* ---- strongest / weakest ---- */}
                <Panel className="span-6 panel--pad">
                  <h4 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="trending_up" />
                    Strongest segments
                  </h4>
                  <SegmentBars rows={report.strongest_segments} overall={report.overall_score} />
                </Panel>
                <Panel className="span-6 panel--pad">
                  <h4 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="trending_down" />
                    Weakest segments
                  </h4>
                  <SegmentBars rows={report.weakest_segments} overall={report.overall_score} />
                </Panel>

                {/* ---- cultural sensitivity ---- */}
                <Panel className="span-12 panel--clip">
                  <PanelHead title="Cultural sensitivity" icon="public">
                    <div className="row row--tight">
                      {["HIGH", "MEDIUM", "LOW"].map((level) => (
                        <span
                          key={level}
                          className="status-pill"
                          data-tone={level === "HIGH" ? "bad" : level === "MEDIUM" ? "warn" : "ok"}
                        >
                          <span className="dot" />
                          {current.sensitivity?.severity_counts?.[level] ?? 0} {level.toLowerCase()}
                        </span>
                      ))}
                    </div>
                  </PanelHead>
                  <div className="panel--pad">
                    {!current.sensitivity?.markets?.length ? (
                      <EmptyState icon="public_off" title="No market findings">
                        No sensitivity concerns were raised for the selected markets from this material.
                      </EmptyState>
                    ) : (
                      <div className="findings">
                        {current.sensitivity.markets.map((market) => (
                          <div key={market.market} className="market-block">
                            <div className="between" style={{ marginBottom: 8 }}>
                              <strong className="body-md">{market.market}</strong>
                              <span className="mono-data muted">{market.findings?.length || 0} findings</span>
                            </div>
                            {(market.findings || []).map((f, i) => (
                              <SensitivityFinding key={i} finding={f} marketName={market.market} />
                            ))}
                            {market.overall_note && (
                              <p className="body-sm muted" style={{ marginTop: 8 }}>{market.overall_note}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {current.sensitivity?.sources?.length > 0 && (
                      <div className="sources">
                        <p className="mono-label muted" style={{ marginBottom: 6 }}>Researched sources</p>
                        {current.sensitivity.sources.map((s, i) => (
                          <a key={i} href={s.url} target="_blank" rel="noreferrer noopener" className="source-link">
                            <Icon name="link" size={14} />
                            {s.title || s.url}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </Panel>

                {/* ---- PR ---- */}
                {current.recommendations && (
                  <Panel className="span-12 panel--pad">
                    <h4 className="panel-title mono-label" style={{ marginBottom: 16 }}>
                      <Icon name="campaign" />
                      PR recommendations — for the team to weigh, not decisions
                    </h4>
                    <dl className="rec-grid">
                      {[
                        ["Positioning", current.recommendations.positioning],
                        ["Marketing angle", current.recommendations.marketing_angle],
                        ["Primary audience", current.recommendations.primary_audience],
                        ["Secondary audience", current.recommendations.secondary_audience],
                        ["Approach carefully", current.recommendations.approach_carefully],
                        ["Potential controversy", current.recommendations.potential_controversy],
                        ["Messaging to avoid", current.recommendations.messaging_to_avoid],
                      ]
                        .filter(([, v]) => v)
                        .map(([k, v]) => (
                          <div key={k}>
                            <dt>{k}</dt>
                            <dd>{v}</dd>
                          </div>
                        ))}
                    </dl>
                    {current.recommendations.trailer_considerations?.length > 0 && (
                      <>
                        <p className="mono-label muted" style={{ margin: "16px 0 6px" }}>Trailer considerations</p>
                        <ul className="point-list">
                          {current.recommendations.trailer_considerations.map((t, i) => (
                            <li key={i}><span>{t}</span></li>
                          ))}
                        </ul>
                      </>
                    )}
                  </Panel>
                )}

                {/* ---- reproducibility ---- */}
                <Panel className="span-12 panel--pad">
                  <h4 className="panel-title mono-label" style={{ marginBottom: 12 }}>
                    <Icon name="fingerprint" />
                    Run record
                  </h4>
                  <dl className="rec-grid mono-data">
                    <div><dt>Simulation</dt><dd>{current.simulation_id}</dd></div>
                    <div><dt>Material</dt><dd>{current.config?.material_label} ({current.config?.material_chars} chars)</dd></div>
                    <div><dt>Material fingerprint</dt><dd>{current.config?.material_fingerprint}</dd></div>
                    <div><dt>Panel / seed</dt><dd>{current.config?.panel_size} · seed {current.config?.seed}</dd></div>
                    <div><dt>Models</dt><dd>{current.provenance?.models_used?.join(", ") || "offline fallback"}</dd></div>
                    <div><dt>Created</dt><dd>{current.created_at}</dd></div>
                  </dl>
                </Panel>
              </div>
            </>
          )}

          {/* ---- history ---- */}
          {history.length > 1 && (
            <Panel className="panel--clip">
              <PanelHead title="Simulation history" icon="history" />
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Run</th><th>Material</th><th>Panel</th>
                      <th className="num">Overall</th><th className="num">Would watch</th><th>Mode</th><th />
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((h) => (
                      <tr key={h.simulation_id} className={cn(h.simulation_id === current?.simulation_id && "current-row")}>
                        <td className="muted">{h.created_at?.slice(0, 16).replace("T", " ")}</td>
                        <td>{h.material_label || "—"}</td>
                        <td>{h.panel_size}</td>
                        <td className="num">{h.overall_score ?? "—"}</td>
                        <td className="num">{h.would_watch_pct != null ? `${h.would_watch_pct}%` : "—"}</td>
                        <td>
                          <span className="status-pill" data-tone={h.mode === "live" ? "ok" : h.mode === "mixed" ? "warn" : "neutral"}>
                            <span className="dot" />{h.mode || h.status}
                          </span>
                        </td>
                        <td className="num">
                          {h.simulation_id !== current?.simulation_id && (
                            <button type="button" className="btn btn--ghost" onClick={() => openSimulation(h.simulation_id)}>
                              Open
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

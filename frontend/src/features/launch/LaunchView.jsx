import { useMemo, useState } from "react";
import Panel, { PanelFoot, PanelHead } from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import MetricCard, { MetricRow } from "../../shared/MetricCard.jsx";
import Meter from "../../shared/Meter.jsx";
import { RadialGauge } from "../../shared/Gauge.jsx";
import StatusBadge from "../../shared/StatusBadge.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import Icon from "../../shared/Icon.jsx";
import LiveAgentTerminal from "../../shared/LiveAgentTerminal.jsx";
import AudienceSimulation from "./audience/AudienceSimulation.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn, statusLabel } from "../../lib/utils.js";
import { STAGE_BY_PATH } from "../../shared/navigation.js";

// Agents that belong to the launch half of the pipeline — the side terminal on
// this page shows only their traffic, so it reads as an audience-sim console.
const LAUNCH_AGENTS =
  /persona|viewer|critic|aggregation|synthesis|recut|telemetry|campaign|reel_cutter|visual|market_synergy|pr_shield|publisher/i;

// Phase V & VI — projected reception, scene heatmap and marketing asset
// readiness. Layout follows the Stitch "Launch Analytics" bento.
export default function LaunchView() {
  const { state, events, revealed, running, runPipeline } = useProject();
  // In-page tabs keep the existing launch analytics intact while giving the
  // audience simulator the room it needs. Sidebar navigation is unchanged.
  const [tab, setTab] = useState("audience");
  const report = state?.audience_report;
  const assets = state?.marketing_assets || [];

  const heatmap = useMemo(() => {
    const entries = Object.entries(report?.heatmap || {});
    const max = Math.max(1, ...entries.map(([, v]) => Number(v) || 0));
    return entries
      .map(([scene, score]) => ({
        scene,
        score: Number(score) || 0,
        pct: ((Number(score) || 0) / max) * 100,
        weakest: scene === report?.weakest_scene_id,
      }))
      .sort((a, b) => a.score - b.score);
  }, [report]);

  const launchEvents = useMemo(
    () => events.slice(0, revealed).filter((e) => LAUNCH_AGENTS.test(e.sender || "")),
    [events, revealed]
  );

  const approved = assets.filter((a) => ["APPROVED", "SCHEDULED", "POSTED"].includes(a.status)).length;
  const blocked = assets.filter((a) => a.status === "BLOCKED").length;
  const hasReport = Boolean(report && (report.tomatometer || report.audience_score));

  return (
    <>
      <PageHeader
        title="Launch Analytics"
        sub="Sentiment aggregation, scene-level engagement predictions and asset readiness tracking."
        meta={STAGE_BY_PATH["/marketing"]}
        actions={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => window.print()}>
              <Icon name="download" />
              Export report
            </button>
            {/* the real pipeline action, presented as the Stitch "Run Simulation" CTA */}
            <button type="button" className="btn btn--primary" onClick={runPipeline} disabled={running}>
              <Icon name={running ? "progress_activity" : "play_arrow"} className={running ? "spin" : undefined} />
              {running ? "Simulating…" : "Run simulation"}
            </button>
          </>
        }
      />

      <div className="pill-toggle" style={{ alignSelf: "flex-start" }}>
        <button type="button" className={cn(tab === "audience" && "active")} onClick={() => setTab("audience")}>
          Audience simulation
        </button>
        <button type="button" className={cn(tab === "analytics" && "active")} onClick={() => setTab("analytics")}>
          Launch analytics
        </button>
      </div>

      {tab === "audience" && <AudienceSimulation />}

      {tab === "analytics" && (
      <div className="grid">
        {/* Projected reception */}
        <Panel className="span-8 panel--pad">
          <h3 className="headline-md" style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="speed" style={{ color: "var(--primary)" }} />
            Projected Reception
          </h3>
          {!hasReport ? (
            <EmptyState
              icon={running ? "progress_activity" : "theaters"}
              title={running ? "Audience agents are screening…" : "No screening data yet"}
            >
              Run the pipeline to let the audience-simulation agents score the cut.
            </EmptyState>
          ) : (
            <div className="gauge-pair">
              <RadialGauge
                value={report.tomatometer}
                label="Critics"
                tone="primary"
                footer={
                  <span className="status-pill" data-tone={report.tomatometer >= 60 ? "ok" : "warn"}>
                    <span className="dot" />
                    {report.tomatometer >= 60 ? "Certified direction" : "Below threshold"}
                  </span>
                }
              />
              <RadialGauge
                value={report.audience_score}
                label="Audience"
                tone="secondary"
                footer={
                  <span className="status-pill" data-tone="neutral">
                    <span className="dot" />
                    Simulated panel
                  </span>
                }
              />
            </div>
          )}
        </Panel>

        {/* Audience sim node — real A2A traffic from the launch agents */}
        <Panel className="span-4 panel--flex panel--clip" style={{ minHeight: 320 }}>
          <PanelHead title="Audience_Sim_Node" icon="monitoring">
            <span className="row row--tight">
              <span className="lamp-dot" style={{ width: 8, height: 8, borderRadius: 999, background: launchEvents.length ? "var(--status-success)" : "var(--surface-variant)", display: "block" }} />
            </span>
          </PanelHead>
          <div style={{ flex: 1, minHeight: 0, display: "flex", padding: 12 }}>
            <LiveAgentTerminal events={launchEvents} revealed={launchEvents.length} compact />
          </div>
        </Panel>

        {/* Scene heatmap */}
        <Panel className="span-6 panel--clip panel--flex">
          <PanelHead title="Scene engagement heatmap" icon="local_fire_department">
            {report?.weakest_scene_id && (
              <span className="status-pill" data-tone="warn">
                <span className="dot" />
                Weakest {report.weakest_scene_id}
              </span>
            )}
          </PanelHead>
          {heatmap.length === 0 ? (
            <EmptyState icon="insights" title="No scene scores yet">
              The audience agents produce a per-scene mean once the screening runs.
            </EmptyState>
          ) : (
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th>Scene</th>
                    <th style={{ width: "55%" }}>Mean score</th>
                    <th className="num">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {heatmap.map((row) => (
                    <tr key={row.scene}>
                      <td className={cn(row.weakest && "text-warn")}>
                        {row.scene}
                        {row.weakest && " ⚠"}
                      </td>
                      <td>
                        <Meter value={row.pct} tone={row.weakest ? "warn" : undefined} />
                      </td>
                      <td className="num">{row.score.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {/* Launch scoreboard */}
        <Panel className="span-6 panel--pad panel--flex">
          <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
            <Icon name="rocket_launch" />
            Launch readiness
          </h3>
          <MetricRow>
            <MetricCard label="Tomatometer" value={hasReport ? `${Math.round(report.tomatometer)}%` : "—"} />
            <MetricCard
              label="Audience"
              value={hasReport ? `${Math.round(report.audience_score)}` : "—"}
              tone="plain"
            />
            <MetricCard label="Assets ready" value={`${approved}/${assets.length}`} tone={approved ? "ok" : "plain"} />
            <MetricCard label="Blocked" value={blocked} tone={blocked ? "bad" : "plain"} />
          </MetricRow>
          <p className="muted body-sm" style={{ marginTop: 16 }}>
            {report?.weakest_scene_id
              ? `The recut advisor flagged ${report.weakest_scene_id} as the weakest scene — marketing assets sourced from it are held for review.`
              : "No weak scene flagged for this cut."}
          </p>
        </Panel>

        {/* Marketing assets */}
        <Panel className="span-12 panel--clip">
          <PanelHead title="Marketing assets" icon="campaign">
            <span className="mono-data muted">{assets.length} assets</span>
          </PanelHead>
          {assets.length === 0 ? (
            <EmptyState icon="photo_library" title="No assets generated">
              The marketing agents build reels, memes, posters and copy from the strongest scenes.
            </EmptyState>
          ) : (
            <>
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Type</th>
                      <th>Source scene</th>
                      <th>Status</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.map((a) => (
                      <tr key={a.asset_id}>
                        <td>{a.asset_id}</td>
                        <td>
                          <span className="tag-chip">{a.type}</span>
                        </td>
                        <td className={cn(a.source_scene_id === report?.weakest_scene_id && "text-warn")}>
                          {a.source_scene_id || "—"}
                        </td>
                        <td>
                          <StatusBadge status={a.status} />
                        </td>
                        <td className="muted">
                          {a.content?.caption || a.content?.tagline || a.content?.format || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <PanelFoot>
                <span>
                  {approved} approved · {blocked} blocked
                </span>
                <span>
                  Casting: <span className="text-primary">{statusLabel(state?.casting_status)}</span>
                </span>
              </PanelFoot>
            </>
          )}
        </Panel>
      </div>
      )}
    </>
  );
}

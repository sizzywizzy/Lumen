import { STATUS_COLORS } from "../../lib/utils.js";

// Phase V & VI dashboard: Tomatometer, scene heatmap, marketing assets.
export default function LaunchView({ state }) {
  if (!state) return <div className="empty">No project state yet.</div>;
  const report = state.audience_report;

  return (
    <>
      <div className="card">
        <div className="metric-row">
          <div className="metric">
            <div className="value">🍅 {report.tomatometer}%</div>
            <div className="label">Tomatometer</div>
          </div>
          <div className="metric">
            <div className="value">{report.audience_score}</div>
            <div className="label">Audience score</div>
          </div>
          <div className="metric">
            <div className="value">{report.weakest_scene_id || "—"}</div>
            <div className="label">Weakest scene</div>
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Scene Heatmap</h3>
        <table>
          <thead><tr><th>Scene</th><th>Mean score</th></tr></thead>
          <tbody>
            {Object.entries(report.heatmap).map(([scene, score]) => (
              <tr key={scene}>
                <td>{scene}{scene === report.weakest_scene_id ? " ⚠️" : ""}</td>
                <td>{score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Marketing Assets</h3>
        <table>
          <thead><tr><th>Asset</th><th>Type</th><th>Source</th><th>Status</th><th>Detail</th></tr></thead>
          <tbody>
            {state.marketing_assets.map((a) => (
              <tr key={a.asset_id}>
                <td>{a.asset_id}</td>
                <td>{a.type}</td>
                <td>{a.source_scene_id}</td>
                <td><span className="chip" style={{ color: STATUS_COLORS[a.status] }}>{a.status}</span></td>
                <td>{a.content?.caption || a.content?.tagline || a.content?.format || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

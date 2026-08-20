import { STATUS_COLORS } from "../../lib/utils.js";

// Phase III & IV dashboard: stripboard, burn rate, territory compliance.
export default function ProdView({ state }) {
  if (!state) return <div className="empty">No project state yet.</div>;
  const { schedule, budget_state, compliance_state } = state;

  return (
    <>
      <div className="card">
        <div className="metric-row">
          <div className="metric">
            <div className="value">${Math.round(budget_state.daily_burn).toLocaleString()}</div>
            <div className="label">Daily burn</div>
          </div>
          <div className="metric">
            <div className="value">{schedule.stripboard.length}</div>
            <div className="label">Scenes scheduled</div>
          </div>
          <div className="metric">
            <div className="value">{schedule.conflicts.length}</div>
            <div className="label">Conflicts resolved</div>
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Stripboard</h3>
        <table>
          <thead><tr><th>Date</th><th>Scene</th><th>Venue</th></tr></thead>
          <tbody>
            {schedule.stripboard.map((e) => (
              <tr key={e.scene_id}><td>{e.date}</td><td>{e.scene_id}</td><td>{e.venue}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Compliance by Territory</h3>
        {Object.entries(compliance_state).map(([territory, status]) => (
          <span key={territory} className="chip"
                style={{ color: STATUS_COLORS[status], marginRight: 8 }}>
            {territory}: {status}
          </span>
        ))}
        {Object.keys(compliance_state).length === 0 && <span className="empty">Phase IV not run yet.</span>}
      </div>
    </>
  );
}

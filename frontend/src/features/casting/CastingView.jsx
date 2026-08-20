import { STATUS_COLORS } from "../../lib/utils.js";

// Phase I & II dashboard: leaderboard + disqualifications.
export default function CastingView({ state }) {
  if (!state) return <div className="empty">No project state yet.</div>;
  const ranked = [...state.candidates].sort(
    (a, b) => (b.scores.composite ?? -1) - (a.scores.composite ?? -1)
  );

  return (
    <>
      <div className="card">
        <h3>Casting Status — {state.casting_status}</h3>
        <table>
          <thead>
            <tr>
              <th>Candidate</th><th>Role</th><th>Audition</th><th>Hype</th>
              <th>PR</th><th>Budget</th><th>Composite</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.role_id}</td>
                <td>{c.scores.audition ?? "—"}</td>
                <td>{c.scores.hype ?? "—"}</td>
                <td>{c.scores.pr ?? "—"}</td>
                <td>{c.scores.budget ?? "—"}</td>
                <td><strong>{c.scores.composite ?? "—"}</strong></td>
                <td><span className="chip" style={{ color: STATUS_COLORS[c.status] }}>{c.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Risk Router — Disqualified</h3>
        {state.candidates.filter((c) => c.status === "DISQUALIFIED").map((c) => (
          <div key={c.id}>⛔ <strong>{c.name}</strong> — {c.disqualify_reason}</div>
        ))}
      </div>
    </>
  );
}

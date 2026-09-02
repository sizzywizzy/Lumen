// Summary stat tile: uppercase mono label over a headline-md figure.
// Used by the leaderboard header, schedule metrics and launch metrics.
export default function MetricCard({ label, value, tone = "info", title }) {
  return (
    <div className="stat-tile" title={title}>
      <span className="k">{label}</span>
      <span className="v" data-tone={tone === "info" ? undefined : tone}>
        {value}
      </span>
    </div>
  );
}

export function MetricRow({ children }) {
  return <div className="stat-row">{children}</div>;
}

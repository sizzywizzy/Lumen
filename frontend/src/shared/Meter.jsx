import { clampPercent, cn } from "../lib/utils.js";

// Track + fill bar. `tone` maps to the status palette; the default fill is the
// theme's primary-container (wine in dark, brand blue in light).
export default function Meter({ value, tone, thin = false, className, style }) {
  return (
    <div className={cn("meter", thin && "meter--thin", className)} style={style}>
      <i data-tone={tone} style={{ width: `${clampPercent(value)}%` }} />
    </div>
  );
}

// Leaderboard score cell: numeric readout beside a 64px bar.
export function ScoreCell({ score, tone, dim = false, max = 100 }) {
  if (score === undefined || score === null) {
    return <span className="muted">—</span>;
  }
  const pct = (Number(score) / max) * 100;
  return (
    <div className={cn("score-cell", dim && "dim")}>
      <span>{Number(score).toFixed(1)}</span>
      <Meter value={pct} tone={dim ? "muted" : tone} thin />
    </div>
  );
}

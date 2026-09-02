import { clampPercent } from "../lib/utils.js";

const TONE_STROKE = {
  ok: "var(--status-success)",
  warn: "var(--status-warning)",
  bad: "var(--status-error)",
  primary: "var(--primary-container)",
  secondary: "var(--secondary-container)",
};

// Semicircular burn-rate gauge (Stitch "Burn Rate Meter"): 40r arc across a
// 100x50 box, so the sweep length is pi*40 = 125.66 user units.
const ARC_LEN = Math.PI * 40;

export function ArcGauge({ value, tone = "warn", caption, label }) {
  const pct = clampPercent(value);
  const t = pct / 100;
  const angle = ((180 - 180 * t) * Math.PI) / 180;
  const knobX = 50 + 40 * Math.cos(angle);
  const knobY = 50 - 40 * Math.sin(angle);
  const stroke = TONE_STROKE[tone] || TONE_STROKE.primary;

  return (
    <>
      <div className="gauge-arc">
        <svg viewBox="0 0 100 50" role="img" aria-label={`${label || "Gauge"}: ${Math.round(pct)}%`}>
          <path
            d="M 10 50 A 40 40 0 0 1 90 50"
            fill="none"
            stroke="var(--surface-raised)"
            strokeWidth="8"
            strokeLinecap="round"
          />
          <path
            d="M 10 50 A 40 40 0 0 1 90 50"
            fill="none"
            stroke={stroke}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={ARC_LEN}
            strokeDashoffset={ARC_LEN * (1 - t)}
            style={{ transition: "stroke-dashoffset .6s ease" }}
          />
          <circle cx={knobX} cy={knobY} r="4" fill="var(--on-surface)" />
        </svg>
        <div className="readout">
          <span className="n" style={{ color: stroke }}>
            {Math.round(pct)}%
          </span>
          {caption && <p className="mono-data muted">{caption}</p>}
        </div>
      </div>
      <div className="gauge-scale">
        <span>Safe</span>
        <span className="text-bad">Critical</span>
      </div>
    </>
  );
}

// Circular score ring (Stitch "Projected Reception"). The path is drawn so its
// circumference is exactly 100 units, letting the dash array read as a percent.
const RING = "M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831";

export function RadialGauge({ value, label, tone = "primary", suffix = "%", footer }) {
  const pct = clampPercent(value);
  const stroke = TONE_STROKE[tone] || TONE_STROKE.primary;
  return (
    <div className="gauge-stack">
      <div className="gauge-radial">
        <svg viewBox="0 0 36 36" role="img" aria-label={`${label}: ${Math.round(pct)}${suffix}`}>
          <path d={RING} fill="none" stroke="var(--surface-container-high)" strokeWidth="3" />
          <path
            d={RING}
            fill="none"
            stroke={stroke}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={`${pct}, 100`}
            style={{ transition: "stroke-dasharray .6s ease" }}
          />
        </svg>
        <div className="readout">
          <span className="n">
            {Math.round(pct)}
            {suffix}
          </span>
          <span className="mono-label muted">{label}</span>
        </div>
      </div>
      {footer}
    </div>
  );
}

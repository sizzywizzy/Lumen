// CineNode wordmark — the "o" of Node is a cine camera (lens + twin film reels).
// Same geometry as assets/logo.svg, fixed to the app's dark palette.
export default function CineNodeLogo({ height = 30 }) {
  return (
    <svg
      viewBox="8 18 404 92"
      height={height}
      role="img"
      aria-label="CineNode"
      style={{ display: "block" }}
    >
      <text
        x="24" y="95" textLength="212" lengthAdjust="spacingAndGlyphs"
        style={{ font: "700 76px 'Segoe UI', Inter, system-ui, sans-serif", letterSpacing: "-1px", fill: "var(--text)" }}
      >
        CineN
      </text>
      <g>
        <circle cx="250" cy="41" r="8.5" fill="none" stroke="var(--accent)" strokeWidth="5" />
        <circle cx="276" cy="41" r="8.5" fill="none" stroke="var(--accent)" strokeWidth="5" />
        <circle cx="263" cy="73" r="22" fill="none" stroke="var(--accent)" strokeWidth="11" />
        <circle cx="263" cy="73" r="12.5" fill="none" stroke="var(--accent-2)" strokeWidth="3.5" />
        <circle cx="263" cy="73" r="6" fill="var(--accent-2)" />
        <circle cx="259" cy="69" r="2.4" fill="#ffffff" />
      </g>
      <text
        x="290" y="95"
        style={{ font: "700 76px 'Segoe UI', Inter, system-ui, sans-serif", letterSpacing: "-1px", fill: "var(--text)" }}
      >
        de
      </text>
    </svg>
  );
}
